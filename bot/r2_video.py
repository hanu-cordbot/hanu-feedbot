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
from typing import Optional, Tuple, Any
from bot.config import r2_client, SEEN_R2_BUCKET

# R2 video storage configuration
# IMPORTANT: Use a dedicated public bucket for videos to avoid exposing private state.
R2_VIDEO_BUCKET = (
    os.getenv('R2_VIDEO_BUCKET')
    or os.getenv('R2_BUCKET')
    or os.getenv('FEEDS_R2_BUCKET')
)
# Prefer a dedicated public URL for the video bucket; fallback to generic R2_PUBLIC_URL
R2_VIDEO_PUBLIC_URL = os.getenv('R2_VIDEO_PUBLIC_URL') or os.getenv('R2_PUBLIC_URL')  # e.g., "https://videos.example.r2.dev"

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

def upload_video_to_r2(video_data: bytes, post_title: str, client: Any = None) -> Optional[str]:
    """Upload video to R2 bucket and return public URL."""
    if not R2_VIDEO_BUCKET:
        print("❌ R2 bucket not configured for video upload")
        return None
    # Allow caller to provide a prepared client so we reuse connections during async flows
    if callable(client):
        client = client()
    client = client or r2_client()
    if not client:
        print("❌ R2 client not available")
        return None
    try:
        # Generate unique filename
        filename = generate_video_filename(post_title)

        # Determine public base URL at call time (so runtime env is respected)
        r2_public_env = os.getenv('R2_VIDEO_PUBLIC_URL') or os.getenv('R2_PUBLIC_URL')
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
        # Require an explicit public base URL to be set in the runtime environment.
        # No fallback allowed because cloudflarestorage URLs don't embed reliably in Discord.
        if r2_public_env:
            public_url = f"{r2_public_env.rstrip('/')}/{filename}"
            print(f"ℹ️ Using R2_PUBLIC_URL from environment: {r2_public_env}")
        elif R2_VIDEO_PUBLIC_URL:
            public_url = f"{R2_VIDEO_PUBLIC_URL.rstrip('/')}/{filename}"
            print(f"ℹ️ Using R2_VIDEO_PUBLIC_URL from module config: {R2_VIDEO_PUBLIC_URL}")
        else:
            # Refuse to generate a cloudflarestorage fallback URL
            print('ERROR: No R2 public URL configured for videos; refusing fallback cloudflarestorage URL.')
            return None

        print(f"✅ Video uploaded to R2: {public_url}")
        return public_url
    except Exception as e:
        print(f"❌ Failed to upload video to R2: {e}")
        import traceback
        traceback.print_exc()
        return None

async def upload_video_to_r2_async(video_data: bytes, post_title: str, client: Any = None, bucket_name: Optional[str] = None) -> Optional[str]:
    """Async wrapper for R2 video upload with optional storage management."""
    prepared_client = client() if callable(client) else client
    if prepared_client and bucket_name:
        # Check storage before upload
        await check_and_cleanup_r2_storage(prepared_client, bucket_name)

    # Perform the upload using the same client instance when available
    return await asyncio.to_thread(upload_video_to_r2, video_data, post_title, prepared_client)

def create_video_embed_message(video_url: str, post_title: str, post_url: Optional[str] = None) -> str:
    """Return a Discord-friendly message with a bare video URL for auto-embed."""
    parts = []
    if post_title:
        parts.append(f"**{post_title.strip()}**")
    parts.append(video_url)
    if post_url:
        parts.append(f"Original: {post_url}")
    return "\n".join(parts)

def get_video_size_limit() -> int:
    """Get the size limit for direct Discord uploads (8MB)"""
    return 8 * 1024 * 1024  # 8MB in bytes

def should_use_r2_storage(file_size: int) -> bool:
    """Determine if a video should be stored in R2 instead of direct upload"""
    return file_size > get_video_size_limit()

async def check_and_cleanup_r2_storage(client: Any, bucket_name: str, max_storage_gb: float = 4.9):
    """Check R2 storage usage and delete old files if approaching limit."""
    max_storage_bytes = max_storage_gb * 1024 * 1024 * 1024  # Convert GB to bytes
    
    try:
        if not bucket_name:
            return
        if callable(client):
            client = client()
        if not client:
            print("⚠️ Skipping R2 storage check; client unavailable.")
            return

        # List all objects in bucket on a thread to avoid blocking the event loop
        def _collect_objects():
            paginator = client.get_paginator('list_objects_v2')
            collected = []
            for page in paginator.paginate(Bucket=bucket_name):
                if 'Contents' in page:
                    collected.extend(page['Contents'])
            return collected

        objects = await asyncio.to_thread(_collect_objects)
        
        if not objects:
            print(f"📊 R2 Storage: 0GB / {max_storage_gb}GB (0%)")
            return
            
        # Calculate total storage
        total_size = sum(obj['Size'] for obj in objects)
        usage_percent = (total_size / max_storage_bytes) * 100
        
        print(f"📊 R2 Storage: {total_size/1024/1024/1024:.2f}GB / {max_storage_gb}GB ({usage_percent:.1f}%)")
        
        if usage_percent >= 90:  # Start cleanup at 90% usage
            print("🧹 Starting R2 cleanup...")
            
            # Sort by last modified (oldest first)
            objects.sort(key=lambda x: x['LastModified'])
            
            # Delete oldest files until we're under 70%
            target_size = max_storage_bytes * 0.7
            deleted_count = 0
            deleted_size = 0
            
            for obj in objects:
                if total_size <= target_size:
                    break
                    
                try:
                    await asyncio.to_thread(
                        client.delete_object,
                        Bucket=bucket_name,
                        Key=obj['Key']
                    )
                    total_size -= obj['Size']
                    deleted_size += obj['Size']
                    deleted_count += 1
                    print(f"🗑️ Deleted: {obj['Key']} ({obj['Size']/1024/1024:.1f}MB)")
                except Exception as e:
                    print(f"❌ Failed to delete {obj['Key']}: {e}")
            
            print(f"✅ Cleanup complete: deleted {deleted_count} files ({deleted_size/1024/1024:.1f}MB)")
            
    except Exception as e:
        print(f"❌ Error checking R2 storage: {e}")

def build_public_url_for_key(key: str) -> str:
    """Return the public URL that would be used for a given object key.

    Useful for runtime testing without performing an upload.
    """
    # Prefer runtime env
    r2_public_env = os.getenv('R2_VIDEO_PUBLIC_URL') or os.getenv('R2_PUBLIC_URL')
    if r2_public_env:
        return f"{r2_public_env.rstrip('/')}/{key}"
    if R2_VIDEO_PUBLIC_URL:
        return f"{R2_VIDEO_PUBLIC_URL.rstrip('/')}/{key}"
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
    masked = _mask_url(R2_VIDEO_PUBLIC_URL)
    print(f"🔎 R2_VIDEO_PUBLIC_URL (masked): {masked}")
except Exception:
    pass
