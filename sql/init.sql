-- ============================================================
-- PostgreSQL initialization: real-time serving store tables
-- Also used by Airflow as metadata DB (shared database)
-- ============================================================

-- Schema for real-time aggregates
CREATE SCHEMA IF NOT EXISTS realtime;

-- Events per minute (tumbling window)
-- No PK: streaming job uses truncate+overwrite per micro-batch
CREATE TABLE IF NOT EXISTS realtime.events_per_minute (
    window_start    TIMESTAMP NOT NULL,
    window_end      TIMESTAMP NOT NULL,
    event_type      VARCHAR(50) NOT NULL,
    event_count     BIGINT NOT NULL,
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Logins per source per minute
CREATE TABLE IF NOT EXISTS realtime.logins_per_source (
    window_start    TIMESTAMP NOT NULL,
    window_end      TIMESTAMP NOT NULL,
    source          VARCHAR(20) NOT NULL,
    login_count     BIGINT NOT NULL,
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Purchases per minute
CREATE TABLE IF NOT EXISTS realtime.purchases_per_minute (
    window_start    TIMESTAMP NOT NULL,
    window_end      TIMESTAMP NOT NULL,
    purchase_count  BIGINT NOT NULL,
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Indexes for dashboard queries
CREATE INDEX IF NOT EXISTS idx_epm_window ON realtime.events_per_minute (window_start DESC);
CREATE INDEX IF NOT EXISTS idx_lps_window ON realtime.logins_per_source (window_start DESC);
CREATE INDEX IF NOT EXISTS idx_ppm_window ON realtime.purchases_per_minute (window_start DESC);

-- Schema for Gold layer outputs (historical dashboards)
CREATE SCHEMA IF NOT EXISTS gold;

-- DAU (daily active users) - populated by batch job
CREATE TABLE IF NOT EXISTS gold.daily_active_users (
    event_date      DATE PRIMARY KEY,
    dau_count       BIGINT NOT NULL,
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Events per source per day
CREATE TABLE IF NOT EXISTS gold.events_per_source_daily (
    event_date      DATE NOT NULL,
    source          VARCHAR(20) NOT NULL,
    event_count     BIGINT NOT NULL,
    updated_at      TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (event_date, source)
);

-- Purchases per page per day
CREATE TABLE IF NOT EXISTS gold.purchases_per_page_daily (
    event_date      DATE NOT NULL,
    page            VARCHAR(255) NOT NULL,
    purchase_count  BIGINT NOT NULL,
    updated_at      TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (event_date, page)
);

-- Conversion rate per day (purchases / total events)
CREATE TABLE IF NOT EXISTS gold.conversion_rate_daily (
    event_date          DATE PRIMARY KEY,
    total_events        BIGINT NOT NULL,
    total_purchases     BIGINT NOT NULL,
    conversion_rate     DOUBLE PRECISION NOT NULL,
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dau_date ON gold.daily_active_users (event_date DESC);
CREATE INDEX IF NOT EXISTS idx_eps_date ON gold.events_per_source_daily (event_date DESC);
CREATE INDEX IF NOT EXISTS idx_ppp_date ON gold.purchases_per_page_daily (event_date DESC);
CREATE INDEX IF NOT EXISTS idx_cr_date ON gold.conversion_rate_daily (event_date DESC);

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA realtime TO platform;
GRANT ALL PRIVILEGES ON SCHEMA gold TO platform;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA realtime TO platform;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA gold TO platform;
