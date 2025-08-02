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

# Basic auth credentials from environment
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

@app.route(JOB_ENDPOINT)
def trigger_bot_job():
    """
    This endpoint sends a task to the Celery worker to run the bot job.
    It is protected by a secret URL path.
    """
    print(f"Received request for secret job endpoint. Dispatching task to Celery worker...")
    # .delay() sends the job to the queue and returns immediately.
    run_discord_bot_job.delay() # type: ignore
    return jsonify(message="Bot job has been successfully queued."), 202

@app.route("/")
def index():
    """Public feed list with grouping and sorting options."""
    # update heartbeat in Redis (expires in 60s)
    try:
        redis_client.set(
            "bot:status",
            datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            ex=int(os.environ.get("STATUS_TTL", 60))
        )
    except Exception:
        pass
    # Load feeds from committed feeds.txt (not DATA_DIR)
    with open("feeds.txt", "r") as f:
        feeds = [line.strip() for line in f if line.strip()]
    # Load cached feed metadata
    try:
        meta = json.load(open(FEED_META_FILE))
    except Exception:
        meta = {}
    # Fallback: if metadata lacks title, parse feed to get title
    import feedparser  # ensure feedparser available
    meta_updated = False
    for url in feeds:
        m = meta.get(url, {})
        if not m.get('title'):
            try:
                parsed = feedparser.parse(url)
                feed_feed = getattr(parsed, 'feed', {}) or {}
                feed_title = feed_feed.get('title')
                if feed_title:
                    m['title'] = feed_title
                    meta[url] = m
                    meta_updated = True
            except Exception:
                pass
    
    # Save updated metadata if any changes were made
    if meta_updated:
        with open(FEED_META_FILE, "w") as f:
            json.dump(meta, f)
    # Build feed items list
    feed_items = []
    for url in feeds:
        m = meta.get(url, {})
        title = m.get("title") or url
        last_post_str = m.get("last_post")
        if last_post_str:
            try:
                last_post = datetime.fromisoformat(last_post_str)
            except Exception:
                last_post = None
        else:
            last_post = None
        feed_items.append({"url": url, "title": title, "last_post": last_post})
    # Load groups
    if os.path.exists(GROUPS_FILE):
        try:
            groups = json.load(open(GROUPS_FILE))
        except Exception:
            groups = {}
    else:
        groups = {}
    # Invert group mapping
    feed_group_map = {}
    for grp, flist in groups.items():
        for fu in flist:
            feed_group_map[fu] = grp
    # Load channel mappings for display
    try:
        feed_map = json.load(open(FEED_MAP_FILE))
    except Exception:
        feed_map = {}
    # Load channels and resolve names via Discord API if needed
    if os.path.exists(CHANNELS_FILE):
        channels = json.load(open(CHANNELS_FILE))
        # Coerce to list if file contains a dict (old format)
        if not isinstance(channels, list):
            channels = []
    else:
        channels = []
    BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
    headers = {'Authorization': f'Bot {BOT_TOKEN}'} if BOT_TOKEN else {}
    channel_name_map = {}
    for ch in channels:
        cid = ch.get('id')
        name = ch.get('name')
        if not name and BOT_TOKEN:
            try:
                r = requests.get(f'https://discord.com/api/v10/channels/{cid}', headers=headers, timeout=5)
                r.raise_for_status()
                data = r.json()
                name = data.get('name') or str(cid)
            except Exception:
                name = str(cid)
        if not name:
            name = str(cid)
        channel_name_map[cid] = name
    # Determine view, sort, and grouping options
    view = request.args.get('view', 'grouped')
    group_by = request.args.get('group_by', 'channel')  # default to channel grouping so unmapped feeds appear
    flat_view = (view == 'flat')
    sort_by = request.args.get('sort', 'last')
    order = request.args.get('order', 'desc')  # 'asc' or 'desc'
    if sort_by not in ('name', 'url', 'last', 'oldest'):
        sort_by = 'last'
    if order not in ('asc', 'desc'):
        order = 'desc'
    # Apply sorting with order
    reverse = (order == 'desc')
    if sort_by == 'name':
        feed_items.sort(key=lambda f: f.get('title','').lower(), reverse=reverse)
    elif sort_by == 'url':
        feed_items.sort(key=lambda f: f.get('url','').lower(), reverse=reverse)
    elif sort_by == 'last':
        feed_items.sort(key=lambda f: f.get('last_post') or datetime.min, reverse=reverse)
    elif sort_by == 'oldest':
        # oldest first if desc, otherwise newest first
        feed_items.sort(key=lambda f: f.get('last_post') or datetime.min, reverse=not reverse)
    # Count unmapped
    unmapped_count = sum(1 for f in feed_items if not feed_group_map.get(f['url']))
    # Build nested grouping based on group_by
    group_channels = {}
    if view == 'grouped' and group_by == 'group':
        # manual grouping: group -> channel -> items
        for grp, flist in groups.items():
            ch_map = {}
            for url in flist:
                item = next((f for f in feed_items if f['url'] == url), None)
                if not item:
                    continue
                ch = feed_map.get(url)
                ch_map.setdefault(ch, []).append(item)
            group_channels[grp] = ch_map
        # unmapped feeds
        unmapped_map = {}
        for item in feed_items:
            if not feed_group_map.get(item['url']):
                ch = feed_map.get(item['url'])
                unmapped_map.setdefault(ch, []).append(item)
        if unmapped_map:
            group_channels[None] = unmapped_map
    elif view == 'grouped' and group_by == 'channel':
        # channel grouping: channel -> items
        for item in feed_items:
            ch = feed_map.get(item['url'])
            group_channels.setdefault(ch, []).append(item)
    # Render public feed list
    return render_template(
        "public_feeds.html",
        order=order,
        feed_items=feed_items,
        groups=groups,
        view=view,
        group_by=group_by,
        group_channels=group_channels,
        feed_group_map=feed_group_map,
        flat_view=flat_view,
        sort_by=sort_by,
        unmapped_count=unmapped_count,
        feed_map=feed_map,
        channel_name_map=channel_name_map,
        meta=meta
    )

