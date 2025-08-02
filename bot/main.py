import os
import json
import asyncio
import pendulum
import discord
import sys
from dotenv import load_dotenv
from collections import defaultdict

# Load all environment variables from the .env file for local development
load_dotenv()

# --- REVISED: Centralized Configuration and Validation ---
print("Initializing configuration...")
try:
    # Validate and load all required environment variables first
    BOT_TOKEN = os.environ['DISCORD_BOT_TOKEN']
    TARGET_CHANNEL_ID = int(os.environ['CHANNEL_ID'])
    # These are checked here to ensure all modules can import them safely
    os.environ['GEMINI_API_KEY']
    os.environ['DISCORD_WEBHOOK_URL']
    
    MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "36"))
    SHORT_POST_WORD_THRESHOLD = 40
    print("✅ All required environment variables are present.")

except KeyError as e:
    print(f"🚨 FATAL ERROR: The environment variable {e} is missing.")
    print("   Please add it to the 'Variables' tab in your Railway service dashboard.")
    sys.exit(1)
except (ValueError, TypeError):
    print(f"🚨 FATAL ERROR: The CHANNEL_ID '{os.getenv('CHANNEL_ID')}' is not a valid integer.")
    sys.exit(1)

# --- REVISED: Correctly define file paths for persistent storage ---
if os.path.exists("/data"):
    BASE_DIR = "/data"
    print("Persistent storage at /data detected.")
else:
    BASE_DIR = "."
    print("Running locally, using current directory for storage.")

SEEN_FILE = os.path.join(BASE_DIR, "seen.json")
DETAILS_FILE = os.path.join(BASE_DIR, "details_thread_id.json")
DETAILS_MAP_FILE = os.path.join(BASE_DIR, 'details_threads.json')

# --- Now that configuration is validated, import the rest of the bot ---
from bot.parser import iter_entries
from bot.formatter import build_prompt, split_reply, format_vietnamese_date
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

# --- Environment Variables ---
SUMMARY_CHANNEL_ID = os.getenv('SUMMARY_CHANNEL_ID')
if SUMMARY_CHANNEL_ID:
    SUMMARY_CHANNEL_ID = int(SUMMARY_CHANNEL_ID)
else:
    SUMMARY_CHANNEL_ID = None
FALLBACK_ENABLED = os.getenv('FALLBACK_ENABLED', 'true').lower() in ('1', 'true', 'yes')

# --- Seen GUIDs Management ---
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
        json.dump(list(guids)[-500:], f, indent=2)

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
                import time
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


async def run_bot_job():
    """The main logic of the bot, now encapsulated in a single function that runs once."""
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
        print("🔌 Discord client closed after job.")

    await client.start(BOT_TOKEN)

