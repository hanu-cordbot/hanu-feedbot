#!/usr/bin/env python3
"""
Quick test script to verify GitHub Actions workflow setup
and test Discord forum channel support
"""

import os
import json
import asyncio
import discord
from dotenv import load_dotenv

async def test_discord_forum_access():
    """Test access to the Discord forum channel"""
    load_dotenv()
    
    BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    FORUM_CHANNEL_ID = 1393729514927947817
    
    if not BOT_TOKEN:
        print("❌ DISCORD_BOT_TOKEN not found")
        return False
    
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        print(f"✅ Connected as {client.user}")
        
        # Test forum channel access
        forum_channel = client.get_channel(FORUM_CHANNEL_ID)
        if forum_channel:
            channel_name = getattr(forum_channel, 'name', f'Channel-{FORUM_CHANNEL_ID}')
            print(f"✅ Forum channel found: {channel_name}")
            print(f"📝 Channel type: {type(forum_channel)}")
            
            if isinstance(forum_channel, discord.ForumChannel):
                print(f"🧵 Forum channel confirmed!")
                print(f"📊 Available tags: {len(getattr(forum_channel, 'available_tags', []))}")
                
                # Test if we can create a thread (commented out to avoid spam)
                # thread = await forum_channel.create_thread(name="Test Thread")
                # print(f"✅ Test thread created: {thread.name}")
                
                print("🎯 Forum channel is ready for bot posts!")
            else:
                print(f"⚠️ Channel is not a forum channel: {type(forum_channel)}")
        else:
            print(f"❌ Cannot access forum channel {FORUM_CHANNEL_ID}")
        
        await client.close()
    
    try:
        await client.start(BOT_TOKEN)
        return True
    except Exception as e:
        print(f"❌ Discord connection failed: {e}")
        return False

def check_feed_mapping():
    """Check current feed mapping configuration"""
    print("\n📋 Feed Mapping Configuration:")
    
    try:
        with open('feed_map.json', 'r') as f:
            feed_map = json.load(f)
        
        for feed_url, channel_id in feed_map.items():
            if channel_id == 1393729514927947817:
                print(f"✅ Forum channel mapped: {feed_url[:50]}...")
            else:
                print(f"📍 Regular channel {channel_id}: {feed_url[:50]}...")
        
        print(f"📊 Total mapped feeds: {len(feed_map)}")
        return True
        
    except FileNotFoundError:
        print("❌ feed_map.json not found")
        return False
    except Exception as e:
        print(f"❌ Error reading feed_map.json: {e}")
        return False

def check_seen_entries():
    """Check current seen entries count"""
    print("\n📊 Seen Entries Status:")
    
    try:
        with open('seen.json', 'r') as f:
            seen = json.load(f)
        
        print(f"📈 Total seen entries: {len(seen)}")
        print(f"📝 Last few entries:")
        for entry in seen[-3:]:
            print(f"   - {entry}")
        
        return len(seen)
        
    except FileNotFoundError:
        print("⚠️ seen.json not found (fresh start)")
        return 0
    except Exception as e:
        print(f"❌ Error reading seen.json: {e}")
        return 0

def main():
    print("🧪 GitHub Actions Workflow Test Setup")
    print("=" * 50)
    
    # Check environment
    load_dotenv()
    required_vars = ['DISCORD_BOT_TOKEN', 'GEMINI_API_KEY', 'CHANNEL_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing environment variables: {missing_vars}")
        return 1
    
    print("✅ Environment variables configured")
    
    # Check feed mapping
    if not check_feed_mapping():
        return 1
    
    # Check seen entries
    seen_count = check_seen_entries()
    
    # Test Discord access
    print("\n🔗 Testing Discord Forum Channel Access...")
    try:
        success = asyncio.run(test_discord_forum_access())
        if not success:
            return 1
    except Exception as e:
        print(f"❌ Discord test failed: {e}")
        return 1
    
    print("\n" + "=" * 50)
    print("🎯 Test Setup Summary:")
    print(f"✅ Environment: Ready")
    print(f"✅ Feed mapping: {len(json.load(open('feed_map.json')))} feeds")
    print(f"📊 Seen entries: {seen_count}")
    print(f"✅ Discord access: Confirmed")
    print(f"🧵 Forum channel: Ready for testing")
    
    print("\n🚀 Next Steps:")
    print("1. Commit and push the test workflow")
    print("2. Go to Actions tab → 'HANU Feed Bot - TEST MODE'")
    print("3. Run workflow with test_entries_count=3")
    print("4. Check Discord forum channel for new threads")
    print("5. Monitor execution logs for any issues")
    
    return 0

if __name__ == "__main__":
    exit(main())
