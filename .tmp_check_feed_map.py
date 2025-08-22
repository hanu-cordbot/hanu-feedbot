import json
from pathlib import Path
BASE_DIR = Path('.').resolve()
fm = BASE_DIR / 'feed_map.json'
print('cwd=', BASE_DIR)
print('feed_map exists?', fm.exists())
if fm.exists():
    with open(fm,'r',encoding='utf-8') as f:
        data = json.load(f)
    print('feed_map keys:', list(data.keys()))

import sys
sys.path.insert(0,str(BASE_DIR))
from bot.parser import iter_entries
feeds=set()
for e in iter_entries():
    feeds.add(e['feed'])
print('feeds count:', len(feeds))
print('sample feeds:', list(feeds)[:5])
