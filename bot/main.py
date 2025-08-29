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
from dotenv import load_dotenv

# Load all environment variables from .env for local development
load_dotenv()

# --- GLOBAL CONFIGURATION ---
print("Initializing configuration...")

# Global cleanup list for temporary directories
TEMP_DIRS_TO_CLEANUP = []

# HTTP session will be created when needed
HTTP_SESSION = None

# Load DISCORD_BOT_TOKEN, warn if missing
BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
if not BOT_TOKEN:
    print("⚠️  Warning: DISCORD_BOT_TOKEN is missing; run_bot_job will be disabled.")

# Load optional TARGET_CHANNEL_ID
channel_id_env = os.environ.get('CHANNEL_ID')
if channel_id_env:
    try:
        TARGET_CHANNEL_ID = int(channel_id_env)
    except ValueError:
        print(f"🚨 ERROR: CHANNEL_ID '{channel_id_env}' is not a valid integer. Ignoring.")
        TARGET_CHANNEL_ID = None
else:
    print("⚠️  CHANNEL_ID not set; TARGET_CHANNEL_ID will be None.")
    TARGET_CHANNEL_ID = None

# Warn if optional environment variables are missing
for var in ('GEMINI_API_KEY', 'DISCORD_WEBHOOK_URL'):
    if var not in os.environ:
        print(f"⚠️  Warning: {var} is missing. Related features may not work.")

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

# Import migrated config paths
from bot.config import SEEN_DB
SEEN_FILE = str(SEEN_DB)  # Use migrated dashboard/data/seen.json path
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
from bot.config import SEEN_R2_BUCKET, r2_client
from bot.facebook_downloader import download_video_ytdlp, normalize_url
from bot.r2_video import (
    upload_video_to_r2_async,
    create_video_embed_message,
    should_use_r2_storage,
    get_video_size_limit
)

print("✅ Configuration loaded.")

# Discord file size limit
DISCORD_LIMIT = get_video_size_limit()  # 8MB

# --- HELPER FUNCTIONS ---
def get_http_session():
    """Get or create the HTTP session"""
    global HTTP_SESSION
    if HTTP_SESSION is None or HTTP_SESSION.closed:
        HTTP_SESSION = ClientSession(timeout=ClientTimeout(total=60))
    return HTTP_SESSION

async def download_bytes(url: str) -> bytes:
    """Fetch raw bytes for a media URL."""
    # Use shared HTTP_SESSION with increased timeout for large media
    session = get_http_session()
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
        resp.raise_for_status()
        return await resp.read()

def _split_message_by_newline(content: str, limit: int = 2000) -> list[str]:
    """Split content into chunks <= limit, preferring newline breaks over mid-line cuts."""
    if len(content) <= limit:
        return [content]
    parts = content.split("\n")
    chunks: list[str] = []
    current = ""
    for p in parts:
        add = p if not current else ("\n" + p)
        if len(current) + len(add) > limit:
            if current:
                chunks.append(current)
            current = p
        else:
            current += add
    if current:
        chunks.append(current)
    return chunks

def load_seen_guids():
    """Loads the set of processed post IDs from the state file."""
    print(f"🔍 Loading seen guids from: {SEEN_FILE}")
    # If R2 is configured, try to download seen.json from R2 first
    try:
        client = r2_client()
        if client:
            try:
                import io, gzip
                buf = io.BytesIO()
                # Prefer dashboard/data/source/seen.json, then dashboard/data/seen.json, fallback to legacy seen.json
                last_err = None
                for key in ('dashboard/data/source/seen.json', 'dashboard/data/seen.json', 'seen.json'):
                    try:
                        buf.seek(0); buf.truncate(0)
                        client.download_fileobj(SEEN_R2_BUCKET, key, buf)
                        break
                    except Exception as ex:
                        last_err = ex
                        continue
                else:
                    raise last_err or Exception('seen.json not found in R2')
                buf.seek(0)
                # Try to detect gzip by magic header
                head = buf.read(2)
                buf.seek(0)
                if head == b'\x1f\x8b':
                    with gzip.GzipFile(fileobj=buf, mode='rb') as gz:
                        data = gz.read().decode('utf-8')
                        seen = set(json.loads(data))
                        print(f"🔁 Loaded {len(seen)} guids from R2")
                        return seen
                else:
                    seen = set(json.load(buf))
                    print(f"🔁 Loaded {len(seen)} guids from R2 (plain)")
                    return seen
            except Exception as e:
                print(f"⚠️ Could not fetch seen.json from R2: {e}")
        # Fallback to local file
        if os.path.exists(SEEN_FILE):
            with open(SEEN_FILE, 'r') as f:
                seen = set(json.load(f))
                print(f"📂 Loaded {len(seen)} guids from local {SEEN_FILE}")
                return seen
        else:
            print(f"{SEEN_FILE} does not exist locally; initializing empty seen set")
            return set()
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"'{SEEN_FILE}' not found or invalid. Initializing a new one.")
        return set()

