# Grafana Dashboard Guide

## 🚀 Quick Access

**URL**: http://localhost:3000
**Username**: `admin`
**Password**: `admin`

## 📊 Pre-Configured Dashboard

Your Grafana instance comes with a **pre-configured dashboard** called **"Lakehouse Platform Overview"** that's automatically loaded on startup.

### What You'll See

#### **Top Row: Key Metrics (4 Stat Panels)**
1. **Daily Active Users** - Total unique users today
2. **Conversion Rate** - Purchase conversion percentage
3. **Total Purchases** - Number of purchases today
4. **Total Events Today** - All events processed

#### **Middle Row: Real-Time Charts (2 Time Series)**
5. **Events Per Minute (Last Hour)** - Line chart showing event counts by type
   - Auto-refreshes every 10 seconds
   - Shows: login, click, purchase, logout events
   - Last 1 hour of data

6. **Logins Per Source (Last Hour)** - Line chart showing logins by source
   - Auto-refreshes every 10 seconds
   - Shows: mobile vs web logins

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

### Dashboard Features

#### Auto-Refresh
- Dashboard automatically refreshes every **10 seconds**
- See the refresh interval in top-right corner
- Change it by clicking the dropdown next to the refresh icon

#### Time Range
- Default: Last 1 hour
- Change by clicking the time picker in top-right
- Options: Last 5m, 15m, 30m, 1h, 3h, 6h, 12h, 24h, etc.

#### Zoom In/Out
- Click and drag on any chart to zoom into a time range
- Click "Zoom out" button to return to full range

#### Panel Menu
- Hover over any panel title
- Click the **⋮** menu for options:
  - View - Full screen mode
  - Edit - Modify panel query/settings
  - Share - Get embed code or snapshot
  - Explore - Open in Explore view with full query editor

## 📈 Understanding the Data

### Real-Time vs Historical

**Real-Time Data** (updates every 30 seconds):
- Events per minute charts
- Logins per source chart
- Source: `realtime.*` PostgreSQL tables

**Historical Data** (updates hourly via Airflow):
- Daily Active Users stat
- Conversion Rate stat
- Total Purchases stat
- Events by source pie chart
- Top pages table
- Source: `gold.*` PostgreSQL tables

### Data Flow

```
Producer → Kafka → Spark Streaming → PostgreSQL (realtime.*) → Grafana (10s refresh)
                         ↓
                   Delta Lake (Bronze)
                         ↓
                   Airflow Batch (hourly)
                         ↓
                   PostgreSQL (gold.*) → Grafana
```

## 🛠️ Customizing the Dashboard

### Add a New Panel

1. Click **"Add"** → **"Visualization"** in top-right
2. Select data source: **PostgreSQL**
3. Write SQL query, example:
```sql
SELECT
  window_start as time,
  purchase_count as value
FROM realtime.purchases_per_minute
WHERE window_start >= NOW() - INTERVAL '1 hour'
ORDER BY window_start
```
4. Choose visualization type (Time series, Bar chart, Gauge, etc.)
5. Click **"Apply"** to add to dashboard
6. Click **"Save"** (disk icon) to save dashboard

### Edit Existing Panel

1. Hover over panel title
2. Click **⋮** → **Edit**
3. Modify query or visualization settings
4. Click **"Apply"** then **"Save"**

### Duplicate Dashboard

1. Click **⚙️** (dashboard settings) in top-right
2. Click **"Save As"**
3. Give it a new name
4. Click **"Save"**

## 📊 Useful Queries for New Panels

### Real-Time Monitoring

#### Purchase Rate (Last 10 Minutes)
```sql
SELECT
  window_start as time,
  purchase_count as "Purchases"
FROM realtime.purchases_per_minute
WHERE window_start >= NOW() - INTERVAL '10 minutes'
ORDER BY window_start
```

#### Current Event Rate (Events/Second)
```sql
SELECT
  window_start as time,
  SUM(event_count) / 60.0 as "Events per Second"
FROM realtime.events_per_minute
WHERE window_start >= NOW() - INTERVAL '5 minutes'
GROUP BY window_start
ORDER BY window_start
```

#### Mobile vs Web Login Split
```sql
SELECT
  source,
  SUM(login_count) as count
FROM realtime.logins_per_source
WHERE window_start >= NOW() - INTERVAL '30 minutes'
GROUP BY source
```

### Historical Analysis

#### Daily Active Users Trend (Last 7 Days)
```sql
SELECT
  event_date as time,
  dau_count as "DAU"
FROM gold.daily_active_users
WHERE event_date >= CURRENT_DATE - 7
ORDER BY event_date
```

#### Conversion Rate Over Time
```sql
SELECT
  event_date as time,
  ROUND(conversion_rate * 100, 2) as "Conversion %"
FROM gold.conversion_rate_daily
ORDER BY event_date
```

#### Traffic Source Distribution (Today)
```sql
SELECT
  source,
  event_count
FROM gold.events_per_source_daily
WHERE event_date = CURRENT_DATE
```

