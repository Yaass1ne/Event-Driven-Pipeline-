"""
Grafana Chatbot - Natural Language Interface to Analytics Data & Dashboards
Uses Groq (LLaMA 3.3 70B) for NL→SQL queries and dashboard modifications.
"""

import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from groq import Groq
from clickhouse_driver import Client

app = Flask(__name__)
CORS(app)

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
CH_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CH_PORT = int(os.getenv("CLICKHOUSE_PORT", "9000"))
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://grafana:3000")
GRAFANA_USER = os.getenv("GRAFANA_USER", "admin")
GRAFANA_PASSWORD = os.getenv("GRAFANA_PASSWORD", "admin")

# Initialize clients
groq_client = Groq(api_key=GROQ_API_KEY)
ch_client = Client(host=CH_HOST, port=CH_PORT, database="default")

# Dashboard UID (from Grafana provisioning)
DASHBOARD_UID = "lakehouse-overview"

# Schema context for data queries
SCHEMA_CONTEXT = """
You are a SQL expert. Convert natural language questions to ClickHouse SQL queries.

AVAILABLE TABLES:
1. gold.daily_active_users (event_date, dau_count)
2. gold.revenue_daily (event_date, total_revenue, total_purchases, avg_order_value)
3. gold.conversion_rate_daily (event_date, dau_count, unique_buyers, conversion_rate)
4. gold.category_sales_daily (event_date, category, units_sold, category_revenue)
5. gold.cart_abandonment_daily (event_date, sessions_with_cart, abandoned_carts, abandonment_rate)
6. realtime.revenue_per_minute (window_start, window_end, revenue, purchase_count)
7. realtime.events_per_minute (window_start, event_type, event_count)

RULES:
1. Use ClickHouse SQL syntax
2. For dates: today(), yesterday(), toDate()
3. For latest: ORDER BY event_date DESC LIMIT 1
4. Return ONLY the SQL query, no explanations
5. Do NOT use FORMAT clauses

Examples:
- "revenue yesterday" → SELECT total_revenue FROM gold.revenue_daily WHERE event_date = yesterday()
- "top 5 categories" → SELECT category, units_sold FROM gold.category_sales_daily WHERE event_date = today() ORDER BY units_sold DESC LIMIT 5
"""

# Dashboard modification context
DASHBOARD_CONTEXT = """
You are a Grafana dashboard expert. Analyze user requests to modify dashboards.

CAPABILITIES:
1. Change time ranges (last 6h, 12h, 24h, 7d, 30d)
2. Update panel titles
3. Modify queries (add filters, change aggregations)
4. Add new panels (stat, timeseries, barchart, piechart, table)
5. Change visualization types
6. Rearrange panel positions

AVAILABLE PANELS IN DASHBOARD:
- Panel 1: Daily Active Users (stat)
- Panel 2: Conversion Rate (stat)
- Panel 3: Total Revenue Today (stat)
- Panel 4: Total Events (stat)
- Panel 5: Real-Time Event Stream (timeseries)
- Panel 6: Revenue Per Minute (timeseries)
- Panel 7: Revenue by Category (piechart)
- Panel 8: Top Categories by Units Sold (barchart)

Respond with JSON:
{
    "action": "change_time_range" | "update_title" | "modify_query" | "add_panel" | "change_viz_type" | "rearrange",
    "target": "panel_id or panel_title",
    "changes": {
        // Specific changes based on action
    }
}
"""


# ==================== Grafana API Functions ====================

def get_grafana_headers():
    """Get auth headers for Grafana API."""
    import base64
    auth = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASSWORD}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json"
    }


