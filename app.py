#!/usr/bin/env python3
import os
from flask import Flask, jsonify, render_template_string, send_file
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Use your actual dashboard HTML
DASHBOARD_HTML = open('dashboard.html', 'r').read() if os.path.exists('dashboard.html') else '''
<!DOCTYPE html>
<html>
<head>
    <title>Hughes Lawn AI Dashboard</title>
    <style>
        body {
            background-image: url('/grass-background');
            background-size: cover;
            color: white;
            font-family: -apple-system, sans-serif;
        }
        .container {
            background: rgba(0,0,0,0.5);
            padding: 20px;
            border-radius: 10px;
            margin: 20px;
        }
        h1 {
            color: #4ade80;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Hughes Lawn AI Dashboard</h1>
        <p>Smart Irrigation System - Azure Deployment</p>
        <p>Weather: 89°F | Humidity: 47%</p>
        <p>Zones: 7 configured | RainBird: q0852082.eero.online</p>
    </div>
</body>
</html>
'''

@app.route('/')
def index():
    return DASHBOARD_HTML

@app.route('/grass-background')
def grass_background():
    try:
        return send_file('grass.jpeg', mimetype='image/jpeg')
    except:
        return '', 404

@app.route('/api/status')
def api_status():
    return jsonify({'status': 'online', 'timestamp': datetime.now().isoformat()})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
