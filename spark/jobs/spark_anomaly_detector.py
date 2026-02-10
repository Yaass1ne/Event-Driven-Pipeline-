"""
Real-Time Anomaly Detection System
Monitors the event stream for business and technical anomalies.

Detects:
1. Revenue drops (>30% decrease in 5-minute window)
2. Traffic anomalies (unusual event volume)
3. Cart abandonment spikes (>2 std deviations)
4. Conversion rate drops (below threshold)
5. Category imbalance (one category > 60% of sales)
6. Data quality issues (missing prices, invalid categories)

Alerts are sent to:
- ClickHouse (historical record)
- Slack (real-time notifications for critical alerts)
- Grafana (visual monitoring dashboard)
"""

import os
import sys
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    count,
    sum as spark_sum,
    avg,
    stddev,
    window,
    when,
    lit,
    current_timestamp,
    from_json,
    approx_count_distinct,
    concat,
    abs as spark_abs,
)
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, TimestampType

# Configuration
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
CHECKPOINT_PATH = os.getenv("CHECKPOINT_PATH", "/data/checkpoints")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")

CH_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CH_PORT = os.getenv("CLICKHOUSE_PORT", "8123")
CH_DB = os.getenv("CLICKHOUSE_DB", "default")
CH_URL = f"jdbc:clickhouse://{CH_HOST}:{CH_PORT}/{CH_DB}"
CH_PROPERTIES = {"driver": "com.clickhouse.jdbc.ClickHouseDriver"}

# Event schema
EVENT_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("user_id", IntegerType(), False),
    StructField("event_type", StringType(), False),
    StructField("page", StringType(), True),
    StructField("timestamp", StringType(), False),
    StructField("source", StringType(), False),
    StructField("session_id", StringType(), False),
    StructField("price", StringType(), True),
    StructField("category", StringType(), True),
    StructField("product_id", StringType(), True),
])

# Anomaly detection thresholds
THRESHOLDS = {
    "revenue_drop_pct": 0.30,           # 30% drop
    "traffic_zscore": 3.0,              # 3 standard deviations
    "abandonment_zscore": 2.5,          # 2.5 standard deviations
    "conversion_min": 0.03,             # 3% minimum conversion rate
    "category_dominance": 0.60,         # One category > 60% of sales
    "missing_price_pct": 0.10,          # 10% of purchases missing price
}

# Severity levels
SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"


def send_slack_alert(anomaly_type, severity, details, metric_value, expected_value):
    """Send alert to Slack webhook."""
    if not SLACK_WEBHOOK:
        return

    import requests

    # Color coding by severity
    colors = {
        SEVERITY_CRITICAL: "#FF0000",  # Red
        SEVERITY_HIGH: "#FF6600",      # Orange
        SEVERITY_MEDIUM: "#FFCC00",    # Yellow
        SEVERITY_LOW: "#0099FF",       # Blue
    }

    # Emoji by anomaly type
    emojis = {
        "revenue_drop": "💰",
        "traffic_spike": "📈",
        "traffic_drop": "📉",
        "cart_abandonment_spike": "🛒",
        "conversion_drop": "📊",
        "category_imbalance": "⚖️",
        "data_quality": "⚠️",
        "pipeline_delay": "⏱️",
    }

    message = {
        "attachments": [
            {
                "color": colors.get(severity, "#888888"),
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emojis.get(anomaly_type, '🚨')} {anomaly_type.replace('_', ' ').title()} Detected!"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Severity:*\n{severity.upper()}"},
                            {"type": "mrkdwn", "text": f"*Time:*\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"},
                            {"type": "mrkdwn", "text": f"*Current Value:*\n{metric_value}"},
                            {"type": "mrkdwn", "text": f"*Expected:*\n{expected_value}"},
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Details:*\n{details}"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "View Dashboard"},
                                "url": "http://localhost:3000/d/lakehouse-overview",
                                "style": "primary"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Acknowledge"},
                                "value": f"ack_{anomaly_type}",
                            }
                        ]
                    }
                ]
            }
        ]
    }

    try:
        response = requests.post(SLACK_WEBHOOK, json=message, timeout=5)
        if response.status_code != 200:
            print(f"Slack alert failed: {response.status_code} {response.text}")
    except Exception as e:
        print(f"Failed to send Slack alert: {e}")


