#!/usr/bin/env python3
"""Quick test script to check feed parsing and processing"""

import os
from dotenv import load_dotenv
from bot.parser import iter_entries

# Load environment variables
load_dotenv()

def test_feed_parsing():
    """Test parsing feeds using the bot's parser"""
    feeds_file = "feeds.txt"
    
    if not os.path.exists(feeds_file):
        print("❌ feeds.txt not found!")
        return
    
    with open(feeds_file, 'r') as f:
        feed_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    print(f"📁 Found {len(feed_urls)} feed URLs")
    
    # Test all feeds using iter_entries()
    print(f"\n🔍 Testing all feeds using iter_entries()...")
    try:
        entries = list(iter_entries())
        print(f"✅ Found {len(entries)} total entries")
        
        if entries:
            print(f"\n📰 Sample entries:")
            for i, entry in enumerate(entries[:5], 1):
                print(f"  {i}. {entry.get('title', 'No title')[:60]}...")
                print(f"     🔗 {entry.get('link', 'No link')}")
                print(f"     📅 {entry.get('published', 'No date')}")
                print(f"     📄 {entry.get('page_name', 'No page')}")
                print()
        else:
            print("⚠️ No entries found in any feeds")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_feed_parsing()
