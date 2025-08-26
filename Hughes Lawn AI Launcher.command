#!/bin/bash

# Hughes Lawn AI Launcher Script
# Double-click this file to start the system

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=================================="
echo "🌱 HUGHES LAWN AI LAUNCHER"
echo "=================================="
echo ""
echo "📍 Location: $SCRIPT_DIR"
echo ""
echo "Starting the complete Hughes Lawn AI system..."
echo "This includes:"
echo "  🚿 RainBird Irrigation Controller"
echo "  🧠 AI Dashboard & Analytics" 
echo "  🌤️  Weather Station Integration"
echo ""

# Change to the script directory
cd "$SCRIPT_DIR"

# Run the start system script
echo "🚀 Launching system..."
./start_system.sh

echo ""
echo "✅ Hughes Lawn AI is now running!"
echo ""
echo "🌐 Open in browser:"
echo "   Dashboard:  http://localhost:8000"
echo "   RainBird:   http://localhost:3000"
echo ""
echo "🔍 Opening dashboard in your browser..."

# Wait a moment then open the browser
sleep 2
open http://localhost:8000

echo ""
echo "✨ Hughes Lawn AI is ready to use!"
echo ""
echo "Press any key to close this window..."
read -n 1 -s

exit 0
