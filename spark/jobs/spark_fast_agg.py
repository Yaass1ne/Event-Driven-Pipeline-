"""
Spark Structured Streaming: Kafka -> ClickHouse (real-time aggregates)
Computes windowed aggregates with watermarks and writes to serving store.
- Events per minute by event_type
- Logins per source per minute
- Purchases per minute
"""

import os

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    count,
    current_timestamp,
    from_json,
    window,
    sum as spark_sum,
)
from pyspark.sql.types import (
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
CHECKPOINT_PATH = os.getenv("CHECKPOINT_PATH", "/data/checkpoints")

CH_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CH_PORT = os.getenv("CLICKHOUSE_PORT", "8123")
CH_DB = os.getenv("CLICKHOUSE_DB", "default")

CH_URL = f"jdbc:clickhouse://{CH_HOST}:{CH_PORT}/{CH_DB}"
CH_PROPERTIES = {
    "driver": "com.clickhouse.jdbc.ClickHouseDriver",
    # "ssl": "false" 
}

EVENT_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("user_id", IntegerType(), False),
    StructField("event_type", StringType(), False),
    StructField("page", StringType(), True),
    StructField("timestamp", StringType(), False),
    StructField("source", StringType(), False),
    # E-commerce fields
    StructField("session_id", StringType(), False),
    StructField("price", StringType(), True),
    StructField("category", StringType(), True),
    StructField("product_id", StringType(), True),
])


def write_to_clickhouse(batch_df, batch_id, table_name):
    """Write a micro-batch to ClickHouse."""
    if batch_df.isEmpty():
        return
    enriched = batch_df.withColumn("updated_at", current_timestamp())
    (
        enriched.write
        .mode("append")
        .jdbc(CH_URL, table_name, properties=CH_PROPERTIES)
    )


def main():
    spark = (
        SparkSession.builder
        .appName("fast-agg-kafka-to-clickhouse")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        # Ensure the jar name matches exactly what we downloaded in Dockerfile
        .config("spark.jars", "/opt/spark/extra-jars/clickhouse-jdbc-0.6.0-all.jar")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # Read from Kafka
    kafka_df = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", "user-events")
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .load()
    )

    # Parse and cast
    parsed_df = (
        kafka_df
        .selectExpr("CAST(value AS STRING) as json_str")
        .select(from_json(col("json_str"), EVENT_SCHEMA).alias("data"))
        .select(
            col("data.event_id"),
            col("data.user_id"),
            col("data.event_type"),
            col("data.page"),
            col("data.timestamp").cast(TimestampType()).alias("event_timestamp"),
            col("data.source"),
            # E-commerce fields
            col("data.session_id"),
            col("data.price").cast("double").alias("price"),
            col("data.category"),
            col("data.product_id"),
        )
        .withWatermark("event_timestamp", "2 minutes")
    )

    # ----- Aggregate 1: Events per minute by event_type -----
    events_per_min = (
        parsed_df
        .groupBy(
            window(col("event_timestamp"), "1 minute"),
            col("event_type"),
        )
        .agg(count("*").alias("event_count"))
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("event_type"),
            col("event_count"),
        )
    )

    q1 = (
        events_per_min.writeStream
        .outputMode("update")
        .foreachBatch(lambda df, bid: write_to_clickhouse(df, bid, "realtime.events_per_minute"))
        .option("checkpointLocation", f"{CHECKPOINT_PATH}/fast_agg_events_per_min")
        .trigger(processingTime="30 seconds")
        .start()
    )

    # ----- Aggregate 2: Real-time Revenue per minute (REPLACES logins_per_source) -----
    revenue_per_min = (
        parsed_df
        .filter(col("event_type") == "purchase")
        .groupBy(window(col("event_timestamp"), "1 minute"))
        .agg(
            spark_sum("price").alias("revenue"),
            count("*").alias("purchase_count"),
        )
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("revenue"),
            col("purchase_count"),
        )
    )

    q2 = (
        revenue_per_min.writeStream
        .outputMode("update")
        .foreachBatch(lambda df, bid: write_to_clickhouse(df, bid, "realtime.revenue_per_minute"))
        .option("checkpointLocation", f"{CHECKPOINT_PATH}/fast_agg_revenue_per_min")
        .trigger(processingTime="30 seconds")
        .start()
    )

    # ----- Aggregate 3: Purchases per minute -----
    purchases_per_min = (
        parsed_df
        .filter(col("event_type") == "purchase")
        .groupBy(window(col("event_timestamp"), "1 minute"))
        .agg(count("*").alias("purchase_count"))
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("purchase_count"),
        )
    )

    q3 = (
        purchases_per_min.writeStream
        .outputMode("update")
        .foreachBatch(lambda df, bid: write_to_clickhouse(df, bid, "realtime.purchases_per_minute"))
        .option("checkpointLocation", f"{CHECKPOINT_PATH}/fast_agg_purchases_per_min")
        .trigger(processingTime="30 seconds")
        .start()
    )

    # ----- Aggregate 4: Category Velocity (purchases per category per minute) -----
    category_velocity = (
        parsed_df
        .filter(col("event_type") == "purchase")
        .groupBy(
            window(col("event_timestamp"), "1 minute"),
            col("category"),
        )
        .agg(
            count("*").alias("purchase_count"),
            spark_sum("price").alias("revenue"),
        )
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("category"),
            col("purchase_count"),
            col("revenue"),
        )
    )

    q4 = (
        category_velocity.writeStream
        .outputMode("update")
        .foreachBatch(lambda df, bid: write_to_clickhouse(df, bid, "realtime.category_velocity"))
        .option("checkpointLocation", f"{CHECKPOINT_PATH}/fast_agg_category_velocity")
        .trigger(processingTime="30 seconds")
        .start()
    )

    print("Fast-agg streaming queries started (4 aggregate streams) -> ClickHouse")
    print("  1. Events per minute by type")
    print("  2. Revenue per minute")
    print("  3. Purchases per minute")
    print("  4. Category velocity")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
