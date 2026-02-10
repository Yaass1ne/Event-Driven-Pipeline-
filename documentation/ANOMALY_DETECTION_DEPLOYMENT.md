# 🚨 Anomaly Detection System - Full Deployment Guide

## Overview

Your e-commerce analytics platform now has **production-ready anomaly detection** that monitors your entire data pipeline in real-time and alerts you to issues BEFORE they impact customers.

---

## What Was Implemented

### ✅ **1. Spark Anomaly Detector** (`spark/jobs/spark_anomaly_detector.py`)

**Detects 7 Types of Anomalies**:

| Anomaly Type | What It Detects | Severity Levels | Alert Threshold |
|--------------|-----------------|-----------------|-----------------|
| 💰 **Revenue Drop** | Sudden decrease in purchase revenue | Critical: >50% drop<br>High: >40% drop<br>Medium: >30% drop | 30% drop from baseline |
| 📈 **Traffic Spike** | Unusual increase in events | Critical: >5σ<br>High: >4σ<br>Medium: >3σ | 3 standard deviations |
| 📉 **Traffic Drop** | Sudden decrease in events | Critical: <-5σ<br>High: <-4σ<br>Medium: <-3σ | 3 standard deviations |
| 🛒 **Cart Abandonment Spike** | High cart abandonment rate | Critical: >90%<br>High: >80%<br>Medium: >70% | 2.5σ above mean + >70% |
| 📊 **Conversion Drop** | Low purchase conversion | Critical: <1%<br>High: <2%<br>Medium: <3% | <3% conversion rate |
| ⚠️ **Data Quality Issue** | Missing prices/categories | Critical: >50%<br>High: >25%<br>Medium: >10% | >10% missing price |
| ⚖️ **Category Imbalance** | One category dominates | Low only | >60% of sales |

**How It Works**:
- Monitors Kafka stream in real-time
- Computes metrics per 5-minute window
- Calculates rolling baseline (last 12 windows = 1 hour)
- Uses Z-score and percentage change detection
- Writes anomalies to ClickHouse
- Sends Slack alerts for critical/high severity

---

### ✅ **2. ClickHouse Schema** (`sql/clickhouse_init.sql`)

**3 New Tables**:

#### **realtime.anomalies**
Stores all detected anomalies with details:
```sql
- window_start (DateTime) - When anomaly occurred
- anomaly_type (String) - Type of anomaly
- severity (String) - critical/high/medium/low
- description (String) - Human-readable explanation
- metric_value (String) - Current value
- expected_value (String) - Baseline/expected value
- detected_at (DateTime) - Detection timestamp
- acknowledged (UInt8) - 0=active, 1=acknowledged
- acknowledged_at (DateTime) - When acked
- acknowledged_by (String) - Who acked
```

#### **realtime.anomaly_baselines**
Stores statistical baselines for metrics (future use):
```sql
- metric_name (String)
- window_size (String) - 5min/1hour/1day
- avg_value, stddev_value, min_value, max_value
- percentile_95, sample_count
```

#### **realtime.anomaly_summary** (Materialized View)
Pre-aggregated counts for fast dashboard queries:
```sql
- anomaly_date (Date)
- severity (String)
- anomaly_type (String)
- anomaly_count (UInt64)
```

---

### ✅ **3. Grafana Anomaly Dashboard** (`grafana/dashboards/anomaly-monitoring.json`)

**New Dashboard**: "🚨 Anomaly Detection & Alerts"

**6 Panels**:

1. **Active Alerts (Last Hour)** - Stat panel showing unacknowledged alerts
2. **Critical Alerts (24h)** - Count of critical-severity alerts
3. **Alerts by Severity (24h)** - Pie chart breakdown
4. **Alerts by Type (24h)** - Donut chart showing anomaly types
5. **Recent Alerts (Last 6 Hours)** - Table with full details
   - Color-coded severity
   - Emoji icons by type
   - Current vs expected values
   - Acknowledgment status
6. **Anomaly Timeline (24h)** - Stacked bar chart over time

**Auto-Refresh**: 30 seconds
**Access**: http://localhost:3000/d/anomaly-monitoring

---

### ✅ **4. Slack Integration** (Optional)

**Rich Alert Messages** with:
- Color-coded by severity
- Emoji by anomaly type
- Current vs expected metrics
- Action buttons (View Dashboard, Acknowledge)

