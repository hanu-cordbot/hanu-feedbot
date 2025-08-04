# === FILE: celery_app.py ===

import os
import sys
from pathlib import Path

# Add the project root to the Python path to ensure modules are found.
ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

from celery import Celery
from flask import Flask

def create_flask_app():
    app = Flask(__name__)
    # Your Flask app configuration
    return app

# Initialize Flask app
flask_app = create_flask_app()
# Celery configured with in-memory broker and backend; tasks run eagerly (no Redis needed)
celery = Celery(
    flask_app.import_name,
    broker='memory://',
    backend='cache+memory://'
)
celery.conf.update(flask_app.config)
celery.conf.task_always_eager = True

# --- Scheduled tasks: fetch and cache resource metrics ---
from celery.schedules import crontab
import requests

# --- Scheduled tasks: fetch and cache feed metadata every minute ---
@celery.on_after_configure.connect
def setup_feed_meta_task(sender, **kwargs):
    # every hour
        sender.add_periodic_task(
        crontab(minute=0),  # run hourly
        fetch_feed_meta.s(),
        name='update feed metadata every hour'
    )

@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # every 60 minutes
    sender.add_periodic_task(
        crontab(minute='*/60'),
        update_metrics.s(),
        name='update resource metrics every 60m'
    )

@celery.task(name='update_metrics')
def update_metrics():
    """Fetch CPU & memory usage via Railway API and cache in Redis"""
    api_key = os.getenv('RAILWAY_API_KEY')
    project_id = os.getenv('RAILWAY_PROJECT_ID')
    if not api_key or not project_id:
        return
    url = f'https://backboard.railway.app/projects/{project_id}/metrics'
    try:
        resp = requests.get(url, headers={'Authorization': api_key}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        # cache for 6 minutes
        for key in ('cpu', 'memory'):
            val = data.get(key)
            if val is not None:
                redis_client.set(f'metrics:{key}', val, ex=360)
    except Exception as e:
        print(f'Error fetching metrics: {e}')
    # end update_metrics

@celery.task(name='fetch_feed_meta')
def fetch_feed_meta():
    """Fetch feed titles and last post timestamps and cache to JSON file"""
    import json
    import feedparser
    meta = {}
    try:
        with open('feeds.txt', 'r') as f:
            feeds = [line.strip() for line in f if line.strip()]
    except Exception:
        feeds = []
    for url in feeds:
        entry_url = None
        page_url = None
        # fetch raw feed to extract the channel <link> (Facebook page URL)
        try:
            import requests, xml.etree.ElementTree as ET
            resp = requests.get(url, timeout=5)
            root = ET.fromstring(resp.content)
            chan = root.find('channel')
            if chan is not None:
                link_elem = chan.find('link')
                if link_elem is not None and link_elem.text:
                    page_url = link_elem.text.strip()
        except Exception:
            pass
        try:
            parsed = feedparser.parse(url)
            feed_info = parsed.get('feed', {})
            title = feed_info.get('title') or url
            entries = parsed.entries or []
            last_post = None
            # fallback to feed parser link if not found via raw XML
            if not page_url:
                page_url = feed_info.get('link')
            if entries:
                first = entries[0]
                # Extract published or updated parsed time
                lp = first.get('published_parsed') or first.get('updated_parsed')
                if lp and isinstance(lp, (list, tuple)):
                    try:
                        # Build ISO timestamp without timezone so JS treats as local (UTC+7 RSS feed)
                        parts = [int(x) for x in lp[:6]]  # year, month, day, hour, minute, second
                        last_post = f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}T{parts[3]:02d}:{parts[4]:02d}:{parts[5]:02d}"
                    except Exception:
                        last_post = None
                else:
                    last_post = None
                # store first entry link safely
                entry_url = first.get('link')
        except Exception:
            title = url
            last_post = None
        meta[url] = {'title': title, 'last_post': last_post, 'entry_url': entry_url, 'page_url': page_url}
    try:
        with open('feed_meta.json', 'w') as f:
            json.dump(meta, f)
    except Exception as e:
        print(f'Error writing feed metadata cache: {e}')

@celery.task(name="run_discord_bot_job")
def run_discord_bot_job():
    """
    This is the Celery task that will run our bot's logic.
    We import the bot's main function here to avoid circular dependencies.
    """
    from bot.main import run_bot_job
    import asyncio
    try:
        print("Celery worker: Starting bot job...")
        # Use existing event loop or create a new one to avoid closed loop errors
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Event loop closed")
        except Exception:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(run_bot_job())
        print("Celery worker: Bot job finished successfully.")
    except Exception as e:
        print(f"Celery worker: An error occurred in the bot job: {e}")

# Expose celery_app for Celery CLI discovery
celery_app = celery
