-- ClickHouse Initialization: E-commerce Analytics Platform

CREATE DATABASE IF NOT EXISTS realtime;
CREATE DATABASE IF NOT EXISTS gold;

-- ==================== Real-Time Aggregates ====================
-- (MergeTree engines for high-throughput ingestion)

CREATE TABLE IF NOT EXISTS realtime.events_per_minute (
    window_start    DateTime,
    window_end      DateTime,
    event_type      String,
    event_count     UInt64,
    updated_at      DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (window_start, event_type);

-- Removed: realtime.logins_per_source (replaced by revenue_per_minute)

CREATE TABLE IF NOT EXISTS realtime.purchases_per_minute (
    window_start    DateTime,
    window_end      DateTime,
    purchase_count  UInt64,
    updated_at      DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY window_start;

-- NEW: Real-time Revenue Stream (replaces logins_per_source)
CREATE TABLE IF NOT EXISTS realtime.revenue_per_minute (
    window_start    DateTime,
    window_end      DateTime,
    revenue         Float64,
    purchase_count  UInt64,
    updated_at      DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY window_start;

-- NEW: Category Velocity (purchases per category per minute)
CREATE TABLE IF NOT EXISTS realtime.category_velocity (
    window_start    DateTime,
    window_end      DateTime,
    category        String,
    purchase_count  UInt64,
    revenue         Float64,
    updated_at      DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (window_start, category);

-- ==================== Gold Tables (Batch Aggregates) ====================
-- (ReplacingMergeTree to handle upserts/updates)

CREATE TABLE IF NOT EXISTS gold.daily_active_users (
    event_date      Date,
    dau_count       UInt64,
    updated_at      DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY event_date;

CREATE TABLE IF NOT EXISTS gold.events_per_source_daily (
    event_date      Date,
    source          String,
    event_count     UInt64,
    updated_at      DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (event_date, source);

-- Kept for backward compatibility, but less relevant for e-commerce
CREATE TABLE IF NOT EXISTS gold.purchases_per_page_daily (
    event_date      Date,
    page            String,
    purchase_count  UInt64,
    updated_at      DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (event_date, page);

-- UPDATED: Conversion Rate (unique buyers / DAU, not total_purchases / total_events)
DROP TABLE IF EXISTS gold.conversion_rate_daily;
CREATE TABLE IF NOT EXISTS gold.conversion_rate_daily (
    event_date          Date,
    dau_count           UInt64,
    unique_buyers       UInt64,
    conversion_rate     Float64,
    updated_at          DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY event_date;

-- NEW: Daily Revenue Metrics
CREATE TABLE IF NOT EXISTS gold.revenue_daily (
    event_date          Date,
    total_revenue       Float64,
    total_purchases     UInt64,
    avg_order_value     Float64,
    updated_at          DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY event_date;

-- NEW: Category Sales (units and revenue per category)
CREATE TABLE IF NOT EXISTS gold.category_sales_daily (
    event_date          Date,
    category            String,
    units_sold          UInt64,
    category_revenue    Float64,
    updated_at          DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (event_date, category);

-- NEW: Cart Abandonment Rate
CREATE TABLE IF NOT EXISTS gold.cart_abandonment_daily (
    event_date          Date,
    sessions_with_cart  UInt64,
    abandoned_carts     UInt64,
    abandonment_rate    Float64,
    updated_at          DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY event_date;

-- ==================== Anomaly Detection Tables ====================

-- Real-time Anomalies (detected by Spark streaming)
CREATE TABLE IF NOT EXISTS realtime.anomalies (
    window_start        DateTime,
    anomaly_type        String,  -- 'revenue_drop', 'traffic_spike', 'traffic_drop', 'cart_abandonment_spike', 'conversion_drop', 'data_quality', 'category_imbalance'
    severity            String,  -- 'critical', 'high', 'medium', 'low'
    description         String,  -- Human-readable description
    metric_value        String,  -- Current value
    expected_value      String,  -- Expected/baseline value
    detected_at         DateTime DEFAULT now(),
    acknowledged        UInt8 DEFAULT 0,
    acknowledged_at     Nullable(DateTime),
    acknowledged_by     Nullable(String)
) ENGINE = MergeTree()
ORDER BY (detected_at, severity, anomaly_type);

-- Anomaly Baselines (statistical baselines for anomaly detection)
CREATE TABLE IF NOT EXISTS realtime.anomaly_baselines (
    metric_name         String,
    window_size         String,  -- '5min', '1hour', '1day'
    avg_value           Float64,
    stddev_value        Float64,
    min_value           Float64,
    max_value           Float64,
    percentile_95       Float64,
    sample_count        UInt64,
    updated_at          DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (metric_name, window_size);

-- Anomaly Summary (for dashboard KPIs)
CREATE MATERIALIZED VIEW IF NOT EXISTS realtime.anomaly_summary
ENGINE = SummingMergeTree()
ORDER BY (anomaly_date, severity, anomaly_type)
AS
SELECT
    toDate(detected_at) as anomaly_date,
    severity,
    anomaly_type,
    count(*) as anomaly_count
FROM realtime.anomalies
GROUP BY anomaly_date, severity, anomaly_type;