**Example Alert**:
```
💰 Revenue Drop Detected!
─────────────────────────
Severity:     🔴 CRITICAL
Time:         2026-02-10 14:35:22
Current:      $245
Expected:     $1,850

Details:
Revenue dropped by 87% from baseline ($1,850 → $245).
Possible payment system failure!

[View Dashboard] [Acknowledge]
```

---

### ✅ **5. Docker Compose Service**

New service: `spark-anomaly-detector`
- Memory: 1024M
- Restart: on-failure
- Depends on: Kafka, ClickHouse
- Environment: Inherits Spark config + SLACK_WEBHOOK_URL

---

## 🚀 Deployment Steps

### **Step 1: (Optional) Set Up Slack Webhook**

If you want Slack alerts:

1. **Create Slack Incoming Webhook**:
   - Go to: https://api.slack.com/apps
   - Create new app → From scratch
   - Enable "Incoming Webhooks"
   - Add webhook to workspace → Select channel (e.g., `#alerts`)
   - Copy webhook URL

2. **Add to .env file**:
   ```bash
   # Create .env file in project root
   echo 'SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL' > .env
   ```

3. **Test webhook**:
   ```bash
   curl -X POST $SLACK_WEBHOOK_URL \
     -H 'Content-Type: application/json' \
     -d '{"text":"🚨 Test Alert - Anomaly Detection System Online!"}'
   ```

See `documentation/SLACK_SETUP.md` for detailed instructions.

**Skip if you don't want Slack alerts** - anomalies will still be stored in ClickHouse and visible in Grafana.

---

### **Step 2: Deploy Updated System**

```bash
# Navigate to project directory
cd "C:\Users\Yassine\Desktop\EventDriven Click"

# Stop all services
docker-compose down

# CRITICAL: Wipe volumes (required for ClickHouse schema changes)
docker-compose down -v

# Rebuild Spark image (includes new anomaly detector)
docker-compose build spark-raw-landing

# Start all services
docker-compose up -d

# Monitor startup (wait ~2 minutes)
docker-compose ps
```

Expected services running:
```
spark-anomaly-detector   ✓ Up
spark-raw-landing        ✓ Up
spark-fast-agg           ✓ Up
producer                 ✓ Up
clickhouse               ✓ Up (healthy)
kafka                    ✓ Up (healthy)
grafana                  ✓ Up
airflow-scheduler        ✓ Up
airflow-webserver        ✓ Up
mysql                    ✓ Up
```

---

### **Step 3: Verify Anomaly Detector is Running**

```bash
# Check anomaly detector logs
docker-compose logs spark-anomaly-detector

# Should see:
# 🚨 Anomaly Detection System Started
#    Monitoring: revenue, traffic, cart abandonment, conversion, data quality
#    Window: 5 minutes, Check interval: 30 seconds
#    Alerts: ClickHouse + Slack (webhook: configured/not configured)
```

---

### **Step 4: Generate Test Data & Wait for Anomalies**

The system needs **15-30 minutes** of data to establish baselines and detect anomalies.

```bash
# Monitor producer (generating e-commerce events)
docker-compose logs -f producer | grep "Sent"

# Wait for ~20 minutes of data collection...
```

---

### **Step 5: Check for Anomalies in ClickHouse**

```bash
# View all detected anomalies
docker-compose exec clickhouse clickhouse-client --query \
  "SELECT
     formatDateTime(detected_at, '%H:%M:%S') as time,
     severity,
     anomaly_type,
     description
   FROM realtime.anomalies
   ORDER BY detected_at DESC
   LIMIT 10
   FORMAT Vertical"
```

**Expected Output** (after 20+ minutes):
```
Row 1:
──────
time:         14:45:08
severity:     high
anomaly_type: cart_abandonment_spike
description:  Cart abandonment SPIKE: 78% (expected ~45%). Possible checkout bug or payment issue. 52 carts added, only 11 purchases.

Row 2:
──────
time:         14:40:15
severity:     medium
anomaly_type: traffic_drop
description:  Traffic DROP: 287 events (expected ~450). Possible system issue or producer failure.
```

**If no anomalies yet**: This is GOOD! It means your system is healthy. The anomaly detector is working and monitoring silently.

---

### **Step 6: View Grafana Anomaly Dashboard**

