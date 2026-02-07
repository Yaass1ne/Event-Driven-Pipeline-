# Example Database Queries

This guide provides useful SQL queries to explore your lakehouse data.

## Quick Access

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U platform -d serving
```

---

## Real-Time Schema Queries

### Events Per Minute

**View recent event activity:**
```sql
SELECT
  window_start,
  event_type,
  SUM(event_count) as total_events
FROM realtime.events_per_minute
GROUP BY window_start, event_type
ORDER BY window_start DESC
LIMIT 20;
```

**Get current minute's events:**
```sql
SELECT
  event_type,
  SUM(event_count) as count
FROM realtime.events_per_minute
WHERE window_start = date_trunc('minute', NOW())
GROUP BY event_type
ORDER BY count DESC;
```

**Events by type (last hour):**
```sql
SELECT
  event_type,
  SUM(event_count) as total,
  AVG(event_count) as avg_per_minute,
  MAX(event_count) as peak
FROM realtime.events_per_minute
WHERE window_start >= NOW() - INTERVAL '1 hour'
GROUP BY event_type
ORDER BY total DESC;
```

### Logins Per Source

**Current login distribution:**
```sql
SELECT
  source,
  SUM(login_count) as total_logins
FROM realtime.logins_per_source
WHERE window_start >= NOW() - INTERVAL '30 minutes'
GROUP BY source
ORDER BY total_logins DESC;
```

**Login trends over time:**
```sql
SELECT
  window_start,
  source,
  SUM(login_count) as logins
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
  SUM(purchase_count) as purchases
FROM realtime.purchases_per_minute
GROUP BY window_start
ORDER BY window_start DESC
LIMIT 10;
```

**Purchase rate (last hour):**
```sql
SELECT
  COUNT(DISTINCT window_start) as minutes,
  SUM(purchase_count) as total_purchases,
  ROUND(SUM(purchase_count)::numeric / COUNT(DISTINCT window_start), 2) as avg_per_minute
FROM realtime.purchases_per_minute
WHERE window_start >= NOW() - INTERVAL '1 hour';
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
  LAG(dau_count) OVER (ORDER BY event_date) as previous_day,
  dau_count - LAG(dau_count) OVER (ORDER BY event_date) as daily_change,
  ROUND(
    100.0 * (dau_count - LAG(dau_count) OVER (ORDER BY event_date)) /
    NULLIF(LAG(dau_count) OVER (ORDER BY event_date), 0),
    2
  ) as growth_percent
FROM gold.daily_active_users
ORDER BY event_date DESC;
```

### Conversion Rate

**Today's conversion metrics:**
```sql
SELECT
  event_date,
  ROUND((conversion_rate * 100)::numeric, 2) as conversion_pct,
  total_purchases,
  dau_count,
  updated_at
FROM gold.conversion_rate_daily
WHERE event_date = CURRENT_DATE;
```

**Conversion rate trends:**
```sql
SELECT
  event_date,
  ROUND((conversion_rate * 100)::numeric, 2) as conversion_pct,
  total_purchases,
  dau_count
FROM gold.conversion_rate_daily
ORDER BY event_date DESC
LIMIT 7;
```

**Best/worst conversion days:**
```sql
SELECT
  event_date,
  ROUND((conversion_rate * 100)::numeric, 2) as conversion_pct,
  total_purchases
FROM gold.conversion_rate_daily
ORDER BY conversion_rate DESC
LIMIT 5;
```

### Events Per Source

**Today's source breakdown:**
```sql
SELECT
  source,
  event_count,
  ROUND(100.0 * event_count / SUM(event_count) OVER(), 2) as percentage
FROM gold.events_per_source_daily
WHERE event_date = CURRENT_DATE
ORDER BY event_count DESC;
```

**Source trends over time:**
```sql
SELECT
  event_date,
  source,
  event_count