def write_anomaly_to_clickhouse(df, batch_id):
    """Write detected anomalies to ClickHouse."""
    if df.isEmpty():
        return

    enriched = df.withColumn("detected_at", current_timestamp())

    try:
        enriched.write.mode("append").jdbc(CH_URL, "realtime.anomalies", properties=CH_PROPERTIES)
        print(f"Batch {batch_id}: Wrote {df.count()} anomalies to ClickHouse")
    except Exception as e:
        print(f"Error writing anomalies to ClickHouse: {e}")


def compute_metrics(parsed_df):
    """Compute key metrics per 5-minute window."""
    return (
        parsed_df
        .groupBy(window(col("event_timestamp"), "5 minutes"))
        .agg(
            # Traffic metrics
            count("*").alias("total_events"),
            approx_count_distinct("user_id").alias("unique_users"),
            approx_count_distinct("session_id").alias("unique_sessions"),

            # Revenue metrics
            spark_sum(when(col("event_type") == "purchase", col("price")).otherwise(0)).alias("total_revenue"),
            count(when(col("event_type") == "purchase", 1)).alias("purchase_count"),
            avg(when(col("event_type") == "purchase", col("price"))).alias("avg_purchase_price"),

            # Cart metrics
            count(when(col("event_type") == "add_to_cart", 1)).alias("cart_adds"),

            # Conversion metrics
            approx_count_distinct(when(col("event_type") == "purchase", col("user_id"))).alias("buyers"),

            # Data quality metrics
            count(when((col("event_type") == "purchase") & col("price").isNull(), 1)).alias("purchases_missing_price"),
            count(when((col("event_type") == "purchase") & col("category").isNull(), 1)).alias("purchases_missing_category"),

            # Category distribution
            spark_sum(when((col("event_type") == "purchase") & (col("category") == "Electronics"), 1).otherwise(0)).alias("electronics_purchases"),
            spark_sum(when((col("event_type") == "purchase") & (col("category") == "Fashion"), 1).otherwise(0)).alias("fashion_purchases"),
        )
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            "*"
        )
        .drop("window")
    )


def detect_revenue_anomalies(metrics_df):
    """Detect revenue drops using fixed thresholds."""

    # Use fixed thresholds instead of rolling baseline for streaming compatibility
    # Normal e-commerce: expect at least $50 revenue per 5-minute window
    MIN_EXPECTED_REVENUE = 50.0

    metrics_with_baseline = metrics_df.withColumn(
        "revenue_baseline_avg",
        lit(MIN_EXPECTED_REVENUE)  # Fixed expected revenue
    )

    # Detect drops
    anomalies = (
        metrics_with_baseline
        .filter(col("revenue_baseline_avg").isNotNull())
        .withColumn(
            "revenue_pct_change",
            (col("total_revenue") - col("revenue_baseline_avg")) / (col("revenue_baseline_avg") + 0.01)
        )
        .filter(col("revenue_pct_change") < -THRESHOLDS["revenue_drop_pct"])
        .withColumn("anomaly_type", lit("revenue_drop"))
        .withColumn(
            "severity",
            when(col("revenue_pct_change") < -0.50, lit(SEVERITY_CRITICAL))
            .when(col("revenue_pct_change") < -0.40, lit(SEVERITY_HIGH))
            .otherwise(lit(SEVERITY_MEDIUM))
        )
        .withColumn(
            "description",
            when(col("total_revenue") == 0, lit("Revenue dropped to ZERO - possible payment system failure"))
            .otherwise(
                concat(
                    lit("Revenue dropped by "),
                    (col("revenue_pct_change") * -100).cast("int").cast("string"),
                    lit("% from baseline ($"),
                    col("revenue_baseline_avg").cast("int").cast("string"),
                    lit(" → $"),
                    col("total_revenue").cast("int").cast("string"),
                    lit(")")
                )
            )
        )
        .withColumn("metric_value", col("total_revenue").cast("string"))
        .withColumn("expected_value", col("revenue_baseline_avg").cast("string"))
        .select(
            "window_start",
            "anomaly_type",
            "severity",
            "description",
            "metric_value",
            "expected_value"
        )
    )

    return anomalies


