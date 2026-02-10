# Slack Integration Setup Guide

## Overview

The anomaly detection system sends real-time alerts to Slack when critical or high-severity anomalies are detected.

## Step 1: Create Slack Incoming Webhook

1. **Go to Slack API**: https://api.slack.com/apps
2. **Click "Create New App"** → "From scratch"
3. **App Name**: "E-Commerce Anomaly Alerts"
4. **Workspace**: Select your workspace
5. **Click "Create App"**

6. **Enable Incoming Webhooks**:
   - In the left sidebar, click "Incoming Webhooks"
   - Toggle "Activate Incoming Webhooks" to **ON**
   - Click "Add New Webhook to Workspace"
   - Select the channel (e.g., `#alerts` or `#data-monitoring`)
   - Click "Allow"

7. **Copy Webhook URL**:
   - You'll see a URL like: `https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX`
   - **Copy this URL** - you'll need it in Step 2

## Step 2: Configure Environment Variable

Add the Slack webhook to your `.env` file:

```bash
# Create .env file in project root
cat > .env << 'EOF'
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
EOF
```

Then update `docker-compose.yml` to load this environment variable:

```yaml
  spark-anomaly-detector:
    <<: *spark-common
    container_name: spark-anomaly-detector
    environment:
      SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      # ... other env vars
```

## Step 3: Test Slack Integration

Send a test alert:

```bash
curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "🚨 Test Alert from E-Commerce Platform",
    "attachments": [
      {
        "color": "#FF0000",
        "text": "This is a test alert. If you see this, Slack integration is working! ✅"
      }
    ]
  }'
```

You should see a message in your Slack channel.

## Alert Examples

### Revenue Drop Alert (Critical)
```
💰 Revenue Drop Detected!
─────────────────────────
Severity:     CRITICAL
Time:         2026-02-10 14:35:22
Current:      $245
Expected:     $1,850

Details:
Revenue dropped by 87% from baseline ($1,850 → $245)
Possible payment system failure!

[View Dashboard] [Acknowledge]
```

### Traffic Spike Alert (High)
```
📈 Traffic Spike Detected!
─────────────────────────
Severity:     HIGH
Time:         2026-02-10 14:40:15
Current:      5,430 events
Expected:     1,200 events

Details:
Traffic SPIKE: 5,430 events (expected ~1,200).
Z-score: 4.85. Possible bot attack or viral event.

[View Dashboard] [Acknowledge]
```

### Cart Abandonment Spike Alert (High)
```
🛒 Cart Abandonment Spike Detected!
─────────────────────────────────
Severity:     HIGH
Time:         2026-02-10 14:45:08
Current:      92%
Expected:     45%

Details:
Cart abandonment SPIKE: 92% (expected ~45%).
Possible checkout bug or payment issue.
145 carts added, only 12 purchases.

[View Dashboard] [Acknowledge]
```

### Data Quality Issue Alert (Medium)
```
⚠️ Data Quality Detected!
─────────────────────────
Severity:     MEDIUM
Time:         2026-02-10 14:50:33
Current:      18 purchases
Expected:     0

Details:
DATA QUALITY ISSUE: 25% of purchases missing price
(18/72 purchases). Check producer or data pipeline.

[View Dashboard] [Acknowledge]
```

## Alert Severity Levels

| Severity | Color | When to Alert | Action Required |
|----------|-------|---------------|-----------------|
| 🔴 **CRITICAL** | Red | Revenue drop >50%, Traffic drop >80%, Data loss | **Immediate action** - wake on-call engineer |
| 🟠 **HIGH** | Orange | Revenue drop >30%, Traffic anomaly >4σ, Abandonment >80% | **Urgent** - investigate within 15 mins |
| 🟡 **MEDIUM** | Yellow | Data quality issues, Conversion <3%, Abandonment >70% | **Important** - investigate within 1 hour |
| 🔵 **LOW** | Blue | Category imbalance, Minor metrics drift | **FYI** - review during business hours |

## Slack Channel Recommendations

### Option A: Single Alerts Channel
```
#data-alerts
  └── All anomaly alerts (filtered by severity in app)
```

### Option B: Multi-Channel Strategy (Recommended)
```
#critical-alerts     ← CRITICAL only (PagerDuty integration)
#data-monitoring     ← HIGH + MEDIUM alerts
#data-insights       ← LOW alerts + daily summaries
```

## Alert Deduplication

The system automatically deduplicates alerts:
- Same anomaly type within 15-minute window → Only first alert sent
- Prevents alert fatigue from persistent issues
- Acknowledgment system (future feature)

## Customizing Alerts

