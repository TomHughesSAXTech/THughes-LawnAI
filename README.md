# 🌱 Hughes Lawn AI - Complete Lawn Management System

A comprehensive AI-powered lawn care system integrating weather monitoring, soil moisture sensors, irrigation control, and intelligent mowing recommendations.

## 🏗️ System Architecture

```
Hughes Lawn AI/
├── hughes_lawn_ai.py          # Main Flask application
├── hughes_lawn_env/           # Python virtual environment
├── hughes_lawn_ai.db          # SQLite database
├── hughes_lawn_ai.log         # Application logs
├── start_system.sh            # Start all services
├── stop_system.sh             # Stop all services
├── rainbird/                  # RainBird irrigation controller
│   ├── rainbird-controller.js # Node.js backend API
│   ├── rainbird-interface.html# Web interface
│   ├── patched-rainbird.js    # Patched library
│   ├── start-rainbird.sh      # RainBird startup script
│   └── node_modules/          # Node.js dependencies
└── README.md                  # This file
```

## 🚀 Quick Start

### Start the Complete System
```bash
cd "/Users/tom/Desktop/Hughes Lawn AI"
./start_system.sh
```

### Stop the Complete System
```bash
cd "/Users/tom/Desktop/Hughes Lawn AI"
./stop_system.sh
```

## 🌐 Access Points

- **Hughes Lawn AI Dashboard**: http://localhost:8000
- **RainBird Controller**: http://localhost:3000

## 📊 Features

### 🤖 AI Dashboard (Port 8000)
- **Real-time Monitoring**: Soil moisture from 3 sensors
- **Weather Integration**: Ecowitt weather station data
- **AI Recommendations**: Intelligent mowing suggestions with confidence %
- **Smart Calendar**: Event tracking and scheduling
- **Zone Control**: Direct irrigation zone management
- **Historical Data**: SQLite database logging

### 🚿 Irrigation Control (Port 3000)
- **7-Zone Management**: Individual zone start/stop
- **Emergency Stop**: Stop all zones instantly
- **Status Monitoring**: Real-time zone status
- **Direct Hardware**: ESP-ME3 controller (192.168.5.17)

## 🔧 Configuration

### Hardware Setup
- **RainBird Controller**: ESP-ME3 at 192.168.5.17
- **Controller PIN**: 886004
- **Ecowitt Weather Station**: Real API integration
- **Soil Sensors**: 3 moisture sensors (CH12, CH13, CH14)

### Zone Configuration
1. **Zone 1**: Elect Boxes & BBall
2. **Zone 2**: Front Lawn
3. **Zone 3**: Side Yard Left Side
4. **Zone 4**: Back Yard Fence
5. **Zone 5**: Back Yard Middle
6. **Zone 6**: Back Yard Patio
7. **Zone 7**: Side Yard HVAC Side

## 📈 Data Sources

### Weather Data (Every 5 minutes)
- External Temperature (°F)
- Humidity (%)
- Daily/Weekly Rainfall (inches)
- Wind Speed (mph)
- Atmospheric Pressure (inHg)
- UV Index

### Soil Moisture (Real-time)
- **crepe_myrtle**: Sensor CH12
- **swing_set**: Sensor CH13
- **front_yard**: Sensor CH14

## 🧠 AI Features

### Mowing Recommendations
- **Confidence Scoring**: 0-100% recommendation strength
- **Weather Integration**: Rain, temperature, humidity factors
- **Soil Conditions**: Moisture level analysis
- **Growth Patterns**: Historical data analysis

### Smart Scheduling
- **Optimal Timing**: 6 AM watering schedule
- **Weather Awareness**: Rain delay integration
- **Soil-based Adjustments**: Moisture-driven decisions

## 🔍 Monitoring

### Service Logs
- **Hughes Lawn AI**: `hughes_lawn_ai_service.log`
- **RainBird**: `rainbird/rainbird_service.log`

### Database
- **Location**: `hughes_lawn_ai.db`
- **Type**: SQLite
- **Contains**: Weather data, soil readings, AI decisions, events

## 🛠️ Troubleshooting

### Common Issues

**Services Won't Start**
```bash
# Check if ports are in use
lsof -i :8000
lsof -i :3000

# Force stop existing processes
pkill -f "hughes_lawn_ai.py"
pkill -f "rainbird-controller.js"
```

**RainBird Connection Issues**
- Ensure controller at 192.168.5.17 is powered and connected
- Avoid continuous pings to controller (causes overload)
- Check network connectivity: `ping 192.168.5.17`

**Database Issues**
```bash
# Backup current database
cp hughes_lawn_ai.db hughes_lawn_ai.db.backup

# Check database integrity
sqlite3 hughes_lawn_ai.db "PRAGMA integrity_check;"
```

## 📞 Support

### System Requirements
- **macOS**: Tested on macOS with zsh
- **Python**: 3.13+ with virtual environment
- **Node.js**: For RainBird controller
- **Network**: Access to 192.168.5.17 and internet for weather data

### Key Dependencies
- **Python**: Flask, requests, sqlite3, datetime
- **Node.js**: Express, HTTPS, file system modules
- **Hardware**: RainBird ESP-ME3, Ecowitt weather station

---

🌱 **Hughes Lawn AI** - Intelligent lawn care for the modern home
# Force deployment refresh
