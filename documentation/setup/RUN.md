# Running the Lakehouse Platform

## Prerequisites
- Docker Desktop installed and running
- At least 6GB RAM allocated to Docker
- Ports available: 3000 (Grafana), 8123 (ClickHouse), 8082 (Airflow), 9092 (Kafka)

## Quick Start

### 1. Start All Services
```bash
cd <your-project-directory>
docker compose up -d
```

### 2. Verify Services Are Running
```bash
docker compose ps
```

All services should show `Up` or `Up (healthy)` status.

### 3. Wait for Initialization
- **Airflow:** ~1-2 minutes for database setup
- **Kafka:** ~30 seconds for topic creation
- **Grafana:** ~20 seconds to be accessible

### 4. Access the Platform

**Grafana Dashboard:**
```
URL: http://localhost:3000
Login: admin / admin
```

**Airflow UI:**
```
URL: http://localhost:8082
Login: admin / admin
```

**ClickHouse Database (HTTP):**
```
URL: http://localhost:8123
User: default
Password: (none)
```

## First-Time Setup

### Enable Airflow DAG
1. Go to http://localhost:8082
2. Login with admin/admin
3. Find `lakehouse_batch_dag` DAG
4. Toggle it **ON** (switch on the left)
5. Click **Trigger DAG** to run manually

### Verify Data Pipeline
```bash
# Check real-time streaming data (ClickHouse)
docker compose exec clickhouse clickhouse-client --query \
  "SELECT count(*) FROM realtime.events_per_minute"

# Check batch data (after Airflow DAG runs)
docker compose exec clickhouse clickhouse-client --query \
  "SELECT * FROM gold.daily_active_users"
```

### View Grafana Dashboard
1. Open http://localhost:3000
2. Login with admin/admin
3. Dashboard loads automatically
4. Wait 5-10 minutes for charts to populate with streaming data

## Monitoring

### View Service Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f producer
docker compose logs -f spark-fast-agg
docker compose logs -f airflow-scheduler
```

### Check Data Volumes
```bash
# Lakehouse data size
docker exec spark-raw-landing sh -c "du -sh /data/lakehouse/*"

# Expected output:
# 100-500M  /data/lakehouse/bronze (raw events)
# 5-10M     /data/lakehouse/silver (cleaned)
# 5-10M     /data/lakehouse/gold (aggregated)
```

## Stopping the Platform

### Stop Services (Keep Data)
```bash
docker compose down
```

### Stop and Remove All Data (Clean Slate)
```bash
docker compose down -v
```

### Restart Services
```bash
docker compose restart
```

### Rebuild After Code Changes
```bash
docker compose up -d --build
```

## Timeline to See Results

| Time | What You'll See |
|------|-----------------|
| **0-1 min** | Services starting up |
| **1-2 min** | Grafana accessible, top KPIs visible |
| **2-5 min** | Real-time charts start showing data |
| **5-10 min** | Meaningful trends with multiple data points |
| **After Airflow run** | All Gold metrics fully populated |

## Troubleshooting

If services fail to start, see [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

For component details, see [../architecture/COMPONENT_GUIDE.md](../architecture/COMPONENT_GUIDE.md)

For example queries, see [../queries/EXAMPLE_QUERIES.md](../queries/EXAMPLE_QUERIES.md)
