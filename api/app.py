#!/usr/bin/env python3
"""
Hughes Lawn AI - Azure Static Web App Version
Full system adapted for cloud deployment with DynDNS RainBird access and Cosmos DB
"""

import json
import requests
import os
import logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template_string, send_file
from flask_cors import CORS
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment variables
ECOWITT_CONFIG = {
    'url': 'https://api.ecowitt.net/api/v3/device/real_time',
    'params': {
        'application_key': os.environ.get('ECOWITT_APP_KEY', '14CF42F092D6CC8C5421160A37A0417A'),
        'api_key': os.environ.get('ECOWITT_API_KEY', 'e5f2d6ff-2323-477e-8041-6e284b401b83'),
        'mac': '34:94:54:96:22:F5',
        'call_back': 'all',
        'temp_unitid': 1,  # Celsius (we'll convert)
        'pressure_unitid': 5,  # mmHg (we'll convert)
        'wind_unitid': 7,  # km/h (we'll convert)
        'rainfall_unitid': 12,  # mm (we'll convert)
        'solar_irradiance_unitid': 16  # W/m²
    }
}

# n8n Configuration
N8N_CONFIG = {
    'webhook_url': 'https://workflows.saxtechnology.com/webhook/c5186699-f17d-42e6-a3eb-9b83d7f9d2da',
    'api_key': os.environ.get('N8N_API_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmNGM1ZDRmMy0wODlkLTQ3MDQtOWMxNy01MDY3Njc4ZjIxYzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzU2MTY3MTkyfQ.dBCr1c4ypjny1TpY7b8QvosFu0iYAVY_vVI5BzotqNE'),
    'instance_url': 'https://workflows.saxtechnology.com'
}

# RainBird configuration with Dynamic DNS
RAINBIRD_CONFIG = {
    'service_url': f"http://{os.environ.get('RAINBIRD_DNS', 'q0852082.eero.online')}:3000",
    'controller_dns': os.environ.get('RAINBIRD_DNS', 'q0852082.eero.online'),
    'controller_pin': os.environ.get('RAINBIRD_PIN', '886004'),
    'zones': {
        1: "Electric Boxes",
        2: "Front Lawn", 
        3: "Side Yard Left",
        4: "Back Yard Fence",
        5: "Back Yard Middle",
        6: "Back Yard Patio",
        7: "Side Yard HVAC Side"
    },
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

# Location Configuration for Fuquay Varina, NC 27526
LOCATION_CONFIG = {
    'city': 'Fuquay Varina',
    'state': 'NC',
    'zip': '27526',
    'zone': '7b/8a',  # USDA Hardiness Zone
    'latitude': 35.5849,
    'longitude': -78.8001,
    'grass_type': 'TifTuf Bermuda',
    'season_schedule': {
        'dormant': [11, 12, 1, 2],    # November - February
        'green_up': [3, 4],           # March - April
        'growing': [5, 6, 7, 8, 9],   # May - September
        'transition': [10]            # October
    }
}

# Zone Configuration with soil sensors
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

# Global data storage
current_data = {
    'soil_moisture': {},
    'weather': {},
    'rainbird_status': 'online',
    'mow_confidence': 75,
    'ai_analysis': '',
    'calendar_events': {},
    'forecast_data': [],
    'last_updated': None
}

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

def get_current_season():
    """Determine current season based on month"""
    month = datetime.now().month
    for season, months in LOCATION_CONFIG['season_schedule'].items():
        if month in months:
            return season
    return 'growing'  # Default

def call_rainbird_service(endpoint, method='GET', data=None):
    """Communication with RainBird service via Dynamic DNS"""
    url = f"{RAINBIRD_CONFIG['service_url']}/api/{endpoint}"
    headers = {'Content-Type': 'application/json'}
    
    try:
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=15)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=15)
        else:
            raise ValueError("Unsupported HTTP method")
        
        response.raise_for_status()
        return response.json()
        
    except requests.RequestException as e:
        logger.error(f"RainBird service error: {e}")
        return {'status': 'offline', 'error': str(e)}

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
                
                # Store weather data
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
                
                current_data['last_updated'] = datetime.now().isoformat()
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

