FROM apache/spark:3.5.1

USER root

# Install curl for downloading jars
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# PostgreSQL JDBC driver for fast-agg writes
RUN mkdir -p /opt/spark/extra-jars && \
    curl -fSL https://jdbc.postgresql.org/download/postgresql-42.7.1.jar \
         -o /opt/spark/extra-jars/postgresql-42.7.1.jar

# Pre-download ivy dependencies so spark-submit doesn't download at runtime
RUN /opt/spark/bin/spark-shell \
    --packages io.delta:delta-spark_2.12:3.1.0,org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
    --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
    --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
    -e "println(\"Dependencies cached\")" || true

# Create directories writable by spark user
RUN mkdir -p /data/lakehouse /data/checkpoints /opt/spark-jobs && \
    chown -R spark:spark /data /opt/spark-jobs

USER spark