def get_dashboard():
    """Fetch current dashboard JSON."""
    try:
        url = f"{GRAFANA_URL}/api/dashboards/uid/{DASHBOARD_UID}"
        response = requests.get(url, headers=get_grafana_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise Exception(f"Failed to fetch dashboard: {str(e)}")


def update_dashboard(dashboard_json):
    """Update dashboard in Grafana."""
    try:
        url = f"{GRAFANA_URL}/api/dashboards/db"
        payload = {
            "dashboard": dashboard_json["dashboard"],
            "overwrite": True,
            "message": "Updated via chatbot"
        }
        response = requests.post(url, headers=get_grafana_headers(),
                                json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise Exception(f"Failed to update dashboard: {str(e)}")


def find_panel_by_title(dashboard, title):
    """Find panel by title (case-insensitive partial match)."""
    title_lower = title.lower()
    for panel in dashboard["dashboard"]["panels"]:
        if title_lower in panel.get("title", "").lower():
            return panel
    return None


# ==================== Dashboard Modification Functions ====================

def change_panel_time_range(dashboard, panel_title, time_range):
    """Change time range for specific panel or all panels."""
    time_map = {
        "6h": "now-6h", "12h": "now-12h", "24h": "now-24h",
        "7d": "now-7d", "30d": "now-30d", "1h": "now-1h"
    }

    from_time = time_map.get(time_range, "now-24h")

    if panel_title.lower() == "all" or panel_title == "*":
        # Change all panels
        dashboard["dashboard"]["time"] = {"from": from_time, "to": "now"}
        return f"Changed time range for all panels to {time_range}"
    else:
        # Change specific panel
        panel = find_panel_by_title(dashboard, panel_title)
        if not panel:
            return f"Panel '{panel_title}' not found"

        panel["timeFrom"] = from_time
        return f"Changed time range for '{panel.get('title')}' to {time_range}"


def update_panel_title(dashboard, old_title, new_title):
    """Update panel title."""
    panel = find_panel_by_title(dashboard, old_title)
    if not panel:
        return f"Panel '{old_title}' not found"

    old_name = panel.get("title")
    panel["title"] = new_title
    return f"Updated panel title from '{old_name}' to '{new_title}'"


def modify_panel_query(dashboard, panel_title, modification):
    """Modify panel SQL query."""
    panel = find_panel_by_title(dashboard, panel_title)
    if not panel:
        return f"Panel '{panel_title}' not found"

    # Get first target (query)
    if "targets" not in panel or not panel["targets"]:
        return "Panel has no queries"

    target = panel["targets"][0]
    current_query = target.get("rawSql", "")

    # Apply modification using LLM
    modified_query = apply_query_modification(current_query, modification)
    target["rawSql"] = modified_query

    return f"Modified query for '{panel.get('title')}'"


def apply_query_modification(original_query, modification):
    """Use LLM to modify SQL query based on natural language instruction."""
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a SQL expert. Modify the given SQL query based on the user's instruction. Return ONLY the modified SQL query, no explanations."
                },
                {
                    "role": "user",
                    "content": f"Original query:\n{original_query}\n\nModification: {modification}\n\nReturn the modified query:"
                }
            ],
            temperature=0.1,
            max_tokens=500
        )
        return completion.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()
    except Exception as e:
        return original_query  # Return unchanged on error


def add_panel_to_dashboard(dashboard, panel_config):
    """Add new panel to dashboard."""
    panels = dashboard["dashboard"]["panels"]

    # Find next available ID and position
    max_id = max([p.get("id", 0) for p in panels]) if panels else 0
    new_id = max_id + 1

    # Calculate grid position (add to bottom)
    y_pos = max([p.get("gridPos", {}).get("y", 0) + p.get("gridPos", {}).get("h", 0)
                 for p in panels]) if panels else 0

    # Base panel structure
    new_panel = {
        "id": new_id,
        "title": panel_config.get("title", "New Panel"),
        "type": panel_config.get("type", "timeseries"),
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": y_pos},
        "datasource": {"type": "grafana-clickhouse-datasource", "uid": "clickhouse"},
        "targets": [{
            "datasource": {"type": "grafana-clickhouse-datasource", "uid": "clickhouse"},
            "rawSql": panel_config.get("query", "SELECT 1"),
            "refId": "A"
        }]
    }

    # Type-specific configurations
    if panel_config["type"] == "stat":
        new_panel["options"] = {
            "reduceOptions": {"values": False, "calcs": ["lastNotNull"]}
        }
    elif panel_config["type"] == "piechart":
        new_panel["type"] = "piechart"
        new_panel["options"] = {"legend": {"displayMode": "table", "placement": "right"}}
    elif panel_config["type"] == "barchart":
        new_panel["type"] = "barchart"
        new_panel["options"] = {"legend": {"displayMode": "list", "placement": "bottom"}}

    panels.append(new_panel)
    return f"Added new {panel_config['type']} panel: '{panel_config['title']}'"


def change_visualization_type(dashboard, panel_title, new_type):
    """Change panel visualization type."""
    panel = find_panel_by_title(dashboard, panel_title)
    if not panel:
        return f"Panel '{panel_title}' not found"

    old_type = panel.get("type")
    panel["type"] = new_type

    # Update type-specific options
    if new_type == "stat":
        panel["options"] = {"reduceOptions": {"values": False, "calcs": ["lastNotNull"]}}
    elif new_type == "piechart":
        panel["options"] = {"legend": {"displayMode": "table", "placement": "right"}}
    elif new_type == "barchart":
        panel["options"] = {"legend": {"displayMode": "list", "placement": "bottom"}}
    elif new_type == "timeseries":
        panel["options"] = {"legend": {"displayMode": "list", "placement": "bottom"}}

    return f"Changed '{panel.get('title')}' from {old_type} to {new_type}"


