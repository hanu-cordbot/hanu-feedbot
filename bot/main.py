#!/usr/bin/env python3
# === FILE: bot/main.py ===
# Main entry point for the HANU feed bot
import os
import sys
import json
import asyncio
import tempfile
import random
import io
import time
import re
from pathlib import Path
from collections import defaultdict

import pendulum
import discord
import aiohttp
from aiohttp import ClientSession, ClientTimeout
from typing import Optional, cast
from dotenv import load_dotenv

# Load all environment variables from .env for local development
load_dotenv()

# --- GLOBAL CONFIGURATION ---
print("Initializing configuration...")

# Shared HTTP session placeholder; will initialize inside async context
HTTP_SESSION: Optional[ClientSession] = None
# Global list of temporary directories to clean up
TEMP_DIRS_TO_CLEANUP: list[str] = []

# Load DISCORD_BOT_TOKEN, warn if missing
BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
if not BOT_TOKEN:
    print("[WARNING]  Warning: DISCORD_BOT_TOKEN is missing; run_bot_job will be disabled.")

# Load optional TARGET_CHANNEL_ID
channel_id_env = os.environ.get('CHANNEL_ID')
if channel_id_env:
    try:
        TARGET_CHANNEL_ID = int(channel_id_env)
    except ValueError:
        print(f"[CRITICAL] ERROR: CHANNEL_ID '{channel_id_env}' is not a valid integer. Ignoring.")
        TARGET_CHANNEL_ID = None
else:
    print("[WARNING]  CHANNEL_ID not set; TARGET_CHANNEL_ID will be None.")
    TARGET_CHANNEL_ID = None

# Warn if optional environment variables are missing
for var in ('GEMINI_API_KEY', 'DISCORD_WEBHOOK_URL'):
    if var not in os.environ:
        print(f"[WARNING]  Warning: {var} is missing. Related features may not work.")

# Load optional settings
MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "36"))
SHORT_POST_WORD_THRESHOLD = 40
SUMMARY_CHANNEL_ID = os.getenv('SUMMARY_CHANNEL_ID')
if SUMMARY_CHANNEL_ID:
    SUMMARY_CHANNEL_ID = int(SUMMARY_CHANNEL_ID)
FALLBACK_ENABLED = os.getenv('FALLBACK_ENABLED', 'true').lower() in ('1', 'true', 'yes')

# --- FILE PATHS ---
if os.path.exists("/data"):
    BASE_DIR = "/data"
    print("Persistent storage at /data detected.")
else:
    BASE_DIR = "."
    print("Running locally, using current directory for storage.")

SEEN_FILE = os.path.join(BASE_DIR, "seen.json")
DETAILS_FILE = os.path.join(BASE_DIR, "details_thread_id.json")
DETAILS_MAP_FILE = os.path.join(BASE_DIR, 'details_threads.json')

# --- IMPORTS FROM BOT MODULES ---
from bot.parser import iter_entries
from bot.formatter import build_prompt, split_reply, format_vietnamese_date, build_thread_title_prompt
from bot.gemini_client import call_gemini
from bot.dispatcher import (
    push,
    get_daily_summary_message,
    create_daily_summary_message,
    update_daily_summary_message,
    get_or_create_webhook_url,
    FACEBOOK_REACTIONS,
)
from bot.avatar_cache import maybe_update, avatar_for
from bot.config import GLOBAL_FALLBACK_CHANNEL_ID
from bot.facebook_downloader import download_video_ytdlp, normalize_url

print("Configuration loaded.")

# --- HELPER FUNCTIONS ---
async def download_bytes(url: str) -> bytes:
    """Fetch raw bytes for a media URL."""
    # Ensure HTTP_SESSION has been initialized
    if HTTP_SESSION is None:
        raise RuntimeError("HTTP_SESSION not initialized")
    # Use shared HTTP_SESSION with increased timeout for large media
    async with HTTP_SESSION.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
        resp.raise_for_status()
        return await resp.read()

def load_seen_guids():
    """Loads the set of processed post IDs from the state file."""
    try:
        with open(SEEN_FILE, 'r') as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"'{SEEN_FILE}' not found or invalid. Initializing a new one.")
        with open(SEEN_FILE, 'w') as f:
            json.dump([], f)
        return set()

