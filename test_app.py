#!/usr/bin/env python3
"""
Minimal Flask app to test Railway deployment
"""
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "message": "Minimal test app is running",
        "port": os.environ.get('PORT', '5000')
    })

@app.route('/test')
def test():
    """Test endpoint"""
    return jsonify({
        "status": "ok",
        "message": "Test endpoint working",
        "env_vars": {
            "PORT": os.environ.get('PORT'),
            "JOB_ENDPOINT": os.environ.get('JOB_ENDPOINT'),
            "DISCORD_BOT_TOKEN": "***" if os.environ.get('DISCORD_BOT_TOKEN') else None
        }
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Starting minimal test app on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
