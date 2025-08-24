#!/usr/bin/env python3
"""
R2 Video Uploader for HANU Feed Bot
Handles uploading large videos (>8MB) to R2 bucket instead of Catbox
"""
import os
import io
import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from bot.config import r2_client, SEEN_R2_BUCKET

# R2 video storage configuration
R2_VIDEO_BUCKET = os.getenv('R2_BUCKET') or os.getenv('FEEDS_R2_BUCKET') or SEEN_R2_BUCKET
R2_PUBLIC_URL = os.getenv('R2_PUBLIC_URL')  # e.g., "https://pub-xxxxx.r2.dev"

def generate_video_filename(post_title: str, extension: str = "mp4") -> str:
    """Generate a unique filename for video storage"""
    # Clean post title for filename
    clean_title = "".join(c for c in post_title if c.isalnum() or c in (' ', '-', '_')).strip()
    clean_title = clean_title.replace(' ', '_')[:50]  # Limit length
    
    # Add date for organization
    date_str = datetime.now().strftime('%Y%m%d')
    
    # Add hash for uniqueness
    hash_obj = hashlib.md5(f"{post_title}{datetime.now().isoformat()}".encode())
    hash_suffix = hash_obj.hexdigest()[:8]
    
    return f"videos/{date_str}_{clean_title}_{hash_suffix}.{extension}"

def upload_video_to_r2(video_data: bytes, post_title: str) -> Optional[str]:
    """Upload video to R2 bucket and return public URL"""
    if not R2_VIDEO_BUCKET:
        print("❌ R2 bucket not configured for video upload")
        return None
        
    client = r2_client()
    if not client:
        print("❌ R2 client not available")
        return None
    try:
        # Generate unique filename
        filename = generate_video_filename(post_title)

        # Determine public base URL at call time (so runtime env is respected)
        r2_public_env = os.getenv('R2_PUBLIC_URL')
        print(f"📤 Uploading video to R2: {filename} ({len(video_data)/1024/1024:.2f}MB)")

        # Upload to R2
        client.put_object(
            Bucket=R2_VIDEO_BUCKET,
            Key=filename,
            Body=video_data,
            ContentType='video/mp4',
            ACL='public-read'  # Make publicly accessible
        )

        # Generate public URL
        # Prefer runtime environment variable if available
        if r2_public_env:
            public_url = f"{r2_public_env.rstrip('/')}/{filename}"
            print(f"ℹ️ Using R2_PUBLIC_URL from environment: {r2_public_env}")
        elif R2_PUBLIC_URL:
            public_url = f"{R2_PUBLIC_URL.rstrip('/')}/{filename}"
            print(f"ℹ️ Using R2_PUBLIC_URL from module config: {R2_PUBLIC_URL}")
        else:
            # No public base configured — fall back to cloudflarestorage URL but warn
            public_url = f"https://{R2_VIDEO_BUCKET}.r2.cloudflarestorage.com/{filename}"
            print("⚠️ R2_PUBLIC_URL is not set; using cloudflarestorage fallback which may not be publicly accessible")

        print(f"✅ Video uploaded to R2: {public_url}")
        return public_url
    except Exception as e:
        print(f"❌ Failed to upload video to R2: {e}")
        import traceback
        traceback.print_exc()
        return None

async def upload_video_to_r2_async(video_data: bytes, post_title: str) -> Optional[str]:
    """Async wrapper for R2 video upload"""
    return await asyncio.to_thread(upload_video_to_r2, video_data, post_title)

def create_video_embed_message(video_url: str, post_title: str, post_url: str = None) -> str:
    """Create a Discord message with embedded video from R2.

    Simplified format: title + direct video URL. Do not include Original Post link
    (the dispatcher already posts the post URL in the body when relevant).
    """
    message_parts = [
        f"🎥 **{post_title}**",
        video_url,
    ]
    return "\n".join(message_parts)

def get_video_size_limit() -> int:
    """Get the size limit for direct Discord uploads (8MB)"""
    return 8 * 1024 * 1024  # 8MB in bytes

def should_use_r2_storage(file_size: int) -> bool:
    """Determine if a video should be stored in R2 instead of direct upload"""
    return file_size > get_video_size_limit()

# Backup cleanup function for large videos
def cleanup_old_videos(days_old: int = 30) -> None:
    """Clean up old videos from R2 bucket (optional maintenance function)"""
    if not R2_VIDEO_BUCKET:
        return
        
    client = r2_client()
    if not client:
        return
        
    try:
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        # List objects in videos/ folder
        response = client.list_objects_v2(Bucket=R2_VIDEO_BUCKET, Prefix='videos/')
        
        if 'Contents' not in response:
            return
            
        deleted_count = 0
        for obj in response['Contents']:
            if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                client.delete_object(Bucket=R2_VIDEO_BUCKET, Key=obj['Key'])
                deleted_count += 1
                
        if deleted_count > 0:
            print(f"🧹 Cleaned up {deleted_count} old videos from R2")
            
    except Exception as e:
        print(f"⚠️ Error during video cleanup: {e}")


def build_public_url_for_key(key: str) -> str:
    """Return the public URL that would be used for a given object key.

    Useful for runtime testing without performing an upload.
    """
    # Prefer runtime env
    r2_public_env = os.getenv('R2_PUBLIC_URL')
    if r2_public_env:
        return f"{r2_public_env.rstrip('/')}/{key}"
    if R2_PUBLIC_URL:
        return f"{R2_PUBLIC_URL.rstrip('/')}/{key}"
    return f"https://{R2_VIDEO_BUCKET}.r2.cloudflarestorage.com/{key}"


# --- Startup debug (masked) to help confirm which public URL will be used ---
def _mask_url(u: Optional[str]) -> str:
    if not u:
        return "(not set)"
    try:
        # keep scheme and first/last fragments
        if len(u) <= 40:
            return u
        return u[:28] + '...' + u[-10:]
    except Exception:
        return '(invalid)'

try:
    masked = _mask_url(R2_PUBLIC_URL)
    print(f"🔎 R2_PUBLIC_URL (masked): {masked}")
except Exception:
    pass
