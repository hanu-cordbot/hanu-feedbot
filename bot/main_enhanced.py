#!/usr/bin/env python3
"""
Enhanced bot main module with parallel processing, accurate counting, and R2 integration
"""
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
import concurrent.futures
from typing import Optional, cast, List, Dict, Tuple

import pendulum
import discord
import aiohttp
from aiohttp import ClientSession, ClientTimeout
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
    print("[WARNING] Warning: DISCORD_BOT_TOKEN is missing; run_bot_job will be disabled.")

# Load optional TARGET_CHANNEL_ID
channel_id_env = os.environ.get('CHANNEL_ID')
if channel_id_env:
    try:
        TARGET_CHANNEL_ID = int(channel_id_env)
    except ValueError:
        print(f"[CRITICAL] ERROR: CHANNEL_ID '{channel_id_env}' is not a valid integer. Ignoring.")
        TARGET_CHANNEL_ID = None
else:
    print("[WARNING] CHANNEL_ID not set; TARGET_CHANNEL_ID will be None.")
    TARGET_CHANNEL_ID = None

# Warn if optional environment variables are missing
for var in ('GEMINI_API_KEY', 'DISCORD_WEBHOOK_URL'):
    if var not in os.environ:
        print(f"[WARNING] Warning: {var} is missing. Related features may not work.")

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
from r2.uploader import upload_file as r2_upload_file

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

class ProcessingStats:
    """Track processing statistics"""
    def __init__(self):
        self.raw_entries = 0
        self.new_entries = 0
        self.posts_sent = 0
        self.media_processed = 0
        self.r2_uploads = 0
        self.catbox_uploads = 0
        self.errors = 0

# Global stats instance
STATS = ProcessingStats()

async def build_full_body_with_webhook(entry: dict) -> Tuple[str, Optional[dict]]:
    """Build full formatted body and extract webhook info for Discord posting."""
    maybe_update(entry)
    
    # Extract author information for Discord webhook
    webhook_data = None
    page_name = entry.get('page_name', '')
    if page_name:
        avatar_url = avatar_for(entry)
        webhook_data = {
            'username': page_name,
            'avatar_url': avatar_url
        }
    
    if len(entry.get('raw', '').split()) < SHORT_POST_WORD_THRESHOLD:
        parts = []
        title = entry.get('title', '')
        if title:
            parts.append(f"# **{title}**")
        raw = entry.get('raw', '')
        if raw and raw.strip() != title.strip():
            parts.append(raw)
        body = "\n\n".join(parts)
        content = f"{body}\n\n<{entry.get('link')}>"
    else:
        reply = await asyncio.to_thread(call_gemini, build_prompt(entry)) or ""
        if not reply:
            content = f"Error processing content\n\n<{entry.get('link')}>"
        else:
            body, tldr = split_reply(reply)
            full_content = body
            if tldr:
                full_content += f"\n\n{tldr}"
            content = f"{full_content}\n\n<{entry.get('link')}>"
    
    return content, webhook_data

async def upload_to_r2(file_data: bytes, filename: str) -> Optional[str]:
    """Upload file to R2 and return public URL."""
    try:
        # Generate unique key
        timestamp = int(time.time())
        key = f"videos/{timestamp}_{filename}"
        
        # Upload to R2
        with io.BytesIO(file_data) as file_obj:
            result = await asyncio.to_thread(r2_upload_file, file_obj, key, len(file_data))
        
        if result:
            # Construct public URL
            bucket = os.environ.get('R2_BUCKET')
            public_base = os.environ.get('R2_PUBLIC_BASE')
            if public_base:
                return f"{public_base}/{key}"
            else:
                account_id = os.environ.get('R2_ACCOUNT_ID')
                return f"https://{account_id}.r2.cloudflarestorage.com/{bucket}/{key}"
        
        return None
    except Exception as e:
        print(f"[ERROR] R2 upload failed: {e}")
        return None