def rearrange_panels(dashboard, layout_changes):
    """Rearrange panel positions."""
    for change in layout_changes:
        panel = find_panel_by_title(dashboard, change["panel"])
        if panel:
            panel["gridPos"].update(change["gridPos"])

    return f"Rearranged {len(layout_changes)} panels"


# ==================== LLM Intent Detection ====================

def detect_intent(user_message):
    """Detect if user wants data query or dashboard modification."""
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """Classify the user's intent as either "query" (asking for data) or "modify" (changing dashboard).

Examples:
- "What was revenue yesterday?" → query
- "Show top categories" → query
- "Change time range to 7 days" → modify
- "Add a chart for cart abandonment" → modify
- "Rename the revenue panel" → modify
- "Update conversion rate chart to bar chart" → modify

Respond with ONLY: query or modify"""
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            temperature=0.1,
            max_tokens=10
        )
        intent = completion.choices[0].message.content.strip().lower()
        return "modify" if "modify" in intent else "query"
    except Exception:
        return "query"  # Default to query on error


def parse_modification_request(user_message):
    """Parse dashboard modification request into structured format."""
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """Parse dashboard modification requests into JSON format.

Actions:
- change_time_range: {"action": "change_time_range", "target": "panel_name or all", "time_range": "6h|12h|24h|7d|30d"}
- update_title: {"action": "update_title", "target": "current_name", "new_title": "new name"}
- modify_query: {"action": "modify_query", "target": "panel_name", "modification": "description"}
- add_panel: {"action": "add_panel", "title": "name", "type": "stat|timeseries|barchart|piechart|table", "query": "SQL or description"}
- change_viz_type: {"action": "change_viz_type", "target": "panel_name", "new_type": "stat|timeseries|barchart|piechart"}

Examples:
- "Change all charts to show last 7 days" → {"action": "change_time_range", "target": "all", "time_range": "7d"}
- "Rename revenue panel to Daily Revenue" → {"action": "update_title", "target": "revenue", "new_title": "Daily Revenue"}
- "Add pie chart for category sales" → {"action": "add_panel", "title": "Category Sales", "type": "piechart", "query": "SELECT category, category_revenue FROM gold.category_sales_daily WHERE event_date = today()"}

Return ONLY valid JSON."""
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            temperature=0.1,
            max_tokens=300
        )

        response = completion.choices[0].message.content.strip()
        # Clean JSON from markdown
        response = response.replace("```json", "").replace("```", "").strip()
        return json.loads(response)
    except Exception as e:
        return {"error": f"Could not parse request: {str(e)}"}


# ==================== Query Functions ====================

def generate_sql(user_question):
    """Generate SQL from natural language."""
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SCHEMA_CONTEXT},
                {"role": "user", "content": f"Convert to SQL: {user_question}"}
            ],
            temperature=0.1,
            max_tokens=500
        )
        sql = completion.choices[0].message.content.strip()
        return sql.replace("```sql", "").replace("```", "").strip()
    except Exception as e:
        raise Exception(f"Groq API error: {str(e)}")


def execute_query(sql):
    """Execute SQL against ClickHouse."""
    try:
        result = ch_client.execute(sql)
        if not result:
            return "No data found."

        if len(result) == 1 and len(result[0]) == 1:
            return str(result[0][0])

        output = []
        for row in result:
            output.append(" | ".join(str(col) for col in row))
        return "\n".join(output)
    except Exception as e:
        raise Exception(f"ClickHouse error: {str(e)}")


def generate_answer(user_question, query_result):
    """Generate natural language answer."""
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a business analyst. Provide clear, concise answers with insights. Format numbers nicely ($ for money, % for rates)."
                },
                {
                    "role": "user",
                    "content": f"Question: {user_question}\n\nData: {query_result}\n\nAnswer:"
                }
            ],
            temperature=0.3,
            max_tokens=300
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        return query_result


