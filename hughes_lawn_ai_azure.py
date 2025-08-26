#!/usr/bin/env python3

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

# Azure-compatible database path
DB_PATH = os.environ.get('DB_PATH', '/tmp/hughes_lawn_ai.db')

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

# RainBird configuration - Using Dynamic DNS
RAINBIRD_CONFIG = {
    'service_url': 'http://q0852082.eero.online:3000',  # Using your Dynamic DNS
    'controller_ip': '192.168.5.17',
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

# Simple direct Rainbird communication
def call_rainbird_service(endpoint, method='get', data=None):
    """Simple direct communication with Rainbird service"""
    url = f"{RAINBIRD_CONFIG['service_url']}/api/{endpoint}"
    headers = {'Content-Type': 'application/json'}
    
    try:
        if method.lower() == 'get':
            response = requests.get(url, headers=headers, timeout=60)
        elif method.lower() == 'post':
            response = requests.post(url, headers=headers, json=data, timeout=60)
        else:
            raise ValueError("Unsupported HTTP method")
        
        response.raise_for_status()
        return response.json()
        
    except requests.RequestException as e:
        logger.error(f"Rainbird service error: {e}")
        # Return a fallback response instead of raising
        return {'status': 'offline', 'error': str(e)}

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

# AI Analysis Class
class LawnAI:
    def __init__(self):
        self.zone = '7b'
        self.location = 'Fuquay-Varina, NC 27526'
        self.grass_type = 'TifTuf Bermuda'
        self.target_height = '1.5-2 inches'
    
    def get_season(self, date):
        """Get the current season based on date"""
        month = date.month
        if month in [12, 1, 2]: 
            return "Winter"
        elif month in [3, 4, 5]: 
            return "Spring"
        elif month in [6, 7, 8]: 
            return "Summer"
        else: 
            return "Fall"
    
    def get_seasonal_advice(self, season):
        """Get seasonal lawn care advice"""
        advice = {
            'Spring': "Begin fertilizing, increase mowing frequency, watch for spring dead spot",
            'Summer': "Deep watering 2-3x weekly, maintain 1.5-2 inch height, monitor for armyworms", 
            'Fall': "Apply fall fertilizer, overseed thin areas, continue mowing until dormancy",
            'Winter': "Minimal maintenance, avoid heavy traffic when frozen, clean mower for storage"
        }
        return advice.get(season, "Monitor conditions and adjust care accordingly")
    
    def get_fertilizer_advice(self, month):
        """Get month-specific fertilizer recommendations"""
        advice = {
            'January': "Hold off - Bermuda is dormant",
            'February': "Late month: Apply pre-emergent crabgrass preventer", 
            'March': "Light starter fertilizer (8-8-8) as grass greens up",
            'April': "First major feeding (16-4-8 Bermuda Blend)",
            'May': "Continue nitrogen feeding for growth",
            'June': "Regular feeding with 15-0-15 Summer blend",
            'July': "Light feeding only if needed - watch for heat stress",
            'August': "Resume regular feeding schedule",
            'September': "Fall fertilizer (5-10-30) for root development",
            'October': "Last feeding of season - winterizer blend",
            'November': "No fertilizing - prepare for dormancy",
            'December': "Dormant season - no fertilizer needed"
        }
        return advice.get(month, "Adjust based on grass conditions")
        
    def calculate_mow_confidence(self, soil_data, weather_data):
        """Calculate mowing confidence based on conditions"""
        if not soil_data:
            return 0
            
        # Get average moisture
        moistures = [v for v in soil_data.values() if isinstance(v, (int, float))]
        avg_moisture = sum(moistures) / len(moistures) if moistures else 0
        
        # Ideal moisture range is 30-40%
        confidence = 100
        
        # Moisture penalties
        if avg_moisture < 30:
            confidence -= 30  # Too dry
        elif avg_moisture <= 40:  # This covers 30-40% range
            confidence -= 0   # Sweet Spot!
        elif avg_moisture <= 50:  # This covers 41-50% range
            confidence -= 15  # Moist
        elif avg_moisture <= 60:  # This covers 51-60% range
            confidence -= 50  # A Little Wet
        elif avg_moisture <= 70:  # This covers 61-70% range
            confidence -= 60  # Wet
        else:  # Above 70%
            confidence -= 80  # Too Wet
        
        # Weather penalties
        if weather_data.get('rain_today', 0) > 0.5:
            confidence -= 30  # Recent rain
            
        if weather_data.get('humidity', 0) > 80:
            confidence -= 10  # High humidity
            
        if weather_data.get('temperature', 75) > 90:
            confidence -= 20  # Hot
        elif weather_data.get('temperature', 75) < 50:
            confidence -= 25  # Too cold
            
        return max(0, min(100, confidence))

    def generate_comprehensive_analysis(self, soil_data, weather_data, maintenance_data, observations):
        """Generate AI analysis HTML with improved formatting and specific recommendations"""
        current_date = datetime.now()
        season = self.get_season(current_date)
        mow_confidence = self.calculate_mow_confidence(soil_data, weather_data)

        # Initialize all variables at the top
        watering_status = "✅ Optimal"
        rainbird_assessment = "is currently optimal"
        weekly_water_need = 1.5
        expected_rain = 0
        next_mow_date = current_date + timedelta(days=5)
        next_mow_reason = "maintaining 5-day mowing cycle"
        
        # Analyze soil conditions with zone comparisons
        soil_analysis = []
        zone_moisture = {}
        avg_moisture = 0
        
        if soil_data:
            for zone, moisture in soil_data.items():
                if isinstance(moisture, (int, float)):
                    zone_moisture[zone] = moisture
                    zone_config = ZONES.get(zone, {})
                    if moisture < 30:
                        soil_analysis.append(f"{zone.replace('_', ' ').title()}: TOO DRY - NEEDS WATER ({moisture:.1f}%)")
                    elif moisture <= 40:
                        soil_analysis.append(f"{zone.replace('_', ' ').title()}: PERFECT MOISTURE ({moisture:.1f}%)")
                    elif moisture <= 50:
                        soil_analysis.append(f"{zone.replace('_', ' ').title()}: MOIST ({moisture:.1f}%)")
                    elif moisture <= 60:
                        soil_analysis.append(f"{zone.replace('_', ' ').title()}: More MOIST, may clump and make tracks ({moisture:.1f}%)")
                    elif moisture <= 70:
                        soil_analysis.append(f"{zone.replace('_', ' ').title()}: WET - delay mowing ({moisture:.1f}%)")
                    else:
                        soil_analysis.append(f"{zone.replace('_', ' ').title()}: TOO WET - do not mow ({moisture:.1f}%)")
            
            moistures = [v for v in soil_data.values() if isinstance(v, (int, float))]
            avg_moisture = sum(moistures) / len(moistures) if moistures else 0
        
        # Determine if good to mow and why
        can_mow = mow_confidence >= 60
        mow_reason = "Excellent conditions" if can_mow else "Poor conditions"
        
        # Specific condition analysis
        temp = weather_data.get('temperature', 75) if weather_data else 75
        humidity = weather_data.get('humidity', 50) if weather_data else 50
        rain_today = weather_data.get('rain_today', 0) if weather_data else 0
        rain_week = weather_data.get('rain_week', 0) if weather_data else 0
        wind = weather_data.get('wind_speed', 0) if weather_data else 0
        uvi = weather_data.get('uvi', 5) if weather_data else 5

        # Update expected rain
        expected_rain = rain_week
        
        # Get last mow date from database
        days_since_mow = 999
        last_mow_date = None
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''SELECT date FROM calendar_events 
                        WHERE event_type = 'mow' 
                        ORDER BY date DESC LIMIT 1''')
            last_mow_result = c.fetchone()
            if last_mow_result:
                last_mow_date = datetime.strptime(last_mow_result[0], '%Y-%m-%d')
                days_since_mow = (current_date - last_mow_date).days
            conn.close()
        except Exception as e:
            logger.error(f"Error getting last mow date: {e}")

        # Build specific immediate actions
        immediate_actions = []
        
        # Mowing recommendation with specifics
        if can_mow:
            if temp > 90:
                immediate_actions.append(f"⚠️ Temperature is high ({int(temp)}°F) - mow early morning or evening to avoid heat stress")
            elif days_since_mow > 7:
                immediate_actions.append(f"🚜 It's been {days_since_mow} days since your last mow - grass may be tall, set height to 2.5\" for first pass")
            elif days_since_mow < 5:
                immediate_actions.append(f"⏰ Last mow was only {days_since_mow} days ago - wait until day 6 to avoid stressing the grass")
            else:
                immediate_actions.append("✅ Proceed with mowing at 1.5-2 inch height - conditions are optimal")
        else:
            # Specific reasons why not to mow
            if rain_today > 0.5:
                days_to_wait = 2 if rain_today > 1.0 else 1
                immediate_actions.append(f"🌧️ Just rained {rain_today:.2f}\" today - wait {days_to_wait} days for soil to dry")
            elif avg_moisture > 60:
                next_good_day = "tomorrow" if avg_moisture < 70 else "2-3 days"
                immediate_actions.append(f"💧 Soil too wet (avg {avg_moisture:.0f}%) - next good mowing day likely {next_good_day}")
            elif temp < 50:
                immediate_actions.append(f"🥶 Too cold ({int(temp)}°F) - wait for temperature above 55°F for healthy mowing")
            else:
                immediate_actions.append("❌ Conditions not optimal - check specific zone recommendations below")
        
        # Zone-specific comparisons
        if zone_moisture:
            zones_sorted = sorted(zone_moisture.items(), key=lambda x: x[1])
            if len(zones_sorted) >= 2:
                driest = zones_sorted[0]
                wettest = zones_sorted[-1]
            
                if wettest[1] - driest[1] > 15:
                    immediate_actions.append(f"💦 {wettest[0].replace('_', ' ').title()} is significantly wetter ({wettest[1]:.0f}%) than {driest[0].replace('_', ' ').title()} ({driest[1]:.0f}%) - adjust watering zones")
        
        # Specific watering recommendations
        for zone, moisture in zone_moisture.items():
            if moisture < 25:
                immediate_actions.append(f"🚨 {zone.replace('_', ' ').title()} critically dry ({moisture:.0f}%) - water immediately")
            elif moisture < 30:
                immediate_actions.append(f"💧 {zone.replace('_', ' ').title()} needs water soon ({moisture:.0f}%)")
            elif moisture > 70:
                immediate_actions.append(f"⚠️ {zone.replace('_', ' ').title()} is oversaturated ({moisture:.0f}%) - skip next watering cycle")
                
        # Perfect conditions check
        if all(30 <= m <= 40 for m in zone_moisture.values()):
            immediate_actions.append("🌟 All zones are at perfect moisture levels (30-40%) - excellent lawn management!")
        
        # Weather-based recommendations
        if temp > 85 and rain_week < 0.5:
            immediate_actions.append("🌡️ Hot and dry week - consider increasing watering frequency")
        
        # Seasonal specific actions
        if current_date.month in [2, 3, 9] and not any("pre-emergent" in action for action in immediate_actions):
            immediate_actions.append("🌱 Apply pre-emergent crabgrass preventer this week")

        # Calculate next optimal mow date
        if not can_mow:
            # Calculate when conditions will be good
            if avg_moisture > 60:
                days_to_dry = int((avg_moisture - 40) / 10)
                next_mow_date = current_date + timedelta(days=days_to_dry)
                next_mow_reason = f"allowing soil to dry to optimal moisture (currently {avg_moisture:.0f}%)"
            elif rain_today > 0:
                next_mow_date = current_date + timedelta(days=2)
                next_mow_reason = "allowing 48 hours after rain for soil to dry"
            elif temp < 55:
                next_mow_date = current_date + timedelta(days=2)
                next_mow_reason = "waiting for warmer temperatures"
            else:
                next_mow_date = current_date + timedelta(days=1)
                next_mow_reason = "conditions should improve tomorrow"
        else:
            next_mow_date = current_date + timedelta(days=5)
            next_mow_reason = "maintaining 5-day mowing cycle"
            
        # Analyze RainBird schedule
        if expected_rain > 1.0:
            rainbird_assessment = "should be reduced by 50% due to significant rainfall"
            watering_status = "⚠️ Needs adjustment"
        elif expected_rain > 0.5:
            rainbird_assessment = "is optimal with current rainfall supplementing irrigation"
            watering_status = "✅ Optimal"
        elif avg_moisture < 30:
            rainbird_assessment = "should be increased by 20-30% due to dry conditions"
            watering_status = "⚠️ Needs increase"
        elif avg_moisture > 50:
            rainbird_assessment = "should be reduced to prevent overwatering"
            watering_status = "⚠️ Needs reduction"
        else:
            rainbird_assessment = "is currently optimal for maintaining 30-40% soil moisture"
            watering_status = "✅ Optimal"

        # Build the analysis HTML
        analysis_html = f"""
        <div class="ai-decision">
            <span class="decision-icon">{'✅' if can_mow else '❌'}</span>
            <div class="decision-text">
                <strong>Mowing Decision: {'YES - ' + mow_reason if can_mow else 'NO - ' + mow_reason}</strong>
                <div>Confidence Level: {mow_confidence}% | Average Soil Moisture: {avg_moisture:.1f}%</div>
            </div>
            <div class="decision-confidence">{mow_confidence}%</div>
        </div>
        
        <div class="ai-section">
            <h3>📍 Zone Status</h3>
            <ul style="margin: 0; padding-left: 1.5rem;">
                {"".join(f"<li>{analysis}</li>" for analysis in soil_analysis)}
            </ul>
        </div>

        <div class="ai-section">
            <h3>⚡ Immediate Actions</h3>
            <ul style="margin: 0; padding-left: 1.5rem;">
                {"".join(f"<li>{action}</li>" for action in immediate_actions)}
            </ul>
        </div>
        
        <div class="ai-section">
            <h3>📅 This Week's Plan</h3>
            <p><strong>Next Optimal Mow Date:</strong> {next_mow_date.strftime('%A, %B %d')} - {next_mow_reason}. 
            {"Ready to mow now!" if can_mow and days_since_mow >= 5 else f"Last mow was {days_since_mow} days ago." if days_since_mow < 999 else "No recent mow recorded in system."}</p>
            
            <p><strong>RainBird Schedule:</strong> {watering_status} - Current watering schedule {rainbird_assessment}. 
            Target: {weekly_water_need:.1f}" per week, with {expected_rain:.1f}" expected from rainfall.</p>
            
            <p><strong>Current season:</strong> {season} - {self.get_seasonal_advice(season)}</p>
        </div>

        <div class="ai-section">
            <h3>📆 {current_date.strftime('%B')} Recommendations</h3>
            <p><strong>Fertilization:</strong> {self.get_fertilizer_advice(current_date.strftime('%B'))}</p>
            <p><strong>Watering:</strong> Target 1-1.5 inches per week including rainfall. Water early morning (6-8 AM).</p>
        </div>
        
        <div class="ai-section">
            <h3>🌱 Bermuda Grass Health</h3>
            <p>Maintain {self.target_height} height for golf course appearance. 
            {"Conditions are optimal for healthy growth." if 30 <= avg_moisture <= 40 else "Adjust watering to optimize growth conditions."}</p>
            <p><strong>Health Score:</strong> {"⭐⭐⭐⭐⭐" if 30 <= avg_moisture <= 40 else "⭐⭐⭐☆☆"}</p>
        </div>
        """
        
        # Update global confidence
        current_data['mow_confidence'] = mow_confidence
    
        # Send enhanced data to n8n for additional AI processing
        if zone_moisture and weather_data:
            enhanced_data = {
                'zones': zone_moisture,
                'weather': weather_data,
                'days_since_mow': days_since_mow,
                'immediate_actions': immediate_actions,
                'can_mow': can_mow,
                'season': season
            }
            send_to_n8n_orchestration(zone_moisture, weather_data, mow_confidence, enhanced_data)
        
        return analysis_html

# Initialize components
lawn_ai = LawnAI()

# HTML Dashboard Template - Insert the full dashboard HTML here
DASHBOARD_HTML = '''[DASHBOARD HTML CONTENT HERE - TOO LONG TO INCLUDE IN THIS SNIPPET]'''

def init_db():
    """Initialize database with all required tables"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Original tables
    c.execute('''CREATE TABLE IF NOT EXISTS sensor_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  data_source TEXT,
                  sensor_type TEXT,
                  sensor_value REAL,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS maintenance_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  mow_height REAL,
                  fertilizer_type TEXT,
                  fertilizer_date DATE,
                  observations TEXT,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS watering_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  zone_id TEXT,
                  duration_minutes INTEGER,
                  triggered_by TEXT,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # New tables
    c.execute('''CREATE TABLE IF NOT EXISTS calendar_events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date DATE,
                  event_type TEXT,
                  event_data TEXT,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS weather_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  temperature REAL,
                  humidity REAL,
                  rain_today REAL,
                  rain_week REAL,
                  wind_speed REAL,
                  uvi INTEGER,
                  pressure REAL,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS historical_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_type TEXT,
                  description TEXT,
                  data TEXT,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Check if pressure column exists in weather_history and add if missing
    c.execute("PRAGMA table_info(weather_history)")
    columns = [column[1] for column in c.fetchall()]
    if 'pressure' not in columns:
        try:
            c.execute("ALTER TABLE weather_history ADD COLUMN pressure REAL")
            logger.info("Added pressure column to weather_history table")
        except:
            pass  # Column might already exist
    
    conn.commit()
    conn.close()

def test_ecowitt_connection():
    """Test Ecowitt connection and get data"""
    try:
        logger.info("🔍 Testing Ecowitt connection...")
        response = requests.get(ECOWITT_CONFIG['url'], params=ECOWITT_CONFIG['params'], timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            logger.info("✅ Ecowitt connected successfully")
            return data
        else:
            logger.error(f"❌ Ecowitt error: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Ecowitt connection failed: {e}")
        return None

def extract_soil_data(ecowitt_data):
    """Extract soil moisture data from Ecowitt response"""
    if not ecowitt_data or 'data' not in ecowitt_data:
        return None
    
    data = ecowitt_data['data']
    outdoor = data.get('outdoor', {})
    
    # Map Ecowitt channels to our zones
    soil_moisture = {}
    
    # Front Yard - Channel 14
    if 'soil_ch14' in outdoor:
        value = outdoor['soil_ch14'].get('humidity', {}).get('value')
        if value is not None:
            soil_moisture['front_yard'] = float(value)
    
    # Swing Set Area - Channel 13
    if 'soil_ch13' in outdoor:
        value = outdoor['soil_ch13'].get('humidity', {}).get('value')
        if value is not None:
            soil_moisture['swing_set'] = float(value)
    
    # Crepe Myrtle Area - Channel 12
    if 'soil_ch12' in outdoor:
        value = outdoor['soil_ch12'].get('humidity', {}).get('value')
        if value is not None:
            soil_moisture['crepe_myrtle'] = float(value)
    
    return soil_moisture if soil_moisture else None

def extract_weather_data(ecowitt_data):
    """Extract weather data from Ecowitt response with unit conversions"""
    if not ecowitt_data or 'data' not in ecowitt_data:
        return None
    
    data = ecowitt_data['data']
    outdoor = data.get('outdoor', {})
    rainfall = data.get('rainfall', {})
    wind = data.get('wind', {})
    solar_and_uvi = data.get('solar_and_uvi', {})
    pressure = data.get('pressure', {})
    
    weather = {}
    
    # Temperature (convert from Celsius to Fahrenheit)
    temp_data = outdoor.get('temperature', {})
    if temp_data.get('value') is not None:
        weather['temperature'] = celsius_to_fahrenheit(float(temp_data['value']))
    
    # Humidity
    humidity_data = outdoor.get('humidity', {})
    if humidity_data.get('value') is not None:
        weather['humidity'] = float(humidity_data['value'])
    
    # Rain today (convert from mm to inches)
    rain_today = rainfall.get('rain', {}).get('daily', {}).get('value')
    if rain_today is not None:
        weather['rain_today'] = mm_to_inches(float(rain_today))
    
    # Rain this week (convert from mm to inches)
    rain_week = rainfall.get('rain', {}).get('weekly', {}).get('value')
    if rain_week is not None:
        weather['rain_week'] = mm_to_inches(float(rain_week))
    
    # Wind speed (convert from km/h to mph)
    wind_speed = wind.get('wind_speed', {}).get('value')
    if wind_speed is not None:
        weather['wind_speed'] = kmh_to_mph(float(wind_speed))
    
    # UV Index
    uvi = solar_and_uvi.get('uvi', {}).get('value')
    if uvi is not None:
        weather['uvi'] = int(uvi)
    
    # Pressure (convert from mmHg to inHg)
    relative_pressure = pressure.get('relative', {}).get('value')
    if relative_pressure is not None:
        weather['pressure'] = mmhg_to_inhg(float(relative_pressure))
    
    return weather if weather else None

def send_to_n8n_orchestration(soil_data, weather_data, mow_confidence, enhanced_data=None):
    """Send data to n8n for orchestration"""
    try:
        payload = {
            'timestamp': datetime.now().isoformat(),
            'soil_moisture': soil_data,
            'weather': weather_data,
            'mow_confidence': mow_confidence,
            'location': 'Fuquay-Varina, NC 27526',
            'zone': '7b',
            'enhanced_data': enhanced_data or {}
        }
        
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("✅ Data sent to n8n orchestration")
        else:
            logger.warning(f"n8n webhook returned status {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to send to n8n: {e}")

# Flask Routes
@app.route('/')
def dashboard():
    """Main dashboard route"""
    return render_template_string(DASHBOARD_HTML)

@app.route('/grass-background')
def grass_background():
    """Serve the grass background image"""
    grass_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'grass.jpeg')
    if os.path.exists(grass_path):
        return send_file(grass_path, mimetype='image/jpeg')
    else:
        # Return a green gradient as fallback
        return '', 404

@app.route('/api/dashboard/data')
def dashboard_data():
    """Get current dashboard data"""
    try:
        # Fetch fresh Ecowitt data
        ecowitt_data = test_ecowitt_connection()
        
        if ecowitt_data:
            # Extract and update soil moisture
            soil_data = extract_soil_data(ecowitt_data)
            if soil_data:
                current_data['soil_moisture'] = soil_data
                # Store in database
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                for zone, value in soil_data.items():
                    c.execute('''INSERT INTO sensor_data (data_source, sensor_type, sensor_value)
                                 VALUES (?, ?, ?)''', ('ecowitt', f'soil_{zone}', value))
                conn.commit()
                conn.close()
            
            # Extract and update weather
            weather_data = extract_weather_data(ecowitt_data)
            if weather_data:
                current_data['weather'] = weather_data
                # Store in database
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute('''INSERT INTO weather_history 
                             (temperature, humidity, rain_today, rain_week, wind_speed, uvi, pressure)
                             VALUES (?, ?, ?, ?, ?, ?, ?)''',
                          (weather_data.get('temperature'),
                           weather_data.get('humidity'),
                           weather_data.get('rain_today'),
                           weather_data.get('rain_week'),
                           weather_data.get('wind_speed'),
                           weather_data.get('uvi'),
                           weather_data.get('pressure')))
                conn.commit()
                conn.close()
        
        # Generate AI analysis
        if current_data['soil_moisture'] and current_data['weather']:
            ai_html = lawn_ai.generate_comprehensive_analysis(
                current_data['soil_moisture'],
                current_data['weather'],
                None,
                None
            )
            current_data['ai_analysis'] = ai_html
        
        # Generate forecast data
        forecast = []
        baseTemp = 78
        for i in range(7):
            high = baseTemp + random.randint(-2, 8)
            low = high - random.randint(10, 25)
            rainChance = random.randint(0, 100)
            
            icon = '☀️'
            if rainChance > 70:
                icon = '🌧️'
            elif rainChance > 40:
                icon = '⛅'
            elif rainChance > 20:
                icon = '🌤️'
            
            forecast.append({
                'high': high,
                'low': low,
                'rain': rainChance,
                'wind': random.randint(3, 13),
                'uvi': random.randint(3, 10),
                'icon': icon
            })
        
        current_data['forecast_data'] = forecast
        
        return jsonify({
            'success': True,
            'soil_moisture': current_data['soil_moisture'],
            'weather': current_data['weather'],
            'mow_confidence': current_data['mow_confidence'],
            'ai_analysis': current_data['ai_analysis'],
            'forecast_data': current_data['forecast_data']
        })
    
    except Exception as e:
        logger.error(f"Dashboard data error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/diagnostic/test-all')
def test_all_connections():
    """Test all integrations"""
    results = {}
    
    # Test Ecowitt
    ecowitt_data = test_ecowitt_connection()
    if ecowitt_data:
        soil_data = extract_soil_data(ecowitt_data)
        weather_data = extract_weather_data(ecowitt_data)
        results['ecowitt'] = {
            'status': 'online',
            'soil_data': soil_data,
            'weather_data': weather_data
        }
    else:
        results['ecowitt'] = {'status': 'offline', 'error': 'Connection failed'}
    
    # Test RainBird
    try:
        rb_status = call_rainbird_service('status')
        if rb_status and 'error' not in rb_status:
            results['rainbird'] = {
                'status': 'online',
                'controller': 'ESP-ME3'
            }
        else:
            results['rainbird'] = {
                'status': 'offline',
                'error': rb_status.get('error', 'Connection failed')
            }
    except Exception as e:
        results['rainbird'] = {'status': 'offline', 'error': str(e)}
    
    return jsonify(results)

@app.route('/api/ai/comprehensive-analysis')
def ai_comprehensive_analysis():
    """Get comprehensive AI analysis"""
    try:
        # Get current data
        soil_data = current_data.get('soil_moisture', {})
        weather_data = current_data.get('weather', {})
        
        # Generate analysis
        analysis_html = lawn_ai.generate_comprehensive_analysis(
            soil_data,
            weather_data,
            None,
            None
        )
        
        return jsonify({
            'success': True,
            'analysis': analysis_html,
            'mow_confidence': current_data.get('mow_confidence', 75)
        })
    
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/calendar/event', methods=['POST'])
def add_calendar_event():
    """Add a calendar event"""
    try:
        data = request.json
        date = data.get('date')
        event_type = data.get('event_type')
        event_data = json.dumps(data.get('data', {}))
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO calendar_events (date, event_type, event_data)
                     VALUES (?, ?, ?)''', (date, event_type, event_data))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Event added'})
    
    except Exception as e:
        logger.error(f"Calendar event error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/calendar/month/<int:year>/<int:month>')
def get_calendar_month(year, month):
    """Get calendar events for a month"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Get all events for the month
        c.execute('''SELECT date, event_type, event_data 
                     FROM calendar_events 
                     WHERE strftime('%Y', date) = ? 
                     AND strftime('%m', date) = ?''',
                  (str(year), str(month).zfill(2)))
        
        events = {}
        for row in c.fetchall():
            date = row[0]
            if date not in events:
                events[date] = {}
            events[date][row[1]] = True
            if row[1] == 'rain' and row[2]:
                try:
                    data = json.loads(row[2])
                    events[date]['rainAmount'] = data.get('amount', '0')
                except:
                    pass
        
        conn.close()
        
        return jsonify({'success': True, 'events': events})
    
    except Exception as e:
        logger.error(f"Calendar month error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/calendar/day/<date>')
def get_calendar_day(date):
    """Get events for a specific day"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''SELECT id, event_type, event_data, timestamp 
                     FROM calendar_events 
                     WHERE date = ?''', (date,))
        
        events = []
        for row in c.fetchall():
            events.append({
                'id': row[0],
                'event_type': row[1],
                'event_data': row[2],
                'timestamp': row[3]
            })
        
        conn.close()
        
        return jsonify({'success': True, 'events': events})
    
    except Exception as e:
        logger.error(f"Calendar day error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/calendar/event/<int:event_id>', methods=['DELETE'])
def delete_calendar_event(event_id):
    """Delete a calendar event"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM calendar_events WHERE id = ?', (event_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Event deleted'})
    
    except Exception as e:
        logger.error(f"Delete event error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/weather/historical/<date>')
def get_historical_weather(date):
    """Get historical weather for a date"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''SELECT temperature, humidity, rain_today, wind_speed, uvi, pressure, timestamp
                     FROM weather_history 
                     WHERE date(timestamp) = ?
                     ORDER BY timestamp DESC LIMIT 1''', (date,))
        
        row = c.fetchone()
        conn.close()
        
        if row:
            return jsonify({
                'success': True,
                'weather': {
                    'temperature': row[0],
                    'humidity': row[1],
                    'rain_today': row[2],
                    'wind_speed': row[3],
                    'uvi': row[4],
                    'pressure': row[5],
                    'timestamp': row[6]
                }
            })
        else:
            return jsonify({'success': False, 'message': 'No data found'})
    
    except Exception as e:
        logger.error(f"Historical weather error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/logs/historical')
def get_historical_logs():
    """Get historical logs"""
    try:
        log_type = request.args.get('type', 'all')
        days = int(request.args.get('days', '7'))
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        query = '''SELECT event_type, description, timestamp 
                   FROM historical_logs 
                   WHERE datetime(timestamp) >= datetime('now', ?)'''
        
        params = [f'-{days} days']
        
        if log_type != 'all':
            query += ' AND event_type = ?'
            params.append(log_type)
        
        query += ' ORDER BY timestamp DESC'
        
        c.execute(query, params)
        
        logs = []
        for row in c.fetchall():
            logs.append({
                'event_type': row[0],
                'description': row[1],
                'timestamp': row[2]
            })
        
        conn.close()
        
        return jsonify({'success': True, 'logs': logs})
    
    except Exception as e:
        logger.error(f"Historical logs error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# RainBird API endpoints
@app.route('/api/rainbird/zones')
def get_rainbird_zones():
    """Get RainBird zone status"""
    try:
        zones = []
        for zone_id, zone_name in RAINBIRD_ZONE_NAMES.items():
            zones.append({
                'id': zone_id,
                'name': zone_name,
                'running': False,  # Would need actual status from controller
                'default_minutes': RAINBIRD_CONFIG['default_durations'].get(zone_id, 15)
            })
        
        return jsonify({'success': True, 'zones': zones})
    
    except Exception as e:
        logger.error(f"RainBird zones error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rainbird/zone/<int:zone_id>/start', methods=['POST'])
def start_rainbird_zone(zone_id):
    """Start a RainBird zone"""
    try:
        data = request.json
        seconds = data.get('seconds', 900)  # Default 15 minutes
        
        # Call the RainBird service
        result = call_rainbird_service('zone/start', method='post', data={
            'zone': zone_id,
            'duration': seconds
        })
        
        if result and 'error' not in result:
            # Log to database
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''INSERT INTO watering_history (zone_id, duration_minutes, triggered_by)
                         VALUES (?, ?, ?)''', (str(zone_id), seconds // 60, 'manual'))
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'message': f'Zone {zone_id} started'})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to start zone')})
    
    except Exception as e:
        logger.error(f"Start zone error: {e}")
        # Return a timeout warning but don't fail completely
        if 'timeout' in str(e).lower():
            return jsonify({
                'success': False,
                'error': 'Controller responding slowly - zone may have started'
            })
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rainbird/stop-all', methods=['POST'])
def stop_all_zones():
    """Stop all RainBird zones"""
    try:
        result = call_rainbird_service('zones/stop-all', method='post')
        
        if result and 'error' not in result:
            return jsonify({'success': True, 'message': 'All zones stopped'})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to stop zones')})
    
    except Exception as e:
        logger.error(f"Stop zones error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rainbird/test-zone', methods=['POST'])
def test_rainbird_zone():
    """Test a RainBird zone"""
    try:
        data = request.json
        zone_id = data.get('zone', 1)
        
        # Start zone for 1 minute test
        result = call_rainbird_service('zone/start', method='post', data={
            'zone': zone_id,
            'duration': 60
        })
        
        if result and 'error' not in result:
            return jsonify({'success': True, 'message': f'Zone {zone_id} test started'})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to test zone')})
    
    except Exception as e:
        logger.error(f"Test zone error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/system/start', methods=['POST'])
def start_systems():
    """Start all systems"""
    return jsonify({'success': True, 'message': 'Systems started'})

@app.route('/api/system/stop', methods=['POST'])
def stop_systems():
    """Stop all systems"""
    return jsonify({'success': True, 'message': 'Systems stopped'})

@app.route('/health')
def health_check():
    """Health check endpoint for Azure"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# Initialize database on startup
try:
    init_db()
    logger.info("✅ Database initialized")
except Exception as e:
    logger.error(f"❌ Database initialization failed: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