@app.route(f"/{JOB_ENDPOINT}")
def trigger_job():
    """Triggers the Celery job."""
    print("Received request, triggering Celery job...")
    run_bot_job.delay() # type: ignore
    return "Job triggered!"

# Login route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username")
        pwd = request.form.get("password", "").encode()
        if user == ADMIN_USER and hashlib.sha256(pwd).hexdigest() == ADMIN_PASS_HASH:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")

# Logout route
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Dashboard route
@app.route("/dashboard")
@login_required
def dashboard():
    # Load feeds
    with open("feeds.txt", "r") as f:
        feeds = [line.strip() for line in f if line.strip()]
    # Load cached feed metadata to avoid re-parsing on each page load
    try:
        meta = json.load(open(FEED_META_FILE))
    except Exception:
        meta = {}
    
    # Fallback: if metadata lacks title, parse feed to get title
    import feedparser  # ensure feedparser available
    meta_updated = False
    for url in feeds:
        m = meta.get(url, {})
        if not m.get('title'):
            try:
                parsed = feedparser.parse(url)
                feed_feed = getattr(parsed, 'feed', {}) or {}
                feed_title = feed_feed.get('title')
                if feed_title:
                    m['title'] = feed_title
                    meta[url] = m
                    meta_updated = True
            except Exception:
                pass
    
    # Save updated metadata if any changes were made
    if meta_updated:
        with open(FEED_META_FILE, "w") as f:
            json.dump(meta, f)
    feed_items = []
    for url in feeds:
        m = meta.get(url, {})
        title = m.get("title") or url
        last_post_str = m.get("last_post")
        if last_post_str:
            try:
                last_post = datetime.fromisoformat(last_post_str)
            except Exception:
                last_post = None
        else:
            last_post = None
        feed_items.append({"url": url, "title": title, "last_post": last_post})
    # Load channels from JSON
    if os.path.exists(CHANNELS_FILE):
        channels = json.load(open(CHANNELS_FILE))
        # Coerce to list if file contains a dict (old format)
        if not isinstance(channels, list):
            channels = []
    else:
        channels = []
    # Load feed→channel map
    if os.path.exists(FEED_MAP_FILE):
        feed_map = json.load(open(FEED_MAP_FILE))
    else:
        feed_map = {}
    # Load groups
    if os.path.exists(GROUPS_FILE):
        try:
            groups = json.load(open(GROUPS_FILE))
        except Exception:
            groups = {}
    else:
        groups = {}
    # Invert group mapping: feed_url -> group name
    feed_group_map = {}
    for grp, feeds in groups.items():
        for fu in feeds:
            feed_group_map[fu] = grp
    # Include legacy CHANNEL_ID from env if present
    legacy_id = os.environ.get("CHANNEL_ID")
    if legacy_id:
        try:
            lid = int(legacy_id)
        except ValueError:
            pass
        else:
            if not any(c.get("id") == lid for c in channels):
                # mark env-provided channel
                channels.append({"id": lid, "type": "env"})
    # Cache info
    try:
        seen = json.load(open("seen.json"))
    except:
        seen = []
    # Fetch last bot status and TTL
    try:
        raw = redis_client.get("bot:status")
        status = raw.decode() if isinstance(raw, (bytes, bytearray)) else None
        status_ttl = redis_client.ttl("bot:status")
    except Exception:
        status = None
        status_ttl = None
    # Fetch cached resource metrics
    try:
        raw_cpu = redis_client.get("metrics:cpu")
        raw_mem = redis_client.get("metrics:memory")
        cpu = float(raw_cpu) if isinstance(raw_cpu, (bytes, bytearray)) else None
        memory = float(raw_mem) if isinstance(raw_mem, (bytes, bytearray)) else None
    except Exception:
        cpu = None
        memory = None
    # Load cached feed metadata for page links
    try:
        meta = json.load(open(FEED_META_FILE))
    except Exception:
        meta = {}
    # Resolve channel names and types via Discord API
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    print(f"🔍 Dashboard: Resolving {len(channels)} channels, bot_token available: {bool(bot_token)}")
    headers = {"Authorization": f"Bot {bot_token}"} if bot_token else {}
    channel_items = []
    channels_updated = False
    
    for i, ch in enumerate(channels):
        cid = ch.get("id")
        info = {"id": cid, "type": ch.get("type")}
        print(f"📋 Processing channel {cid}: stored_name='{ch.get('name')}', stored_type='{ch.get('type')}'")
        
        # Always try to fetch from Discord API if we have a bot token
        # This ensures we get the latest channel info including correct types
        if bot_token:
            try:
                print(f"🌐 Fetching channel info for {cid} from Discord API...")
                r = requests.get(f"https://discord.com/api/v10/channels/{cid}", headers=headers, timeout=5)
                print(f"📡 Discord API response status: {r.status_code}")
                r.raise_for_status()
                data = r.json()
                print(f"📊 Channel info received: {data}")
                channel_name = data.get("name") or data.get("topic") or str(cid)
                t = data.get("type")
                detected_type = "forum" if t == 15 else "thread" if t in (10, 11, 12) else "text"
                print(f"✅ Parsed: name='{channel_name}', type='{detected_type}' (Discord type: {t})")
                
                info["name"] = channel_name
                info["detected_type"] = detected_type
                
                # Update the stored channel data if it's different
                if ch.get("name") != channel_name or ch.get("type") != detected_type:
                    print(f"💾 Updating stored data for channel {cid}")
                    channels[i]["name"] = channel_name
                    channels[i]["type"] = detected_type
                    channels_updated = True
                    
            except Exception as e:
                print(f"❌ Failed to fetch channel {cid}: {e}")
                # Fall back to stored data or defaults
                info["name"] = ch.get("name") or str(cid)
                info["detected_type"] = ch.get("type") or "text"
        else:
            print("⚠️ No bot token available, using stored data")
            # No bot token, use stored data
            info["name"] = ch.get("name") or str(cid)
            info["detected_type"] = ch.get("type") or "text"
            
        print(f"📝 Final channel info: {info}")
        channel_items.append(info)
    
    # Save updated channel data if any changes were made
    if channels_updated:
        print(f"💾 Saving updated channel data to {CHANNELS_FILE}")
        with open(CHANNELS_FILE, "w") as f:
            json.dump(channels, f)
    else:
        print("ℹ️ No channel updates needed")
    # Determine view (grouped or flat) and sort key
    view = request.args.get('view', 'grouped')
    flat_view = (view == 'flat')
    sort_by = request.args.get('sort', 'last')
    # Validate sort key
    if sort_by not in ('name', 'url', 'channel', 'last', 'oldest'):
        sort_by = 'last'
    # Apply sorting for all views
    if sort_by == 'name':
        feed_items.sort(key=lambda f: f.get('title','').lower())
    elif sort_by == 'url':
        feed_items.sort(key=lambda f: f.get('url','').lower())
    elif sort_by == 'channel':
        ch_name = {ch['id']: ch['name'] for ch in channel_items}
        feed_items.sort(key=lambda f: ch_name.get(feed_map.get(f['url']), '').lower())
    elif sort_by == 'last':
        feed_items.sort(key=lambda f: f.get('last_post') or datetime.min, reverse=True)
    elif sort_by == 'oldest':
        feed_items.sort(key=lambda f: f.get('last_post') or datetime.min)
    # Count unmapped feeds for display
    unmapped_count = sum(1 for f in feed_items if not feed_group_map.get(f['url']))
    return render_template(
        "dashboard.html",
        feed_items=feed_items,
        channels=channel_items,
        feed_map=feed_map,
        seen_count=len(seen),
        status=status,
        status_ttl=status_ttl,
        cpu=cpu,
        memory=memory,
        sort_by=sort_by,
        flat_view=flat_view,
        groups=groups,
        feed_group_map=feed_group_map,
        unmapped_count=unmapped_count,
        public_view=False,
        meta=meta,
    )

