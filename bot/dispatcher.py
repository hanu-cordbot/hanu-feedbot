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
from bot.r2_video import (
    upload_video_to_r2_async,
    create_video_embed_message,
    should_use_r2_storage,
    get_video_size_limit,
    R2_VIDEO_BUCKET
)
from bot.config import r2_client
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
DISCORD_LIMIT = get_video_size_limit()  # Use centralized limit from r2_video
CATBOX_LIMIT = 200 * 1024 * 1024  # 200MB Catbox limit

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
    """Get or create a webhook URL for the given channel."""
    print(f"🔍 Checking webhooks in channel: {channel.name}")
    existing = await channel.webhooks()  # type: ignore
    print(f"📋 Found {len(existing)} webhooks in channel")
    
    for hook in existing:
        print(f"🔎 Webhook: {hook.name} (ID: {hook.id})")
        if hook.name == 'hanu-feedbot':
            # Delete existing webhook to ensure clean recreation
            try:
                await hook.delete()
                print(f"🗑️ Successfully deleted existing webhook for clean recreation")
            except Exception as e:
                print(f"⚠️ Could not delete existing webhook: {e}")
                # Try to use the existing webhook anyway
                return f"https://discord.com/api/webhooks/{hook.id}/{hook.token}"
            break
    
    # Create fresh webhook with explicit defaults that can be overridden
    try:
        print(f"🏗️ Creating new webhook in channel: {channel.name}")
        # Create webhook with explicit defaults that match our desired behavior
        new_hook = await channel.create_webhook(
            name='hanu-feedbot',
            avatar=None  # Explicitly set to None so send() can override
        )
        print(f"✅ Successfully created webhook: {new_hook.name} (ID: {new_hook.id})")
        return f"https://discord.com/api/webhooks/{new_hook.id}/{new_hook.token}"
    except discord.Forbidden as e:
        print(f"❌ Insufficient permissions to create webhook in {channel.name}: {e}")
        # Try to use existing webhook if creation fails
        for hook in existing:
            if hook.name == 'hanu-feedbot':
                print(f"⚠️ Using existing webhook due to permission issues")
                return f"https://discord.com/api/webhooks/{hook.id}/{hook.token}"
        raise
    except Exception as e:
        print(f"❌ Failed to create webhook: {e}")
        raise

