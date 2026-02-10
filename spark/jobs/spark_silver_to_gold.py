"""
Batch Spark job: Silver -> Gold (Delta Lake + ClickHouse)
Produces star-schema / KPI aggregate tables:
- dim_users, dim_pages (dimensions)
- fact_events (fact table)
- KPIs: DAU, events per source, purchases per page, conversion rate
Gold Delta tables are written to the lakehouse.
Gold KPI summaries are also written to ClickHouse for historical dashboards.
"""

import os
import sys

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    count,
    countDistinct,
    current_timestamp,
    lit,
    to_date,
    sum as spark_sum,
    round as spark_round,
    when,
)
from clickhouse_driver import Client

LAKEHOUSE_PATH = os.getenv("LAKEHOUSE_PATH", "/data/lakehouse")
SILVER_PATH = f"{LAKEHOUSE_PATH}/silver/user_events"
GOLD_PATH = f"{LAKEHOUSE_PATH}/gold"

CH_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CH_PORT = os.getenv("CLICKHOUSE_PORT", "8123")
CH_DB = os.getenv("CLICKHOUSE_DB", "default")

CH_URL = f"jdbc:clickhouse://{CH_HOST}:{CH_PORT}/{CH_DB}"
CH_PROPERTIES = {
    "driver": "com.clickhouse.jdbc.ClickHouseDriver",
    # "ssl": "false"
}


def write_ch(df, table_name):
    """
    Write DataFrame to ClickHouse with automatic deduplication.

    Strategy:
    1. Delete today's data from the table (avoids duplicates)
    2. Write new data
    3. ReplacingMergeTree handles any remaining duplicates during merges

    This ensures each DAG run replaces values instead of accumulating duplicates.
    """
    # Connect to ClickHouse
    try:
        ch_client = Client(host=CH_HOST, port=9000, database=CH_DB)

        # Delete today's data before writing new data
        # This prevents duplicates from accumulating
        delete_query = f"ALTER TABLE {table_name} DELETE WHERE event_date = today()"
        print(f"Deleting today's data from {table_name}...")
        ch_client.execute(delete_query)
        print(f"✓ Deleted existing data from {table_name}")
    except Exception as e:
        print(f"⚠ Could not delete existing data from {table_name}: {str(e)}")
        print("  Continuing with write (ReplacingMergeTree will eventually deduplicate)...")

    # Add updated_at timestamp
    enriched = df.withColumn("updated_at", current_timestamp())

    # Write to ClickHouse
    (
        enriched.write
        .mode("append")
        .jdbc(CH_URL, table_name, properties=CH_PROPERTIES)
    )

    # Force optimization to deduplicate immediately
    try:
        ch_client.execute(f"OPTIMIZE TABLE {table_name} FINAL")
        print(f"✓ Optimized {table_name}")
    except Exception as e:
        print(f"⚠ Could not optimize {table_name}: {str(e)}")

    print(f"✓ Written to {table_name}")


