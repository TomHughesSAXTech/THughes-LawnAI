from flask import Flask, jsonify, send_file
from datetime import datetime
import os

app = Flask(__name__)

HTML = """<!DOCTYPE html><html><head><title>Hughes Lawn AI</title>
<style>body{background:url(/grass-background) center/cover;color:white;font-family:sans-serif;padding:20px}
.container{background:rgba(0,0,0,0.7);padding:30px;border-radius:15px;max-width:1200px;margin:auto}
h1{color:#4ade80}</style></head><body><div class="container">
<h1>Hughes Lawn AI Dashboard</h1>
<p>Weather: 89°F | Humidity: 47% | RainBird: q0852082.eero.online</p>
<p>Front Yard: 40% | Backyard: 60% | Crepe Myrtle: 67%</p>
</div></body></html>"""

@app.route("/")
def home(): return HTML

@app.route("/grass-background")
def bg():
    try: return send_file("grass.jpeg", mimetype="image/jpeg")
    except: return "", 404

@app.route("/api/status")
def status(): return jsonify({"status":"online","timestamp":datetime.now().isoformat()})

@app.route("/health")
def health(): return jsonify({"status":"healthy"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
