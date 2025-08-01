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
    
    # This is the simplified cookie handling logic.
    cookie_data = os.environ.get('YT_DLP_COOKIES')
    temp_cookie_file_path = None

    try:
        # If the environment variable exists, write its content to a temporary file.
        if cookie_data:
            print("   🔑 Found YT_DLP_COOKIES environment variable. Using it for authentication.")
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
                f.write(cookie_data)
                temp_cookie_file_path = f.name
            # Tell yt-dlp to use this newly created file.
            ydl_opts['cookiefile'] = temp_cookie_file_path
        else:
            print("   ⚠️ No cookies found. Login-required videos may fail to download.")

        # Download the video.
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([normalized_url])
        return True

    except Exception as e:
        print(f"\nError downloading video with yt-dlp: {e}")
        return False
    finally:
        # Securely clean up the temporary cookie file.
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
