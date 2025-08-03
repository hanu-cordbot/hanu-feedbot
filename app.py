# === FILE: app.py ===

import os
from datetime import datetime, timezone
from flask import Flask, jsonify, abort, render_template, request, redirect, url_for, Response, session, flash
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
from celery_app import run_discord_bot_job, fetch_feed_meta  # also import fetch_feed_meta

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
# Redis client for real-time status and metrics
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
redis_client: Redis = cast(Redis, redis.from_url(REDIS_URL))

# --- SECURITY UPDATE ---
# Get the secret endpoint from an environment variable.
# If it's not set, the application will not start.
JOB_ENDPOINT = os.environ.get("JOB_ENDPOINT")
if not JOB_ENDPOINT:
    raise ValueError("FATAL: JOB_ENDPOINT environment variable not set. Please provide a secret URL path.")

# Ensure the endpoint starts with a slash for the Flask route
if not JOB_ENDPOINT.startswith('/'):
    JOB_ENDPOINT = f'/{JOB_ENDPOINT}'

app = Flask(__name__)
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
ADMIN_PASS_HASH = os.environ.get("ADMIN_PASS_HASH", hashlib.sha256(b"hyperdelusionsinallofexistence").hexdigest())  # store hashed password
# If ADMIN_PASS_HASH is provided plaintext, convert it to its SHA-256 hash
if len(ADMIN_PASS_HASH) != 64 or not re.fullmatch(r"[0-9a-f]{64}", ADMIN_PASS_HASH):
    ADMIN_PASS_HASH = hashlib.sha256(ADMIN_PASS_HASH.encode()).hexdigest()

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
CORS(app, origins=[
    "https://yourusername.github.io",  # Replace with your GitHub Pages URL
    "http://localhost:3000",            # Local dev frontend
    "http://127.0.0.1:5000"            # Local API testing
])

# Authentication bridge for JWT-like tokens
@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """JWT-compatible login endpoint for dashboard"""
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password", "").encode()
    if username == ADMIN_USER and hashlib.sha256(password).hexdigest() == ADMIN_PASS_HASH:
        import base64, time
        token_data = {"user": username, "exp": int(time.time()) + 3600}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()
        return jsonify({"success": True, "token": token})
    return jsonify({"success": False, "error": "Invalid credentials"}), 401


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
    return jsonify({
        "feeds": feed_items,
        "metadata": meta,
        "groups": groups,
        "mappings": feed_map,
        "channels": channels
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

@app.route("/api/channels")
@api_login_required
def api_channels():
    """JSON API for channel management"""
    channels = json.load(open(CHANNELS_FILE)) if os.path.exists(CHANNELS_FILE) else []
    return jsonify({"channels": channels})

@app.route("/api/channels", methods=["POST"])
@api_login_required
def api_add_channel():
    """Add channel via JSON API"""
    data = request.get_json() or {}
    cid = data.get("channelId")
    if cid:
        try:
            cid_int = int(cid)
        except ValueError:
            return jsonify({"success": False, "error": "Invalid channelId"}), 400
        channels = json.load(open(CHANNELS_FILE)) if os.path.exists(CHANNELS_FILE) else []
        if not any(c.get("id") == cid_int for c in channels):
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
            
            channel_data = {"id": cid_int, "type": detected_type, "name": channel_name}
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

# Direct runnable entrypoint
if __name__ == "__main__":
    print("Starting Flask server at http://127.0.0.1:5000/")
    app.run(host="127.0.0.1", port=5000, debug=True)