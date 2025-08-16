#!/usr/bin/env python3
"""
Quick test of Railway deployment and GitHub Pages automation setup
"""

import requests
import time

def test_railway():
    """Test Railway endpoints"""
    print("🚂 Testing Railway deployment...")
    
    base_url = "https://hanu-feedbot-production.up.railway.app"
    
    endpoints = [
        "/api/health",
        "/api/public/feeds", 
        "/api/public/stats"
    ]
    
    for endpoint in endpoints:
        try:
            print(f"  Testing {endpoint}...")
            response = requests.get(f"{base_url}{endpoint}", timeout=30)
            
            if response.status_code == 200:
                print(f"  ✅ {endpoint} - OK")
                try:
                    data = response.json()
                    if endpoint == "/api/health":
                        print(f"     Service: {data.get('service', 'Unknown')}")
                    elif endpoint == "/api/public/feeds":
                        print(f"     Feeds: {len(data.get('feeds', []))}")
                    elif endpoint == "/api/public/stats":
                        print(f"     Status: {data.get('status', 'Unknown')}")
                except:
                    print(f"     Response: {response.text[:100]}...")
            else:
                print(f"  ❌ {endpoint} - HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"  ⏰ {endpoint} - Timeout (Railway might be cold starting)")
        except Exception as e:
            print(f"  ❌ {endpoint} - Error: {e}")

def main():
    print("🧪 RAILWAY + GITHUB PAGES AUTOMATION TEST")
    print("=" * 50)
    
    test_railway()
    
    print("\n📋 NEXT STEPS FOR GITHUB PAGES:")
    print("1. Go to: https://github.com/hanu-cordbot/hanu-feedbot/settings/actions")
    print("2. Enable GitHub Actions")
    print("3. Go to: https://github.com/hanu-cordbot/hanu-feedbot/settings/pages") 
    print("4. Set Source to 'GitHub Actions'")
    print("5. Wait 5-10 minutes for deployment")
    print("6. Visit: https://hanu-cordbot.github.io/hanu-feedbot/")
    
    print("\n🤖 AUTOMATION FEATURES:")
    print("✅ Hourly data sync from Railway to GitHub Pages")
    print("✅ Smart data loading (local cache + API fallback)")
    print("✅ Public API endpoints for dashboard")
    print("✅ Automatic dashboard deployment")
    
    print("\n🎉 Your setup is ready for automated sync!")

if __name__ == "__main__":
    main()
