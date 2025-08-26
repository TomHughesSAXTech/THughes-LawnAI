#!/bin/bash

# Rainbird Irrigation Controller Startup Script
# Navigate to this directory and start the controller

# Add Homebrew to PATH
export PATH="/opt/homebrew/bin:$PATH"

echo "🌱 Starting Rainbird Irrigation Controller..."
echo ""
echo "📡 Controller: 192.168.5.17"
echo "🔑 PIN: 886004"
echo ""
echo "🌐 Web Interface will be available at:"
echo "   http://localhost:3000"
echo ""
echo "🚿 Your Custom Zones:"
echo "   Zone 1: Elect Boxes & BBall"
echo "   Zone 2: Front Lawn"
echo "   Zone 3: Side Yard Left Side"
echo "   Zone 4: Back Yard Fence"
echo "   Zone 5: Back Yard Middle"
echo "   Zone 6: Back Yard Patio"
echo "   Zone 7: Side Yard HVAC Side"
echo ""
echo "Press Ctrl+C to stop the controller"
echo ""

# Start the Node.js server
node rainbird-controller.js
