FROM apache/airflow:2.8.1-python3.11

USER root

# Install Java (needed for spark-submit)
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-17-jre-headless curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

# Install Spark client (for spark-submit)
RUN curl -fSL https://archive.apache.org/dist/spark/spark-3.5.1/spark-3.5.1-bin-hadoop3.tgz \
    | tar -xz -C /opt/ && \
    ln -s /opt/spark-3.5.1-bin-hadoop3 /opt/spark

# MySQL and ClickHouse drivers
RUN mkdir -p /opt/spark/extra-jars && \
    curl -fSL https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/8.2.0/mysql-connector-j-8.2.0.jar \
         -o /opt/spark/extra-jars/mysql-connector-j-8.2.0.jar && \
    curl -fSL https://repo1.maven.org/maven2/com/clickhouse/clickhouse-jdbc/0.6.0/clickhouse-jdbc-0.6.0-all.jar \
         -o /opt/spark/extra-jars/clickhouse-jdbc-0.6.0-all.jar

ENV SPARK_HOME=/opt/spark
ENV PATH="${SPARK_HOME}/bin:${PATH}"

USER airflow

RUN pip install --no-cache-dir \
    apache-airflow-providers-apache-spark==4.7.1 \
    apache-airflow-providers-mysql \
    clickhouse-driver==0.2.6 \
    delta-spark==3.1.0 \
    mysqlclient

COPY dags/ /opt/airflow/dags/