def main():
    spark = (
        SparkSession.builder
        .appName("silver-to-gold-clickhouse")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        # Ensure the jar name matches exactly what we downloaded in Dockerfile
        .config("spark.jars", "/opt/spark/extra-jars/clickhouse-jdbc-0.6.0-all.jar")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # Read Silver
    try:
        silver_df = spark.read.format("delta").load(SILVER_PATH)
    except Exception as e:
        print(f"ERROR: Cannot read Silver table at {SILVER_PATH}: {e}")
        sys.exit(1)

    silver_count = silver_df.count()
    print(f"Silver records read: {silver_count}")
    if silver_count == 0:
        print("No data in Silver. Exiting.")
        sys.exit(0)

    silver_df = silver_df.withColumn("event_date", to_date(col("event_timestamp")))
    silver_df.cache()

    # ============================================================
    # DIMENSION TABLES
    # ============================================================

    # dim_users: distinct user_id with latest source
    dim_users = (
        silver_df
        .groupBy("user_id")
        .agg(
            count("*").alias("total_events"),
            countDistinct("source").alias("source_count"),
        )
    )
    dim_users.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/dim_users")
    print(f"dim_users: {dim_users.count()} records")

    # dim_pages: distinct pages with event counts
    dim_pages = (
        silver_df
        .groupBy("page")
        .agg(count("*").alias("total_events"))
    )
    dim_pages.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/dim_pages")
    print(f"dim_pages: {dim_pages.count()} records")

    # ============================================================
    # FACT TABLE
    # ============================================================

    fact_events = silver_df.select(
        "event_id", "user_id", "event_type", "page",
        "event_timestamp", "source", "event_date",
    )
    (
        fact_events.write
        .format("delta")
        .mode("overwrite")
        .partitionBy("event_date")
        .save(f"{GOLD_PATH}/fact_events")
    )
    print(f"fact_events: {fact_events.count()} records")

    # ============================================================
    # KPI AGGREGATES -> ClickHouse
    # ============================================================

    # 1. DAU (Daily Active Users)
    dau = (
        silver_df
        .groupBy("event_date")
        .agg(countDistinct("user_id").alias("dau_count"))
    )
    dau.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/kpi_dau")
    write_ch(dau, "gold.daily_active_users")
    print(f"DAU records: {dau.count()}")

    # 2. Events per source per day
    events_per_source = (
        silver_df
        .groupBy("event_date", "source")
        .agg(count("*").alias("event_count"))
    )
    events_per_source.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/kpi_events_per_source")
    write_ch(events_per_source, "gold.events_per_source_daily")
    print(f"Events per source records: {events_per_source.count()}")

    # 3. Purchases per page per day
    purchases_per_page = (
        silver_df
        .filter(col("event_type") == "purchase")
        .groupBy("event_date", "page")
        .agg(count("*").alias("purchase_count"))
    )
    purchases_per_page.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/kpi_purchases_per_page")
    write_ch(purchases_per_page, "gold.purchases_per_page_daily")
    print(f"Purchases per page records: {purchases_per_page.count()}")

    # 4. Daily Revenue (sum of purchase prices)
    revenue_daily = (
        silver_df
        .filter(col("event_type") == "purchase")
        .groupBy("event_date")
        .agg(
            spark_sum("price").alias("total_revenue"),
            count("*").alias("total_purchases"),
            spark_round(spark_sum("price") / count("*"), 2).alias("avg_order_value")
        )
    )
    revenue_daily.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/kpi_revenue_daily")
    write_ch(revenue_daily, "gold.revenue_daily")
    print(f"Revenue daily records: {revenue_daily.count()}")

    # 5. Category Sales (units and revenue per category per day)
    category_sales = (
        silver_df
        .filter(col("event_type") == "purchase")
        .groupBy("event_date", "category")
        .agg(
            count("*").alias("units_sold"),
            spark_sum("price").alias("category_revenue")
        )
    )
    category_sales.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/kpi_category_sales")
    write_ch(category_sales, "gold.category_sales_daily")
    print(f"Category sales records: {category_sales.count()}")

    # 6. Cart Abandonment Rate (users who add_to_cart but don't purchase)
    cart_adds = (
        silver_df
        .filter(col("event_type") == "add_to_cart")
        .groupBy("event_date", "session_id")
        .agg(count("*").alias("cart_add_count"))
        .select("event_date", "session_id")
    )

    purchases = (
        silver_df
        .filter(col("event_type") == "purchase")
        .groupBy("event_date", "session_id")
        .agg(count("*").alias("purchase_count"))
        .select("event_date", "session_id", "purchase_count")
    )

    cart_abandonment = (
        cart_adds
        .join(purchases, ["event_date", "session_id"], "left")
        .groupBy("event_date")
        .agg(
            count("*").alias("sessions_with_cart"),
            spark_sum(when(col("purchase_count").isNull(), 1).otherwise(0)).alias("abandoned_carts"),
        )
        .withColumn(
            "abandonment_rate",
            spark_round(col("abandoned_carts") / col("sessions_with_cart"), 4)
        )
    )
    cart_abandonment.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/kpi_cart_abandonment")
    write_ch(cart_abandonment, "gold.cart_abandonment_daily")
    print(f"Cart abandonment records: {cart_abandonment.count()}")

    # 7. Conversion Rate (unique buyers / DAU, not total_purchases / total_events)
    unique_buyers = (
        silver_df
        .filter(col("event_type") == "purchase")
        .groupBy("event_date")
        .agg(countDistinct("user_id").alias("unique_buyers"))
    )

    conversion = (
        dau
        .join(unique_buyers, "event_date", "left")
        .fillna(0, subset=["unique_buyers"])
        .withColumn("conversion_rate",
                    spark_round(col("unique_buyers") / col("dau_count"), 4))
    )
    conversion.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/kpi_conversion_rate")
    write_ch(conversion, "gold.conversion_rate_daily")
    print(f"Conversion rate records: {conversion.count()}")

    silver_df.unpersist()
    spark.stop()
    print("Gold layer complete (Delta + ClickHouse).")


if __name__ == "__main__":
    main()