# Add feed
@app.route("/add_feed", methods=["POST"])
@login_required
def add_feed():
    url = request.form.get("feed_url")
    if url:
        with open("feeds.txt", "a") as f:
            f.write(url + "\n")
        flash("Feed added.", "success")
    return redirect(url_for("dashboard"))

# Remove feed
@app.route("/remove_feed", methods=["POST"])
@login_required
def remove_feed():
    url = request.form.get("feed_url")
    if url:
        lines = []
        with open("feeds.txt", "r") as f:
            lines = [l for l in f if l.strip() != url]
        with open("feeds.txt", "w") as f:
            f.writelines(lines)
        flash("Feed removed.", "success")
    return redirect(url_for("dashboard"))
    
# Add channel
@app.route("/add_channel", methods=["POST"])
@login_required
def add_channel():
    channel_id = request.form.get("channel_id")
    if channel_id:
        try:
            cid = int(channel_id)
        except ValueError:
            flash("Invalid channel ID", "danger")
            return redirect(url_for("dashboard"))
        channels = json.load(open(CHANNELS_FILE)) if os.path.exists(CHANNELS_FILE) else []
        if not any(c.get("id") == cid for c in channels):
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
            
            channel_data = {"id": cid, "type": detected_type, "name": channel_name}
            print(f"💾 Saving channel data: {channel_data}")
            channels.append(channel_data)
            with open(CHANNELS_FILE, "w") as f:
                json.dump(channels, f)
            flash("Channel added.", "success")
        else:
            flash("Channel already exists.", "warning")
    return redirect(url_for("dashboard"))

