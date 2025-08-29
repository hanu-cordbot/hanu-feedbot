#!/usr/bin/env python3
"""
Test what happens when R2_PUBLIC_URL is not set
"""
import os
import sys
from pathlib import Path

# Add the bot module to path
sys.path.insert(0, str(Path(__file__).parent))

# Clear R2_PUBLIC_URL to simulate deployment issue
if 'R2_PUBLIC_URL' in os.environ:
    del os.environ['R2_PUBLIC_URL']

print("🔍 Testing without R2_PUBLIC_URL...")
r2_url = os.getenv('R2_PUBLIC_URL')
print(f"R2_PUBLIC_URL from env: {r2_url}")

# Simulate what the upload function would return
if r2_url:
    result_url = f"{r2_url.rstrip('/')}/videos/test.mp4"
    print(f"Would generate: {result_url}")
else:
    print("❌ ERROR: R2_PUBLIC_URL not set - upload would return None")
    print("📝 This is why videos are not being posted!")
    print("")
    print("🔧 SOLUTION:")
    print("   1. Set R2_PUBLIC_URL in your deployment environment")
    print("   2. Value should be: https://pub-12350027ec6c427c8f0b83401e0310bb.r2.dev")
    print("   3. Restart the bot to pick up the new environment variable")
