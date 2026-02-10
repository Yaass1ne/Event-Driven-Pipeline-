# 🤖 AI Chatbot Usage Guide

Complete guide to using the natural language analytics chatbot powered by Groq (LLaMA 3.3 70B).

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Quick Start](#-quick-start)
- [Data Queries](#-data-queries)
- [Dashboard Modifications](#-dashboard-modifications)
- [Advanced Features](#-advanced-features)
- [Troubleshooting](#-troubleshooting)
- [Architecture](#-architecture)

---

## 🎯 Overview

The AI chatbot provides a **natural language interface** to your analytics platform. Instead of writing SQL queries or manually configuring Grafana, simply ask questions in plain English.

### What Can It Do?

**📊 Query Analytics Data:**
- Revenue, conversions, user metrics
- Category performance, cart abandonment
- Real-time event streams

**🎨 Modify Grafana Dashboards:**
- Change time ranges on panels
- Update panel titles
- Modify SQL queries with filters/aggregations
- Add new visualization panels
- Change chart types (line/bar/pie/stat)

### Key Technologies

- **LLaMA 3.3 70B** (via Groq API) - Intent detection, SQL generation, query modification
- **Flask** - Web server and API
- **ClickHouse** - Data source
- **Grafana API** - Dashboard manipulation

---

## 🚀 Quick Start

### 1. Access the Chatbot

Open in your browser:
```
http://localhost:5000
```

### 2. Try Example Queries

**Click the suggestion buttons:**
- 💰 Revenue yesterday
- 📈 Conversion rate
- 🏆 Top categories
- ⏰ Change time to 7d

**Or type your own questions!**

### 3. Understand the Response

**For Data Queries** (Blue Badge):
```
📊 DATA QUERY

Yesterday's revenue was $15,234.56 from 287 purchases,
with an average order value of $53.08.

📝 Query: SELECT total_revenue, total_purchases,
avg_order_value FROM gold.revenue_daily
WHERE event_date = yesterday()
```

**For Dashboard Modifications** (Yellow Badge):
```
🎨 DASHBOARD UPDATE

✅ Changed time range for all panels to 7d

🔗 View updated dashboard: http://grafana:3000/d/lakehouse-overview

🔧 {"action": "change_time_range", "target": "all", "time_range": "7d"}
```

---

## 📊 Data Queries

### Revenue Metrics

**Daily Revenue:**
```
"What was revenue yesterday?"
"Show me revenue for the last 7 days"
"What's today's revenue so far?"
```

**Response Example:**
```
Yesterday's revenue was $15,234.56 from 287 purchases,
with an average order value of $53.08. This represents
a 12% increase from the previous day.
```

**Average Order Value:**
```
"What is the average order value?"
"Show AOV trend"
```

**Purchase Volume:**
```
"How many purchases today?"
"What's the purchase count for this week?"
```

### User Metrics

**Daily Active Users:**
```
"How many active users today?"
"Show DAU for the last 7 days"
"What's the user count?"
```

**Conversion Rate:**
```
"What is the conversion rate?"
"Show me conversion rate yesterday"
"Is conversion rate above 3%?"
```

### Category Analysis

**Top Categories:**
```
"Show top 5 categories by sales"
"Which category has the most revenue?"
"Top performing categories today"
```

**Specific Category Performance:**
```
"How many Electronics sold today?"
"What's Fashion category revenue?"
"Show Beauty category performance"
```

### Cart Abandonment

```
"What is the cart abandonment rate?"
"Show abandoned cart stats"
"How many carts were abandoned yesterday?"
```

### Real-Time Metrics

```
"What's the revenue per minute right now?"
"Show recent event activity"
"How many purchases in the last hour?"
```

---

## 🎨 Dashboard Modifications

### Level 1: Time Range Changes

**Change All Panels:**
```
"Change all charts to show last 7 days"
"Set all panels to 30 day view"
"Update dashboard time range to 6 hours"
```

**Change Specific Panel:**
```
"Change revenue panel to show last 24 hours"
"Set conversion rate chart to 7 day view"
"Update DAU panel to show last month"
```

**Supported Time Ranges:**
- 1h, 6h, 12h, 24h (hours)
- 7d, 30d (days)

### Level 1: Title Updates

```
"Rename revenue panel to Daily Revenue"
"Change conversion rate title to CR %"
"Update DAU panel title to Active Users"
```

### Level 1: Query Modifications

**Add Filters:**
```
"Filter category sales to show only Electronics"
"Show revenue excluding orders under $50"
"Display only mobile events in event stream"
```

**Change Aggregations:**
```
"Show revenue by hour instead of day"
"Group categories by week"
"Display purchase count instead of sum"
```

**Add Calculations:**
```
"Add growth percentage to revenue panel"
"Show conversion rate as percentage"
"Calculate year-over-year comparison"
```

### Level 2: Add New Panels

**Stat Panels:**
```
"Add a stat panel showing total purchases"
"Create a number panel for average order value"
"Insert a stat showing cart abandonment rate"
```

**Time Series Charts:**
```
"Add a line chart for conversion rate trend"
"Create time series showing revenue by hour"
"Insert chart tracking purchase velocity"
```

**Bar Charts:**
```
"Add a bar chart for top 10 products"
"Create horizontal bars for category comparison"
"Insert bar chart showing daily revenue"
```

**Pie Charts:**
```
"Add a pie chart for cart abandonment"
"Create pie chart showing revenue by category"
"Insert donut chart for source distribution"
```

**Tables:**
```
"Add a table showing all categories with revenue"
"Create data table for top users by purchases"
"Insert table with conversion rate breakdown"
```

### Level 2: Change Visualization Types

```
"Change revenue chart to bar chart"
"Convert category sales to pie chart"
"Make conversion rate a stat panel"
"Transform DAU to time series"
```

**Supported Types:**
- `stat` - Single number/stat
- `timeseries` - Line chart with time
- `barchart` - Bar chart
- `piechart` - Pie/donut chart
- `table` - Data table

---

## 🎓 Advanced Features

### Combining Queries

The chatbot can handle complex, multi-part questions:

```
"Show me revenue and conversion rate for yesterday"
"What are the top 3 categories and their abandonment rates?"
"Compare today's purchases to yesterday"
```

### SQL Transparency

Every data query shows the generated SQL:
```
📝 Query: SELECT category, units_sold
FROM gold.category_sales_daily
WHERE event_date = today()
ORDER BY units_sold DESC LIMIT 5
```

**Why This Matters:**
- Learn SQL by example
- Verify query accuracy
- Debug unexpected results
- Extend queries manually

### Dashboard Modification Details

Every modification shows the JSON structure:
```
🔧 {
  "action": "add_panel",
  "title": "Cart Abandonment",
  "type": "piechart",
  "query": "SELECT sessions_with_cart, abandoned_carts..."
}
```

**Use This To:**
- Understand what changed
- Replicate modifications
- Debug panel issues
- Learn Grafana API structure

### Context-Aware Responses

The chatbot remembers panel names and adapts:

```
User: "Show revenue per minute panel"
Bot: [Shows current revenue chart]

User: "Change it to bar chart"
Bot: ✅ Changed 'Revenue Per Minute' to bar chart
```

---

## 📝 Example Workflows

### Workflow 1: Morning Dashboard Review

**1. Check Yesterday's Performance:**
```
User: "What was revenue yesterday?"
Bot: $15,234 from 287 purchases, AOV $53.08

User: "What about conversion rate?"
Bot: 3.2%, slightly below last week's 3.5%

User: "Show top 3 categories"
Bot: 1. Electronics: 89 units
     2. Fashion: 67 units
     3. Home: 45 units
```

**2. Adjust Dashboard:**
```
User: "Change all charts to show last 7 days"
Bot: ✅ Changed time range for all panels to 7d
```

### Workflow 2: Deep-Dive Analysis

**1. Identify Issue:**
```
User: "What's the cart abandonment rate?"
Bot: 68% - 234 out of 345 carts were abandoned

User: "That's high. Show me which categories have highest abandonment"
Bot: [Executes custom query]
     Electronics: 75%, Fashion: 62%, Home: 58%
```

**2. Add Tracking:**
```
User: "Add a pie chart for cart abandonment by category"
Bot: ✅ Added new piechart panel: 'Cart Abandonment by Category'

User: "Also add a stat panel showing abandonment rate"
Bot: ✅ Added new stat panel: 'Cart Abandonment Rate'
```

### Workflow 3: Custom Dashboard Creation

**1. Start Fresh:**
```
User: "Add a time series for hourly revenue"
Bot: ✅ Added new timeseries panel: 'Hourly Revenue'

User: "Add a bar chart comparing categories"
Bot: ✅ Added new barchart panel: 'Category Comparison'

User: "Add stat panels for key metrics"
Bot: ✅ Added new stat panel: 'Key Metrics'
```

**2. Refine:**
```
User: "Change time range to 24 hours"
Bot: ✅ Changed time range for all panels to 24h

User: "Rename hourly revenue to Real-Time Revenue"
Bot: ✅ Updated panel title to 'Real-Time Revenue'
```

---

## 🔧 Troubleshooting

### Issue 1: Buttons Not Working

**Symptoms:** Clicking suggestion buttons does nothing

**Solutions:**
1. **Hard refresh:** Ctrl+F5 or Cmd+Shift+R
2. **Clear cache:** Browser settings → Clear cache
3. **Check console:** F12 → Console tab for errors
4. **Restart chatbot:**
   ```bash
   docker compose restart chatbot
   ```

### Issue 2: "No Data Found" Responses

**Symptoms:** Chatbot returns empty results

**Causes:**
- Data hasn't accumulated yet (wait 10 minutes)
- Batch pipeline hasn't run (trigger in Airflow)
- Wrong table queried

**Solutions:**
1. **Check ClickHouse:**
   ```bash
   curl "http://localhost:8123" --data "SELECT count(*) FROM gold.revenue_daily"
   ```

2. **Trigger Airflow DAG:**
   - Go to http://localhost:8082
   - Enable and trigger `lakehouse_batch_pipeline`

3. **Verify real-time data:**
   ```bash
   curl "http://localhost:8123" --data "SELECT count(*) FROM realtime.events_per_minute"
   ```

### Issue 3: Dashboard Modifications Don't Appear

**Symptoms:** Chatbot confirms change but Grafana doesn't update

**Solutions:**
1. **Hard refresh Grafana:** Ctrl+F5 on dashboard
2. **Check Grafana logs:**
   ```bash
   docker compose logs grafana --tail 50
   ```
3. **Verify dashboard UID:**
   - Should be: `lakehouse-overview`
   - Check URL: `/d/lakehouse-overview`

### Issue 4: Groq API Errors

**Symptoms:** "Groq API error" messages

**Causes:**
- Invalid API key
- Rate limit exceeded
- Network issues

**Solutions:**
1. **Verify API key:**
   ```bash
   docker compose exec chatbot printenv GROQ_API_KEY
   ```

2. **Get new key:** https://console.groq.com

3. **Update docker-compose.yml:**
   ```yaml
   chatbot:
     environment:
       GROQ_API_KEY: "your-new-key"
   ```

4. **Restart:**
   ```bash
   docker compose up -d chatbot
   ```

### Issue 5: SQL Query Errors

**Symptoms:** "ClickHouse error" in response

**Causes:**
- Invalid SQL syntax
- Table doesn't exist
- Column name mismatch

**Solutions:**
1. **Check error message:** Shows specific SQL error
2. **Verify table schema:**
   ```bash
   curl "http://localhost:8123" --data "DESCRIBE gold.revenue_daily"
   ```
3. **Rephrase question:** Try simpler query first

---

## 🏗️ Architecture

### System Overview

```
User Browser
     │
     ▼
Flask Web Server (Port 5000)
     │
     ├─► Intent Detection (Groq LLM)
     │        │
     │        ├─► "query" → SQL Generation
     │        │              │
     │        │              ▼
     │        │         ClickHouse Execute
     │        │              │
     │        │              ▼
     │        │         Answer Generation
     │        │
     │        └─► "modify" → Parse Request
     │                        │
     │                        ▼
     │                   Fetch Dashboard (Grafana API)
     │                        │
     │                        ▼
     │                   Apply Modification
     │                        │
     │                        ▼
     │                   Save Dashboard (Grafana API)
     │
     └─► Response to User
```

### Data Flow: Query Request

```
1. User: "What was revenue yesterday?"

2. Intent Detection:
   - Calls Groq API
   - Returns: "query"

3. SQL Generation:
   - Sends question + schema context to Groq
   - Returns: "SELECT total_revenue FROM gold.revenue_daily
              WHERE event_date = yesterday()"

4. Execute Query:
   - Connects to ClickHouse
   - Returns: 15234.56

5. Generate Answer:
   - Sends result to Groq with question
   - Returns: "Yesterday's revenue was $15,234.56..."

6. Display to User:
   - Shows answer with SQL code
   - Blue "DATA QUERY" badge
```

### Data Flow: Modification Request

```
1. User: "Change all charts to show last 7 days"

2. Intent Detection:
   - Calls Groq API
   - Returns: "modify"

3. Parse Request:
   - Sends to Groq with modification context
   - Returns: {"action": "change_time_range",
              "target": "all", "time_range": "7d"}

4. Fetch Dashboard:
   - GET /api/dashboards/uid/lakehouse-overview
   - Returns: Full dashboard JSON (500+ lines)

5. Apply Modification:
   - Find target panels
   - Update timeFrom/timeTo fields
   - Modify dashboard JSON

6. Save Dashboard:
   - POST /api/dashboards/db
   - With: {"dashboard": {...}, "overwrite": true}

7. Display to User:
   - Shows success message
   - Yellow "DASHBOARD UPDATE" badge
   - Link to updated dashboard
```

### Key Components

**Intent Detector:**
```python
def detect_intent(user_message):
    # Groq classifies as "query" or "modify"
    # Temperature: 0.1 (deterministic)
    # Max tokens: 10 (single word response)
```

**SQL Generator:**
```python
def generate_sql(user_question):
    # Context: All table schemas
    # Model: llama-3.3-70b-versatile
    # Returns: Single SQL query
```

**Dashboard Modifier:**
```python
def change_panel_time_range(dashboard, panel_title, time_range):
    # Find panel by title (fuzzy match)
    # Update time range fields
    # Return success message
```

### Available Tables (Schema Context)

The chatbot knows about:

**Gold Layer (Business KPIs):**
- `gold.daily_active_users`
- `gold.revenue_daily`
- `gold.conversion_rate_daily`
- `gold.category_sales_daily`
- `gold.cart_abandonment_daily`
- `gold.events_per_source_daily`
- `gold.purchases_per_page_daily`

**Real-Time Layer:**
- `realtime.events_per_minute`
- `realtime.revenue_per_minute`

### Modification Actions

**Implemented:**
1. `change_time_range` - Update panel time windows
2. `update_title` - Rename panels
3. `modify_query` - Change SQL with filters/aggregations
4. `add_panel` - Insert new visualizations
5. `change_viz_type` - Convert chart types

**Future Enhancements:**
6. `rearrange` - Move panels in grid
7. `delete_panel` - Remove visualizations
8. `update_colors` - Change color schemes
9. `add_alert` - Create alert rules
10. `clone_panel` - Duplicate panels

---

## 🎯 Best Practices

### For Data Queries

**✅ DO:**
- Ask specific questions
- Use common terms (yesterday, today, last week)
- Reference table names if known
- Check SQL output for accuracy

**❌ DON'T:**
- Ask overly complex multi-table joins
- Use ambiguous time references
- Assume table names without checking
- Expect real-time data in Gold tables

### For Dashboard Modifications

**✅ DO:**
- Use descriptive panel names
- Test with small changes first
- Keep dashboard link for rollback
- Verify changes in Grafana after modification

**❌ DON'T:**
- Change all panels without testing
- Delete panels accidentally (use carefully)
- Modify production dashboards without backup
- Trust modifications without verification

### Performance Tips

**Fast Queries:**
- Use Gold tables (pre-aggregated)
- Limit results (TOP 10, LIMIT 5)
- Use specific dates

**Slow Queries:**
- Avoid Bronze/Silver tables (raw data)
- Don't scan all history without date filters
- Limit real-time table queries to recent windows

---

## 📚 Additional Resources

### Related Documentation
- [Main README](../README.md) - Platform overview
- [Architecture Guide](architecture/ARCHITECTURE.md) - System design
- [Example Queries](queries/EXAMPLE_QUERIES.md) - SQL reference
- [Troubleshooting](setup/TROUBLESHOOTING.md) - Common issues

### External Links
- [Groq API Docs](https://console.groq.com/docs) - LLaMA model reference
- [ClickHouse SQL](https://clickhouse.com/docs/en/sql-reference) - Query syntax
- [Grafana API](https://grafana.com/docs/grafana/latest/developers/http_api/) - Dashboard API
- [LLaMA 3.3](https://www.llama.com/) - Model capabilities

---

## 🚀 Future Enhancements

**Planned Features:**
- 🔄 Dashboard version control (rollback changes)
- 📊 Multi-dashboard support (switch between dashboards)
- 🎨 Theme customization (dark mode, color schemes)
- 📧 Email report generation (scheduled insights)
- 🔔 Alert configuration (set thresholds via chat)
- 📈 Trend analysis (automatic insight detection)
- 💬 Conversation history (remember context)
- 🔐 User authentication (role-based access)

**Want a feature?** Open an issue or contribute!

---

**Built with ❤️ powered by Groq (LLaMA 3.3 70B)**

Questions? Check [TROUBLESHOOTING.md](setup/TROUBLESHOOTING.md) or open an issue.