# ==================== HTML Template ====================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>📊 Analytics Chatbot</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 900px;
            height: 90vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            text-align: center;
            border-radius: 20px 20px 0 0;
        }
        .header h1 { font-size: 28px; margin-bottom: 8px; }
        .header p { opacity: 0.9; font-size: 14px; }
        .suggestions {
            padding: 15px 25px;
            background: white;
            border-bottom: 1px solid #e0e0e0;
            overflow-x: auto;
            white-space: nowrap;
        }
        .suggestion-btn {
            background: #f1f3f4;
            border: none;
            padding: 8px 15px;
            border-radius: 15px;
            margin: 5px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
            display: inline-block;
        }
        .suggestion-btn:hover {
            background: #667eea;
            color: white;
            transform: translateY(-2px);
        }
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 25px;
            background: #f8f9fa;
        }
        .message {
            margin-bottom: 20px;
            animation: slideIn 0.3s ease;
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .message.user {
            display: flex;
            justify-content: flex-end;
        }
        .message.bot {
            display: flex;
            justify-content: flex-start;
        }
        .message-content {
            max-width: 70%;
            padding: 15px 20px;
            border-radius: 15px;
            word-wrap: break-word;
        }
        .message.user .message-content {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .message.bot .message-content {
            background: white;
            color: #333;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .sql-query, .modification-details {
            background: #f1f3f4;
            padding: 10px;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            margin-top: 8px;
            color: #555;
            border-left: 3px solid #667eea;
        }
        .modification-details {
            border-left: 3px solid #f59e0b;
        }
        .input-container {
            padding: 20px;
            background: white;
            border-top: 1px solid #e0e0e0;
            display: flex;
            gap: 10px;
            border-radius: 0 0 20px 20px;
        }
        #userInput {
            flex: 1;
            padding: 15px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            font-size: 15px;
            outline: none;
            transition: border-color 0.3s;
        }
        #userInput:focus {
            border-color: #667eea;
        }
        #sendBtn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 35px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 15px;
            font-weight: 600;
            transition: transform 0.2s;
        }
        #sendBtn:hover {
            transform: scale(1.05);
        }
        #sendBtn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: scale(1);
        }
        .loading {
            display: none;
            text-align: center;
            padding: 10px;
            color: #666;
        }
        .loading.active { display: block; }
        .loading::after {
            content: '...';
            animation: dots 1.5s steps(4, end) infinite;
        }
        @keyframes dots {
            0%, 20% { content: '.'; }
            40% { content: '..'; }
            60%, 100% { content: '...'; }
        }
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            margin-bottom: 5px;
        }
        .badge-query { background: #dbeafe; color: #1e40af; }
        .badge-modify { background: #fef3c7; color: #92400e; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Analytics Chatbot</h1>
            <p>Ask questions or modify your Grafana dashboard using plain English</p>
        </div>

        <div class="suggestions">
            <button class="suggestion-btn" onclick="askQuestion('What was the revenue yesterday?')">💰 Revenue yesterday</button>
            <button class="suggestion-btn" onclick="askQuestion('What is the conversion rate?')">📈 Conversion rate</button>
            <button class="suggestion-btn" onclick="askQuestion('Show top 5 categories')">🏆 Top categories</button>
            <button class="suggestion-btn" onclick="askQuestion('Change all charts to show last 7 days')">⏰ Change time to 7d</button>
            <button class="suggestion-btn" onclick="askQuestion('Add a pie chart for cart abandonment')">➕ Add chart</button>
            <button class="suggestion-btn" onclick="askQuestion('Change revenue chart to bar chart')">🎨 Change viz type</button>
        </div>

        <div class="chat-container" id="chatContainer">
            <div class="message bot">
                <div class="message-content">
                    👋 Hi! I'm your analytics assistant. I can help you with:<br><br>
                    <strong>📊 Data Queries:</strong><br>
                    • "What was revenue yesterday?"<br>
                    • "Show conversion rate"<br>
                    • "Top selling categories"<br><br>
                    <strong>🎨 Dashboard Modifications:</strong><br>
                    • "Change time range to 7 days"<br>
                    • "Add cart abandonment chart"<br>
                    • "Rename revenue panel to Daily Revenue"<br>
                    • "Change conversion chart to bar chart"
                </div>
            </div>
        </div>

        <div class="loading" id="loading">Thinking</div>

        <div class="input-container">
            <input type="text" id="userInput" placeholder="Ask about data or modify dashboard..." onkeypress="handleKeyPress(event)">
            <button id="sendBtn" onclick="sendMessage()">Send</button>
        </div>
    </div>

    <script>
        console.log('✅ Chatbot UI loaded');

        async function sendMessage() {
            const input = document.getElementById('userInput');
            const question = input.value.trim();

            if (!question) return;

            console.log('📤 Sending:', question);

            addMessage(question, 'user');
            input.value = '';

            document.getElementById('loading').classList.add('active');
            document.getElementById('sendBtn').disabled = true;

            try {
                const response = await fetch('/api/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question })
                });

                const data = await response.json();
                console.log('📥 Response:', data);

                if (data.error) {
                    addMessage('❌ ' + data.error, 'bot');
                } else if (data.type === 'query') {
                    addMessage(data.answer, 'bot', data.sql, 'query');
                } else if (data.type === 'modify') {
                    addMessage(data.message, 'bot', data.details, 'modify');
                }
            } catch (error) {
                console.error('❌ Error:', error);
                addMessage('❌ Connection error: ' + error.message, 'bot');
            } finally {
                document.getElementById('loading').classList.remove('active');
                document.getElementById('sendBtn').disabled = false;
            }
        }

        function addMessage(text, type, details = null, badge = null) {
            const container = document.getElementById('chatContainer');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${type}`;

            let badgeHtml = '';
            if (badge === 'query') {
                badgeHtml = '<span class="badge badge-query">📊 DATA QUERY</span><br>';
            } else if (badge === 'modify') {
                badgeHtml = '<span class="badge badge-modify">🎨 DASHBOARD UPDATE</span><br>';
            }

            let content = `<div class="message-content">${badgeHtml}${escapeHtml(text)}`;

            if (details) {
                const detailClass = badge === 'modify' ? 'modification-details' : 'sql-query';
                const icon = badge === 'modify' ? '🔧' : '📝';
                content += `<div class="${detailClass}">${icon} ${escapeHtml(details)}</div>`;
            }

            content += '</div>';

            messageDiv.innerHTML = content;
            container.appendChild(messageDiv);
            container.scrollTop = container.scrollHeight;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML.replace(/\\n/g, '<br>');
        }

        function askQuestion(question) {
            document.getElementById('userInput').value = question;
            sendMessage();
        }

        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }
    </script>
</body>
</html>
"""


# ==================== API Routes ====================

@app.route('/')
def index():
    """Serve chatbot UI."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/ask', methods=['POST'])
def ask():
    """Main API endpoint - handles both queries and modifications."""
    try:
        data = request.json
        user_question = data.get('question', '').strip()

        if not user_question:
            return jsonify({"error": "Question cannot be empty"}), 400

        print(f"📥 Question: {user_question}")

        # Detect intent
        intent = detect_intent(user_question)
        print(f"🎯 Intent: {intent}")

        if intent == "modify":
            # Dashboard modification
            mod_request = parse_modification_request(user_question)

            if "error" in mod_request:
                return jsonify({"error": mod_request["error"]}), 400

            print(f"🔧 Modification: {json.dumps(mod_request, indent=2)}")

            # Get current dashboard
            dashboard = get_dashboard()

            # Apply modification
            action = mod_request.get("action")
            result_msg = ""

            if action == "change_time_range":
                result_msg = change_panel_time_range(
                    dashboard,
                    mod_request.get("target", "all"),
                    mod_request.get("time_range", "24h")
                )
            elif action == "update_title":
                result_msg = update_panel_title(
                    dashboard,
                    mod_request.get("target"),
                    mod_request.get("new_title")
                )
            elif action == "modify_query":
                result_msg = modify_panel_query(
                    dashboard,
                    mod_request.get("target"),
                    mod_request.get("modification")
                )
            elif action == "add_panel":
                result_msg = add_panel_to_dashboard(dashboard, mod_request)
            elif action == "change_viz_type":
                result_msg = change_visualization_type(
                    dashboard,
                    mod_request.get("target"),
                    mod_request.get("new_type")
                )
            else:
                return jsonify({"error": f"Unknown action: {action}"}), 400

            # Save dashboard
            update_dashboard(dashboard)
            print(f"✅ {result_msg}")

            return jsonify({
                "type": "modify",
                "message": f"✅ {result_msg}\n\n🔗 View updated dashboard: {GRAFANA_URL}/d/{DASHBOARD_UID}",
                "details": json.dumps(mod_request, indent=2)
            })

        else:
            # Data query
            sql = generate_sql(user_question)
            print(f"🔍 SQL: {sql}")

            query_result = execute_query(sql)
            print(f"✅ Result: {query_result[:100]}...")

            answer = generate_answer(user_question, query_result)
            print(f"💬 Answer: {answer[:100]}...")

            return jsonify({
                "type": "query",
                "question": user_question,
                "sql": sql,
                "answer": answer
            })

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error: {error_msg}")
        return jsonify({"error": error_msg}), 500


@app.route('/health')
def health():
    """Health check."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


if __name__ == '__main__':
    print("🤖 Analytics Chatbot starting...")
    print(f"   ClickHouse: {CH_HOST}:{CH_PORT}")
    print(f"   Grafana: {GRAFANA_URL}")
    print(f"   Dashboard: {GRAFANA_URL}/d/{DASHBOARD_UID}")
    print(f"   Access at: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