1. **Open Grafana**: http://localhost:3000
2. **Login**: admin / admin
3. **Navigate**: Home → Dashboards → "🚨 Anomaly Detection & Alerts"

You should see:
- **Active Alerts**: 0 or more
- **Critical Alerts**: 0 (hopefully!)
- **Alerts by Severity**: Pie chart (if any anomalies detected)
- **Recent Alerts**: Table showing latest anomalies with emoji icons

**Auto-refreshes every 30 seconds**

---

### **Step 7: (Optional) Force an Anomaly for Testing**

To test the system, simulate anomalies:

#### **Test 1: Traffic Drop (Easy)**
```bash
# Stop producer temporarily
docker-compose stop producer

# Wait 10 minutes for anomaly detection
# Should trigger "traffic_drop" alert

# Restart producer
docker-compose start producer
```

#### **Test 2: Revenue Drop (Medium)**
```bash
# Modify producer to set price to 0
docker-compose exec -it producer bash
# Edit producer.py to temporarily set all prices to 0
# Wait 10 minutes
# Should trigger "revenue_drop" CRITICAL alert
```

#### **Test 3: Data Quality Issue (Easy)**
```bash
# Modify producer to skip price field
# Wait 10 minutes
# Should trigger "data_quality" alert
```

---

## 📊 Understanding Anomaly Detection

### **How Baselines Work**

The system uses **rolling baselines**:
- Last 12 windows = 1 hour of data
- Calculates: Mean, Standard Deviation, Min, Max
- Updates continuously as new data arrives

**Example**:
```
Current Window: 2:35 PM
Baseline: Data from 1:35 PM - 2:30 PM (last 12 × 5-minute windows)

If current revenue ($245) is 87% below baseline avg ($1,850)
→ Trigger "revenue_drop" CRITICAL alert
```

### **Detection Methods**

1. **Z-Score Detection** (Traffic anomalies):
   - Measures how many standard deviations from mean
   - Z-score > 3 or < -3 → Anomaly

2. **Percentage Change** (Revenue anomalies):
   - Compares current value to baseline
   - Drop > 30% → Anomaly

3. **Threshold Detection** (Conversion rate):
   - Absolute threshold
   - < 3% conversion → Anomaly

4. **Combination** (Cart abandonment):
   - Z-score > 2.5 AND rate > 70% → Anomaly

---

## 🔧 Customization

### **Adjust Detection Sensitivity**

Edit `spark/jobs/spark_anomaly_detector.py`:

```python
# Line 57-64: Adjust thresholds
THRESHOLDS = {
    "revenue_drop_pct": 0.30,      # 30% → Change to 0.20 for 20% (more sensitive)
    "traffic_zscore": 3.0,          # 3σ → Change to 2.5 (more sensitive)
    "abandonment_zscore": 2.5,      # 2.5σ
    "conversion_min": 0.03,         # 3% → Change to 0.05 for 5%
    "category_dominance": 0.60,     # 60% → Change to 0.70 for 70%
    "missing_price_pct": 0.10,      # 10% → Change to 0.05 for 5% (stricter)
}
```

**After changing**, rebuild and restart:
```bash
docker-compose build spark-raw-landing
docker-compose restart spark-anomaly-detector
```

---

### **Adjust Severity Levels**

Edit `spark/jobs/spark_anomaly_detector.py`:

```python
# Example: Revenue drop severity (Line 182-186)
.withColumn(
    "severity",
    when(col("revenue_pct_change") < -0.50, lit(SEVERITY_CRITICAL))  # ← -50%
    .when(col("revenue_pct_change") < -0.40, lit(SEVERITY_HIGH))     # ← -40%
    .otherwise(lit(SEVERITY_MEDIUM))
)

# Change to be more/less aggressive:
when(col("revenue_pct_change") < -0.70, lit(SEVERITY_CRITICAL))  # Only critical at -70%
```

---

### **Add New Anomaly Types**

Add custom detection logic:

```python
def detect_session_duration_anomalies(metrics_df):
    """Detect abnormally short/long session durations."""

    # Add session duration calculation
    # Detect anomalies
    # Return anomaly DataFrame

    return anomalies

# In main():
session_anomalies = detect_session_duration_anomalies(metrics_df)

all_anomalies = (
    revenue_anomalies
    .union(traffic_anomalies)
    .union(session_anomalies)  # ← Add new type
    # ... other unions
)
```

---

## 📈 Monitoring & Operations

