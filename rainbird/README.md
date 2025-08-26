# 🌱 Rainbird Irrigation Automation System

**Professional irrigation control system for your Rainbird controller with custom zone management.**

## 🚀 Quick Start

### Method 1: Double-click to start
1. Double-click `start-rainbird.sh` in this folder
2. Open your web browser to http://localhost:3000
3. Start controlling your irrigation zones!

### Method 2: Terminal start
1. Open Terminal
2. Navigate to this folder: `cd "/Users/tom/Desktop/Rainbird Automation"`
3. Run: `./start-rainbird.sh`
4. Open your web browser to http://localhost:3000

## 🚿 Your Custom Zones

- **Zone 1:** Elect Boxes & BBall
- **Zone 2:** Front Lawn  
- **Zone 3:** Side Yard Left Side
- **Zone 4:** Back Yard Fence
- **Zone 5:** Back Yard Middle
- **Zone 6:** Back Yard Patio
- **Zone 7:** Side Yard HVAC Side

## 📡 System Configuration

- **Controller IP:** 192.168.5.17
- **PIN:** 886004
- **Protocol:** HTTPS with AES encryption
- **Web Interface:** http://localhost:3000

## 🎯 Features

✅ **Individual Zone Control** - Start/stop any zone with custom durations  
✅ **Emergency Stop** - Instant stop all zones  
✅ **Custom Zone Names** - Easy identification of irrigation areas  
✅ **Mobile Responsive** - Works on phones, tablets, and computers  
✅ **Timeout Protection** - No hanging interface  
✅ **Retry Logic** - Reliable connection handling  
✅ **Real-time Status** - Live zone status updates  

## 🛠 How to Use

1. **Start a Zone:**
   - Select duration (1-30 minutes)
   - Click "🚿 Start Zone X"
   - Watch for confirmation message

2. **Stop a Zone:**
   - Click "⛔ Stop Zone X" 
   - Or use "⛔ STOP ALL ZONES" for emergency

3. **Check Status:**
   - Click "📊 Zone Status" to see active zones
   - Click "ℹ️ Controller Info" for system details

## 🔧 Troubleshooting

**If zones don't start:**
- Check that controller IP 192.168.5.17 is reachable
- Verify PIN 886004 is correct
- Try the "⛔ STOP ALL ZONES" first, then restart zone

**If interface hangs:**
- Wait 15 seconds for timeout
- Refresh the web page
- Restart the controller with Ctrl+C and run again

**If nothing works:**
- Check your network connection
- Restart your Rainbird LNK2 module
- Run `./start-rainbird.sh` again

## 📁 File Structure

- `rainbird-controller.js` - Main server application
- `rainbird-interface.html` - Web interface
- `patched-rainbird.js` - HTTPS-compatible Rainbird library
- `start-rainbird.sh` - Easy startup script
- `package.json` - Node.js dependencies
- `node_modules/` - Required libraries

## 🔒 Security

- Uses HTTPS with SSL certificate verification disabled for self-signed certs
- AES-256 encryption for all communication with controller
- PIN-based authentication
- Local network access only

## 📞 Support

This system was custom-built for your specific Rainbird controller setup. All zones are tested and working with proper timeout handling and retry logic.

**To stop the system:** Press `Ctrl+C` in the terminal

**To restart:** Run `./start-rainbird.sh` again

---

*Built with Node.js, Express, and the Rainbird SIP protocol. Professional irrigation automation made simple.*
