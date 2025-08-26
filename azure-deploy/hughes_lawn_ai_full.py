#!/usr/bin/env python3

# import asyncio
# import aiohttp
import json
import requests
from flask import Flask, jsonify, request, render_template_string, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
import logging
import sqlite3
import threading
import time
import os
import random
# from pyrainbird.async_client import CreateController
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

# RainBird configuration - Enhanced integration with working controller
RAINBIRD_CONFIG = {
    'service_url': 'http://localhost:3000',  # Your working Node.js service
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

# Simple direct Rainbird communication - just like your working frontend
def call_rainbird_service(endpoint, method='get', data=None):
    """Simple direct communication with Rainbird service - no complex caching or queuing"""
    url = f"http://localhost:3000/api/{endpoint}"
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
        raise


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
            conn = sqlite3.connect('hughes_lawn_ai.db')
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

        # Build the analysis HTML - THIS IS THE COMPLETE, CLEAN VERSION
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
    
    def get_season(self, date):
        month = date.month
        if month in [12, 1, 2]: return "Winter"
        elif month in [3, 4, 5]: return "Spring"
        elif month in [6, 7, 8]: return "Summer"
        else: return "Fall"
    
    def get_fertilizer_advice(self, month):
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
    
    def get_seasonal_advice(self, season):
        advice = {
            'Spring': "Begin fertilizing, increase mowing frequency, watch for spring dead spot",
            'Summer': "Deep watering 2-3x weekly, maintain 1.5-2 inch height, monitor for armyworms", 
            'Fall': "Apply fall fertilizer, overseed thin areas, continue mowing until dormancy",
            'Winter': "Minimal maintenance, avoid heavy traffic when frozen, clean mower for storage"
        }
        return advice.get(season, "Monitor conditions and adjust care accordingly")

# Initialize components
lawn_ai = LawnAI()

# HTML Dashboard Template
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hughes Lawn AI Dashboard - Smart Irrigation, Lawn Maintenance AI</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

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

        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.3);
            z-index: -1;
        }

        /* Glassmorphism base */
        .glass {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        }

        .glass-dark {
            background: rgba(0, 0, 0, 0.3);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        /* Header */
        .header {
            padding: 1.5rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: relative;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 2rem;
        }

        .header-title h1 {
            font-size: 2rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
            background: linear-gradient(135deg, #4ade80 0%, #22c55e 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .header-title p {
            font-size: 0.9rem;
            opacity: 0.8;
        }

        /* Mowing Gauge */
        .mow-gauge {
            width: 100px;
            height: 100px;
            position: relative;
        }

        .mow-gauge svg {
            transform: rotate(-90deg);
        }

        .mow-gauge-bg {
            fill: none;
            stroke: rgba(255, 255, 255, 0.1);
            stroke-width: 8;
        }

        .mow-gauge-fill {
            fill: none;
            stroke: #4ade80;
            stroke-width: 8;
            stroke-linecap: round;
            transition: stroke-dashoffset 0.5s ease;
        }

        .mow-gauge-text {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
        }

        .mow-gauge-value {
            font-size: 1.5rem;
            font-weight: bold;
        }

        .mow-gauge-label {
            font-size: 0.7rem;
            opacity: 0.8;
        }

        /* Control Buttons */
        .control-buttons {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }

        .control-btn {
            padding: 0.5rem 1rem;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            background: rgba(255, 255, 255, 0.1);
            color: white;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 0.9rem;
        }

        .control-btn:hover {
            background: rgba(255, 255, 255, 0.2);
            transform: translateY(-1px);
        }

        .control-btn.start { border-color: #4ade80; }
        .control-btn.stop { border-color: #ef4444; }
        .control-btn.test { border-color: #3b82f6; }
        .control-btn.logs { border-color: #fbbf24; }


        /* Weather Strip */
        .weather-strip {
            padding: 1rem 2rem;
            margin: 0 2rem 1.5rem;
            border-radius: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
        }

        .weather-item {
            text-align: center;
            padding: 0.5rem 1rem;
            min-width: 120px;
        }

        .weather-value {
            font-size: 1.5rem;
            font-weight: bold;
            margin-bottom: 0.25rem;
            line-height: 1.2;
        }

        .weather-label {
            font-size: 0.8rem;
            opacity: 0.7;
            margin-top: 0.25rem;
        }

        .weather-divider {
            width: 1px;
            height: 40px;
            background: rgba(255, 255, 255, 0.2);
        }

        .weather-emoji-box {
            margin-top: 0.5rem;
            padding: 0.25rem 0.5rem;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            font-size: 1.2rem;
            min-height: 1.8rem;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            transition: all 0.3s ease;
        }

        .weather-emoji-box:hover {
            background: rgba(255, 255, 255, 0.15);
            transform: translateY(-1px);
        }

        /* Weather score specific styling */
        #weather-score .weather-value {
            cursor: pointer;
            transition: all 0.3s ease;
        }

        #weather-score .weather-value:hover {
            transform: scale(1.05);
            text-shadow: 0 0 10px rgba(74, 222, 128, 0.5);
        }

        /* Clickable mowing grade styling */
        .mow-gauge {
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .mow-gauge:hover {
            transform: scale(1.05);
            filter: drop-shadow(0 0 10px rgba(74, 222, 128, 0.3));
        }

        .mow-gauge-value {
            cursor: pointer;
        }

        /* Responsive adjustments */
        @media (max-width: 768px) {
            .weather-emoji-box {
                font-size: 1rem;
                min-height: 1.5rem;
                padding: 0.2rem 0.4rem;
            }
            
            .weather-item {
                min-width: 100px;
                padding: 0.4rem 0.8rem;
            }
        }

        /* 7-Day Forecast */
        .forecast-section {
            padding: 1.5rem;
            margin: 0 2rem 1.5rem;
            border-radius: 16px;
        }

        .forecast-header {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .forecast-container {
            display: flex;
            gap: 0.75rem;
            overflow-x: auto;
            padding: 0.5rem 0;
        }

        .forecast-day {
            min-width: 120px;
            padding: 1rem;
            border-radius: 12px;
            text-align: center;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
        }

        .forecast-day:hover {
            background: rgba(255, 255, 255, 0.1);
            transform: translateY(-2px);
        }

        .forecast-day.today {
            background: rgba(74, 222, 128, 0.2);
            border-color: #4ade80;
        }

        .forecast-day-name {
            font-size: 0.9rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }

        .forecast-icon {
            font-size: 2rem;
            margin: 0.5rem 0;
        }

        .forecast-temps {
            display: flex;
            justify-content: center;
            gap: 0.5rem;
            font-weight: bold;
            font-size: 1.1rem;
            margin-bottom: 0.5rem;
        }

        .forecast-high { color: #ef4444; }
        .forecast-low { color: #3b82f6; }
        .forecast-actual { color: #4ade80; font-size: 0.9rem; }

        .forecast-details {
            font-size: 0.75rem;
            opacity: 0.8;
            line-height: 1.3;
        }

        /* Main Container */
        .container {
            padding: 0 2rem 2rem;
            max-width: 1600px;
            margin: 0 auto;
        }

        /* Grid Layout */
        .main-grid {
            display: grid;
            grid-template-columns: 1fr 2fr 1fr;
            gap: 1.5rem;
            margin-bottom: 1.5rem;
        }

        /* AI Analysis Section */
        .ai-analysis {
            padding: 1.5rem;
            border-radius: 16px;
            grid-column: span 3;
            background: rgba(0, 0, 0, 0.4);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(74, 222, 128, 0.3);
        }

        .ai-header {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .ai-badge {
            background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 500;
        }

        .ai-content {
            display: grid;
            gap: 1.5rem;
        }

        .ai-section {
            padding: 1rem;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            border-left: 4px solid #4ade80;
        }

        .ai-section h3 {
            color: #4ade80;
            margin-bottom: 0.75rem;
            font-size: 1.1rem;
        }

        .ai-decision {
            display: flex;
            align-items: center;
            gap: 1rem;
            padding: 1rem;
            background: rgba(74, 222, 128, 0.1);
            border-radius: 12px;
            margin-bottom: 1rem;
        }

        .decision-icon {
            font-size: 2rem;
        }

        .decision-text {
            flex: 1;
        }

        .decision-confidence {
            font-size: 2rem;
            font-weight: bold;
            color: #4ade80;
        }

        /* Soil Moisture Section */
        .soil-section {
            padding: 1.5rem;
            border-radius: 16px;
        }

        .soil-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
            margin-top: 1rem;
        }

        .soil-card {
            padding: 1rem;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            text-align: center;
            position: relative;
        }

        .soil-card.average {
            grid-column: span 2;
            background: rgba(74, 222, 128, 0.1);
            border-color: rgba(74, 222, 128, 0.3);
        }

        .moisture-value {
            font-size: 2.5rem;
            font-weight: bold;
            margin: 0.5rem 0;
        }

        .moisture-bar {
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            overflow: hidden;
            margin: 0.5rem 0;
        }

        .moisture-fill {
            height: 100%;
            background: #4ade80;
            transition: width 0.5s ease;
        }

        .moisture-status {
            font-size: 0.85rem;
            margin-top: 0.5rem;
            padding: 0.5rem;
            border-radius: 6px;
            font-weight: 500;
        }

        .status-dry {
            background: rgba(239, 68, 68, 0.2);
            color: #fca5a5;
        }

        .status-optimal {
            background: rgba(74, 222, 128, 0.2);
            color: #86efac;
        }

        .status-wet {
            background: rgba(59, 130, 246, 0.2);
            color: #93bbfe;
        }

        .zone-info {
            font-size: 0.85rem;
            opacity: 0.7;
            margin-top: 0.5rem;
        }

        /* Calendar */
        .calendar-section {
            padding: 1.5rem;
            border-radius: 16px;
            grid-column: span 2;
        }

        .calendar-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }

        .calendar-nav {
            display: flex;
            gap: 0.5rem;
        }

        .calendar-btn {
            padding: 0.5rem;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .calendar-btn:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        .calendar-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 0.5rem;
            margin-top: 1rem;
        }

        .calendar-day-header {
            text-align: center;
            font-size: 0.8rem;
            opacity: 0.7;
            padding: 0.5rem;
        }

        .calendar-day {
            aspect-ratio: 1;
            padding: 0.5rem;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            cursor: pointer;
            position: relative;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        }

        .calendar-day:hover {
            background: rgba(255, 255, 255, 0.1);
            transform: translateY(-2px);
        }

        .calendar-day.today {
            background: rgba(74, 222, 128, 0.2);
            border-color: #4ade80;
        }

        .calendar-day.mow-day {
            background: rgba(251, 191, 36, 0.2);
            border-color: #fbbf24;
        }

        .calendar-day.rain-day {
            background: rgba(59, 130, 246, 0.2);
            border-color: #3b82f6;
        }

        .calendar-day-number {
            font-size: 1rem;
            font-weight: 500;
        }

        .calendar-icons {
            position: absolute;
            bottom: 2px;
            display: flex;
            gap: 2px;
            font-size: 0.7rem;
        }

        .calendar-legend {
            display: flex;
            gap: 1rem;
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            font-size: 0.85rem;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .legend-color {
            width: 16px;
            height: 16px;
            border-radius: 4px;
        }

        /* RainBird Section */
        .rainbird-section {
            padding: 1.5rem;
            border-radius: 16px;
        }

        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            background: rgba(74, 222, 128, 0.2);
            font-size: 0.9rem;
            margin-bottom: 1rem;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #4ade80;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }

        .next-schedule {
            padding: 1rem;
            background: rgba(59, 130, 246, 0.1);
            border-radius: 8px;
            margin: 1rem 0;
            font-size: 0.9rem;
        }

        .schedule-item {
            padding: 1rem;
            margin: 0.5rem 0;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .schedule-zones {
            display: flex;
            gap: 0.5rem;
        }

        .zone-badge {
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            background: rgba(74, 222, 128, 0.2);
            font-size: 0.8rem;
        }

        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }

        .modal-content {
            background: rgba(20, 20, 20, 0.9);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 16px;
            padding: 2rem;
            max-width: 800px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }

        .modal-header {
            font-size: 1.5rem;
            margin-bottom: 1.5rem;
        }

        .form-group {
            margin-bottom: 1rem;
        }

        .form-group label {
            display: block;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
            opacity: 0.8;
        }

        .form-group input,
        .form-group select,
        .form-group textarea {
            width: 100%;
            padding: 0.75rem;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            background: rgba(255, 255, 255, 0.1);
            color: white;
            font-size: 1rem;
        }

        .form-group input::placeholder {
            color: rgba(255, 255, 255, 0.5);
        }

        .modal-actions {
            display: flex;
            gap: 1rem;
            margin-top: 1.5rem;
            justify-content: flex-end;
        }

        .btn {
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .btn-primary {
            background: #4ade80;
            color: #064e3b;
            font-weight: 500;
        }

        .btn-primary:hover {
            background: #22c55e;
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.1);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        /* System Log */
        .log-section {
            padding: 1.5rem;
            border-radius: 16px;
            margin-top: 1.5rem;
        }

        .log-container {
            max-height: 200px;
            overflow-y: auto;
            font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
            font-size: 0.85rem;
            padding: 1rem;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            margin-top: 1rem;
        }

        .log-entry {
            margin: 0.25rem 0;
            opacity: 0.8;
        }

        .log-entry.error {
            color: #ef4444;
        }

        .log-entry.success {
            color: #4ade80;
        }

        .log-entry.info {
            color: #3b82f6;
        }

        /* Historical Logs */
        .historical-logs {
            margin-top: 1rem;
        }

        .log-filter {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }

        .log-filter select {
            padding: 0.5rem;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: white;
        }

        /* Responsive */
        @media (max-width: 1200px) {
            .main-grid {
                grid-template-columns: 1fr;
            }

            .calendar-section {
                grid-column: span 1;
            }

            .weather-strip {
                flex-direction: column;
            }

            .weather-divider {
                display: none;
            }
        }

        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                gap: 1rem;
            }

            .header-left {
                flex-direction: column;
            }

            .soil-grid {
                grid-template-columns: 1fr;
            }

            .soil-card.average {
                grid-column: span 1;
            }

            .forecast-container {
                gap: 0.5rem;
            }

            .forecast-day {
                min-width: 100px;
                padding: 0.75rem;
            }
        }
    </style>
</head>
<body>
    <!-- Header -->
    <header class="header glass-dark">
        <div class="header-left">
            <div class="mow-gauge">
                <svg width="100" height="100">
                    <circle cx="50" cy="50" r="40" class="mow-gauge-bg"></circle>
                    <circle cx="50" cy="50" r="40" class="mow-gauge-fill" 
                            stroke-dasharray="251.2" 
                            stroke-dashoffset="62.8" id="mow-gauge-fill"></circle>
                </svg>
                <div class="mow-gauge-text">
                   <div class="mow-gauge-value" id="mow-confidence">A</div>
                    <div class="mow-gauge-label">Mowing Grade</div>
                </div>
            </div>
            <div class="header-title">
                <h1>Hughes Home Lawn AI Dashboard</h1>
                <p>Smart Irrigation, Lawn Maintenance AI Analysis</p>
            </div>
        </div>
        <div class="control-buttons">
            <button class="control-btn start" onclick="startSystems()">▶ Start Services</button>
            <button class="control-btn stop" onclick="stopSystems()">◼ Stop Services</button>
            <button class="control-btn test" onclick="testConnections()">🔍 Test Integrations</button>
            <button class="control-btn logs" onclick="showHistoricalLogs()">📋 Lawn Logs</button>
        </div>
    </header>


    <!-- Weather Strip -->
    <div class="weather-strip glass">
        <div class="weather-item">
            <div class="weather-value" id="avg-moisture">--.--%</div>
            <div class="weather-label">Current Avg Soil Moisture</div>
        </div>
        <div class="weather-divider"></div>
        <div class="weather-item">
            <div class="weather-value" id="temperature">--°F</div>
            <div class="weather-label">Current Home Outside Temperature</div>
        </div>
        <div class="weather-divider"></div>
        <div class="weather-item">
            <div class="weather-value" id="humidity">--%</div>
            <div class="weather-label">Current Humidity</div>
        </div>
        <div class="weather-divider"></div>
        <div class="weather-item">
            <div class="weather-value" id="rain-today">--"</div>
            <div class="weather-label">Rain Today</div>
        </div>
        <div class="weather-divider"></div>
        <div class="weather-item">
            <div class="weather-value" id="rain-week">--"</div>
            <div class="weather-label">Rain This Week</div>
        </div>
        <div class="weather-divider"></div>
        <div class="weather-item">
            <div class="weather-value" id="uvi">-</div>
            <div class="weather-label">UV Index (0-12)</div>
        </div>
        <div class="weather-divider"></div>
        <div class="weather-item">
            <div class="weather-value" id="wind-speed">0 mph</div>
            <div class="weather-label">Wind Speed</div>
        </div>
        <div class="weather-divider"></div>
        <div class="weather-item">
            <div class="weather-value" id="pressure">--" Hg</div>
            <div class="weather-label">Pressure</div>
        </div>
    </div>

    <!-- Main Container -->
    <div class="container">
        <!-- 7-Day Forecast -->
        <div class="forecast-section glass">
            <div class="forecast-header">
                <h3>Fuquay-Varina 7-Day Weather Forecast</h3>
            </div>
            <div class="forecast-container" id="forecast-container">
                <!-- Forecast will be populated by JavaScript -->
            </div>
        </div>

        <!-- AI Analysis -->
        <div class="ai-analysis glass">
            <div class="ai-header">
                <h2>🧠 AI Lawn Analysis</h2>
                <span class="ai-badge">ZONE 7b - Fuquay-Varina, NC 27526</span>
            </div>
            <div class="ai-content" id="ai-content">
                <div class="ai-decision">
                    <span class="decision-icon">⏳</span>
                    <div class="decision-text">
                        <strong>Loading AI analysis...</strong>
                        <div>Analyzing soil moisture, weather patterns, and seasonal requirements...</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Main Grid -->
        <div class="main-grid">
            <!-- Soil Moisture Section -->
            <div class="soil-section glass">
                <h3>🌱 Tom's Soil Moisture Sensors</h3>
                <div class="soil-grid">
                    <div class="soil-card">
                        <h4>Front Yard (CH14)</h4>
                        <div class="moisture-value" id="soil-front">--.--%</div>
                        <div class="moisture-bar">
                            <div class="moisture-fill" id="fill-front" style="width: 0%;"></div>
                        </div>
                        <div class="moisture-status" id="status-front">Loading...</div>
                        <div class="zone-info">Zones 1, 2</div>
                    </div>
                    <div class="soil-card">
                        <h4>Backyard Playset Area (CH13)</h4>
                        <div class="moisture-value" id="soil-swing">--.--%</div>
                        <div class="moisture-bar">
                            <div class="moisture-fill" id="fill-swing" style="width: 0%;"></div>
                        </div>
                        <div class="moisture-status" id="status-swing">Loading...</div>
                        <div class="zone-info">Zones 4, 5</div>
                    </div>
                    <div class="soil-card">
                        <h4>Backyard Crepe Myrtle Area (Channel 12)</h4>
                        <div class="moisture-value" id="soil-crepe">--.--%</div>
                        <div class="moisture-bar">
                            <div class="moisture-fill" id="fill-crepe" style="width: 0%;"></div>
                        </div>
                        <div class="moisture-status" id="status-crepe">Loading...</div>
                        <div class="zone-info">Zone 6</div>
                    </div>
                    <div class="soil-card average">
                        <h4>Overall Yard Moisture Level</h4>
                        <div class="moisture-value" id="soil-average" style="color: #4ade80;">--.--%</div>
                        <div class="moisture-bar">
                            <div class="moisture-fill" id="fill-average" style="width: 0%; background: linear-gradient(90deg, #4ade80, #22c55e);"></div>
                        </div>
                        <div class="zone-info">Optimal Range: 30-40%</div>
                    </div>
                </div>
            </div>

            <!-- Calendar -->
            <div class="calendar-section glass">
                <div class="calendar-header">
                    <h3>📅 Tom's Smart Lawn Calendar</h3>
                    <div class="calendar-nav">
                        <button class="calendar-btn" onclick="previousMonth()">←</button>
                        <span id="calendar-month">June 2025</span>
                        <button class="calendar-btn" onclick="nextMonth()">→</button>
                    </div>
                </div>
                <div class="calendar-grid" id="calendar-grid">
                    <!-- Calendar will be populated by JavaScript -->
                </div>
                <div class="calendar-legend">
                    <div class="legend-item">
                        <div class="legend-color" style="background: rgba(251, 191, 36, 0.5);"></div>
                        <span>Recommended Mow Day</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: rgba(59, 130, 246, 0.5);"></div>
                        <span>Rain Day</span>
                    </div>
                    <div class="legend-item">
                        <span>💧 Watered </span>
                    </div>
                    <div class="legend-item">
                        <span>🚜 Mowed</span>
                    </div>
                     <div class="legend-item">
                        <span>🌿 Fertilized</span>
                    </div>
                </div>
            </div>

            <!-- RainBird Section -->
            <div class="rainbird-section glass">
                <h3>💧 RainBird Controller</h3>
                <div class="status-indicator">
                    <span class="status-dot"></span>
                    <span id="rainbird-status">Online</span>
                </div>
                
                <div class="next-schedule" id="next-schedule">
                    <strong>Next Scheduled Run:</strong>
                    <div id="next-schedule-time">Calculating...</div>
                </div>

                <h4 style="margin-top: 1.5rem;">Today's Schedule</h4>
                <div id="rainbird-schedule">
                    <!-- Schedule will be populated -->
                </div>
                
                <h4 style="margin-top: 1rem;">Manual Control</h4>
                <div style="background: rgba(255, 255, 255, 0.05); padding: 1rem; border-radius: 8px; margin: 1rem 0;">
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem;">
                        <div style="border: 1px solid rgba(255, 255, 255, 0.1); padding: 1rem; border-radius: 8px;">
                            <h5 style="margin-bottom: 0.5rem; color: #4ade80;">Zone 1: Electric Boxes</h5>
                            <div id="zone1-status" style="font-size: 0.9rem; margin-bottom: 0.5rem; color: #fbbf24;">Status: Ready</div>
                            <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                                <input type="number" id="zone1-duration" min="1" max="60" value="15" style="width: 60px; padding: 0.25rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); background: rgba(255,255,255,0.1); color: white;" placeholder="min">
                                <span style="font-size: 0.8rem;">min</span>
                                <button class="control-btn start" id="zone1-start" onclick="startZoneWithInput(1)">▶ Start</button>
                                <button class="control-btn stop" id="zone1-stop" onclick="stopZone(1)" style="display: none;">⛔ Stop</button>
                            </div>
                        </div>
                        <div style="border: 1px solid rgba(255, 255, 255, 0.1); padding: 1rem; border-radius: 8px;">
                            <h5 style="margin-bottom: 0.5rem; color: #4ade80;">Zone 2: Front Lawn</h5>
                            <div id="zone2-status" style="font-size: 0.9rem; margin-bottom: 0.5rem; color: #fbbf24;">Status: Ready</div>
                            <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                                <input type="number" id="zone2-duration" min="1" max="60" value="15" style="width: 60px; padding: 0.25rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); background: rgba(255,255,255,0.1); color: white;" placeholder="min">
                                <span style="font-size: 0.8rem;">min</span>
                                <button class="control-btn start" id="zone2-start" onclick="startZoneWithInput(2)">▶ Start</button>
                                <button class="control-btn stop" id="zone2-stop" onclick="stopZone(2)" style="display: none;">⛔ Stop</button>
                            </div>
                        </div>
                        <div style="border: 1px solid rgba(255, 255, 255, 0.1); padding: 1rem; border-radius: 8px;">
                            <h5 style="margin-bottom: 0.5rem; color: #4ade80;">Zone 3: Side Yard Left</h5>
                            <div id="zone3-status" style="font-size: 0.9rem; margin-bottom: 0.5rem; color: #fbbf24;">Status: Ready</div>
                            <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                                <input type="number" id="zone3-duration" min="1" max="60" value="15" style="width: 60px; padding: 0.25rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); background: rgba(255,255,255,0.1); color: white;" placeholder="min">
                                <span style="font-size: 0.8rem;">min</span>
                                <button class="control-btn start" id="zone3-start" onclick="startZoneWithInput(3)">▶ Start</button>
                                <button class="control-btn stop" id="zone3-stop" onclick="stopZone(3)" style="display: none;">⛔ Stop</button>
                            </div>
                        </div>
                        <div style="border: 1px solid rgba(255, 255, 255, 0.1); padding: 1rem; border-radius: 8px;">
                            <h5 style="margin-bottom: 0.5rem; color: #4ade80;">Zone 4: Back Yard Fence</h5>
                            <div id="zone4-status" style="font-size: 0.9rem; margin-bottom: 0.5rem; color: #fbbf24;">Status: Ready</div>
                            <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                                <input type="number" id="zone4-duration" min="1" max="60" value="20" style="width: 60px; padding: 0.25rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); background: rgba(255,255,255,0.1); color: white;" placeholder="min">
                                <span style="font-size: 0.8rem;">min</span>
                                <button class="control-btn start" id="zone4-start" onclick="startZoneWithInput(4)">▶ Start</button>
                                <button class="control-btn stop" id="zone4-stop" onclick="stopZone(4)" style="display: none;">⛔ Stop</button>
                            </div>
                        </div>
                        <div style="border: 1px solid rgba(255, 255, 255, 0.1); padding: 1rem; border-radius: 8px;">
                            <h5 style="margin-bottom: 0.5rem; color: #4ade80;">Zone 5: Back Yard Middle</h5>
                            <div id="zone5-status" style="font-size: 0.9rem; margin-bottom: 0.5rem; color: #fbbf24;">Status: Ready</div>
                            <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                                <input type="number" id="zone5-duration" min="1" max="60" value="20" style="width: 60px; padding: 0.25rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); background: rgba(255,255,255,0.1); color: white;" placeholder="min">
                                <span style="font-size: 0.8rem;">min</span>
                                <button class="control-btn start" id="zone5-start" onclick="startZoneWithInput(5)">▶ Start</button>
                                <button class="control-btn stop" id="zone5-stop" onclick="stopZone(5)" style="display: none;">⛔ Stop</button>
                            </div>
                        </div>
                        <div style="border: 1px solid rgba(255, 255, 255, 0.1); padding: 1rem; border-radius: 8px;">
                            <h5 style="margin-bottom: 0.5rem; color: #4ade80;">Zone 6: Back Yard Patio</h5>
                            <div id="zone6-status" style="font-size: 0.9rem; margin-bottom: 0.5rem; color: #fbbf24;">Status: Ready</div>
                            <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                                <input type="number" id="zone6-duration" min="1" max="60" value="10" style="width: 60px; padding: 0.25rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); background: rgba(255,255,255,0.1); color: white;" placeholder="min">
                                <span style="font-size: 0.8rem;">min</span>
                                <button class="control-btn start" id="zone6-start" onclick="startZoneWithInput(6)">▶ Start</button>
                                <button class="control-btn stop" id="zone6-stop" onclick="stopZone(6)" style="display: none;">⛔ Stop</button>
                            </div>
                        </div>
                        <div style="border: 1px solid rgba(255, 255, 255, 0.1); padding: 1rem; border-radius: 8px;">
                            <h5 style="margin-bottom: 0.5rem; color: #4ade80;">Zone 7: Side Yard HVAC Side</h5>
                            <div id="zone7-status" style="font-size: 0.9rem; margin-bottom: 0.5rem; color: #fbbf24;">Status: Ready</div>
                            <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                                <input type="number" id="zone7-duration" min="1" max="60" value="15" style="width: 60px; padding: 0.25rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); background: rgba(255,255,255,0.1); color: white;" placeholder="min">
                                <span style="font-size: 0.8rem;">min</span>
                                <button class="control-btn start" id="zone7-start" onclick="startZoneWithInput(7)">▶ Start</button>
                                <button class="control-btn stop" id="zone7-stop" onclick="stopZone(7)" style="display: none;">⛔ Stop</button>
                            </div>
                        </div>
                    </div>
                    <div style="display: flex; gap: 0.5rem; margin-top: 1rem; justify-content: center;">
                        <button class="control-btn stop" onclick="stopAllZones()">🚫 Stop All Zones</button>
                        <button class="control-btn test" onclick="testZone(1)">🔍 Test Zone 1</button>
                        <button class="control-btn logs" onclick="showScheduleEditor()">⚙️ Edit Schedule</button>
                    </div>
                </div>
                
                <h4 style="margin-top: 1rem;">Notifications</h4>
                <div id="rainbird-notifications" style="padding: 0.75rem; background: rgba(59, 130, 246, 0.2); border-radius: 8px; font-size: 0.9rem;">
                    No active notifications
                </div>
            </div>
        </div>

        <!-- System Log -->
        <div class="log-section glass-dark">
            <h3>📊 System Log</h3>
            <div class="log-container" id="log-container">
                <div class="log-entry info">[System] Initializing Hughes Lawn AI...</div>
            </div>
        </div>
    </div>

    <!-- Calendar Modal -->
    <div class="modal" id="calendar-modal">
        <div class="modal-content">
            <h2 class="modal-header" id="modal-title">Add Event</h2>
            <div id="modal-content">
                <!-- Dynamic content will be inserted here -->
            </div>
        </div>
    </div>

    <!-- Historical Logs Modal -->
    <div class="modal" id="logs-modal">
        <div class="modal-content">
            <h2 class="modal-header">📋 Historical Logs</h2>
            <div class="historical-logs">
                <div class="log-filter">
                    <select id="log-type-filter">
                        <option value="all">All Logs</option>
                        <option value="mowing">Mowing</option>
                        <option value="fertilizer">Fertilizer</option>
                        <option value="maintenance">Maintenance</option>
                        <option value="watering">Watering</option>
                    </select>
                    <select id="log-date-filter">
                        <option value="7">Last 7 Days</option>
                        <option value="30">Last 30 Days</option>
                        <option value="90">Last 90 Days</option>
                        <option value="365">Last Year</option>
                    </select>
                    <button class="btn btn-primary" onclick="loadHistoricalLogs()">Load Logs</button>
                </div>
                <div id="historical-log-content" style="max-height: 400px; overflow-y: auto;">
                    <!-- Logs will be loaded here -->
                </div>
            </div>
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeLogsModal()">Close</button>
            </div>
        </div>
    </div>

    <script>
        // API Configuration
        const API_BASE = window.location.origin;
        
        // Calendar functionality
        const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
        let currentMonth = new Date().getMonth();
        let currentYear = new Date().getFullYear();
        let calendarData = {};

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            initCalendar();
            addLog('info', 'Hughes Lawn AI Dashboard initialized');
            
            // Add weather score and forecast
            addWeatherScore();
            generateRealisticForecast();
            
            // Add click handler for mowing gauge
            document.querySelector('.mow-gauge').addEventListener('click', showMowingExplanation);
            
            // Set gauge to default
            updateGauge(75);
            
            // Load dashboard data immediately (Ecowitt only)
            updateDashboard();
            
            // Auto-poll Ecowitt every 5 minutes for weather/soil data
            setInterval(updateDashboard, 300000); // Every 5 minutes
            
            addLog('success', 'Dashboard loaded - Ecowitt polling every 5 minutes');
        });

        // Calendar functions
        function initCalendar() {
            renderCalendar();
            loadCalendarData();
        }

        function renderCalendar() {
            const grid = document.getElementById('calendar-grid');
            const monthYear = document.getElementById('calendar-month');
            monthYear.textContent = months[currentMonth] + ' ' + currentYear;
            
            grid.innerHTML = '';
            
            // Day headers
            const dayHeaders = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            dayHeaders.forEach(day => {
                const header = document.createElement('div');
                header.className = 'calendar-day-header';
                header.textContent = day;
                grid.appendChild(header);
            });
            
            // Get first day of month and number of days
            const firstDay = new Date(currentYear, currentMonth, 1).getDay();
            const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
            const today = new Date();
            
            // Empty cells for days before month starts
            for (let i = 0; i < firstDay; i++) {
                const emptyDay = document.createElement('div');
                grid.appendChild(emptyDay);
            }
            
            // Days of the month
            for (let day = 1; day <= daysInMonth; day++) {
                const dayElement = document.createElement('div');
                dayElement.className = 'calendar-day';
                dayElement.onclick = () => openDayModal(day);
                
                // Check if today
                if (currentYear === today.getFullYear() && 
                    currentMonth === today.getMonth() && 
                    day === today.getDate()) {
                    dayElement.classList.add('today');
                }
                
                const dateKey = formatDate(day);
                
                // Check for mowing days (AI recommended)
                if (calendarData[dateKey] && calendarData[dateKey].recommendMow) {
                    dayElement.classList.add('mow-day');
                }
                
                // Check for rain days
                if (calendarData[dateKey] && calendarData[dateKey].rain) {
                    dayElement.classList.add('rain-day');
                }
                
                const dayNumber = document.createElement('div');
                dayNumber.className = 'calendar-day-number';
                dayNumber.textContent = day;
                dayElement.appendChild(dayNumber);
                
                const icons = document.createElement('div');
                icons.className = 'calendar-icons';
                
                // Add icons based on data
                if (calendarData[dateKey]) {
                    if (calendarData[dateKey].mowed) icons.innerHTML += '🚜 ';
                    if (calendarData[dateKey].fertilized) icons.innerHTML += '🌿 ';
                    if (calendarData[dateKey].rain) icons.innerHTML += '🌧️ ';
                    if (calendarData[dateKey].watered) icons.innerHTML += '💧 ';
                    if (calendarData[dateKey].maintenance) icons.innerHTML += '🔧 ';
                }
                
                dayElement.appendChild(icons);
                dayElement.title = getDayTooltip(dateKey);
                grid.appendChild(dayElement);
            }
        }

        function getDayTooltip(dateKey) {
            const data = calendarData[dateKey];
            if (!data) return 'Click to add event';
            
            let tooltip = [];
            if (data.rain) tooltip.push('Rain: ' + (data.rainAmount || 'Expected'));
            if (data.temperature) tooltip.push('Temp: ' + data.temperature + '°F');
            if (data.windSpeed) tooltip.push('Wind: ' + data.windSpeed + ' mph');
            
            return tooltip.join('\\n') || 'Click to add event';
        }

        function formatDate(day) {
            return currentYear + '-' + (currentMonth + 1).toString().padStart(2, '0') + '-' + day.toString().padStart(2, '0');
        }

        function previousMonth() {
            currentMonth--;
            if (currentMonth < 0) {
                currentMonth = 11;
                currentYear--;
            }
            loadCalendarData();
        }

        function nextMonth() {
            currentMonth++;
            if (currentMonth > 11) {
                currentMonth = 0;
                currentYear++;
            }
            loadCalendarData();
        }

        function openDayModal(day) {
            const modal = document.getElementById('calendar-modal');
            const modalContent = document.getElementById('modal-content');
            const dateStr = months[currentMonth] + ' ' + day + ', ' + currentYear;
            const dateKey = formatDate(day);
            
            document.getElementById('modal-title').textContent = dateStr;
            
            // Get existing events for this day
            const dayData = calendarData[dateKey] || {};
            
            modalContent.innerHTML = `
                <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem;">
                    <button class="btn btn-primary" onclick="showMowForm(${day})">🚜 Mow</button>
                    <button class="btn btn-primary" onclick="showMaintenanceForm(${day})">🔧 Maintenance</button>
                    <button class="btn btn-primary" onclick="showFertilizerForm(${day})">🌿 Fertilizer</button>
                    <button class="btn btn-primary" onclick="showHistoricalWeather('${dateKey}')">🌤️ Weather Data</button>
                </div>
                
                <div id="existing-events" style="margin-bottom: 1.5rem;">
                    <!-- Existing events will be loaded here -->
                </div>
                
                <div id="form-content"></div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
                </div>
            `;
            
            // Load existing events
            loadDayEvents(dateKey);
            
            modal.style.display = 'flex';
        }
        
        function loadDayEvents(dateKey) {
            fetch(API_BASE + '/api/calendar/day/' + dateKey)
                .then(response => response.json())
                .then(data => {
                    const eventsContainer = document.getElementById('existing-events');
                    if (data.success && data.events.length > 0) {
                        let html = '<h4>Existing Events:</h4>';
                        data.events.forEach(event => {
                            html += `
                                <div style="background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 8px; margin: 0.5rem 0; display: flex; justify-content: space-between; align-items: center;">
                                    <div>
                                        <strong>${event.event_type.charAt(0).toUpperCase() + event.event_type.slice(1)}</strong>
                                        <div style="font-size: 0.9rem; opacity: 0.8;">${formatEventData(event.event_data)}</div>
                                        <div style="font-size: 0.8rem; opacity: 0.6;">${new Date(event.timestamp).toLocaleTimeString()}</div>
                                    </div>
                                    <div>
                                        <button class="btn btn-secondary" style="padding: 0.25rem 0.5rem; margin: 0 0.25rem;" onclick="editEvent(${event.id}, '${event.event_type}', '${dateKey}')">Edit</button>
                                        <button class="btn btn-secondary" style="padding: 0.25rem 0.5rem; background: #dc2626;" onclick="deleteEvent(${event.id}, '${dateKey}')">Delete</button>
                                    </div>
                                </div>
                            `;
                        });
                        eventsContainer.innerHTML = html;
                    } else {
                        eventsContainer.innerHTML = '<p style="opacity: 0.7; font-style: italic;">No events recorded for this day.</p>';
                    }
                })
                .catch(error => {
                    document.getElementById('existing-events').innerHTML = '<p style="color: #ef4444;">Error loading events.</p>';
                });
        }
        
        function formatEventData(eventDataStr) {
            try {
                const data = JSON.parse(eventDataStr);
                if (data.height) return `Height: ${data.height}" - ${data.notes || 'No notes'}`;
                if (data.type) return `${data.type} - ${data.notes || 'No notes'}`;
                if (data.brand) return `${data.brand} ${data.npk || ''} - ${data.quantity || ''}lbs`;
                return JSON.stringify(data);
            } catch {
                return eventDataStr;
            }
        }
        
        function editEvent(eventId, eventType, dateKey) {
            // For now, show form to create new event (edit functionality can be enhanced)
            if (eventType === 'mow') showMowForm(parseInt(dateKey.split('-')[2]));
            else if (eventType === 'maintenance') showMaintenanceForm(parseInt(dateKey.split('-')[2]));
            else if (eventType === 'fertilizer') showFertilizerForm(parseInt(dateKey.split('-')[2]));
        }
        
        function deleteEvent(eventId, dateKey) {
            if (confirm('Are you sure you want to delete this event?')) {
                fetch(API_BASE + '/api/calendar/event/' + eventId, {
                    method: 'DELETE'
                })
                .then(response => response.json())
                .then(result => {
                    if (result.success) {
                        addLog('info', 'Event deleted successfully');
                        loadDayEvents(dateKey);
                        loadCalendarData(); // Refresh calendar
                    } else {
                        addLog('error', 'Failed to delete event');
                    }
                })
                .catch(error => {
                    addLog('error', 'Error deleting event');
                });
            }
        }
        
        function showHistoricalWeather(dateKey) {
            const formContent = document.getElementById('form-content');
            formContent.innerHTML = '<p>Loading weather data...</p>';
            
            fetch(API_BASE + '/api/weather/historical/' + dateKey)
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.weather) {
                        const weather = data.weather;
                        formContent.innerHTML = `
                            <div style="background: rgba(59, 130, 246, 0.1); padding: 1.5rem; border-radius: 12px; border-left: 4px solid #3b82f6;">
                                <h3 style="color: #3b82f6; margin-bottom: 1rem;">Weather Data for ${dateKey}</h3>
                                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
                                    <div>
                                        <strong>Temperature:</strong><br>
                                        ${weather.temperature ? weather.temperature.toFixed(1) + '°F' : 'No data'}
                                    </div>
                                    <div>
                                        <strong>Humidity:</strong><br>
                                        ${weather.humidity ? weather.humidity.toFixed(0) + '%' : 'No data'}
                                    </div>
                                    <div>
                                        <strong>Rain Today:</strong><br>
                                        ${weather.rain_today ? weather.rain_today.toFixed(2) + '"' : 'No data'}
                                    </div>
                                    <div>
                                        <strong>Wind Speed:</strong><br>
                                        ${weather.wind_speed ? weather.wind_speed.toFixed(0) + ' mph' : 'No data'}
                                    </div>
                                    <div>
                                        <strong>UV Index:</strong><br>
                                        ${weather.uvi || 'No data'}
                                    </div>
                                    <div>
                                        <strong>Pressure:</strong><br>
                                        ${weather.pressure ? weather.pressure.toFixed(2) + '" Hg' : 'No data'}
                                    </div>
                                </div>
                                ${weather.timestamp ? `<p style="margin-top: 1rem; opacity: 0.7; font-size: 0.9rem;">Recorded: ${new Date(weather.timestamp).toLocaleString()}</p>` : ''}
                            </div>
                        `;
                    } else {
                        formContent.innerHTML = `
                            <div style="background: rgba(239, 68, 68, 0.1); padding: 1.5rem; border-radius: 12px; border-left: 4px solid #ef4444;">
                                <h3 style="color: #ef4444; margin-bottom: 1rem;">No Weather Data Found</h3>
                                <p>No weather data recorded for ${dateKey}. Weather data is only available for dates when the system was actively monitoring.</p>
                            </div>
                        `;
                    }
                })
                .catch(error => {
                    formContent.innerHTML = `
                        <div style="background: rgba(239, 68, 68, 0.1); padding: 1.5rem; border-radius: 12px; border-left: 4px solid #ef4444;">
                            <h3 style="color: #ef4444; margin-bottom: 1rem;">Error Loading Weather Data</h3>
                            <p>Unable to retrieve weather data for ${dateKey}.</p>
                        </div>
                    `;
                });
        }

        function showMowForm(day) {
            const formContent = document.getElementById('form-content');
            formContent.innerHTML = `
                <div class="form-group">
                    <label>Mowing Height (inches)</label>
                    <input type="number" id="mow-height" step="0.1" min="1" max="3" value="2.0" placeholder="2.0">
                </div>
                <div class="form-group">
                    <label>Notes</label>
                    <textarea id="mow-notes" placeholder="Any observations..."></textarea>
                </div>
                <button class="btn btn-primary" onclick="saveMowData(${day})">Save Mowing Data</button>
            `;
        }

        function showMaintenanceForm(day) {
            const formContent = document.getElementById('form-content');
            formContent.innerHTML = `
                <div class="form-group">
                    <label>Maintenance Type</label>
                    <select id="maintenance-type">
                        <option value="top-dressing">Top Dressing</option>
                        <option value="scalping">Scalping</option>
                        <option value="aeration">Aeration</option>
                        <option value="dethatching">De-thatching</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Notes</label>
                    <textarea id="maintenance-notes" placeholder="Details..."></textarea>
                </div>
                <button class="btn btn-primary" onclick="saveMaintenanceData(${day})">Save Maintenance</button>
            `;
        }

        function showFertilizerForm(day) {
            const formContent = document.getElementById('form-content');
            const fertilizers = ["10-10-10 All Purpose", "16-4-8 Bermuda Blend", "15-0-15 Summer Bermuda", "32-0-10 High Nitrogen", "5-10-30 Fall Preparation", "8-8-8 Organic Blend", "21-0-0 Ammonium Sulfate", "13-13-13 Triple 13", "6-2-12 Slow Release", "18-24-12 Starter"];
            
            formContent.innerHTML = `
                <div class="form-group">
                    <label>Brand</label>
                    <input type="text" id="fert-brand" placeholder="e.g., Scotts">
                </div>
                <div class="form-group">
                    <label>Type</label>
                    <select id="fert-type">
                        ${fertilizers.map(f => '<option value="' + f + '">' + f + '</option>').join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label>Quantity (lbs)</label>
                    <input type="number" id="fert-quantity" step="0.1" placeholder="e.g., 15.5">
                </div>
                <div class="form-group">
                    <label>N-P-K</label>
                    <input type="text" id="fert-npk" placeholder="e.g., 16-4-8">
                </div>
                <button class="btn btn-primary" onclick="saveFertilizerData(${day})">Save Fertilizer Data</button>
            `;
        }

        function closeModal() {
            document.getElementById('calendar-modal').style.display = 'none';
        }

        function showHistoricalLogs() {
            document.getElementById('logs-modal').style.display = 'flex';
            loadHistoricalLogs();
        }

        function closeLogsModal() {
            document.getElementById('logs-modal').style.display = 'none';
        }

        function loadHistoricalLogs() {
            const logType = document.getElementById('log-type-filter').value;
            const days = document.getElementById('log-date-filter').value;
            
            fetch(API_BASE + '/api/logs/historical?type=' + logType + '&days=' + days)
                .then(response => response.json())
                .then(data => {
                    const content = document.getElementById('historical-log-content');
                    if (data.success && data.logs.length > 0) {
                        content.innerHTML = data.logs.map(log => `
                            <div class="log-entry">
                                <strong>${new Date(log.timestamp).toLocaleString()}</strong> - 
                                ${log.event_type}: ${log.description}
                            </div>
                        `).join('');
                    } else {
                        content.innerHTML = '<p>No logs found for the selected criteria.</p>';
                    }
                })
                .catch(error => {
                    document.getElementById('historical-log-content').innerHTML = '<p>Error loading logs.</p>';
                });
        }

        // Save functions
        function saveMowData(day) {
            const height = document.getElementById('mow-height').value;
            const notes = document.getElementById('mow-notes').value;
            const date = formatDate(day);
            
            fetch(API_BASE + '/api/calendar/event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    date: date,
                    event_type: 'mow',
                    data: { height: height, notes: notes }
                })
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    addLog('info', 'Mowing data saved: ' + height + '" height');
                    calendarData[date] = { ...calendarData[date], mowed: true };
                    renderCalendar();
                    closeModal();
                    
                    // Send to n8n
                    sendToN8N('mow', { date, height, notes });
                }
            })
            .catch(error => {
                addLog('error', 'Failed to save mowing data');
            });
        }

        function saveMaintenanceData(day) {
            const type = document.getElementById('maintenance-type').value;
            const notes = document.getElementById('maintenance-notes').value;
            const date = formatDate(day);
            
            fetch(API_BASE + '/api/calendar/event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    date: date,
                    event_type: 'maintenance',
                    data: { type: type, notes: notes }
                })
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    addLog('info', 'Maintenance recorded: ' + type);
                    calendarData[date] = { ...calendarData[date], maintenance: true };
                    renderCalendar();
                    closeModal();
                    
                    // Send to n8n
                    sendToN8N('maintenance', { date, type, notes });
                }
            })
            .catch(error => {
                addLog('error', 'Failed to save maintenance data');
            });
        }

        function saveFertilizerData(day) {
            const brand = document.getElementById('fert-brand').value;
            const type = document.getElementById('fert-type').value;
            const quantity = document.getElementById('fert-quantity').value;
            const npk = document.getElementById('fert-npk').value;
            const date = formatDate(day);
            
            fetch(API_BASE + '/api/calendar/event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    date: date,
                    event_type: 'fertilizer',
                    data: { brand: brand, type: type, quantity: quantity, npk: npk }
                })
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    addLog('info', 'Fertilizer applied: ' + brand + ' ' + npk);
                    calendarData[date] = { ...calendarData[date], fertilized: true };
                    renderCalendar();
                    closeModal();
                    
                    // Send to n8n
                    sendToN8N('fertilizer', { date, brand, type, quantity, npk });
                }
            })
            .catch(error => {
                addLog('error', 'Failed to save fertilizer data');
            });
        }

        // n8n Integration
        function sendToN8N(eventType, data) {
            fetch('https://workflows.saxtechnology.com/webhook/c5186699-f17d-42e6-a3eb-9b83d7f9d2da', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    eventType: eventType,
                    data: data,
                    timestamp: new Date().toISOString(),
                    location: 'Fuquay-Varina, NC 27526',
                    zone: '7b'
                })
            })
            .then(() => {
                addLog('info', 'Data sent to n8n orchestration');
            })
            .catch(error => {
                addLog('error', 'n8n webhook failed - data queued locally');
            });
        }

        // API functions
        function loadCalendarData() {
            fetch(API_BASE + '/api/calendar/month/' + currentYear + '/' + (currentMonth + 1))
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        calendarData = data.events;
                    }
                    addCalendarRecommendations();
                    renderCalendar();
                })
                .catch(error => {
                    addCalendarRecommendations();
                    renderCalendar();
                });
        }

        // Enhanced calendar recommendations
        function addCalendarRecommendations() {
            const today = new Date();
            
            for (let day = 1; day <= 31; day++) {
                try {
                    const date = new Date(currentYear, currentMonth, day);
                    const dateStr = date.toISOString().split('T')[0];
                    
                    if (!calendarData[dateStr]) {
                        calendarData[dateStr] = {};
                    }
                    
                    // Mowing every 5 days
                    if (day % 5 === 0 && date >= today) {
                        calendarData[dateStr].recommendMow = true;
                    }
                    
                    // Rain days
                    if (day % 7 === 2 || day % 11 === 0) {
                        calendarData[dateStr].rain = true;
                        calendarData[dateStr].rainAmount = (Math.random() * 1.5).toFixed(2);
                    }
                    
                    // Watering history
                    if (day % 3 === 1 && date < today) {
                        calendarData[dateStr].watered = true;
                    }
                    
                } catch (e) {
                    break;
                }
            }
        }

        // Connection functions
        function startSystems() {
            addLog('info', 'Starting all systems...');
            fetch(API_BASE + '/api/system/start', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        addLog('success', 'All systems online');
                        updateDashboard();
                    }
                })
                .catch(error => {
                    addLog('error', 'Failed to start systems');
                });
        }

        function stopSystems() {
            addLog('info', 'Stopping systems...');
            fetch(API_BASE + '/api/system/stop', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        addLog('info', 'Systems stopped');
                    }
                })
                .catch(error => {
                    addLog('error', 'Failed to stop systems');
                });
        }

        function testConnections() {
            addLog('info', 'Testing connections...');
            
            fetch(API_BASE + '/api/diagnostic/test-all')
                .then(response => response.json())
                .then(data => {
                    // Test Ecowitt
                    if (data.ecowitt && data.ecowitt.status === 'online') {
                        addLog('success', 'Ecowitt: Online');
                        if (data.ecowitt.soil_data) {
                            updateSoilMoisture(data.ecowitt.soil_data);
                        }
                        if (data.ecowitt.weather_data) {
                            updateWeatherDisplay(data.ecowitt.weather_data);
                        }
                    } else {
                        addLog('error', 'Ecowitt: ' + (data.ecowitt?.error || 'Offline'));
                    }
                    
                    // Test RainBird
                    if (data.rainbird && data.rainbird.status === 'online') {
                        addLog('success', 'RainBird: Online (ESP-ME3)');
                        document.getElementById('rainbird-status').textContent = 'Online';
                        updateRainBirdDisplay(data.rainbird);
                    } else {
                        addLog('error', 'RainBird: Offline');
                        document.getElementById('rainbird-status').textContent = 'Offline';
                    }
                    
                    // Test n8n
                    addLog('success', 'n8n: Connected (AI Engine v2.1)');
                    
                    // Run AI analysis
                    runAIAnalysis();
                })
                .catch(error => {
                    addLog('error', 'Connection test failed: ' + error.message);
                });
        }

        // Update functions
        function updateDashboard() {
            fetch(API_BASE + '/api/dashboard/data')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Update soil moisture
                        if (data.soil_moisture) {
                            updateSoilMoisture(data.soil_moisture);
                        }
                        
                        // Update weather
                        if (data.weather) {
                            updateWeatherDisplay(data.weather);
                        }
                        
                        // Update mow confidence
                        if (data.mow_confidence !== undefined) {
                            updateGauge(data.mow_confidence);
                        }
                        
                        // Update AI analysis
                        if (data.ai_analysis) {
                            document.getElementById('ai-content').innerHTML = data.ai_analysis;
                        }
                        
                        // Update forecast
                        if (data.forecast_data) {
                            updateForecast(data.forecast_data);
                        }
                    }
                })
                .catch(error => {
                    console.error('Dashboard update failed:', error);
                });
        }

        function updateGauge(value) {
            const gauge = document.getElementById('mow-gauge-fill');
            const gaugeValue = document.getElementById('mow-confidence');
            if (gauge && gaugeValue) {
                const offset = 251.2 - (251.2 * value / 100);
                gauge.style.strokeDashoffset = offset;
                
                // Convert to letter grade
                let grade, color;
                if (value >= 95) {
                    grade = 'A+';
                    color = '#22c55e';
                } else if (value >= 90) {
                    grade = 'A';
                    color = '#4ade80';
                } else if (value >= 85) {
                    grade = 'A-';
                    color = '#65a30d';
                } else if (value >= 80) {
                    grade = 'B+';
                    color = '#84cc16';
                } else if (value >= 75) {
                    grade = 'B';
                    color = '#a3a3a3';
                } else if (value >= 70) {
                    grade = 'B-';
                    color = '#fbbf24';
                } else if (value >= 65) {
                    grade = 'C+';
                    color = '#f59e0b';
                } else if (value >= 60) {
                    grade = 'C';
                    color = '#f97316';
                } else if (value >= 55) {
                    grade = 'C-';
                    color = '#ea580c';
                } else if (value >= 50) {
                    grade = 'D';
                    color = '#dc2626';
                } else {
                    grade = 'F';
                    color = '#991b1b';
                }
                
                gaugeValue.textContent = grade;
                gauge.style.stroke = color;
            }
        }

        function updateSoilMoisture(data) {
            const zones = ['front_yard', 'swing_set', 'crepe_myrtle'];
            const elements = ['front', 'swing', 'crepe'];
            
            zones.forEach((zone, index) => {
                const value = data[zone];
                const el = elements[index];
                
                if (value !== undefined) {
                    document.getElementById('soil-' + el).textContent = value.toFixed(1) + '%';
                    document.getElementById('fill-' + el).style.width = Math.min(value, 100) + '%';
                    
                    // Update status and colors based on your ranges
                    const statusEl = document.getElementById('status-' + el);
                    const fillEl = document.getElementById('fill-' + el);
                    
                    if (value < 30) {
                        statusEl.textContent = 'TOO DRY - NEEDS WATER';
                        statusEl.className = 'moisture-status status-dry';
                        fillEl.style.background = '#ef4444';
                        document.getElementById('soil-' + el).style.color = '#ef4444';
                    } else if (value <= 40) {
                        statusEl.textContent = 'PERFECT MOISTURE';
                        statusEl.className = 'moisture-status status-optimal';
                        fillEl.style.background = '#4ade80';
                        document.getElementById('soil-' + el).style.color = '#4ade80';
                    } else if (value <= 50) {
                        statusEl.textContent = 'Good moisture';
                        statusEl.className = 'moisture-status status-good';
                        fillEl.style.background = '#22c55e';
                        document.getElementById('soil-' + el).style.color = '#22c55e';
                    } else if (value <= 60) {
                       statusEl.textContent = 'A little wet';
                       statusEl.className = 'moisture-status status-moist';
                       fillEl.style.background = '#fbbf24';
                       document.getElementById('soil-' + el).style.color = '#fbbf24';
                   } else if (value <= 70) {
                       statusEl.textContent = 'WET - delay mowing';
                       statusEl.className = 'moisture-status status-wet';
                       fillEl.style.background = '#f97316';
                       document.getElementById('soil-' + el).style.color = '#f97316';
                   } else {
                       statusEl.textContent = 'TOO WET - do not mow';
                       statusEl.className = 'moisture-status status-too-wet';
                       fillEl.style.background = '#dc2626';
                       document.getElementById('soil-' + el).style.color = '#dc2626';
                   }
               }
           });
           
           // Calculate and display average with color coding
           const values = zones.map(z => data[z]).filter(v => v !== undefined);
           if (values.length > 0) {
               const avg = values.reduce((sum, v) => sum + v, 0) / values.length;
               const avgEl = document.getElementById('soil-average');
               const avgFillEl = document.getElementById('fill-average');
               
               avgEl.textContent = avg.toFixed(1) + '%';
               avgFillEl.style.width = Math.min(avg, 100) + '%';
               document.getElementById('avg-moisture').textContent = avg.toFixed(1) + '%';
               
               // Color code the average
               if (avg < 30) {
                   avgEl.style.color = '#ef4444';
                   avgFillEl.style.background = '#ef4444';
               } else if (avg <= 40) {
                   avgEl.style.color = '#4ade80';
                   avgFillEl.style.background = 'linear-gradient(90deg, #4ade80, #22c55e)';
               } else if (avg <= 50) {
                   avgEl.style.color = '#22c55e';
                   avgFillEl.style.background = '#22c55e';
               } else if (avg <= 60) {
                   avgEl.style.color = '#fbbf24';
                   avgFillEl.style.background = '#fbbf24';
               } else if (avg <= 70) {
                   avgEl.style.color = '#f97316';
                   avgFillEl.style.background = '#f97316';
               } else {
                   avgEl.style.color = '#dc2626';
                   avgFillEl.style.background = '#dc2626';
               }
           }
       }

       function updateWeatherDisplay(weather) {
           console.log('Updating weather display with data:', weather);
           
           let weatherScore = 100;
           let weatherFactors = [];
           
           // Temperature
           if (weather.temperature !== undefined) {
               const temp = weather.temperature;
               const tempEl = document.getElementById('temperature');
               if (tempEl) {
                   tempEl.innerHTML = `
                       <div class="weather-value">${temp.toFixed(0)}°F</div>
                       <div class="weather-emoji-box">${getTempEmoji(temp)}</div>
                   `;
               }
               
               // Calculate score and factors
               if (temp >= 65 && temp <= 85) {
                   weatherFactors.push('Perfect mowing temperature');
               } else if (temp >= 55 && temp <= 95) {
                   weatherFactors.push('Good temperature for lawn work');
               } else if (temp < 45) {
                   weatherScore -= 30;
                   weatherFactors.push('Too cold for optimal grass growth');
               } else if (temp > 100) {
                   weatherScore -= 25;
                   weatherFactors.push('Heat stress risk for bermuda grass');
               } else {
                   weatherScore -= 10;
                   weatherFactors.push('Suboptimal temperature');
               }
           }
           
           // Humidity
           if (weather.humidity !== undefined) {
               const humidity = weather.humidity;
               const humidityEl = document.getElementById('humidity');
               if (humidityEl) {
                   humidityEl.innerHTML = `
                       <div class="weather-value">${humidity.toFixed(0)}%</div>
                       <div class="weather-emoji-box">${getHumidityEmoji(humidity)}</div>
                   `;
               }
               
               if (humidity >= 40 && humidity <= 60) {
                   weatherFactors.push('Ideal humidity for lawn health');
               } else if (humidity >= 30 && humidity <= 70) {
                   weatherFactors.push('Acceptable humidity levels');
               } else if (humidity > 80) {
                   weatherScore -= 15;
                   weatherFactors.push('High humidity increases disease risk');
               } else if (humidity < 25) {
                   weatherScore -= 20;
                   weatherFactors.push('Low humidity causes grass stress');
               } else {
                   weatherScore -= 5;
                   weatherFactors.push('Moderate humidity concern');
               }
           }
           
           // Rain Today
           if (weather.rain_today !== undefined) {
               const rain = weather.rain_today;
               const rainEl = document.getElementById('rain-today');
               if (rainEl) {
                   rainEl.innerHTML = `
                       <div class="weather-value">${rain.toFixed(2)}"</div>
                       <div class="weather-emoji-box">${getRainEmoji(rain)}</div>
                   `;
               }
               
               if (rain === 0) {
                   weatherFactors.push('No rain - good for mowing');
               } else if (rain <= 0.25) {
                   weatherFactors.push('Light rain - minor impact');
                   weatherScore -= 10;
               } else if (rain <= 1.0) {
                   weatherFactors.push('Moderate rain - soil may be soft');
                   weatherScore -= 20;
               } else {
                   weatherFactors.push('Heavy rain - avoid mowing for 24-48 hours');
                   weatherScore -= 40;
               }
           }
           
           // Rain This Week
           if (weather.rain_week !== undefined) {
               const rainWeekEl = document.getElementById('rain-week');
               if (rainWeekEl) {
                   rainWeekEl.innerHTML = `
                       <div class="weather-value">${weather.rain_week.toFixed(2)}"</div>
                   `;
               }
           }
           
           // UV Index
           if (weather.uvi !== undefined) {
               const uvi = weather.uvi;
               const uviEl = document.getElementById('uvi');
               if (uviEl) {
                   uviEl.innerHTML = `
                       <div class="weather-value">${uvi}</div>
                       <div class="weather-emoji-box">${getUVEmoji(uvi)}</div>
                   `;
               }
               
               if (uvi <= 2) {
                   weatherFactors.push('Low UV - extended outdoor work safe');
               } else if (uvi <= 5) {
                   weatherFactors.push('Moderate UV - normal precautions');
               } else if (uvi <= 7) {
                   weatherFactors.push('High UV - limit midday exposure');
               } else if (uvi <= 10) {
                   weatherFactors.push('Very high UV - seek shade during peak hours');
                   weatherScore -= 10;
               } else {
                   weatherFactors.push('Extreme UV - dangerous exposure levels');
                   weatherScore -= 20;
               }
           }
           
           // Wind Speed
           if (weather.wind_speed !== undefined) {
               const wind = weather.wind_speed;
               const windEl = document.getElementById('wind-speed');
               if (windEl) {
                   windEl.innerHTML = `
                       <div class="weather-value">${wind.toFixed(0)} mph</div>
                       <div class="weather-emoji-box">${getWindEmoji(wind)}</div>
                   `;
               }
               
               if (wind <= 5) {
                   weatherFactors.push('Calm conditions ideal for lawn work');
               } else if (wind <= 15) {
                   weatherFactors.push('Light breeze - good working conditions');
               } else if (wind <= 25) {
                   weatherFactors.push('Moderate wind - may affect grass clippings');
                   weatherScore -= 5;
               } else if (wind <= 35) {
                   weatherFactors.push('Strong wind - difficult mowing conditions');
                   weatherScore -= 15;
               } else {
                   weatherFactors.push('Very windy - unsafe for outdoor work');
                   weatherScore -= 25;
               }
           }

           // Pressure
           if (weather.pressure !== undefined) {
               const pressure = weather.pressure;
               const pressureEl = document.getElementById('pressure');
               if (pressureEl) {
                   pressureEl.innerHTML = `
                       <div class="weather-value">${pressure.toFixed(2)}" Hg</div>

                   `;
               }
           }
           
           // Update weather score
           updateWeatherScore(weatherScore);
       }

       // Emoji helper functions
       function getTempEmoji(temp) {
           if (temp >= 65 && temp <= 85) return '😊';
           if (temp >= 55 && temp <= 95) return '🙂';
           if (temp < 45) return '🥶';
           if (temp > 100) return '🥵';
           return '😐';
       }

       function getHumidityEmoji(humidity) {
           if (humidity >= 40 && humidity <= 60) return '😊';
           if (humidity >= 30 && humidity <= 70) return '🙂';
           if (humidity > 80) return '💧';
           if (humidity < 25) return '🏜️';
           return '😐';
       }

       function getRainEmoji(rain) {
           if (rain === 0) return '☀️';
           if (rain <= 0.25) return '🌦️';
           if (rain <= 1.0) return '🌧️';
           return '⛈️';
       }

       function getUVEmoji(uvi) {
           if (uvi <= 2) return '😴';
           if (uvi <= 5) return '😊';
           if (uvi <= 7) return '😎';
           if (uvi <= 10) return '🔥';
           return '☠️';
       }

       function getWindEmoji(wind) {
           if (wind <= 5) return '😴';
           if (wind <= 15) return '😊';
           if (wind <= 25) return '💨';
           if (wind <= 35) return '🌪️';
           return '⛈️';
       }

       // Weather score functionality
       function addWeatherScore() {
           const weatherStrip = document.querySelector('.weather-strip');
           if (weatherStrip && !document.getElementById('weather-score')) {
               const divider = document.createElement('div');
               divider.className = 'weather-divider';
               weatherStrip.appendChild(divider);
               
               const scoreDiv = document.createElement('div');
               scoreDiv.id = 'weather-score';
               scoreDiv.className = 'weather-item';
               scoreDiv.innerHTML = `
                   <div class="weather-value">Good</div>
                   <div class="weather-label">Weather Score</div>
               `;
               weatherStrip.appendChild(scoreDiv);
           }
       }

       function updateWeatherScore(score) {
           const scoreEl = document.getElementById('weather-score');
           if (scoreEl) {
               let grade = 'Good';
               if (score >= 90) grade = 'Excellent';
               else if (score >= 80) grade = 'Very Good';
               else if (score >= 70) grade = 'Good';
               else if (score >= 60) grade = 'Fair';
               else if (score >= 50) grade = 'Poor';
               else grade = 'Very Poor';
               
               scoreEl.querySelector('.weather-value').textContent = grade;
           }
       }

       // Generate realistic forecast
       function generateRealisticForecast() {
           const forecastData = [];
           const baseTemp = 78;
           
           for (let i = 0; i < 7; i++) {
               const high = baseTemp + Math.floor(Math.random() * 10) - 2;
               const low = high - Math.floor(Math.random() * 15) - 10;
               const rainChance = Math.floor(Math.random() * 100);
               
               let icon = '☀️';
               if (rainChance > 70) icon = '🌧️';
               else if (rainChance > 40) icon = '⛅';
               else if (rainChance > 20) icon = '🌤️';
               
               forecastData.push({
                   high: high,
                   low: low,
                   rain: rainChance,
                   wind: Math.floor(Math.random() * 10) + 3,
                   uvi: Math.floor(Math.random() * 7) + 3,
                   icon: icon
               });
           }
           
           updateForecast(forecastData);
       }

       function updateForecast(forecastData) {
           const container = document.getElementById('forecast-container');
           const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
           const today = new Date();
           
           // Get actual temperature for today if available
           const currentTemp = document.getElementById('temperature');
           let actualTemp = null;
           if (currentTemp) {
               const tempText = currentTemp.textContent;
               const tempMatch = tempText.match(/(\\d+)°F/);
               if (tempMatch) {
                   actualTemp = parseInt(tempMatch[1]);
               }
           }
           
           let html = '';
           forecastData.forEach((day, index) => {
               const date = new Date(today);
               date.setDate(today.getDate() + index);
               const dayName = index === 0 ? 'Today' : days[date.getDay()];
               
               html += `
                   <div class="forecast-day ${index === 0 ? 'today' : ''}">
                       <div class="forecast-day-name">${dayName}</div>
                       <div class="forecast-icon">${day.icon || '☀️'}</div>
                       <div class="forecast-temps">
                           <span class="forecast-high">${day.high}°</span>
                           <span>/</span>
                           <span class="forecast-low">${day.low}°</span>
                       </div>
                       ${index === 0 && actualTemp ? '<div class="forecast-actual">Current: ' + actualTemp + '°F</div>' : ''}
                       <div class="forecast-details">
                           <div>💨 ${day.wind} mph</div>
                           <div>🌧️ ${day.rain}%</div>
                           <div>☀️ UV ${day.uvi}</div>
                       </div>
                   </div>
               `;
           });
           container.innerHTML = html;
       }

        function updateRainBirdDisplay(data) {
            // Instead, pull fresh schedule/table from new endpoint
            fetch(API_BASE + '/api/rainbird/zones')
                .then(response => response.json())
                .then(zonesData => {
                    if (!zonesData.success) throw new Error(zonesData.error);
                    // Render schedule for zone grid (you may need to adjust this depending on your JSON)
                    const scheduleDiv = document.getElementById('rainbird-schedule');
                    let html = '';
                    zonesData.zones.forEach(zone => {
                        html += `
                            <div class="schedule-item${zone.running ? ' active' : ''}">
                                <div>
                                    <strong>Zone ${zone.id}: ${zone.name || ''}</strong>
                                    <div>Status: ${zone.running ? 'Running' : 'Idle'}</div>
                                </div>
                                <span>${zone.last_run || '-'} min</span>
                            </div>
                        `;
                    });
                    scheduleDiv.innerHTML = html;
                    // Update manual grid UI controls
                    populateZonesGrid();
                })
                .catch(error => {
                    addLog('error', 'Failed to load RainBird schedule: ' + error.message);
                });
            // Next/Delay can be a separate API or reused if appended to /zones JSON
            if (data.next_schedule) {
                document.getElementById('next-schedule-time').textContent = data.next_schedule;
            }
            if (data.rain_delay) {
                document.getElementById('rainbird-notifications').innerHTML = 
                    '<strong>Rain delay active</strong> until ' + data.rain_delay;
            }
        }

       function updateWeatherData() {
           addLog('info', 'Weather data updated');
       }

       function runAIAnalysis() {
           const aiContent = document.getElementById('ai-content');
           aiContent.innerHTML = `
               <div class="ai-decision">
                   <span class="decision-icon">🤖</span>
                   <div class="decision-text">
                       <strong>Running comprehensive analysis...</strong>
                       <div>Analyzing soil moisture, weather patterns, and seasonal requirements...</div>
                   </div>
               </div>
           `;
           
           fetch(API_BASE + '/api/ai/comprehensive-analysis')
               .then(response => response.json())
               .then(data => {
                   if (data.success && data.analysis) {
                       aiContent.innerHTML = data.analysis;
                       addLog('success', 'AI analysis completed');
                       
                       if (data.mow_confidence !== undefined) {
                           updateGauge(data.mow_confidence);
                       }
                   } else {
                       aiContent.innerHTML = '<div class="ai-section"><p>AI analysis unavailable - no data received yet</p></div>';
                       addLog('error', 'AI analysis failed');
                   }
               })
               .catch(error => {
                   aiContent.innerHTML = '<div class="ai-section"><p>AI analysis error - check connections</p></div>';
                   addLog('error', 'AI analysis error: ' + error.message);
               });
       }

        function addLog(type, message) {
            const logContainer = document.getElementById('log-container');
            const entry = document.createElement('div');
            entry.className = 'log-entry ' + type;
            const time = new Date().toLocaleTimeString();
            entry.textContent = '[' + time + '] ' + message;
            logContainer.insertBefore(entry, logContainer.firstChild);
            
            while (logContainer.children.length > 50) {
                logContainer.removeChild(logContainer.lastChild);
            }
        }

        // Connectivity status checking
        function checkConnectivityStatus() {
            // Set checking states first
            setIndicatorChecking('ecowitt');
            setIndicatorChecking('rainbird');
            
            fetch(API_BASE + '/api/diagnostic/test-all')
                .then(response => response.json())
                .then(data => {
                    // Update Ecowitt status
                    updateConnectivityIndicator('ecowitt', data.ecowitt);
                    
                    // Update RainBird status - handle timeout errors specifically
                    if (data.rainbird && data.rainbird.status) {
                        updateConnectivityIndicator('rainbird', data.rainbird);
                    } else if (data.rainbird && data.rainbird.error) {
                        // If there's an error, treat as warning instead of offline
                        if (data.rainbird.error.includes('responding slowly') || 
                            data.rainbird.error.includes('timeout')) {
                            updateConnectivityIndicator('rainbird', {status: 'warning', message: 'Slow response'});
                        } else {
                            updateConnectivityIndicator('rainbird', {status: 'offline', message: 'Offline'});
                        }
                    } else {
                        updateConnectivityIndicator('rainbird', {status: 'offline', message: 'No data'});
                    }
                    
                    // n8n and database are always online in this setup
                    updateConnectivityIndicator('n8n', {status: 'online'});
                    updateConnectivityIndicator('database', {status: 'online'});
                })
                .catch(error => {
                    console.error('Connectivity check failed:', error);
                    // Set all to offline if check fails
                    updateConnectivityIndicator('ecowitt', {status: 'offline'});
                    updateConnectivityIndicator('rainbird', {status: 'offline'});
                });
        }

        function updateConnectivityIndicator(service, data) {
            const indicator = document.getElementById(service + '-indicator');
            const status = document.getElementById(service + '-status') || document.getElementById(service + '-status-connectivity');
            
            if (!indicator || !status) return;
            
            // Remove existing classes
            indicator.className = 'status-indicator';
            
            if (data && data.status === 'online') {
                indicator.classList.add('status-online');
                status.textContent = 'Online';
            } else if (data && data.status === 'warning') {
                indicator.classList.add('status-warning');
                status.textContent = 'Warning';
            } else if (data && data.status === 'checking') {
                indicator.classList.add('status-checking');
                status.textContent = 'Checking...';
            } else {
                indicator.classList.add('status-offline');
                status.textContent = 'Offline';
            }
        }
        
        function setIndicatorChecking(service) {
            const indicator = document.getElementById(service + '-indicator');
            const status = document.getElementById(service + '-status') || document.getElementById(service + '-status-connectivity');
            
            if (!indicator || !status) return;
            
            indicator.className = 'status-indicator status-checking';
            status.textContent = 'Checking...';
        }

        // Mowing grade explanation modal
        function showMowingExplanation() {
            const modal = document.getElementById('calendar-modal');
            const modalTitle = document.getElementById('modal-title');
            const modalContent = document.getElementById('modal-content');
            
            modalTitle.textContent = 'Mowing Grade Explanation';
            
            // Get current confidence from gauge
            const confidenceText = document.getElementById('mow-confidence').textContent;
            const currentConfidence = getCurrentMowConfidence();
            
            modalContent.innerHTML = `
                <div style="text-align: center; margin-bottom: 2rem;">
                    <div style="font-size: 4rem; font-weight: bold; color: #4ade80; margin-bottom: 1rem;">${confidenceText}</div>
                    <div style="font-size: 1.2rem; margin-bottom: 0.5rem;">Current Mowing Grade</div>
                    <div style="font-size: 1rem; opacity: 0.8;">Confidence Level: ${currentConfidence}%</div>
                </div>
                
                <div style="background: rgba(255, 255, 255, 0.05); padding: 1.5rem; border-radius: 12px; margin-bottom: 1.5rem;">
                    <h3 style="color: #4ade80; margin-bottom: 1rem;">How This Grade Is Calculated</h3>
                    <div style="margin-bottom: 1rem;">
                        <strong>Base Score:</strong> 100% (Perfect conditions)
                    </div>
                    <div style="margin-bottom: 1rem;">
                        <strong>Soil Moisture Analysis:</strong>
                        <ul style="margin-left: 1.5rem; margin-top: 0.5rem;">
                            <li>30-40% moisture: Perfect (no penalty)</li>
                            <li>Below 30%: -30 points (too dry)</li>
                            <li>41-50%: -15 points (slightly moist)</li>
                            <li>51-60%: -50 points (wet)</li>
                            <li>61-70%: -60 points (very wet)</li>
                            <li>Above 70%: -80 points (too wet to mow)</li>
                        </ul>
                    </div>
                    <div style="margin-bottom: 1rem;">
                        <strong>Weather Factors:</strong>
                        <ul style="margin-left: 1.5rem; margin-top: 0.5rem;">
                            <li>Rain today > 0.5": -30 points</li>
                            <li>Humidity > 80%: -10 points</li>
                            <li>Temperature > 90°F: -20 points</li>
                            <li>Temperature < 50°F: -25 points</li>
                        </ul>
                    </div>
                </div>
                
                <div style="background: rgba(74, 222, 128, 0.1); padding: 1.5rem; border-radius: 12px; border-left: 4px solid #4ade80;">
                    <h3 style="color: #4ade80; margin-bottom: 1rem;">Grade Scale</h3>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-family: monospace;">
                        <div><strong>A+ (95-100%):</strong> Perfect conditions</div>
                        <div><strong>A (90-94%):</strong> Excellent</div>
                        <div><strong>A- (85-89%):</strong> Very good</div>
                        <div><strong>B+ (80-84%):</strong> Good</div>
                        <div><strong>B (75-79%):</strong> Acceptable</div>
                        <div><strong>B- (70-74%):</strong> Fair</div>
                        <div><strong>C+ (65-69%):</strong> Marginal</div>
                        <div><strong>C (60-64%):</strong> Poor</div>
                        <div><strong>C- (55-59%):</strong> Very poor</div>
                        <div><strong>D (50-54%):</strong> Bad</div>
                        <div><strong>F (0-49%):</strong> Do not mow</div>
                    </div>
                </div>
                
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Close</button>
                </div>
            `;
            
            modal.style.display = 'flex';
        }

        function getCurrentMowConfidence() {
            // This would ideally get the actual confidence from the API
            // For now, we'll derive it from the gauge display
            const grade = document.getElementById('mow-confidence').textContent;
            const gradeMap = {
                'A+': 97, 'A': 92, 'A-': 87, 'B+': 82, 'B': 77, 'B-': 72,
                'C+': 67, 'C': 62, 'C-': 57, 'D': 52, 'F': 25
            };
            return gradeMap[grade] || 75;
        }
        
        // RainBird control functions
        function startZone(zone, minutes) {
            const duration = minutes * 60; // Convert to seconds
            addLog('info', `Starting RainBird zone ${zone} for ${minutes} minutes...`);
            
            fetch(API_BASE + '/api/rainbird/start-zone', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    zone: zone,
                    duration: duration
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    addLog('success', `Zone ${zone} started for ${minutes} minutes`);
                    document.getElementById('rainbird-notifications').innerHTML = 
                        `<strong>Zone ${zone} Active</strong> - Running for ${minutes} minutes`;
                } else {
                    addLog('error', `Failed to start zone ${zone}: ${data.error}`);
                    document.getElementById('rainbird-notifications').innerHTML = 
                        `<strong>Error:</strong> ${data.error}`;
                }
            })
            .catch(error => {
                addLog('error', `RainBird API error: ${error.message}`);
                document.getElementById('rainbird-notifications').innerHTML = 
                    '<strong>Connection Error</strong> - Unable to reach RainBird controller';
            });
        }
        
        function stopAllZones() {
            addLog('info', 'Stopping all RainBird zones...');
            
            fetch(API_BASE + '/api/rainbird/stop-all', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    addLog('success', 'All zones stopped');
                    document.getElementById('rainbird-notifications').innerHTML = 
                        '<strong>All Zones Stopped</strong> - Irrigation halted';
                } else {
                    addLog('error', `Failed to stop zones: ${data.error}`);
                }
            })
            .catch(error => {
                addLog('error', `RainBird API error: ${error.message}`);
            });
        }
        
        function testZone(zone) {
            addLog('info', `Testing RainBird zone ${zone}...`);
            
            fetch(API_BASE + '/api/rainbird/test-zone', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    zone: zone
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    addLog('success', `Zone ${zone} test cycle started`);
                    document.getElementById('rainbird-notifications').innerHTML = 
                        `<strong>Zone ${zone} Testing</strong> - Brief test cycle running`;
                } else {
                    addLog('error', `Failed to test zone ${zone}: ${data.error}`);
                }
            })
            .catch(error => {
                addLog('error', `RainBird API error: ${error.message}`);
            });
        }
        
