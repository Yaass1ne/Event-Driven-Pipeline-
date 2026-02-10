# Example Database Queries

This guide provides useful SQL queries to explore your lakehouse data in ClickHouse.

## Quick Access

```bash
# Connect to ClickHouse via Docker
docker compose exec clickhouse clickhouse-client
```

---

## Real-Time Schema Queries

### Events Per Minute

**View recent event activity:**
```sql
SELECT
  window_start,
  event_type,
  sum(event_count) as total_events
FROM realtime.events_per_minute
GROUP BY window_start, event_type
ORDER BY window_start DESC
LIMIT 20;
```

**Get current minute's events:**
```sql
SELECT
  event_type,
  sum(event_count) as count
FROM realtime.events_per_minute
WHERE window_start = toStartOfMinute(now())
GROUP BY event_type
ORDER BY count DESC;
```

**Events by type (last hour):**
```sql
SELECT
  event_type,
  sum(event_count) as total,
  avg(event_count) as avg_per_minute,
  max(event_count) as peak
FROM realtime.events_per_minute
WHERE window_start >= now() - INTERVAL 1 HOUR
GROUP BY event_type
ORDER BY total DESC;
```

### Logins Per Source

**Current login distribution:**
```sql
SELECT
  source,
  sum(login_count) as total_logins
FROM realtime.logins_per_source
WHERE window_start >= now() - INTERVAL 30 MINUTE
GROUP BY source
ORDER BY total_logins DESC;
```

**Login trends over time:**
```sql
SELECT
  window_start,
  source,
  sum(login_count) as logins
FROM realtime.logins_per_source
GROUP BY window_start, source
ORDER BY window_start DESC
LIMIT 20;
```

### Purchases Per Minute

**Recent purchase activity:**
```sql
SELECT
  window_start,
  sum(purchase_count) as purchases
FROM realtime.purchases_per_minute
GROUP BY window_start
ORDER BY window_start DESC
LIMIT 10;
```

**Purchase rate (last hour):**
```sql
SELECT
  uniq(window_start) as minutes,
  sum(purchase_count) as total_purchases,
  round(sum(purchase_count) / uniq(window_start), 2) as avg_per_minute
FROM realtime.purchases_per_minute
WHERE window_start >= now() - INTERVAL 1 HOUR;
```

---

## Gold Schema Queries

### Daily Active Users

**View DAU history:**
```sql
SELECT
  event_date,
  dau_count,
  updated_at
FROM gold.daily_active_users
ORDER BY event_date DESC;
```

**DAU growth calculation:**
```sql
SELECT
    event_date,
    dau_count,
    neighbor(dau_count, -1) as previous_day,
    dau_count - previous_day as daily_change,
    round(100.0 * daily_change / previous_day, 2) as growth_percent
FROM gold.daily_active_users
ORDER BY event_date DESC;
```

### Conversion Rate

**Today's conversion metrics:**
```sql
SELECT
  event_date,
  round(conversion_rate * 100, 2) as conversion_pct,
  total_purchases,
  dau_count,
  updated_at
FROM gold.conversion_rate_daily
WHERE event_date = today();
```

**Conversion rate trends:**
```sql
SELECT
  event_date,
  round(conversion_rate * 100, 2) as conversion_pct,
  total_purchases,
  dau_count
FROM gold.conversion_rate_daily
ORDER BY event_date DESC
LIMIT 7;
```

### Events Per Source

**Today's source breakdown:**
```sql
SELECT
  source,
  event_count,
  round(100.0 * event_count / sum(event_count) OVER (), 2) as percentage
FROM gold.events_per_source_daily
WHERE event_date = today()
ORDER BY event_count DESC;
```

**Mobile vs Web comparison:**
```sql
SELECT
  event_date,
  maxIf(event_count, source = 'mobile') as mobile_events,
  maxIf(event_count, source = 'web') as web_events,
  round(100.0 * mobile_events / sum(event_count), 2) as mobile_percentage
FROM gold.events_per_source_daily
GROUP BY event_date
ORDER BY event_date DESC;
```

### Purchases Per Page

**Top performing pages today:**
```sql
SELECT
  page,
  purchase_count,
  round(100.0 * purchase_count / sum(purchase_count) OVER (), 2) as percentage
FROM gold.purchases_per_page_daily
WHERE event_date = today()
ORDER BY purchase_count DESC;
```

---

## Combined Analytics Queries

### Platform Overview

**Daily summary:**
```sql
SELECT
  d.event_date,
  d.dau_count as active_users,
  round(c.conversion_rate * 100, 2) as conversion_pct,
  c.total_purchases,
  sum(e.event_count) as total_events
FROM gold.daily_active_users d
JOIN gold.conversion_rate_daily c ON d.event_date = c.event_date
JOIN gold.events_per_source_daily e ON d.event_date = e.event_date
WHERE d.event_date = today()
GROUP BY d.event_date, d.dau_count, c.conversion_rate, c.total_purchases;
```

### Real-Time + Historical Comparison

**Current activity vs daily average:**
```sql
WITH current_hour AS (
  SELECT
    sum(event_count) as events_this_hour
  FROM realtime.events_per_minute
  WHERE window_start >= toStartOfHour(now())
),
daily_avg AS (
  SELECT
    avg(event_count) as avg_events_per_day
  FROM gold.events_per_source_daily
)
SELECT
  events_this_hour,
  avg_events_per_day,
  round(100.0 * events_this_hour / avg_events_per_day, 2) as current_vs_avg_pct
FROM current_hour, daily_avg;
```

---

## Data Quality Checks

### Check for Missing Data

**Gaps in real-time data:**
```sql
WITH time_series AS (
    SELECT toStartOfMinute(now() - INTERVAL 1 HOUR) + number * 60 as expected_minute
    FROM numbers(60)
)
SELECT expected_minute
FROM time_series
WHERE expected_minute NOT IN (
    SELECT DISTINCT window_start
    FROM realtime.events_per_minute
    WHERE window_start >= now() - INTERVAL 1 HOUR
)
ORDER BY expected_minute DESC;
```

---

## Performance Queries

### Table Sizes

**Check database size:**
```sql
SELECT
    database,
    table,
    formatReadableSize(sum(bytes)) as size,
    sum(rows) as rows
FROM system.parts
WHERE active AND database IN ('realtime', 'gold')
GROUP BY database, table
ORDER BY sum(bytes) DESC;
```

### Row Counts

**Count all records:**
```sql
SELECT 'realtime' as db, table, count() as count
FROM realtime.events_per_minute
UNION ALL SELECT 'realtime', 'logins_per_source', count() FROM realtime.logins_per_source
UNION ALL SELECT 'realtime', 'purchases_per_minute', count() FROM realtime.purchases_per_minute
UNION ALL SELECT 'gold', 'daily_active_users', count() FROM gold.daily_active_users
UNION ALL SELECT 'gold', 'conversion_rate_daily', count() FROM gold.conversion_rate_daily
UNION ALL SELECT 'gold', 'events_per_source_daily', count() FROM gold.events_per_source_daily
UNION ALL SELECT 'gold', 'purchases_per_page_daily', count() FROM gold.purchases_per_page_daily;
```
