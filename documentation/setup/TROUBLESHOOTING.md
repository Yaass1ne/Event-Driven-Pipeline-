# Troubleshooting Guide

## Common Issues and Solutions

### Services Won't Start

#### Out of Memory (OOM)
**Symptoms:** Docker Desktop crashes, containers stop randomly
**Solution:**
```bash
# Check Docker Desktop settings
# Increase allocated RAM to at least 6GB

# Stop all services and clean up
docker compose down -v

# Restart Docker Desktop

# Start services
docker compose up -d
```

#### Port Already in Use
**Symptoms:** Error: "port is already allocated"
**Solution:**
```bash
# Find what's using the port (example for port 3000)
# Windows:
netstat -ano | findstr :3000

# Kill the process or change the port in docker-compose.yml
```

#### ZooKeeper Connection Issues
**Symptoms:** Kafka shows "ZooKeeper connection timeout"
**Solution:**
```bash
# Wait for ZooKeeper to fully start (20-30 seconds)
docker compose logs zookeeper

# Restart Kafka
docker compose restart kafka
```

---

### Grafana Dashboard Issues

#### "No Data" on All Panels
**Cause:** ClickHouse not populated yet or Grafana can't connect
**Solution:**
```bash
# 1. Check ClickHouse is running
docker compose ps clickhouse

# 2. Verify data exists
docker compose exec clickhouse clickhouse-client --query \
  "SELECT count(*) FROM realtime.events_per_minute"

# 3. Check Grafana logs
docker compose logs grafana

# 4. Restart Grafana
docker compose restart grafana
```

#### "Bad Request" or "Query Error"
**Cause:** Invalid SQL syntax for ClickHouse (e.g. using PostgreSQL functions like `NOW()` instead of `now()`)
**Solution:**
- Click "Edit" on the panel
- Check the generated SQL
- Ensure it uses ClickHouse syntax (e.g. `toStartOfMinute`, `now()`)

#### Charts Show Old Data
**Cause:** Grafana caching
**Solution:**
1. In Grafana, click the refresh button (top right)
2. Or force refresh: Ctrl+Shift+R (Windows)
3. Or restart Grafana: `docker compose restart grafana`

---

### Airflow Issues

#### DAG Not Appearing
**Cause:** Airflow scheduler not running or DAG file syntax error
**Solution:**
```bash
# Check scheduler logs
docker compose logs airflow-scheduler

# Verify DAG file exists
docker compose exec airflow-webserver ls /opt/airflow/dags/

# Restart scheduler
docker compose restart airflow-scheduler
```

#### "Permission Denied" on Lakehouse
**Cause:** Volume permissions mismatch
**Solution:**
```bash
# Fix permissions on lakehouse directory
docker compose exec spark-raw-landing chmod -R 777 /data/lakehouse/
```

#### Tasks Stuck in "Running"
**Cause:** Spark job hanging or insufficient resources
**Solution:**
```bash
# Check Spark logs
docker compose logs airflow-scheduler | grep -i "spark"

# Kill stuck task in Airflow UI
# Or restart scheduler
docker compose restart airflow-scheduler
```

#### Cannot Delete DAG Run from UI
**Symptoms:** Failed DAG runs that won't delete via Airflow UI, very long-running tasks
**Solution:**
```bash
# 1. List DAG runs to find the run_id
docker exec --user airflow airflow-scheduler airflow dags list-runs -d lakehouse_batch_pipeline --no-backfill

# 2. Delete directly from MySQL database
# Replace <run_id> with the actual run_id (e.g., scheduled__2026-02-10T18:00:00+00:00)
docker exec mysql mysql -uplatform -pplatform123 serving -e \
  "DELETE FROM dag_run WHERE dag_id = 'lakehouse_batch_pipeline' AND run_id = '<run_id>';"

# 3. Verify deletion
docker exec --user airflow airflow-scheduler airflow dags list-runs -d lakehouse_batch_pipeline --no-backfill | grep "<run_id>"
# Should return no results

# Note: Use --user airflow for airflow CLI commands, not root
```

---

### Streaming Job Issues

#### Spark Streaming Job Crashes
**Symptoms:** spark-fast-agg or spark-raw-landing shows "Exited (1)"
**Solution:**
```bash
# Check logs for errors
docker compose logs spark-fast-agg
docker compose logs spark-raw-landing

# Common issue: ClassCastException or JDBC Driver missing
# Fix: Ensure correct jars are in /opt/spark/extra-jars

# Restart the job
docker compose restart spark-fast-agg
```

#### No Events in Kafka
**Symptoms:** Producer running but no data in Kafka
**Solution:**
```bash
# Check producer logs
docker compose logs producer

# Verify Kafka topic exists
docker compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# Check Kafka messages
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic user-events \
  --from-beginning \
  --max-messages 10
```