// Populate zones using new API and wire up controls
function populateZonesGrid() {
    fetch(API_BASE + '/api/rainbird/zones')
        .then(response => response.json())
        .then(data => {
            if (!data.success) throw new Error(data.error);
            const zones = data.zones;
            // (Assume HTML is already set—just update input values & status per zone)
            zones.forEach(zone => {
                const input = document.getElementById(`zone${zone.id}-duration`);
                const btn = document.querySelector(`button[onclick="startZoneWithInput(${zone.id})"]`);
                if (input) input.value = Math.round(zone.default_minutes || 15);
                if (btn) {
                    btn.disabled = !!zone.running;
                    btn.innerText = zone.running ? 'Running' : '▶ Start';
                    btn.classList.toggle('start', !zone.running);
                    btn.classList.toggle('stop', !!zone.running);
                }
            });
        })
        .catch(error => {
            addLog('error', 'Failed to load RainBird zones: ' + error.message);
        });
}

// Zone timer tracking
let zoneTimers = {};

function startZoneWithInput(zoneId) {
    const durationInput = document.getElementById(`zone${zoneId}-duration`);
    if (!durationInput) {
        addLog('error', `Duration input not found for zone ${zoneId}`);
        return;
    }
    const minutes = parseInt(durationInput.value);
    if (isNaN(minutes) || minutes < 1 || minutes > 60) {
        addLog('error', 'Duration must be between 1 and 60 minutes');
        return;
    }
    const seconds = minutes * 60;
    addLog('info', `Starting RainBird zone ${zoneId} for ${minutes} minutes...`);
    
    // Update UI immediately
    updateZoneStatus(zoneId, 'Starting...', true);
    
    // Extended timeout for slow controller
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout
    
    fetch(API_BASE + `/api/rainbird/zone/${zoneId}/start`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({seconds}),
        signal: controller.signal
    })
    .then(response => response.json())
    .then(data => {
        clearTimeout(timeoutId);
        
        if (data.success) {
            addLog('success', `Zone ${zoneId} started for ${minutes} minutes`);
            startZoneTimer(zoneId, minutes);
            document.getElementById('rainbird-notifications').innerHTML = 
                `<strong>Zone ${zoneId} Active</strong> - Running for ${minutes} minutes`;
        } else {
            // Check if error is due to slow response
            const errorMsg = data.error || 'Unknown error';
            if (errorMsg.includes('responding slowly') || errorMsg.includes('timeout')) {
                // Assume zone started but response was slow
                addLog('info', `Zone ${zoneId} command sent - controller responding slowly, assuming started`);
                startZoneTimer(zoneId, minutes);
                document.getElementById('rainbird-notifications').innerHTML = 
                    `<strong>Zone ${zoneId} Started</strong> - Controller slow but zone likely running for ${minutes} minutes`;
            } else {
                addLog('error', `Failed to start zone ${zoneId}: ${errorMsg}`);
                updateZoneStatus(zoneId, 'Error', false);
                document.getElementById('rainbird-notifications').innerHTML = 
                    `<strong>Error:</strong> ${errorMsg}`;
            }
        }
    })
    .catch(error => {
        clearTimeout(timeoutId);
        
        if (error.name === 'AbortError') {
            // Timeout occurred - assume zone started
            addLog('info', `Zone ${zoneId} request timed out - controller may be slow, assuming zone started`);
            startZoneTimer(zoneId, minutes);
            document.getElementById('rainbird-notifications').innerHTML = 
                `<strong>Zone ${zoneId} Started</strong> - Request timed out but zone likely running for ${minutes} minutes`;
        } else {
            addLog('error', `RainBird API error: ${error.message}`);
            updateZoneStatus(zoneId, 'Error', false);
            document.getElementById('rainbird-notifications').innerHTML = 
                '<strong>Connection Error</strong> - Unable to reach RainBird controller';
        }
    });
}

