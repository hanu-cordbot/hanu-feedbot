# === FILE: app.py ===

import os
from datetime import datetime, timezone
from flask import Flask, jsonify, abort, render_template, request, redirect, url_for, Response, session, flash, send_from_directory
from dotenv import load_dotenv
from functools import wraps
import hashlib
import json
import re  # for password hashing check
import feedparser
import requests  # for Discord API lookups
import redis
from redis import Redis
from typing import cast, Optional
from bot.formatter import build_prompt  # Import build_prompt function

# Optional Celery imports - fallback to direct execution if not available
try:
    from celery_app import run_discord_bot_job, fetch_feed_meta
    CELERY_AVAILABLE = True
    print("✅ Celery imports available")
except ImportError as e:
    print(f"⚠️ Celery not available: {e}")
    CELERY_AVAILABLE = False
    run_discord_bot_job = None
    fetch_feed_meta = None

# Data directory for persistent storage (mount a volume here)
DATA_DIR = os.environ.get('DATA_DIR', os.getcwd())
os.makedirs(DATA_DIR, exist_ok=True)
# Channels storage
CHANNELS_FILE = os.path.join(DATA_DIR, "channels.json")
# Feed→Channel map storage
FEED_MAP_FILE = os.path.join(DATA_DIR, "feed_map.json")
# Feed grouping storage
GROUPS_FILE = os.path.join(DATA_DIR, "groups.json")
# System prompt storage
PROMPT_FILE = os.path.join(DATA_DIR, "system_prompt.json")
# Cached feed metadata storage
FEED_META_FILE = os.path.join(DATA_DIR, "feed_meta.json")
# Feeds list storage
FEEDS_FILE = os.path.join(DATA_DIR, "feeds.txt")

# Ensure default storage files exist (excluding channels which should be a list)
for _path in (FEED_MAP_FILE, GROUPS_FILE, FEED_META_FILE):
    if not os.path.exists(_path):
        with open(_path, 'w', encoding='utf-8') as _f:
            json.dump({}, _f)
# Ensure channels file exists as a list
if not os.path.exists(CHANNELS_FILE):
    with open(CHANNELS_FILE, 'w', encoding='utf-8') as _f:
        json.dump([], _f)
# Ensure prompt file exists
if not os.path.exists(PROMPT_FILE):
    with open(PROMPT_FILE, 'w', encoding='utf-8') as _f:
        json.dump([], _f)
# Ensure feeds list exists
if not os.path.exists(FEEDS_FILE):
    open(FEEDS_FILE, 'w').close()

# Load environment variables from .env file at the very beginning
load_dotenv()
# Redis client for real-time status and metrics (optional)
REDIS_URL = os.environ.get("REDIS_URL")
redis_client: Optional[Redis] = None

if REDIS_URL:
    try:
        redis_client = cast(Redis, redis.from_url(REDIS_URL))
        # Test connection
        redis_client.ping()
        print("✅ Redis connected successfully")
    except Exception as e:
        print(f"⚠️ Redis connection failed: {e}")
        redis_client = None
else:
    print("⚠️ Redis not configured - running without real-time metrics")

# --- SECURITY UPDATE ---
# Get the secret endpoint from an environment variable.
# Job endpoint configuration - with fallback for Railway deployment
JOB_ENDPOINT = os.environ.get("JOB_ENDPOINT", "/cron-job-default")
print(f"📋 Job endpoint configured: {JOB_ENDPOINT}")

# Ensure the endpoint starts with a slash for the Flask route
if not JOB_ENDPOINT.startswith('/'):
    JOB_ENDPOINT = f'/{JOB_ENDPOINT}'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, 'docs')
app = Flask(__name__)
# Serve public static pages from the docs directory
@app.route('/')
@app.route('/index.html')
def serve_index():
    return send_from_directory(DOCS_DIR, 'index.html')
@app.route('/<path:filename>')
def serve_docs(filename):
    return send_from_directory(DOCS_DIR, filename)
