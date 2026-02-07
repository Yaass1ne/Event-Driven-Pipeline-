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

# PostgreSQL JDBC driver
RUN mkdir -p /opt/spark/extra-jars && \
    curl -fSL https://jdbc.postgresql.org/download/postgresql-42.7.1.jar \
         -o /opt/spark/extra-jars/postgresql-42.7.1.jar

ENV SPARK_HOME=/opt/spark
ENV PATH="${SPARK_HOME}/bin:${PATH}"

USER airflow

RUN pip install --no-cache-dir \
    apache-airflow-providers-apache-spark==4.7.1 \
    delta-spark==3.1.0 \
    psycopg2-binary==2.9.9

COPY dags/ /opt/airflow/dags/