FROM gold.events_per_source_daily
ORDER BY event_date DESC, source;
```

**Mobile vs Web comparison:**
```sql
SELECT
  event_date,
  MAX(CASE WHEN source = 'mobile' THEN event_count END) as mobile_events,
  MAX(CASE WHEN source = 'web' THEN event_count END) as web_events,
  ROUND(
    100.0 * MAX(CASE WHEN source = 'mobile' THEN event_count END) /
    NULLIF(SUM(event_count), 0),
    2
  ) as mobile_percentage
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
  ROUND(100.0 * purchase_count / SUM(purchase_count) OVER(), 2) as percentage
FROM gold.purchases_per_page_daily
WHERE event_date = CURRENT_DATE
ORDER BY purchase_count DESC;
```

**Page performance trends:**
```sql
SELECT
  page,
  event_date,
  purchase_count
FROM gold.purchases_per_page_daily
WHERE page IN ('/checkout', '/cart', '/products/detail')
ORDER BY event_date DESC, purchase_count DESC;
```

**Pages with no purchases:**
```sql
SELECT DISTINCT page
FROM gold.purchases_per_page_daily
WHERE purchase_count = 0
  AND event_date = CURRENT_DATE;
```

---

## Combined Analytics Queries

### Platform Overview

**Daily summary:**
```sql
SELECT
  d.event_date,
  d.dau_count as active_users,
  ROUND((c.conversion_rate * 100)::numeric, 2) as conversion_pct,
  c.total_purchases,
  SUM(e.event_count) as total_events
FROM gold.daily_active_users d
JOIN gold.conversion_rate_daily c ON d.event_date = c.event_date
JOIN gold.events_per_source_daily e ON d.event_date = e.event_date
WHERE d.event_date = CURRENT_DATE
GROUP BY d.event_date, d.dau_count, c.conversion_rate, c.total_purchases;
```

### Real-Time + Historical Comparison

**Current activity vs daily average:**
```sql
WITH current_hour AS (
  SELECT
    SUM(event_count) as events_this_hour
  FROM realtime.events_per_minute
  WHERE window_start >= date_trunc('hour', NOW())
),
daily_avg AS (
  SELECT
    AVG(event_count) as avg_events_per_day
  FROM gold.events_per_source_daily
)
SELECT
  events_this_hour,
  avg_events_per_day,
  ROUND(100.0 * events_this_hour / NULLIF(avg_events_per_day, 0), 2) as current_vs_avg_pct
FROM current_hour, daily_avg;
```

### User Engagement Metrics

**Engagement score (events per user):**
```sql
SELECT
  event_date,
  dau_count,
  (SELECT SUM(event_count) FROM gold.events_per_source_daily e WHERE e.event_date = d.event_date) as total_events,
  ROUND(
    (SELECT SUM(event_count) FROM gold.events_per_source_daily e WHERE e.event_date = d.event_date)::numeric /
    NULLIF(d.dau_count, 0),
    2
  ) as events_per_user
FROM gold.daily_active_users d
ORDER BY event_date DESC
LIMIT 7;
```

---

## Data Quality Checks

### Check for Missing Data

**Gaps in real-time data:**
```sql
SELECT
  generate_series(
    date_trunc('minute', NOW() - INTERVAL '1 hour'),
    date_trunc('minute', NOW()),
    '1 minute'::interval
  ) as expected_minute
EXCEPT
SELECT DISTINCT window_start
FROM realtime.events_per_minute
WHERE window_start >= NOW() - INTERVAL '1 hour'
ORDER BY 1 DESC;
```

**Days with no data:**
```sql
SELECT
  generate_series(
    CURRENT_DATE - INTERVAL '7 days',
    CURRENT_DATE,
    '1 day'::interval
  )::date as expected_date
