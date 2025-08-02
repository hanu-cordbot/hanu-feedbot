# bot/facebook_downloader.py

import os
import tempfile
import yt_dlp
import re
from typing import Optional

def download_video_ytdlp(video_url: str, output_path: Optional[str] = None) -> bool:
    """
    Download a Facebook video using yt-dlp, using cookies from an environment variable.
    """
    normalized_url = normalize_url(video_url)
    if not normalized_url:
        print("Error: Invalid Facebook video URL")
        return False
    
    # Track download progress via yt-dlp hook
    def progress_hook(info: dict):
        status = info.get('status')
        if status == 'downloading':
            total = info.get('total_bytes') or info.get('total_bytes_estimate')
            downloaded = info.get('downloaded_bytes', 0)
            if total:
                percent = downloaded / total * 100
                print(f"   📊 Downloading video: {percent:.1f}% ({downloaded}/{total} bytes)")
            else:
                print(f"   📊 Downloaded {downloaded} bytes so far...")

    output_template = '%(title).200s.%(ext)s' if not output_path else output_path
    
    ydl_opts = {
        'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        'outtmpl': output_template,
        'merge_output_format': 'mp4',
        'quiet': False,
        'no_warnings': False,
        'noplaylist': True,
        'progress_hooks': [progress_hook],  # report download progress
    }
    
    # Cookiefile logic: use YT_DLP_COOKIES env var or cookies.txt, else fallback to browser cookies
    env_cookies = os.environ.get('YT_DLP_COOKIES')
    temp_cookie_file_path = None
    cookiefile = None
    if env_cookies:
        # If the env var is a path to an existing cookies file, use it directly
        if os.path.isfile(env_cookies):
            cookiefile = env_cookies
            print(f"   🔑 Found YT_DLP_COOKIES environment variable pointing to file; using '{env_cookies}' for authentication.")
        else:
            # Treat env var as cookie content and write to a temp file
            print("   🔑 Found YT_DLP_COOKIES environment variable; using its content for authentication.")
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
                f.write(env_cookies)
                temp_cookie_file_path = f.name
            cookiefile = temp_cookie_file_path
    else:
        # Use cookies.txt directly if available
        cookies_path = os.path.join(os.getcwd(), 'cookies.txt')
        if os.path.exists(cookies_path):
            # Detect if cookies.txt is in Netscape format (not JSON)
            try:
                with open(cookies_path, 'r', encoding='utf-8') as cf:
                    first_char = cf.read(1)
                if first_char not in ('#', '.') and first_char.isalpha():
                    cookiefile = cookies_path
                    print(f"   🔑 Using cookies.txt at '{cookies_path}' for authentication.")
                else:
                    print(f"   ⚠️ cookies.txt appears to be JSON; skipping cookiefile, will use browser cookies.")
            except Exception:
                print(f"   ⚠️ Could not inspect cookies.txt; skipping cookiefile.")
    

    # Validate cookiefile format: ensure Netscape format, else skip and use browser cookies
    if cookiefile:
        try:
            with open(cookiefile, 'r', encoding='utf-8') as cf:
                first_char = cf.read(1)
            # Netscape cookies files start with '#' or domain entries (alpha); JSON files start with '{' or '['
            if first_char not in ('#', '.') and not first_char.isalpha():
                print(f"   ⚠️ Cookie file '{cookiefile}' appears to be JSON or invalid; skipping cookiefile, will use browser cookies.")
                # cleanup temp cookie file if created
                if temp_cookie_file_path and cookiefile == temp_cookie_file_path:
                    try:
                        os.remove(temp_cookie_file_path)
                    except Exception:
                        pass
                cookiefile = None
        except Exception:
            print(f"   ⚠️ Could not inspect cookie file '{cookiefile}'; skipping cookiefile.")
            if temp_cookie_file_path and cookiefile == temp_cookie_file_path:
                try:
                    os.remove(temp_cookie_file_path)
                except Exception:
                    pass
            cookiefile = None
    try:
        # If the environment variable exists, write its content to a temporary file.
        # Configure yt-dlp cookiefile or browser cookies fallback
        if cookiefile:
            ydl_opts['cookiefile'] = cookiefile
        else:
            print("   ⚠️ No valid cookie file found; continuing without cookies.")

        # Download the video.
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([normalized_url])
        return True

    except Exception as e:
        print(f"\nError downloading video with yt-dlp: {e}")
        return False
    finally:
        # Clean up temp cookiefile if one was created from env var
        if temp_cookie_file_path and os.path.exists(temp_cookie_file_path):
            os.remove(temp_cookie_file_path)

def normalize_url(url: str) -> Optional[str]:
    """Normalize and validate a Facebook video URL."""
    if not url: return None
    if not url.startswith(('http://', 'https://')): url = 'https://' + url
    
    patterns = [
        r'(?:https?:\/\/)?(?:www\.|m\.|mobile\.)?facebook\.com\/(?:[^\/]+\/videos\/|video\.php\?v=)(\d+)',
        r'(?:https?:\/\/)?(?:www\.)?facebook\.com\/watch\/\?v=(\d+)',
        r'(?:https?:\/\/)?(?:www\.)?facebook\.com\/reel\/(\d+)',
    ]
    
    url = url.split('#')[0]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return f'https://www.facebook.com/video.php?v={match.group(1)}'
    return None
