# Event-Driven Data Pipeline Documentation

This document details the architecture, data structures, and processing logic of the Lakehouse platform.

## 1. Data Source: Producer
The producer (`producer/producer.py`) simulates user activity on an e-commerce platform.

### Producer JSON Structure
Each event is a JSON object with the following schema:
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",  // UUID
  "user_id": 123,                                     // Integer
  "event_type": "click",                              // String: login, click, purchase, logout
  "page": "/products/detail",                         // String: URL path
  "timestamp": "2024-01-01T12:00:00.000000+00:00",    // ISO8601 String
  "source": "mobile"                                  // String: web, mobile
}
```

### Kafka Handling
*   **Topic**: `user-events`
*   **Key**: `event_type` (ensures events of same type go to same partition if ordered)
*   **Serialization**: JSON value, String key.

---

## 2. Ingestion Layer: Spark Raw Landing
**Script**: `spark/jobs/spark_raw_landing.py`
**Type**: Structured Streaming

### Treatment
1.  Reads stream from Kafka topic `user-events`.
2.  Parses the JSON value into a structured Spark DataFrame.
3.  Adds metadata columns:
    *   `ingestion_timestamp`: Current timestamp of processing.
4.  Writes to **Bronze Layer** (Delta Lake) at `lakehouse/bronze/user_events`.
    *   Mode: Append
    *   Format: Delta (Parquet backed)

---

## 3. Refinement Layer: Bronze to Silver
**Script**: `spark/jobs/spark_bronze_to_silver.py`
**Type**: Batch (Hourly)

### Treatment
1.  Reads all data from Bronze table.
2.  **Deduplication**: Removes duplicate events based on `event_id`.
3.  **Schema Enforcement**: Casts types (timestamp to TimestampType, user_id to Integer).
4.  **Cleaning**: Filters out malformed records (null event_ids).
5.  Adds `processed_timestamp`.
6.  Writes to **Silver Layer** (Delta Lake) at `lakehouse/silver/user_events`.
    *   Mode: Overwrite (or Merge in production)

---

## 4. Aggregation Layer: Silver to Gold
**Script**: `spark/jobs/spark_silver_to_gold.py`
**Type**: Batch (Hourly)

### Treatment
Creates a Dimensional Model (Star Schema) and Aggregate KPIs.

#### Data Warehouse Schema (Gold Layer)
1.  **Fact Table**: `fact_events`
    *   Granularity: Individual event (cleaned)
    *   Partitioned by: `event_date`
2.  **Dimension Tables**:
    *   `dim_users`: User statistics (total events, source count).
    *   `dim_pages`: Page statistics (popularity).
3.  **KPI Aggregates**:
    *   `kpi_dau`: Daily Active Users.
    *   `kpi_events_per_source`: Event counts by source/day.
    *   `kpi_conversion_rate`: Purchases / Total Events per day.

### ClickHouse Sync
The KPI aggregate tables are also written to ClickHouse (`gold` schema) for fast dashboarding.
*   Engine: `ReplacingMergeTree` (handles updates/duplicates by replacing old versions).

---

## 5. Real-Time Layer: Spark Fast Agg
**Script**: `spark/jobs/spark_fast_agg.py`
**Type**: Structured Streaming

### Treatment
1.  Reads stream from Kafka `user-events`.
2.  **Windowed Aggregation**: Computes metrics over 1-minute tumbling windows.
    *   *Events per minute* (by type)
    *   *Logins per source* (by source)
    *   *Purchases per minute*
3.  **Watermarking**: Handles late data (2-minute watermark).
4.  Writes results continuously to ClickHouse (`realtime` schema).

---

## 6. Serving Layer: ClickHouse
Stores both real-time streams and historical batch aggregates.

### Schemas
#### `realtime` Database
*   **Table**: `events_per_minute`
    *   Columns: `window_start`, `window_end`, `event_type`, `event_count`
    *   Engine: `MergeTree`
    *   Ordering: `(window_start, event_type)`

#### `gold` Database
*   **Table**: `daily_active_users`
    *   Columns: `event_date`, `dau_count`, `updated_at`
    *   Engine: `ReplacingMergeTree`
    *   Ordering: `event_date`

---

## 7. Visualization: Grafana
**Datasource**: ClickHouse Plugin (`http://clickhouse:8123`)

### Example Queries
**Real-Time Event Stream**:
```sql
SELECT
  window_start as time,
  event_type as metric,
  sum(event_count) as value
FROM realtime.events_per_minute
WHERE $__timeFilter(window_start)
GROUP BY window_start, event_type
ORDER BY window_start ASC
```

**Daily Active Users (Batch)**:
```sql
SELECT dau_count 
FROM gold.daily_active_users 
ORDER BY event_date DESC 
LIMIT 1
```

**Conversion Rate**:
```sql
SELECT round((conversion_rate * 100), 2) as value 
FROM gold.conversion_rate_daily 
ORDER BY event_date DESC 
LIMIT 1
```