#### Events Not Reaching ClickHouse
**Symptoms:** Kafka has data, but ClickHouse tables empty
**Solution:**
```bash
# Check Spark fast-agg logs
docker compose logs spark-fast-agg | tail -50

# Verify ClickHouse connection
docker compose exec clickhouse clickhouse-client --query "SHOW DATABASES"

# Restart streaming job
docker compose restart spark-fast-agg
```

---

### ClickHouse Data Quality Issues

#### Duplicate Data in Grafana Charts
**Symptoms:** Grafana charts show duplicate bars/values for the same day, multiple rows for same date in gold tables
**Cause:** Missing `clickhouse-driver` Python module prevents DELETE/OPTIMIZE operations in `spark_silver_to_gold.py`
**Solution:**
```bash
# 1. Install clickhouse-driver in Airflow containers
docker exec --user airflow airflow-scheduler python3 -m pip install --user clickhouse-driver==0.2.6
docker exec --user airflow airflow-webserver python3 -m pip install --user clickhouse-driver==0.2.6

# 2. Verify installation
docker exec --user airflow airflow-scheduler python3 -c "import clickhouse_driver; print('✅ clickhouse_driver version:', clickhouse_driver.__version__)"

# 3. Check for duplicates
docker exec clickhouse clickhouse-client --query \
  "SELECT event_date, category, COUNT(*) as count FROM gold.category_sales_daily GROUP BY event_date, category HAVING COUNT(*) > 1"

# 4. If duplicates exist, clean and re-run
docker exec clickhouse clickhouse-client --query "TRUNCATE TABLE gold.category_sales_daily"
docker exec clickhouse clickhouse-client --query "TRUNCATE TABLE gold.revenue_daily"
docker exec clickhouse clickhouse-client --query "TRUNCATE TABLE gold.conversion_rate_daily"
docker exec clickhouse clickhouse-client --query "TRUNCATE TABLE gold.cart_abandonment_daily"

# 5. Trigger fresh DAG run
docker exec --user airflow airflow-scheduler airflow dags trigger lakehouse_batch_pipeline

# 6. Force Grafana refresh (Ctrl+Shift+R in browser)
```

**Permanent Fix:** Ensure `clickhouse-driver` is in `airflow/Dockerfile` requirements and rebuild:
```bash
docker compose down
docker compose build airflow-scheduler airflow-webserver
docker compose up -d
```

---

### Database Issues

#### Can't Connect to ClickHouse
**Cause:** Port blocked, service not healthy, or wrong credentials
**Solution:**
```bash
# Check ClickHouse status
docker compose ps clickhouse

# Check ClickHouse logs
docker compose logs clickhouse

# Test connection via HTTP
curl 'http://localhost:8123/?query=SELECT%201'
```

#### Tables Missing
**Cause:** Initialization script didn't run
**Solution:**
```bash
# Check if init script ran
docker compose logs clickhouse | grep "init.sql"

# Manually run init script
cat sql/clickhouse_init.sql | docker compose exec -T clickhouse clickhouse-client

# Or recreate database container volume
docker compose down -v
docker compose up -d clickhouse
```

---

### Data Pipeline Issues

#### Bronze Layer Not Growing
**Cause:** Kafka not receiving events or spark-raw-landing not running
**Solution:**
```bash
# 1. Check producer
docker compose logs producer | tail -20

# 2. Check Kafka has messages
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic user-events \
  --from-beginning \
  --max-messages 5

# 3. Check spark-raw-landing
docker compose logs spark-raw-landing | tail -30

# 4. Check Bronze size
docker exec spark-raw-landing sh -c "du -sh /data/lakehouse/bronze"
```

#### Silver/Gold Not Updating
**Cause:** Airflow DAG not running
**Solution:**
```bash
# 1. Check Airflow DAG status
# Go to http://localhost:8082

# 2. Enable DAG if disabled

# 3. Trigger manually

# 4. Check scheduler logs
docker compose logs airflow-scheduler | tail -50
```

---

## Memory Optimization

If running into memory issues, try these optimizations:

### Reduce Spark Memory
Edit `docker-compose.yml`:
```yaml
spark-raw-landing:
  command: [...--driver-memory 384m...]  # Reduce from 512m
  deploy:
    resources:
      limits:
        memory: 768M  # Reduce from 896M
```

### Reduce Airflow Memory
```yaml
airflow-scheduler:
  deploy:
    resources:
      limits:
        memory: 1024M  # Reduce from 1280M
```

### Disable Grafana Auto-Refresh
In Grafana dashboard, set refresh to "Off" in top-right dropdown

---

## Performance Tuning

### Speed Up Data Processing
```yaml
# In docker-compose.yml, increase events per second
producer:
  environment:
    EVENTS_PER_SECOND: "10"  # Increase from 5
```

### Reduce Checkpoint Overhead
```bash
# Clean old checkpoints periodically
docker exec spark-raw-landing sh -c "rm -rf /data/checkpoints/*"
docker compose restart spark-raw-landing spark-fast-agg
```