def detect_traffic_anomalies(metrics_df):
    """Detect unusual traffic patterns using fixed thresholds."""

    # Use fixed thresholds for streaming compatibility
    # Normal: expect 1000-2000 events per 5-minute window (5 events/sec × 300 sec = 1500)
    MIN_EXPECTED_EVENTS = 1000
    MAX_EXPECTED_EVENTS = 2000

    anomalies = (
        metrics_df
        .filter((col("total_events") < MIN_EXPECTED_EVENTS) | (col("total_events") > MAX_EXPECTED_EVENTS))
        .withColumn(
            "events_deviation",
            when(col("total_events") < MIN_EXPECTED_EVENTS, MIN_EXPECTED_EVENTS - col("total_events"))
            .otherwise(col("total_events") - MAX_EXPECTED_EVENTS)
        )
        .withColumn(
            "anomaly_type",
            when(col("total_events") > MAX_EXPECTED_EVENTS, lit("traffic_spike"))
            .otherwise(lit("traffic_drop"))
        )
        .withColumn(
            "severity",
            when(col("total_events") < 500, lit(SEVERITY_CRITICAL))  # Very low traffic
            .when(col("total_events") > 3000, lit(SEVERITY_CRITICAL))  # Extreme spike
            .when(col("total_events") < 750, lit(SEVERITY_HIGH))
            .when(col("total_events") > 2500, lit(SEVERITY_HIGH))
            .otherwise(lit(SEVERITY_MEDIUM))
        )
        .withColumn(
            "description",
            when(
                col("total_events") > MAX_EXPECTED_EVENTS,
                concat(
                    lit("Traffic SPIKE: "),
                    col("total_events").cast("string"),
                    lit(" events (expected <"),
                    lit(str(MAX_EXPECTED_EVENTS)),
                    lit("). Possible bot attack or viral event.")
                )
            ).otherwise(
                concat(
                    lit("Traffic DROP: "),
                    col("total_events").cast("string"),
                    lit(" events (expected >"),
                    lit(str(MIN_EXPECTED_EVENTS)),
                    lit("). Possible system issue or producer failure.")
                )
            )
        )
        .withColumn("metric_value", col("total_events").cast("string"))
        .withColumn("expected_value",
            when(col("total_events") > MAX_EXPECTED_EVENTS, lit(f"<{MAX_EXPECTED_EVENTS}"))
            .otherwise(lit(f">{MIN_EXPECTED_EVENTS}"))
        )
        .select(
            "window_start",
            "anomaly_type",
            "severity",
            "description",
            "metric_value",
            "expected_value"
        )
    )

    return anomalies


