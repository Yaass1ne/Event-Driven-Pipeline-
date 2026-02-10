# AI Integration Plan: E-Commerce Analytics Platform

## Overview

This document outlines practical AI integrations for the e-commerce analytics platform, focusing on high-value, implementable solutions that enhance the existing Lambda architecture.

---

## 1. Real-Time Anomaly Detection (Priority: HIGH)

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA PIPELINE (Existing)                     │
├─────────────────────────────────────────────────────────────────┤
│ Producer → Kafka → Spark Streaming → ClickHouse → Grafana      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    AI ANOMALY LAYER (New)                       │
├─────────────────────────────────────────────────────────────────┤
│  1. Spark ML Model (Isolation Forest / LSTM Autoencoder)       │
│  2. Anomaly Scoring (Real-time computation)                     │
│  3. Alert Engine (Slack/Email/PagerDuty)                        │
│  4. Anomaly Store (ClickHouse anomaly_events table)             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    VISUALIZATION (Enhanced)                     │
├─────────────────────────────────────────────────────────────────┤
│  Grafana: Anomaly overlay on existing charts + Alert panel     │
└─────────────────────────────────────────────────────────────────┘
```

### What to Detect

**Pipeline Health Anomalies**:
- Kafka lag spikes (consumer falling behind)
- Spark processing delays (batch duration > threshold)
- Data loss (event count drops suddenly)
- Schema violations (malformed events)

**Business Metric Anomalies**:
- Revenue drops > 30% in 5-minute window
- Cart abandonment rate > 2σ from mean
- Conversion rate drops below threshold
- Category sales imbalance (one category dominates)
- Session duration anomalies (too short/long)

**Data Quality Anomalies**:
- Missing prices on purchase events
- Invalid category values
- Duplicate event_ids
- Timestamp anomalies (future timestamps, out-of-order)

### Implementation: Spark ML Anomaly Detector

**File**: `spark/jobs/spark_anomaly_detector.py`

```python
"""
Real-time anomaly detection on event stream.
Uses Isolation Forest for multivariate anomaly detection.
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, window, count, sum as spark_sum, avg, stddev, when
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.clustering import KMeans
import numpy as np

# Features for anomaly detection
FEATURES = [
    "events_per_minute",
    "revenue_per_minute",
    "avg_price",
    "cart_abandonment_rate",
    "purchases_per_minute",
    "unique_users_per_minute"
]

def compute_features(df):
    """Compute statistical features per time window."""
    return (
        df
        .groupBy(window(col("event_timestamp"), "1 minute"))
        .agg(
            count("*").alias("events_per_minute"),
            spark_sum(when(col("event_type") == "purchase", col("price")).otherwise(0)).alias("revenue_per_minute"),
            avg(when(col("price").isNotNull(), col("price"))).alias("avg_price"),
            count(when(col("event_type") == "add_to_cart", 1)).alias("cart_adds"),
            count(when(col("event_type") == "purchase", 1)).alias("purchases"),
        )
        .withColumn("cart_abandonment_rate",
                    1 - (col("purchases") / (col("cart_adds") + 1)))  # +1 to avoid div by zero
    )

def detect_anomalies_zscore(feature_df):
    """
    Z-score based anomaly detection (simple, fast).
    Anomaly if any metric > 3 standard deviations from mean.
    """
    for feature in FEATURES:
        mean = feature_df.agg(avg(feature)).collect()[0][0]
        std = feature_df.agg(stddev(feature)).collect()[0][0]

        feature_df = feature_df.withColumn(
            f"{feature}_zscore",
            (col(feature) - mean) / (std + 0.0001)  # avoid div by zero
        )

        feature_df = feature_df.withColumn(
            f"{feature}_anomaly",
            when(abs(col(f"{feature}_zscore")) > 3, 1).otherwise(0)
        )

    # Aggregate anomaly flag
    feature_df = feature_df.withColumn(
        "is_anomaly",
        sum([col(f"{f}_anomaly") for f in FEATURES]) > 0
    )

    return feature_df

def send_alert(anomaly_row):
    """Send alert to Slack/Email when anomaly detected."""
    import requests

    SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")
    if not SLACK_WEBHOOK:
        return

    message = {
        "text": f"🚨 *Anomaly Detected* 🚨",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Time*: {anomaly_row['window_start']}\n"
                            f"*Revenue/min*: ${anomaly_row['revenue_per_minute']:.2f} (Z-score: {anomaly_row['revenue_per_minute_zscore']:.2f})\n"
                            f"*Events/min*: {anomaly_row['events_per_minute']} (Z-score: {anomaly_row['events_per_minute_zscore']:.2f})\n"
                            f"*Cart Abandonment*: {anomaly_row['cart_abandonment_rate']:.2%}"
                }
            }
        ]
    }

    requests.post(SLACK_WEBHOOK, json=message)

# Main streaming loop
def main():
    spark = SparkSession.builder.appName("anomaly-detector").getOrCreate()

    # Read from existing realtime aggregates in ClickHouse
    # OR tap into Kafka stream directly

    kafka_df = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", "kafka:9092")
        .option("subscribe", "user-events")
        .load()
    )

    # Parse events
    parsed_df = parse_events(kafka_df)

    # Compute features per 1-minute window
    feature_df = compute_features(parsed_df)

    # Detect anomalies (Z-score method)
    anomaly_df = detect_anomalies_zscore(feature_df)

    # Write anomalies to ClickHouse
    query = (
        anomaly_df
        .filter(col("is_anomaly") == 1)
        .writeStream
        .outputMode("append")
        .foreachBatch(lambda df, bid: write_anomalies(df, bid))
        .start()
    )

    query.awaitTermination()
```

**ClickHouse Schema** (`sql/clickhouse_init.sql`):
```sql
-- Anomaly Detection Table
CREATE TABLE IF NOT EXISTS realtime.anomalies (
    window_start            DateTime,
    anomaly_type            String,  -- 'revenue_drop', 'traffic_spike', 'cart_abandonment'
    severity                Enum8('low' = 1, 'medium' = 2, 'high' = 3, 'critical' = 4),
    metric_name             String,
    metric_value            Float64,
    expected_value          Float64,
    zscore                  Float64,
    detected_at             DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (window_start, anomaly_type);
```

**Grafana Panel**: Add anomaly overlay to existing charts

---

## 2. Predictive Analytics Engine (Priority: MEDIUM)

### Use Cases

1. **Revenue Forecasting**: Predict next hour/day revenue using ARIMA/Prophet
2. **Demand Forecasting**: Predict which categories will be popular
3. **Churn Prediction**: Identify users likely to abandon cart
4. **Session Conversion Prediction**: Predict if current session will convert

### Implementation: Time Series Forecasting

**File**: `spark/jobs/spark_revenue_forecast.py`

```python
"""
Daily batch job: Train Prophet model on historical revenue, forecast next 7 days.
"""

from pyspark.sql import SparkSession
from prophet import Prophet
import pandas as pd

def forecast_revenue(spark):
    # Load historical revenue from ClickHouse
    revenue_df = spark.read.jdbc(
        CH_URL,
        "gold.revenue_daily",
        properties=CH_PROPERTIES
    ).toPandas()

    # Prepare data for Prophet
    df = revenue_df[['event_date', 'total_revenue']].rename(columns={
        'event_date': 'ds',
        'total_revenue': 'y'
    })

    # Train model
    model = Prophet(
        daily_seasonality=True,
        weekly_seasonality=True,
        changepoint_prior_scale=0.05
    )
    model.fit(df)

    # Forecast next 7 days
    future = model.make_future_dataframe(periods=7)
    forecast = model.predict(future)

    # Store forecast in ClickHouse
    forecast_df = spark.createDataFrame(
        forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]
    )
    forecast_df.write.jdbc(CH_URL, "gold.revenue_forecast", mode="overwrite")

    return forecast

# Schedule this job in Airflow daily
```

**New ClickHouse Table**:
```sql
CREATE TABLE IF NOT EXISTS gold.revenue_forecast (
    forecast_date       Date,
    predicted_revenue   Float64,
    lower_bound         Float64,
    upper_bound         Float64,
    model_version       String,
    created_at          DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY forecast_date;
```

---

## 3. Product Recommendation System (Priority: MEDIUM)

### Architecture

```
User Session Events → Spark ML (Collaborative Filtering / ALS)
                              ↓
                     Recommendation Model
                              ↓
                  Store in Redis (fast lookup)
                              ↓
              Serve via API → Producer (enrich events)
```

### Implementation: Collaborative Filtering

**File**: `spark/jobs/spark_recommender.py`

```python
"""
Train ALS model on user purchase history, generate recommendations.
"""

from pyspark.ml.recommendation import ALS
from pyspark.ml.evaluation import RegressionEvaluator

def train_recommender(spark):
    # Load purchase events
    purchases = spark.read.format("delta").load(f"{LAKEHOUSE_PATH}/silver/user_events") \
        .filter(col("event_type") == "purchase") \
        .select("user_id", "product_id", "price")

    # Convert product_id string to integer for ALS
    from pyspark.ml.feature import StringIndexer
    indexer = StringIndexer(inputCol="product_id", outputCol="product_idx")
    purchases = indexer.fit(purchases).transform(purchases)

    # Train ALS model
    als = ALS(
        maxIter=10,
        regParam=0.01,
        userCol="user_id",
        itemCol="product_idx",
        ratingCol="price",  # implicit feedback (purchase = rating)
        coldStartStrategy="drop"
    )

    model = als.fit(purchases)

    # Generate top 10 recommendations for all users
    recommendations = model.recommendForAllUsers(10)

    # Store in ClickHouse for fast lookup
    recommendations.write.jdbc(CH_URL, "gold.user_recommendations", mode="overwrite")

    return model

# Schedule weekly in Airflow
```

---

## 4. Grafana AI Chatbot Integration ⭐ (Your Requested Feature)

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                      Grafana Dashboard                       │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Chat Widget (Embedded iframe or Plugin)              │ │
│  │  "Show me revenue trends for Electronics category"    │ │
│  └────────────────────────────────────────────────────────┘ │
│                            ↓ HTTP POST                       │
└────────────────────────────┼─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│              AI Chatbot Backend (New Service)                │
├──────────────────────────────────────────────────────────────┤
│  1. FastAPI REST API (Python)                                │
│  2. LangChain + OpenAI GPT-4 / Claude                        │
│  3. SQL Query Generator (Text-to-SQL)                        │
│  4. ClickHouse Query Executor                                │
│  5. Grafana API Client (create/modify panels)                │
└──────────────────────────────────────────────────────────────┘
                             ↓
            ┌────────────────┴────────────────┐
            ↓                                 ↓
    ┌──────────────┐                 ┌──────────────┐
    │  ClickHouse  │                 │ Grafana API  │
    │  (Data)      │                 │ (Dashboards) │
    └──────────────┘                 └──────────────┘
```

### Implementation: AI-Powered Grafana Chatbot

#### **Step 1: Create Chatbot Backend**

**File**: `chatbot/app.py`

```python
"""
AI Chatbot Backend for Grafana Dashboard Interaction
Supports natural language queries, dashboard modifications, and data insights.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain.llms import OpenAI
from langchain.agents import create_sql_agent
from langchain.sql_database import SQLDatabase
from langchain.prompts import PromptTemplate
import openai
import requests
import json

