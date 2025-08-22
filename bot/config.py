# bot/config.py
import os
from pathlib import Path

# --- REVISED: Path Configuration ---
# Check if we are running in the Railway environment by looking for the volume.
# If so, use the persistent /data directory. Otherwise, use the local directory.
if Path("/data").exists():
    BASE_DIR = Path("/data")
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

# Prefer dashboard/data structure, fallback to root
def _get_data_path(filename):
    """Get path for data files, preferring dashboard/data/ structure"""
    dashboard_path = BASE_DIR / "dashboard" / "data" / filename
    root_path = BASE_DIR / filename
    
    # If dashboard version exists, use it; otherwise use root (for backward compatibility)
    if dashboard_path.exists():
        return dashboard_path
    return root_path

FEED_LIST = _get_data_path("feeds.txt")  # Try dashboard/data/feeds.txt first

# Optional: if FEEDS_R2_BUCKET is configured, attempt to download feeds.txt from R2 at startup
def _maybe_fetch_feeds_from_r2():
    import os
    from pathlib import Path
    # Prefer canonical R2_BUCKET, then FEEDS_R2_BUCKET, then SEEN_R2_BUCKET.
    # This keeps backward-compatibility while making R2_BUCKET the primary name.
    bucket = os.getenv('R2_BUCKET') or os.getenv('FEEDS_R2_BUCKET') or os.getenv('SEEN_R2_BUCKET')
    access_key = os.getenv('R2_ACCESS_KEY_ID')
    secret = os.getenv('R2_SECRET_ACCESS_KEY')
    endpoint = os.getenv('R2_ENDPOINT')
    if not bucket or not access_key or not secret:
        return
    try:
        # Lazy-import boto3 to avoid requiring it unless configured
        import boto3
        s3 = boto3.client('s3', aws_access_key_id=access_key, aws_secret_access_key=secret, endpoint_url=endpoint)
        target = _get_data_path("feeds.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Try dashboard/data/feeds.txt first, fallback to feeds.txt
        for key in ['dashboard/data/feeds.txt', 'feeds.txt']:
            try:
                with open(target, 'wb') as f:
                    s3.download_fileobj(bucket, key, f)
                print(f'Downloaded {key} from R2')
                break
            except Exception as e:
                print(f'Could not download {key} from R2: {e}')
                continue
    except Exception as e:
        # Surface download error to CI logs so we can debug missing feeds.txt
        try:
            print('Could not download feeds.txt from R2:', e)
        except Exception:
            pass
        return

# Try to fetch feeds from R2 on import
_maybe_fetch_feeds_from_r2()
SEEN_DB   = _get_data_path("seen.json")  # Try dashboard/data/seen.json first

# Optional R2/S3 bucket for persisting runtime state (seen.json)
SEEN_R2_BUCKET = os.getenv('SEEN_R2_BUCKET') or os.getenv('FEEDS_R2_BUCKET') or os.getenv('R2_BUCKET')

def r2_client():
    """Return a boto3 S3-compatible client if R2 envs are set, else None."""
    bucket = SEEN_R2_BUCKET
    access_key = os.getenv('R2_ACCESS_KEY_ID') or os.getenv('R2_ACCESS_KEY')
    secret = os.getenv('R2_SECRET_ACCESS_KEY') or os.getenv('R2_SECRET')
    endpoint = os.getenv('R2_ENDPOINT')
    if not bucket or not access_key or not secret:
        return None
    try:
        import boto3
        s3 = boto3.client('s3', aws_access_key_id=access_key, aws_secret_access_key=secret, endpoint_url=endpoint)
        return s3
    except Exception as e:
        try:
            print('r2_client error:', e)
        except Exception:
            pass
        return None

# ── Discord text limits & reactions ──────────────────────────────────────
MAX_BODY = 2_000                            # hard limit per message
EMOJIS   = ["👍", "❤️", "😆", "😲", "😢", "😡"]
# Global fallback channel ID for unmapped feeds; set via env var GLOBAL_FALLBACK_CHANNEL_ID or leave unset
_fallback = os.getenv("GLOBAL_FALLBACK_CHANNEL_ID")
GLOBAL_FALLBACK_CHANNEL_ID = int(_fallback) if _fallback is not None else None
