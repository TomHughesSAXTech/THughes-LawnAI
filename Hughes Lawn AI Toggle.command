#!/bin/bash

# Hughes Lawn AI Toggle Script
cd "/Users/tom/Desktop/Hughes Lawn AI"

# Check if system is running
if pgrep -f "hughes_lawn_ai.py" > /dev/null || pgrep -f "rainbird-controller.js" > /dev/null; then
    # System is running, stop it
    osascript -e 'display notification "Stopping Hughes Lawn AI System..." with title "Hughes Lawn AI"'
    bash stop_system.sh
    osascript -e 'display notification "Hughes Lawn AI System Stopped" with title "Hughes Lawn AI"'
    echo "✅ Hughes Lawn AI System Stopped"
else
    # System not running, start it
    osascript -e 'display notification "Starting Hughes Lawn AI System..." with title "Hughes Lawn AI"'
    bash start_system.sh > /dev/null 2>&1 &
    sleep 3
    osascript -e 'display notification "Hughes Lawn AI System Started" with title "Hughes Lawn AI"'
    echo "✅ Hughes Lawn AI System Started"
fi

echo ""
echo "Press any key to close this window..."
read -n 1