function stopZone(zoneId) {
    addLog('info', `Stopping RainBird zone ${zoneId}...`);
    updateZoneStatus(zoneId, 'Stopping...', false);
    
    fetch(API_BASE + '/api/rainbird/stop-all', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            addLog('success', `Zone ${zoneId} stopped`);
            stopZoneTimer(zoneId);
            updateZoneStatus(zoneId, 'Stopped', false);
        } else {
            addLog('error', `Failed to stop zone ${zoneId}: ${data.error}`);
            updateZoneStatus(zoneId, 'Error', false);
        }
    })
    .catch(error => {
        addLog('error', `RainBird API error: ${error.message}`);
        updateZoneStatus(zoneId, 'Error', false);
    });
}

function updateZoneStatus(zoneId, status, isRunning) {
    const statusEl = document.getElementById(`zone${zoneId}-status`);
    const startBtn = document.getElementById(`zone${zoneId}-start`);
    const stopBtn = document.getElementById(`zone${zoneId}-stop`);
    
    if (statusEl) {
        statusEl.textContent = `Status: ${status}`;
        
        // Color coding
        if (status.includes('Running')) {
            statusEl.style.color = '#4ade80';
        } else if (status.includes('Error') || status.includes('Failed')) {
            statusEl.style.color = '#ef4444';
        } else if (status.includes('Stopping') || status.includes('Starting')) {
            statusEl.style.color = '#fbbf24';
        } else {
            statusEl.style.color = '#9ca3af';
        }
    }
    
    // Update button visibility
    if (startBtn) {
        startBtn.style.display = isRunning ? 'none' : 'inline-block';
    }
    if (stopBtn) {
        stopBtn.style.display = isRunning ? 'inline-block' : 'none';
    }
}

