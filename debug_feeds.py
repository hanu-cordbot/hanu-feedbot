#!/usr/bin/env python3
"""
Debug script to check RSS feeds and understand why no entries are being processed
"""
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.parser import iter_entries
import pendulum

def debug_feeds():
    """Debug feed parsing to see what's available"""
    print("🔍 RSS Feed Debug Analysis")
    print("=" * 50)
    
    # Load feed mapping
    try:
        with open('feed_map.json', 'r') as f:
            feed_map = json.load(f)
        print(f"📋 Found {len(feed_map)} mapped feeds:")
        for feed_url, channel_id in feed_map.items():
            print(f"  - {feed_url[:60]}... → Channel {channel_id}")
    except Exception as e:
        print(f"❌ Error loading feed_map.json: {e}")
        return
    
    print("\n🔄 Parsing feeds...")
    
    # Parse feeds and check content
    try:
        all_entries = list(iter_entries())
        print(f"📊 Total entries found: {len(all_entries)}")
        
        if len(all_entries) == 0:
            print("❌ No entries found in any feeds!")
            print("Possible causes:")
            print("  - RSS feeds are down or empty")
            print("  - Network connectivity issues")
            print("  - RSS feed URLs have changed")
            return
        
        # Analyze entry ages
        now = pendulum.now('Asia/Ho_Chi_Minh')
        print(f"\n📅 Current time: {now}")
        
        age_buckets = {
            "< 1 hour": 0,
            "< 24 hours": 0, 
            "< 7 days": 0,
            "< 30 days": 0,
            "> 30 days": 0
        }
        
        print("\n📈 Entry age analysis:")
        for i, entry in enumerate(all_entries[:10]):  # Check first 10
            pub_date = entry.get('published_parsed')
            if pub_date:
                entry_time = pendulum.from_timestamp(pub_date.timestamp())
                age_hours = (now - entry_time).total_hours()
                
                title = entry.get('title', 'No title')[:50]
                print(f"  {i+1}. {title}... (Age: {age_hours:.1f} hours)")
                
                if age_hours < 1:
                    age_buckets["< 1 hour"] += 1
                elif age_hours < 24:
                    age_buckets["< 24 hours"] += 1
                elif age_hours < 168:  # 7 days
                    age_buckets["< 7 days"] += 1
                elif age_hours < 720:  # 30 days
                    age_buckets["< 30 days"] += 1
                else:
                    age_buckets["> 30 days"] += 1
            else:
                print(f"  {i+1}. {entry.get('title', 'No title')[:50]}... (No date)")
        
        print(f"\n📊 Age distribution (first 10 entries):")
        for bucket, count in age_buckets.items():
            print(f"  {bucket}: {count} entries")
        
        # Check seen entries
        try:
            with open('seen.json', 'r') as f:
                seen = json.load(f)
            print(f"\n👁️ Seen entries: {len(seen)}")
            
            # Check which entries are new
            new_entries = [e for e in all_entries if e.get('guid') not in seen]
            print(f"🆕 New (unseen) entries: {len(new_entries)}")
            
            if len(new_entries) > 0:
                print("📝 First few new entries:")
                for i, entry in enumerate(new_entries[:5]):
                    title = entry.get('title', 'No title')[:50]
                    print(f"  {i+1}. {title}...")
            
        except Exception as e:
            print(f"⚠️ Could not check seen entries: {e}")
        
    except Exception as e:
        print(f"❌ Error parsing feeds: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_feeds()
