# Lakehouse Streaming Data Platform

A complete end-to-end lakehouse platform implementing the Lambda Architecture pattern with real-time streaming and batch processing.

**Producer → Kafka → Spark Streaming → Delta Lake → Airflow → PostgreSQL → Grafana**

---

## 🎯 Quick Start

### Prerequisites
- Docker Desktop with **6GB RAM** allocated
- Docker Compose v2
- ~10 GB disk space

### Start the Platform
```bash
cd <your-project-directory>
docker compose up -d
```

**Wait 1-2 minutes** for all services to initialize.

### Access Dashboards

**Grafana (Real-Time Dashboards):**
```
URL: http://localhost:3000
Login: admin / admin
```

**Airflow (Batch Orchestration):**
```
URL: http://localhost:8082
Login: admin / admin
```

---

## 📊 Features

### Real-Time Layer (Speed)
- **Kafka** streaming user events (5/sec, growing user base)
- **Spark Streaming** processing events every 30 seconds
- **PostgreSQL** real-time aggregations (minute-by-minute)
- **Grafana** dashboards auto-refreshing every 10 seconds

### Batch Layer (Accuracy)
- **Delta Lake** Bronze/Silver/Gold architecture (ACID-compliant)
- **Airflow** orchestrating daily transformations
- **PostgreSQL** serving business KPIs
- **Grafana** historical analytics panels

### What's Monitored
- Daily Active Users (DAU)
- Conversion Rate (purchase %)
- Events by source (Mobile vs Web)
- Top pages by purchases
- Real-time event streams
- Login activity by source

---

## 📚 Documentation

### Setup & Running
- **[Quick Start Guide](documentation/setup/RUN.md)** - How to run the project
- **[Troubleshooting](documentation/setup/TROUBLESHOOTING.md)** - Common issues and fixes

### Architecture
- **[System Architecture](documentation/architecture/ARCHITECTURE.md)** - Design decisions and data flow
- **[Component Guide](documentation/architecture/COMPONENT_GUIDE.md)** - Detailed explanation of each component

### Usage
- **[Example Queries](documentation/queries/EXAMPLE_QUERIES.md)** - SQL queries for data exploration

---

## 🏗️ Architecture Overview