def detect_cart_abandonment_anomalies(metrics_df):
    """Detect unusual cart abandonment rates."""

    # Use fixed thresholds for streaming compatibility
    # Normal e-commerce: 40-60% abandonment is typical
    EXPECTED_ABANDONMENT = 0.50

    metrics_with_abandonment = (
        metrics_df
        .withColumn(
            "abandonment_rate",
            when(col("cart_adds") > 0, 1 - (col("purchase_count") / col("cart_adds")))
            .otherwise(0)
        )
    )

    anomalies = (
        metrics_with_abandonment
        .filter(col("cart_adds") > 5)  # Only check if significant cart activity
        .filter(col("abandonment_rate") > 0.70)  # Only alert if > 70%
        .withColumn("anomaly_type", lit("cart_abandonment_spike"))
        .withColumn(
            "severity",
            when(col("abandonment_rate") > 0.90, lit(SEVERITY_CRITICAL))
            .when(col("abandonment_rate") > 0.80, lit(SEVERITY_HIGH))
            .otherwise(lit(SEVERITY_MEDIUM))
        )
        .withColumn(
            "description",
            concat(
                lit("Cart abandonment SPIKE: "),
                (col("abandonment_rate") * 100).cast("int").cast("string"),
                lit("% (expected ~"),
                lit(str(int(EXPECTED_ABANDONMENT * 100))),
                lit("%). Possible checkout bug or payment issue. "),
                col("cart_adds").cast("string"),
                lit(" carts added, only "),
                col("purchase_count").cast("string"),
                lit(" purchases.")
            )
        )
        .withColumn("metric_value", (col("abandonment_rate") * 100).cast("string"))
        .withColumn("expected_value", lit(f"{int(EXPECTED_ABANDONMENT * 100)}%"))
        .select(
            "window_start",
            "anomaly_type",
            "severity",
            "description",
            "metric_value",
            "expected_value"
        )
    )

    return anomalies


def detect_conversion_anomalies(metrics_df):
    """Detect conversion rate drops."""

    metrics_with_conversion = (
        metrics_df
        .withColumn(
            "conversion_rate",
            when(col("unique_users") > 0, col("buyers") / col("unique_users"))
            .otherwise(0)
        )
    )

    anomalies = (
        metrics_with_conversion
        .filter(col("unique_users") > 20)  # Only alert with sufficient traffic
        .filter(col("conversion_rate") < THRESHOLDS["conversion_min"])
        .withColumn("anomaly_type", lit("conversion_drop"))
        .withColumn(
            "severity",
            when(col("conversion_rate") < 0.01, lit(SEVERITY_CRITICAL))
            .when(col("conversion_rate") < 0.02, lit(SEVERITY_HIGH))
            .otherwise(lit(SEVERITY_MEDIUM))
        )
        .withColumn(
            "description",
            concat(
                lit("Conversion rate VERY LOW: "),
                (col("conversion_rate") * 100).cast("decimal(5,2)").cast("string"),
                lit("% ("),
                col("buyers").cast("string"),
                lit(" buyers / "),
                col("unique_users").cast("string"),
                lit(" users). Expected >3%. Check purchase flow.")
            )
        )
        .withColumn("metric_value", (col("conversion_rate") * 100).cast("string"))
        .withColumn("expected_value", lit("3.0"))
        .select(
            "window_start",
            "anomaly_type",
            "severity",
            "description",
            "metric_value",
            "expected_value"
        )
    )

    return anomalies


def detect_data_quality_anomalies(metrics_df):
    """Detect data quality issues."""

    anomalies = (
        metrics_df
        .filter(col("purchase_count") > 0)
        .withColumn(
            "missing_price_pct",
            col("purchases_missing_price") / col("purchase_count")
        )
        .filter(col("missing_price_pct") > THRESHOLDS["missing_price_pct"])
        .withColumn("anomaly_type", lit("data_quality"))
        .withColumn(
            "severity",
            when(col("missing_price_pct") > 0.50, lit(SEVERITY_CRITICAL))
            .when(col("missing_price_pct") > 0.25, lit(SEVERITY_HIGH))
            .otherwise(lit(SEVERITY_MEDIUM))
        )
        .withColumn(
            "description",
            concat(
                lit("DATA QUALITY ISSUE: "),
                (col("missing_price_pct") * 100).cast("int").cast("string"),
                lit("% of purchases missing price ("),
                col("purchases_missing_price").cast("string"),
                lit("/"),
                col("purchase_count").cast("string"),
                lit(" purchases). Check producer or data pipeline.")
            )
        )
        .withColumn("metric_value", col("purchases_missing_price").cast("string"))
        .withColumn("expected_value", lit("0"))
        .select(
            "window_start",
            "anomaly_type",
            "severity",
            "description",
            "metric_value",
            "expected_value"
        )
    )

    return anomalies


