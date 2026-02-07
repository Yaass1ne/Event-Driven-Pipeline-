"""
Batch Spark job: Silver -> Gold (Delta Lake + PostgreSQL)
Produces star-schema / KPI aggregate tables:
- dim_users, dim_pages (dimensions)
- fact_events (fact table)
- KPIs: DAU, events per source, purchases per page, conversion rate
Gold Delta tables are written to the lakehouse.
Gold KPI summaries are also written to PostgreSQL for historical dashboards.
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
)

LAKEHOUSE_PATH = os.getenv("LAKEHOUSE_PATH", "/data/lakehouse")
SILVER_PATH = f"{LAKEHOUSE_PATH}/silver/user_events"
GOLD_PATH = f"{LAKEHOUSE_PATH}/gold"

PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB = os.getenv("POSTGRES_DB", "serving")
PG_USER = os.getenv("POSTGRES_USER", "platform")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "platform123")

PG_URL = f"jdbc:postgresql://{PG_HOST}:{PG_PORT}/{PG_DB}"
PG_PROPERTIES = {
    "user": PG_USER,
    "password": PG_PASSWORD,
    "driver": "org.postgresql.Driver",
}


def write_pg(df, table_name):
    """Write DataFrame to PostgreSQL, overwriting existing data."""
    enriched = df.withColumn("updated_at", current_timestamp())
    enriched.write.mode("overwrite").jdbc(PG_URL, table_name, properties=PG_PROPERTIES)


def main():
    spark = (
        SparkSession.builder
        .appName("silver-to-gold")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.jars", "/opt/spark/extra-jars/postgresql-42.7.1.jar")
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
    # KPI AGGREGATES
    # ============================================================

    # 1. DAU (Daily Active Users)
    dau = (
        silver_df
        .groupBy("event_date")
        .agg(countDistinct("user_id").alias("dau_count"))
    )
    dau.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/kpi_dau")
    write_pg(dau, "gold.daily_active_users")
    print(f"DAU records: {dau.count()}")

    # 2. Events per source per day
    events_per_source = (
        silver_df
        .groupBy("event_date", "source")
        .agg(count("*").alias("event_count"))
    )
    events_per_source.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/kpi_events_per_source")
    write_pg(events_per_source, "gold.events_per_source_daily")
    print(f"Events per source records: {events_per_source.count()}")

    # 3. Purchases per page per day
    purchases_per_page = (
        silver_df
        .filter(col("event_type") == "purchase")
        .groupBy("event_date", "page")
        .agg(count("*").alias("purchase_count"))
    )
    purchases_per_page.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/kpi_purchases_per_page")
    write_pg(purchases_per_page, "gold.purchases_per_page_daily")
    print(f"Purchases per page records: {purchases_per_page.count()}")

    # 4. Conversion rate per day (purchases / total events)
    total_events = silver_df.groupBy("event_date").agg(count("*").alias("total_events"))
    total_purchases = (
        silver_df
        .filter(col("event_type") == "purchase")
        .groupBy("event_date")
        .agg(count("*").alias("total_purchases"))
    )
    conversion = (
        total_events
        .join(total_purchases, "event_date", "left")
        .fillna(0, subset=["total_purchases"])
        .withColumn("conversion_rate", col("total_purchases") / col("total_events"))
    )
    conversion.write.format("delta").mode("overwrite").save(f"{GOLD_PATH}/kpi_conversion_rate")
    write_pg(conversion, "gold.conversion_rate_daily")
    print(f"Conversion rate records: {conversion.count()}")

    silver_df.unpersist()
    spark.stop()
    print("Gold layer complete.")


if __name__ == "__main__":
    main()