# Jinja filter to display relative times (e.g., '2 hours ago')
@app.template_filter('relativetime')
def relative_time(dt):
    if not dt:
        return ''
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    secs = int(diff.total_seconds())
    if secs < 60:
        unit = 'second' if secs == 1 else 'seconds'
        return f"{secs} {unit} ago"
    mins = int(secs / 60)
    if mins < 60:
        unit = 'minute' if mins == 1 else 'minutes'
        return f"{mins} {unit} ago"
    hrs = int(mins / 60)
    if hrs < 24:
        unit = 'hour' if hrs == 1 else 'hours'
        return f"{hrs} {unit} ago"
    days = int(hrs / 24)
    if days < 7:
        unit = 'day' if days == 1 else 'days'
        return f"{days} {unit} ago"
    weeks = int(days / 7)
    if weeks < 4:
        unit = 'week' if weeks == 1 else 'weeks'
        return f"{weeks} {unit} ago"
    months = int(days / 30)
    if months < 12:
        unit = 'month' if months == 1 else 'months'
        return f"{months} {unit} ago"
    years = int(days / 365)
    unit = 'year' if years == 1 else 'years'
    return f"{years} {unit} ago"

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
# Accept a plain-text admin password via ADMIN_PASS
ADMIN_PASS = os.environ.get("ADMIN_PASS", "hyperdelusionsinallofexistence")

app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# CORS configuration for GitHub Pages and local development
from flask_cors import CORS
# Allow GitHub Pages site and Railway backend URL
CORS(app, origins=[
    # Only allow via Cloudflare Worker proxy
    "https://hanu-api-proxy.snacky496.workers.dev"
])

# === ESSENTIAL API ENDPOINTS ===

@app.route('/api/health')
def health():
    """Health check endpoint for Railway and monitoring"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "hanu-feedbot-enhanced",
        "version": "2.0.0",
        "endpoints": {
            "job": JOB_ENDPOINT,
            "dashboard": "/",
            "api": "/api/"
        }
    })

# Authentication bridge for JWT-like tokens
@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """JWT-compatible login endpoint for dashboard"""
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password", "").encode()
    # Accept raw password match
    if username == ADMIN_USER and password.decode() == ADMIN_PASS:
        import base64, time
        token_data = {"user": username, "exp": int(time.time()) + 3600}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()
        return jsonify({"success": True, "token": token})
    return jsonify({"success": False, "error": "Invalid credentials"}), 401

@app.route('/api/status')
def api_status():
    """Endpoint to check token validity"""
    if not verify_api_token():
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"status": "ok"}), 200
    
@app.route('/api/reset-summary', methods=['POST'])
def api_reset_summary():
    if not verify_api_token():
        return jsonify({"error": "Authentication required"}), 401
    # Stub: reset any daily summary state if applicable
    return jsonify({"success": True, "message": "Daily summary reset"}), 200

@app.route('/api/cache', methods=['DELETE'])
def api_clear_cache():
    if not verify_api_token():
        return jsonify({"error": "Authentication required"}), 401
    # Clear avatar cache
    try:
        with open(os.path.join(DATA_DIR, 'avatar_cache.json'), 'w') as f:
            json.dump({}, f)
    except Exception:
        pass
    return jsonify({"success": True, "message": "Cache cleared"}), 200

@app.route('/api/run-job', methods=['POST'])
def api_run_job():
    """Trigger the background Discord RSS bot run job"""
    if not verify_api_token():
        return jsonify({"error": "Authentication required"}), 401
    try:
        # Use enhanced cron worker instead of Celery
        if CELERY_AVAILABLE and run_discord_bot_job:
            # Use Celery if available
            run_discord_bot_job.delay()  # type: ignore
            return jsonify({"success": True, "message": "Run job enqueued via Celery"}), 200
        else:
            # Run enhanced cron worker directly
            import subprocess
            import sys
            result = subprocess.run([
                sys.executable, "cron_worker_enhanced.py"
            ], capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0:
                return jsonify({"success": True, "message": "Enhanced job completed successfully"}), 200
            else:
                return jsonify({"success": False, "error": f"Job failed: {result.stderr}"}), 500
                
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route('/api/channels/fetch-name', methods=['POST'])
def api_fetch_channel_name():
    if not verify_api_token():
        return jsonify({"error": "Authentication required"}), 401
    data = request.get_json() or {}
    cid = data.get('channelId')
    if not cid:
        return jsonify({"error": "channelId required"}), 400
    bot_token = os.environ.get('DISCORD_BOT_TOKEN')
    # If no bot token, return stored name or ID
    if not bot_token:
        try:
            channels = json.load(open(CHANNELS_FILE))
            for ch in channels:
                if str(ch.get('id')) == str(cid):
                    return jsonify({"success": True, "name": ch.get('name') or str(cid)}), 200
        except Exception:
            pass
        return jsonify({"success": True, "name": str(cid)}), 200
    # Fetch from Discord API
    try:
        headers = {"Authorization": f"Bot {bot_token}"}
        resp = requests.get(f"https://discord.com/api/v10/channels/{cid}", headers=headers, timeout=5)
        resp.raise_for_status()
        info = resp.json()
        name = info.get('name') or str(cid)
    except Exception as e:
        # on failure, fallback to stored or raw ID
        print(f"Warning: Discord API fetch failed: {e}")
        try:
            channels = json.load(open(CHANNELS_FILE))
            for ch in channels:
                if str(ch.get('id')) == str(cid):
                    return jsonify({"success": True, "name": ch.get('name') or str(cid)}), 200
        except Exception:
            pass
        return jsonify({"success": True, "name": str(cid)}), 200
    # attempt to update channels file (non-fatal)
    try:
        channels = json.load(open(CHANNELS_FILE))
        for ch in channels:
            if str(ch.get('id')) == str(cid):
                ch['name'] = name
        with open(CHANNELS_FILE, 'w') as f:
            json.dump(channels, f)
    except Exception as file_err:
        print(f"Warning: failed to update channels file: {file_err}")
    return jsonify({"success": True, "name": name}), 200


def verify_api_token():
    """Verify JWT-like token from Authorization header"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header.split(" ", 1)[1]
    try:
        import base64, time
        token_data = json.loads(base64.b64decode(token).decode())
        if token_data.get("exp", 0) > time.time():
            return True
    except Exception:
        pass
    return False


