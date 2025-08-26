#!/bin/bash

# Hughes Lawn AI Stop Script
# Double-click this file to stop the system

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=================================="
echo "🛑 HUGHES LAWN AI STOP"
echo "=================================="
echo ""
echo "📍 Location: $SCRIPT_DIR"
echo ""
echo "Stopping the Hughes Lawn AI system..."
echo ""

# Change to the script directory
cd "$SCRIPT_DIR"

# Run the stop system script
echo "🔄 Shutting down services..."
./stop_system.sh

echo ""
echo "✅ Hughes Lawn AI has been stopped!"
echo ""
echo "Press any key to close this window..."
read -n 1 -s

exit 0
