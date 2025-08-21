#!/usr/bin/env python3
"""
Download a Facebook post's video using the bot helper and upload to R2 using r2.uploader.
Usage: python tools/fb_upload_run.py <post_url>
"""
import sys
import asyncio
import os
import io
from pathlib import Path

from bot.facebook_downloader import download_video_ytdlp
from r2.uploader import upload_file


async def run(url: str):
    temp = await download_video_ytdlp(url)
    if not temp:
        print('No video downloaded')
        return 1
    print('Downloaded to', temp)
    with open(temp, 'rb') as f:
        data = f.read()
    bio = io.BytesIO(data)
    key = f"videos/{int(__import__('time').time())}_facebook_video.mp4"
    res = upload_file(bio, key, len(data))
    if res:
        print('Uploaded to R2:', res)
        return 0
    else:
        print('Upload failed')
        return 2


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: fb_upload_run.py <post_url>')
        sys.exit(2)
    url = sys.argv[1]
    sys.exit(asyncio.run(run(url)))
