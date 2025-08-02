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
import pendulum
from bot.avatar_cache import avatar_for
from bot.facebook_downloader import download_video_ytdlp
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

def _chunker(seq, size):
    """Yield successive n-sized chunks from a sequence."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]

# Helper to get or create a webhook in a TextChannel
async def get_or_create_webhook_url(channel: Any) -> str:
    existing = await channel.webhooks()  # type: ignore
    for hook in existing:
        if hook.name == 'hanu-feedbot':
            return f"https://discord.com/api/webhooks/{hook.id}/{hook.token}"
    new_hook = await channel.create_webhook(name='hanu-feedbot')  # type: ignore
    return f"https://discord.com/api/webhooks/{new_hook.id}/{new_hook.token}"

async def push(client: discord.Client, target: discord.TextChannel | discord.ForumChannel | discord.Thread, entry: dict, body: str, tldr: str, post_time: str):
    """
    Posts content via webhook to a text or forum channel (or existing thread via Thread), creating threads as needed,
    and queues reactions via Redis.
    """
    # Determine webhook channel, forum flag, and initial thread_id
    # Determine context: forum channel, existing thread, or plain text channel
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
    DISCORD_LIMIT, CATBOX_LIMIT = 10 * 1024 * 1024, 200 * 1024 * 1024

    # --- Media Processing Logic ---
    video_processed = False
    with tempfile.TemporaryDirectory() as temp_dir:
        for url in entry.get("media_all", []):
            is_video = "facebook.com/" in url and ("/videos/" in url or "/watch/" in url or "/reel/" in url)
            if is_video:
                print(f"📹 Found Facebook video, processing: {url}")
                temp_filename = os.path.join(temp_dir, f"video_{os.urandom(8).hex()}.mp4")
                try:
                    if download_video_ytdlp(url, output_path=temp_filename) and os.path.exists(temp_filename):
                        with open(temp_filename, 'rb') as f: video_data = f.read()
                        size_mb = len(video_data) / (1024*1024); print(f"   Video downloaded. Size: {size_mb:.2f} MB")
                        if len(video_data) > CATBOX_LIMIT: print(f"   Skipping video, too large for Catbox.")
                        elif len(video_data) < DISCORD_LIMIT: files_to_upload.append(discord.File(io.BytesIO(video_data), filename="video.mp4"))
                        else:
                            catbox_link = await upload_to_catbox_async(video_data)
                            if catbox_link: catbox_video_links.append(catbox_link)
                except Exception as e: print(f"An error occurred while processing video {url}: {e}")
                video_processed = True; break
        if not video_processed:
            for url in entry.get("media_all", []):
                if "facebook.com/" in url and ("/videos/" in url or "/watch/" in url or "/reel/" in url): continue
                print(f"   🖼️ Found image, processing: {url}")
                try:
                    # allow longer timeout for large media
                    resp = requests.get(url, timeout=60, headers={'User-Agent': 'DiscordBot/1.0'}); resp.raise_for_status()
                    data = resp.content
                    if len(data) > DISCORD_LIMIT: print(f"   Skipping image, too large: {url}"); continue
                    filename = url.split('/')[-1].split('?')[0] or f"media_{len(files_to_upload)}.jpg"
                    files_to_upload.append(discord.File(io.BytesIO(data), filename=filename))
                except requests.RequestException as e: print(f"   Failed to download image from {url}: {e}")

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
        # queue reaction job
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

    # --- REVISED Interaction Logic ---
    # **FIX**: Prioritize the last media message as the anchor. Fall back to the last content message.
    final_anchor_id = last_media_msg_id or last_content_msg_id

    # Return the last sent message for jump_url and reactions
    return posted_message


def _split_message(content, limit=2000):
    if len(content) <= limit: return [content]
    parts = content.split('\n')
    chunks, current_chunk = [], ""
    for part in parts:
        if not part.strip(): continue
        if current_chunk and len(current_chunk) + len(part) + 1 > limit:
            chunks.append(current_chunk); current_chunk = ""
        current_chunk = f"{current_chunk}\n{part}" if current_chunk else part
    if current_chunk: chunks.append(current_chunk)
    return chunks

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
        print(f"🚨 Lacking permissions to send messages or add reactions in channel {channel.id}.")
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
    thread_url = getattr(posted_message, 'jump_url', None)
    summary_header = f"## {new_num}. {summary_text.strip()}"
    # Compose link line: Facebook post and Discord thread
    if thread_url:
        summary_link = f"-# {author} - <{post_url}> - {thread_url}"
    else:
        summary_link = f"-# {author} - <{post_url}>"
    # Record full summary line to file for count tracking
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"\n{new_num}. {summary_text.strip()} - {author} - <{post_url}>")
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

async def send_post_to_discord(
    page_description: str,
    tldr: str,
    username: str,
    avatar: str,
    files: list,
    catbox_video_links: list,
    thread_id: int | None = None,
):
    """Sends the post to Discord."""
    # The client is needed for the webhook to work.
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    webhook = discord.Webhook.from_url(WH_URL, client=client)

    # Use thread object for webhook sends
    thread_obj = discord.Object(id=thread_id) if thread_id else None
    msg = None

    # First, send the description if it exists.
    if page_description:
        # Send description into the thread or channel
        if thread_obj:
            # Send to thread
            await webhook.send(
                content=page_description,
                username=username,
                avatar_url=avatar,
                wait=False,
                thread=thread_obj,
            )
        else:
            await webhook.send(
                content=page_description,
                username=username,
                avatar_url=avatar,
                wait=False,
            )

    # Then, send the files or text chunks.
    if catbox_video_links:
        # Send first video link in the thread or channel
        if thread_obj:
            # Send to thread
            msg = await webhook.send(
                content=catbox_video_links[0],
                username=username,
                avatar_url=avatar,
                wait=True,
                thread=thread_obj,
            )
        else:
            msg = await webhook.send(
                content=catbox_video_links[0],
                username=username,
                avatar_url=avatar,
                wait=True,
            )
    elif files:
        # Send files in chunks of 10 in the thread or channel
        file_chunks = [files[i : i + 10] for i in range(0, len(files), 10)]
        for file_chunk in file_chunks:
            if thread_obj:
                # Send to thread
                msg = await webhook.send(
                    files=file_chunk,
                    username=username,
                    avatar_url=avatar,
                    wait=True,
                    thread=thread_obj,
                )
            else:
                msg = await webhook.send(
                    files=file_chunk,
                    username=username,
                    avatar_url=avatar,
                    wait=True,
                )
    else:
        # If there are no files, send the text in chunks in the thread or channel.
        chunks = _split_message(page_description)
        for chunk in chunks:
            if thread_obj:
                # Send to thread
                msg = await webhook.send(
                    content=chunk,
                    username=username,
                    avatar_url=avatar,
                    wait=True,
                    thread=thread_obj,
                )
            else:
                msg = await webhook.send(
                    content=chunk,
                    username=username,
                    avatar_url=avatar,
                    wait=True,
                )

    # Finally, send the TL;DR.
    if tldr:
        # Send tl;dr at the end
        if thread_obj:
            # Send to thread
            await webhook.send(
                content=tldr,
                username=username,
                avatar_url=avatar,
                wait=False,
                thread=thread_obj,
            )
        else:
            await webhook.send(
                content=tldr,
                username=username,
                avatar_url=avatar,
                wait=False,
            )

    # Reaction jobs are queued in push(), so skip here
    
    await client.close()

# === END FILE ===
