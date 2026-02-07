"""
Spark Structured Streaming: Kafka -> PostgreSQL (real-time aggregates)
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

EVENT_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("user_id", IntegerType(), False),
    StructField("event_type", StringType(), False),
    StructField("page", StringType(), True),
    StructField("timestamp", StringType(), False),
    StructField("source", StringType(), False),
])


def write_to_postgres(batch_df, batch_id, table_name):
    """Write a micro-batch to PostgreSQL, appending new data for time-series visualization."""
    if batch_df.isEmpty():
        return
    enriched = batch_df.withColumn("updated_at", current_timestamp())
    (
        enriched.write
        .mode("append")
        .jdbc(PG_URL, table_name, properties=PG_PROPERTIES)
    )


def main():
    spark = (
        SparkSession.builder
        .appName("fast-agg-kafka-to-postgres")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.jars", "/opt/spark/extra-jars/postgresql-42.7.1.jar")
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
        .foreachBatch(lambda df, bid: write_to_postgres(df, bid, "realtime.events_per_minute"))
        .option("checkpointLocation", f"{CHECKPOINT_PATH}/fast_agg_events_per_min")
        .trigger(processingTime="30 seconds")
        .start()
    )

    # ----- Aggregate 2: Logins per source per minute -----
    logins_per_source = (
        parsed_df
        .filter(col("event_type") == "login")
        .groupBy(
            window(col("event_timestamp"), "1 minute"),
            col("source"),
        )
        .agg(count("*").alias("login_count"))
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("source"),
            col("login_count"),
        )
    )

    q2 = (
        logins_per_source.writeStream
        .outputMode("update")
        .foreachBatch(lambda df, bid: write_to_postgres(df, bid, "realtime.logins_per_source"))
        .option("checkpointLocation", f"{CHECKPOINT_PATH}/fast_agg_logins_per_source")
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
        .foreachBatch(lambda df, bid: write_to_postgres(df, bid, "realtime.purchases_per_minute"))
        .option("checkpointLocation", f"{CHECKPOINT_PATH}/fast_agg_purchases_per_min")
        .trigger(processingTime="30 seconds")
        .start()
    )

    print("Fast-agg streaming queries started (3 aggregate streams)")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