# Remove channel
@app.route("/remove_channel", methods=["POST"])
@login_required
def remove_channel():
    channel_id = request.form.get("channel_id")
    if channel_id:
        try:
            cid = int(channel_id)
        except ValueError:
            flash("Invalid channel ID", "danger")
            return redirect(url_for("dashboard"))
        channels = json.load(open(CHANNELS_FILE)) if os.path.exists(CHANNELS_FILE) else []
        channels = [c for c in channels if c.get("id") != cid]
        with open(CHANNELS_FILE, "w") as f:
            json.dump(channels, f)
        flash("Channel removed.", "success")
    return redirect(url_for("dashboard"))
    
# Map a feed URL to a channel ID
@app.route("/map_feed_channel", methods=["POST"])
@login_required
def map_feed_channel():
    feed_url = request.form.get("feed_url")
    channel_id = request.form.get("channel_id")
    if feed_url:
        try:
            cid = int(channel_id)
        except (TypeError, ValueError):
            cid = None
        fmap = json.load(open(FEED_MAP_FILE)) if os.path.exists(FEED_MAP_FILE) else {}
        if cid:
            fmap[feed_url] = cid
        else:
            fmap.pop(feed_url, None)
        with open(FEED_MAP_FILE, "w") as f:
            json.dump(fmap, f)
        flash("Feed mapping updated.", "success")
    return redirect(url_for("dashboard"))
    