def save_seen_guids(guids):
    """Saves the set of processed post IDs to the state file."""
    with open(SEEN_FILE, 'w') as f:
        json.dump(list(guids)[-500:], f, indent=2)  # Keep last 500 posts

async def build_full_body(entry: dict) -> str:
    """Build full formatted body for an entry using existing logic."""
    maybe_update(entry)
    
    if len(entry.get('raw', '').split()) < SHORT_POST_WORD_THRESHOLD:
        parts = []
        title = entry.get('title', '')
        if title:
            parts.append(f"# **{title}**")
        raw = entry.get('raw', '')
        if raw and raw.strip() != title.strip():
            parts.append(raw)
        body = "\n\n".join(parts)
        return f"{body}\n\n<{entry.get('link')}>"
    else:
        reply = await asyncio.to_thread(call_gemini, build_prompt(entry)) or ""
        if not reply:
            return f"Error processing content\n\n<{entry.get('link')}>"
        body, tldr = split_reply(reply)
        full_content = body
        if tldr:
            full_content += f"\n\n{tldr}"
        return f"{full_content}\n\n<{entry.get('link')}>"

async def get_or_create_channel_details_thread(
    client: discord.Client,
    channel: discord.TextChannel,
    summary_msg: discord.Message,
    details_map: dict[str, int],
) -> discord.Thread:
    """Returns a valid per-channel 'Details' thread for today's summary message."""
    
    # 1) Try persisted ID first
    tid = details_map.get(str(channel.id))
    if tid:
        cand = client.get_channel(tid)
        if isinstance(cand, discord.Thread) and cand.parent_id == summary_msg.id:
            return cand
    
    # 2) CRITICAL: Check if a thread already exists for this SPECIFIC message
    # Discord only allows ONE thread per message, so check the message directly
    try:
        # Refresh the message to get current threads
        fresh_msg = await channel.fetch_message(summary_msg.id)
        if hasattr(fresh_msg, 'thread') and fresh_msg.thread:
            # Message already has a thread
            existing_thread = fresh_msg.thread
            details_map[str(channel.id)] = existing_thread.id
            with open(DETAILS_MAP_FILE, "w") as f:
                json.dump(details_map, f)
            return existing_thread
    except Exception as e:
        print(f"[WARNING] Could not fetch fresh message: {e}")
    
    # 3) Search existing threads manually (fallback)
    for t in channel.threads:
        if hasattr(t, 'parent_id') and t.parent_id == summary_msg.id and t.name == "Details":
            details_map[str(channel.id)] = t.id
            with open(DETAILS_MAP_FILE, "w") as f:
                json.dump(details_map, f)
            return t
    
    # 4) Try to create new thread
    try:
        thread = await summary_msg.create_thread(name="Details")
        details_map[str(channel.id)] = thread.id
        with open(DETAILS_MAP_FILE, "w") as f:
            json.dump(details_map, f)
        return thread
        
    except discord.HTTPException as e:
        if e.code == 160004:
            print(f"[CRITICAL] CRITICAL: Thread exists but we can't find it. Message ID: {summary_msg.id}")
            print(f"    Message threads: {getattr(summary_msg, 'thread', 'None')}")
            print(f"    Channel threads: {[t.name + '(parent:' + str(getattr(t, 'parent_id', 'None')) + ')' for t in channel.threads]}")
            
            # Last resort: try to find ANY thread with "Details" name for this channel today
            for t in channel.threads:
                if t.name == "Details":
                    print(f"    Found fallback Details thread: {t.id}")
                    details_map[str(channel.id)] = t.id
                    with open(DETAILS_MAP_FILE, "w") as f:
                        json.dump(details_map, f)
                    return t
            
            # If we still can't find it, create with a unique name
            try:
                unique_name = f"Details-{int(time.time())}"
                thread = await summary_msg.create_thread(name=unique_name)
                details_map[str(channel.id)] = thread.id
                with open(DETAILS_MAP_FILE, "w") as f:
                    json.dump(details_map, f)
                return thread
            except Exception as fallback_e:
                print(f"[CRITICAL] Even unique thread creation failed: {fallback_e}")
                raise e
        else:
            raise e

