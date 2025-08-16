# === FILE: bot/dispatcher.py ===

import os
import re
import io
import asyncio
import requests
import time
import discord
from discord.ext import commands
import tempfile
import random
import pendulum
from bot.avatar_cache import avatar_for
from bot.facebook_downloader import (
    check_special_posts, 
    download_video_ytdlp, 
    mark_special_post_seen,
    extract_facebook_post_url
)
from bot.gemini_client import call_gemini
from bot.formatter import build_prompt, split_reply
import redis
import json
from typing import Any, Optional

# --- Disable Redis reactions to avoid connection errors ---
class DummyRedisClient:
    def rpush(self, *args, **kwargs):
        pass
redis_client = DummyRedisClient()

# --- Webhook and Bot Client Setup ---
WH_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
FACEBOOK_REACTIONS = ["👍", "❤️", "😆", "😲", "😢", "😡"]
DISCORD_LIMIT = 8 * 1024 * 1024  # 8MB Discord file limit
CATBOX_LIMIT = 200 * 1024 * 1024  # 200MB Catbox limit

# Webhook cache for channels
WEBHOOK_CACHE = {}

def _chunker(seq, size):
    """Yield successive n-sized chunks from a sequence."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]

def _split_message(content, limit=2000):
    """Split a message into chunks of at most 'limit' characters."""
    if len(content) <= limit: 
        return [content]
    
    parts = content.split('\n')
    chunks, current_chunk = [], ""
    
    for part in parts:
        if not part.strip(): 
            continue
        if current_chunk and len(current_chunk) + len(part) + 1 > limit:
            chunks.append(current_chunk)
            current_chunk = ""
        current_chunk = f"{current_chunk}\n{part}" if current_chunk else part
    
    if current_chunk: 
        chunks.append(current_chunk)
    
    return chunks

# Helper to get or create a webhook in a TextChannel
async def get_or_create_webhook_url(channel: Any) -> str:
    """Get or create a webhook URL for the given channel with caching."""
    # Check cache first
    if hasattr(channel, 'id') and channel.id in WEBHOOK_CACHE:
        return WEBHOOK_CACHE[channel.id]
    
    try:
        existing = await channel.webhooks()  # type: ignore
        for hook in existing:
            if hook.name == 'hanu-feedbot':
                url = f"https://discord.com/api/webhooks/{hook.id}/{hook.token}"
                # Cache the result
                if hasattr(channel, 'id'):
                    WEBHOOK_CACHE[channel.id] = url
                return url
        
        new_hook = await channel.create_webhook(name='hanu-feedbot')  # type: ignore
        url = f"https://discord.com/api/webhooks/{new_hook.id}/{new_hook.token}"
        # Cache the result
        if hasattr(channel, 'id'):
            WEBHOOK_CACHE[channel.id] = url
        return url
    except Exception as e:
        print(f"[WARNING] Failed to get/create webhook for channel: {e}")
        # Fallback to global webhook
        return WH_URL or ""

async def push(client: discord.Client, target: discord.TextChannel | discord.ForumChannel | discord.Thread, entry: dict, body: str, tldr: str, post_time: str):
    """
    Posts content via webhook to a text or forum channel (or existing thread via Thread), creating threads as needed,
    and queues reactions via Redis.
    """
    # Debug output
    print(f"\n{'='*40}")
    print(f"? PROCESSING ENTRY: {entry.get('title', 'No title')}")
    print(f"? Link: {entry.get('link', 'No link')}")
    print(f"? Date: {post_time}")
    print(f"? Entry ID: {entry.get('id', 'No ID')}")
    print(f"{'='*40}\n")

    # Determine webhook channel, forum flag, and initial thread_id
    if isinstance(target, discord.Thread):
        # existing thread (forum or text-thread)
        thread_id = target.id
        channel_for_webhook = target.parent
        is_forum_initial = False
    elif isinstance(target, discord.ForumChannel):
        # Forum channel: will create threads on first send
        thread_id = None
        channel_for_webhook = target
        is_forum_initial = True
    elif isinstance(target, discord.TextChannel):
        # Plain text channel: no threads
        thread_id = None
        channel_for_webhook = target
        is_forum_initial = False
    else:
        thread_id = None
        channel_for_webhook = None
        is_forum_initial = False

    # Resolve webhook URL
    if channel_for_webhook is not None:
        webhook_url = await get_or_create_webhook_url(channel_for_webhook)
    else:
        webhook_url = WH_URL

    # Initialize webhook client
    webhook = discord.Webhook.from_url(webhook_url, client=client)
    username = entry["page_name"].strip()
    avatar = avatar_for(entry)
    files_to_upload, catbox_video_links = [], []

    # --- Media Processing Logic ---
    # First check for our known target post ID anywhere in the entry
    if str(entry).find("743124275142078") >= 0 or str(entry).find("4010190512624581") >= 0:
        print(f"??? FOUND TARGET POST ID in entry text!")
        facebook_url = "https://www.facebook.com/720895507364955/posts/743124275142078"
    else:
        # Try to find any Facebook video URL in the entry
        facebook_url = extract_facebook_post_url(entry)

    # Try to download video if URL found
    video_processed = False
    if facebook_url:
        print(f"? Found Facebook URL: {facebook_url}")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_filename = os.path.join(temp_dir, f"facebook_video_{random.randint(1000, 9999)}.mp4")
                video_path = await download_video_ytdlp(facebook_url, output_path=temp_filename)
                
                if video_path and os.path.exists(video_path):
                    file_size = os.path.getsize(video_path)
                    print(f"[OK] Video downloaded successfully: {file_size/1024/1024:.2f}MB")
                    
                    if file_size < DISCORD_LIMIT:
                        files_to_upload.append(discord.File(video_path, filename="facebook_video.mp4"))
                        video_processed = True
                    else:
                        print(f"[WARNING] Video too large for Discord ({file_size/1024/1024:.2f}MB)")
                        # Handle large files with Catbox
                        try:
                            with open(video_path, 'rb') as f:
                                video_data = f.read()
                            catbox_url = await upload_to_catbox_async(video_data)
                            if catbox_url:
                                catbox_video_links.append(catbox_url)
                                video_processed = True
                            else:
                                print("[ERROR] Failed to upload large video to Catbox")
                        except Exception as e:
                            print(f"[ERROR] Error uploading to Catbox: {e}")
                else:
                    print("[WARNING] No video found in post or download failed")
        except Exception as e:
            print(f"[ERROR] Error processing Facebook video: {e}")
            import traceback
            traceback.print_exc()

    # Only process images if no video was found
    if not video_processed:
        for url in entry.get("media_all", []):
            # Skip Facebook video URLs that we couldn't download
            if "facebook.com/" in url and ("/videos/" in url or "/watch/" in url or "/reel/" in url):
                continue
                
            # Skip URLs that are clearly Facebook CDN images
            if "fbcdn.net" in url or "scontent-" in url:
                print(f"   ?? Processing image: {url}")
                try:
                    # Allow longer timeout for large media
                    resp = requests.get(url, timeout=60, headers={'User-Agent': 'DiscordBot/1.0'})
                    resp.raise_for_status()
                    data = resp.content
                    
                    if len(data) > DISCORD_LIMIT: 
                        print(f"   Skipping image, too large: {url}")
                        continue
                        
                    filename = url.split('/')[-1].split('?')[0] or f"media_{len(files_to_upload)}.jpg"
                    files_to_upload.append(discord.File(io.BytesIO(data), filename=filename))
                except requests.RequestException as e: 
                    print(f"   Failed to download image from {url}: {e}")

    # --- Sending Logic & Forum Thread Creation ---
    print("   Posting content via webhook...")
    last_media_msg_id = None
    last_content_msg_id = None
    posted_message = None

    # Prepare page description (channel info)
    page_description = "\n".join([f"-# {l.strip()}" for l in entry.get("about", "").split("\n") if l.strip()])
    
    # Forum initial post: generate AI title and post body, then description
    if isinstance(target, discord.ForumChannel) and thread_id is None:
        # Generate AI thread title
        try:
            import asyncio
            from bot.formatter import build_thread_title_prompt
            title_prompt = build_thread_title_prompt(entry.get('raw', ''))
            gen_reply = await asyncio.to_thread(call_gemini, title_prompt)
            thread_title = gen_reply.strip().splitlines()[0][:100] or username[:50]
        except Exception:
            date_only = post_time.split('T')[0]
            thread_title = f"{username[:50]}-{date_only}"
            
        # Create thread with first media or body if no media
        if catbox_video_links:
            content_first = catbox_video_links[0]
            send_kwargs = {"content": content_first, "username": username, "avatar_url": avatar, "thread_name": thread_title, "wait": True}
        elif files_to_upload:
            first_files = [files_to_upload.pop(0)]
            send_kwargs = {"files": first_files, "username": username, "avatar_url": avatar, "thread_name": thread_title, "wait": True}
        else:
            send_kwargs = {"content": body, "username": username, "avatar_url": avatar, "thread_name": thread_title, "wait": True}
            
        msg = await webhook.send(**send_kwargs)
        posted_message = msg
        thread_id = msg.channel.id
        
        # Post description if exists
        if page_description:
            await webhook.send(content=page_description, username=username, avatar_url=avatar, thread=discord.Object(id=thread_id), wait=False)
            
        # Post remaining media
        for link in catbox_video_links[1:]:
            await webhook.send(content=link, username=username, avatar_url=avatar, thread=discord.Object(id=thread_id), wait=True)
            
        # Post remaining files
        for chunk_files in _chunker(files_to_upload, 10):
            await webhook.send(files=chunk_files, username=username, avatar_url=avatar, thread=discord.Object(id=thread_id), wait=True)
            
        # If first send was media/files, now post body
        if catbox_video_links or files_to_upload:
            for chunk in _split_message(body):
                await webhook.send(content=chunk, username=username, avatar_url=avatar, thread=discord.Object(id=thread_id), wait=False)
                
        # Finally, send the tl;dr
        if tldr:
            await webhook.send(content=tldr, username=username, avatar_url=avatar, thread=discord.Object(id=thread_id), wait=False)
            
        return posted_message
        
    # Existing threads or text channels
    # Text channels: send body only
    # Text channels or new threads: send body in chunks to respect 2000-char limit
    if isinstance(target, discord.TextChannel) or (isinstance(target, discord.Thread) and thread_id is None):
        last_msg = None
        for chunk in _split_message(body):
            send_kwargs = {"content": chunk, "username": username, "avatar_url": avatar, "wait": False}
            last_msg = await webhook.send(**send_kwargs)
            
        # For a new thread via Thread object, set thread_id
        if isinstance(target, discord.Thread) and thread_id is None:
            thread_id = target.id
            
        posted_message = last_msg
        
    elif isinstance(target, discord.Thread):
        # Existing thread: send into it in chunks
        assert thread_id is not None, "Thread ID is required for existing thread"
        tid: int = thread_id  # type: ignore
        last_msg = None
        
        for chunk in _split_message(body):
            send_kwargs = {"content": chunk, "username": username, "avatar_url": avatar, "thread": discord.Object(id=tid), "wait": False}
            last_msg = await webhook.send(**send_kwargs)
            
        posted_message = last_msg

    if catbox_video_links:
        # Prepare to send first media; for forums, create thread if not yet created
        send_kwargs = {"content": catbox_video_links[0], "username": username, "avatar_url": avatar, "wait": True}
        
        if isinstance(target, discord.ForumChannel) and thread_id is None:
            date_only = post_time.split('T')[0]
            send_kwargs["thread_name"] = f"{username[:50]}-{date_only}"
        elif thread_id is not None:
            send_kwargs["thread"] = discord.Object(id=int(thread_id))
            
        msg = await webhook.send(**send_kwargs)
        last_media_msg_id = msg.id
        posted_message = msg
        
        # Queue reaction job
        job = {"channel_id": thread_id if thread_id else target.id, "message_id": msg.id, "reactions": FACEBOOK_REACTIONS}
        redis_client.rpush("reaction_queue", json.dumps(job))
        
    if files_to_upload:
        for chunk_files in _chunker(files_to_upload, 10):
            send_kwargs = {"files": chunk_files, "username": username, "avatar_url": avatar, "wait": True}
            
            if isinstance(target, discord.ForumChannel) and thread_id is None:
                date_only = post_time.split('T')[0]
                send_kwargs["thread_name"] = f"{username[:50]}-{date_only}"
            elif thread_id is not None:
                send_kwargs["thread"] = discord.Object(id=int(thread_id))
                
            msg = await webhook.send(**send_kwargs)
            last_media_msg_id = msg.id
            posted_message = msg
            
            job = {"channel_id": thread_id if thread_id else target.id, "message_id": msg.id, "reactions": FACEBOOK_REACTIONS}
            redis_client.rpush("reaction_queue", json.dumps(job))

    if body.strip():
        for chunk in _split_message(body):
            send_kwargs = {"content": chunk, "username": username, "avatar_url": avatar, "wait": True}
            
            if isinstance(target, discord.ForumChannel) and thread_id is None:
                date_only = post_time.split('T')[0]
                send_kwargs["thread_name"] = f"{username[:50]}-{date_only}"
            elif thread_id is not None:
                send_kwargs["thread"] = discord.Object(id=int(thread_id))
                
            msg = await webhook.send(**send_kwargs)
            last_content_msg_id = msg.id
            posted_message = msg
            
            job = {"channel_id": thread_id if thread_id else target.id, "message_id": msg.id, "reactions": FACEBOOK_REACTIONS}
            redis_client.rpush("reaction_queue", json.dumps(job))
    
    if tldr.strip():
        send_kwargs = {"content": tldr, "username": username, "avatar_url": avatar, "wait": False}
        
        if thread_id is not None:
            send_kwargs["thread"] = discord.Object(id=int(thread_id))
            
        await webhook.send(**send_kwargs)

    # Prioritize the last media message as the anchor. Fall back to the last content message.
    final_anchor_id = last_media_msg_id or last_content_msg_id

    # Return the last sent message for jump_url and reactions
    return posted_message

async def get_daily_summary_message(channel, today_str):
    """Finds the summary message for the current day."""
    async for message in channel.history(limit=50):
        if message.author.bot and message.content.startswith(f"#") and today_str in message.content:
            return message
    return None

async def create_daily_summary_message(channel, vietnamese_date):
    """Creates the initial summary message for the day using a file as source of truth."""
    # Create daily summary header and file
    # Use local Vietnam timezone to match displayed Vietnamese date
    today_str = pendulum.now('Asia/Ho_Chi_Minh').to_date_string()
    
    # Format header with credit line
    header_line = f"{vietnamese_date} ({today_str})"
    credit_line = "-# *[hanu-news bot](https://hanu-feedbot-production.up.railway.app/) - made with <3 by namesn_pe*"
    content = f"{header_line}\n{credit_line}"
    
    try:
        message = await channel.send(content)
        
        # Add reactions only to the date message
        for reaction in ["👍", "❤️", "😂", "😮", "😢", "😡"]:
            await message.add_reaction(reaction)
            
        # Initialize summary file with header and credit
        file_path = f"daily_summary_{today_str}.txt"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return message
    except discord.Forbidden:
        print(f"[CRITICAL] Lacking permissions to send messages or add reactions in channel {channel.id}.")
        return None

async def update_daily_summary_message(summary_message, entry, posted_message):
    """Appends a new post's summary to the daily summary message."""
    # Build and append a numbered summary line to file
    header = summary_message.content.splitlines()[0]
    m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", header)
    today_str = m.group(1) if m else pendulum.now('UTC').to_date_string()
    file_path = f"daily_summary_{today_str}.txt"
    
    # Generate one-sentence summary via Gemini
    prompt = f"Summarize the following post in exactly one sentence, using the same language and tone as the post:\n\n{entry.get('raw', '')}"
    summary_text = call_gemini([{"type": "text", "text": prompt}]) or "Không thể tạo tóm tắt."
    
    # Determine new entry number based on existing file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []
        
    new_num = sum(1 for ln in lines if re.match(r'^\d+\.', ln)) + 1
    
    # Build summary lines: numbered header, author/link line, and thread link
    author = entry.get('page_name', 'Facebook Post')
    post_url = entry.get('link', '#')
    # Create a formatted Discord message link
    if posted_message:
        guild_id = posted_message.guild.id if hasattr(posted_message, 'guild') and posted_message.guild else "@me"
        channel_id = posted_message.channel.id if hasattr(posted_message, 'channel') else "unknown"
        message_id = posted_message.id if hasattr(posted_message, 'id') else "unknown"
        thread_url = f"[Details](https://discord.com/channels/{guild_id}/{channel_id}/{message_id})"
    else:
        thread_url = "[Details](#)"
    summary_header = f"## {new_num}. {summary_text.strip()}"
    summary_link = f"-# {thread_url} - <{post_url}>"

        
    # Record full summary line and its media URLs to file for count tracking
    media_urls = entry.get('media_all', []) or []
    media_part = ''
    
    if media_urls:
        # include up to 3 media links in summary file
        media_links = [f'<{u}>' for u in media_urls]
        media_part = ' ' + ' '.join(media_links)
        
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"\n{new_num}. {summary_text.strip()} - {author} - <{post_url}>{media_part}")
        
    # Send summary lines as separate message(s)
    content = f"{summary_header}\n{summary_link}"
    for chunk in _split_message(content, limit=2000):
        await summary_message.channel.send(chunk)

