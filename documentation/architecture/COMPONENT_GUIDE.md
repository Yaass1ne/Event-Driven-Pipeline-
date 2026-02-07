# Complete Platform Guide: Understanding Every Component

This guide explains every component in the lakehouse data platform, how they work together, and how to interact with them.

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Data Flow](#data-flow)
3. [Component Deep Dive](#component-deep-dive)
4. [Hands-On Usage Guide](#hands-on-usage-guide)
5. [Querying and Analyzing Data](#querying-and-analyzing-data)
6. [Common Use Cases](#common-use-cases)

---

## Architecture Overview

### The Big Picture

```
Producer → Kafka → Spark Streaming Jobs → Delta Lake + PostgreSQL → BI Tools/Dashboards
                          ↓
                    Airflow Batch Jobs
```

**What problem does this solve?**
- **Real-time insights**: See what's happening right now (last minute of events)
- **Historical analysis**: Understand trends over days/weeks/months
- **Data quality**: Clean, deduplicated, validated data
- **Scalability**: Can handle millions of events per day

---

## Data Flow

### Real-Time Path (Streaming)
```
1. Producer generates events (clicks, purchases, logins)
   ↓
2. Kafka queues events (message broker)
   ↓
3a. Spark raw-landing: Kafka → Bronze Delta (raw storage)
3b. Spark fast-agg: Kafka → PostgreSQL (real-time dashboards)
```

### Batch Path (Hourly Processing)
```
1. Bronze Delta (raw events from streaming)
   ↓
2. Airflow triggers Spark job: Bronze → Silver (cleaned)
   ↓
3. Airflow triggers Spark job: Silver → Gold (analytics)
   ↓
4. Gold tables in PostgreSQL (historical dashboards)
```

---

## Component Deep Dive

### 1. Producer (Event Generator)

**Location**: `producer/producer.py`

**What it does:**
- Simulates a real application generating user events
- Creates JSON events: logins, clicks, purchases, logouts
- Sends events to Kafka at configurable rate (default: 5/sec)

**Event Structure:**
```json
{
  "event_id": "uuid-here",
  "user_id": 42,
  "event_type": "purchase",
  "page": "/checkout",
  "timestamp": "2026-02-06T14:30:00",
  "source": "web"
}
```

**Configuration (docker-compose.yml):**
```yaml
environment:
  EVENTS_PER_SECOND: "5"    # How fast to generate events
  NUM_USERS: "100"           # Pool of unique users
  KAFKA_TOPIC: "user-events" # Where to send events
```

**How to see it working:**
```bash
# Watch events being generated
docker compose logs -f producer

# Expected output:
# Sent 50 events (latest: purchase user=42)
# Sent 100 events (latest: click user=78)
```

**Real-world equivalent:** Your website/app sending events to analytics

---

### 2. Apache Kafka (Message Broker)

**What it does:**
- Receives events from producer
- Stores them temporarily in a queue (topic)
- Allows multiple consumers to read the same events
- Provides durability and ordering guarantees

**Key concepts:**
- **Topic**: Named stream of events (`user-events`)
- **Partition**: Parallel processing unit (3 partitions = 3 parallel readers)
- **Consumer Group**: Multiple apps reading from same topic
- **Retention**: How long to keep events (24 hours in our setup)

**How to interact:**

```bash
# 1. List all topics
docker compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# 2. Describe the user-events topic
docker compose exec kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --describe --topic user-events

# Expected output:
# Topic: user-events  PartitionCount: 3  ReplicationFactor: 1

# 3. Read last 10 events from the topic
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic user-events \
  --from-beginning \
  --max-messages 10

# 4. Count total events in topic
docker compose exec kafka kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic user-events
```

**How to see data flow:**
```bash
# Monitor consumer lag (how far behind are consumers)
docker compose exec kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe --all-groups
```

**Real-world equivalent:** Apache Kafka, AWS Kinesis, Google Pub/Sub

---

### 3. Spark Streaming Job: Raw Landing

**Location**: `spark/jobs/spark_raw_landing.py`

**What it does:**
- Reads events from Kafka in real-time (micro-batches every 30 seconds)
- Minimal transformation (parse timestamp, add ingestion time)
- Writes to Delta Lake Bronze layer
- Partitions by date for efficient queries

**Code flow:**
```python
1. Connect to Kafka (readStream)
2. Parse JSON events
3. Cast timestamp to proper type
4. Add event_date partition column
5. Write to Delta Lake with checkpointing
```

**Output location:** `/data/lakehouse/bronze/user_events/`

**File structure:**
```
bronze/user_events/
├── _delta_log/              # Transaction log (ACID guarantees)
│   ├── 00000000000000000000.json  # Commit 0
│   ├── 00000000000000000001.json  # Commit 1
│   └── 00000000000000000010.checkpoint.parquet  # Checkpoint
└── event_date=2026-02-06/   # Partitioned by date
    ├── part-00000-xxx.snappy.parquet
    └── part-00001-xxx.snappy.parquet
```

**How to see it working:**

```bash
# 1. Check if streaming job is running
docker compose logs spark-raw-landing | grep "streaming"

# Expected: "Raw landing streaming to /data/lakehouse/bronze/user_events"

# 2. List Bronze Delta table structure
docker compose exec spark-raw-landing ls -la /data/lakehouse/bronze/user_events/

# 3. Check transaction log (how many commits)
docker compose exec spark-raw-landing ls /data/lakehouse/bronze/user_events/_delta_log/ | wc -l

# 4. Check partition directories (one per date)
docker compose exec spark-raw-landing ls /data/lakehouse/bronze/user_events/ | grep event_date

# 5. Count parquet files (each micro-batch creates 1-2 files)
docker compose exec spark-raw-landing \
  find /data/lakehouse/bronze/user_events/event_date=2026-02-06/ -name "*.parquet" | wc -l

# 6. Check size of Bronze data
docker compose exec spark-raw-landing du -sh /data/lakehouse/bronze/user_events/
```

**How to query Bronze data** (using Spark SQL):

```bash
# Start Spark SQL shell
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog

# Inside Spark SQL:
# 1. Read Bronze table
spark-sql> SELECT * FROM delta.`/data/lakehouse/bronze/user_events` LIMIT 10;

# 2. Count events by type
spark-sql> SELECT event_type, COUNT(*) as count
           FROM delta.`/data/lakehouse/bronze/user_events`
           GROUP BY event_type;

# 3. Count events by source
spark-sql> SELECT source, COUNT(*) as count
           FROM delta.`/data/lakehouse/bronze/user_events`
           GROUP BY source;

# 4. Check latest events
spark-sql> SELECT event_type, user_id, page, event_timestamp
           FROM delta.`/data/lakehouse/bronze/user_events`
           ORDER BY event_timestamp DESC
           LIMIT 10;
```

**Real-world equivalent:** Raw data ingestion pipeline, data lake landing zone

---

### 4. Spark Streaming Job: Fast Aggregation

**Location**: `spark/jobs/spark_fast_agg.py`

**What it does:**
- Reads events from Kafka (parallel to raw-landing)
- Performs real-time aggregations with tumbling windows (1 minute)
- Writes 3 aggregate tables to PostgreSQL every 30 seconds
- Uses watermarks to handle late-arriving events (2-minute delay tolerance)

**Three aggregations:**

1. **Events per minute by type**
   - Count of login, click, purchase, logout per minute
   - Use case: Real-time monitoring dashboard

2. **Logins per source per minute**
   - Count of logins split by web/mobile
   - Use case: Traffic source analysis

3. **Purchases per minute**
   - Total purchase count per minute
   - Use case: Revenue monitoring, alerting

**Write strategy:**
- Mode: `overwrite` (replaces entire table each micro-batch)
- Truncate: `true` (preserves schema/indexes, fast)
- No primary keys (streaming data, optimized for speed)

**How to see it working:**

```bash
# 1. Check if fast-agg job is running
docker compose logs spark-fast-agg | grep "Fast-agg"

# 2. Query real-time events per minute
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT
     window_start,
     event_type,
     event_count
   FROM realtime.events_per_minute
   ORDER BY window_start DESC
   LIMIT 10;"

# Example output:
#     window_start     | event_type | event_count
# ---------------------+------------+-------------
#  2026-02-06 14:30:00 | click      |         139
#  2026-02-06 14:30:00 | purchase   |          52
#  2026-02-06 14:30:00 | login      |          31
#  2026-02-06 14:30:00 | logout     |          40

# 3. Query logins by source
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT
     window_start,
     source,
     login_count
   FROM realtime.logins_per_source
   ORDER BY window_start DESC
   LIMIT 10;"

# 4. Query purchase rate over time
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT
     window_start,
     purchase_count,
     ROUND(purchase_count::numeric / 60, 2) as purchases_per_second
   FROM realtime.purchases_per_minute
   ORDER BY window_start DESC
   LIMIT 10;"

# 5. Real-time dashboard query: Last 30 minutes activity
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT
     event_type,
     SUM(event_count) as total_events,
     ROUND(AVG(event_count), 1) as avg_per_minute
   FROM realtime.events_per_minute
   WHERE window_start >= NOW() - INTERVAL '30 minutes'
   GROUP BY event_type
   ORDER BY total_events DESC;"
```

**Real-world use cases:**
- Real-time monitoring dashboards (Grafana, Datadog)
- Alerting on anomalies (sudden drop in purchases)
- Live KPI tracking for business teams

---

### 5. Delta Lake (Lakehouse Storage)

**What it is:**
- Open-source storage layer on top of Parquet files
- Provides ACID transactions, time travel, schema evolution
- Think: "PostgreSQL reliability + Data Lake scalability"

**Three-layer architecture:**

#### Bronze Layer (Raw)
- **Purpose**: Store everything as-is from source
- **Schema**: Exactly as received from Kafka
- **Quality**: No validation, may have duplicates/nulls
- **Retention**: Long-term (years)
- **Use case**: Reprocessing, auditing, debugging

#### Silver Layer (Cleaned)
- **Purpose**: Clean, validated, deduplicated data
- **Schema**: Same as Bronze but enforced
- **Quality**:
  - Nulls removed
  - Invalid event_types filtered out
  - Duplicates removed by event_id
- **Retention**: Long-term
- **Use case**: Analytics, ML training data

#### Gold Layer (Curated)
- **Purpose**: Business-ready analytics tables
- **Schema**: Star schema (dimensions + facts) + KPIs
- **Quality**: Aggregated, optimized for queries
- **Retention**: Long-term
- **Use case**: BI dashboards, reporting

**How to explore Delta Lake:**

```bash
# 1. List all layers
docker compose exec spark-raw-landing ls -la /data/lakehouse/

# Output:
# bronze/  silver/  gold/

# 2. Explore transaction history (time travel)
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
  -e "DESCRIBE HISTORY delta.\`/data/lakehouse/bronze/user_events\`"

# Shows: version, timestamp, operation, operationMetrics

# 3. Query old version (time travel)
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
  -e "SELECT COUNT(*) FROM delta.\`/data/lakehouse/bronze/user_events\` VERSION AS OF 5"

# 4. Check table details
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
  -e "DESCRIBE DETAIL delta.\`/data/lakehouse/bronze/user_events\`"

# Shows: format=delta, numFiles, sizeInBytes, partitionColumns
```

**Real-world equivalent:** Databricks Delta Lake, AWS Lake Formation with Iceberg

---

### 6. Airflow (Batch Orchestration)

**What it does:**
- Schedules and monitors batch jobs
- Runs hourly: Bronze → Silver → Gold pipeline
- Provides UI for monitoring, logs, retries
- Ensures data quality with checks

**DAG Structure** (`airflow/dags/lakehouse_batch_dag.py`):

```python
check_bronze_exists (Python)
    ↓
    ├─→ skip_pipeline (if Bronze empty)
    └─→ run_bronze_to_silver (Bash: spark-submit)
            ↓
        run_silver_to_gold (Bash: spark-submit)
            ↓
        data_quality_checks (Python)
            ↓
        pipeline_done (Empty)
```

**Task Details:**

1. **check_bronze_exists** (BranchPythonOperator)
   - Checks if Bronze Delta table exists and has data
   - If yes → run pipeline
   - If no → skip pipeline

2. **run_bronze_to_silver** (BashOperator)
   - Runs: `spark-submit spark_bronze_to_silver.py`
   - Reads Bronze, cleans data, writes Silver
   - Takes ~40-50 seconds for 15K events

3. **run_silver_to_gold** (BashOperator)
   - Runs: `spark-submit spark_silver_to_gold.py`
   - Creates 7 Gold tables (3 dimensions, 1 fact, 4 KPIs)
   - Writes to both Delta Lake and PostgreSQL
   - Takes ~35-45 seconds

4. **data_quality_checks** (PythonOperator)
   - Validates Gold PostgreSQL tables have data
   - Checks for NULL values in key columns
   - Verifies Delta tables exist

**How to use Airflow:**

```bash
# 1. Access Airflow UI
# Open browser: http://localhost:8082
# Login: admin / admin

# 2. Via CLI: List DAGs
docker compose exec airflow-scheduler airflow dags list

# 3. Trigger DAG manually
docker compose exec airflow-scheduler airflow dags trigger lakehouse_batch_pipeline

# 4. Check DAG run status
docker compose exec airflow-scheduler airflow dags list-runs -d lakehouse_batch_pipeline

# 5. View task states for a specific run
docker compose exec airflow-scheduler airflow tasks states-for-dag-run \
  lakehouse_batch_pipeline \
  manual__2026-02-06T13:15:32+00:00

# 6. View logs for a specific task
docker compose exec airflow-scheduler airflow tasks log \
  lakehouse_batch_pipeline \
  run_bronze_to_silver \
  manual__2026-02-06T13:15:32+00:00 \
  1

# 7. Pause/unpause DAG
docker compose exec airflow-scheduler airflow dags pause lakehouse_batch_pipeline
docker compose exec airflow-scheduler airflow dags unpause lakehouse_batch_pipeline

# 8. List all tasks in DAG
docker compose exec airflow-scheduler airflow tasks list lakehouse_batch_pipeline

# 9. Test a single task (dry-run)
docker compose exec airflow-scheduler airflow tasks test \
  lakehouse_batch_pipeline \
  check_bronze_exists \
  2026-02-06
```

**Airflow UI Guide:**

1. **DAGs page**: List of all DAGs, toggle on/off
2. **Graph View**: Visual task dependencies
3. **Tree View**: Historical runs, color-coded status
4. **Gantt Chart**: Task duration timeline
5. **Task Logs**: Stdout/stderr for debugging
6. **Code**: View DAG source code

**Real-world equivalent:** Apache Airflow, Prefect, Dagster, AWS Step Functions

---

### 7. Batch Spark Job: Bronze to Silver

**Location**: `spark/jobs/spark_bronze_to_silver.py`

**What it does:**
1. Read Bronze Delta table (all events since last run)
2. Filter out nulls in critical columns
3. Validate event_type is in allowed list
4. Validate source is web or mobile
5. Deduplicate by event_id (keep first occurrence)
6. Write to Silver Delta table

**Code logic:**
```python
# Read Bronze
bronze = spark.read.format("delta").load("/data/lakehouse/bronze/user_events")

# Clean
silver = (
    bronze
    .filter(col("event_id").isNotNull())
    .filter(col("event_type").isin(["login", "click", "purchase", "logout"]))
    .filter(col("source").isin(["web", "mobile"]))
    .dropDuplicates(["event_id"])  # Keep first
)

# Write Silver (append new, update existing)
silver.write.format("delta").mode("append").partitionBy("event_date").save("/data/lakehouse/silver/user_events")
```

**How to verify:**

```bash
# 1. Query Silver table
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
  -e "SELECT COUNT(*) FROM delta.\`/data/lakehouse/silver/user_events\`"

# 2. Compare Bronze vs Silver counts (should be close, Silver slightly less due to deduplication)
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
  -e "
  SELECT
    'Bronze' as layer, COUNT(*) as count FROM delta.\`/data/lakehouse/bronze/user_events\`
  UNION ALL
  SELECT
    'Silver' as layer, COUNT(*) as count FROM delta.\`/data/lakehouse/silver/user_events\`
  "

# 3. Check for any invalid event_types in Bronze (should be filtered out in Silver)
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
  -e "
  SELECT DISTINCT event_type
  FROM delta.\`/data/lakehouse/silver/user_events\`
  "
# Should only show: login, click, purchase, logout
```

---

### 8. Batch Spark Job: Silver to Gold

**Location**: `spark/jobs/spark_silver_to_gold.py`

**What it does:**
1. Read Silver Delta table
2. Create **3 dimension tables** (slowly changing dimensions)
3. Create **1 fact table** (event details)
4. Create **4 KPI tables** (aggregated metrics)
5. Write to both Delta Lake and PostgreSQL

**Gold Tables Created:**

#### Dimensions:
- **dim_users**: User attributes (user_id, total_events, source_count)
- **dim_pages**: Page attributes (page, total_events)
- **dim_dates**: Date attributes (would be expanded in production)

#### Fact:
- **fact_events**: Denormalized event details with foreign keys to dimensions

#### KPIs:
- **kpi_dau**: Daily Active Users (event_date, dau_count)
- **kpi_events_per_source**: Events by source by day (event_date, source, event_count)
- **kpi_purchases_per_page**: Purchase counts by page (event_date, page, purchase_count)
- **kpi_conversion_rate**: Purchase conversion rate (event_date, total_events, total_purchases, conversion_rate)

**How to query Gold data:**

```bash
# PostgreSQL (optimized for BI tools)

# 1. Daily Active Users trend
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT
     event_date,
     dau_count,
     updated_at
   FROM gold.daily_active_users
   ORDER BY event_date DESC;"

# 2. Traffic source breakdown
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT
     event_date,
     source,
     event_count,
     ROUND(100.0 * event_count / SUM(event_count) OVER (PARTITION BY event_date), 1) as pct
   FROM gold.events_per_source_daily
   ORDER BY event_date DESC, event_count DESC;"

# 3. Top performing pages by purchases
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT
     page,
     purchase_count,
     RANK() OVER (ORDER BY purchase_count DESC) as rank
   FROM gold.purchases_per_page_daily
   WHERE event_date = CURRENT_DATE
   ORDER BY purchase_count DESC
   LIMIT 10;"

# 4. Conversion rate analysis
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT
     event_date,
     total_events,
     total_purchases,
     ROUND(conversion_rate * 100, 2) || '%' as conversion_pct
   FROM gold.conversion_rate_daily
   ORDER BY event_date DESC;"

# 5. Multi-metric dashboard query
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT
     d.event_date,
     d.dau_count as daily_users,
     SUM(e.event_count) as total_events,
     c.total_purchases,
     ROUND(c.conversion_rate * 100, 1) || '%' as conversion
   FROM gold.daily_active_users d
   JOIN gold.events_per_source_daily e ON d.event_date = e.event_date
   JOIN gold.conversion_rate_daily c ON d.event_date = c.event_date
   GROUP BY d.event_date, d.dau_count, c.total_purchases, c.conversion_rate
   ORDER BY d.event_date DESC;"
```

**Gold Delta Lake queries:**

```bash
# Query Gold dimensions and facts
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog

# Inside Spark SQL:

# 1. Top users by activity
spark-sql> SELECT * FROM delta.`/data/lakehouse/gold/dim_users`
           ORDER BY total_events DESC LIMIT 10;

# 2. Page popularity
spark-sql> SELECT * FROM delta.`/data/lakehouse/gold/dim_pages`
           ORDER BY total_events DESC LIMIT 10;

# 3. Fact table joins
spark-sql> SELECT
             f.event_id,
             f.event_type,
             f.event_timestamp,
             u.total_events as user_total_events,
             p.total_events as page_total_events
           FROM delta.`/data/lakehouse/gold/fact_events` f
           JOIN delta.`/data/lakehouse/gold/dim_users` u ON f.user_id = u.user_id
           JOIN delta.`/data/lakehouse/gold/dim_pages` p ON f.page = p.page
           LIMIT 10;
```

---

### 9. PostgreSQL (Serving Store)

**What it does:**
- Stores data optimized for fast queries (BI tools)
- Two schemas:
  - **realtime**: Streaming aggregates (last updated 30 seconds ago)
  - **gold**: Historical KPIs (updated hourly)

**Schema Structure:**

```sql
-- Realtime schema (updated every 30 seconds by Spark streaming)
realtime.events_per_minute
realtime.logins_per_source
realtime.purchases_per_minute

-- Gold schema (updated hourly by Airflow batch)
gold.daily_active_users
gold.events_per_source_daily
gold.purchases_per_page_daily
gold.conversion_rate_daily
```

**How to connect from outside:**

```bash
# Using psql
psql -h localhost -p 5432 -U platform -d serving

# Using Python
import psycopg2
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="serving",
    user="platform",
    password="platform123"
)

# Using JDBC (Java/Scala)
jdbc:postgresql://localhost:5432/serving
```

**Useful queries for BI dashboards:**

```sql
-- Real-time dashboard: Last hour activity
SELECT
    DATE_TRUNC('minute', window_start) as time,
    event_type,
    SUM(event_count) as events
FROM realtime.events_per_minute
WHERE window_start >= NOW() - INTERVAL '1 hour'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

-- Historical dashboard: Week-over-week growth
SELECT
    event_date,
    dau_count,
    LAG(dau_count, 7) OVER (ORDER BY event_date) as dau_last_week,
    ROUND(100.0 * (dau_count - LAG(dau_count, 7) OVER (ORDER BY event_date)) /
          NULLIF(LAG(dau_count, 7) OVER (ORDER BY event_date), 0), 1) as growth_pct
FROM gold.daily_active_users
ORDER BY event_date DESC;

-- Cohort analysis: New vs returning users (would need additional ETL)
-- Purchase funnel: Page views -> Checkout -> Purchase
SELECT
    p_checkout.purchase_count as checkouts,
    p_purchase.purchase_count as purchases,
    ROUND(100.0 * p_purchase.purchase_count / NULLIF(p_checkout.purchase_count, 0), 1) as checkout_conversion_pct
FROM gold.purchases_per_page_daily p_checkout
JOIN gold.purchases_per_page_daily p_purchase
  ON p_checkout.event_date = p_purchase.event_date
WHERE p_checkout.page = '/checkout'
  AND p_purchase.page = '/confirmation';
```

---

## Hands-On Usage Guide

### Scenario 1: Monitor Real-Time System Health

**Goal:** Check if data is flowing through all components

```bash
# Step 1: Verify producer is running
docker compose logs producer --tail 5
# Expected: "Sent XXXX events"

# Step 2: Check Kafka has events
docker compose exec kafka kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic user-events
# Expected: Non-zero offsets

# Step 3: Verify Bronze streaming is working
docker compose logs spark-raw-landing | tail -20
# Expected: No errors, occasional "INFO" messages

# Step 4: Check Bronze has recent data
docker compose exec spark-raw-landing \
  find /data/lakehouse/bronze/user_events/event_date=$(date +%Y-%m-%d)/ \
  -name "*.parquet" -mmin -5
# Expected: Recently modified files

# Step 5: Verify PostgreSQL real-time aggregates are updating
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT MAX(updated_at) FROM realtime.events_per_minute;"
# Expected: Timestamp within last minute
```

### Scenario 2: Run Complete Batch Pipeline

**Goal:** Process Bronze → Silver → Gold

```bash
# Step 1: Fix permissions (first time only)
docker compose exec spark-raw-landing chmod -R 777 /data/lakehouse/

# Step 2: Trigger Airflow DAG
docker compose exec airflow-scheduler airflow dags trigger lakehouse_batch_pipeline

# Step 3: Monitor progress
watch -n 5 'docker compose exec airflow-scheduler airflow tasks states-for-dag-run lakehouse_batch_pipeline manual__$(date +%Y-%m-%d)T*'

# Step 4: Check results after completion
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT * FROM gold.daily_active_users;"
```

### Scenario 3: Query Data for Analysis

**Goal:** Answer business questions

```bash
# Question: What's our purchase conversion rate today?
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT
     ROUND(conversion_rate * 100, 2) || '%' as conversion_rate,
     total_purchases || ' purchases',
     total_events || ' total events'
   FROM gold.conversion_rate_daily
   WHERE event_date = CURRENT_DATE;"

# Question: Which pages drive the most purchases?
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT page, purchase_count
   FROM gold.purchases_per_page_daily
   WHERE event_date = CURRENT_DATE
   ORDER BY purchase_count DESC
   LIMIT 5;"

# Question: Are mobile or web users more active?
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT source, event_count
   FROM gold.events_per_source_daily
   WHERE event_date = CURRENT_DATE;"
```

### Scenario 4: Time Travel (Debugging)

**Goal:** Compare current data vs 1 hour ago

```bash
# Step 1: Check current version
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
  -e "DESCRIBE HISTORY delta.\`/data/lakehouse/bronze/user_events\`"

# Step 2: Query old version (e.g., version 10)
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
  -e "SELECT COUNT(*) FROM delta.\`/data/lakehouse/bronze/user_events\` VERSION AS OF 10"

# Step 3: Compare counts
# Current count - old count = events added since version 10
```

---

## Querying and Analyzing Data

### Connect with BI Tools

#### Grafana Setup:
```yaml
1. Add PostgreSQL data source
   - Host: localhost:5432
   - Database: serving
   - User: platform
   - Password: platform123

2. Create dashboard panels:
   - Time series: realtime.events_per_minute
   - Bar chart: gold.purchases_per_page_daily
   - Stat: gold.daily_active_users (latest)
   - Gauge: gold.conversion_rate_daily (latest)
```

#### Tableau Setup:
```
1. Connect to PostgreSQL
2. Select schemas: realtime, gold
3. Create calculated fields:
   - Conversion %: [total_purchases] / [total_events] * 100
   - WoW Growth: ([dau_count] - [dau_last_week]) / [dau_last_week]
```

#### Python Analysis:
```python
import pandas as pd
import psycopg2

# Connect
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="serving",
    user="platform",
    password="platform123"
)

# Query Gold data
df = pd.read_sql("""
    SELECT
        event_date,
        dau_count,
        (SELECT SUM(event_count) FROM gold.events_per_source_daily e
         WHERE e.event_date = d.event_date) as total_events
    FROM gold.daily_active_users d
    ORDER BY event_date
""", conn)

# Analysis
print(df.describe())
df.plot(x='event_date', y='dau_count', kind='line')
```

---

## Common Use Cases

### Use Case 1: Real-Time Monitoring Dashboard

**Scenario:** Operations team wants live view of system health

**Solution:**
```sql
-- Grafana query (refresh every 10 seconds)
SELECT
    window_start as time,
    event_type as metric,
    event_count as value
FROM realtime.events_per_minute
WHERE window_start >= NOW() - INTERVAL '1 hour'
ORDER BY window_start;
```

**Alerts:**
- Event count drops below 50/minute → investigate producer
- Purchase count = 0 for 5 minutes → critical alert

### Use Case 2: Daily Executive Report

**Scenario:** Email daily KPIs to leadership

**Solution:**
```sql
-- Scheduled query (run at 9 AM daily)
SELECT
    dau.event_date,
    dau.dau_count as "Active Users",
    e.event_count as "Total Events",
    p.total_purchases as "Purchases",
    ROUND(p.conversion_rate * 100, 1) || '%' as "Conversion"
FROM gold.daily_active_users dau
JOIN (SELECT event_date, SUM(event_count) as event_count
      FROM gold.events_per_source_daily GROUP BY 1) e
  ON dau.event_date = e.event_date
JOIN gold.conversion_rate_daily p
  ON dau.event_date = p.event_date
WHERE dau.event_date = CURRENT_DATE - 1
ORDER BY dau.event_date DESC;
```

### Use Case 3: A/B Test Analysis

**Scenario:** Test if new checkout page increases conversions

**Solution:**
```sql
-- Compare conversion rates by page
SELECT
    page,
    purchase_count,
    (SELECT SUM(event_count)
     FROM gold.events_per_source_daily
     WHERE event_date = p.event_date) as total_events,
    ROUND(100.0 * purchase_count /
          (SELECT SUM(event_count) FROM gold.events_per_source_daily
           WHERE event_date = p.event_date), 2) as conversion_pct
FROM gold.purchases_per_page_daily p
WHERE event_date >= '2026-02-01'
  AND page IN ('/checkout', '/checkout-new')
ORDER BY event_date, page;
```

### Use Case 4: Incident Investigation

**Scenario:** Purchases dropped to zero yesterday 2-3 PM

**Solution:**
```bash
# Step 1: Check real-time aggregates for that time
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT * FROM realtime.purchases_per_minute
   WHERE window_start >= '2026-02-05 14:00:00'
     AND window_start < '2026-02-05 15:00:00'
   ORDER BY window_start;"

# Step 2: Check if producer was running
docker compose logs producer --since "2026-02-05T14:00:00" --until "2026-02-05T15:00:00"

# Step 3: Check Bronze for purchase events
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
  -e "
  SELECT event_type, COUNT(*)
  FROM delta.\`/data/lakehouse/bronze/user_events\`
  WHERE event_timestamp >= '2026-02-05 14:00:00'
    AND event_timestamp < '2026-02-05 15:00:00'
  GROUP BY event_type
  "

# Step 4: Time travel to see what happened
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
  -e "DESCRIBE HISTORY delta.\`/data/lakehouse/bronze/user_events\`"
# Look for operations around 2-3 PM
```

---

## Troubleshooting Guide

### Data Not Flowing

```bash
# Check entire pipeline health
docker compose ps
# All containers should be "Up" (not "Restarting")

# Check producer
docker compose logs producer --tail 10
# Should see "Sent XXX events"

# Check Kafka
docker compose exec kafka kafka-topics --bootstrap-server localhost:9092 --describe --topic user-events
# Should show 3 partitions

# Check Spark streaming
docker compose logs spark-raw-landing --tail 20
docker compose logs spark-fast-agg --tail 20
# Should NOT see errors

# Check PostgreSQL
docker compose exec postgres psql -U platform -d serving -c "\dt realtime.*"
# Should show 3 tables
```

### Airflow DAG Not Running

```bash
# Check scheduler is running
docker compose ps airflow-scheduler
# Should be "Up"

# Check DAG is unpaused
docker compose exec airflow-scheduler airflow dags list | grep lakehouse
# Should show "True" in pause column

# Check for errors
docker compose logs airflow-scheduler | grep -i error

# Manually trigger
docker compose exec airflow-scheduler airflow dags trigger lakehouse_batch_pipeline
```

---

This guide covers the complete platform! Each component plays a specific role in the end-to-end data flow. The real power comes from combining streaming (real-time) and batch (historical) processing to serve both operational and analytical use cases.