def save_seen_guids(guids):
    """Saves the set of processed post IDs to the state file."""
    # Write atomically to avoid corruption between runs
    try:
        import tempfile
        dir_name = os.path.dirname(SEEN_FILE) or '.'
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="seen-", suffix=".tmp")
        with os.fdopen(fd, 'w') as tmpf:
            json.dump(list(guids)[-500:], tmpf, indent=2)
            tmpf.flush()
            os.fsync(tmpf.fileno())
        # Atomic replace
        os.replace(tmp_path, SEEN_FILE)
    except Exception as e:
        print(f"⚠️ Failed to save seen guids atomically: {e}")
        # Fallback to simple write
        try:
            with open(SEEN_FILE, 'w') as f:
                json.dump(list(guids)[-500:], f, indent=2)
        except Exception as e2:
            print(f"❌ Failed to write seen file: {e2}")

    # If R2 is configured, also upload the seen.json to R2 for persistent state across runners
    try:
        client = r2_client()
        if client:
            import io
            buf = io.BytesIO()
            # Write plain JSON bytes (no gzip)
            buf.write(json.dumps(list(guids)[-500:]).encode('utf-8'))
            buf.seek(0)
            # Upload plain JSON content under dashboard/data/source/seen.json (authoritative)
            try:
                client.upload_fileobj(buf, SEEN_R2_BUCKET, 'dashboard/data/source/seen.json')
            except TypeError:
                # Fallback if client.upload_fileobj signature differs
                client.put_object(Bucket=SEEN_R2_BUCKET, Key='dashboard/data/source/seen.json', Body=buf.getvalue())
    except Exception as e:
        print(f"⚠️ Could not upload seen.json to R2: {e}")