# Edit system prompt sections
@app.route("/prompt", methods=["GET", "POST"])
@login_required
def edit_prompt():
    # load or initialize sections
    if os.path.exists(PROMPT_FILE):
        try:
            sections = json.load(open(PROMPT_FILE, encoding="utf-8"))
        except Exception:
            sections = []
    else:
        sections = []
    if request.method == "POST":
        names = request.form.getlist('section_name')
        contents = request.form.getlist('section_content')
        new_sections = []
        for name, content in zip(names, contents):
            if name.strip():
                new_sections.append({'name': name, 'content': content})
        with open(PROMPT_FILE, "w", encoding="utf-8") as f:
            json.dump(new_sections, f, indent=2)
        flash("System prompt sections updated.", "success")
        return redirect(url_for("dashboard"))
    return render_template("prompt.html", sections=sections)

# Clear cache
@app.route("/clear_cache", methods=["POST"])
@login_required
def clear_cache():
    # Clear the seen cache and record action in log
    open("seen.json", "w").write("[]")
    with open("action.log", "a", encoding="utf-8") as log:
        log.write(f"{datetime.now().isoformat()} - Cache cleared" + "\n")
    return redirect(url_for("dashboard"))


# Trigger job from dashboard
@app.route("/run_job", methods=["POST"])
@login_required
def run_job_dashboard():
    run_discord_bot_job.delay()  # type: ignore
    flash("Bot job queued.", "success")
    return redirect(url_for("dashboard"))

# Reset summary route
dashboard_route = "/dashboard"
@app.route("/reset_summary", methods=["POST"])
@login_required
def reset_summary():
    # Clear seen GUIDs to fully reset summaries in both current dir and DATA_DIR
    # Primary seen cache
    try:
        open("seen.json", "w").write("[]")
    except Exception:
        pass
    # Bot's persistent seen cache under DATA_DIR
    seen_path = os.path.join(DATA_DIR, "seen.json")
    try:
        open(seen_path, "w").write("[]")
    except Exception:
        pass
    # Create flag files to signal summary recreation (both locations)
    try:
        with open("reset_summary.flag", "w"): pass
    except Exception:
        pass
    flag_path = os.path.join(DATA_DIR, "reset_summary.flag")
    try:
        with open(flag_path, "w"): pass
    except Exception:
        pass
    # Log reset action
    with open("action.log", "a", encoding="utf-8") as log:
        log.write(f"{datetime.now().isoformat()} - Summary reset requested; seen caches cleared" + "\n")
    return redirect(url_for("dashboard"))

# Stats route
@app.route("/stats")
@login_required
def stats():
    # Fetch bot status and TTL
    try:
        raw = redis_client.get("bot:status")
        status = raw.decode() if raw else None
        status_ttl = redis_client.ttl("bot:status")
    except Exception:
        status, status_ttl = None, None
    # Fetch resource metrics
    try:
        raw_cpu = redis_client.get("metrics:cpu")
        raw_mem = redis_client.get("metrics:memory")
        cpu = float(raw_cpu) if raw_cpu else None
        memory = float(raw_mem) if raw_mem else None
    except Exception:
        cpu, memory = None, None
    # Counts
    with open("feeds.txt") as f:
        feed_count = len([l for l in f if l.strip()])
    channels = json.load(open(CHANNELS_FILE)) if os.path.exists(CHANNELS_FILE) else []
    channel_count = len(channels)
    return render_template(
        "stats.html",
        status=status,
        status_ttl=status_ttl,
        cpu=cpu,
        memory=memory,
        feed_count=feed_count,
        channel_count=channel_count,
    )

