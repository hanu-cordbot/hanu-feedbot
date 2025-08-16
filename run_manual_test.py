#!/usr/bin/env python3
"""
Manual full pipeline test script.
Run this locally to test the complete RSS to Discord pipeline.
"""
import os
import sys
import asyncio
import json
import time
from datetime import datetime, timezone

async def run_manual_test():
    """Run a complete manual test of the pipeline"""
    print("🔬 Starting Manual RSS Bot Pipeline Test")
    print("=" * 60)
    
    # Step 1: Environment Check
    print("\n1️⃣ Checking Environment...")
    required_vars = ['DISCORD_BOT_TOKEN', 'GEMINI_API_KEY', 'CHANNEL_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {missing_vars}")
        print("Please set these in your .env file or environment")
        return False
    
    print("✅ All required environment variables present")
    
    # Step 2: File Structure Check
    print("\n2️⃣ Checking File Structure...")
    required_files = [
        'feeds.txt',
        'bot/main.py',
        'bot/parser.py',
        'bot/formatter.py',
        'bot/gemini_client.py'
    ]
    
    missing_files = [f for f in required_files if not os.path.exists(f)]
    if missing_files:
        print(f"❌ Missing required files: {missing_files}")
        return False
    
    print("✅ All required files present")
    
    # Step 3: Test RSS Feed Parsing
    print("\n3️⃣ Testing RSS Feed Parsing...")
    try:
        from bot.parser import iter_entries
        import feedparser
        
        # Load first few feeds for testing
        with open('feeds.txt', 'r') as f:
            feeds = [line.strip() for line in f if line.strip() and not line.startswith('#')][:3]
        
        total_entries = 0
        for i, feed_url in enumerate(feeds, 1):
            print(f"  Testing feed {i}: {feed_url[:50]}...")
            feed = feedparser.parse(feed_url)
            entries = list(iter_entries(feed.entries))
            total_entries += len(entries)
            print(f"    ✅ {len(entries)} valid entries found")
        
        print(f"✅ RSS parsing successful - {total_entries} total entries")
        
    except Exception as e:
        print(f"❌ RSS parsing failed: {e}")
        return False
    
    # Step 4: Test Gemini Integration
    print("\n4️⃣ Testing Gemini AI Integration...")
    try:
        from bot.gemini_client import call_gemini
        from bot.formatter import build_prompt
        
        test_prompt = build_prompt(
            title="Test Article for Pipeline Verification",
            description="This is a test article to verify the Gemini integration is working correctly.",
            link="https://example.com/test"
        )
        
        response = await call_gemini(test_prompt)
        if response and len(response.strip()) > 10:
            print(f"✅ Gemini integration working - Response: {len(response)} characters")
        else:
            print(f"⚠️ Gemini response seems short: {response}")
            
    except Exception as e:
        print(f"❌ Gemini integration failed: {e}")
        return False
    
    # Step 5: Test Discord Connectivity
    print("\n5️⃣ Testing Discord Connectivity...")
    try:
        import requests
        
        token = os.getenv('DISCORD_BOT_TOKEN')
        headers = {'Authorization': f'Bot {token}'}
        
        # Test bot authentication
        response = requests.get('https://discord.com/api/v10/users/@me', headers=headers, timeout=10)
        if response.status_code == 200:
            bot_info = response.json()
            print(f"✅ Discord bot authenticated: {bot_info.get('username', 'Unknown')}")
        else:
            print(f"❌ Discord authentication failed: HTTP {response.status_code}")
            return False
        
        # Test channel access
        channel_id = os.getenv('CHANNEL_ID')
        channel_response = requests.get(f'https://discord.com/api/v10/channels/{channel_id}', headers=headers, timeout=10)
        if channel_response.status_code == 200:
            channel_info = channel_response.json()
            print(f"✅ Discord channel accessible: {channel_info.get('name', 'Unknown')}")
        else:
            print(f"❌ Discord channel access failed: HTTP {channel_response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Discord connectivity test failed: {e}")
        return False
    
    # Step 6: Ask for Full Pipeline Test Confirmation
    print("\n6️⃣ Full Pipeline Test Option")
    print("⚠️ The next step will run the complete bot pipeline, which will:")
    print("   - Parse all RSS feeds")
    print("   - Generate AI summaries for new articles")
    print("   - Post messages to your Discord channel")
    print("   - Update seen items and metadata")
    
    response = input("\nDo you want to run the full pipeline test? (y/N): ").lower().strip()
    
    if response == 'y' or response == 'yes':
        print("\n🚀 Running Full Pipeline Test...")
        try:
            from bot.main import run_bot_job
            
            # Create backup of seen.json
            seen_backup = None
            if os.path.exists('seen.json'):
                with open('seen.json', 'r') as f:
                    seen_backup = json.load(f)
                print("📁 Created backup of seen.json")
            
            # Run the bot
            start_time = time.time()
            await run_bot_job()
            duration = time.time() - start_time
            
            print(f"✅ Full pipeline test completed in {duration:.2f}s")
            
            # Check results
            if os.path.exists('seen.json'):
                with open('seen.json', 'r') as f:
                    new_seen = json.load(f)
                print(f"📊 Seen items: {len(new_seen)}")
            
            # Ask if user wants to restore backup
            if seen_backup:
                restore = input("\nRestore seen.json backup to avoid marking items as seen? (Y/n): ").lower().strip()
                if restore != 'n' and restore != 'no':
                    with open('seen.json', 'w') as f:
                        json.dump(seen_backup, f)
                    print("🔄 Restored seen.json backup")
            
        except Exception as e:
            print(f"❌ Full pipeline test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print("ℹ️ Skipping full pipeline test")
    
    # Step 7: Generate Dashboard Data
    print("\n7️⃣ Generating Dashboard Data...")
    try:
        # Import and run dashboard data generation
        exec(open('generate_dashboard_data.py').read())
        print("✅ Dashboard data generated")
    except Exception as e:
        print(f"❌ Dashboard data generation failed: {e}")
        return False
    
    # Step 8: Test Web Endpoints
    print("\n8️⃣ Testing Web Endpoints...")
    try:
        import requests
        
        # Test Railway deployment
        try:
            response = requests.get("https://hanu-feedbot-production.up.railway.app/api/health", timeout=10)
            if response.status_code == 200:
                print("✅ Railway deployment accessible")
            else:
                print(f"⚠️ Railway deployment returned HTTP {response.status_code}")
        except Exception as e:
            print(f"⚠️ Railway deployment test failed: {e}")
        
        # Test GitHub Pages
        try:
            response = requests.get("https://hanu-cordbot.github.io/hanu-feedbot/data/stats.json", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data and data != {"stats": {}}:
                    print("✅ GitHub Pages has data")
                else:
                    print("⚠️ GitHub Pages accessible but data is empty")
            else:
                print(f"⚠️ GitHub Pages returned HTTP {response.status_code}")
        except Exception as e:
            print(f"⚠️ GitHub Pages test failed: {e}")
            
    except Exception as e:
        print(f"❌ Web endpoint testing failed: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 Manual Pipeline Test Completed!")
    print("=" * 60)
    
    return True

async def main():
    """Main function"""
    try:
        success = await run_manual_test()
        if success:
            print("\n✅ All tests completed successfully!")
            print("\n📋 Next Steps:")
            print("   1. Check your Discord channel for new messages")
            print("   2. Verify dashboard data at: https://hanu-cordbot.github.io/hanu-feedbot/")
            print("   3. Monitor Railway deployment: https://hanu-feedbot-production.up.railway.app/")
            print("   4. GitHub Actions will run automatically every 30 minutes")
            return 0
        else:
            print("\n❌ Some tests failed - check the output above")
            return 1
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Close HTTP session if it exists
        try:
            from bot.main import HTTP_SESSION
            if HTTP_SESSION and not HTTP_SESSION.closed:
                await HTTP_SESSION.close()
        except:
            pass

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