async def process_feeds_once(client: discord.Client):
    """Scans feeds and processes new entries."""
    
    # Optional global summary: create header in SUMMARY_CHANNEL_ID if set
    if SUMMARY_CHANNEL_ID:
        summary_channel = client.get_channel(int(SUMMARY_CHANNEL_ID))
        if not summary_channel:
            print(f"🚨 Error: Could not find summary channel with ID {SUMMARY_CHANNEL_ID}.")
            return
        if not isinstance(summary_channel, discord.TextChannel):
            print(f"🚨 Error: Summary channel {SUMMARY_CHANNEL_ID} is not a TextChannel.")
            return
    else:
        summary_channel = None

    seen_guids = load_seen_guids()
    # Use GMT+7 (Asia/Ho_Chi_Minh) for local time
    now = pendulum.now('Asia/Ho_Chi_Minh')
    today_str = now.strftime("%Y-%m-%d")
    print(f"[{now.to_iso8601_string()}] 👟 Checking for new entries...")
    
    # Load feed metadata for entry_url resolution
    try:
        with open(os.path.join(BASE_DIR, 'feed_meta.json'), 'r', encoding='utf-8') as f:
            feed_meta = json.load(f)
    except Exception:
        feed_meta = {}

    # Global daily summary header
    if summary_channel:
        daily_summary_message = await get_daily_summary_message(summary_channel, today_str)
    else:
        daily_summary_message = None
        
    # Global reset summary logic
    if summary_channel:
        reset_flag = os.path.exists(os.path.join(BASE_DIR, "reset_summary.flag"))
        if reset_flag:
            # Remove existing summary message and its threads
            if daily_summary_message:
                # Delete any threads under the old summary message
                for thread in summary_channel.threads:
                    if thread.parent_id == daily_summary_message.id:
                        try:
                            await thread.delete()
                        except Exception:
                            pass
            if daily_summary_message:
                try:
                    await daily_summary_message.delete()
                except Exception:
                    pass
                daily_summary_message = None
            # Clear seen GUIDs to reprocess posts
            seen_guids = set()
            save_seen_guids(seen_guids)
            # Remove summary file
            summary_file = f"daily_summary_{today_str}.txt"
            if os.path.exists(summary_file):
                os.remove(summary_file)
            # Remove reset flag and clear persisted Details thread ID
            os.remove(os.path.join(BASE_DIR, "reset_summary.flag"))
            try:
                os.remove(DETAILS_FILE)
            except Exception:
                pass
            # Clear per-channel details thread mapping
            try:
                os.remove(DETAILS_MAP_FILE)
            except Exception:
                pass
    
    # Load user-defined feed->channel mappings and channel details threads
    try:
        with open(os.path.join(BASE_DIR, 'feed_map.json'), 'r') as f:
            user_map = json.load(f)
    except Exception:
        user_map = {}
        
    # Load or init per-channel Details thread map
    try:
        with open(DETAILS_MAP_FILE, 'r') as f:
            details_map = json.load(f)
    except Exception:
        details_map = {}
        
    # If no mappings and fallback disabled, skip parsing feeds
    if not user_map and not FALLBACK_ENABLED:
        print("🚨 No feed mappings and fallback is disabled; skipping feed processing.")
        return
        
    new_posts_this_cycle = []

    for entry in iter_entries():
        # skip feeds without a channel mapping
        if not user_map.get(entry['feed']):
            continue
        if entry['guid'] in seen_guids:
            continue
        if entry['published'] and (now - entry['published']).total_hours() > MAX_AGE_HOURS:
            continue
        
        new_posts_this_cycle.append(entry)

    if not new_posts_this_cycle:
        print("No new entries found in this cycle.")
        return

    # Create global daily summary if enabled and not yet created
    if summary_channel and not daily_summary_message:
        vietnamese_date = format_vietnamese_date(now)
        daily_summary_message = await create_daily_summary_message(summary_channel, vietnamese_date)
        if not daily_summary_message:
            return

    # Global details thread under the daily summary (persisted)
    detail_thread = None
    if summary_channel and daily_summary_message:
        # Try loading existing Details thread ID
        try:
            dtid = int(open(DETAILS_FILE).read().strip())
            detail_thread = client.get_channel(dtid)
            if not detail_thread or getattr(detail_thread, 'parent_id', None) != daily_summary_message.id:
                raise ValueError("Stale Details thread id")
        except Exception:
            # Create new Details thread and persist its ID, handling 'already exists' error
            try:
                detail_thread = await daily_summary_message.create_thread(name='Details')
                with open(DETAILS_FILE, 'w') as df:
                    df.write(str(detail_thread.id))
            except discord.HTTPException as e:
                if getattr(e, 'code', None) == 160004:
                    # A thread already exists for this message; fetch it
                    detail_thread = next(
                        (t for t in summary_channel.threads if t.parent_id == daily_summary_message.id and t.name == 'Details'),
                        None
                    )
                    if detail_thread:
                        with open(DETAILS_FILE, 'w') as df:
                            df.write(str(detail_thread.id))
                else:
                    print(f"🚨 Could not create Details thread: {e}")
                    return
            except Exception as e:
                print(f"🚨 Could not create Details thread: {e}")
                return

    # Group new posts by mapped channel for per-channel pipelines
    channel_groups = defaultdict(list)
    for entry in new_posts_this_cycle:
        mapped_id = user_map.get(entry['feed']) or GLOBAL_FALLBACK_CHANNEL_ID
        if not mapped_id:
            continue
        channel_groups[int(mapped_id)].append(entry)
    
    print(f">>> channel_groups: {channel_groups}")

    # Process each channel separately
    for ch_id, entries in channel_groups.items():
        ch = client.get_channel(ch_id)
        print(f">>> Processing mapped channel_id={ch_id}, channel object={ch}, entries={len(entries)}")
        if ch is None:
            print(f"🚨 Warning: client.get_channel({ch_id}) returned None.")
            continue
            
        # Forum channels: create a thread per entry with summary as thread title and post content
        if isinstance(ch, discord.ForumChannel):
            for entry in entries:
                # Determine post_time
                if entry.get('published'):
                    dt = pendulum.instance(entry['published']).in_timezone('Asia/Ho_Chi_Minh')
                    post_time = dt.to_iso8601_string()
                else:
                    post_time = 'N/A'
                    
                maybe_update(entry)
                
                # Build body and tldr
                if len(entry.get('raw', '').split()) < SHORT_POST_WORD_THRESHOLD:
                    parts, tldr = [], ''
                    title = entry.get('title', '')
                    if title:
                        parts.append(f"# **{title}**")
                    raw = entry.get('raw', '')
                    if raw and raw.strip() != title.strip():
                        parts.append(raw)
                    body = "\n\n".join(parts)
                else:
                    reply = await asyncio.to_thread(call_gemini, build_prompt(entry)) or None
                    if not reply:
                        continue
                    body, tldr = split_reply(reply)
                    
                # Include link to the original post in the thread
                body = f"{body}\n\n<{entry.get('link')}>"
                await push(client, ch, entry, body, tldr, post_time)
                
                # Persist seen GUID
                seen_guids.add(entry['guid'])
                save_seen_guids(seen_guids)
                await asyncio.sleep(5)
            continue

        # Text channels: CRITICAL workflow - Details thread gets FULL content, main channel gets summaries ONLY
        if not isinstance(ch, discord.TextChannel):
            continue
            
        # Daily summary header for this channel
        today = pendulum.now('Asia/Ho_Chi_Minh')
        vietnamese_date = format_vietnamese_date(today)
        
        # Get or create date message
        daily_msg = await get_daily_summary_message(ch, today.to_date_string())
        if not daily_msg:
            daily_msg = await create_daily_summary_message(ch, vietnamese_date)
            if not daily_msg:
                continue

        # Ensure 'Details' thread under the summary message (persisted per channel)
        details_thread = await get_or_create_channel_details_thread(client, ch, daily_msg, details_map)

        # Process each entry: FULL content to Details thread, summary to main channel
        for idx, entry in enumerate(entries, start=1):
            # Build body and tldr
            if entry.get('published'):
                dt = pendulum.instance(entry['published']).in_timezone('Asia/Ho_Chi_Minh')
                post_time = dt.to_iso8601_string()
            else:
                post_time = 'N/A'
            
            maybe_update(entry)
            
            if len(entry.get('raw', '').split()) < SHORT_POST_WORD_THRESHOLD:
                parts, tldr = [], ''
                title = entry.get('title', '')
                if title:
                    parts.append(f"# **{title}**")
                raw = entry.get('raw', '')
                if raw and raw.strip() != title.strip():
                    parts.append(raw)
                body = "\n\n".join(parts)
            else:
                reply = await asyncio.to_thread(call_gemini, build_prompt(entry)) or None
                if not reply:
                    continue
                body, tldr = split_reply(reply)
            
            # CRITICAL: Post FULL content ONLY to Details thread - NEVER to main channel
            # Post full detailed content to Details thread and capture message instance
            detailed_msg = None
            print(f"🔔 Posting detailed content for GUID {entry.get('guid')} to thread {details_thread.id}")
            try:
                detailed_msg = await push(client, details_thread, entry, body, tldr, post_time)
                print(f"🔔 Posted detailed content for GUID {entry.get('guid')}, message ID {getattr(detailed_msg, 'id', None)}")
            except Exception as e:
                print(f"🚨 Error posting detailed content for GUID {entry.get('guid')}: {e}")
            
            # Generate summary for main channel
            raw_text = entry.get('raw', '')
            summary_prompt = f"Summarize the following post in 1-2 sentences, in the same language as the original text:\n\n{raw_text}"
            summary_reply = await asyncio.to_thread(call_gemini, [{"type":"text", "text": summary_prompt}]) or ""
            summary_sentences = summary_reply.strip().replace('\n', ' ')
            
            # Generate a one-phrase descriptor (4-6 words) in original language  
            descriptor_prompt = f"Summarize the overall idea of this post in one phrase (4-6 words), in the same language as the original text:\n\n{raw_text}"
            phrase_reply = await asyncio.to_thread(call_gemini, [{"type":"text", "text": descriptor_prompt}]) or ""
            phrase = phrase_reply.strip().splitlines()[0] or "(No descriptor)"
            
            # Combine descriptor and summary on one line
            summary_line = f"({phrase}) {summary_sentences}"
            
            # Build summary content with separator - ONLY summary goes to main channel
            separator = "\n\u200b\n\u200b\n\u200b\n\u200b"
            # Build summary content with separator - ONLY summary goes to main channel
            fb_link = entry.get('link', '#')
            # Link to detailed Discord message if available
            if detailed_msg and getattr(detailed_msg, 'jump_url', None):
                link_line = f"-# [Details]({detailed_msg.jump_url}) | <{fb_link}>"
            else:
                link_line = f"-# <{fb_link}>"
            summary_content = (
                f"## {idx}. {summary_line}\n"
                f"{link_line}" + separator
            )
            
            # Send ONLY summary via webhook to main channel
            print(f"🔔 Obtaining webhook for channel {ch.id}")
            webhook_url = await get_or_create_webhook_url(ch)
            print(f"🔔 Webhook URL obtained for channel {ch.id}: {webhook_url}")
            webhook = discord.Webhook.from_url(webhook_url, client=client)
            # Split content into <=2000-char chunks to avoid Discord limits
            chunks = [summary_content[i:i+2000] for i in range(0, len(summary_content), 2000)]
            for idx_chunk, chunk in enumerate(chunks, start=1):
                print(f"🔔 Sending summary chunk {idx_chunk}/{len(chunks)} to main channel {ch.id}")
                try:
                    await webhook.send(
                        content=chunk,
                        username=entry.get('page_name'),
                        avatar_url=avatar_for(entry)
                    )
                    print(f"🔔 Sent summary chunk {idx_chunk}/{len(chunks)}")
                except Exception as e:
                    print(f"🚨 Error sending summary chunk {idx_chunk} for GUID {entry.get('guid')}: {e}")
            
            # Persist seen GUID and sleep to avoid rate limits
            seen_guids.add(entry['guid'])
            save_seen_guids(seen_guids)
            await asyncio.sleep(5)