async def build_full_body(entry: dict) -> str:
    """Build full formatted body for an entry using existing logic."""
    maybe_update(entry)
    # Remove useless FB error bodies like "This content isn't available right now".
    raw_text = (entry.get('raw') or '').strip()
    lowered = raw_text.lower()
    unavailable_markers = [
        "this content isn't available right now",
        "this post isn't available right now",
        "bài viết hiện không khả dụng",
        "không khả dụng"
    ]
    if any(m in lowered for m in unavailable_markers):
        raw_text = ""

    if len(raw_text.split()) < SHORT_POST_WORD_THRESHOLD:
        parts = []
        title = entry.get('title', '')
        if title:
            parts.append(f"# **{title}**")
        if raw_text and raw_text.strip() != title.strip():
            parts.append(raw_text)
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
        print(f"⚠️ Could not fetch fresh message: {e}")
    
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
            print(f"🚨 CRITICAL: Thread exists but we can't find it. Message ID: {summary_msg.id}")
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
                print(f"🚨 Even unique thread creation failed: {fallback_e}")
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
            print(f"🎯 FOUND TARGET POST ID in entry!")
            target_url = "https://www.facebook.com/720895507364955/posts/743124275142078"
            print(f"📥 Downloading video from known target URL: {target_url}")
            
            # Generate unique filenames
            download_path = os.path.join(temp_dir, f"facebook_video_{random.randint(1000, 9999)}.mp4")
            
            # Download the video
            file_path = await download_video_ytdlp(target_url, output_path=download_path)
            
            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                print(f"✅ Downloaded target video: {file_size/1024/1024:.2f}MB")
                
                # Check if file is too large for Discord
                if file_size > DISCORD_LIMIT:
                    print(f"⚠️ Video too large for Discord ({file_size/1024/1024:.2f}MB > {DISCORD_LIMIT/1024/1024}MB)")
                    
                    # Read file data
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                    
                    if should_use_r2_storage(file_size):
                        print(f"📤 Uploading to R2...")
                        
                        # Try R2 first
                        post_title = entry.get('title', entry.get('page_name', 'Facebook Video'))
                        r2_url = await upload_video_to_r2_async(file_data, post_title)
                        
                        if r2_url:
                            print(f"✅ Uploaded to R2: {r2_url}")
                            # Send as a formatted embed message
                            video_message = create_video_embed_message(r2_url, post_title, target_url)
                            await channel.send(video_message)
                            video_processed = True
                        else:
                            # Fallback to Catbox if R2 fails
                            print(f"📤 R2 failed, falling back to Catbox...")
                            from bot.dispatcher import upload_to_catbox
                            catbox_url = upload_to_catbox(file_data)
                            if catbox_url:
                                print(f"✅ Uploaded to Catbox: {catbox_url}")
                                await channel.send(f"Video from post: {target_url}\n{catbox_url}")
                                video_processed = True
                            else:
                                print("❌ Failed to upload to both R2 and Catbox")
                    else:
                        print(f"📤 Video too large even for external storage")
                else:
                    # Small enough for Discord, send directly
                    print(f"📤 Video small enough for Discord ({file_size/1024/1024:.2f}MB)")
                    media_files.append(discord.File(file_path, filename="facebook_video.mp4"))
                    video_processed = True
        
        # STEP 2: Try to extract video directly from post URL if target not found
        if not video_processed:
            post_url = entry.get('link', '')
            if "facebook.com" in post_url:
                print(f"📥 Trying direct video download from post URL: {post_url}")
                
                download_path = os.path.join(temp_dir, f"facebook_video_{random.randint(1000, 9999)}.mp4")
                file_path = await download_video_ytdlp(post_url, output_path=download_path)
                
                if file_path and os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    if file_size > 100000:  # Ensure it's not just a thumbnail
                        print(f"✅ Downloaded video from post URL: {file_size/1024/1024:.2f}MB")
                        
                        # Check if too large for Discord
                        if file_size > DISCORD_LIMIT:
                            with open(file_path, 'rb') as f:
                                file_data = f.read()
                            
                            if should_use_r2_storage(file_size):
                                # Try R2 first
                                post_title = entry.get('title', entry.get('page_name', 'Facebook Video'))
                                r2_url = await upload_video_to_r2_async(file_data, post_title)
                                
                                if r2_url:
                                    video_message = create_video_embed_message(r2_url, post_title, post_url)
                                    await channel.send(video_message)
                                    video_processed = True
                                else:
                                    # Fallback to Catbox
                                    from bot.dispatcher import upload_to_catbox
                                    catbox_url = upload_to_catbox(file_data)
                                    if catbox_url:
                                        await channel.send(f"Video from post: {post_url}\n{catbox_url}")
                                        video_processed = True
                        else:
                            media_files.append(discord.File(file_path, filename="facebook_video.mp4"))
                            video_processed = True
                    else:
                        print(f"⚠️ Downloaded file too small: {file_size} bytes")
                else:
                    print(f"❌ No video found at post URL")
        
        # STEP 3: Only if no video processed, try individual media URLs
        if not video_processed:
            print("📷 No video found, processing individual media URLs")
            for url in media_urls:
                if len(media_files) >= 10:  # Discord limit
                    break
                try:
                    # Skip CDN/thumbnail URLs if we've found our target post ID
                    if "743124275142078" in entry_str and ("fbcdn.net" in url or "scontent-" in url):
                        print(f"⚠️ Skipping CDN URL for target post: {url}")
                        continue
                        
                    # Facebook video posts
                    video_norm = normalize_url(url)
                    if video_norm and "facebook.com" in video_norm:
                        print(f"📥 Trying video download from media URL: {video_norm}")
                        download_path = os.path.join(temp_dir, f"facebook_video_{random.randint(1000, 9999)}.mp4")
                        file_path = await download_video_ytdlp(video_norm, output_path=download_path)
                        
                        if file_path and os.path.exists(file_path):
                            file_size = os.path.getsize(file_path)
                            if file_size > 100000:
                                print(f"✅ Downloaded video from media URL: {file_size/1024/1024:.2f}MB")
                                
                                # Check if too large for Discord
                                if file_size > DISCORD_LIMIT:
                                    with open(file_path, 'rb') as f:
                                        file_data = f.read()
                                    
                                    if should_use_r2_storage(file_size):
                                        # Try R2 first
                                        post_title = entry.get('title', entry.get('page_name', 'Facebook Video'))
                                        r2_url = await upload_video_to_r2_async(file_data, post_title)
                                        
                                        if r2_url:
                                            video_message = create_video_embed_message(r2_url, post_title, video_norm)
                                            await channel.send(video_message)
                                            video_processed = True
                                        else:
                                            # Fallback to Catbox
                                            from bot.dispatcher import upload_to_catbox
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
            print(f"📤 Sending {len(media_files)} media files to channel")
            try:
                await channel.send(files=media_files)
                print("✅ Media files sent successfully")
            except discord.errors.HTTPException as e:
                if "Payload Too Large" in str(e) or "40005" in str(e):
                    print(f"⚠️ File too large for Discord, fallback not implemented for this case")
                else:
                    print(f"❌ Error sending media: {e}")
                import traceback
                traceback.print_exc()
        
        return video_processed
    
    finally:
        # Add temp directory to global cleanup list if not already there
        if temp_dir not in TEMP_DIRS_TO_CLEANUP:
            TEMP_DIRS_TO_CLEANUP.append(temp_dir)