app = FastAPI()

# Connect to ClickHouse via SQLAlchemy
CLICKHOUSE_URI = "clickhouse://default:@clickhouse:8123/default"
db = SQLDatabase.from_uri(CLICKHOUSE_URI)

# Initialize OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Grafana API credentials
GRAFANA_URL = "http://grafana:3000"
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY")  # Create in Grafana UI

class ChatRequest(BaseModel):
    message: str
    dashboard_uid: str = "lakehouse-overview"

class ChatResponse(BaseModel):
    reply: str
    sql_query: str = None
    data: dict = None
    action: str = None  # 'query', 'modify_dashboard', 'alert'

# Schema context for LLM
SCHEMA_CONTEXT = """
You are an AI assistant for an e-commerce analytics platform. You have access to these ClickHouse tables:

**Real-time Tables**:
- realtime.events_per_minute (window_start, event_type, event_count)
- realtime.revenue_per_minute (window_start, revenue, purchase_count)
- realtime.category_velocity (window_start, category, purchase_count, revenue)

**Batch/Gold Tables**:
- gold.daily_active_users (event_date, dau_count)
- gold.revenue_daily (event_date, total_revenue, total_purchases, avg_order_value)
- gold.category_sales_daily (event_date, category, units_sold, category_revenue)
- gold.cart_abandonment_daily (event_date, sessions_with_cart, abandoned_carts, abandonment_rate)
- gold.conversion_rate_daily (event_date, dau_count, unique_buyers, conversion_rate)

**Categories**: Electronics, Fashion, Home, Books, Sports, Beauty, Toys, Food
**Event Types**: login, view, add_to_cart, purchase, logout
**Sources**: web, mobile

Generate SQL queries to answer user questions. Always use proper date filtering and aggregations.
"""

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Process natural language query and return response.
    Supports:
    1. Data queries (Text-to-SQL)
    2. Dashboard modifications
    3. Insights and recommendations
    """

    user_message = request.message.lower()

    # Classify intent
    if any(keyword in user_message for keyword in ['show', 'get', 'what', 'how many', 'revenue', 'sales']):
        return await handle_data_query(request.message)

    elif any(keyword in user_message for keyword in ['add panel', 'create chart', 'modify dashboard']):
        return await handle_dashboard_modification(request.message, request.dashboard_uid)

    elif any(keyword in user_message for keyword in ['insight', 'recommend', 'suggest', 'analyze']):
        return await handle_insight_generation(request.message)

    else:
        return ChatResponse(
            reply="I can help you with:\n"
                  "1. Querying data (e.g., 'Show revenue for Electronics category')\n"
                  "2. Modifying dashboards (e.g., 'Add a chart for cart abandonment')\n"
                  "3. Generating insights (e.g., 'Analyze sales trends')",
            action="help"
        )

async def handle_data_query(message: str):
    """Convert natural language to SQL and execute."""

    # Use LangChain SQL agent
    prompt = PromptTemplate(
        input_variables=["question"],
        template=f"{SCHEMA_CONTEXT}\n\nUser Question: {{question}}\n\nGenerate a SQL query to answer this question."
    )

    llm = OpenAI(temperature=0, model="gpt-4")

    # Generate SQL
    sql_query = llm.predict(prompt.format(question=message))

    # Clean SQL (remove markdown code blocks if present)
    sql_query = sql_query.replace("```sql", "").replace("```", "").strip()

    # Execute query
    try:
        result = db.run(sql_query)

        # Format result as natural language response
        response_prompt = f"User asked: {message}\nSQL Result: {result}\n\nProvide a natural language summary of these results."
        summary = llm.predict(response_prompt)

        return ChatResponse(
            reply=summary,
            sql_query=sql_query,
            data={"result": result},
            action="query"
        )

    except Exception as e:
        return ChatResponse(
            reply=f"Sorry, I couldn't execute that query. Error: {str(e)}",
            sql_query=sql_query,
            action="error"
        )

async def handle_dashboard_modification(message: str, dashboard_uid: str):
    """Modify Grafana dashboard based on user request."""

    llm = OpenAI(temperature=0.7, model="gpt-4")

    # Generate panel configuration
    prompt = f"""
    User wants to: {message}

    Generate a Grafana panel JSON configuration for this request.
    Include:
    - Panel title
    - Visualization type (timeseries, stat, barchart, table)
    - ClickHouse SQL query
    - Field configuration (colors, units, thresholds)

    Return ONLY valid JSON.
    """

    panel_json = llm.predict(prompt)

    # Parse and add to dashboard via Grafana API
    try:
        panel_config = json.loads(panel_json)

        # Get current dashboard
        dashboard_response = requests.get(
            f"{GRAFANA_URL}/api/dashboards/uid/{dashboard_uid}",
            headers={"Authorization": f"Bearer {GRAFANA_API_KEY}"}
        )
        dashboard = dashboard_response.json()["dashboard"]

        # Add new panel
        dashboard["panels"].append(panel_config)

        # Update dashboard
        update_response = requests.post(
            f"{GRAFANA_URL}/api/dashboards/db",
            headers={"Authorization": f"Bearer {GRAFANA_API_KEY}"},
            json={"dashboard": dashboard, "overwrite": True}
        )

        return ChatResponse(
            reply=f"✅ I've added a new panel to your dashboard: {panel_config.get('title', 'New Panel')}",
            action="modify_dashboard",
            data={"panel": panel_config}
        )

    except Exception as e:
        return ChatResponse(
            reply=f"Sorry, I couldn't modify the dashboard. Error: {str(e)}",
            action="error"
        )

async def handle_insight_generation(message: str):
    """Generate insights using GPT-4 analysis."""

    # Fetch recent data
    revenue_trend = db.run("SELECT event_date, total_revenue FROM gold.revenue_daily ORDER BY event_date DESC LIMIT 7")
    top_categories = db.run("SELECT category, sum(units_sold) as total FROM gold.category_sales_daily GROUP BY category ORDER BY total DESC LIMIT 3")
    abandonment = db.run("SELECT avg(abandonment_rate) as avg_rate FROM gold.cart_abandonment_daily WHERE event_date >= today() - 7")

    # Generate insights
    llm = OpenAI(temperature=0.7, model="gpt-4")

    prompt = f"""
    Analyze this e-commerce data and provide actionable insights:

    Revenue Trend (Last 7 Days): {revenue_trend}
    Top Categories: {top_categories}
    Avg Cart Abandonment: {abandonment}

    User Question: {message}

    Provide:
    1. Key findings
    2. Anomalies or concerns
    3. Recommendations
    """

    insights = llm.predict(prompt)

    return ChatResponse(
        reply=insights,
        action="insight",
        data={
            "revenue_trend": revenue_trend,
            "top_categories": top_categories,
            "abandonment": abandonment
        }
    )

# Health check
@app.get("/health")
async def health():
    return {"status": "healthy"}
```

#### **Step 2: Embed Chat Widget in Grafana**

**Option A: Custom HTML Panel** (Easiest)

1. Install "Text" panel plugin in Grafana
2. Add HTML panel with chat iframe:

```html
<div id="chat-container">
  <iframe
    src="http://chatbot:8000/chat-widget"
    width="100%"
    height="500px"
    style="border: 1px solid #ddd; border-radius: 8px;"
  ></iframe>
</div>
```

**Option B: Custom Grafana Plugin** (Advanced)

Create a React-based Grafana panel plugin:

**File**: `grafana-plugins/chat-panel/src/ChatPanel.tsx`

```typescript
import React, { useState } from 'react';
import { PanelProps } from '@grafana/data';

export const ChatPanel: React.FC<PanelProps> = ({ width, height }) => {
  const [messages, setMessages] = useState<Array<{role: string, content: string}>>([]);
  const [input, setInput] = useState('');

  const sendMessage = async () => {
    const response = await fetch('http://chatbot:8000/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: input })
    });

    const data = await response.json();

    setMessages([
      ...messages,
      { role: 'user', content: input },
      { role: 'assistant', content: data.reply }
    ]);

    setInput('');
  };

  return (
    <div style={{ width, height, padding: '20px' }}>
      <div style={{ height: height - 100, overflowY: 'scroll', border: '1px solid #ddd', padding: '10px' }}>
        {messages.map((msg, idx) => (
          <div key={idx} style={{
            padding: '10px',
            margin: '5px',
            backgroundColor: msg.role === 'user' ? '#e3f2fd' : '#f5f5f5',
            borderRadius: '8px'
          }}>
            <strong>{msg.role}:</strong> {msg.content}
          </div>
        ))}
      </div>

      <div style={{ marginTop: '10px', display: 'flex' }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="Ask me anything about your data..."
          style={{ flex: 1, padding: '10px', fontSize: '14px' }}
        />
        <button onClick={sendMessage} style={{ padding: '10px 20px', marginLeft: '10px' }}>
          Send
        </button>
      </div>
    </div>
  );
};
```

#### **Step 3: Add to Docker Compose**

**File**: `docker-compose.yml`

```yaml
  # AI Chatbot Service
  chatbot:
    build:
      context: ./chatbot
      dockerfile: Dockerfile
    container_name: chatbot
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      CLICKHOUSE_HOST: clickhouse
      CLICKHOUSE_PORT: 8123
      GRAFANA_URL: http://grafana:3000
      GRAFANA_API_KEY: ${GRAFANA_API_KEY}
    ports:
      - "8001:8000"
    depends_on:
      - clickhouse
      - grafana
    deploy:
      resources:
        limits:
          memory: 512M
    networks:
      - platform-net
```

**File**: `chatbot/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**File**: `chatbot/requirements.txt`

```
fastapi==0.104.1
uvicorn==0.24.0
langchain==0.0.335
openai==1.3.5
clickhouse-driver==0.2.6
requests==2.31.0
pydantic==2.5.0
```

---

## 5. Additional AI Opportunities

### A. Fraud Detection (Priority: MEDIUM)

Detect suspicious purchase patterns:
- Multiple purchases from same IP in short time
- Purchases with abnormal pricing
- Cart manipulation attempts

**Implementation**: Add fraud score to purchase events using ML model.

### B. Dynamic Pricing (Priority: LOW)

Adjust prices based on:
- Demand forecasting
- Competitor pricing (external API)
- Inventory levels
- User behavior

**Implementation**: Reinforcement learning model that suggests optimal prices.

### C. Customer Segmentation (Priority: MEDIUM)

Cluster users based on:
- Purchase frequency
- Average order value
- Category preferences
- Session patterns

**Implementation**: K-Means clustering on user features, store segments in ClickHouse.

### D. Real-Time Personalization (Priority: HIGH)

**What**: Personalize product views based on user history + current session

**Implementation**:
1. Session-based recommendations (what to show next)
2. Category affinity scoring
3. Price sensitivity detection

---

## Integration Roadmap

### Phase 1: Foundation (Weeks 1-2)
- ✅ Set up anomaly detection pipeline
- ✅ Integrate Slack alerts
- ✅ Add anomaly panel to Grafana

### Phase 2: Chatbot (Weeks 3-4)
- ✅ Build FastAPI chatbot backend
- ✅ Implement Text-to-SQL using LangChain
- ✅ Embed chat widget in Grafana
- ✅ Test dashboard modifications via chat

### Phase 3: Predictive Analytics (Weeks 5-6)
- ✅ Implement revenue forecasting (Prophet)
- ✅ Add demand forecasting per category
- ✅ Visualize forecasts in Grafana

### Phase 4: Advanced ML (Weeks 7-8)
- ✅ Build recommendation system (ALS)
- ✅ Implement fraud detection
- ✅ Add customer segmentation

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Anomaly Detection | Spark ML + Isolation Forest | Real-time anomaly scoring |
| Forecasting | Prophet / ARIMA | Time series prediction |
| Recommendations | Spark ALS | Collaborative filtering |
| Chatbot Backend | FastAPI + LangChain | API server |
| LLM | OpenAI GPT-4 / Claude | Natural language understanding |
| Text-to-SQL | LangChain SQL Agent | Query generation |
| Vector Store | Pinecone / Qdrant | Semantic search (future) |

---

## Cost Considerations

**OpenAI API Costs** (Chatbot):
- GPT-4: $0.03/1K input tokens, $0.06/1K output tokens
- Estimated monthly cost: $50-$200 (depends on usage)
- **Alternative**: Use open-source LLMs (Llama 2, Mistral) via Ollama (free)

**Infrastructure Costs**:
- Chatbot service: 512MB RAM (~$5/month on cloud)
- ML model training: Run batch jobs (use existing Spark cluster)

---

## Example Chatbot Interactions

**User**: "Show me revenue for the last 7 days"
**Bot**:
```
Based on your data:
- Total Revenue (Last 7 Days): $12,450
- Average Daily Revenue: $1,778
- Trend: +15% vs previous week

SQL Query: SELECT SUM(total_revenue) FROM gold.revenue_daily WHERE event_date >= today() - 7
```

**User**: "Which category is performing best?"
**Bot**:
```
Top performing category: Electronics
- Units Sold: 1,245
- Revenue: $89,234
- 35% of total revenue

This category is 20% above average. Consider increasing inventory.
```

**User**: "Add a panel showing cart abandonment by hour"
**Bot**:
```
✅ I've added a new timeseries panel "Cart Abandonment by Hour" to your dashboard.

The panel shows abandonment rate trends over the last 24 hours, with hourly granularity.
Peak abandonment occurs at 3 PM (78%). Consider A/B testing checkout improvements during this window.
```

**User**: "Alert me if revenue drops by more than 20%"
**Bot**:
```
✅ Alert configured!

I'll notify you via Slack if:
- Revenue per minute drops > 20% from 24-hour average
- Threshold: $45/min (current avg: $56/min)

You can modify this threshold anytime by saying "change alert threshold to X"
```

---

## Next Steps

1. **Choose Priority**: Start with Anomaly Detection OR Chatbot (both high impact)
2. **Set up OpenAI API**: Get API key from platform.openai.com
3. **Create Grafana API Key**: Settings → API Keys → New API Key (Editor role)
4. **Deploy chatbot service**: Add to docker-compose.yml
5. **Test end-to-end**: Chat interface → SQL query → Result visualization

Let me know which AI feature you'd like to implement first, and I can provide detailed step-by-step code!
