# Lakehouse Architecture Overview

## System Architecture

This lakehouse platform implements a **Lambda Architecture** pattern with both **real-time streaming** and **batch processing** pipelines.

```
┌─────────────┐
│   Producer  │ ──► Generates synthetic user events
└─────────────┘
      │
      ▼
┌─────────────┐
│    Kafka    │ ──► Message broker (user-events topic)
└─────────────┘
      │
      ├──────────────────────────┐
      │                          │
      ▼                          ▼
┌─────────────┐          ┌─────────────┐
│ Spark       │          │ Spark       │
│ Raw Landing │          │ Fast Agg    │
│ (Streaming) │          │ (Streaming) │
└─────────────┘          └─────────────┘
      │                          │
      ▼                          ▼
┌─────────────┐          ┌─────────────┐
│ Delta Lake  │          │ ClickHouse  │
│ Bronze      │          │ realtime.*  │
└─────────────┘          └─────────────┘
      │                          │
      ▼                          │
┌─────────────┐                  │
│  Airflow    │ ──► Batch        │
│  DAG        │     Processing   │
└─────────────┘                  │
      │                          │
      ▼                          │
┌─────────────┐                  │
│ Delta Lake  │                  │
│ Silver/Gold │                  │
└─────────────┘                  │
      │                          │
      ▼                          │
┌─────────────┐                  │
│ ClickHouse  │ ◄────────────────┘
│   gold.*    │
└─────────────┘
      │
      ▼
┌─────────────┐
│   Grafana   │ ──► Dashboards & Visualization
└─────────────┘
```

---

## Data Flow Paths

### Path 1: Real-Time Streaming (Speed Layer)
```
Producer → Kafka → Spark Raw Landing → Delta Bronze
                → Spark Fast Agg → ClickHouse (realtime database)
```

**Purpose:** Low-latency metrics updated every 10-30 seconds
**Updates:** Minute-by-minute aggregations
**Latency:** < 10 seconds

### Path 2: Batch Processing (Batch Layer)
```
Delta Bronze → Airflow → Delta Silver → Delta Gold → ClickHouse (gold database)
```

**Purpose:** Accurate, complete daily analytics
**Updates:** Daily (scheduled or manual)
**Latency:** Minutes to hours

### Path 3: Serving (Presentation Layer)
```
ClickHouse (realtime + gold) → Grafana → User
```

**Purpose:** Unified view of real-time + historical data
**Updates:** Real-time (10s refresh)

---

## Component Breakdown

### 1. Data Ingestion

#### Producer (Python)
- **Role:** Event generator
- **Output:** JSON events to Kafka
- **Rate:** 5 events/second (configurable)
- **Features:**
  - Growing user base (100 → 110+ users)
  - 80% events from active users, 20% from new/returning
  - Realistic event distribution (clicks > logins > purchases)

#### Kafka
- **Role:** Message broker
- **Topic:** `user-events` (3 partitions)
- **Retention:** 24 hours
- **Purpose:** Decouples producers from consumers

### 2. Streaming Processing

#### Spark Raw Landing
- **Input:** Kafka `user-events` topic
- **Output:** Delta Lake Bronze layer
- **Mode:** `local[2]` (in-process, 2 threads)
- **Trigger:** Continuous (micro-batches every 30s)
- **Operations:**
  - Read from Kafka
  - Parse JSON
  - Partition by `event_date`
  - Write to Delta format with ACID guarantees

#### Spark Fast Aggregation
- **Input:** Kafka `user-events` topic
- **Output:** ClickHouse `realtime` database
- **Mode:** `local[2]` (in-process)
- **Trigger:** Every 30 seconds
- **Aggregations:**
  - Events per minute (by event_type)
  - Logins per source per minute
  - Purchases per minute
- **Window:** 1-minute tumbling windows with 2-minute watermark

### 3. Storage Layers

#### Delta Lake (Lakehouse)
**Location:** Docker volume `/data/lakehouse/`

**Bronze Layer:**
- Raw events from Kafka
- Partitioned by `event_date`
- Schema: `{event_id, user_id, event_type, page, timestamp, source}`
- Size: 100-500 MB (grows continuously)

**Silver Layer:**
- Cleaned and validated data
- Duplicate removal
- Data quality checks
- Schema enforcement
- Size: 5-10 MB

