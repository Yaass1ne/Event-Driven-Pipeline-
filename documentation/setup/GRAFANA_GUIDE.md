# Grafana Dashboard Guide

## 🚀 Quick Access

**URL**: http://localhost:3000
**Username**: `admin`
**Password**: `admin`

## 📊 Pre-Configured Dashboard

Your Grafana instance comes with a **pre-configured dashboard** called **"Lakehouse Platform Overview"** that's automatically loaded on startup.

### What You'll See

#### **Top Row: Key Metrics (4 Stat Panels)**
1. **Daily Active Users** - Total unique users today (from Gold layer)
2. **Conversion Rate** - Purchase conversion percentage
3. **Total Purchases** - Number of purchases today
4. **Total Events Today** - All events processed

#### **Middle Row: Real-Time Charts (2 Time Series)**
5. **Events Per Minute (Last Hour)** - Line chart showing event counts by type
   - Auto-refreshes every 10 seconds
   - Shows: login, click, purchase, logout events
   - Source: ClickHouse `realtime.events_per_minute`

6. **Logins Per Source (Last Hour)** - Line chart showing logins by source
   - Auto-refreshes every 10 seconds
   - Shows: mobile vs web logins
   - Source: ClickHouse `realtime.logins_per_source`

#### **Bottom Row: Analysis Panels**
7. **Events by Source (Today)** - Pie chart showing traffic distribution
   - Mobile vs web breakdown

8. **Top Pages by Purchases** - Table showing best performing pages
   - Shows page names and purchase counts
   - Ordered by purchase count descending

## 🎯 How to Use the Dashboard

### First-Time Setup

1. **Open browser** and go to: http://localhost:3000
2. **Login** with admin/admin
3. **Skip password change** (or set a new one)
4. **Dashboard is auto-loaded** - you should immediately see the "Lakehouse Platform Overview" dashboard

### Navigate to the Dashboard

If you don't see the dashboard:
1. Click on **☰** (hamburger menu) in top-left
2. Click **Dashboards**
3. Select **"Lakehouse Platform Overview"**

## 📈 Understanding the Data

### Real-Time vs Historical

**Real-Time Data** (updates every 30 seconds):
- Events per minute charts
- Logins per source chart
- Source: `realtime.*` ClickHouse tables (MergeTree)

**Historical Data** (updates hourly via Airflow):
- Daily Active Users stat
- Conversion Rate stat
- Source: `gold.*` ClickHouse tables (ReplacingMergeTree)

### Data Flow

```
Producer → Kafka → Spark Streaming → ClickHouse (realtime.*) → Grafana (10s refresh)
                         ↓
                   Delta Lake (Bronze)
                         ↓
                   Airflow Batch (hourly)
                         ↓
                   ClickHouse (gold.*) → Grafana
```

## 🛠️ Customizing the Dashboard

### Add a New Panel

1. Click **"Add"** → **"Visualization"** in top-right
2. Select data source: **ClickHouse**
3. Write SQL query (ClickHouse dialect), example:
```sql
SELECT
  toStartOfMinute(window_start) as time,
  sum(purchase_count) as value
FROM realtime.purchases_per_minute
WHERE window_start >= now() - INTERVAL 1 HOUR
GROUP BY time
ORDER BY time
```
4. Choose visualization type (Time series, Bar chart, Gauge, etc.)
5. Click **"Apply"** to add to dashboard
6. Click **"Save"** (disk icon) to save dashboard

## 📊 Useful Queries for New Panels

### Real-Time Monitoring

#### Purchase Rate (Last 10 Minutes)
```sql
SELECT
  window_start as time,
  purchase_count as "Purchases"
FROM realtime.purchases_per_minute
WHERE window_start >= now() - INTERVAL 10 MINUTE
ORDER BY window_start
```

#### Current Event Rate (Events/Second)
```sql
SELECT
  window_start as time,
  sum(event_count) / 60.0 as "Events per Second"
FROM realtime.events_per_minute
WHERE window_start >= now() - INTERVAL 5 MINUTE
GROUP BY time
ORDER BY time
```

### Historical Analysis

#### Daily Active Users Trend (Last 7 Days)
```sql
SELECT
  event_date as time,
  dau_count as "DAU"
FROM gold.daily_active_users
WHERE event_date >= today() - 7
ORDER BY event_date
```

#### Conversion Rate Over Time
```sql
SELECT
  event_date as time,
  round(conversion_rate * 100, 2) as "Conversion %"
FROM gold.conversion_rate_daily
ORDER BY event_date
```

## 🔧 Troubleshooting

### "No Data" on All Panels

**Cause:** ClickHouse not populated yet or Grafana can't connect
**Solution:**

```bash
# 1. Check ClickHouse is running
docker compose ps clickhouse

# 2. Verify data exists via CLI
docker compose exec clickhouse clickhouse-client --query "SELECT count(*) FROM realtime.events_per_minute"
```

### Panels Show "No Data"

**Possible causes:**
1. **Time range too far in past** - Adjust time picker to "Last 1 hour"
2. **Data not generated yet** - Wait for producer/streaming jobs to run
3. **Airflow DAG not run** - Historical panels need first DAG run

### Query Errors

**"Unknown table"**:
- Check schema/database name: `realtime.` or `gold.`

**"Connection refused"**:
- Verify ClickHouse is reachable at `clickhouse:8123` (internal docker network)

## 📚 Resources

### Grafana Documentation
- ClickHouse Plugin: https://grafana.com/grafana/plugins/grafana-clickhouse-datasource/
- Panel types: https://grafana.com/docs/grafana/latest/panels/

### ClickHouse SQL
- Date/Time functions: https://clickhouse.com/docs/en/sql-reference/functions/date-time-functions
- Aggregations: https://clickhouse.com/docs/en/sql-reference/aggregate-functions
