#!/usr/bin/env python3
"""
Azure App Service startup file for Hughes Lawn AI
"""
import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the Flask app
from hughes_lawn_ai import app

if __name__ == "__main__":
    # Azure App Service will handle the port binding
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
