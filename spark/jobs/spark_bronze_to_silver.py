"""
Batch Spark job: Bronze -> Silver (Delta Lake)
- Deduplicate by event_id
- Validate / clean data
- Cast types properly
- Partition by event_date
"""

import os
import sys

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_date

LAKEHOUSE_PATH = os.getenv("LAKEHOUSE_PATH", "/data/lakehouse")

BRONZE_PATH = f"{LAKEHOUSE_PATH}/bronze/user_events"
SILVER_PATH = f"{LAKEHOUSE_PATH}/silver/user_events"

VALID_EVENT_TYPES = ["login", "view", "add_to_cart", "purchase", "logout"]
VALID_SOURCES = ["web", "mobile"]
VALID_CATEGORIES = ["Electronics", "Fashion", "Home", "Books", "Sports", "Beauty", "Toys", "Food"]


def main():
    spark = (
        SparkSession.builder
        .appName("bronze-to-silver")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # Read Bronze Delta table
    try:
        bronze_df = spark.read.format("delta").load(BRONZE_PATH)
    except Exception as e:
        print(f"ERROR: Cannot read Bronze table at {BRONZE_PATH}: {e}")
        sys.exit(1)

    bronze_count = bronze_df.count()
    print(f"Bronze records read: {bronze_count}")

    if bronze_count == 0:
        print("No data in Bronze. Exiting.")
        sys.exit(0)

    # --- Cleaning & Validation ---
    cleaned_df = (
        bronze_df
        # Drop rows with null required fields
        .filter(
            col("event_id").isNotNull()
            & col("user_id").isNotNull()
            & col("event_type").isNotNull()
            & col("event_timestamp").isNotNull()
            & col("source").isNotNull()
            & col("session_id").isNotNull()  # E-commerce: session required
        )
        # Validate event_type
        .filter(col("event_type").isin(VALID_EVENT_TYPES))
        # Validate source
        .filter(col("source").isin(VALID_SOURCES))
        # Validate user_id > 0
        .filter(col("user_id") > 0)
        # E-commerce: Validate category (if present, must be in valid list)
        .filter(
            col("category").isNull() | col("category").isin(VALID_CATEGORIES)
        )
        # E-commerce: Validate price (if present, must be positive)
        .filter(
            col("price").isNull() | (col("price") > 0)
        )
        # E-commerce: Contextual validation - purchases MUST have product data
        .filter(
            (col("event_type") != "purchase") |
            (
                (col("event_type") == "purchase") &
                col("price").isNotNull() &
                col("product_id").isNotNull() &
                col("category").isNotNull()
            )
        )
    )

    # --- Deduplicate by event_id (keep first by ingestion_timestamp) ---
    deduped_df = (
        cleaned_df
        .orderBy("ingestion_timestamp")
        .dropDuplicates(["event_id"])
    )

    # Ensure event_date partition column
    silver_df = deduped_df.withColumn("event_date", to_date(col("event_timestamp")))

    silver_count = silver_df.count()
    dropped = bronze_count - silver_count
    print(f"Silver records after clean+dedupe: {silver_count} (dropped {dropped})")

    # Write Silver Delta table (overwrite for full rebuild; use merge for incremental)
    (
        silver_df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .partitionBy("event_date")
        .save(SILVER_PATH)
    )

    print(f"Silver table written to {SILVER_PATH}")
    spark.stop()


if __name__ == "__main__":
    main()
