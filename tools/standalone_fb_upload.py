#!/usr/bin/env python3
"""
Standalone Facebook download and R2 upload script for GitHub Actions
"""
import os
import sys
import json
import asyncio
import tempfile
import hashlib
from datetime import datetime
from pathlib import Path

def create_r2_client():
    """Create R2 client"""
    try:
        import boto3
    except ImportError:
        print("❌ boto3 not available")
        return None
        
    access_key = os.environ.get('R2_ACCESS_KEY_ID')
    secret_key = os.environ.get('R2_SECRET_ACCESS_KEY') 
    endpoint = os.environ.get('R2_ENDPOINT')
    
    if not all([access_key, secret_key, endpoint]):
        print("❌ Missing R2 credentials")
        print(f"  R2_ACCESS_KEY_ID: {'SET' if access_key else 'MISSING'}")
        print(f"  R2_SECRET_ACCESS_KEY: {'SET' if secret_key else 'MISSING'}")
        print(f"  R2_ENDPOINT: {'SET' if endpoint else 'MISSING'}")
        return None
    
    try:
        return boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint
        )
    except Exception as e:
        print(f"❌ Error creating R2 client: {e}")
        return None

async def download_with_ytdlp(url, output_path):
    """Download using yt-dlp directly"""
    try:
        cmd = [
            "yt-dlp",
            "--cookies", "netscape_cookies.txt",
            "-f", "best",
            "-o", output_path,
            url
        ]
        
        print(f"📥 Running: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        stdout_text = stdout.decode()
        stderr_text = stderr.decode()
        
        print(f"📤 yt-dlp stdout: {stdout_text}")
        if stderr_text:
            print(f"⚠️ yt-dlp stderr: {stderr_text}")
        
        if process.returncode == 0 and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f"✅ Download successful: {output_path} ({file_size/1024/1024:.2f}MB)")
            return output_path
        else:
            print(f"❌ Download failed with return code {process.returncode}")
            return None
            
    except Exception as e:
        print(f"❌ Download error: {e}")
        import traceback
        traceback.print_exc()
        return None

async def download_and_upload():
    """Download Facebook video and upload to R2"""
    post_url = os.environ.get('POST_URL')
    bucket_name = os.environ.get('BUCKET_NAME', 'video-data')
    
    if not post_url:
        print("❌ POST_URL not provided")
        return False
    
    print(f"📥 Downloading from: {post_url}")
    print(f"🪣 Target bucket: {bucket_name}")
    
    # Create temporary directory for download
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract post ID for filename
        post_id = post_url.split('/')[-1]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_file = os.path.join(temp_dir, f"fb_video_{post_id}_{timestamp}.mp4")
        
        print(f"📁 Temporary file: {temp_file}")
        
        # Try to download using yt-dlp directly
        downloaded_file = await download_with_ytdlp(post_url, temp_file)
        
        if not downloaded_file or not os.path.exists(downloaded_file):
            print("❌ Failed to download video")
            return False
        
        file_size = os.path.getsize(downloaded_file)
        print(f"✅ Downloaded video: {downloaded_file} ({file_size/1024/1024:.2f}MB)")
        
        # Create R2 client
        r2_client = create_r2_client()
        if not r2_client:
            print("❌ Failed to create R2 client")
            return False
        
        # Create key for R2 upload
        file_hash = hashlib.md5(open(downloaded_file, 'rb').read()).hexdigest()[:8]
        key = f"facebook_videos/{post_id}_{timestamp}_{file_hash}.mp4"
        
        print(f"📤 Uploading to R2 bucket '{bucket_name}' with key: {key}")
        
        # Upload to R2
        try:
            with open(downloaded_file, 'rb') as f:
                r2_client.upload_fileobj(f, bucket_name, key)
            
            print(f"✅ Successfully uploaded to R2: {key}")
            
            # Verify upload by checking object metadata
            try:
                response = r2_client.head_object(Bucket=bucket_name, Key=key)
                print(f"📊 Upload verified - Size: {response['ContentLength']} bytes")
                print(f"📅 Last Modified: {response['LastModified']}")
                return True
            except Exception as e:
                print(f"⚠️ Upload verification failed: {e}")
                return False
                
        except Exception as e:
            print(f"❌ R2 upload failed: {e}")
            import traceback
            traceback.print_exc()
            return False

def check_environment():
    """Check if all required tools and environment variables are available"""
    print("🔍 Checking environment...")
    
    # Check yt-dlp
    try:
        import subprocess
        result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ yt-dlp available: {result.stdout.strip()}")
        else:
            print("❌ yt-dlp not working")
            return False
    except Exception as e:
        print(f"❌ yt-dlp check failed: {e}")
        return False
    
    # Check boto3
    try:
        import boto3
        print("✅ boto3 available")
    except ImportError:
        print("❌ boto3 not available")
        return False
    
    # Check cookies file
    if os.path.exists("netscape_cookies.txt"):
        print("✅ netscape_cookies.txt exists")
    else:
        print("⚠️ netscape_cookies.txt missing")
    
    return True

if __name__ == "__main__":
    print("🚀 Standalone Facebook download and R2 upload test")
    print()
    
    # Check environment first
    if not check_environment():
        print("❌ Environment check failed")
        sys.exit(1)
    
    print()
    
    # Run the test
    result = asyncio.run(download_and_upload())
    
    if result:
        print("🎉 Test completed successfully!")
        sys.exit(0)
    else:
        print("❌ Test failed")
        sys.exit(1)