async def push(client: discord.Client, target: discord.TextChannel | discord.ForumChannel | discord.Thread, entry: dict, body: str, tldr: str, post_time: str):
    """
    Posts content via webhook to a text or forum channel (or existing thread via Thread), creating threads as needed,
    and queues reactions via Redis.
    """
    # Debug output
    print(f"\n{'='*40}")
    print(f"🔍 PROCESSING ENTRY: {entry.get('title', 'No title')}")
    print(f"🔗 Link: {entry.get('link', 'No link')}")
    print(f"📅 Date: {post_time}")
    print(f"🔢 Entry ID: {entry.get('id', 'No ID')}")
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
        try:
            webhook_url = await get_or_create_webhook_url(channel_for_webhook)
            print(f"🔗 Successfully got webhook URL for {channel_for_webhook.name}")
        except Exception as e:
            print(f"❌ Failed to get webhook URL for {channel_for_webhook.name}: {e}")
            # Don't fall back to WH_URL as it might have default settings
            raise
    else:
        webhook_url = WH_URL
        print(f"⚠️ Using fallback webhook URL")

    # Initialize webhook client
    try:
        webhook = discord.Webhook.from_url(webhook_url, client=client)
        print(f"🤖 Initialized webhook client successfully")
        
        # Test the webhook with a simple message to verify it works
        test_kwargs = {"content": "🧪 Webhook test", "username": "Test User", "wait": True}
        try:
            test_msg = await webhook.send(**test_kwargs)
            print(f"✅ Webhook test successful - message ID: {test_msg.id}")
            # Delete the test message
            await test_msg.delete()
            print(f"🗑️ Test message deleted")
        except Exception as e:
            print(f"⚠️ Webhook test failed: {e}")
            
    except Exception as e:
        print(f"❌ Failed to initialize webhook client: {e}")
        raise
        
    username = entry["page_name"].strip()
    avatar = avatar_for(entry)
    
    # Validate parameters
    if not username or len(username) < 2:
        username = "Facebook Page"
    if not avatar or not avatar.startswith('http'):
        avatar = None
    
    print(f"👤 Final username: '{username}'")
    print(f"🖼️ Final avatar: {avatar[:50] if avatar else 'None'}")
    
    files_to_upload, video_links = [], []  # Renamed for clarity: includes both R2 and Catbox links

    # --- Media Processing Logic ---
    # First check for our known target post ID anywhere in the entry
    if str(entry).find("743124275142078") >= 0 or str(entry).find("4010190512624581") >= 0:
        print(f"❗❗❗ FOUND TARGET POST ID in entry text!")
        facebook_url = "https://www.facebook.com/720895507364955/posts/743124275142078"
    else:
        # Try to find any Facebook video URL in the entry
        facebook_url = extract_facebook_post_url(entry)

    # Try to download video if URL found
    video_processed = False
    if facebook_url:
        print(f"📹 Found Facebook URL: {facebook_url}")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_filename = os.path.join(temp_dir, f"facebook_video_{random.randint(1000, 9999)}.mp4")
                video_path = await download_video_ytdlp(facebook_url, output_path=temp_filename)
                
                if video_path and os.path.exists(video_path):
                    file_size = os.path.getsize(video_path)
                    print(f"✅ Video downloaded successfully: {file_size/1024/1024:.2f}MB")
                    
                    if file_size < DISCORD_LIMIT:
                        files_to_upload.append(discord.File(video_path, filename="facebook_video.mp4"))
                        video_processed = True
                    elif should_use_r2_storage(file_size):
                        print(f"📤 Video too large for Discord, uploading to R2...")
                        # Upload to R2 instead of Catbox for better reliability
                        try:
                            with open(video_path, 'rb') as f:
                                video_data = f.read()
                            
                            post_title = entry.get('title', entry.get('page_name', 'Facebook Video'))
                            r2_url = await upload_video_to_r2_async(video_data, post_title, r2_client, R2_VIDEO_BUCKET)
                            
                            if r2_url:
                                # Create embed message for R2 video (no original post link)
                                video_message = create_video_embed_message(r2_url, post_title)
                                video_links.append(video_message)
                                video_processed = True
                            else:
                                # Fallback to Catbox if R2 fails
                                print("⚠️ R2 upload failed, falling back to Catbox...")
                                catbox_url = await upload_to_catbox_async(video_data)
                                if catbox_url:
                                    video_links.append(catbox_url)
                                    video_processed = True
                                else:
                                    print("❌ Both R2 and Catbox upload failed")
                        except Exception as e:
                            print(f"❌ Error uploading large video: {e}")
                    else:
                        print(f"⚠️ Video too large even for external storage")
                else:
                    print("⚠️ No video found in post or download failed")
        except Exception as e:
            print(f"❌ Error processing Facebook video: {e}")
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
                print(f"   🖼️ Processing image: {url}")
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
        if video_links:
            content_first = video_links[0]
            send_kwargs = {"content": content_first, "username": username, "thread_name": thread_title, "wait": True}
            if avatar:
                send_kwargs["avatar_url"] = avatar
        elif files_to_upload:
            first_files = [files_to_upload.pop(0)]
            send_kwargs = {"files": first_files, "username": username, "thread_name": thread_title, "wait": True}
            if avatar:
                send_kwargs["avatar_url"] = avatar
        else:
            send_kwargs = {"content": body, "username": username, "thread_name": thread_title, "wait": True}
            if avatar:
                send_kwargs["avatar_url"] = avatar
            
        msg = await webhook.send(**send_kwargs)
        posted_message = msg
        thread_id = msg.channel.id
        
        # Post description if exists
        if page_description:
            desc_kwargs = {"content": page_description, "username": username, "thread": discord.Object(id=thread_id), "wait": False}
            if avatar:
                desc_kwargs["avatar_url"] = avatar
            await webhook.send(**desc_kwargs)
            
        # Post remaining media
        for link in video_links[1:]:
            media_kwargs = {"content": link, "username": username, "thread": discord.Object(id=thread_id), "wait": True}
            if avatar:
                media_kwargs["avatar_url"] = avatar
            await webhook.send(**media_kwargs)
            
        # Post remaining files
        for chunk_files in _chunker(files_to_upload, 10):
            file_kwargs = {"files": chunk_files, "username": username, "thread": discord.Object(id=thread_id), "wait": True}
            if avatar:
                file_kwargs["avatar_url"] = avatar
            await webhook.send(**file_kwargs)
            
        # If first send was media/files, now post body
        if video_links or files_to_upload:
            for chunk in _split_message(body):
                body_kwargs = {"content": chunk, "username": username, "thread": discord.Object(id=thread_id), "wait": False}
                if avatar:
                    body_kwargs["avatar_url"] = avatar
                await webhook.send(**body_kwargs)
                
        # Finally, send the tl;dr
        if tldr:
            tldr_kwargs = {"content": tldr, "username": username, "thread": discord.Object(id=thread_id), "wait": False}
            if avatar:
                tldr_kwargs["avatar_url"] = avatar
            await webhook.send(**tldr_kwargs)
            
        return posted_message
        
    # Handle existing threads or text channels
    if isinstance(target, discord.TextChannel):
        # Plain text channel: send everything directly
        pass  # Continue to unified sending logic below
    elif isinstance(target, discord.Thread):
        # Existing thread: ensure thread_id is set
        if thread_id is None:
            thread_id = target.id

    # Unified sending logic for text channels and existing threads
    # Send video links first
    if video_links:
        for i, video_link in enumerate(video_links):
            send_kwargs = {"content": video_link, "username": username, "wait": True}
            if avatar:
                send_kwargs["avatar_url"] = avatar
            
            if thread_id is not None:
                send_kwargs["thread"] = discord.Object(id=int(thread_id))
                
            print(f"📤 Sending video link with params: username='{username}', avatar_url={avatar[:50] if avatar else 'None'}...")
            try:
                msg = await webhook.send(**send_kwargs)
                print(f"✅ Video link sent successfully")
                last_media_msg_id = msg.id
                posted_message = msg
            except Exception as e:
                print(f"❌ Failed to send video link: {e}")
                continue
            
            # Queue reaction job
            job = {"channel_id": thread_id if thread_id else target.id, "message_id": msg.id, "reactions": FACEBOOK_REACTIONS}
            redis_client.rpush("reaction_queue", json.dumps(job))
        
    # Send file attachments
    if files_to_upload:
        for chunk_files in _chunker(files_to_upload, 10):
            send_kwargs = {"files": chunk_files, "username": username, "wait": True}
            if avatar:
                send_kwargs["avatar_url"] = avatar
            
            if thread_id is not None:
                send_kwargs["thread"] = discord.Object(id=int(thread_id))
                
            msg = await webhook.send(**send_kwargs)
            last_media_msg_id = msg.id
            posted_message = msg
            
            # Queue reaction job
            job = {"channel_id": thread_id if thread_id else target.id, "message_id": msg.id, "reactions": FACEBOOK_REACTIONS}
            redis_client.rpush("reaction_queue", json.dumps(job))

    # Send body text
    if body.strip():
        for chunk in _split_message(body):
            send_kwargs = {"content": chunk, "username": username, "wait": True}
            if avatar:
                send_kwargs["avatar_url"] = avatar
            
            if thread_id is not None:
                send_kwargs["thread"] = discord.Object(id=int(thread_id))
                
            msg = await webhook.send(**send_kwargs)
            last_content_msg_id = msg.id
            posted_message = msg
            
            job = {"channel_id": thread_id if thread_id else target.id, "message_id": msg.id, "reactions": FACEBOOK_REACTIONS}
            redis_client.rpush("reaction_queue", json.dumps(job))
            posted_message = msg
            
            job = {"channel_id": thread_id if thread_id else target.id, "message_id": msg.id, "reactions": FACEBOOK_REACTIONS}
            redis_client.rpush("reaction_queue", json.dumps(job))
    
    if tldr.strip():
        send_kwargs = {"content": tldr, "username": username, "wait": False}
        if avatar:
            send_kwargs["avatar_url"] = avatar
        
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
        if message.author.bot and today_str in message.content and "hanu-news bot" in message.content:
            return message
    return None

