#!/usr/bin/env python3
"""
Local test for Facebook download and R2 upload
"""
import os
import sys
import json
import asyncio
import tempfile
import hashlib
from datetime import datetime
from pathlib import Path

# Add bot directory to path
sys.path.insert(0, 'bot')

def test_imports():
    """Test if all required imports work"""
    print("🧪 Testing imports...")
    
    try:
        import boto3
        print("✅ boto3 imported successfully")
    except ImportError as e:
        print(f"❌ boto3 import failed: {e}")
        return False
    
    try:
        from facebook_downloader import download_video_ytdlp
        print("✅ facebook_downloader imported successfully")
    except ImportError as e:
        print(f"❌ facebook_downloader import failed: {e}")
        return False
    
    return True

def test_facebook_downloader_function():
    """Test if the Facebook downloader function exists and is callable"""
    try:
        from facebook_downloader import download_video_ytdlp
        
        if callable(download_video_ytdlp):
            print("✅ download_video_ytdlp is callable")
            return True
        else:
            print("❌ download_video_ytdlp is not callable")
            return False
    except Exception as e:
        print(f"❌ Error testing download_video_ytdlp: {e}")
        return False

def create_r2_client():
    """Create R2 client"""
    access_key = os.environ.get('R2_ACCESS_KEY_ID')
    secret_key = os.environ.get('R2_SECRET_ACCESS_KEY') 
    endpoint = os.environ.get('R2_ENDPOINT')
    
    if not all([access_key, secret_key, endpoint]):
        print("❌ Missing R2 credentials (this is expected for local test)")
        return None
    
    try:
        import boto3
        return boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint
        )
    except Exception as e:
        print(f"❌ Error creating R2 client: {e}")
        return None

async def test_download_only():
    """Test just the download part without R2 upload"""
    post_url = "https://www.facebook.com/720895507364955/posts/743124275142078"
    
    print(f"📥 Testing download from: {post_url}")
    
    # Create temporary directory for download
    with tempfile.TemporaryDirectory() as temp_dir:
        post_id = post_url.split('/')[-1]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_file = os.path.join(temp_dir, f"fb_video_{post_id}_{timestamp}.mp4")
        
        print(f"📁 Temporary file: {temp_file}")
        
        try:
            from facebook_downloader import download_video_ytdlp
            
            # Check if cookies file exists
            if not os.path.exists("netscape_cookies.txt"):
                print("⚠️ Creating empty netscape_cookies.txt")
                Path("netscape_cookies.txt").touch()
            
            downloaded_file = await download_video_ytdlp(post_url, temp_file)
            
            if downloaded_file and os.path.exists(downloaded_file):
                file_size = os.path.getsize(downloaded_file)
                print(f"✅ Download successful: {downloaded_file} ({file_size/1024/1024:.2f}MB)")
                return True
            else:
                print("❌ Download failed - no file created")
                return False
                
        except Exception as e:
            print(f"❌ Download test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    print("🚀 Testing Facebook download functionality locally")
    print()
    
    # Test 1: Check imports
    print("1️⃣ Testing imports...")
    imports_ok = test_imports()
    print()
    
    # Test 2: Check function
    print("2️⃣ Testing download function...")
    function_ok = test_facebook_downloader_function()
    print()
    
    # Test 3: Test R2 client (will fail without creds, that's ok)
    print("3️⃣ Testing R2 client creation...")
    r2_client = create_r2_client()
    r2_ok = r2_client is not None
    print()
    
    # Test 4: Test download (may fail without proper cookies)
    print("4️⃣ Testing actual download...")
    if imports_ok and function_ok:
        download_ok = asyncio.run(test_download_only())
    else:
        download_ok = False
        print("⏭️ Skipping download test due to import failures")
    print()
    
    print("📊 Summary:")
    print(f"  Imports: {'✅' if imports_ok else '❌'}")
    print(f"  Function: {'✅' if function_ok else '❌'}")
    print(f"  R2 Client: {'✅' if r2_ok else '❌'}")
    print(f"  Download: {'✅' if download_ok else '❌'}")
    
    if imports_ok and function_ok:
        print("\n✅ Core functionality is available!")
    else:
        print("\n❌ There are issues with the core functionality")