**Gold Layer:**
- Business-level aggregations
- Tables:
  - `daily_active_users` - Unique users per day
  - `conversion_rate_daily` - Purchase conversion metrics
  - `events_per_source_daily` - Source breakdown
  - `purchases_per_page_daily` - Page-level purchase analysis
- Size: 5-10 MB

#### ClickHouse (OLAP Serving)
**Databases:**

**`realtime` database:**
- `events_per_minute` (MergeTree)
- `logins_per_source` (MergeTree)
- `purchases_per_minute` (MergeTree)
- Updated: Every 30 seconds via Spark JDBC
- Engine: `MergeTree` for high-speed ingestion

**`gold` database:**
- Mirror of Delta Gold layer
- Updated: Daily via Airflow
- Engine: `ReplacingMergeTree` (handles updates/deduplication)
- Purpose: Sub-second queries for dashboards

### 4. Batch Orchestration

#### Airflow
- **DAG:** `lakehouse_batch_dag`
- **Schedule:** Daily (can be triggered manually)
- **Metadata DB:** MySQL
- **Tasks:**
  1. `bronze_to_silver` - Clean and validate Bronze data
  2. `silver_to_gold_dau` - Calculate Daily Active Users
  3. `silver_to_gold_conversion` - Calculate conversion rates
  4. `silver_to_gold_events_source` - Aggregate by source
  5. `silver_to_gold_purchases_page` - Aggregate by page
  6. `gold_to_clickhouse` - Load Gold tables to ClickHouse using JDBC

**Executor:** LocalExecutor (single-node)
**Dependencies:** Tasks run in sequence with defined order

### 5. Visualization

#### Grafana
- **Dashboard:** Lakehouse Platform Overview
- **Panels:**
  - **Top Row (Batch):** DAU, Conversion Rate, Total Purchases, Total Events
  - **Middle Row (Real-time):** Event Stream, Logins Per Source
  - **Bottom Row (Batch):** Top Pages by Purchases
- **Refresh:** Auto-refresh every 10 seconds
- **Datasource:** ClickHouse Plugin (official)

---

## Data Models

### Event Schema (Bronze)
```json
{
  "event_id": "uuid-string",
  "user_id": 1-104,
  "event_type": "login|click|purchase|logout",
  "page": "/home|/products|/cart|...",
  "timestamp": "ISO-8601 timestamp",
  "source": "web|mobile"
}
```

### Real-Time Tables (ClickHouse)
```sql
-- events_per_minute (MergeTree)
window_start DateTime, window_end DateTime, event_type String, event_count UInt64

-- logins_per_source (MergeTree)
window_start DateTime, window_end DateTime, source String, login_count UInt64

-- purchases_per_minute (MergeTree)
window_start DateTime, window_end DateTime, purchase_count UInt64
```

### Gold Tables (ClickHouse)
```sql
-- daily_active_users (ReplacingMergeTree)
event_date Date, dau_count Int64, updated_at DateTime

-- conversion_rate_daily (ReplacingMergeTree)
event_date Date, conversion_rate Float64, total_purchases Int64, dau_count Int64

-- events_per_source_daily (ReplacingMergeTree)
event_date Date, source String, event_count Int64

-- purchases_per_page_daily (ReplacingMergeTree)
event_date Date, page String, purchase_count Int64
```

---

## Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Message Broker** | Apache Kafka | 7.5.3 | Event streaming |
| **Stream Processing** | Apache Spark | 3.5.1 | Real-time aggregations |
| **Data Lake** | Delta Lake | 3.1.0 | ACID-compliant storage |
| **Batch Orchestration** | Apache Airflow | 2.8.1 | Workflow management |
| **Serving Database** | ClickHouse | 23.8 | Real-time OLAP |
| **Metadata Database** | MySQL | 8.0 | Airflow metadata |
| **Visualization** | Grafana | 10.2.0 | Dashboards |
| **Container Runtime** | Docker Compose | - | Service orchestration |

---

## Design Decisions

### Why ClickHouse over PostgreSQL?
- **Columnar Storage:** Lightning-fast aggregations on large datasets.
- **Compression:** significantly reduces storage footprint.
- **MergeTree Engine:** Designed for high-speed ingestion of time-series data.
- **Scalability:** Horizontal scaling via sharding/replication (easier than Postgres).