async def process_media(entry, channel):
    """Process media for an entry with improved Facebook video handling."""
    # Discord file size limits
    DISCORD_LIMIT = 8 * 1024 * 1024  # 8MB Discord file limit
    
    video_exts = ('.mp4', '.webm', '.mov', '.mkv')
    image_exts = ('.jpg', '.jpeg', '.png', '.gif')
    media_urls = entry.get('media_all', []) or []
    media_files = []
    video_processed = False
    
    # Create a manual temp directory instead of using context manager
    temp_dir = tempfile.mkdtemp(prefix="hanu_feedbot_")
    TEMP_DIRS_TO_CLEANUP.append(temp_dir)  # Add to global cleanup list
    
    try:
        # STEP 1: First check for target post ID "743124275142078"
        entry_str = str(entry)
        if "743124275142078" in entry_str or "4010190512624581" in entry_str:
            print(f"[TARGET] FOUND TARGET POST ID in entry!")
            target_url = "https://www.facebook.com/720895507364955/posts/743124275142078"
            print(f"[DOWNLOAD] Downloading video from known target URL: {target_url}")
            
            # Generate unique filenames
            download_path = os.path.join(temp_dir, f"facebook_video_{random.randint(1000, 9999)}.mp4")
            
            # Download the video
            file_path = await download_video_ytdlp(target_url, output_path=download_path)
            
            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                print(f"[OK] Downloaded target video: {file_size/1024/1024:.2f}MB")
                
                # Check if file is too large for Discord
                if file_size > DISCORD_LIMIT:
                    print(f"[WARNING] Video too large for Discord ({file_size/1024/1024:.2f}MB > {DISCORD_LIMIT/1024/1024}MB)")
                    print(f"[UPLOAD] Uploading to Catbox instead...")
                    
                    # Import upload function from dispatcher
                    from bot.dispatcher import upload_to_catbox
                    
                    # Read file data
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                    
                    # Upload to Catbox
                    catbox_url = upload_to_catbox(file_data)
                    if catbox_url:
                        print(f"[OK] Uploaded to Catbox: {catbox_url}")
                        # Send as a message instead of file attachment
                        await channel.send(f"Video from post: {target_url}\n{catbox_url}")
                        video_processed = True
                    else:
                        print("[ERROR] Failed to upload to Catbox")
                else:
                    # Small enough for Discord, send directly
                    print(f"[UPLOAD] Video small enough for Discord ({file_size/1024/1024:.2f}MB)")
                    media_files.append(discord.File(file_path, filename="facebook_video.mp4"))
                    video_processed = True
        
        # STEP 2: Try to extract video directly from post URL if target not found
        if not video_processed:
            post_url = entry.get('link', '')
            if "facebook.com" in post_url:
                print(f"[DOWNLOAD] Trying direct video download from post URL: {post_url}")
                
                download_path = os.path.join(temp_dir, f"facebook_video_{random.randint(1000, 9999)}.mp4")
                file_path = await download_video_ytdlp(post_url, output_path=download_path)
                
                if file_path and os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    if file_size > 100000:  # Ensure it's not just a thumbnail
                        print(f"[OK] Downloaded video from post URL: {file_size/1024/1024:.2f}MB")
                        
                        # Check if too large for Discord
                        if file_size > DISCORD_LIMIT:
                            from bot.dispatcher import upload_to_catbox
                            with open(file_path, 'rb') as f:
                                file_data = f.read()
                            catbox_url = upload_to_catbox(file_data)
                            if catbox_url:
                                video_processed = True
                        else:
                            media_files.append(discord.File(file_path, filename="facebook_video.mp4"))
                            video_processed = True
                    else:
                        print(f"[WARNING] Downloaded file too small: {file_size} bytes")
                else:
                    print(f"[ERROR] No video found at post URL")
        
        # STEP 3: Only if no video processed, try individual media URLs
        if not video_processed:
            print("[MEDIA] No video found, processing individual media URLs")
            for url in media_urls:
                if len(media_files) >= 10:  # Discord limit
                    break
                try:
                    # Skip CDN/thumbnail URLs if we've found our target post ID
                    if "743124275142078" in entry_str and ("fbcdn.net" in url or "scontent-" in url):
                        print(f"[WARNING] Skipping CDN URL for target post: {url}")
                        continue
                        
                    # Facebook video posts
                    video_norm = normalize_url(url)
                    if video_norm and "facebook.com" in video_norm:
                        print(f"[DOWNLOAD] Trying video download from media URL: {video_norm}")
                        download_path = os.path.join(temp_dir, f"facebook_video_{random.randint(1000, 9999)}.mp4")
                        file_path = await download_video_ytdlp(video_norm, output_path=download_path)
                        
                        if file_path and os.path.exists(file_path):
                            file_size = os.path.getsize(file_path)
                            if file_size > 100000:
                                print(f"[OK] Downloaded video from media URL: {file_size/1024/1024:.2f}MB")
                                
                                # Check if too large for Discord
                                if file_size > DISCORD_LIMIT:
                                    from bot.dispatcher import upload_to_catbox
                                    with open(file_path, 'rb') as f:
                                        file_data = f.read()
                                    catbox_url = upload_to_catbox(file_data)
                                    if catbox_url:
                                        await channel.send(f"Video from media URL: {video_norm}\n{catbox_url}")
                                        video_processed = True
                                else:
                                    media_files.append(discord.File(file_path, filename=os.path.basename(file_path)))
                                    video_processed = True
                                continue
                                
                    # Direct video links
                    path = url.split('?')[0].lower()
                    if any(path.endswith(ext) for ext in video_exts):
                        video_data = await download_bytes(url)
                        name = url.split('/')[-1].split('?')[0] or 'video.mp4'
                        media_files.append(discord.File(io.BytesIO(video_data), filename=name))
                        continue
                        
                    # Image links
                    if any(path.endswith(ext) for ext in image_exts):
                        img_data = await download_bytes(url)
                        name = url.split('/')[-1].split('?')[0] or 'image.jpg'
                        media_files.append(discord.File(io.BytesIO(img_data), filename=name))
                        continue
                except Exception as err:
                    print(f"Failed to download media {url}: {err}")
        
        # Send media files to channel
        if media_files:
            print(f"[UPLOAD] Sending {len(media_files)} media files to channel")
            try:
                await channel.send(files=media_files)
                print("[OK] Media files sent successfully")
            except discord.errors.HTTPException as e:
                if "Payload Too Large" in str(e) or "40005" in str(e):
                    print(f"[WARNING] File too large for Discord, fallback not implemented for this case")
                else:
                    print(f"[ERROR] Error sending media: {e}")
                import traceback
                traceback.print_exc()
        
        return video_processed
    
    finally:
        # Add temp directory to global cleanup list if not already there
        if temp_dir not in TEMP_DIRS_TO_CLEANUP:
            TEMP_DIRS_TO_CLEANUP.append(temp_dir)

