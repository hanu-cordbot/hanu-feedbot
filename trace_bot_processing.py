#!/usr/bin/env python3
"""Test to trace exactly where the bot processing stops"""

import os
import json
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

async def trace_bot_processing():
    """Trace the bot processing step by step"""
    
    # Import required modules
    from bot.parser import iter_entries
    from bot.main import load_seen_guids
    from bot.config import GLOBAL_FALLBACK_CHANNEL_ID
    import discord
    
    print("🔍 Tracing bot processing logic...")
    
    # Load configuration
    now = datetime.now(timezone.utc)
    seen = load_seen_guids()
    MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "36"))
    
    # Load feed mapping
    try:
        with open('feed_map.json', 'r') as f:
            user_map = json.load(f)
    except Exception:
        user_map = {}
    
    print(f"📊 Configuration:")
    print(f"  - Max age: {MAX_AGE_HOURS} hours")
    print(f"  - Fallback channel: {GLOBAL_FALLBACK_CHANNEL_ID}")
    print(f"  - Mapped feeds: {len(user_map)}")
    
    # Step 1: Collect new entries (same as bot logic)
    print(f"\n🔍 Step 1: Collecting new entries...")
    new_posts = []
    for e in iter_entries():
        cid = user_map.get(e['feed']) or GLOBAL_FALLBACK_CHANNEL_ID
        if not cid or e['guid'] in seen: 
            continue
        published = e.get('published')
        if published:
            age = (now - published).total_seconds() / 3600
            if age > MAX_AGE_HOURS: 
                continue
        new_posts.append(e)
    
    print(f"✅ Found {len(new_posts)} new posts to process")
    
    if not new_posts:
        print("❌ No new entries - bot would exit here")
        return
    
    # Step 2: Group by channel (same as bot logic)
    print(f"\n🔍 Step 2: Grouping by channel...")
    from collections import defaultdict
    channel_groups = defaultdict(list)
    for e in new_posts:
        cid = user_map.get(e['feed']) or GLOBAL_FALLBACK_CHANNEL_ID
        if cid is None:
            continue
        channel_groups[int(cid)].append(e)
    
    print(f"✅ Grouped into {len(channel_groups)} channels:")
    for ch_id, entries in channel_groups.items():
        print(f"  Channel {ch_id}: {len(entries)} entries")
    
    # Step 3: Test Discord connection for each channel
    print(f"\n🔍 Step 3: Testing Discord channel access...")
    bot_token = os.getenv('DISCORD_BOT_TOKEN')
    
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        print(f"✅ Connected as {client.user}")
        
        for ch_id, entries in channel_groups.items():
            print(f"\n🔍 Testing channel {ch_id}...")
            ch = client.get_channel(ch_id)
            
            if not ch:
                print(f"❌ Channel {ch_id} not found!")
                continue
                
            print(f"✅ Found channel: #{getattr(ch, 'name', f'Channel-{ch_id}')}")
            print(f"📝 Channel type: {type(ch)}")
            print(f"📊 Entries to process: {len(entries)}")
            
            if not isinstance(ch, discord.TextChannel):
                print(f"❌ Channel {ch_id} is not a TextChannel (type: {type(ch)})")
                continue
            
            print(f"✅ Channel {ch_id} is valid for posting")
            
            # Show first entry that would be processed
            if entries:
                first_entry = entries[0]
                print(f"📰 First entry to process:")
                print(f"  Title: {first_entry.get('title', 'No title')}")
                print(f"  Link: {first_entry.get('link', 'No link')}")
                
        await client.close()
    
    try:
        await client.start(bot_token)
    except Exception as e:
        print(f"❌ Discord connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(trace_bot_processing())