def api_login_required(f):
    """Decorator for API endpoints requiring token authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not verify_api_token():
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated

# JSON API endpoints for Phase 3
@app.route("/api/public/feeds")
def api_public_feeds():
    """JSON API for public feed data - matches dashboard expectations"""
    # Load feeds and metadata
    with open(FEEDS_FILE, "r") as f:
        feeds = [line.strip() for line in f if line.strip()]
    try:
        meta = json.load(open(FEED_META_FILE))
    except Exception:
        meta = {}
    try:
        feed_map = json.load(open(FEED_MAP_FILE))
    except Exception:
        feed_map = {}
    try:
        groups = json.load(open(GROUPS_FILE))
    except Exception:
        groups = {}
    channels = json.load(open(CHANNELS_FILE)) if os.path.exists(CHANNELS_FILE) else []
    # Build feed items list
    feed_items = []
    for url in feeds:
        m = meta.get(url, {})
        title = m.get("title") or url
        last_post = None
        if m.get("last_post"):
            try:
                last_post = datetime.fromisoformat(m.get("last_post")).isoformat()
            except Exception:
                last_post = None
        feed_items.append({"url": url, "title": title, "last_post": last_post})
    # Include API timestamp for front-end last-update display (based on feed_meta cache file)
    try:
        mtime = os.path.getmtime(FEED_META_FILE)
        last_update = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except Exception:
        last_update = None
    return jsonify({
        "feeds": feed_items,
        "metadata": meta,
        "groups": groups,
        "mappings": feed_map,
        "channels": channels,
        "last_update": last_update
    })

@app.route("/api/feeds")
@api_login_required
def api_feeds():
    """JSON API for admin feed management"""
    with open(FEEDS_FILE, "r") as f:
        feeds = [line.strip() for line in f if line.strip()]
    return jsonify({"feeds": feeds})

@app.route("/api/feeds", methods=["POST"])
@api_login_required
def api_add_feed():
    """Add feed via JSON API"""
    data = request.get_json() or {}
    url = data.get("feedUrl")
    if url:
        with open(FEEDS_FILE, "a") as f:
            f.write(url + "\n")
        return jsonify({"success": True, "message": "Feed added"})
    return jsonify({"success": False, "error": "feedUrl required"}), 400

@app.route("/api/feeds", methods=["DELETE"])
@api_login_required
def api_remove_feed():
    """Remove feed via JSON API"""
    data = request.get_json() or {}
    url = data.get("feedUrl")
    if url:
        lines = [l for l in open(FEEDS_FILE) if l.strip() != url]
        open(FEEDS_FILE, "w").writelines(lines)
        return jsonify({"success": True, "message": "Feed removed"})
    return jsonify({"success": False, "error": "feedUrl required"}), 400

@app.route("/api/channels", methods=["GET"])
@api_login_required
def api_channels():
    """JSON API for channel management"""
    channels = json.load(open(CHANNELS_FILE)) if os.path.exists(CHANNELS_FILE) else []
    # Represent IDs as strings to avoid JS precision loss
    for ch in channels:
        ch['id'] = str(ch.get('id'))
    return jsonify({'channels': channels})

@app.route("/api/channels", methods=["DELETE"])
@api_login_required
def api_delete_channel():
    """Delete a channel via JSON API"""
    data = request.get_json() or {}
    cid = data.get('channelId')
    if cid is None:
        return jsonify({'success': False, 'error': 'channelId required'}), 400
    # Filter out the channel
    channels = json.load(open(CHANNELS_FILE)) if os.path.exists(CHANNELS_FILE) else []
    channels = [c for c in channels if str(c.get('id')) != str(cid)]
    with open(CHANNELS_FILE, 'w') as f:
        json.dump(channels, f)
    return jsonify({'success': True, 'message': 'Channel deleted'}), 200

@app.route("/api/channels", methods=["POST"])
@api_login_required
def api_add_channel():
    """Add channel via JSON API"""
    data = request.get_json() or {}
    cid = data.get("channelId")
    if cid:
        # Preserve channel ID as string to avoid precision loss
        cid_str = str(cid)
        try:
            cid_int = int(cid_str)
        except ValueError:
            return jsonify({"success": False, "error": "Invalid channelId"}), 400
        channels = json.load(open(CHANNELS_FILE)) if os.path.exists(CHANNELS_FILE) else []
        if not any(str(c.get("id")) == cid_str for c in channels):
            # Detect channel type via Discord API
            bot_token = os.environ.get("DISCORD_BOT_TOKEN")
            print(f"🔍 Adding channel {cid}, bot_token available: {bool(bot_token)}")
            headers = {"Authorization": f"Bot {bot_token}"} if bot_token else {}
            detected_type = "text"
            channel_name = str(cid)
            if bot_token:
                try:
                    print(f"🌐 Fetching channel info for {cid} from Discord API...")
                    resp = requests.get(f"https://discord.com/api/v10/channels/{cid}", headers=headers, timeout=5)
                    print(f"📡 Discord API response status: {resp.status_code}")
                    resp.raise_for_status()
                    chinfo = resp.json()
                    print(f"📊 Channel info received: {chinfo}")
                    t = chinfo.get('type')
                    detected_type = 'forum' if t == 15 else 'thread' if t in (10,11,12) else 'text'
                    # Store channel name when adding
                    channel_name = chinfo.get('name') or str(cid)
                    print(f"✅ Parsed: name='{channel_name}', type='{detected_type}' (Discord type: {t})")
                except Exception as e:
                    print(f"❌ Failed to fetch channel info: {e}")
                    detected_type = 'text'
            else:
                print("⚠️ No bot token available, using defaults")
            
            channel_data = {"id": cid_str, "type": detected_type, "name": channel_name}
            print(f"💾 Saving channel data: {channel_data}")
            channels.append(channel_data)
            with open(CHANNELS_FILE, "w") as f:
                json.dump(channels, f)
            return jsonify({"success": True, "message": "Channel added"})
        return jsonify({"success": False, "error": "Channel already exists"}), 400
    return jsonify({"success": False, "error": "channelId required"}), 400

@app.route("/api/groups")
@api_login_required
def api_groups():
    """JSON API for group management"""
    groups = json.load(open(GROUPS_FILE)) if os.path.exists(GROUPS_FILE) else {}
    return jsonify({"groups": groups})
    
@app.route("/api/groups", methods=["POST"])
@api_login_required
def api_add_group():
    """JSON API for creating a new group"""
    data = request.get_json() or {}
    name = data.get('groupName')
    if not name:
        return jsonify({'success': False, 'error': 'groupName required'}), 400
    groups = json.load(open(GROUPS_FILE)) if os.path.exists(GROUPS_FILE) else {}
    if name in groups:
        return jsonify({'success': False, 'error': 'Group already exists'}), 400
    groups[name] = []
    with open(GROUPS_FILE, 'w') as f:
        json.dump(groups, f)
    return jsonify({'success': True, 'message': 'Group created'}), 200

@app.route("/api/groups", methods=["PUT"])
@api_login_required
def api_rename_group():
    """JSON API for renaming an existing group"""
    data = request.get_json() or {}
    old = data.get('oldName')
    new = data.get('newName')
    if not old or not new:
        return jsonify({'success': False, 'error': 'oldName and newName required'}), 400
    groups = json.load(open(GROUPS_FILE)) if os.path.exists(GROUPS_FILE) else {}
    if old not in groups:
        return jsonify({'success': False, 'error': 'Group not found'}), 404
    if new in groups:
        return jsonify({'success': False, 'error': 'New group name already exists'}), 400
    groups[new] = groups.pop(old)
    with open(GROUPS_FILE, 'w') as f:
        json.dump(groups, f)
    return jsonify({'success': True, 'message': 'Group renamed'}), 200

@app.route("/api/groups", methods=["DELETE"])
@api_login_required
def api_delete_group():
    """JSON API for deleting a group"""
    name = request.args.get('name')
    if not name:
        return jsonify({'success': False, 'error': 'name parameter required'}), 400
    groups = json.load(open(GROUPS_FILE)) if os.path.exists(GROUPS_FILE) else {}
    if name not in groups:
        return jsonify({'success': False, 'error': 'Group not found'}), 404
    groups.pop(name)
    with open(GROUPS_FILE, 'w') as f:
        json.dump(groups, f)
    return jsonify({'success': True, 'message': 'Group deleted'}), 200

# === DYNAMIC JOB ENDPOINT ROUTE ===
def cron_job():
    """Dynamic cron job endpoint - the actual job runner"""
    try:
        print(f"🔔 Cron job triggered via {JOB_ENDPOINT}")
        
        # Use enhanced cron worker instead of Celery
        if CELERY_AVAILABLE and run_discord_bot_job:
            # Use Celery if available
            run_discord_bot_job.delay()  # type: ignore
            return jsonify({"status": "success", "message": "Job enqueued via Celery"}), 200
        else:
            # Run enhanced cron worker directly
            import subprocess
            import sys
            
            print("🚀 Running enhanced cron worker...")
            result = subprocess.run([
                sys.executable, "cron_worker_enhanced.py"
            ], capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0:
                print("✅ Enhanced cron job completed successfully")
                return jsonify({"status": "success", "message": "Job completed successfully"}), 200
            else:
                print(f"❌ Enhanced cron job failed: {result.stderr}")
                return jsonify({"status": "error", "message": f"Job failed: {result.stderr}"}), 500
                
    except Exception as e:
        print(f"❌ Cron job exception: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Register the dynamic route
app.add_url_rule(JOB_ENDPOINT, 'cron_job', cron_job, methods=['POST'])
print(f"✅ Registered cron job endpoint: {JOB_ENDPOINT}")

# Direct runnable entrypoint
if __name__ == "__main__":
    # Use PORT env var for local testing and bind to all interfaces
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Flask server at http://0.0.0.0:{port}/")
    app.run(host="0.0.0.0", port=port, debug=True)