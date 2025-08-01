# === FILE: bot/avatar_cache.py ===

import os
import json

# --- REVISED: More robust path handling for Railway's persistent volume ---
if os.path.exists("/data"):
    BASE_DIR = "/data"
else:
    BASE_DIR = "." # Fallback for local development

CACHE_FILE = os.path.join(BASE_DIR, "avatar_cache.json")

# --- REVISED: Lazy initialization of the cache ---
def _load_cache():
    """Loads the avatar cache from disk, creating it if it doesn't exist."""
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # **FIX**: If the file doesn't exist or is empty, create it and return an empty dictionary.
        print(f"'{CACHE_FILE}' not found or invalid. Initializing a new one.")
        with open(CACHE_FILE, 'w') as f:
            json.dump({}, f)
        return {}

_cache = _load_cache()

def _save_cache():
    """Saves the current cache state to disk."""
    with open(CACHE_FILE, 'w') as f:
        json.dump(_cache, f)

def _slug(entry) -> str:
    return entry["link"].split("/")[3]

def avatar_for(entry) -> str:
    slug = _slug(entry)
    # The default URL is a fallback if no avatar is cached
    return _cache.get(slug, f"https://graph.facebook.com/{slug}/picture?type=large")

def maybe_update(entry) -> None:
    """
    Checks the media list for a profile picture or cover photo URL
    and updates the cache if one is found.
    """
    media_urls = entry.get("media_all", [])
    if not media_urls:
        return

    for url in media_urls:
        if "/profile_pictures/" in url or "/cover_photos/" in url:
            slug = _slug(entry)
            if _cache.get(slug) != url:
                _cache[slug] = url
                _save_cache()
                print(f"Avatar cache updated for '{slug}'.")
            break