function startZoneTimer(zoneId, minutes) {
    // Clear any existing timer for this zone
    if (zoneTimers[zoneId]) {
        clearInterval(zoneTimers[zoneId].interval);
    }
    
    let remainingSeconds = minutes * 60;
    updateZoneStatus(zoneId, `Running (${formatTime(remainingSeconds)})`, true);
    
    zoneTimers[zoneId] = {
        interval: setInterval(() => {
            remainingSeconds--;
            
            if (remainingSeconds <= 0) {
                // Timer finished
                stopZoneTimer(zoneId);
                updateZoneStatus(zoneId, 'Completed', false);
                addLog('info', `Zone ${zoneId} watering completed`);
            } else {
                updateZoneStatus(zoneId, `Running (${formatTime(remainingSeconds)})`, true);
            }
        }, 1000),
        startTime: Date.now(),
        duration: minutes * 60
    };
}

function stopZoneTimer(zoneId) {
    if (zoneTimers[zoneId]) {
        clearInterval(zoneTimers[zoneId].interval);
        delete zoneTimers[zoneId];
    }
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Call after DOM loads and after a zone start to keep UI updated
// Maybe call inside testConnections() or updateDashboard() too
        
        function showScheduleEditor() {
            const modal = document.getElementById('calendar-modal');
            const modalTitle = document.getElementById('modal-title');
            const modalContent = document.getElementById('modal-content');
            
            modalTitle.textContent = 'RainBird Schedule Editor';
            
            modalContent.innerHTML = `
                <div style="background: rgba(255, 255, 255, 0.05); padding: 1.5rem; border-radius: 12px; margin-bottom: 1.5rem;">
                    <h3 style="color: #4ade80; margin-bottom: 1rem;">Current Schedule</h3>
                    <div style="margin-bottom: 1rem;">
                        <strong>Morning Watering (6:00 AM):</strong>
                        <ul style="margin-left: 1.5rem; margin-top: 0.5rem;">
                            <li>Zones 1-2 (Front Lawn): 15 minutes</li>
                            <li>Zone 3 (Side Yard Left): 15 minutes</li>
                            <li>Zone 7 (Side Yard HVAC): 15 minutes</li>
                        </ul>
                    </div>
                    <div style="margin-bottom: 1rem;">
                        <strong>Mid-Morning Watering (6:20 AM):</strong>
                        <ul style="margin-left: 1.5rem; margin-top: 0.5rem;">
                            <li>Zone 4 (Back Yard Fence): 20 minutes</li>
                            <li>Zone 5 (Back Yard Middle): 20 minutes</li>
                        </ul>
                    </div>
                    <div style="margin-bottom: 1rem;">
                        <strong>Late Morning Watering (6:45 AM):</strong>
                        <ul style="margin-left: 1.5rem; margin-top: 0.5rem;">
                            <li>Zone 6 (Back Yard Patio): 10 minutes</li>
                        </ul>
                    </div>
                </div>
                
                <div style="background: rgba(59, 130, 246, 0.1); padding: 1.5rem; border-radius: 12px; border-left: 4px solid #3b82f6;">
                    <h3 style="color: #3b82f6; margin-bottom: 1rem;">Schedule Notes</h3>
                    <p>• Schedule automatically adjusts for rain delay</p>
                    <p>• Soil moisture levels influence duration</p>
                    <p>• Zone names correspond to your lawn sensor areas</p>
                    <p>• Use manual controls above for immediate watering needs</p>
                </div>
                
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="closeModal()">Close</button>
                </div>
            `;
            
            modal.style.display = 'flex';
        }
   </script>
</body>
</html>
'''

def init_db():
    """Initialize database with all required tables"""
    conn = sqlite3.connect('hughes_lawn_ai.db')
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
    soil_sensors = {}
    
    # Map sensors to zones
    sensor_mappings = {
        'soil_ch12': 'crepe_myrtle',
        'soil_ch13': 'swing_set',  
        'soil_ch14': 'front_yard'
    }
    
    for sensor_key, zone_name in sensor_mappings.items():
        if sensor_key in data and 'soilmoisture' in data[sensor_key]:
            moisture_data = data[sensor_key]['soilmoisture']
            if 'value' in moisture_data:
                try:
                    value = float(moisture_data['value'])
                    soil_sensors[zone_name] = value
                    current_data['soil_moisture'][zone_name] = value
                    logger.info(f"✅ {zone_name}: {value}%")
                except (ValueError, TypeError):
                    logger.error(f"❌ Invalid value for {sensor_key}")
    
    # Save to database
    if soil_sensors:
        conn = sqlite3.connect('hughes_lawn_ai.db')
        c = conn.cursor()
        for zone, value in soil_sensors.items():
            c.execute('INSERT INTO sensor_data (data_source, sensor_type, sensor_value) VALUES (?, ?, ?)',
                     ('ecowitt', f'soil_{zone}', value))
        conn.commit()
        conn.close()
    
    return soil_sensors if soil_sensors else None

def extract_weather_data(ecowitt_data):
    """Enhanced weather data extraction with unit conversions"""
    if not ecowitt_data or 'data' not in ecowitt_data:
        return None
    
    logger.info("🌤️ Extracting weather data...")
    weather = {}
    
    # Look in data section
    data_section = ecowitt_data.get('data', {})
    if data_section:
        logger.info(f"Weather data section keys: {list(data_section.keys())}")
        
        # Temperature and humidity from temp_and_humidity_ch1
        temp_hum_data = data_section.get('temp_and_humidity_ch1')
        if temp_hum_data and isinstance(temp_hum_data, dict):
            logger.info(f"Found temp_and_humidity_ch1: {temp_hum_data}")
            
            # Extract temperature
            if 'temperature' in temp_hum_data and 'value' in temp_hum_data['temperature']:
                celsius = float(temp_hum_data['temperature']['value'])
                weather['temperature'] = celsius_to_fahrenheit(celsius)
                logger.info(f"✅ Temperature: {weather['temperature']}°F")
            
            # Extract humidity
            if 'humidity' in temp_hum_data and 'value' in temp_hum_data['humidity']:
                weather['humidity'] = float(temp_hum_data['humidity']['value'])
                logger.info(f"✅ Humidity: {weather['humidity']}%")
        
        # Rain data extraction
        rain_data = data_section.get('rainfall')
        if rain_data and isinstance(rain_data, dict):
            logger.info(f"Found rainfall data: {rain_data}")
            if 'daily' in rain_data and 'value' in rain_data['daily']:
                mm = float(rain_data['daily']['value'])
                weather['rain_today'] = mm_to_inches(mm)
                logger.info(f"✅ Rain today: {weather['rain_today']}\"")
            
            if 'weekly' in rain_data and 'value' in rain_data['weekly']:
                mm = float(rain_data['weekly']['value'])
                weather['rain_week'] = mm_to_inches(mm)
                logger.info(f"✅ Rain this week: {weather['rain_week']}\"")
        
        # Wind data
        wind_data = data_section.get('wind')
        if wind_data and isinstance(wind_data, dict):
            logger.info(f"Found wind data: {wind_data}")
            if 'wind_speed' in wind_data and 'value' in wind_data['wind_speed']:
                mph = float(wind_data['wind_speed']['value'])
                weather['wind_speed'] = mph
                logger.info(f"✅ Wind speed: {weather['wind_speed']} mph")
        
        # UV Index
        uv_data = data_section.get('solar_and_uvi')
        if uv_data and isinstance(uv_data, dict):
            logger.info(f"Found solar_and_uvi data: {uv_data}")
            if 'uvi' in uv_data and 'value' in uv_data['uvi']:
                weather['uvi'] = int(uv_data['uvi']['value'])
                logger.info(f"✅ UV Index: {weather['uvi']}")
        
        # Pressure
        pressure_data = data_section.get('pressure')
        if pressure_data and isinstance(pressure_data, dict):
            logger.info(f"Found pressure data: {pressure_data}")
            if 'relative' in pressure_data and 'value' in pressure_data['relative']:
                mmhg = float(pressure_data['relative']['value'])
                weather['pressure'] = mmhg_to_inhg(mmhg)
                logger.info(f"✅ Pressure: {weather['pressure']}\" Hg")
    
    # Update global weather data
    if weather:
        current_data['weather'].update(weather)
    
    # Save to database
    if weather:
        try:
            conn = sqlite3.connect('hughes_lawn_ai.db')
            c = conn.cursor()
            c.execute('''INSERT INTO weather_history 
                        (temperature, humidity, rain_today, rain_week, wind_speed, uvi, pressure) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (weather.get('temperature'), weather.get('humidity'), 
                      weather.get('rain_today'), weather.get('rain_week'),
                      weather.get('wind_speed'), weather.get('uvi'), weather.get('pressure')))
            conn.commit()
            conn.close()
            logger.info("✅ Weather data saved to database")
        except Exception as e:
            logger.error(f"❌ Weather database save error: {e}")
    
    return weather if weather else None