def calculate_mowing_confidence():
    """Calculate AI-driven mowing confidence score"""
    weather = current_data.get('weather', {})
    soil_moisture = current_data.get('soil_moisture', {})
    
    confidence = 0
    factors = []
    
    # Temperature check (50-85°F optimal)
    temp = weather.get('temperature', 75)
    if 50 <= temp <= 85:
        confidence += 25
        factors.append(f"Temperature optimal ({temp}°F)")
    elif temp < 50:
        factors.append(f"Too cold ({temp}°F)")
    else:
        factors.append(f"Too hot ({temp}°F)")
    
    # Rainfall check (no rain in 24h)
    rain = weather.get('rainfall_24h', 0)
    if rain < 0.1:
        confidence += 25
        factors.append("No recent rainfall")
    else:
        factors.append(f"Recent rain ({rain}\")")
    
    # Wind check (<15 mph)
    wind = weather.get('wind_speed', 0)
    if wind < 15:
        confidence += 15
        factors.append(f"Wind acceptable ({wind} mph)")
    else:
        factors.append(f"Too windy ({wind} mph)")
    
    # Soil moisture check (not oversaturated)
    avg_moisture = sum(soil_moisture.values()) / len(soil_moisture) if soil_moisture else 35
    if 20 <= avg_moisture <= 50:
        confidence += 20
        factors.append(f"Soil moisture good ({avg_moisture:.1f}%)")
    else:
        factors.append(f"Soil moisture poor ({avg_moisture:.1f}%)")
    
    # Season check
    season = get_current_season()
    if season == 'growing':
        confidence += 15
        factors.append("Growing season")
    elif season == 'transition':
        confidence += 10
        factors.append("Transition season")
    else:
        factors.append(f"Not optimal season ({season})")
    
    current_data['mow_confidence'] = confidence
    current_data['confidence_factors'] = factors
    
    return confidence, factors

# API Routes
@app.route('/api/status')
def api_status():
    """Get comprehensive system status"""
    weather = get_ecowitt_weather()
    confidence, factors = calculate_mowing_confidence()
    
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'location': LOCATION_CONFIG,
        'weather': weather,
        'soil_moisture': current_data.get('soil_moisture', {}),
        'mowing': {
            'confidence': confidence,
            'factors': factors,
            'season': get_current_season()
        },
        'rainbird': {
            'status': 'connected',
            'dns': RAINBIRD_CONFIG['controller_dns'],
            'zones': RAINBIRD_CONFIG['zones']
        }
    })

@app.route('/api/rainbird/status')
def rainbird_status():
    """Get RainBird controller status"""
    try:
        result = call_rainbird_service('zone-status')
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/rainbird/irrigate', methods=['POST'])
def rainbird_irrigate():
    """Trigger RainBird irrigation"""
    try:
        data = request.json
        zone = data.get('zone', 1)
        duration = data.get('duration', RAINBIRD_CONFIG['default_durations'].get(zone, 15))
        
        # Call RainBird service
        result = call_rainbird_service('start-zone', 'POST', {
            'zone': zone,
            'duration': duration
        })
        
        # Log to n8n webhook if needed
        webhook_data = {
            'action': 'irrigation_triggered',
            'zone': zone,
            'duration': duration,
            'timestamp': datetime.now().isoformat(),
            'result': result
        }
        
        try:
            requests.post(N8N_CONFIG['webhook_url'], json=webhook_data, timeout=5)
        except:
            pass  # Don't fail if webhook fails
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/rainbird/stop', methods=['POST'])
def rainbird_stop():
    """Stop all RainBird irrigation"""
    try:
        result = call_rainbird_service('stop-zone', 'POST', {})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-analysis', methods=['POST'])
def ai_analysis():
    """Get AI analysis for lawn conditions"""
    try:
        data = request.json or {}
        weather = get_ecowitt_weather()
        confidence, factors = calculate_mowing_confidence()
        
        # Prepare comprehensive data for AI analysis
        analysis_data = {
            'location': LOCATION_CONFIG,
            'weather': weather,
            'soil_moisture': current_data.get('soil_moisture', {}),
            'mowing_confidence': confidence,
            'factors': factors,
            'season': get_current_season(),
            'timestamp': datetime.now().isoformat()
        }
        
        # Send to n8n for AI processing
        webhook_data = {
            'action': 'ai_analysis',
            'data': analysis_data,
            'callback_url': request.host_url.rstrip('/')
        }
        
        try:
            response = requests.post(N8N_CONFIG['webhook_url'], json=webhook_data, timeout=10)
            if response.status_code == 200:
                return jsonify(response.json())
        except Exception as e:
            logger.error(f"n8n webhook failed: {e}")
        
        # Fallback response if n8n fails
        return jsonify({
            'status': 'success',
            'confidence': confidence,
            'recommendation': 'Good to mow' if confidence >= 70 else 'Wait for better conditions',
            'factors': factors,
            'analysis_data': analysis_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/webhook', methods=['POST'])
def n8n_webhook():
    """Handle incoming n8n webhooks"""
    try:
        data = request.json
        logger.info(f"n8n webhook received: {data}")
        
        # Process the webhook data
        if data.get('action') == 'autonomous_irrigation':
            # Handle autonomous irrigation commands
            zones_to_water = data.get('zones', [])
            for zone_data in zones_to_water:
                if zone_data.get('should_water'):
                    zone = zone_data.get('zone')
                    duration = zone_data.get('duration', 15)
                    
                    # Trigger irrigation
                    call_rainbird_service('start-zone', 'POST', {
                        'zone': zone,
                        'duration': duration
                    })
        
        return jsonify({'status': 'success', 'message': 'Webhook processed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0-cloud'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