### Why Delta Lake over Apache Iceberg?
- **Native Spark integration** - First-class support in PySpark
- **Simpler setup** - No additional catalog required
- **Time travel** - Built-in versioning for debugging
- **ACID guarantees** - Safe concurrent reads/writes

### Why MySQL for Airflow?
- **Compatibility:** Official support in Airflow.
- **Separation of Concerns:** Keeps metadata separate from analytical data (ClickHouse).
- **Stability:** Proven reliability for transactional metadata workloads.

### Why Append Mode for Realtime Tables?
- **ClickHouse Optimization:** ClickHouse prefers appends over updates.
- **Aggregation on Read:** Queries use `SUM()` to aggregate micro-batches.
- **Deduplication:** `ReplacingMergeTree` handles updates independently in background.

---

## Scaling Considerations

### Current Limits
- **Throughput:** 5 events/sec (can handle 1000+)
- **Memory:** ~6-7 GB total
- **Concurrency:** Single-node (all services on one machine)

### How to Scale

**Increase Throughput:**
```yaml
# docker-compose.yml
producer:
  environment:
    EVENTS_PER_SECOND: "50"  # Increase from 5
```

**Add More Partitions:**
```bash
# Increase Kafka partitions
kafka-topics --bootstrap-server kafka:9092 \
  --alter --topic user-events --partitions 10
```

**Horizontal Scaling:**
- Deploy Spark on a cluster (Kubernetes, YARN)
- Use ClickHouse Cloud or a cluster
- Separate Airflow workers (Celery/Kubernetes Executor)
- Use Kafka cluster (multiple brokers)

---

## Security Considerations

**Current State:** Demo/development - minimal security

**Production Recommendations:**
1. **Authentication:**
   - Enable Kafka SASL/SSL
   - ClickHouse user/password and SSL
   - Airflow RBAC with LDAP/OAuth
   - Grafana OAuth integration

2. **Authorization:**
   - Kafka ACLs per topic
   - ClickHouse RBAC (Role Based Access Control)
   - Airflow role-based permissions

3. **Encryption:**
   - Kafka TLS encryption
   - Data at rest encryption
   - Secure secrets management (Vault, AWS Secrets)

---

## Monitoring & Observability

### Current Monitoring
- Grafana dashboards for business metrics
- Airflow UI for DAG execution
- Docker logs for debugging

### Production Recommendations
1. **Metrics:** Prometheus + Grafana for system metrics (Container/JVM stats)
2. **Logging:** ELK/EFK stack (Elasticsearch, Logstash, Kibana)
3. **Tracing:** Jaeger for distributed tracing
4. **Alerting:** Grafana alerts + PagerDuty/Slack

---

## Disaster Recovery

### Current Backup Strategy
- **Delta Lake:** Versioned (time travel to previous versions)
- **ClickHouse:** No automatic backups

### Recommended Strategy
```bash
# Backup ClickHouse
clickhouse-backup create full_backup

# Backup Delta Lake
docker cp spark-raw-landing:/data/lakehouse ./lakehouse-backup

# Restore ClickHouse
clickhouse-backup restore full_backup
```

---

## Performance Benchmarks

**Measured on:** Windows Docker Desktop with 6GB RAM

| Metric | Value |
|--------|-------|
| Event ingestion rate | 5 events/sec |
| End-to-end latency (Kafka → ClickHouse) | < 10 seconds |
| Bronze write throughput | ~300 events/min → ~200 KB/min |
| Spark micro-batch time | 5-10 seconds |
| Airflow DAG execution | 2-3 minutes |
| Grafana query time | < 20ms |
| Dashboard refresh | 10 seconds |

---

## Future Enhancements

1. **Real-time ML:** Add Spark MLlib for anomaly detection
2. **Data Quality:** Implement Great Expectations for validation
3. **Schema Evolution:** Add schema registry (Confluent/AWS Glue)
4. **CDC:** Capture database changes with Debezium
5. **API Layer:** Add REST API with FastAPI (ClickHouse driver)
6. **Notebook Integration:** Add Jupyter for ad-hoc analysis
7. **Partitioning:** Implement Z-ordering for faster queries
8. **Compaction:** Auto-compact Delta tables periodically
