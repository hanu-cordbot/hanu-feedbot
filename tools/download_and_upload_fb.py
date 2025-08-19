#!/usr/bin/env python3
"""
Download a Facebook post/video using the project's facebook_downloader and upload to R2
Usage: python tools/download_and_upload_fb.py <facebook_post_url>
"""
import os
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.facebook_downloader import download_video_ytdlp, normalize_url
from bot.config import r2_client

async def run(url):
    url = normalize_url(url)
    out = await download_video_ytdlp(url)
    if not out:
        print('No downloadable video found for URL')
        return 2
    print('Downloaded file:', out)

    # Upload to R2 bucket 'video-data'
    bucket = os.environ.get('VIDEO_DATA_R2_BUCKET') or os.environ.get('VIDEO_DATA_BUCKET') or 'video-data'
    print('Uploading to bucket:', bucket)
    client = r2_client()
    if not client:
        print('Could not create R2 client; ensure R2 env vars are set')
        return 3

    key = Path(out).name
    try:
        with open(out, 'rb') as f:
            client.put_object(Bucket=bucket, Key=key, Body=f.read())
        print('Uploaded to R2 as', key)
    except Exception as e:
        print('Upload failed:', e)
        return 4

    return 0

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python tools/download_and_upload_fb.py <facebook_post_url>')
        sys.exit(1)
    url = sys.argv[1]
    sys.exit(asyncio.run(run(url)))