```
Producer (Events) → Kafka (user-events)
                        │
        ┌───────────────┴────────────────┐
        │                                │
        ▼                                ▼
Spark Raw Landing              Spark Fast Aggregation
        │                                │
        ▼                                ▼
Delta Bronze                  PostgreSQL (realtime.*)
        │
        ▼
    Airflow DAG
        │
        ├─► Delta Silver (cleaned)
        │
        └─► Delta Gold (aggregated)
                │
                ▼
        PostgreSQL (gold.*)
                │
                ▼
            Grafana
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Message Broker** | Apache Kafka 7.5.3 |
| **Stream Processing** | Apache Spark 3.5.1 |
| **Data Lake** | Delta Lake 3.1.0 |
| **Batch Orchestration** | Apache Airflow 2.8.1 |
| **Serving Database** | PostgreSQL 15 |
| **Visualization** | Grafana 10.2.0 |
| **Orchestration** | Docker Compose |

---

## 📋 Service Ports

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / admin |
| Airflow | http://localhost:8082 | admin / admin |
| PostgreSQL | localhost:5432 | platform / platform123 |
| Kafka | localhost:29092 | - |

---

## 🔍 Verify Installation

### Check All Services
```bash
docker compose ps
```
All services should show `Up` or `Up (healthy)`.

### Query Real-Time Data
```bash
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT COUNT(*) FROM realtime.events_per_minute;"
```

### Check Lakehouse Size
```bash
docker exec spark-raw-landing sh -c "du -sh /data/lakehouse/*"
```
Expected: Bronze 100-500MB, Silver 5-10MB, Gold 5-10MB

---

## 🚦 First-Time Setup

### 1. Enable Airflow DAG
1. Go to http://localhost:8082
2. Toggle **ON** the `lakehouse_bronze_to_gold` DAG
3. Click **Trigger DAG** to run manually

### 2. Wait for Data
- **Real-time charts:** 5-10 minutes to populate
- **Batch metrics:** After first Airflow DAG run (2-3 min)

---

## 🛑 Stop/Restart

**Stop services (keep data):**
```bash
docker compose down
```

**Stop and remove all data:**
```bash
docker compose down -v
```

**Restart a specific service:**
```bash
docker compose restart <service-name>
```

**Rebuild after code changes:**
```bash
docker compose up -d --build
```

---

## 🎓 Learn More

- **Architecture deep-dive:** [ARCHITECTURE.md](documentation/architecture/ARCHITECTURE.md)
- **Component details:** [COMPONENT_GUIDE.md](documentation/architecture/COMPONENT_GUIDE.md)
- **Example queries:** [EXAMPLE_QUERIES.md](documentation/queries/EXAMPLE_QUERIES.md)
- **Troubleshooting:** [TROUBLESHOOTING.md](documentation/setup/TROUBLESHOOTING.md)

---

## 📊 Performance Characteristics

- **Event throughput:** 5 events/sec (configurable up to 100+)
- **End-to-end latency:** < 60 seconds (Kafka → PostgreSQL)
- **Batch processing:** 2-3 minutes for daily aggregations
- **Memory usage:** ~5-6 GB total (optimized for laptops)
- **Storage growth:** ~200KB/min Bronze, ~100KB/day Gold

---

## 🔧 Memory Optimization

This platform is **memory-optimized** for development environments:
- Spark runs in `local[2]` mode (saves ~2GB vs cluster mode)
- All containers have memory limits
- JVM heap sizes tuned per service
- Total memory: ~5.3GB across 9 containers

**Memory breakdown:**
- ZooKeeper: 256M, Kafka: 512M, PostgreSQL: 192M
- Spark jobs: 896M each (2 × 896M = 1.8GB)
- Airflow: 384M webserver + 1280M scheduler
- Producer: 48M, Grafana: 256M

---

## 📁 Project Structure

```
├── docker-compose.yml              # Service orchestration
├── README.md                       # This file
├── documentation/                  # All documentation
│   ├── setup/
│   │   ├── RUN.md                 # Quick start guide
│   │   └── TROUBLESHOOTING.md     # Common issues
│   ├── architecture/
│   │   ├── ARCHITECTURE.md        # System design
│   │   └── COMPONENT_GUIDE.md     # Component details
│   └── queries/
│       └── EXAMPLE_QUERIES.md     # SQL examples
├── producer/                       # Event generator
│   ├── producer.py
│   └── requirements.txt
├── spark/                          # Streaming & batch jobs
│   ├── Dockerfile
│   └── jobs/
│       ├── spark_raw_landing.py
│       ├── spark_fast_agg.py
│       ├── spark_bronze_to_silver.py
│       └── spark_silver_to_gold.py
├── airflow/                        # Batch orchestration
│   ├── Dockerfile
│   └── dags/
│       └── lakehouse_batch_dag.py
├── grafana/                        # Dashboards
│   └── provisioning/
│       ├── datasources/
│       └── dashboards/
└── sql/
    └── init.sql                    # PostgreSQL schema
```

---

## 🎯 Use Cases

This platform demonstrates:
- ✅ Real-time event streaming with Kafka
- ✅ Lakehouse architecture (Bronze/Silver/Gold)
- ✅ Lambda Architecture (Speed + Batch layers)
- ✅ ACID transactions with Delta Lake
- ✅ Batch orchestration with Airflow
- ✅ Real-time dashboards with Grafana
- ✅ Growing user base simulation
- ✅ Multi-source analytics (Mobile vs Web)

---

## 🆘 Need Help?

1. Check [TROUBLESHOOTING.md](documentation/setup/TROUBLESHOOTING.md)
2. Review service logs: `docker compose logs <service-name>`
3. Verify all services are healthy: `docker compose ps`
4. Full restart: `docker compose down && docker compose up -d`
