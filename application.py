#!/usr/bin/env python3
from flask import Flask, jsonify, send_file
from datetime import datetime
import os

app = Flask(__name__)

@app.route('/')
def index():
    return 'Hughes Lawn AI is running!'

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