# Serve cached feed metadata for client-side refresh
@app.route("/feed_meta")
@login_required
def feed_meta():
    try:
        meta = json.load(open(FEED_META_FILE))
    except Exception:
        meta = {}
    return jsonify(meta)

# Add manual refresh feed metadata endpoint
@app.route("/refresh_feed_meta", methods=["POST"])
@login_required
def refresh_feed_meta():
    fetch_feed_meta.delay()  # type: ignore
    flash("Feed metadata refresh has been queued.", "info")
    return redirect(url_for('dashboard'))

# Add manual refresh channel information endpoint
@app.route("/refresh_channels", methods=["POST"])
@login_required
def refresh_channels():
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not bot_token:
        flash("Discord bot token not configured", "danger")
        return redirect(url_for('dashboard'))
        
    headers = {"Authorization": f"Bot {bot_token}"}
    channels = json.load(open(CHANNELS_FILE)) if os.path.exists(CHANNELS_FILE) else []
    updated_count = 0
    
    for i, ch in enumerate(channels):
        cid = ch.get("id")
        try:
            r = requests.get(f"https://discord.com/api/v10/channels/{cid}", headers=headers, timeout=5)
            r.raise_for_status()
            data = r.json()
            channel_name = data.get("name") or data.get("topic") or str(cid)
            t = data.get("type")
            detected_type = "forum" if t == 15 else "thread" if t in (10, 11, 12) else "text"
            
            # Update if different
            if ch.get("name") != channel_name or ch.get("type") != detected_type:
                channels[i]["name"] = channel_name
                channels[i]["type"] = detected_type
                updated_count += 1
                
        except Exception as e:
            print(f"⚠️ Failed to refresh channel {cid}: {e}")
            continue
    
    # Save updated channel data
    with open(CHANNELS_FILE, "w") as f:
        json.dump(channels, f)
    
    flash(f"Channel information refreshed. {updated_count} channels updated.", "success")
    return redirect(url_for('dashboard'))

# Add group
@app.route("/add_group", methods=["POST"])
@login_required
def add_group():
    name = request.form.get('group_name', '').strip()
    if name:
        groups = json.load(open(GROUPS_FILE)) if os.path.exists(GROUPS_FILE) else {}
        if name not in groups:
            groups[name] = []
            with open(GROUPS_FILE, 'w') as f:
                json.dump(groups, f)
            flash('Group added.', 'success')
        else:
            flash('Group already exists.', 'warning')
    return redirect(url_for('dashboard'))

# Rename group
@app.route("/rename_group", methods=["POST"])
@login_required
def rename_group():
    old = request.form.get('old_name')
    new = request.form.get('new_name', '').strip()
    groups = json.load(open(GROUPS_FILE)) if os.path.exists(GROUPS_FILE) else {}
    if old and new and old in groups and new != old:
        groups[new] = groups.pop(old)
        with open(GROUPS_FILE, 'w') as f:
            json.dump(groups, f)
        flash('Group renamed.', 'success')
    return redirect(url_for('dashboard'))

# Remove group
@app.route("/remove_group", methods=["POST"])
@login_required
def remove_group():
    name = request.form.get('group_name')
    groups = json.load(open(GROUPS_FILE)) if os.path.exists(GROUPS_FILE) else {}
    if name in groups:
        groups.pop(name)
        with open(GROUPS_FILE, 'w') as f:
            json.dump(groups, f)
        flash('Group removed.', 'success')
    return redirect(url_for('dashboard'))

# Map feed to group
@app.route("/map_feed_group", methods=["POST"])
@login_required
def map_feed_group():
    feed_url = request.form.get('feed_url')
    grp = request.form.get('group_name')
    groups = json.load(open(GROUPS_FILE)) if os.path.exists(GROUPS_FILE) else {}
    # remove from any group
    for feeds in groups.values():
        if feed_url in feeds:
            feeds.remove(feed_url)
    # add to selected group
    if grp and grp in groups:
        groups[grp].append(feed_url)
    with open(GROUPS_FILE, 'w') as f:
        json.dump(groups, f)
    flash('Feed grouping updated.', 'success')
    return redirect(url_for('dashboard'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