def upload_to_catbox(video_data: bytes) -> str | None:
    """Uploads video data to Catbox.moe with retry logic on failures."""
    max_retries = 3
    backoff_factor = 5
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"   ?? Uploading to Catbox.moe... (attempt {attempt}/{max_retries})")
            r = requests.post(
                'https://catbox.moe/user/api.php',
                files={'fileToUpload': ('video.mp4', video_data)},
                data={'reqtype': 'fileupload', 'userhash': ''},
                timeout=90
            )
            r.raise_for_status()
            
            if r.text.startswith("https://"):
                return r.text
            else:
                print(f"   [ERROR] Catbox API returned an error: {r.text}")
                return None
        except requests.RequestException as e:
            print(f"   [ERROR] Catbox upload failed (attempt {attempt}/{max_retries}): {e}")
            
            if attempt < max_retries:
                wait = backoff_factor * (2 ** (attempt - 1))
                print(f"   ? Retrying in {wait} seconds...")
                time.sleep(wait)
            else:
                print("   [ERROR] All Catbox upload attempts failed.")
                return None

# Async wrapper to keep event loop responsive
async def upload_to_catbox_async(video_data: bytes) -> str | None:
    """Async wrapper to run blocking Catbox upload in a thread."""
    return await asyncio.to_thread(upload_to_catbox, video_data)

