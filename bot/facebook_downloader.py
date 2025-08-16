import re
import os
import json
import random
import asyncio
import tempfile
from pathlib import Path

try:  # R2 uploads are optional; skip if package not available
    from r2 import upload_path_and_prune
except Exception:  # pragma: no cover - optional dependency
    upload_path_and_prune = None

# Path to cookies file
COOKIES_PATH = Path("netscape_cookies.txt")
JSON_COOKIES_PATH = Path("cookies.txt")

# Target Facebook page ID
FB_PAGE_ID = "720895507364955"

# Special posts we always want to process (even if not in feed)
SPECIAL_POSTS = [
    {
        "id": "743124275142078",
        "url": "https://www.facebook.com/720895507364955/posts/743124275142078",
        "title": "HANU Special Video Post"
    }
]

# File to track processed special posts
SPECIAL_POSTS_SEEN_FILE = Path("special_posts_seen.json")

def normalize_url(url):
    """Compatibility function for backward compatibility"""
    return url

def check_special_posts():
    """Check if we have any special posts to process"""
    # Load seen posts
    seen_posts = set()
    if SPECIAL_POSTS_SEEN_FILE.exists():
        try:
            with open(SPECIAL_POSTS_SEEN_FILE, 'r') as f:
                seen_posts = set(json.load(f))
        except:
            pass
    
    # Find posts we haven't processed yet
    posts_to_process = []
    for post in SPECIAL_POSTS:
        if post["id"] not in seen_posts:
            posts_to_process.append(post)
    
    if posts_to_process:
        print(f"? Found {len(posts_to_process)} special posts to process")
    
    return posts_to_process

def mark_special_post_seen(post_id):
    """Mark a special post as seen"""
    # Load seen posts
    seen_posts = set()
    if SPECIAL_POSTS_SEEN_FILE.exists():
        try:
            with open(SPECIAL_POSTS_SEEN_FILE, 'r') as f:
                seen_posts = set(json.load(f))
        except:
            pass
    
    # Add post ID and save
    seen_posts.add(post_id)
    with open(SPECIAL_POSTS_SEEN_FILE, 'w') as f:
        json.dump(list(seen_posts), f)

def extract_facebook_post_url(entry):
    """Extract Facebook post URL from entry using multiple strategies"""
    # Debug output
    print(f"? Processing entry: {entry.get('title', '')}")
    
    # Check for our target post ID in any field
    for key in ['link', 'id', 'title', 'summary']:
        if key in entry:
            value = entry.get(key)
            if isinstance(value, str) and "743124275142078" in value:
                print(f"[TARGET] FOUND TARGET POST ID IN FIELD '{key}'!")
                return "https://www.facebook.com/720895507364955/posts/743124275142078"
    
    # Convert entry to string and check if our target ID exists ANYWHERE
    entry_str = str(entry)
    if "743124275142078" in entry_str:
        print(f"[TARGET] FOUND TARGET VIDEO POST! Entry title: {entry.get('title', 'Unknown')}")
        return "https://www.facebook.com/720895507364955/posts/743124275142078"
    
    # Regular URL extraction logic
    link = entry.get('link', '')
    if link and "facebook.com" in link and ("/posts/" in link or "/videos/" in link or "/watch/" in link):
        print(f"[OK] Found Facebook post in main link: {link}")
        return link
    
    # Look for FB post patterns in the entry string
    patterns = [
        r'facebook\.com/\d+/posts/\d+',
        r'facebook\.com/\d+/videos/\d+',
        r'facebook\.com/watch\?v=\d+'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, entry_str)
        if matches:
            for match in matches:
                full_url = f"https://www.{match}" if not match.startswith('http') else match
                print(f"[OK] Found Facebook URL pattern: {full_url}")
                return full_url
    
    return None

async def download_video_ytdlp(url, output_path=None):
    """Download Facebook video using yt-dlp with authentication"""
    # Skip image/CDN URLs - only process actual Facebook posts
    if "fbcdn.net" in url or "scontent-" in url:
        print(f"[WARNING] SKIPPING CDN URL: {url}")
        return None
        
    # Skip non-Facebook URLs
    if not "facebook.com" in url:
        print(f"[WARNING] Not a Facebook URL: {url}")
        return None
    
    try:
        # Generate a safe temporary filename if not provided
        if not output_path:
            temp_dir = tempfile.gettempdir()
            random_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
            output_path = os.path.join(temp_dir, f"facebook_video_{random_id}.mp4")
        
        # Use the EXACT command that works for you
        cmd = [
            "yt-dlp",
            "--cookies", "netscape_cookies.txt",
            "-f", "best",
            "-o", output_path,
            url
        ]
        
        print(f"[DOWNLOAD] DOWNLOADING FACEBOOK VIDEO: {url}")
        
        # Run yt-dlp as a subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        stdout_text = stdout.decode()
        stderr_text = stderr.decode()
        
        # Check if this is a "no video available" error
        if "This video is only available for registered users" in stderr_text:
            print(f"[WARNING] Post does not contain a downloadable video")
            return None
        
        # Check for other errors
        if process.returncode != 0:
            print(f"[ERROR] Download failed with return code {process.returncode}")
            print(f"[ERROR] Error: {stderr_text}")
            return None
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f"[OK] Successfully downloaded video ({file_size/1024/1024:.2f}MB): {output_path}")

            # Only consider it a success if it's large enough to be a video
            if file_size < 100000:
                print(f"[WARNING] File too small to be a video ({file_size} bytes), likely just an image")
                return None
            # Upload to R2 if configured
            if upload_path_and_prune and os.environ.get("R2_BUCKET"):
                try:
                    upload_path_and_prune(output_path)
                except Exception as exc:
                    print(f"[WARNING] Failed to upload to R2: {exc}")

            return output_path
        else:
            print(f"[ERROR] Output file not found: {output_path}")
            return None
            
    except Exception as e:
        print(f"[ERROR] Error downloading video: {e}")
        import traceback
        traceback.print_exc()
        return None
