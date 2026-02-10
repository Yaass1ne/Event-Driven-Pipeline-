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
Producer → Kafka → Spark Streaming Jobs → Delta Lake + ClickHouse → BI Tools/Dashboards
                          ↓
                    Airflow Batch Jobs
```

**What problem does this solve?**
- **Real-time insights**: See what's happening right now (last minute of events)
- **Historical analysis**: Understand trends over days/weeks/months
- **Data quality**: Clean, deduplicated, validated data
- **Scalability**: Can handle millions of events per day using ClickHouse

---

## Data Flow

### Real-Time Path (Streaming)
```
1. Producer generates events (clicks, purchases, logins)
   ↓
2. Kafka queues events (message broker)
   ↓
3a. Spark raw-landing: Kafka → Bronze Delta (raw storage)
3b. Spark fast-agg: Kafka → ClickHouse (real-time dashboards)
```

### Batch Path (Hourly Processing)
```
1. Bronze Delta (raw events from streaming)
   ↓
2. Airflow triggers Spark job: Bronze → Silver (cleaned)
   ↓
3. Airflow triggers Spark job: Silver → Gold (analytics)
   ↓
4. Gold tables in ClickHouse (historical dashboards via JDBC sync)
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

---

### 3. Spark Streaming Job: Raw Landing

**Location**: `spark/jobs/spark_raw_landing.py`

**What it does:**
- Reads events from Kafka in real-time (micro-batches every 30 seconds)
- Minimal transformation (parse timestamp, add ingestion time)
- Writes to Delta Lake Bronze layer
- Partitions by date for efficient queries

**Output location:** `/data/lakehouse/bronze/user_events/`

**How to see it working:**

```bash
# 1. Check if streaming job is running
docker compose logs spark-raw-landing | grep "streaming"

# Expected: "Raw landing streaming to /data/lakehouse/bronze/user_events"

# 2. List Bronze Delta table structure
docker compose exec spark-raw-landing ls -la /data/lakehouse/bronze/user_events/
```

**How to query Bronze data** (using Spark SQL):

```bash
# Start Spark SQL shell
docker compose exec spark-raw-landing /opt/spark/bin/spark-sql \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog

# Inside Spark SQL:
spark-sql> SELECT * FROM delta.`/data/lakehouse/bronze/user_events` LIMIT 10;
```

---

### 4. Spark Streaming Job: Fast Aggregation

**Location**: `spark/jobs/spark_fast_agg.py`

**What it does:**
- Reads events from Kafka (parallel to raw-landing)
- Performs real-time aggregations with tumbling windows (1 minute)
- Writes 3 aggregate tables to **ClickHouse** every 30 seconds
- Uses watermarks to handle late-arriving events

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

**How to see it working:**

```bash
# 1. Check if fast-agg job is running
docker compose logs spark-fast-agg | grep "Fast-agg"

# 2. Query real-time events per minute in ClickHouse
docker compose exec clickhouse clickhouse-client --query "
  SELECT
    window_start,
    event_type,
    event_count
  FROM realtime.events_per_minute
  ORDER BY window_start DESC
  LIMIT 10
"

# 3. Query purchases per minute
docker compose exec clickhouse clickhouse-client --query "
  SELECT
    window_start,
    purchase_count
  FROM realtime.purchases_per_minute
  ORDER BY window_start DESC
  LIMIT 10
"
```

---

### 5. Delta Lake (Lakehouse Storage)

**Three-layer architecture:**

#### Bronze Layer (Raw)
- **Purpose**: Store everything as-is from source
- **Schema**: Exactly as received from Kafka
- **Retention**: Long-term (years)

#### Silver Layer (Cleaned)
- **Purpose**: Clean, validated, deduplicated data
- **Schema**: Same as Bronze but enforced
- **Quality**: Nulls removed, invalid types filtered, duplicates removed

#### Gold Layer (Curated)
- **Purpose**: Business-ready analytics tables
- **Schema**: Star schema (dimensions + facts) + KPIs
- **Quality**: Aggregated, optimized for queries

**How to explore Delta Lake:**

```bash
# List all layers
docker compose exec spark-raw-landing ls -la /data/lakehouse/
```

---

### 6. Airflow (Batch Orchestration)

