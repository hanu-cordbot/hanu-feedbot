#!/usr/bin/env python3
"""
🤖 HANU-FEEDBOT AUTOMATION SETUP
Creates UptimeRobot monitor for hourly job execution
"""

import requests
import json
import os

def setup_uptimerobot_monitor():
    """Set up UptimeRobot for automated hourly job execution"""
    
    print("🤖 HANU-FEEDBOT AUTOMATION SETUP")
    print("=" * 50)
    
    # Get UptimeRobot API key
    api_key = input("Enter your UptimeRobot API key (or press Enter to skip): ").strip()
    
    if not api_key:
        print("\n📋 MANUAL SETUP INSTRUCTIONS:")
        print("1. Go to: https://uptimerobot.com/")
        print("2. Sign up for free account")
        print("3. Add New Monitor:")
        print("   - Monitor Type: HTTP(s)")
        print("   - Friendly Name: Hanu FeedBot Hourly")
        print("   - URL: https://hanu-feedbot-production.up.railway.app/cron-job-default")
        print("   - Method: POST")
        print("   - Monitoring Interval: 60 minutes")
        print("   - Alert Contacts: Your email")
        print("4. Save Monitor")
        print("\n✅ Your bot will run automatically every hour!")
        return
    
    # Create monitor via API
    url = "https://api.uptimerobot.com/v2/newMonitor"
    
    data = {
        "api_key": api_key,
        "format": "json",
        "type": 1,  # HTTP(s)
        "url": "https://hanu-feedbot-production.up.railway.app/cron-job-default",
        "friendly_name": "Hanu FeedBot Hourly",
        "interval": 3600,  # 3600 seconds = 1 hour
        "http_method": 2,  # POST
        "timeout": 30
    }
    
    try:
        response = requests.post(url, data=data)
        result = response.json()
        
        if result.get("stat") == "ok":
            print("✅ UptimeRobot monitor created successfully!")
            print(f"Monitor ID: {result['monitor']['id']}")
            print("🎯 Your bot will now run automatically every hour!")
        else:
            print(f"❌ Failed to create monitor: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Error creating monitor: {e}")

def setup_railway_cron():
    """Instructions for Railway cron setup"""
    print("\n🚂 RAILWAY CRON SETUP (Alternative):")
    print("1. Go to: https://railway.app/dashboard")
    print("2. Select your hanu-feedbot project")
    print("3. Click 'Cron Jobs' tab")
    print("4. Add New Cron Job:")
    print("   - Schedule: 0 * * * * (every hour)")
    print("   - Command: curl -X POST https://hanu-feedbot-production.up.railway.app/cron-job-default")
    print("5. Save")

def test_manual_trigger():
    """Test manual job trigger"""
    print("\n🧪 TESTING MANUAL TRIGGER:")
    
    try:
        response = requests.post(
            "https://hanu-feedbot-production.up.railway.app/cron-job-default",
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Manual trigger successful: {result.get('message', 'Job executed')}")
        elif response.status_code == 401:
            print("⚠️ Authentication required (this is normal for production)")
        elif response.status_code == 405:
            print("⚠️ Method not allowed - check endpoint configuration")
        else:
            print(f"⚠️ Unexpected response: HTTP {response.status_code}")
            
    except requests.exceptions.Timeout:
        print("⚠️ Request timeout (job may be running)")
    except Exception as e:
        print(f"❌ Test failed: {e}")

def main():
    """Main automation setup"""
    print("Choose your automation method:")
    print("1. UptimeRobot (Free, Automatic)")
    print("2. Railway Cron (Manual Setup)")
    print("3. Test Manual Trigger")
    print("4. Show All Options")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice == "1":
        setup_uptimerobot_monitor()
    elif choice == "2":
        setup_railway_cron()
    elif choice == "3":
        test_manual_trigger()
    elif choice == "4":
        setup_uptimerobot_monitor()
        setup_railway_cron()
    else:
        print("Invalid choice. Showing all options:")
        setup_uptimerobot_monitor()
        setup_railway_cron()
    
    print("\n🎉 AUTOMATION SETUP COMPLETE!")
    print("Your Hanu FeedBot will now run automatically every hour!")
    print("\n📊 Monitor your bot:")
    print("- Dashboard: https://hanu-feedbot-production.up.railway.app/")
    print("- Railway Logs: https://railway.app/dashboard")
    print("- Discord: Check your configured channel for new posts")

if __name__ == "__main__":
    main()
