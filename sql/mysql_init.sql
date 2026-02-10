-- Initialize MySQL for Airflow metadata
CREATE DATABASE IF NOT EXISTS serving;
CREATE USER IF NOT EXISTS 'platform'@'%' IDENTIFIED BY 'platform123';
GRANT ALL PRIVILEGES ON serving.* TO 'platform'@'%';
FLUSH PRIVILEGES;