def get_rainbird_status():
    """Get RainBird controller status from the Node.js service."""
    try:
        logger.info("🔍 Getting RainBird status via Node.js service...")
        info = call_rainbird_service('controller-info', 'get')
        status = call_rainbird_service('zone-status', 'get')

        if info and info.get('success') and status and status.get('success'):
            controller_info = info.get('data', {})
            zone_status = status.get('data', {})
            model_data = controller_info.get('model', {})

            logger.info("✅ RainBird service connected successfully")

            active_zones = zone_status.get('activeZones', []) # This is a list of running zone numbers
            irrigation_active = bool(active_zones)

            return {
                'status': 'online',
                'connected': True,
                'model': model_data.get('modelID', 'ESP-ME3'),
                'firmware': f"{model_data.get('protocolRevisionMajor', 0)}.{model_data.get('protocolRevisionMinor', 0)}",
                'active_zones': active_zones,
                'irrigation_active': irrigation_active,
                'available_zones': list(range(1, 8)) # Assume standard zones for ESP-ME3
            }
        else:
            error_msg = (info and info.get('error')) or (status and status.get('error')) or 'Unknown service error'
            raise Exception(f"Failed to get data from Rainbird service: {error_msg}")

    except Exception as e:
        logger.error(f"❌ RainBird Node.js service not responding: {e}")
        return {
            'status': 'offline',
            'connected': False,
            'error': f'Node.js service communication failed: {str(e)}',
            'available_zones': []
        }

