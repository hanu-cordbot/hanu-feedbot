# Script to check feed_map.json against feeds discovered by bot.parser.iter_entries()
import json, os
from pathlib import Path
BASE_DIR = Path('.')
feed_map_path = BASE_DIR / 'feed_map.json'
if not feed_map_path.exists():
    print('feed_map.json not found')
    raise SystemExit(1)
with open(feed_map_path, 'r', encoding='utf-8') as f:
    user_map = json.load(f)
print(f'Loaded feed_map.json with {len(user_map)} keys')
try:
    from bot.parser import iter_entries
except Exception as e:
    print('Failed to import iter_entries:', e)
    raise
feeds = set()
for e in iter_entries():
    feeds.add(e['feed'])
print(f'Found {len(feeds)} distinct feeds from feeds.txt')
# Show which mapping keys are present in feeds
present = [k for k in user_map.keys() if k in feeds]
missing = [k for k in user_map.keys() if k not in feeds]
print(f'Mapped keys present in feeds.txt: {len(present)}')
if present:
    print(' Sample present keys:')
    for k in present[:5]:
        print('  ', k, '->', user_map[k])
print(f'Mapped keys missing from feeds.txt: {len(missing)}')
if missing:
    print(' Sample missing keys:')
    for k in missing[:10]:
        print('  ', repr(k), '->', user_map[k])
# Also show a few feeds that are not mapped
unmapped_feeds = [f for f in sorted(feeds) if f not in user_map]
print(f'Feeds without mappings: {len(unmapped_feeds)}')
for f in unmapped_feeds[:10]:
    print('  ', f)
print('\nDone')