Edit `spark/jobs/spark_anomaly_detector.py`:

```python
# Adjust thresholds
THRESHOLDS = {
    "revenue_drop_pct": 0.30,      # 30% drop → adjust to 0.20 for 20%
    "traffic_zscore": 3.0,          # 3σ → adjust to 2.5 for more sensitive
    "abandonment_zscore": 2.5,      # 2.5σ
    "conversion_min": 0.03,         # 3% min → adjust to 0.05 for 5%
}

# Adjust severity levels
def detect_revenue_anomalies(metrics_df):
    .withColumn(
        "severity",
        when(col("revenue_pct_change") < -0.50, lit(SEVERITY_CRITICAL))  # ← Change -0.50 to -0.40
        .when(col("revenue_pct_change") < -0.40, lit(SEVERITY_HIGH))
        .otherwise(lit(SEVERITY_MEDIUM))
    )
```

## Advanced: Alert Routing

Route different anomaly types to different channels:

```python
# In spark_anomaly_detector.py
SLACK_WEBHOOKS = {
    "critical": os.getenv("SLACK_WEBHOOK_CRITICAL"),
    "revenue": os.getenv("SLACK_WEBHOOK_REVENUE"),
    "technical": os.getenv("SLACK_WEBHOOK_TECHNICAL"),
}

def send_slack_alert(anomaly_type, severity, details, metric_value, expected_value):
    # Route by type
    if severity == SEVERITY_CRITICAL:
        webhook = SLACK_WEBHOOKS["critical"]
    elif anomaly_type in ["revenue_drop", "conversion_drop"]:
        webhook = SLACK_WEBHOOKS["revenue"]
    else:
        webhook = SLACK_WEBHOOKS["technical"]

    # Send to appropriate channel
    requests.post(webhook, json=message)
```

## Troubleshooting

### Alerts not appearing in Slack?

1. **Check webhook URL**:
   ```bash
   echo $SLACK_WEBHOOK_URL
   # Should print: https://hooks.slack.com/services/...
   ```

2. **Check Spark logs**:
   ```bash
   docker-compose logs spark-anomaly-detector | grep -i slack
   ```

3. **Test webhook manually**:
   ```bash
   curl -X POST $SLACK_WEBHOOK_URL \
     -H 'Content-Type: application/json' \
     -d '{"text":"Test from terminal"}'
   ```

4. **Verify anomalies are being detected**:
   ```bash
   docker-compose exec clickhouse clickhouse-client --query \
     "SELECT * FROM realtime.anomalies ORDER BY detected_at DESC LIMIT 5"
   ```

### Too many alerts?

1. **Increase thresholds** (less sensitive)
2. **Add minimum traffic filter** (only alert with sufficient data)
3. **Implement alert deduplication** (already built-in for 15-min window)
4. **Adjust severity levels** (fewer CRITICAL/HIGH alerts)

### Want email instead of Slack?

Replace Slack webhook with SMTP email:

```python
import smtplib
from email.mime.text import MIMEText

def send_email_alert(to_email, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = os.getenv("ALERT_EMAIL_FROM")
    msg['To'] = to_email

    with smtplib.SMTP(os.getenv("SMTP_HOST"), 587) as server:
        server.starttls()
        server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        server.send_message(msg)
```

## PagerDuty Integration (Production)

For production systems, integrate with PagerDuty for on-call alerts:

1. **Create PagerDuty Integration**:
   - Service → Integrations → Add Integration → Events API v2
   - Copy integration key

2. **Send to PagerDuty**:
```python
def send_pagerduty_alert(anomaly_type, severity, details):
    if severity != SEVERITY_CRITICAL:
        return  # Only critical to PagerDuty

    payload = {
        "routing_key": os.getenv("PAGERDUTY_INTEGRATION_KEY"),
        "event_action": "trigger",
        "payload": {
            "summary": f"{anomaly_type}: {details}",
            "severity": "critical",
            "source": "e-commerce-platform",
            "custom_details": {
                "metric_value": metric_value,
                "expected_value": expected_value
            }
        }
    }

    requests.post(
        "https://events.pagerduty.com/v2/enqueue",
        json=payload
    )
```

---

## Quick Start

```bash
# 1. Get Slack webhook URL (see Step 1)
# 2. Add to .env file
echo 'SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL' >> .env

# 3. Restart services
docker-compose down
docker-compose up -d

# 4. Verify alerts are working
docker-compose logs -f spark-anomaly-detector

# 5. Check Slack channel - you should see alerts within 5-10 minutes
```

Done! 🎉 You'll now receive real-time alerts for any anomalies in your e-commerce platform.