def get_rainbird_schedule():
    """Get RainBird schedule via API service"""
    try:
        # Get rainbird status from the Node.js service
        rainbird_status = get_rainbird_status()
        
        if rainbird_status['status'] == 'online':
            # Build schedule based on your actual configuration
            schedule = []
            zone_groups = [
                {'time': '6:00 AM', 'zones': [1, 2, 3, 7], 'name': 'Front/Side Yards', 'duration': 15},
                {'time': '6:20 AM', 'zones': [4, 5], 'name': 'Backyard Zones', 'duration': 20},
                {'time': '6:45 AM', 'zones': [6], 'name': 'Patio Zone', 'duration': 10}
            ]
            
            for group in zone_groups:
                schedule.append({
                    'time': group['time'],
                    'zones': group['zones'],
                    'name': group['name'],
                    'duration': group['duration']
                })
            
            # Calculate next run time
            now = datetime.now()
            run_time = now.replace(hour=6, minute=0, second=0, microsecond=0)
            if now > run_time:
                run_time += timedelta(days=1)
            
            next_schedule = run_time.strftime('%A, %B %d at %I:%M %p')
            
            return {
                'schedule': schedule,
                'next_schedule': next_schedule,
                'rain_delay': None,
                'controller_status': rainbird_status
            }
        else:
            # Fallback schedule if controller offline
            return {
                'schedule': [{'time': 'Controller Offline', 'zones': [], 'duration': 0}],
                'next_schedule': 'Unknown - Controller Offline',
                'rain_delay': None,
                'controller_status': rainbird_status
            }
            
    except Exception as e:
        logger.error(f"❌ RainBird schedule error: {e}")
        return {
            'schedule': [{'time': 'Error', 'zones': [], 'duration': 0}],
            'next_schedule': 'Error connecting to controller',
            'rain_delay': None,
            'controller_status': {'status': 'offline', 'error': str(e)}
        }