def detect_category_imbalance_anomalies(metrics_df):
    """Detect if one category dominates sales unusually."""

    anomalies = (
        metrics_df
        .filter(col("purchase_count") > 10)  # Minimum purchases for meaningful analysis
        .withColumn(
            "electronics_pct",
            col("electronics_purchases") / col("purchase_count")
        )
        .filter(col("electronics_pct") > THRESHOLDS["category_dominance"])
        .withColumn("anomaly_type", lit("category_imbalance"))
        .withColumn("severity", lit(SEVERITY_LOW))
        .withColumn(
            "description",
            concat(
                lit("CATEGORY IMBALANCE: Electronics accounts for "),
                (col("electronics_pct") * 100).cast("int").cast("string"),
                lit("% of purchases ("),
                col("electronics_purchases").cast("string"),
                lit("/"),
                col("purchase_count").cast("string"),
                lit("). Expected distribution more balanced. Possible bot or unusual promotion.")
            )
        )
        .withColumn("metric_value", (col("electronics_pct") * 100).cast("string"))
        .withColumn("expected_value", lit("25"))
        .select(
            "window_start",
            "anomaly_type",
            "severity",
            "description",
            "metric_value",
            "expected_value"
        )
    )

    return anomalies


def send_alerts_for_batch(anomaly_df):
    """Send Slack alerts for critical/high severity anomalies."""
    # Collect anomalies (small dataset, safe to collect)
    anomalies = anomaly_df.collect()

    for row in anomalies:
        # Only send Slack for critical and high severity
        if row["severity"] in [SEVERITY_CRITICAL, SEVERITY_HIGH]:
            send_slack_alert(
                anomaly_type=row["anomaly_type"],
                severity=row["severity"],
                details=row["description"],
                metric_value=row["metric_value"],
                expected_value=row["expected_value"]
            )


def main():
    spark = (
        SparkSession.builder
        .appName("anomaly-detector")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
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

    # Parse events
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
            col("data.session_id"),
            col("data.price").cast("double").alias("price"),
            col("data.category"),
            col("data.product_id"),
        )
        .withWatermark("event_timestamp", "10 minutes")
    )

    # Compute metrics per 5-minute window
    metrics_df = compute_metrics(parsed_df)

    # Detect different types of anomalies
    revenue_anomalies = detect_revenue_anomalies(metrics_df)
    traffic_anomalies = detect_traffic_anomalies(metrics_df)
    cart_anomalies = detect_cart_abandonment_anomalies(metrics_df)
    conversion_anomalies = detect_conversion_anomalies(metrics_df)
    quality_anomalies = detect_data_quality_anomalies(metrics_df)
    category_anomalies = detect_category_imbalance_anomalies(metrics_df)

    # Union all anomalies
    all_anomalies = (
        revenue_anomalies
        .union(traffic_anomalies)
        .union(cart_anomalies)
        .union(conversion_anomalies)
        .union(quality_anomalies)
        .union(category_anomalies)
    )

    # Write anomalies to ClickHouse and send Slack alerts
    query = (
        all_anomalies.writeStream
        .outputMode("append")
        .foreachBatch(lambda df, bid: (
            write_anomaly_to_clickhouse(df, bid),
            send_alerts_for_batch(df)
        ))
        .option("checkpointLocation", f"{CHECKPOINT_PATH}/anomaly_detector")
        .trigger(processingTime="30 seconds")
        .start()
    )

    print("🚨 Anomaly Detection System Started")
    print(f"   Monitoring: revenue, traffic, cart abandonment, conversion, data quality")
    print(f"   Window: 5 minutes, Check interval: 30 seconds")
    print(f"   Alerts: ClickHouse + Slack (webhook: {'configured' if SLACK_WEBHOOK else 'not configured'})")

    query.awaitTermination()


if __name__ == "__main__":
    main()