async def process_media_enhanced(entry: dict, channel: discord.TextChannel) -> bool:
    """Enhanced media processing with R2 integration and better handling."""
    # Discord file size limits
    DISCORD_LIMIT = 8 * 1024 * 1024  # 8MB Discord file limit
    R2_THRESHOLD = 10 * 1024 * 1024  # 10MB threshold for R2
    
    video_exts = ('.mp4', '.webm', '.mov', '.mkv')
    image_exts = ('.jpg', '.jpeg', '.png', '.gif')
    media_urls = entry.get('media_all', []) or []
    media_files = []
    video_processed = False
    
    # Create a manual temp directory instead of using context manager
    temp_dir = tempfile.mkdtemp(prefix="hanu_feedbot_")
    TEMP_DIRS_TO_CLEANUP.append(temp_dir)
    
    try:
        # STEP 1: Try to extract video from post URL
        post_url = entry.get('link', '')
        if "facebook.com" in post_url:
            print(f"[DOWNLOAD] Trying video download from post URL: {post_url}")
            
            download_path = os.path.join(temp_dir, f"facebook_video_{random.randint(1000, 9999)}.mp4")
            file_path = await download_video_ytdlp(post_url, output_path=download_path)
            
            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                if file_size > 100000:  # Ensure it's not just a thumbnail
                    print(f"[OK] Downloaded video: {file_size/1024/1024:.2f}MB")
                    
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                    
                    # Check size thresholds
                    if file_size > R2_THRESHOLD:
                        print(f"[UPLOAD] Video too large ({file_size/1024/1024:.2f}MB), uploading to R2...")
                        r2_url = await upload_to_r2(file_data, "facebook_video.mp4")
                        if r2_url:
                            print(f"[OK] Uploaded to R2: {r2_url}")
                            STATS.r2_uploads += 1
                            await channel.send(f"🎥 **Video**: {r2_url}")
                            video_processed = True
                        else:
                            print("[ERROR] R2 upload failed, trying Catbox...")
                            from bot.dispatcher import upload_to_catbox
                            catbox_url = upload_to_catbox(file_data)
                            if catbox_url:
                                print(f"[OK] Uploaded to Catbox: {catbox_url}")
                                STATS.catbox_uploads += 1
                                await channel.send(f"🎥 **Video**: {catbox_url}")
                                video_processed = True
                    elif file_size > DISCORD_LIMIT:
                        print(f"[UPLOAD] Video medium size ({file_size/1024/1024:.2f}MB), uploading to Catbox...")
                        from bot.dispatcher import upload_to_catbox
                        catbox_url = upload_to_catbox(file_data)
                        if catbox_url:
                            print(f"[OK] Uploaded to Catbox: {catbox_url}")
                            STATS.catbox_uploads += 1
                            await channel.send(f"🎥 **Video**: {catbox_url}")
                            video_processed = True
                    else:
                        print(f"[UPLOAD] Video small enough for Discord ({file_size/1024/1024:.2f}MB)")
                        media_files.append(discord.File(file_path, filename="facebook_video.mp4"))
                        video_processed = True
        
        # STEP 2: Process individual media URLs if no video found
        if not video_processed and media_urls:
            print("[MEDIA] Processing individual media URLs")
            for url in media_urls[:10]:  # Discord limit
                try:
                    # Direct video links
                    path = url.split('?')[0].lower()
                    if any(path.endswith(ext) for ext in video_exts):
                        video_data = await download_bytes(url)
                        if len(video_data) > R2_THRESHOLD:
                            filename = url.split('/')[-1].split('?')[0] or 'video.mp4'
                            r2_url = await upload_to_r2(video_data, filename)
                            if r2_url:
                                print(f"[OK] Large video uploaded to R2: {r2_url}")
                                STATS.r2_uploads += 1
                                await channel.send(f"🎥 **Video**: {r2_url}")
                                continue
                        
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
                    print(f"[ERROR] Failed to download media {url}: {err}")
                    STATS.errors += 1
        
        # Send media files to channel
        if media_files:
            print(f"[UPLOAD] Sending {len(media_files)} media files to Discord")
            try:
                await channel.send(files=media_files)
                print("[OK] Media files sent successfully")
                STATS.media_processed += len(media_files)
            except discord.errors.HTTPException as e:
                if "Payload Too Large" in str(e) or "40005" in str(e):
                    print(f"[WARNING] Files too large for Discord: {e}")
                    STATS.errors += 1
                else:
                    print(f"[ERROR] Error sending media: {e}")
                    STATS.errors += 1
        
        return video_processed
    
    finally:
        # Add temp directory to global cleanup list if not already there
        if temp_dir not in TEMP_DIRS_TO_CLEANUP:
            TEMP_DIRS_TO_CLEANUP.append(temp_dir)

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
    
    # 2) Check if a thread already exists for this SPECIFIC message
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
            print(f"[CRITICAL] Thread exists but we can't find it. Message ID: {summary_msg.id}")
            
            # Last resort: try to find ANY thread with "Details" name for this channel today
            for t in channel.threads:
                if t.name == "Details":
                    print(f"Found fallback Details thread: {t.id}")
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