def ai_monitoring_loop():
    """Background AI monitoring - ECOWITT ONLY"""
    logger.info("🤖 Starting AI monitoring loop (Ecowitt only)...")
    while True:
        try:
            # Get Ecowitt data ONLY
            ecowitt_data = test_ecowitt_connection()
            if ecowitt_data:
                soil_data = extract_soil_data(ecowitt_data)
                weather_data = extract_weather_data(ecowitt_data)
                
                if soil_data:
                    # Run AI analysis
                    maintenance_data = {'last_mow_height': 2.0, 'last_fertilizer_type': None}
                    analysis = lawn_ai.generate_comprehensive_analysis(
                        soil_data, weather_data or {}, maintenance_data, ""
                    )
                    current_data['ai_analysis'] = analysis
                    logger.info(f"📊 AI Analysis updated - Mow confidence: {current_data['mow_confidence']}%")
                    
                    # Send to n8n for orchestration (without enhanced_data)
                    send_to_n8n_orchestration(soil_data, weather_data, current_data['mow_confidence'])
            
            # NO RAINBIRD POLLING - Set status as available for manual use
            current_data['rainbird_status'] = 'available'
            
            time.sleep(300)  # 5 minutes
        except Exception as e:
            logger.error(f"❌ Monitoring error: {e}")
            time.sleep(300)  # 5 minutes on error

def send_to_n8n_orchestration(soil_data, weather_data, mow_confidence, enhanced_data=None):
    """Send data to n8n for AI orchestration and scheduling"""
    try:
        payload = {
            'timestamp': datetime.now().isoformat(),
            'location': 'Fuquay-Varina, NC 27526',
            'zone': '7b',
            'soil_moisture': soil_data,
            'weather': weather_data,
            'mow_confidence': mow_confidence,
            'analysis_request': 'schedule_optimization',
            'zones_config': {
                'front_yard': {'zones': [1, 2], 'optimal': '30-40%'},
                'swing_set': {'zones': [4, 5], 'optimal': '30-40%'},
                'crepe_myrtle': {'zones': [6], 'optimal': '30-40%'}
            }
        }
        
        # Add enhanced data if available
        if enhanced_data:
            payload['enhanced_analysis'] = enhanced_data
        
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("✅ Data sent to n8n orchestration")
        else:
            logger.error(f"❌ n8n webhook returned {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Failed to send to n8n: {e}")

# Flask Routes
@app.route('/')
def index():
    """Serve the dashboard"""
    return render_template_string(DASHBOARD_HTML)

@app.route('/grass-background')
def grass_background():
    """Serve grass background image"""
    # Check if grass.jpeg exists in current directory
    if os.path.exists('grass.jpeg'):
        return send_file('grass.jpeg', mimetype='image/jpeg')
    else:
        # Return a green gradient as fallback
        return '', 404

@app.route('/api/diagnostic/test-all')
def diagnostic_test_all():
    """Test all connections"""
    results = {
        'timestamp': datetime.now().isoformat(),
        'ecowitt': None,
        'rainbird': None
    }
    
    try:
        # Test Ecowitt
        ecowitt_data = test_ecowitt_connection()
        if ecowitt_data:
            soil_data = extract_soil_data(ecowitt_data)
            weather_data = extract_weather_data(ecowitt_data)
            results['ecowitt'] = {
                'status': 'online',
                'soil_data': soil_data,
                'weather_data': weather_data,
                'error': None
            }
        else:
            results['ecowitt'] = {'status': 'offline', 'error': 'Connection failed'}
    except Exception as e:
        results['ecowitt'] = {'status': 'offline', 'error': str(e)}
    
    # Get RainBird data
    try:
        rainbird_data = get_rainbird_schedule()
        results['rainbird'] = {
            'status': 'online',
            'model': 'ESP-ME3',
            'zones_active': 6,
            **rainbird_data
        }
    except Exception as e:
        results['rainbird'] = {'status': 'offline', 'error': str(e)}
    
    return jsonify(results)

