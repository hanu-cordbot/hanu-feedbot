"""
fetch_channel_names.py

Reads feed_map.json for channel IDs and queries Discord's API (v10) for channel names and types.
Writes channels.json with an array of { id, name, type }.

Usage:
  export DISCORD_BOT_TOKEN="<token>"
  python fetch_channel_names.py

This script is safe to run in CI when DISCORD_BOT_TOKEN is provided via GitHub Secrets.
"""
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DISCORD_API = "https://discord.com/api/v10/channels/"
TOKEN = os.environ.get('DISCORD_BOT_TOKEN')

def load_feed_map(path='feed_map.json'):
    if not os.path.exists(path):
        return {}
    try:
        return json.load(open(path, 'r', encoding='utf-8'))
    except Exception as e:
        print(f"Failed to load {path}: {e}")
        return {}

def is_id_like(s):
    try:
        return str(int(str(s))) == str(s)
    except Exception:
        return False

def fetch_channel_info(cid):
    url = DISCORD_API + str(cid)
    req = Request(url)
    req.add_header('Authorization', f'Bot {TOKEN}')
    req.add_header('User-Agent', 'hanu-feedbot/ci-fetch-channel-names')
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.load(resp)
            return data
    except HTTPError as e:
        print(f"HTTPError fetching {cid}: {e.code} {e.reason}")
    except URLError as e:
        print(f"URLError fetching {cid}: {e}")
    except Exception as e:
        print(f"Error fetching {cid}: {e}")
    return None

TYPE_MAP = {
    0: 'text',
    5: 'announcement',
    13: 'stage',
    15: 'forum',
    2: 'voice',
}

if __name__ == '__main__':
    if not TOKEN:
        print('DISCORD_BOT_TOKEN not set; exiting (no changes).')
        sys.exit(0)

    feed_map = load_feed_map('feed_map.json')
    candidates = set()
    for v in feed_map.values():
        if isinstance(v, list):
            for item in v:
                if is_id_like(item): candidates.add(str(item))
        else:
            if v is None: continue
            if is_id_like(v): candidates.add(str(v))

    if not candidates:
        print('No numeric channel IDs found in feed_map.json; nothing to fetch.')
        sys.exit(0)

    channels = []
    for cid in sorted(candidates):
        print(f'Fetching channel {cid}...')
        info = fetch_channel_info(cid)
        if info:
            ch_type = TYPE_MAP.get(info.get('type'), 'text')
            channels.append({
                'id': str(info.get('id')),
                'name': info.get('name') or f'channel-{str(info.get("id"))[-4:]}',
                'type': ch_type
            })

    if channels:
        out = 'channels.json'
        try:
            json.dump(channels, open(out, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
            print(f'Wrote {len(channels)} channels to {out}')
        except Exception as e:
            print('Failed writing channels.json:', e)
            sys.exit(2)
    else:
        print('No channel info fetched.')
    