**What it does:**
- Schedules and monitors batch jobs
- Runs hourly: Bronze → Silver → Gold pipeline
- Uses **MySQL** for its own metadata (users, runs, task states)

**DAG Structure** (`airflow/dags/lakehouse_batch_dag.py`):

```python
check_bronze_exists (Python)
    ↓
    ├─→ skip_pipeline (if Bronze empty)
    └─→ run_bronze_to_silver (Bash: spark-submit)
            ↓
        run_silver_to_gold (Bash: spark-submit)
            ↓
        data_quality_checks (Python - ClickHouse check)
            ↓
        pipeline_done (Empty)
```

**Task Details:**
... (Standard tasks as before) ...
**6. gold_to_clickhouse** (Implemented within `spark_silver_to_gold.py`):
   - Spark calculates Gold tables
   - Writes to Delta Lake (storage)
   - Writes to ClickHouse (serving) via JDBC

**How to use Airflow:**

```bash
# 1. Access Airflow UI
# Open browser: http://localhost:8082
# Login: admin / admin

# 2. Trigger DAG manually
docker compose exec airflow-scheduler airflow dags trigger lakehouse_batch_pipeline
```

---

### 7. ClickHouse (Serving Store)

**What it does:**
- Stores data optimized for fast queries (BI tools)
- Two databases:
  - **realtime**: Streaming aggregates (last updated 30 seconds ago)
  - **gold**: Historical KPIs (updated hourly)

**Why ClickHouse?**
- **Column-oriented**: Reads only necessary columns, perfect for analytics
- **Vectorized execution**: Processes data in blocks, extremely fast
- **MergeTree Engine**: Handles high-speed writes and background data merging

**Schema Structure:**

```sql
-- Realtime database (MergeTree)
realtime.events_per_minute
realtime.logins_per_source
realtime.purchases_per_minute

-- Gold database (ReplacingMergeTree)
gold.daily_active_users
gold.events_per_source_daily
gold.purchases_per_page_daily
gold.conversion_rate_daily
```

**How to connect:**

```bash
# Using clickhouse-client via Docker
docker compose exec clickhouse clickhouse-client

# Using HTTP API
curl 'http://localhost:8123/?query=SELECT%201'

# Using JDBC (Java/Spark)
jdbc:clickhouse://clickhouse:8123/default
```

**Useful queries for BI dashboards:**

```sql
-- Real-time dashboard: Last hour activity
SELECT
    toStartOfMinute(window_start) as time,
    event_type,
    SUM(event_count) as events
FROM realtime.events_per_minute
WHERE window_start >= now() - INTERVAL 1 HOUR
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

-- Historical dashboard: Week-over-week growth
SELECT
    event_date,
    dau_count,
    neighbor(dau_count, -7) as dau_last_week,
    round(100.0 * (dau_count - dau_last_week) / dau_last_week, 1) as growth_pct
FROM gold.daily_active_users
ORDER BY event_date DESC;
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

# Step 3: Check ClickHouse has data
docker compose exec clickhouse clickhouse-client --query "SELECT count(*) FROM realtime.events_per_minute"
```

### Scenario 2: Run Batch Pipeline

**Goal:** Process today's data into Gold layer

1. Navigate to http://localhost:8082
2. Trigger `lakehouse_batch_dag`
3. Wait for success (green circles)
4. Verify Gold data in ClickHouse:
   ```bash
   docker compose exec clickhouse clickhouse-client --query "SELECT * FROM gold.daily_active_users"
   ```

---

## Querying and Analyzing Data

**Using ClickHouse Client:**

```bash
# interactive mode
docker compose exec clickhouse clickhouse-client
```

**Common Queries:**

```sql
-- Top 5 pages by purchase count today
SELECT page, purchase_count
FROM gold.purchases_per_page_daily
WHERE event_date = today()
ORDER BY purchase_count DESC
LIMIT 5;

-- Total events ingested in last 5 minutes
SELECT sum(event_count)
FROM realtime.events_per_minute
WHERE window_start >= now() - INTERVAL 5 MINUTE;
```

---

## Common Use Cases

1. **Real-time Monitoring Dashboard**: Use `realtime` tables in Grafana with 10s refresh.
2. **Daily Business Reports**: Use `gold` tables for consistent, daily metrics.
3. **Ad-hoc Analysis**: Connect DBeaver or DataGrip to ClickHouse port 8123 to run custom SQL.
