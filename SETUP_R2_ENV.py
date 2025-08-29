#!/usr/bin/env python3
"""
Environment Variable Setup Guide for HANU Feed Bot R2 Video Storage
"""

print("🔧 HANU FEED BOT - R2 ENVIRONMENT SETUP")
print("=" * 60)
print()

print("📋 REQUIRED ENVIRONMENT VARIABLES:")
print("   R2_BUCKET=hanu-feedbot-seen")
print("   R2_PUBLIC_URL=https://pub-12350027ec6c427c8f0b83401e0310bb.r2.dev")
print("   R2_ACCESS_KEY_ID=<your_r2_access_key>")
print("   R2_SECRET_ACCESS_KEY=<your_r2_secret_key>")
print("   R2_ENDPOINT=https://fac2cd87940bd85e71170e5cc88fe0b0.r2.cloudflarestorage.com")
print()

print("🎯 WHERE TO SET THESE:")
print()

print("1️⃣  GITHUB ACTIONS SECRETS:")
print("   • Go to: Repository → Settings → Secrets and variables → Actions")
print("   • Add each variable as a 'Repository secret'")
print("   • Make sure your workflow file (.github/workflows/*.yml) includes:")
print("     env:")
print("       R2_PUBLIC_URL: ${{ secrets.R2_PUBLIC_URL }}")
print("       R2_BUCKET: ${{ secrets.R2_BUCKET }}")
print("       # ... other R2 variables")
print()

print("2️⃣  RAILWAY DEPLOYMENT:")
print("   • Go to: Railway dashboard → Your project → Variables")
print("   • Add each variable with the exact names above")
print("   • Deploy/restart the service")
print()

print("3️⃣  DOCKER / DOCKER COMPOSE:")
print("   • Add to your .env file or docker-compose.yml:")
print("     environment:")
print("       - R2_PUBLIC_URL=https://pub-12350027ec6c427c8f0b83401e0310bb.r2.dev")
print("       - R2_BUCKET=hanu-feedbot-seen")
print("       # ... other variables")
print()

print("4️⃣  HEROKU:")
print("   • Run: heroku config:set R2_PUBLIC_URL=https://pub-12350027ec6c427c8f0b83401e0310bb.r2.dev")
print("   • Or use the Heroku dashboard → Settings → Config Vars")
print()

print("✅ VERIFICATION:")
print("   After setting variables and restarting:")
print("   1. Check bot logs for: '🔎 R2_PUBLIC_URL (masked): pub-1235...0bb.r2.dev'")
print("   2. If you see '(not set)', the environment variable is missing")
print("   3. Test video posting - should use pub-...r2.dev URLs")
print()

print("🚨 CRITICAL:")
print("   The bot will NOT post videos if R2_PUBLIC_URL is missing!")
print("   It will log: 'ERROR: R2_PUBLIC_URL is not set; refusing fallback'")
print()

print("💡 QUICK TEST:")
print("   Set R2_PUBLIC_URL locally and run:")
print("   python test_r2_video.py")
print("   Should show: '✅ R2_PUBLIC_URL is set correctly'")
