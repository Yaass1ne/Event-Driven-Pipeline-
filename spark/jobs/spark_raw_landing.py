"""
Spark Structured Streaming: Kafka -> Bronze (Delta Lake)
ELT load only: schema validation, minimal parsing, date partitioning.
No business aggregations.
"""

import os

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, to_date
from pyspark.sql.types import (
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
LAKEHOUSE_PATH = os.getenv("LAKEHOUSE_PATH", "/data/lakehouse")
CHECKPOINT_PATH = os.getenv("CHECKPOINT_PATH", "/data/checkpoints")

BRONZE_PATH = f"{LAKEHOUSE_PATH}/bronze/user_events"
BRONZE_CHECKPOINT = f"{CHECKPOINT_PATH}/raw_landing"

EVENT_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("user_id", IntegerType(), False),
    StructField("event_type", StringType(), False),
    StructField("page", StringType(), True),
    StructField("timestamp", StringType(), False),
    StructField("source", StringType(), False),
    # E-commerce fields
    StructField("session_id", StringType(), False),
    StructField("price", StringType(), True),  # String to handle null, cast to double later
    StructField("category", StringType(), True),
    StructField("product_id", StringType(), True),
])


def main():
    spark = (
        SparkSession.builder
        .appName("raw-landing-kafka-to-bronze")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
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

    # Parse JSON value
    parsed_df = (
        kafka_df
        .selectExpr("CAST(value AS STRING) as json_str", "timestamp as kafka_timestamp")
        .select(
            from_json(col("json_str"), EVENT_SCHEMA).alias("data"),
            col("kafka_timestamp"),
        )
        .select(
            col("data.event_id").alias("event_id"),
            col("data.user_id").alias("user_id"),
            col("data.event_type").alias("event_type"),
            col("data.page").alias("page"),
            col("data.timestamp").cast(TimestampType()).alias("event_timestamp"),
            col("data.source").alias("source"),
            # E-commerce fields
            col("data.session_id").alias("session_id"),
            col("data.price").cast("double").alias("price"),
            col("data.category").alias("category"),
            col("data.product_id").alias("product_id"),
            col("kafka_timestamp").alias("ingestion_timestamp"),
        )
        .withColumn("event_date", to_date(col("event_timestamp")))
    )

    # Write to Delta Bronze table, partitioned by event_date
    query = (
        parsed_df.writeStream
        .format("delta")
        .outputMode("append")
        .option("checkpointLocation", BRONZE_CHECKPOINT)
        .partitionBy("event_date")
        .start(BRONZE_PATH)
    )

    print(f"Raw landing streaming to {BRONZE_PATH}")
    query.awaitTermination()


if __name__ == "__main__":
    main()
