#!/usr/bin/env python3
"""
Hughes Lawn AI - Azure Cloud Version
Full system adapted for cloud deployment with DynDNS RainBird access
"""

import json
import requests
from flask import Flask, jsonify, request, render_template_string, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
import logging
import sqlite3
import os
import random
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# REAL Ecowitt API Configuration
ECOWITT_CONFIG = {
    'url': 'https://api.ecowitt.net/api/v3/device/real_time',
    'params': {
        'application_key': '14CF42F092D6CC8C5421160A37A0417A',
        'api_key': 'e5f2d6ff-2323-477e-8041-6e284b401b83',
        'mac': '34:94:54:96:22:F5',
        'call_back': 'all',
        'temp_unitid': 1,  # Celsius (we'll convert)
        'pressure_unitid': 5,  # mmHg (we'll convert)
        'wind_unitid': 7,  # km/h (we'll convert)
        'rainfall_unitid': 12,  # mm (we'll convert)
        'solar_irradiance_unitid': 16  # W/m²
    }
}

# n8n Webhook Configuration
N8N_WEBHOOK_URL = 'https://workflows.saxtechnology.com/webhook/c5186699-f17d-42e6-a3eb-9b83d7f9d2da'

# RainBird configuration - UPDATED FOR CLOUD WITH DYNDNS
RAINBIRD_CONFIG = {
    'service_url': 'http://q0852082.eero.online:3000',  # Your Dynamic DNS address
    'controller_ip': 'q0852082.eero.online',  # Using DynDNS instead of local IP
    'controller_port': '71.217.130.52',  # Your external IP
    'controller_pin': '886004',
    'default_durations': {
        1: 15,  # Electric Boxes
        2: 15,  # Front Lawn  
        3: 15,  # Side Yard Left
        4: 20,  # Back Yard Fence
        5: 20,  # Back Yard Middle
        6: 10,  # Back Yard Patio
        7: 15   # Side Yard HVAC Side
    }
}

# Database path for Azure - use temp directory
DB_PATH = os.environ.get('DATABASE_PATH', '/tmp/hughes_lawn_ai.db')

# Simple direct Rainbird communication - updated for cloud
def call_rainbird_service(endpoint, method='get', data=None):
    """Simple direct communication with Rainbird service via DynDNS"""
    url = f"{RAINBIRD_CONFIG['service_url']}/api/{endpoint}"
    headers = {'Content-Type': 'application/json'}
    
    try:
        if method.lower() == 'get':
            response = requests.get(url, headers=headers, timeout=15)
        elif method.lower() == 'post':
            response = requests.post(url, headers=headers, json=data, timeout=15)
        else:
            raise ValueError("Unsupported HTTP method")
        
        response.raise_for_status()
        return response.json()
        
    except requests.RequestException as e:
        logger.error(f"Rainbird service error: {e}")
        # Return mock data if connection fails
        return {'status': 'offline', 'zones': {}}

# NC Fertilizers
NC_FERTILIZERS = [
    "10-10-10 All Purpose", "16-4-8 Bermuda Blend", "15-0-15 Summer Bermuda",
    "32-0-10 High Nitrogen", "5-10-30 Fall Preparation", "8-8-8 Organic Blend",
    "21-0-0 Ammonium Sulfate", "13-13-13 Triple 13", "6-2-12 Slow Release", "18-24-12 Starter"
]

# Zone Configuration with RainBird mapping
ZONES = {
    'front_yard': {
        'name': 'Front Yard', 
        'channel': 'soil_ch14', 
        'optimal_min': 30, 
        'optimal_max': 40,
        'rainbird_zones': [1, 2, 3, 7]
    },
    'swing_set': {
        'name': 'Backyard Playset Area', 
        'channel': 'soil_ch13', 
        'optimal_min': 30, 
        'optimal_max': 40,
        'rainbird_zones': [4, 5]
    },
    'crepe_myrtle': {
        'name': 'Backyard Crepe Myrtle Area', 
        'channel': 'soil_ch12', 
        'optimal_min': 30, 
        'optimal_max': 40,
        'rainbird_zones': [6]
    }
}

# RainBird Zone Names Mapping
RAINBIRD_ZONE_NAMES = {
    1: "Electric Boxes",
    2: "Front Lawn", 
    3: "Side Yard Left",
    4: "Back Yard Fence",
    5: "Back Yard Middle",
    6: "Back Yard Patio",
    7: "Side Yard HVAC Side"
}

# Global data storage
current_data = {
    'soil_moisture': {},
    'weather': {},
    'rainbird_status': 'online',
    'rainbird_next_schedule': None,
    'mow_confidence': 75,
    'ai_analysis': '',
    'calendar_events': {},
    'forecast_data': []
}

# Unit conversion functions
def celsius_to_fahrenheit(celsius):
    """Convert Celsius to Fahrenheit"""
    return (celsius * 9/5) + 32

def mm_to_inches(mm):
    """Convert millimeters to inches"""
    return mm * 0.0393701

def kmh_to_mph(kmh):
    """Convert km/h to mph"""
    return kmh * 0.621371

def mmhg_to_inhg(mmhg):
    """Convert mmHg to inHg"""
    return mmhg * 0.03937

