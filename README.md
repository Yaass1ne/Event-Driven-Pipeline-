# Lakehouse Streaming Data Platform

> End-to-end Lambda Architecture with real-time streaming and batch processing — fully Dockerized, runs locally on 6GB RAM.

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Apache Kafka](https://img.shields.io/badge/Kafka-231F20?style=flat-square&logo=apache-kafka&logoColor=white)
![Apache Spark](https://img.shields.io/badge/Spark_3.5-E25A1C?style=flat-square&logo=apache-spark&logoColor=white)
![Airflow](https://img.shields.io/badge/Airflow-017CEE?style=flat-square&logo=apache-airflow&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?style=flat-square&logo=grafana&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)

**Pipeline:** `Producer → Kafka → Spark Streaming → Delta Lake → Airflow → PostgreSQL → Grafana`

### Key specs
- Event throughput: 5 events/sec (configurable to 100+)
- End-to-end latency: < 60 seconds
- Bronze/Silver/Gold Delta Lake architecture (ACID-compliant)
- Memory-optimized: ~5.3GB total across 9 containers

---
---

## 🎯 Quick Start

### Prerequisites
- Docker Desktop with **8GB RAM** allocated
- Docker Compose v2
- ~15 GB disk space
- Groq API key (free at https://console.groq.com)

### Start the Platform
```bash
cd <your-project-directory>
docker compose up -d
```

**Wait 2-3 minutes** for all services to initialize.

### Access Services

| Service | URL | Credentials | Purpose |
|---------|-----|-------------|---------|
| **🤖 AI Chatbot** | http://localhost:5000 | - | Query data & modify dashboards |
| **📊 Grafana** | http://localhost:3000 | admin / admin | Real-time dashboards |
| **⚙️ Airflow** | http://localhost:8082 | admin / admin | Batch orchestration |
| **💾 ClickHouse** | localhost:8123 (HTTP) | default / - | Analytics database |

---

## ✨ Key Features

### 🤖 AI-Powered Chatbot (NEW!)
**Natural language interface** to query data and modify Grafana dashboards:

**Data Queries:**
- "What was revenue yesterday?"
- "Show conversion rate"
- "Top 5 categories by sales"

**Dashboard Modifications:**
- "Change all charts to show last 7 days"
- "Add a pie chart for cart abandonment"
- "Rename revenue panel to Daily Revenue"
- "Change conversion chart to bar chart"

👉 **[Full Chatbot Guide](documentation/CHATBOT.md)**

### 🚨 Real-Time Anomaly Detection (NEW!)
**Intelligent monitoring** with Slack alerts:
- Traffic spikes/drops (>2x or <0.5x baseline)
- Revenue anomalies (>2x or <0.5x expected)
- Conversion rate drops (below 1%)
- Zero purchase alerts

👉 **[Anomaly Detection Setup](documentation/ANOMALY_DETECTION_DEPLOYMENT.md)**

### 🛒 E-Commerce Analytics (NEW!)
**Realistic e-commerce metrics** with 1,000 users:
- **Revenue tracking**: Daily revenue, AOV, total purchases
- **Category analysis**: 8 product categories with sales trends
- **Cart abandonment**: Session tracking with abandonment rates
- **Conversion rate**: Unique buyers / DAU (realistic 2-5%)
- **Session management**: 30-minute timeout, cart persistence

### ⚡ Real-Time Layer (Speed)
- **Kafka** streaming 5 events/sec from 1,000 users
- **Spark Streaming** processing every 30 seconds
- **ClickHouse** minute-by-minute aggregations
- **Grafana** auto-refresh every 10 seconds

### 📊 Batch Layer (Accuracy)
- **Delta Lake** Bronze/Silver/Gold architecture (ACID)
- **Airflow** hourly batch transformations
- **ClickHouse** serving business KPIs
- **Grafana** historical analytics

---

## 📊 Business Metrics

### Real-Time Metrics
- **Events per minute** by type (login, view, add_to_cart, purchase, logout)
- **Revenue per minute** with purchase count
- **Category velocity** (real-time sales by category)

### Daily KPIs (Gold Layer)
- **Daily Active Users (DAU)** - Unique users per day
- **Revenue Daily** - Total revenue, purchases, average order value
- **Conversion Rate** - Unique buyers / DAU
- **Category Sales** - Units sold and revenue by category
- **Cart Abandonment** - Sessions with cart vs. completed purchases
- **Events by Source** - Mobile vs. Web distribution

---

## 🏗️ Architecture Overview

```
Producer (1000 users) → Kafka (user-events topic)
                              │
              ┌───────────────┴─────────────────┬──────────────────┐
              │                                 │                  │
              ▼                                 ▼                  ▼
    Spark Raw Landing              Spark Fast Aggregation   Spark Anomaly
    (Bronze ingestion)             (Real-time metrics)      (Alerts)
              │                                 │                  │
              ▼                                 ▼                  ▼
      Delta Bronze                    ClickHouse realtime.*   Slack Webhook
              │
              ▼
         Airflow DAG
         (Hourly)
              │
              ├─► Delta Silver (cleaned, validated)
              │
              └─► Delta Gold (business KPIs)
                      │
                      ▼
              ClickHouse gold.*
                      │
                      ├──────────────┐
                      ▼              ▼
                  Grafana      AI Chatbot
                (Dashboards)   (NL queries +
                               Dashboard mods)
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Events** | Python Producer | E-commerce event simulation |
| **Streaming** | Apache Kafka 7.5.3 | Message broker |
| **Processing** | Apache Spark 3.5.1 | Stream & batch processing |
| **Storage** | Delta Lake 3.1.0 | ACID data lake |
| **Orchestration** | Apache Airflow 2.8.1 | Batch scheduling |
| **Analytics DB** | ClickHouse 23.8 | OLAP serving layer |
| **Visualization** | Grafana 10.2.0 | Dashboards |
| **AI/ML** | Groq (LLaMA 3.3 70B) | Chatbot NL→SQL |
| **Alerts** | Slack Webhooks | Anomaly notifications |
| **Metadata** | MySQL 8.0 | Airflow backend |

---

## 🚀 Getting Started

### 1. Clone and Configure

```bash
cd "EventDriven Click"
```

**Set Groq API Key** (for chatbot):
```bash
# In docker-compose.yml, update GROQ_API_KEY in chatbot service
# Get free API key at: https://console.groq.com
```

**Optional - Slack Alerts**:
```bash
# In docker-compose.yml, update SLACK_WEBHOOK_URL in spark-anomaly-detector
# See: documentation/SLACK_SETUP.md
```

### 2. Start Services

```bash
docker compose up -d
```

Monitor startup:
```bash
docker compose logs -f producer | head -20
```

### 3. Verify Data Flow

**Check real-time data (after 2 minutes):**
```bash
curl -s "http://localhost:8123" --data "SELECT count(*) FROM realtime.events_per_minute"
```

**Check producer stats:**
```bash
docker compose logs producer --tail 5 | grep "Sent"
```

### 4. Trigger Batch Pipeline

**Via Airflow UI:**
1. Open http://localhost:8082 (admin/admin)
2. Enable `lakehouse_batch_pipeline` DAG
3. Click **Trigger DAG**

**Or via command:**
```bash
docker compose exec spark-raw-landing spark-submit \
  --master local[2] --driver-memory 512m \
  --packages io.delta:delta-spark_2.12:3.1.0 \
  /opt/spark-jobs/spark_bronze_to_silver.py
```

### 5. Explore with Chatbot

1. Open http://localhost:5000
2. Try: **"What was revenue yesterday?"**
3. Try: **"Change all charts to show last 7 days"**
4. Try: **"Add a pie chart for cart abandonment"**

---

## 📚 Documentation

### Quick Guides
- **[🤖 Chatbot Guide](documentation/CHATBOT.md)** - How to use the AI chatbot
- **[🚀 Quick Start](documentation/setup/RUN.md)** - Detailed startup guide
- **[🔧 Troubleshooting](documentation/setup/TROUBLESHOOTING.md)** - Common issues

### Architecture & Design
- **[🏗️ System Architecture](documentation/architecture/ARCHITECTURE.md)** - Design decisions
- **[📦 Component Guide](documentation/architecture/COMPONENT_GUIDE.md)** - Service details
- **[🔄 Data Pipeline](documentation/architecture/DATA_PIPELINE.md)** - Data flow

### Advanced Features
- **[🚨 Anomaly Detection](documentation/ANOMALY_DETECTION_DEPLOYMENT.md)** - Alert setup
- **[💬 Slack Integration](documentation/SLACK_SETUP.md)** - Webhook configuration
- **[📊 Example Queries](documentation/queries/EXAMPLE_QUERIES.md)** - SQL examples

---

## 🎨 AI Chatbot Examples

### Data Queries
```
User: "What was revenue yesterday?"
Bot: Yesterday's revenue was $15,234.56 from 287 purchases, with an average order value of $53.08.
```

### Dashboard Modifications
```
User: "Change all charts to show last 7 days"
Bot: ✅ Changed time range for all panels to 7d
     🔗 View updated dashboard: http://grafana:3000/d/lakehouse-overview
```

### Adding New Visualizations
```
User: "Add a pie chart for cart abandonment"
Bot: ✅ Added new piechart panel: 'Cart Abandonment'
     🔗 View updated dashboard: http://grafana:3000/d/lakehouse-overview
```

---

## 📊 Sample Dashboard Panels

1. **Daily Active Users** - Stat panel showing unique users
2. **Conversion Rate** - Percentage of users who purchase
3. **Total Revenue Today** - Dollar amount with sparkline
4. **Total Events** - Event count across all types
5. **Real-Time Event Stream** - Time series by event type
6. **Revenue Per Minute** - Real-time revenue tracking
7. **Revenue by Category** - Pie chart (8 categories)
8. **Top Categories** - Bar chart by units sold

---

## 🔍 Data Validation

### Check Gold Layer Metrics

**Conversion Rate (should be 2-5%):**
```bash
curl -s "http://localhost:8123" --data "
SELECT
    event_date,
    dau_count,
    unique_buyers,
    round(conversion_rate * 100, 2) as conv_pct
FROM gold.conversion_rate_daily
ORDER BY event_date DESC
LIMIT 1 FORMAT Vertical"
```

**Revenue Breakdown:**
```bash
curl -s "http://localhost:8123" --data "
SELECT
    total_revenue,
    total_purchases,
    round(avg_order_value, 2) as aov
FROM gold.revenue_daily
ORDER BY event_date DESC
LIMIT 1 FORMAT Vertical"
```

**Category Performance:**
```bash
curl -s "http://localhost:8123" --data "
SELECT
    category,
    units_sold,
    round(category_revenue, 2) as revenue
FROM gold.category_sales_daily
WHERE event_date = today()
ORDER BY units_sold DESC
FORMAT Pretty"
```

---

## 🎯 Configuration

### Environment Variables

**Producer Configuration:**
```yaml
EVENTS_PER_SECOND: "5"        # Event generation rate
NUM_USERS: "1000"             # User pool size
USER_GROWTH_RATE: "10"        # New users per hour
```

**Anomaly Detector:**
```yaml
SLACK_WEBHOOK_URL: "your-webhook-url"  # Slack alerts
```

**Chatbot:**
```yaml
GROQ_API_KEY: "your-groq-api-key"      # LLaMA 3.3 70B access
GRAFANA_URL: "http://grafana:3000"
GRAFANA_USER: "admin"
GRAFANA_PASSWORD: "admin"
```

---

## 🔧 Operational Commands

### Service Management

**View all services:**
```bash
docker compose ps
```

**Restart specific service:**
```bash
docker compose restart producer
docker compose restart chatbot
```

**View logs:**
```bash
docker compose logs -f <service-name>
docker compose logs -f producer | grep "Events"
```

**Clear data and restart:**
```bash
docker compose down -v
docker compose up -d
```

### Data Management

**Check lakehouse size:**
```bash
docker exec spark-raw-landing du -sh /data/lakehouse/*
```

**Clear ClickHouse tables:**
```bash
docker compose exec clickhouse clickhouse-client --multiquery <<'SQL'
TRUNCATE TABLE gold.revenue_daily;
TRUNCATE TABLE gold.conversion_rate_daily;
SQL
```

---

## 📈 Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Event throughput** | 5 events/sec | Configurable up to 100+ |
| **End-to-end latency** | < 10 seconds | Kafka → ClickHouse |
| **Batch processing** | 3-5 minutes | Bronze → Silver → Gold |
| **Memory usage** | ~8 GB total | With all services |
| **Storage growth** | ~300KB/min | Bronze layer |
| **User pool** | 1,000 users | Growing at 10/hour |
| **Conversion rate** | 2-5% | Realistic e-commerce |

---

## 🆘 Troubleshooting

### Common Issues

**1. Chatbot buttons not working**
```bash
# Clear browser cache and refresh
# Or restart chatbot
docker compose restart chatbot
```

**2. Conversion rate still 99%**
```bash
# Producer needs rebuild, not just restart
docker compose stop producer
docker compose build producer
docker compose up -d producer
```

**3. No data in Grafana**
```bash
# Wait 5-10 minutes for data accumulation
# Or trigger Airflow DAG manually
```

**4. Docker Desktop connectivity issues**
```bash
# Restart Docker Desktop application
# Then: docker compose up -d --build
```

**5. Out of memory errors**
```bash
# Increase Docker Desktop RAM to 8GB
# Settings → Resources → Memory
```

👉 **Full troubleshooting guide:** [TROUBLESHOOTING.md](documentation/setup/TROUBLESHOOTING.md)

---

## 🎓 Learn More

### Tutorials & Guides
- **Lambda Architecture** - Combining Speed and Batch layers
- **Delta Lake ACID** - Time travel and UPSERT operations
- **ClickHouse OLAP** - Columnar storage and aggregations
- **Spark Structured Streaming** - Micro-batch processing
- **Grafana Provisioning** - Dashboard as code

### Example Workflows
1. **Add new KPI**: Silver → Gold transform → ClickHouse table → Grafana panel
2. **Custom alert**: Modify anomaly thresholds in `spark_anomaly_detector.py`
3. **New visualization**: Use chatbot to add panel, then customize in Grafana

---

## 📁 Project Structure

```
├── README.md                           # This file
├── docker-compose.yml                  # Service orchestration
├── documentation/                      # All guides
│   ├── CHATBOT.md                     # AI chatbot usage guide
│   ├── ANOMALY_DETECTION_DEPLOYMENT.md
│   ├── SLACK_SETUP.md
│   ├── setup/
│   ├── architecture/
│   └── queries/
├── producer/                           # E-commerce event generator
│   ├── producer.py                    # 1000 users, 8 categories
│   ├── Dockerfile
│   └── requirements.txt
├── spark/                              # Streaming & batch jobs
│   ├── Dockerfile
│   └── jobs/
│       ├── spark_raw_landing.py       # Bronze ingestion
│       ├── spark_fast_agg.py          # Real-time metrics
│       ├── spark_anomaly_detector.py  # Alert monitoring
│       ├── spark_bronze_to_silver.py  # Data cleaning
│       └── spark_silver_to_gold.py    # Business KPIs
├── airflow/                            # Batch orchestration
│   ├── Dockerfile
│   └── dags/
│       └── lakehouse_batch_dag.py     # Hourly pipeline
├── chatbot/                            # AI-powered assistant
│   ├── app.py                         # Flask app + Groq API
│   ├── requirements.txt
│   └── Dockerfile
├── grafana/                            # Dashboards
│   └── provisioning/
│       ├── datasources/
│       └── dashboards/
│           └── lakehouse-overview.json
└── sql/
    ├── clickhouse_init.sql             # Schema + tables
    └── mysql_init.sql                  # Airflow backend
```

---

## 🎯 Use Cases & Demonstrations

This platform demonstrates:

✅ **Real-time streaming** with Kafka and Spark
✅ **Lambda Architecture** (Speed + Batch layers)
✅ **Lakehouse pattern** (Bronze/Silver/Gold)
✅ **ACID transactions** with Delta Lake
✅ **Batch orchestration** with Airflow
✅ **OLAP analytics** with ClickHouse
✅ **Real-time dashboards** with Grafana
✅ **AI-powered insights** with LLaMA 3.3 70B
✅ **Anomaly detection** with automated alerts
✅ **Natural language** dashboard management
✅ **E-commerce analytics** at scale (1000 users)

---

## 🤝 Contributing

To extend the platform:

1. **Add new event types**: Update `producer/producer.py`
2. **Create new KPIs**: Add transforms in `spark_silver_to_gold.py`
3. **Custom dashboards**: Add JSON in `grafana/provisioning/dashboards/`
4. **New alerts**: Extend `spark_anomaly_detector.py`
5. **Chatbot features**: Modify `chatbot/app.py`

---

## 📄 License

MIT License - Feel free to use for learning and commercial projects.

---

## 🌟 Highlights

- **Production-ready architecture** following industry best practices
- **Fully containerized** - one command to start everything
- **Memory optimized** - runs on standard development machines
- **Realistic data** - simulates actual e-commerce behavior
- **AI-enhanced** - natural language interface to your data
- **Self-documenting** - comprehensive guides and examples
- **Extensible** - easy to add new metrics and features

---

**Built with ❤️ for the data engineering community**

Questions? Check [TROUBLESHOOTING.md](documentation/setup/TROUBLESHOOTING.md) or review service logs.
