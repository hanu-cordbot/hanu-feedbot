#!/usr/bin/env python3
"""Test script to verify Discord posting with recent entries or test with extended age filter"""

import os
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_discord_posting():
    """Test Discord posting functionality"""
    
    # Import bot components
    from bot.parser import iter_entries
    from bot.main import load_seen_guids, TARGET_CHANNEL_ID, MAX_AGE_HOURS
    
    print(f"🔧 Configuration:")
    print(f"  - Target Channel ID: {TARGET_CHANNEL_ID}")
    print(f"  - Max Age Hours: {MAX_AGE_HOURS}")
    print(f"  - Discord Bot Token: {'✅ Set' if os.getenv('DISCORD_BOT_TOKEN') else '❌ Missing'}")
    print(f"  - Gemini API Key: {'✅ Set' if os.getenv('GEMINI_API_KEY') else '❌ Missing'}")
    
    # Check for recent entries
    print(f"\n🔍 Analyzing feed entries...")
    now = datetime.now(timezone.utc)
    seen = load_seen_guids()
    
    all_entries = list(iter_entries())
    print(f"📊 Total entries: {len(all_entries)}")
    print(f"🔍 Already seen: {len(seen)}")
    
    # Check age distribution
    recent_entries = []
    age_buckets = {"< 1 day": 0, "1-7 days": 0, "1-4 weeks": 0, "> 4 weeks": 0}
    
    for entry in all_entries:
        if entry['guid'] in seen:
            continue
            
        published = entry.get('published')
        if published:
            age_hours = (now - published).total_seconds() / 3600
            age_days = age_hours / 24
            
            if age_days < 1:
                age_buckets["< 1 day"] += 1
            elif age_days < 7:
                age_buckets["1-7 days"] += 1
            elif age_days < 28:
                age_buckets["1-4 weeks"] += 1
            else:
                age_buckets["> 4 weeks"] += 1
                
            if age_hours <= MAX_AGE_HOURS:
                recent_entries.append(entry)
    
    print(f"\n📈 Age distribution of unseen entries:")
    for bucket, count in age_buckets.items():
        print(f"  {bucket}: {count}")
    
    print(f"\n⏰ Recent entries (within {MAX_AGE_HOURS}h): {len(recent_entries)}")
    
    if recent_entries:
        print("✅ Found recent entries! The bot should process these:")
        for i, entry in enumerate(recent_entries[:3], 1):
            age_hours = (now - entry.get('published')).total_seconds() / 3600
            print(f"  {i}. {entry.get('title', 'No title')[:50]}...")
            print(f"     Age: {age_hours:.1f} hours")
            print(f"     Link: {entry.get('link')}")
    else:
        print("⚠️ No recent entries found within the current age limit.")
        print("💡 The bot ran successfully but had no recent content to process.")
        
        # Show the most recent entries regardless of age
        all_with_dates = [e for e in all_entries if e.get('published') and e['guid'] not in seen]
        if all_with_dates:
            all_with_dates.sort(key=lambda x: x['published'], reverse=True)
            print(f"\n📰 Most recent unseen entries (regardless of age):")
            for i, entry in enumerate(all_with_dates[:5], 1):
                published = entry.get('published')
                if published:
                    age_days = (now - published).total_seconds() / (3600 * 24)
                    print(f"  {i}. {entry.get('title', 'No title')[:50]}...")
                    print(f"     Age: {age_days:.1f} days")
                    print(f"     Published: {published}")

# Test with temporarily extended age limit
async def test_with_extended_age():
    """Test by temporarily extending the age limit to process older entries"""
    print(f"\n🧪 Testing with extended age limit...")
    
    # Temporarily set a much larger age limit
    original_max_age = os.environ.get('MAX_AGE_HOURS', '36')
    os.environ['MAX_AGE_HOURS'] = '8760'  # 1 year
    
    try:
        # Import after setting the environment variable
        from bot.main import run_bot_job
        
        print(f"🤖 Running bot with extended age limit (1 year)...")
        await run_bot_job()
        print(f"✅ Bot execution completed!")
        
        # Check if anything was processed
        from bot.main import load_seen_guids
        seen_after = load_seen_guids()
        print(f"📝 Entries marked as seen: {len(seen_after)}")
        
    finally:
        # Restore original setting
        os.environ['MAX_AGE_HOURS'] = original_max_age

async def main():
    await test_discord_posting()
    
    # Offer to test with extended age limit
    print(f"\n❓ Would you like to test Discord posting with older entries?")
    print(f"   This will temporarily extend the age limit to process older content.")
    print(f"   Reply 'y' to continue with extended test, or any other key to skip.")
    
    # For automated testing, let's run the extended test
    print(f"🚀 Running extended age test...")
    await test_with_extended_age()

if __name__ == "__main__":
    asyncio.run(main())