#### Top 10 Pages by Purchases (Today)
```sql
SELECT
  page,
  purchase_count
FROM gold.purchases_per_page_daily
WHERE event_date = CURRENT_DATE
ORDER BY purchase_count DESC
LIMIT 10
```

### Advanced Queries

#### Week-over-Week Growth
```sql
SELECT
  event_date as time,
  dau_count as "This Week",
  LAG(dau_count, 7) OVER (ORDER BY event_date) as "Last Week",
  ROUND(100.0 * (dau_count - LAG(dau_count, 7) OVER (ORDER BY event_date)) /
        NULLIF(LAG(dau_count, 7) OVER (ORDER BY event_date), 0), 1) as "Growth %"
FROM gold.daily_active_users
ORDER BY event_date DESC
```

#### Hourly Event Distribution (Today)
```sql
SELECT
  DATE_TRUNC('hour', window_start) as time,
  event_type,
  SUM(event_count) as count
FROM realtime.events_per_minute
WHERE window_start >= CURRENT_DATE
GROUP BY 1, 2
ORDER BY 1, 2
```

## 🚨 Setting Up Alerts

### Create an Alert Rule

1. Edit a panel with a time series query
2. Click **"Alert"** tab
3. Click **"Create alert rule from this panel"**
4. Set conditions, example:
   - **Condition**: `WHEN last() OF query(A) IS BELOW 50`
   - **For**: 5 minutes
   - **Meaning**: Alert if events per minute drops below 50 for 5 minutes

5. Add notification channel (Email, Slack, PagerDuty, etc.)
6. Save the alert rule

### Example Alert: Purchase Drop

**Use Case**: Alert if purchases drop to zero

**Query**:
```sql
SELECT
  SUM(purchase_count) as value
FROM realtime.purchases_per_minute
WHERE window_start >= NOW() - INTERVAL '5 minutes'
```

**Condition**:
- WHEN `last()` OF query(A) IS BELOW 1
- FOR 5 minutes

**Action**: Send notification to #alerts Slack channel

## 🎨 Dashboard Tips

### Color Schemes
- Use consistent colors for event types across panels
- Green for success metrics (purchases, conversions)
- Blue for neutral metrics (events, users)
- Red for alerts or errors

### Panel Sizing
- Stats panels: 6 units wide (4 per row)
- Time series: 12 units wide (2 per row) or 24 units (full width)
- Tables: 12-16 units wide

### Best Practices
1. **Group related metrics** - Put real-time panels together, historical together
2. **Use consistent time ranges** - Align related panels to same time window
3. **Add descriptions** - Use panel descriptions to explain what data shows
4. **Set meaningful thresholds** - Use red/yellow/green for stat panels
5. **Auto-refresh sensibly** - 10s for real-time, 1m for near-real-time, 5m for historical

## 🔧 Troubleshooting

### Dashboard Not Loading

```bash
# Check Grafana is running
docker compose ps grafana

# Check Grafana logs
docker compose logs grafana --tail 50

# Restart Grafana
docker compose restart grafana
```

### No Data Showing

**Check PostgreSQL connection:**
1. Go to **Configuration** → **Data Sources**
2. Click **PostgreSQL**
3. Scroll down and click **"Save & Test"**
4. Should see: "Database Connection OK"

**If connection fails:**
```bash
# Check PostgreSQL is running
docker compose ps postgres

# Verify data exists
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT COUNT(*) FROM realtime.events_per_minute;"
```

### Panels Show "No Data"

**Possible causes:**
1. **Time range too far in past** - Adjust time picker to "Last 1 hour"
2. **Data not generated yet** - Wait for producer/streaming jobs to run
3. **Airflow DAG not run** - Historical panels need first DAG run

**Check data exists:**
```bash
# Real-time data
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT * FROM realtime.events_per_minute ORDER BY window_start DESC LIMIT 5;"

# Historical data
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT * FROM gold.daily_active_users;"
```

### Query Errors

**"relation does not exist"**:
- Table hasn't been created yet
- Check schema name: `realtime.` or `gold.`
- Run Airflow DAG to create Gold tables

**"permission denied"**:
- Check datasource credentials (platform/platform123)
- Verify user has access: `GRANT ALL ON SCHEMA realtime, gold TO platform;`

## 📚 Resources

### Grafana Documentation
- Panel types: https://grafana.com/docs/grafana/latest/panels/
- Alerting: https://grafana.com/docs/grafana/latest/alerting/
- PostgreSQL datasource: https://grafana.com/docs/grafana/latest/datasources/postgres/

### Query Language
- PostgreSQL functions: https://www.postgresql.org/docs/15/functions.html
- Window functions: https://www.postgresql.org/docs/15/tutorial-window.html
- Date/time functions: https://www.postgresql.org/docs/15/functions-datetime.html

## 🎯 Next Steps

1. **Explore the dashboard** - Click around, zoom in/out, change time ranges
2. **Create your own panels** - Add business-specific metrics
3. **Set up alerts** - Get notified when metrics go out of range
4. **Share with team** - Create user accounts or use anonymous access
5. **Export/import** - Save dashboard JSON for version control

---

**Dashboard automatically updates!** Just leave the browser tab open and watch your data flow in real-time. 📊✨