EXCEPT
SELECT event_date
FROM gold.daily_active_users
ORDER BY 1 DESC;
```

### Validate Data Consistency

**Check conversion rate calculation:**
```sql
SELECT
  event_date,
  total_purchases,
  dau_count,
  ROUND((conversion_rate * 100)::numeric, 2) as reported_conversion,
  ROUND(100.0 * total_purchases / NULLIF(dau_count, 0), 2) as calculated_conversion,
  ABS(
    ROUND((conversion_rate * 100)::numeric, 2) -
    ROUND(100.0 * total_purchases / NULLIF(dau_count, 0), 2)
  ) as difference
FROM gold.conversion_rate_daily
WHERE event_date = CURRENT_DATE;
```

**Check event totals match:**
```sql
SELECT
  event_date,
  SUM(event_count) as total_from_source_table,
  (SELECT SUM(purchase_count) FROM gold.purchases_per_page_daily p WHERE p.event_date = e.event_date) as purchases_from_page_table
FROM gold.events_per_source_daily e
WHERE event_date = CURRENT_DATE
GROUP BY event_date;
```

---

## Performance Queries

### Table Sizes

**Check database size:**
```sql
SELECT
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
  pg_total_relation_size(schemaname||'.'||tablename) as bytes
FROM pg_tables
WHERE schemaname IN ('realtime', 'gold')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Row Counts

**Count all records:**
```sql
SELECT 'realtime.events_per_minute' as table_name, COUNT(*) FROM realtime.events_per_minute
UNION ALL
SELECT 'realtime.logins_per_source', COUNT(*) FROM realtime.logins_per_source
UNION ALL
SELECT 'realtime.purchases_per_minute', COUNT(*) FROM realtime.purchases_per_minute
UNION ALL
SELECT 'gold.daily_active_users', COUNT(*) FROM gold.daily_active_users
UNION ALL
SELECT 'gold.conversion_rate_daily', COUNT(*) FROM gold.conversion_rate_daily
UNION ALL
SELECT 'gold.events_per_source_daily', COUNT(*) FROM gold.events_per_source_daily
UNION ALL
SELECT 'gold.purchases_per_page_daily', COUNT(*) FROM gold.purchases_per_page_daily;
```

---

## Export Queries

### Export to CSV

**From psql command line:**
```bash
# Export to CSV file
docker compose exec postgres psql -U platform -d serving -c \
  "COPY (SELECT * FROM gold.daily_active_users) TO STDOUT WITH CSV HEADER" > dau_export.csv
```

### Create Views for Easy Access

**Create a combined metrics view:**
```sql
CREATE OR REPLACE VIEW gold.daily_metrics AS
SELECT
  d.event_date,
  d.dau_count,
  ROUND((c.conversion_rate * 100)::numeric, 2) as conversion_pct,
  c.total_purchases,
  m.mobile_events,
  w.web_events
FROM gold.daily_active_users d
LEFT JOIN gold.conversion_rate_daily c ON d.event_date = c.event_date
LEFT JOIN (
  SELECT event_date, event_count as mobile_events
  FROM gold.events_per_source_daily
  WHERE source = 'mobile'
) m ON d.event_date = m.event_date
LEFT JOIN (
  SELECT event_date, event_count as web_events
  FROM gold.events_per_source_daily
  WHERE source = 'web'
) w ON d.event_date = w.event_date
ORDER BY d.event_date DESC;

-- Query the view
SELECT * FROM gold.daily_metrics;
```

---

## Tips

1. **Use EXPLAIN ANALYZE** to check query performance:
   ```sql
   EXPLAIN ANALYZE SELECT * FROM gold.daily_active_users;
   ```

2. **Create indexes** for frequently queried columns:
   ```sql
   CREATE INDEX IF NOT EXISTS idx_events_window ON realtime.events_per_minute(window_start);
   ```

3. **Use transactions** for data consistency:
   ```sql
   BEGIN;
   -- Your queries here
   COMMIT;
   ```

4. **Backup before destructive operations:**
   ```bash
   docker compose exec postgres pg_dump -U platform serving > backup.sql
   ```