### **Daily Health Check**

```bash
# Check anomaly detector is running
docker-compose ps spark-anomaly-detector

# View recent anomalies
docker-compose exec clickhouse clickhouse-client --query \
  "SELECT count(*) as total, severity FROM realtime.anomalies \
   WHERE detected_at >= today() GROUP BY severity"

# Check Slack alerts (if configured)
# → Open Slack channel, should see alerts
```

---

### **Weekly Review**

```bash
# Anomaly summary by type (last 7 days)
docker-compose exec clickhouse clickhouse-client --query \
  "SELECT
     anomaly_type,
     count(*) as total,
     countIf(severity = 'critical') as critical,
     countIf(severity = 'high') as high
   FROM realtime.anomalies
   WHERE detected_at >= today() - 7
   GROUP BY anomaly_type
   ORDER BY total DESC"

# Most common anomalies
# → Investigate root causes
```

---

### **Troubleshooting**

#### **Problem: No anomalies detected after 30 minutes**

**Possible Causes**:
1. System is healthy (GOOD!)
2. Thresholds too strict
3. Not enough data for baseline

**Solution**:
```bash
# Check data is flowing
docker-compose exec clickhouse clickhouse-client --query \
  "SELECT count(*) FROM realtime.revenue_per_minute \
   WHERE window_start >= now() - INTERVAL 1 HOUR"

# Should return >10 rows
# If 0, check producer and Spark streaming jobs
```

#### **Problem: Too many false positives**

**Solution**:
- Increase thresholds (less sensitive)
- Increase baseline window (more stable)
- Add minimum traffic filters

#### **Problem: Slack alerts not appearing**

**Solution**:
```bash
# Check webhook URL is configured
docker-compose exec spark-anomaly-detector bash -c 'echo $SLACK_WEBHOOK_URL'

# Check Spark logs for Slack errors
docker-compose logs spark-anomaly-detector | grep -i slack

# Test webhook manually
curl -X POST $SLACK_WEBHOOK_URL -H 'Content-Type: application/json' \
  -d '{"text":"Test from terminal"}'
```

---

## 🎯 Success Metrics

After 24 hours of operation, you should see:

✅ **Anomaly Detector Status**: Running continuously
✅ **Anomalies Detected**: 5-20 per day (depending on system stability)
✅ **False Positive Rate**: <10% (most alerts are actionable)
✅ **Alert Response Time**: <5 minutes (Slack → Investigation)
✅ **Grafana Dashboard**: Loading in <2 seconds
✅ **ClickHouse Storage**: <100MB for anomaly data

---

## 📚 Additional Resources

- **Slack Setup**: `documentation/SLACK_SETUP.md`
- **AI Integration Plan**: `documentation/AI_INTEGRATION_PLAN.md`
- **ClickHouse Schema**: `sql/clickhouse_init.sql`
- **Anomaly Detector Code**: `spark/jobs/spark_anomaly_detector.py`

---

## 🚀 What's Next?

### **Phase 2 Enhancements** (Future):

1. **Machine Learning Models**:
   - Replace Z-score with LSTM Autoencoder
   - Use Isolation Forest for multivariate detection
   - Prophet for time series forecasting

2. **Alert Acknowledgment System**:
   - Web UI to acknowledge alerts
   - Track who acknowledged and when
   - Alert escalation (if not acked in 30 mins)

3. **Anomaly Prediction**:
   - Predict anomalies before they happen
   - Preventive maintenance alerts

4. **Root Cause Analysis**:
   - Automatically suggest likely causes
   - Link to related logs and metrics

5. **Alert Deduplication**:
   - Don't spam same alert repeatedly
   - Group related anomalies

---

## 🎉 Congratulations!

You now have a **production-grade anomaly detection system** monitoring your e-commerce platform 24/7!

**What you get**:
- 🔍 Real-time monitoring of 7 anomaly types
- 📊 Beautiful Grafana dashboard
- 💬 Slack alerts for critical issues
- 📈 Historical anomaly tracking
- ⚙️ Fully customizable thresholds

**Your platform will now alert you to**:
- Payment system failures (revenue drops)
- Bot attacks (traffic spikes)
- Checkout bugs (cart abandonment)
- Data pipeline issues (quality alerts)
- Traffic drops (producer failures)

🚨 **Sleep better knowing your system is being monitored!** 🚨