async def create_daily_summary_message(channel, vietnamese_date):
    """Creates the initial summary message for the day using bot identity."""
    # Create daily summary header and file
    # Use local Vietnam timezone to match displayed Vietnamese date
    today_str = pendulum.now('Asia/Ho_Chi_Minh').to_date_string()
    
    # Format header with credit line
    header_line = f"{vietnamese_date} ({today_str})"
    credit_line = "-# *[hanu-news bot](https://hanu-cordbot.github.io/hanu-feedbot) - made with <3 by namesn_pe*"
    content = f"{header_line}\n{credit_line}"
    
    try:
        # Always use bot identity for daily summary message
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
        print(f"🚨 Lacking permissions to send messages or add reactions in channel {channel.id}.")
        return None
    except Exception as e:
        print(f"❌ Error creating daily summary message: {e}")
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
        
    # Send summary lines as separate message(s) using webhook with Facebook identity
    content = f"{summary_header}\n{summary_link}"
    
    # Use webhook to impersonate Facebook page identity
    try:
        webhook_url = await get_or_create_webhook_url(summary_message.channel)
        webhook = discord.Webhook.from_url(webhook_url, client=None)
        
        username = entry.get("page_name", "").strip() or "Facebook Page"
        avatar = avatar_for(entry)
        
        # Prepare media attachment for the header message
        files_to_attach = []
        if media_urls:
            # Download first media item for attachment
            first_media_url = media_urls[0]
            try:
                print(f"📥 Downloading media for summary: {first_media_url}")
                resp = requests.get(first_media_url, timeout=30, headers={'User-Agent': 'DiscordBot/1.0'})
                resp.raise_for_status()
                data = resp.content
                
                if len(data) < DISCORD_LIMIT:
                    # Determine filename from URL
                    filename = first_media_url.split('/')[-1].split('?')[0] or "media.jpg"
                    if not filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mov', '.webm')):
                        filename += ".jpg"
                    
                    files_to_attach.append(discord.File(io.BytesIO(data), filename=filename))
                    print(f"✅ Media downloaded for summary: {len(data)/1024:.1f}KB")
                else:
                    print(f"⚠️ Media too large for summary attachment: {len(data)/1024/1024:.1f}MB")
            except Exception as e:
                print(f"⚠️ Failed to download media for summary: {e}")
        
        # Send header with media attached
        header_kwargs = {"content": summary_header, "username": username, "wait": True}
        if avatar:
            header_kwargs["avatar_url"] = avatar
        if files_to_attach:
            header_kwargs["files"] = files_to_attach
        
        await webhook.send(**header_kwargs)
        print(f"✅ Sent summary header with media")
        
        # Send detail link separately
        link_kwargs = {"content": summary_link, "username": username, "wait": True}
        if avatar:
            link_kwargs["avatar_url"] = avatar
        
        await webhook.send(**link_kwargs)
        print(f"✅ Sent summary detail link")
            
    except Exception as e:
        print(f"❌ Failed to send summary via webhook: {e}")
        # Fallback to regular channel send
        try:
            # Send header first
            await summary_message.channel.send(summary_header)
            # Send detail link
            await summary_message.channel.send(summary_link)
        except Exception as e2:
            print(f"❌ Fallback also failed: {e2}")