async def process_feeds_once(client: discord.Client):
    """Scans feeds and processes new entries per-channel summary."""
    # Debug: show feeds loading
    print("[IMPORT] Starting feed loop?")
    # Placeholder for raw parsed entries
    raw_entries = []
    # Collect all parsed entries and filter new ones
    print("? Collecting and filtering parsed entries...")
    seen = load_seen_guids()
    now = pendulum.now('Asia/Ho_Chi_Minh')
    today = now.format('YYYY-MM-DD')

    # Load mappings and thread map
    try:
        with open(os.path.join(BASE_DIR, 'feed_map.json'), 'r') as f: 
            user_map = json.load(f)
    except Exception:
        user_map = {}
    try:
        with open(DETAILS_MAP_FILE) as f: 
            details_map = json.load(f)
    except: 
        details_map = {}

    # Collect new entries
    new_posts = []
    for e in iter_entries():
        raw_entries.append(e)
        cid = user_map.get(e['feed']) or GLOBAL_FALLBACK_CHANNEL_ID
        if not cid or e['guid'] in seen:
            continue
        age = (now - e.get('published', now)).total_hours()
        if age > MAX_AGE_HOURS:
            continue
        new_posts.append(e)
    # Debug: show counts after parsing and filtering
    print(f"   ? Raw entries parsed: {len(raw_entries)}")
    print(f"   ? New entries to process: {len(new_posts)}")
    # Debug: show how many new posts to process
    print(f"   ? Total new posts: {len(new_posts)}")
    if not new_posts:
        print("No new entries this cycle.")
        return

    # Bucket by channel
    channel_groups = defaultdict(list)
    for e in new_posts:
        cid = user_map.get(e['feed']) or GLOBAL_FALLBACK_CHANNEL_ID
        if cid is None:
            continue
        channel_groups[int(cid)].append(e)

    # Show channel grouping
    channels = list(channel_groups.items())
    print(f"[IMPORT] Will process {len(channels)} channels")
    total_entries = len(new_posts)
    processed_count = 0
    # Process each channel
    for ch_idx, (ch_id, entries) in enumerate(channels, start=1):
        print(f"[{ch_idx}/{len(channels)}] Processing channel {ch_id} ({len(entries)} entries)")
        try:
            ch = client.get_channel(ch_id)
            if not isinstance(ch, discord.TextChannel):
                print(f"Skipping non-text channel {ch_id}")
                continue
            # 1) Summary header
            vietnamese_date = format_vietnamese_date(now)
            summary = await get_daily_summary_message(ch, today)
            print(f"   ? Summary message for channel {ch_id}: {summary and getattr(summary, 'id', None)}")
            if not summary:
                summary = await create_daily_summary_message(ch, vietnamese_date)
                print(f"   ? Created new summary message: {summary and getattr(summary, 'id', None)}")
                if not summary:
                    continue
            # 2) Details thread under summary
            thr = await get_or_create_channel_details_thread(client, ch, summary, details_map)
            print(f"   ? Using thread: {getattr(thr, 'id', None)}")
            # 3) Post each entry
            for entry_idx, e in enumerate(entries, start=1):
                processed_count += 1
                # Debug info per entry with global count
                print(f"\n{'='*40}")
                print(f"[Entry {processed_count}/{total_entries}] ? PROCESSING ENTRY: {e.get('title', 'No title')}")
                print(f"? Link: {e.get('link', 'No link')}")
                print(f"{'='*40}\n")
                # Generate and send body content
                body = await build_full_body(e)
                last_msg = None
                for idx in range(0, len(body), 2000):
                    chunk = body[idx:idx+2000]
                    last_msg = await thr.send(chunk)
                posted_message = last_msg
                # Append summary to daily summary message
                await update_daily_summary_message(summary, e, posted_message)
                print(f"   ? Updated daily summary with entry {e.get('guid')}")
                # Process media (Facebook videos, images, etc.)
                await process_media(e, ch)
                print(f"   ? Media processed for entry {e.get('guid')}")
                # Mark as seen and save
                seen.add(e['guid'])
                save_seen_guids(seen)
                # Rate limit to avoid Discord issues
                await asyncio.sleep(1)
        except Exception as channel_err:
            print(f"[ERROR] Error processing channel {ch_id}: {channel_err}")
            import traceback; traceback.print_exc()
    # Persist thread map
    with open(DETAILS_MAP_FILE, 'w') as f:
        json.dump(details_map, f, indent=2)

    print("[OK] Finished per-channel summaries and details threads")

async def run_bot_job():
    """The main logic of the bot, now encapsulated in a single function that runs once."""
    if not BOT_TOKEN:
        print("[WARNING]  Cannot start bot: DISCORD_BOT_TOKEN is not configured.")
        return
    # Initialize shared HTTP session now that event loop is running
    global HTTP_SESSION
    HTTP_SESSION = ClientSession(timeout=ClientTimeout(total=60))  # Increased timeout for large media
        
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True 
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user} to perform job.")
        await process_feeds_once(client)
        print("Job complete. Logging out.")
        await client.close()
        print("[DISCONNECT] Discord client closed after job.")
        # Close shared HTTP session
        if HTTP_SESSION is not None:
            await HTTP_SESSION.close()
        # Explicit exit to ensure clean shutdown
        import sys
        sys.exit(0)

    await client.start(BOT_TOKEN)

# === END FILE ===

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_bot_job())