async def process_entries_parallel(entries: List[dict], channel: discord.TextChannel, thread: discord.Thread) -> int:
    """Process multiple entries in parallel for Gemini API calls, but send sequentially to Discord."""
    
    # Step 1: Build all content in parallel (this is where Gemini API calls happen)
    print(f"[PARALLEL] Building content for {len(entries)} entries in parallel...")
    
    async def build_entry_content(entry: dict) -> Tuple[dict, str, Optional[dict]]:
        """Build content for a single entry."""
        try:
            content, webhook_data = await build_full_body_with_webhook(entry)
            return entry, content, webhook_data
        except Exception as e:
            print(f"[ERROR] Failed to build content for entry {entry.get('guid')}: {e}")
            STATS.errors += 1
            return entry, f"Error processing content\n\n<{entry.get('link')}>", None
    
    # Execute all content building in parallel
    tasks = [build_entry_content(entry) for entry in entries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Step 2: Send to Discord sequentially (to maintain order and avoid rate limits)
    posts_sent = 0
    for result in results:
        if isinstance(result, Exception):
            print(f"[ERROR] Entry processing failed: {result}")
            STATS.errors += 1
            continue
            
        entry, content, webhook_data = result
        
        try:
            print(f"[POST] Sending entry: {entry.get('title', 'No title')[:50]}...")
            
            # Send content to thread
            last_msg = None
            for idx in range(0, len(content), 2000):
                chunk = content[idx:idx+2000]
                if webhook_data and idx == 0:  # Use webhook for first message only
                    # Get webhook URL for this channel
                    webhook_url = get_or_create_webhook_url(channel)
                    if webhook_url:
                        try:
                            import aiohttp
                            async with HTTP_SESSION.post(webhook_url, json={
                                'content': chunk,
                                'username': webhook_data['username'],
                                'avatar_url': webhook_data['avatar_url']
                            }) as resp:
                                if resp.status == 200:
                                    print(f"[OK] Sent via webhook as {webhook_data['username']}")
                                else:
                                    # Fallback to regular send
                                    last_msg = await thread.send(chunk)
                        except Exception as webhook_err:
                            print(f"[WARNING] Webhook send failed, using regular send: {webhook_err}")
                            last_msg = await thread.send(chunk)
                    else:
                        last_msg = await thread.send(chunk)
                else:
                    last_msg = await thread.send(chunk)
            
            # Update summary
            if last_msg:
                summary_msg = await channel.fetch_message(thread.parent_id)
                await update_daily_summary_message(summary_msg, entry, last_msg)
            
            # Process media
            await process_media_enhanced(entry, channel)
            
            posts_sent += 1
            STATS.posts_sent += 1
            
            # Rate limiting
            await asyncio.sleep(1)
            
        except Exception as send_err:
            print(f"[ERROR] Failed to send entry {entry.get('guid')}: {send_err}")
            STATS.errors += 1
    
    return posts_sent

async def process_feeds_once(client: discord.Client):
    """Enhanced feed processing with accurate counting and parallel optimization."""
    global STATS
    STATS = ProcessingStats()  # Reset stats
    
    print("[IMPORT] Starting enhanced feed processing...")
    
    # Collect all parsed entries and filter new ones
    print("Collecting and filtering parsed entries...")
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
        STATS.raw_entries += 1
        cid = user_map.get(e['feed']) or GLOBAL_FALLBACK_CHANNEL_ID
        if not cid or e['guid'] in seen:
            continue
        age = (now - e.get('published', now)).total_hours()
        if age > MAX_AGE_HOURS:
            continue
        new_posts.append(e)
        STATS.new_entries += 1

    # Accurate counting output
    print(f"[STATS] Raw entries parsed: {STATS.raw_entries}")
    print(f"[STATS] New entries to process: {STATS.new_entries}")
    print(f"[STATS] Posts ready for Discord: {len(new_posts)}")
    
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

    # Process each channel
    channels = list(channel_groups.items())
    print(f"[IMPORT] Will process {len(channels)} channels")
    
    for ch_idx, (ch_id, entries) in enumerate(channels, start=1):
        print(f"[{ch_idx}/{len(channels)}] Processing channel {ch_id} ({len(entries)} entries)")
        try:
            ch = client.get_channel(ch_id)
            if not isinstance(ch, discord.TextChannel):
                print(f"Skipping non-text channel {ch_id}")
                continue
                
            # Get/create summary and thread
            vietnamese_date = format_vietnamese_date(now)
            summary = await get_daily_summary_message(ch, today)
            print(f"Summary message for channel {ch_id}: {summary and getattr(summary, 'id', None)}")
            
            if not summary:
                summary = await create_daily_summary_message(ch, vietnamese_date)
                print(f"Created new summary message: {summary and getattr(summary, 'id', None)}")
                if not summary:
                    continue
                    
            thread = await get_or_create_channel_details_thread(client, ch, summary, details_map)
            print(f"Using thread: {getattr(thread, 'id', None)}")
            
            # Process entries in parallel for this channel
            channel_posts_sent = await process_entries_parallel(entries, ch, thread)
            print(f"[OK] Channel {ch_id}: sent {channel_posts_sent}/{len(entries)} posts")
            
            # Mark all entries as seen
            for e in entries:
                seen.add(e['guid'])
            save_seen_guids(seen)
            
        except Exception as channel_err:
            print(f"[ERROR] Error processing channel {ch_id}: {channel_err}")
            STATS.errors += 1
            import traceback
            traceback.print_exc()

    # Persist thread map
    with open(DETAILS_MAP_FILE, 'w') as f:
        json.dump(details_map, f, indent=2)

    # Final statistics
    print("\n" + "="*50)
    print("PROCESSING COMPLETE - FINAL STATS")
    print("="*50)
    print(f"Raw entries parsed: {STATS.raw_entries}")
    print(f"New entries found: {STATS.new_entries}")
    print(f"Posts sent to Discord: {STATS.posts_sent}")
    print(f"Media files processed: {STATS.media_processed}")
    print(f"R2 uploads: {STATS.r2_uploads}")
    print(f"Catbox uploads: {STATS.catbox_uploads}")
    print(f"Errors encountered: {STATS.errors}")
    print("="*50)

async def run_bot_job():
    """The main logic of the bot, now encapsulated in a single function that runs once."""
    if not BOT_TOKEN:
        print("[WARNING] Cannot start bot: DISCORD_BOT_TOKEN is not configured.")
        return
        
    # Initialize shared HTTP session now that event loop is running
    global HTTP_SESSION
    HTTP_SESSION = ClientSession(timeout=ClientTimeout(total=60))
        
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