async def process_entry_in_thread(client, entry, thread, summary):
    """Process a single entry in a text channel thread via webhook (impersonate FB poster)."""
    body = await build_full_body(entry)
    # Send via webhook so messages show as the FB poster
    parent = getattr(thread, 'parent', None)
    webhook_url = await get_or_create_webhook_url(parent or thread)
    webhook = discord.Webhook.from_url(webhook_url, client=client)
    username = (entry.get('page_name') or '').strip() or 'Facebook Page'
    avatar = avatar_for(entry)
    last_msg = None
    for chunk in _split_message_by_newline(body):
        last_msg = await webhook.send(content=chunk, username=username, avatar_url=avatar, thread=discord.Object(id=thread.id), wait=True)
    
    # Update per-channel summary if we have a posted message
    if last_msg:
        await update_daily_summary_message(summary, entry, last_msg)

        print(f"❌ Skipping forum post for '{title}' due to above error")

# Override with webhook-based forum posting so the sender appears as the FB page
async def process_entry_in_forum(client, entry, forum_channel):
    """Create a forum thread via webhook using FB page identity and post content in newline-safe chunks."""
    title = (entry.get('title') or 'Post')[:100]
    try:
        from bot.formatter import build_thread_title_prompt
        gen = await asyncio.to_thread(call_gemini, build_thread_title_prompt(entry.get('raw', '') or ''))
        if gen:
            title = gen.strip().splitlines()[0][:100]
    except Exception:
        pass

    # Collect media
    media_urls = entry.get('media_all', []) or []
    image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
    video_exts = ('.mp4', '.mov', '.webm', '.mkv')
    video_link = None
    image_files: list[discord.File] = []
    for url in media_urls:
        u = (url or '').split('?')[0].lower()
        try:
            if video_link is None and (u.endswith(video_exts) or '/videos/' in u):
                video_link = url
                continue
            if u.endswith(image_exts):
                data = await download_bytes(url)
                if len(data) > DISCORD_LIMIT:
                    continue
                name = url.split('/')[-1].split('?')[0] or 'image.jpg'
                image_files.append(discord.File(io.BytesIO(data), filename=name))
        except Exception:
            continue

    # Build body text and strip trailing original link
    body_full = await build_full_body(entry)
    post_link = entry.get('link') or ''
    link_token = f"<{post_link}>" if post_link else ''
    if link_token and body_full.rstrip().endswith(link_token):
        body_text = body_full[: body_full.rfind(link_token)].rstrip()
    else:
        body_text = body_full
    chunks = _split_message_by_newline(body_text) or [" "]

    try:
        webhook_url = await get_or_create_webhook_url(forum_channel)
        webhook = discord.Webhook.from_url(webhook_url, client=client)
        username = (entry.get('page_name') or '').strip() or 'Facebook Page'
        avatar = avatar_for(entry)
        # Create thread with media or text
        if video_link:
            msg = await webhook.send(content=video_link, username=username, avatar_url=avatar, thread_name=title, wait=True)
        elif image_files:
            first_batch = image_files[:10]
            msg = await webhook.send(username=username, avatar_url=avatar, thread_name=title, files=first_batch, wait=True)
        else:
            msg = await webhook.send(content=chunks[0], username=username, avatar_url=avatar, thread_name=title, wait=True)
        thread = msg.channel
        # Send remaining images batches
        if len(image_files) > 10:
            for i in range(10, len(image_files), 10):
                await webhook.send(username=username, avatar_url=avatar, thread=discord.Object(id=thread.id), files=image_files[i:i+10], wait=False)
        # Post details below media
        if post_link:
            await webhook.send(content=f"Details - <{post_link}>", username=username, avatar_url=avatar, thread=discord.Object(id=thread.id), wait=False)
        # Post remaining text chunks (skip first if used as initial content)
        start_idx = 1 if (not video_link and not image_files and chunks) else 0
        for chunk in chunks[start_idx:]:
            await webhook.send(content=chunk, username=username, avatar_url=avatar, thread=discord.Object(id=thread.id), wait=False)
        return
    except Exception as e:
        print(f"⚠️ Webhook forum post failed: {e}")
        # Fallback to direct API (bot identity)
        try:
            first = video_link or (chunks[0] if chunks else ' ')
            thread = await forum_channel.create_thread(name=title, content=first)
            if image_files:
                for i in range(0, len(image_files), 10):
                    await thread.send(files=image_files[i:i+10])
            if post_link:
                await thread.send(f"Details - <{post_link}>")
            for chunk in (chunks[1:] if (not video_link and not image_files) else chunks):
                try:
                    await thread.send(chunk)
                except Exception:
                    pass
        except Exception as e2:
            print(f"❌ Direct forum thread creation also failed: {e2}")

