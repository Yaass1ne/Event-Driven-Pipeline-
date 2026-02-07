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
**Cause:** PostgreSQL not populated yet or Grafana can't connect
**Solution:**
```bash
# 1. Check PostgreSQL is running
docker compose ps postgres

# 2. Verify data exists
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT COUNT(*) FROM realtime.events_per_minute;"

# 3. Check Grafana logs
docker compose logs grafana

# 4. Restart Grafana
docker compose restart grafana
```

#### Conversion Rate Panel Shows Error
**Cause:** PostgreSQL ROUND() function type mismatch (should be fixed in latest version)
**Solution:**
```bash
# Update dashboard to latest version
docker compose restart grafana
```

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

---

### Streaming Job Issues

#### Spark Streaming Job Crashes
**Symptoms:** spark-fast-agg or spark-raw-landing shows "Exited (1)"
**Solution:**
```bash
# Check logs for errors
docker compose logs spark-fast-agg
docker compose logs spark-raw-landing

# Common issue: ClassCastException
# Fix: Already handled with local[2] mode

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

#### Events Not Reaching PostgreSQL
**Symptoms:** Kafka has data, but PostgreSQL tables empty
**Solution:**
```bash
# Check Spark fast-agg logs
docker compose logs spark-fast-agg | tail -50

# Verify PostgreSQL connection
docker compose exec postgres psql -U platform -d serving -c "\dt realtime.*"

# Restart streaming job
docker compose restart spark-fast-agg
```

---

### Database Issues

#### Can't Connect to PostgreSQL
**Cause:** Port blocked, service not healthy, or wrong credentials
**Solution:**
```bash
# Check PostgreSQL status
docker compose ps postgres

# Check PostgreSQL logs
docker compose logs postgres

# Test connection
docker compose exec postgres psql -U platform -d serving -c "SELECT 1;"

# Verify port mapping
docker compose port postgres 5432
```

#### Tables Missing
**Cause:** Initialization script didn't run
**Solution:**
```bash
# Check if init script ran
docker compose logs postgres | grep "init.sql"

# Manually run init script
docker compose exec postgres psql -U platform -d serving -f /docker-entrypoint-initdb.d/01-init.sql

# Or recreate database
docker compose down -v
docker compose up -d postgres
```

#### Query Performance Slow
**Cause:** Large data accumulation
**Solution:**
```bash
# Check table sizes
docker compose exec postgres psql -U platform -d serving -c \
  "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
   FROM pg_tables
   WHERE schemaname IN ('realtime', 'gold')
   ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"

# Archive old data if needed (manual cleanup)
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

---

## Getting Help

1. **Check logs first:**
   ```bash
   docker compose logs <service-name> | tail -100
   ```

2. **Verify service health:**
   ```bash
   docker compose ps
   ```

3. **Check resource usage:**
   ```bash
   docker stats
   ```

4. **Full restart:**
   ```bash
   docker compose down
   docker compose up -d
   ```

5. **Nuclear option (clean slate):**
   ```bash
   docker compose down -v
   docker compose up -d --build
   ```