def upload_to_catbox(video_data: bytes) -> str | None:
    """Uploads video data to Catbox.moe with retry logic on failures."""
    max_retries = 3
    backoff_factor = 5
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"   ⬆️ Uploading to Catbox.moe... (attempt {attempt}/{max_retries})")
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
                print(f"   ❌ Catbox API returned an error: {r.text}")
                return None
        except requests.RequestException as e:
            print(f"   ❌ Catbox upload failed (attempt {attempt}/{max_retries}): {e}")
            
            if attempt < max_retries:
                wait = backoff_factor * (2 ** (attempt - 1))
                print(f"   ⏳ Retrying in {wait} seconds...")
                time.sleep(wait)
            else:
                print("   ❌ All Catbox upload attempts failed.")
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
        
    print(f"🌟 Found {len(special_posts)} special posts to process")
    
    for post in special_posts:
        print(f"🌟 Processing special post: {post['title']}")
        
        try:
            # Find target channel
            channel_id = config.get("channel_id")
            channel = client.get_channel(channel_id)
            
            if not channel:
                print(f"❌ Channel {channel_id} not found")
                continue
                
            # Download the video
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_filename = os.path.join(temp_dir, f"facebook_video_{random.randint(1000, 9999)}.mp4")
                video_path = await download_video_ytdlp(post["url"], output_path=temp_filename)
                
                if not video_path or not os.path.exists(video_path):
                    print(f"❌ Failed to download video for special post")
                    continue
                    
                file_size = os.path.getsize(video_path)
                print(f"✅ Special post video downloaded: {file_size/1024/1024:.2f}MB")
                
                # Create message with video attachment
                message = None
                if file_size < DISCORD_LIMIT:
                    message = await channel.send(
                        f"🌟 **{post['title']}**\n{post['url']}", 
                        file=discord.File(video_path, filename="facebook_video.mp4")
                    )
                    print(f"✅ Special post sent to Discord")
                elif should_use_r2_storage(file_size):
                    # For large videos, upload to R2 first, fallback to Catbox
                    with open(video_path, 'rb') as f:
                        video_data = f.read()
                    
                    r2_url = await upload_video_to_r2_async(video_data, post['title'], r2_client, R2_VIDEO_BUCKET)
                    
                    if r2_url:
                        video_message = create_video_embed_message(r2_url, post['title'])
                        message = await channel.send(f"🌟 {video_message}")
                        print(f"✅ Special post sent to Discord via R2")
                    else:
                        # Fallback to Catbox
                        catbox_url = await upload_to_catbox_async(video_data)
                        
                        if catbox_url:
                            message = await channel.send(f"🌟 **{post['title']}**\n{post['url']}\n{catbox_url}")
                            print(f"✅ Special post sent to Discord via Catbox")
                        else:
                            print(f"❌ Failed to upload large video to both R2 and Catbox")
                            continue
                
                if not message:
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
            print(f"❌ Error processing special post: {e}")
            import traceback
            traceback.print_exc()

# === END FILE ===