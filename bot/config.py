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

FEED_LIST = Path(__file__).resolve().parent.parent / "feeds.txt" # Feeds should still be read from the repo
SEEN_DB   = BASE_DIR / "seen.json"          # This will now be /data/seen.json on Railway

# ── Discord text limits & reactions ──────────────────────────────────────
MAX_BODY = 2_000                            # hard limit per message
EMOJIS   = ["👍", "❤️", "😆", "😲", "😢", "😡"]
# Global fallback channel ID for unmapped feeds; set via env var GLOBAL_FALLBACK_CHANNEL_ID or leave unset
_fallback = os.getenv("GLOBAL_FALLBACK_CHANNEL_ID")
GLOBAL_FALLBACK_CHANNEL_ID = int(_fallback) if _fallback is not None else None