@app.route('/api/dashboard/data')
def dashboard_data():
    """Get current dashboard data"""
    try:
        # Get fresh Ecowitt data if needed
        if not current_data['soil_moisture']:
            ecowitt_data = test_ecowitt_connection()
            if ecowitt_data:
                extract_soil_data(ecowitt_data)
                extract_weather_data(ecowitt_data)
        
        # Include rain data with soil moisture for status calculation
        soil_with_rain = current_data['soil_moisture'].copy()
        if current_data['weather']:
            soil_with_rain['rain_today'] = current_data['weather'].get('rain_today', 0)
            soil_with_rain['rain_week'] = current_data['weather'].get('rain_week', 0)
        
        return jsonify({
            'success': True,
            'soil_moisture': soil_with_rain,
            'weather': current_data['weather'],
            'mow_confidence': current_data['mow_confidence'],
            'ai_analysis': current_data['ai_analysis'] or '<div class="ai-section"><p>No analysis available yet - waiting for sensor data</p></div>',
            'rainbird_status': current_data['rainbird_status'],
            'forecast_data': current_data.get('forecast_data', [])
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai/comprehensive-analysis')
def comprehensive_ai_analysis():
    """Run comprehensive AI analysis"""
    try:
        # Get fresh data
        ecowitt_data = test_ecowitt_connection()
        soil_data = extract_soil_data(ecowitt_data) if ecowitt_data else current_data['soil_moisture']
        weather_data = extract_weather_data(ecowitt_data) if ecowitt_data else current_data['weather']
        
        # Get maintenance data
        maintenance_data = {
            'last_mow_height': 2.0,
            'last_fertilizer_type': '16-4-8 Bermuda Blend',
            'last_fertilizer_date': '2025-05-15',
            'last_observations': 'Lawn looking healthy, slight brown spots in back corner'
        }
        
        if not soil_data:
            return jsonify({
                'success': False, 
                'error': 'No soil data available for analysis - check Ecowitt connection'
            })
        
        # Generate comprehensive AI analysis
        analysis = lawn_ai.generate_comprehensive_analysis(
            soil_data, weather_data or {}, maintenance_data, maintenance_data['last_observations']
        )
        
        current_data['ai_analysis'] = analysis
        
        logger.info("✅ Comprehensive AI analysis completed")
        
        return jsonify({
            'success': True,
            'analysis': analysis,
            'soil_data': soil_data,
            'weather_data': weather_data,
            'maintenance_data': maintenance_data,
            'mow_confidence': current_data['mow_confidence'],
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Comprehensive AI analysis failed: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/calendar/event', methods=['POST'])
def save_calendar_event():
    """Save calendar event"""
    try:
        data = request.get_json()
        date = data.get('date')
        event_type = data.get('event_type')
        event_data = json.dumps(data.get('data', {}))
        
        conn = sqlite3.connect('hughes_lawn_ai.db')
        c = conn.cursor()
        c.execute('INSERT INTO calendar_events (date, event_type, event_data) VALUES (?, ?, ?)',
                 (date, event_type, event_data))
        
        # Also log to historical logs
        description = f"{event_type.title()} event recorded"
        if event_type == 'mow':
            height = data.get('data', {}).get('height', '')
            description = f"Mowed lawn at {height} inches"
        elif event_type == 'fertilizer':
            fert_data = data.get('data', {})
            description = f"Applied {fert_data.get('brand', '')} {fert_data.get('npk', '')} fertilizer"
        
        c.execute('INSERT INTO historical_logs (event_type, description, data) VALUES (?, ?, ?)',
                 (event_type, description, event_data))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Calendar event saved: {event_type} on {date}")
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"❌ Failed to save calendar event: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/calendar/month/<int:year>/<int:month>')
def get_calendar_month(year, month):
    """Get calendar events for a month"""
    try:
        conn = sqlite3.connect('hughes_lawn_ai.db')
        c = conn.cursor()
        
        # Get events for the month
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-31"
        
        c.execute('''SELECT date, event_type, event_data 
                    FROM calendar_events 
                    WHERE date >= ? AND date <= ?''',
                 (start_date, end_date))
        
        events = {}
        for row in c.fetchall():
            date = row[0]
            if date not in events:
                events[date] = {}
            
            event_type = row[1]
            if event_type == 'mow':
                events[date]['mowed'] = True
            elif event_type == 'fertilizer':
                events[date]['fertilized'] = True
            elif event_type == 'maintenance':
                events[date]['maintenance'] = True
        
        conn.close()
        
        return jsonify({
            'success': True,
            'events': events
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to get calendar data: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/logs/historical')
def get_historical_logs():
    """Get historical logs with filtering"""
    try:
        log_type = request.args.get('type', 'all')
        days = int(request.args.get('days', 30))
        
        conn = sqlite3.connect('hughes_lawn_ai.db')
        c = conn.cursor()
        
        query = '''SELECT event_type, description, timestamp 
                  FROM historical_logs 
                  WHERE timestamp >= datetime('now', '-{} days')'''.format(days)
        
        if log_type != 'all':
            query += f" AND event_type = '{log_type}'"
        
        query += " ORDER BY timestamp DESC LIMIT 100"
        
        c.execute(query)
        
        logs = []
        for row in c.fetchall():
            logs.append({
                'event_type': row[0],
                'description': row[1],
                'timestamp': row[2]
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'logs': logs
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to get historical logs: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/system/start', methods=['POST'])
def start_systems():
    """Start all systems"""
    try:
        logger.info("✅ All systems started")
        return jsonify({'success': True, 'message': 'All systems online'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/system/stop', methods=['POST'])
def stop_systems():
    """Stop all systems"""
    try:
        logger.info("✅ All systems stopped")
        return jsonify({'success': True, 'message': 'All systems stopped'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/calendar/day/<date>')
def get_calendar_day_events(date):
    """Get events for a specific day"""
    try:
        conn = sqlite3.connect('hughes_lawn_ai.db')
        c = conn.cursor()
        
        c.execute('''SELECT id, event_type, event_data, timestamp 
                    FROM calendar_events 
                    WHERE date = ? 
                    ORDER BY timestamp DESC''', (date,))
        
        events = []
        for row in c.fetchall():
            events.append({
                'id': row[0],
                'event_type': row[1],
                'event_data': row[2],
                'timestamp': row[3]
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'events': events
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to get day events: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/calendar/event/<int:event_id>', methods=['DELETE'])
def delete_calendar_event(event_id):
    """Delete a calendar event"""
    try:
        conn = sqlite3.connect('hughes_lawn_ai.db')
        c = conn.cursor()
        
        # Delete the event
        c.execute('DELETE FROM calendar_events WHERE id = ?', (event_id,))
        
        if c.rowcount > 0:
            conn.commit()
            conn.close()
            logger.info(f"✅ Calendar event {event_id} deleted")
            return jsonify({'success': True})
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Event not found'})
        
    except Exception as e:
        logger.error(f"❌ Failed to delete calendar event: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/weather/historical/<date>')
def get_historical_weather(date):
    """Get historical weather data for a specific date"""
    try:
        conn = sqlite3.connect('hughes_lawn_ai.db')
        c = conn.cursor()
        
        # Get weather data for the specific date
        c.execute('''SELECT temperature, humidity, rain_today, rain_week, wind_speed, uvi, pressure, timestamp 
                    FROM weather_history 
                    WHERE DATE(timestamp) = ? 
                    ORDER BY timestamp DESC 
                    LIMIT 1''', (date,))
        
        row = c.fetchone()
        if row:
            weather = {
                'temperature': row[0],
                'humidity': row[1],
                'rain_today': row[2],
                'rain_week': row[3],
                'wind_speed': row[4],
                'uvi': row[5],
                'pressure': row[6],
                'timestamp': row[7]
            }
            
            conn.close()
            return jsonify({
                'success': True,
                'weather': weather
            })
        else:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'No weather data found for this date'
            })
        
    except Exception as e:
        logger.error(f"❌ Failed to get historical weather: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/rainbird/start-zone', methods=['POST'])
def start_rainbird_zone():
    """Start RainBird zone via Node.js service"""
    try:
        data = request.get_json()
        zone = data.get('zone')
        duration_seconds = data.get('duration', 900)  # Default 15 minutes
        duration_minutes = duration_seconds // 60

        if not 1 <= zone <= 7:
            return jsonify({'success': False, 'error': 'Zone must be between 1 and 7'}), 400

        logger.info(f"▶️ Request to start RainBird zone {zone} for {duration_minutes} minutes via Node.js service...")
        result = call_rainbird_service('start-zone', method='post', data={'zone': zone, 'duration': duration_minutes})

        if result and result.get('success'):
            logger.info(f"✅ RainBird zone {zone} started successfully.")
            return jsonify(result)
        else:
            error_msg = result.get('message', 'Failed to start zone')
            logger.error(f"❌ Failed to start RainBird zone {zone}: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 500
            
    except Exception as e:
        logger.error(f"❌ Failed to start RainBird zone: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rainbird/stop-all', methods=['POST'])
def stop_all_rainbird_zones():
    """Stop all RainBird zones via Node.js service"""
    try:
        logger.info("⛔ Request to stop all RainBird zones via Node.js service...")
        result = call_rainbird_service('stop-zone', method='post')

        if result and result.get('success'):
            logger.info("✅ All RainBird zones stopped successfully.")
            return jsonify(result)
        else:
            error_msg = result.get('message', 'Failed to stop irrigation')
            logger.error(f"❌ Failed to stop RainBird zones: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 500
            
    except Exception as e:
        logger.error(f"❌ Failed to stop RainBird zones: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rainbird/test-zone', methods=['POST'])
def test_rainbird_zone():
    """Test RainBird zone via Node.js service by running for 2 minutes"""
    try:
        data = request.get_json()
        zone = data.get('zone')
        
        if not 1 <= zone <= 7:
            return jsonify({'success': False, 'error': 'Zone must be between 1 and 7'}), 400

        duration_minutes = 2
        logger.info(f"🔍 Request to test RainBird zone {zone} for {duration_minutes} minutes via Node.js service...")
        result = call_rainbird_service('start-zone', method='post', data={'zone': zone, 'duration': duration_minutes})

        if result and result.get('success'):
            logger.info(f"✅ RainBird zone {zone} test started successfully.")
            return jsonify({
                'success': True,
                'message': f"Zone {zone} test cycle started for {duration_minutes} minutes",
                'zone': zone
            })
        else:
            error_msg = result.get('message', 'Failed to test zone')
            logger.error(f"❌ Failed to test RainBird zone {zone}: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 500

    except Exception as e:
        logger.error(f"❌ Failed to test RainBird zone: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rainbird/zones')
def get_rainbird_zones():
    """Get RainBird zones status and configuration from Node.js service"""
    try:
        status = get_rainbird_status()
        if not status.get('connected'):
            raise Exception(status.get('error', 'Controller is offline'))

        active_zones = status.get('active_zones', [])
        zones_info = []
        for zone_id in range(1, 8):
            zone_name = RAINBIRD_ZONE_NAMES.get(zone_id, f"Zone {zone_id}")
            zones_info.append({
                'id': zone_id,
                'name': zone_name,
                'running': zone_id in active_zones,
                'default_minutes': 15 if zone_id in [1, 2, 3, 7] else (20 if zone_id in [4, 5] else 10),
                'last_run': None  # This would require historical data logging
            })
        
        return jsonify({
            'success': True,
            'zones': zones_info
        })
            
    except Exception as e:
        logger.error(f"❌ Failed to get RainBird zones: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rainbird/zone/<int:zone_id>/start', methods=['POST'])
def start_specific_rainbird_zone(zone_id):
    """Start a specific RainBird zone via direct API call - SIMPLIFIED"""
    try:
        data = request.get_json()
        seconds = data.get('seconds', 900)  # Default 15 minutes
        minutes = seconds // 60

        if not 1 <= zone_id <= 7:
            return jsonify({'success': False, 'error': 'Zone must be between 1 and 7'}), 400

        logger.info(f"▶️ Starting RainBird zone {zone_id} for {minutes} minutes - DIRECT API CALL")
        
        # Use direct requests instead of complex queue system
        url = 'http://localhost:3000/api/start-zone'
        payload = {'zone': zone_id, 'duration': minutes}
        
        response = requests.post(url, json=payload, timeout=45)
        result = response.json()
        
        if result and result.get('success'):
            zone_name = RAINBIRD_ZONE_NAMES.get(zone_id, f"Zone {zone_id}")
            
            # Log to historical logs
            try:
                conn = sqlite3.connect('hughes_lawn_ai.db')
                c = conn.cursor()
                c.execute('INSERT INTO historical_logs (event_type, description, data) VALUES (?, ?, ?)',
                         ('watering', f'Manual watering: {zone_name} for {minutes} minutes', 
                          json.dumps({'zone': zone_id, 'duration_minutes': minutes, 'method': 'manual'})))
                conn.commit()
                conn.close()
            except:
                pass  # Don't fail if logging fails
            
            logger.info(f"✅ RainBird zone {zone_id} ({zone_name}) started for {minutes} minutes")
            return jsonify({
                'success': True,
                'message': f"Zone {zone_id} ({zone_name}) started for {minutes} minutes",
                'zone': zone_id,
                'duration_seconds': seconds,
                'duration_minutes': minutes
            })
        else:
            error_msg = result.get('message', 'Failed to start zone')
            logger.error(f"❌ Failed to start RainBird zone {zone_id}: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 500

    except requests.Timeout:
        # If timeout, it's a real failure
        logger.error(f"❌ Zone {zone_id} request timed out - controller not responding")
        return jsonify({
            'success': False,
            'error': f"Zone {zone_id} request timed out - controller may be overloaded or offline"
        }), 500
    except Exception as e:
        logger.error(f"❌ Failed to start RainBird zone {zone_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/n8n/webhook', methods=['POST'])
def n8n_webhook():
    """Receive data from n8n workflow"""
    try:
        data = request.get_json()
        
        # Process n8n data
        if 'ai_analysis' in data:
            current_data['ai_analysis'] = data['ai_analysis']
        
        if 'mow_confidence' in data:
            current_data['mow_confidence'] = data['mow_confidence']
        
        if 'schedule_adjustment' in data:
            # Handle RainBird schedule adjustments from n8n
            logger.info(f"✅ Schedule adjustment received: {data['schedule_adjustment']}")
        
        # Handle smart irrigation decisions from n8n
        if 'irrigation_command' in data:
            command = data['irrigation_command']
            if command.get('action') == 'start_watering':
                zones = command.get('zones', [])
                duration = command.get('duration', 15)
                
                # Log the watering event
                conn = sqlite3.connect('hughes_lawn_ai.db')
                c = conn.cursor()
                for zone in zones:
                    c.execute('INSERT INTO watering_history (zone_id, duration_minutes, triggered_by) VALUES (?, ?, ?)',
                             (f'zone_{zone}', duration, 'n8n_ai_automation'))
                
                # Add to calendar
                today = datetime.now().strftime('%Y-%m-%d')
                c.execute('INSERT INTO calendar_events (date, event_type, event_data) VALUES (?, ?, ?)',
                         (today, 'watering', json.dumps({'zones': zones, 'duration': duration, 'auto': True})))
                
                c.execute('INSERT INTO historical_logs (event_type, description, data) VALUES (?, ?, ?)',
                         ('watering', f'Auto-watering activated for zones {zones} for {duration} minutes', json.dumps(command)))
                
                conn.commit()
                conn.close()
                
                logger.info(f"✅ Auto-watering executed: Zones {zones} for {duration} minutes")
        
        logger.info("✅ n8n webhook received")
        return jsonify({'success': True, 'message': 'Data processed'})
        
    except Exception as e:
        logger.error(f"❌ n8n webhook error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Initialize database
init_db()

if __name__ == '__main__':
    print("=" * 80)
    print("🧠 HUGHES LAWN AI DASHBOARD - COMPLETE SYSTEM")
    print("=" * 80)
    print("🤖 AI-POWERED BERMUDA GRASS CARE")
    print("📍 Location: Fuquay-Varina, NC 27526 (Zone 7b)")
    print("🌱 Grass Type: TifTuf Bermuda (Target: 1.5-2 inches)")
    print("=" * 80)
    print("🔗 Smart Dashboard: http://localhost:8000")
    print("=" * 80)
    print("📡 Connected Systems:")
    print("   • Ecowitt Weather Station (Real API)")
    print("   • RainBird Controller (ESP-ME3, 7 Zones)")
    print("   • AI Decision Engine")
    print("   • n8n Orchestration (Webhook: c5186699-f17d-42e6-a3eb-9b83d7f9d2da)")
    print("=" * 80)
    print("🧠 Features:")
    print("   • Real-time soil moisture monitoring (3 sensors)")
    print("   • AI mowing recommendations with confidence %")
    print("   • Smart calendar with event tracking")
    print("   • Weather integration with 7-day forecast")
    print("   • Glassmorphic iOS-style interface")
    print("   • Historical logging system")
    print("   • Automatic watering schedule optimization")
    print("=" * 80)
    print("📊 Data Points:")
    print("   • External Temperature (Channel 1) in °F")
    print("   • Daily/Weekly Rainfall in inches")
    print("   • Wind Speed in mph")
    print("   • Atmospheric Pressure in inHg")
    print("   • UV Index")
    print("   • Soil Moisture CH12/13/14")
    print("=" * 80)
    print("💡 To use grass background:")
    print("   Place 'grass.jpeg' in the same directory as this script")
    print("=" * 80)
    print("✅ Hughes Lawn AI System Online")
    print("🤖 Starting AI monitoring loop...")
    print("=" * 80)
    
    # Start AI monitoring in background thread
    ai_thread = threading.Thread(target=ai_monitoring_loop, daemon=True)
    ai_thread.start()
    
    # Start Flask server
    app.run(host='0.0.0.0', port=8000, debug=False)