#!/usr/bin/env python3
"""Debug script to see exactly what happens during feed processing"""

import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def debug_feed_processing():
    """Debug the feed processing logic step by step"""
    
    from bot.parser import iter_entries
    from bot.main import load_seen_guids
    from bot.config import GLOBAL_FALLBACK_CHANNEL_ID
    
    print(f"🔧 Configuration check:")
    print(f"  - GLOBAL_FALLBACK_CHANNEL_ID: {GLOBAL_FALLBACK_CHANNEL_ID}")
    print(f"  - From env: {os.getenv('GLOBAL_FALLBACK_CHANNEL_ID')}")
    
    # Load feed mapping
    try:
        with open('feed_map.json', 'r') as f:
            user_map = json.load(f)
        print(f"  - Mapped feeds: {len(user_map)}")
        for feed_url, channel_id in user_map.items():
            print(f"    {feed_url[:50]}... -> {channel_id}")
    except Exception as e:
        print(f"  - No feed mapping found: {e}")
        user_map = {}
    
    # Check recent entries step by step
    now = datetime.now(timezone.utc)
    seen = load_seen_guids()
    MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "36"))
    
    print(f"\n🔍 Processing entries...")
    print(f"  - Max age: {MAX_AGE_HOURS} hours")
    print(f"  - Already seen: {len(seen)}")
    
    new_posts = []
    skipped_reasons = {"no_channel": 0, "already_seen": 0, "too_old": 0}
    
    for i, e in enumerate(iter_entries()):
        # Check channel mapping
        cid = user_map.get(e['feed']) or GLOBAL_FALLBACK_CHANNEL_ID
        if not cid:
            skipped_reasons["no_channel"] += 1
            if i < 5:  # Show first few for debugging
                print(f"    Entry {i+1}: No channel - {e.get('title', 'No title')[:40]}...")
            continue
        
        # Check if already seen
        if e['guid'] in seen:
            skipped_reasons["already_seen"] += 1
            continue
            
        # Check age
        published = e.get('published')
        if published is None:
            published = now  # Fallback to now if no published date
        age = (now - published).total_seconds() / 3600  # Convert to hours
        if age > MAX_AGE_HOURS:
            skipped_reasons["too_old"] += 1
            if i < 5:  # Show first few for debugging
                print(f"    Entry {i+1}: Too old ({age:.1f}h) - {e.get('title', 'No title')[:40]}...")
            continue
        
        new_posts.append(e)
        if len(new_posts) <= 5:  # Show first few that would be processed
            print(f"    ✅ Entry {i+1}: Would process ({age:.1f}h old) - {e.get('title', 'No title')[:40]}...")
    
    print(f"\n📊 Results:")
    print(f"  - Would process: {len(new_posts)}")
    print(f"  - Skipped (no channel): {skipped_reasons['no_channel']}")
    print(f"  - Skipped (already seen): {skipped_reasons['already_seen']}")
    print(f"  - Skipped (too old): {skipped_reasons['too_old']}")
    
    if new_posts:
        print(f"\n🎯 Sample entries that would be posted:")
        for i, entry in enumerate(new_posts[:3], 1):
            published = entry.get('published')
            if published:
                age = (now - published).total_seconds() / 3600
            else:
                age = 0
            channel_id = user_map.get(entry['feed']) or GLOBAL_FALLBACK_CHANNEL_ID
            print(f"  {i}. Title: {entry.get('title', 'No title')}")
            print(f"     Age: {age:.1f} hours")
            print(f"     Channel: {channel_id}")
            print(f"     Feed: {entry.get('feed', 'Unknown')[:50]}...")
            print(f"     Link: {entry.get('link', 'No link')}")
            print()

if __name__ == "__main__":
    debug_feed_processing()
