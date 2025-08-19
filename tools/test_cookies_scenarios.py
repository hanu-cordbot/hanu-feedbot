#!/usr/bin/env python3
"""
Test Facebook download with different cookie scenarios
"""
import os
import sys
import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

# Add bot directory to path
sys.path.insert(0, 'bot')

async def test_download_no_cookies():
    """Test download without cookies file"""
    post_url = "https://www.facebook.com/720895507364955/posts/743124275142078"
    
    print(f"📥 Testing download without cookies: {post_url}")
    
    # Remove cookies file if it exists
    cookies_file = Path("netscape_cookies.txt")
    if cookies_file.exists():
        cookies_file.unlink()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        post_id = post_url.split('/')[-1]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_file = os.path.join(temp_dir, f"fb_video_{post_id}_{timestamp}.mp4")
        
        try:
            # Import here to avoid issues
            from facebook_downloader import download_video_ytdlp
            
            downloaded_file = await download_video_ytdlp(post_url, temp_file)
            
            if downloaded_file and os.path.exists(downloaded_file):
                file_size = os.path.getsize(downloaded_file)
                print(f"✅ Download successful without cookies: {downloaded_file} ({file_size/1024/1024:.2f}MB)")
                return True
            else:
                print("❌ Download failed without cookies")
                return False
                
        except Exception as e:
            print(f"❌ Download test failed: {e}")
            return False

async def test_download_with_minimal_cookies():
    """Test download with minimal cookies format"""
    post_url = "https://www.facebook.com/720895507364955/posts/743124275142078"
    
    print(f"📥 Testing download with minimal cookies: {post_url}")
    
    # Create minimal cookies file in Netscape format
    cookies_content = """# Netscape HTTP Cookie File
# This is a generated file!  Do not edit.

"""
    
    with open("netscape_cookies.txt", "w") as f:
        f.write(cookies_content)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        post_id = post_url.split('/')[-1]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_file = os.path.join(temp_dir, f"fb_video_{post_id}_{timestamp}.mp4")
        
        try:
            from facebook_downloader import download_video_ytdlp
            
            downloaded_file = await download_video_ytdlp(post_url, temp_file)
            
            if downloaded_file and os.path.exists(downloaded_file):
                file_size = os.path.getsize(downloaded_file)
                print(f"✅ Download successful with minimal cookies: {downloaded_file} ({file_size/1024/1024:.2f}MB)")
                return True
            else:
                print("❌ Download failed with minimal cookies")
                return False
                
        except Exception as e:
            print(f"❌ Download test failed: {e}")
            return False

if __name__ == "__main__":
    print("🚀 Testing Facebook download with different cookie scenarios")
    print()
    
    # Test 1: No cookies
    print("1️⃣ Testing without cookies...")
    no_cookies_ok = asyncio.run(test_download_no_cookies())
    print()
    
    # Test 2: Minimal cookies
    print("2️⃣ Testing with minimal cookies...")
    minimal_cookies_ok = asyncio.run(test_download_with_minimal_cookies())
    print()
    
    print("📊 Summary:")
    print(f"  No cookies: {'✅' if no_cookies_ok else '❌'}")
    print(f"  Minimal cookies: {'✅' if minimal_cookies_ok else '❌'}")
    
    # Clean up
    cookies_file = Path("netscape_cookies.txt")
    if cookies_file.exists():
        cookies_file.unlink()
        print("\n🧹 Cleaned up test cookies file")