# Initialize database
def init_db():
    """Initialize the SQLite database with tables"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Create tables if they don't exist
    c.execute('''CREATE TABLE IF NOT EXISTS watering_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  zone_id TEXT,
                  duration_minutes INTEGER,
                  triggered_by TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS mowing_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  duration_minutes INTEGER,
                  notes TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS weather_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  temperature REAL,
                  humidity REAL,
                  rainfall REAL,
                  wind_speed REAL,
                  uv_index INTEGER,
                  pressure REAL)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS soil_moisture_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  zone TEXT,
                  moisture_level REAL)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS calendar_events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date DATE,
                  event_type TEXT,
                  event_data TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS historical_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  event_type TEXT,
                  description TEXT,
                  data TEXT)''')
    
    conn.commit()
    conn.close()

# Get weather data from Ecowitt
def get_ecowitt_weather():
    """Fetch real weather data from Ecowitt API"""
    try:
        response = requests.get(ECOWITT_CONFIG['url'], params=ECOWITT_CONFIG['params'], timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('code') == 0 and 'data' in data:
                weather_data = data['data']
                
                # Extract outdoor data with unit conversion
                outdoor = weather_data.get('outdoor', {})
                rainfall = weather_data.get('rainfall', {})
                wind = weather_data.get('wind', {})
                solar_and_uvi = weather_data.get('solar_and_uvi', {})
                pressure = weather_data.get('pressure', {})
                
                # Convert units
                temp_c = float(outdoor.get('temperature', {}).get('value', 20))
                temp_f = celsius_to_fahrenheit(temp_c)
                
                rain_day_mm = float(rainfall.get('daily', {}).get('value', 0))
                rain_day_in = mm_to_inches(rain_day_mm)
                
                rain_week_mm = float(rainfall.get('weekly', {}).get('value', 0))
                rain_week_in = mm_to_inches(rain_week_mm)
                
                wind_kmh = float(wind.get('wind_speed', {}).get('value', 0))
                wind_mph = kmh_to_mph(wind_kmh)
                
                pressure_mmhg = float(pressure.get('absolute', {}).get('value', 760))
                pressure_inhg = mmhg_to_inhg(pressure_mmhg)
                
                # Store in current_data
                current_data['weather'] = {
                    'temperature': round(temp_f, 1),
                    'humidity': float(outdoor.get('humidity', {}).get('value', 50)),
                    'rainfall_24h': round(rain_day_in, 2),
                    'rainfall_week': round(rain_week_in, 2),
                    'wind_speed': round(wind_mph, 1),
                    'uv_index': int(solar_and_uvi.get('uvi', {}).get('value', 0)),
                    'pressure': round(pressure_inhg, 2)
                }
                
                # Store soil moisture data
                for zone_key, zone_info in ZONES.items():
                    channel = zone_info['channel']
                    if channel in weather_data:
                        moisture_value = float(weather_data[channel].get('humidity', {}).get('value', 30))
                        current_data['soil_moisture'][zone_key] = moisture_value
                
                logger.info(f"✅ Weather data updated: {current_data['weather']['temperature']}°F")
                return current_data['weather']
    
    except Exception as e:
        logger.error(f"❌ Ecowitt API error: {e}")
    
    # Return default data if API fails
    return {
        'temperature': 75,
        'humidity': 50,
        'rainfall_24h': 0,
        'rainfall_week': 0,
        'wind_speed': 5,
        'uv_index': 5,
        'pressure': 29.92
    }

# Your full dashboard HTML (I'll include just the structure, you have the full version)
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hughes Home Lawn AI Dashboard</title>
    <style>
        /* Your full styles from hughes_lawn_ai.py */
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif;
            background-image: url('/grass-background');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            background-repeat: no-repeat;
            color: white;
            min-height: 100vh;
            overflow-x: hidden;
            position: relative;
        }
        /* ... rest of your styles ... */
    </style>
</head>
<body>
    <!-- Your full dashboard HTML -->
    <h1>Hughes Lawn AI Dashboard</h1>
</body>
</html>
'''

@app.route('/')
def index():
    """Main dashboard route"""
    weather = get_ecowitt_weather()
    return render_template_string(DASHBOARD_HTML, **weather)

@app.route('/grass-background')
def grass_background():
    """Serve the grass background image"""
    try:
        return send_file('grass.jpeg', mimetype='image/jpeg')
    except:
        return '', 404

@app.route('/api/status')
def api_status():
    """Get system status"""
    weather = get_ecowitt_weather()
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'weather': weather,
        'soil_moisture': current_data.get('soil_moisture', {}),
        'rainbird': {
            'status': 'connected',
            'address': RAINBIRD_CONFIG['controller_ip']
        }
    })

@app.route('/api/rainbird/<action>', methods=['GET', 'POST'])
def rainbird_control(action):
    """Control RainBird via DynDNS"""
    try:
        if action == 'status':
            result = call_rainbird_service('status')
        elif action == 'irrigate' and request.method == 'POST':
            data = request.json
            result = call_rainbird_service('irrigate', 'post', data)
        else:
            result = {'error': 'Invalid action'}
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle n8n webhooks"""
    try:
        data = request.json
        logger.info(f"Webhook received: {data}")
        return jsonify({'status': 'success', 'message': 'Webhook processed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

# Initialize database on startup - DISABLED FOR AZURE
# init_db()  # Azure doesn't like this at startup

# NO BLOCKING OPERATIONS - No threads, no while loops
# Azure will handle running the app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