async def process_special_posts(client, config):
    """Process any special posts that need to be posted regardless of feed state"""
    special_posts = check_special_posts()
    
    if not special_posts:
        return
        
    print(f"? Found {len(special_posts)} special posts to process")
    
    for post in special_posts:
        print(f"? Processing special post: {post['title']}")
        
        try:
            # Find target channel
            channel_id = config.get("channel_id")
            channel = client.get_channel(channel_id)
            
            if not channel:
                print(f"[ERROR] Channel {channel_id} not found")
                continue
                
            # Download the video
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_filename = os.path.join(temp_dir, f"facebook_video_{random.randint(1000, 9999)}.mp4")
                video_path = await download_video_ytdlp(post["url"], output_path=temp_filename)
                
                if not video_path or not os.path.exists(video_path):
                    print(f"[ERROR] Failed to download video for special post")
                    continue
                    
                file_size = os.path.getsize(video_path)
                print(f"[OK] Special post video downloaded: {file_size/1024/1024:.2f}MB")
                
                # Create message with video attachment
                if file_size < DISCORD_LIMIT:
                    message = await channel.send(
                        f"🌟 **{post['title']}**\n{post['url']}", 
                        file=discord.File(video_path, filename="facebook_video.mp4")
                    )
                    print(f"[OK] Special post sent to Discord")
                else:
                    # For large videos, upload to Catbox
                    with open(video_path, 'rb') as f:
                        video_data = f.read()
                    catbox_url = await upload_to_catbox_async(video_data)
                    
                    if catbox_url:
                        message = await channel.send(f"🌟 **{post['title']}**\n{post['url']}\n{catbox_url}")
                        print(f"[OK] Special post sent to Discord via Catbox")
                    else:
                        print(f"[ERROR] Failed to upload large video to Catbox")
                        continue
                
                # Mark as processed
                mark_special_post_seen(post["id"])
                
                # Add reactions
                for reaction in FACEBOOK_REACTIONS:
                    try:
                        await message.add_reaction(reaction)
                    except Exception:
                        pass
                        
        except Exception as e:
            print(f"[ERROR] Error processing special post: {e}")
            import traceback
            traceback.print_exc()

# === END FILE ===