async def process_feeds_once(client: discord.Client):
    """Scans feeds and processes new entries per-channel summary."""
    seen = load_seen_guids()
    now = pendulum.now('Asia/Ho_Chi_Minh')
    today = now.format('YYYY-MM-DD')

    # Load mappings and thread map
    try:
        # Try dashboard/data/source/feed_map.json first (preferred), then dashboard/data/feed_map.json, fallback to root
        source_path = os.path.join(BASE_DIR, 'dashboard', 'data', 'source', 'feed_map.json')
        dashboard_path = os.path.join(BASE_DIR, 'dashboard', 'data', 'feed_map.json')
        root_path = os.path.join(BASE_DIR, 'feed_map.json')
        
        if os.path.exists(source_path):
            with open(source_path, 'r') as f:
                raw_map = json.load(f)
            # Handle both formats: {"url": "channel_id"} or {"url": {"id": "channel_id", ...}}
            user_map = {}
            for url, value in raw_map.items():
                if isinstance(value, dict):
                    channel_id = value.get('id', '') or value.get('channel') or value.get('channel_id')
                    if channel_id:
                        user_map[url] = str(channel_id)
                else:
                    user_map[url] = str(value)
            print(f"🔧 Processed dashboard/data/source/feed_map.json: {len(raw_map)} entries -> {len(user_map)} valid mappings")
        elif os.path.exists(dashboard_path):
            with open(dashboard_path, 'r') as f:
                raw_map = json.load(f)
            # Handle both formats: {"url": "channel_id"} or {"url": {"id": "channel_id", ...}}
            user_map = {}
            for url, value in raw_map.items():
                if isinstance(value, dict):
                    channel_id = value.get('id', '') or value.get('channel') or value.get('channel_id')
                    if channel_id:
                        user_map[url] = str(channel_id)
                else:
                    user_map[url] = str(value)
            print(f"🔧 Processed dashboard/data/feed_map.json: {len(raw_map)} entries -> {len(user_map)} valid mappings")
        elif os.path.exists(root_path):
            with open(root_path, 'r') as f:
                user_map = json.load(f)
            print(f"🔧 Used fallback root feed_map.json: {len(user_map)} mappings")
        else:
            user_map = {}
            print("🔧 No feed_map.json found, using empty mappings")
    except Exception as e:
        user_map = {}
        print(f"🔧 Error loading feed_map: {e}")
    # Debug: surface how many mappings we loaded and a small sample
    try:
        print(f"🔎 Loaded feed_map.json with {len(user_map)} mappings")
        if user_map:
            sample_keys = list(user_map.keys())[:10]
            print(f"🔎 Sample feed_map keys: {sample_keys}")
            # Also show the first few channel IDs for debugging
            sample_values = {k: user_map[k] for k in sample_keys[:3]}
            print(f"🔎 Sample mappings: {sample_values}")
    except Exception:
        pass
    try:
        with open(DETAILS_MAP_FILE) as f: 
            details_map = json.load(f)
    except: 
        details_map = {}

    # Collect new entries - scan ALL feeds but only process those with channel mappings
    new_posts = []
    scanned_count = 0
    seen_count = 0
    age_filtered_count = 0
    unmatched_examples = set()
    mapped_feed_count = 0
    for e in iter_entries():
        scanned_count += 1

        # Skip if already seen
        if e['guid'] in seen:
            seen_count += 1
            continue

        # Determine feed URL and whether it is mapped up-front so we can
        # optionally bypass age filtering for mapped feeds.
        raw_feed = e.get('feed')
        cid = None
        try:
            cid = user_map.get(raw_feed) or user_map.get(str(raw_feed).strip()) or user_map.get(str(raw_feed).rstrip('/'))
        except Exception:
            cid = user_map.get(raw_feed)
        is_mapped_feed = bool(cid)

        # Age check (skip in test mode if FORCE_IGNORE_AGE is set).
        # Mapped feeds bypass the age check so newly mapped feeds get delivered
        # even if their entries are older than MAX_AGE_HOURS.
        force_ignore_age = os.getenv('FORCE_IGNORE_AGE', 'false').lower() == 'true'
        if not force_ignore_age and not is_mapped_feed:
            published_date = e.get('published')
            if published_date is None:
                # If no published date, treat as current time (fresh entry)
                age = 0
            else:
                age = (now - published_date).total_seconds() / 3600  # Convert to hours
            if age > MAX_AGE_HOURS:
                age_filtered_count += 1
                continue
        
        # Use mapping determined earlier (to avoid duplicate lookups)
        if is_mapped_feed and cid:
            # Only add entries that have explicit channel mappings
            try:
                e['target_channel'] = int(str(cid))  # Store the target channel for later processing
            except Exception:
                # Last resort: skip if cid is malformed
                print(f"❌ Invalid channel id for feed {raw_feed}: {cid}")
                continue
            new_posts.append(e)
            mapped_feed_count += 1
            # If the entry was older than MAX_AGE_HOURS but the feed is mapped,
            # indicate we bypassed the age filter so maintainers can see why.
            try:
                published_date = e.get('published')
                if published_date is not None:
                    age = (now - published_date).total_seconds() / 3600
                    if age > MAX_AGE_HOURS:
                        print(f"⚠️ Bypassed age filter for mapped feed {raw_feed} (age={age:.1f}h)")
            except Exception:
                pass
            print(f"✅ Matched entry: {e.get('title', 'No title')[:50]} from {raw_feed} -> {cid}")
        else:
            if raw_feed and len(unmatched_examples) < 10:
                unmatched_examples.add(raw_feed)
        
        # Add GUID to seen set regardless of whether it has a channel mapping
        # This prevents reprocessing the same entries even if they get channel mappings later
        seen.add(e['guid'])
        
        # Limit entries in test mode
        test_entries_count = int(os.getenv('TEST_ENTRIES_COUNT', '999'))
        if len(new_posts) >= test_entries_count:
            print(f"🧪 Test mode: Limited to {test_entries_count} entries")
            break
    
    print(f"📊 Scanned {scanned_count} entries, found {len(new_posts)} with channel mappings")
    print(f"📋 Breakdown: {seen_count} already seen, {age_filtered_count} filtered by age, {mapped_feed_count} from mapped feeds")

    if unmatched_examples:
        try:
            print(f"⚠️ Sample unmatched feeds (first {len(unmatched_examples)}): {list(unmatched_examples)}")
        except Exception:
            pass

    if not new_posts:
        # Ensure we persist the current seen set (may be freshly initialized)
        try:
            save_seen_guids(seen)
            print("No new entries this cycle. Persisted seen.json.")
        except Exception:
            print("No new entries this cycle.")
        return

    # Bucket by channel using the stored target_channel
    channel_groups = defaultdict(list)
    for e in new_posts:
        ch_id = e.get('target_channel')
        if ch_id:
            channel_groups[ch_id].append(e)

    # Process each channel
    for ch_id, entries in channel_groups.items():
        ch = client.get_channel(ch_id)
        
        # Support both TextChannel and ForumChannel
        if isinstance(ch, discord.TextChannel):
            # Regular text channel processing
            vietnamese_date = format_vietnamese_date(now)
            summary = await get_daily_summary_message(ch, today)
            if not summary:
                summary = await create_daily_summary_message(ch, vietnamese_date)
                if not summary:
                    continue

            # Single Details thread under summary
            thr = await get_or_create_channel_details_thread(client, ch, summary, details_map)

            # Post full entries in that thread and update per-channel summary
            for e in entries:
                await process_entry_in_thread(client, e, thr, summary)
                
                # Process media (Facebook videos, images, etc.)
                await process_media(e, ch)
                
                # Mark as seen and save
                seen.add(e['guid'])
                save_seen_guids(seen)
                
                # Rate limit to avoid Discord issues
                await asyncio.sleep(1)
                
        elif isinstance(ch, discord.ForumChannel):
            # Forum channel - create separate thread for each entry
            print(f"Processing {len(entries)} entries for forum channel: {ch.name}")
            for e in entries:
                await process_entry_in_forum(client, e, ch)
                # Mark as seen and save
                seen.add(e['guid'])
                save_seen_guids(seen)
                # Rate limit to avoid Discord issues
                await asyncio.sleep(1)
        else:
            print(f"Skipping unsupported channel type {type(ch)} for channel {ch_id}")
            continue

    # Persist thread map
    with open(DETAILS_MAP_FILE, 'w') as f:
        json.dump(details_map, f, indent=2)

    # Always persist seen state at the end of a successful run (final upload to R2)
    try:
        save_seen_guids(seen)
    except Exception as e:
        print(f"⚠️ Failed to persist final seen state: {e}")

    print("✅ Finished per-channel summaries and details threads")

async def run_bot_job():
    """The main logic of the bot, now encapsulated in a single function that runs once."""
    if not BOT_TOKEN:
        print("⚠️  Cannot start bot: DISCORD_BOT_TOKEN is not configured.")
        return
        
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True 
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user} to perform job.")
        try:
            await process_feeds_once(client)
            print("Job complete. Logging out.")
        finally:
            # Cleanup temporary directories
            import shutil
            for temp_dir in TEMP_DIRS_TO_CLEANUP:
                try:
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                        print(f"🧹 Cleaned up temp directory: {temp_dir}")
                except Exception as e:
                    print(f"⚠️ Failed to cleanup {temp_dir}: {e}")
            TEMP_DIRS_TO_CLEANUP.clear()
            
            await client.close()
            print("🔌 Discord client closed after job.")
            # Close shared HTTP session
            if HTTP_SESSION and not HTTP_SESSION.closed:
                await HTTP_SESSION.close()

    await client.start(BOT_TOKEN)

# === END FILE ===
