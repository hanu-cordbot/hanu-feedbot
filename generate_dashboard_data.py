#!/usr/bin/env python3
"""
Generate dashboard data for GitHub Pages deployment.
Creates stats, feeds, and meta JSON files for the web dashboard.
"""
import os
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import feedparser
from collections import defaultdict

def load_json_file(filepath, default=None):
    """Load JSON file with fallback to default value"""
    if default is None:
        default = {}
    
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading {filepath}: {e}")
    
    return default

def save_json_file(filepath, data):
    """Save data to JSON file"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved {filepath}")
    except Exception as e:
        print(f"❌ Error saving {filepath}: {e}")

def generate_stats():
    """Generate comprehensive stats for the dashboard"""
    print("📊 Generating stats...")
    
    # Load existing data
    seen_data = load_json_file('seen.json', {})
    feed_meta = load_json_file('feed_meta.json', {})
    feed_map = load_json_file('dashboard/data/feed_map.json', {})
    channels = load_json_file('channels.json', [])
    
    # Load feeds list
    feeds = []
    if os.path.exists('feeds.txt'):
        with open('feeds.txt', 'r') as f:
            feeds = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    # Calculate stats
    now = datetime.now(timezone.utc)
    stats = {
        'last_updated': now.isoformat(),
        'total_feeds': len(feeds),
        'total_channels': len(channels),
        'total_seen_items': len(seen_data),
        'feeds_with_metadata': len(feed_meta),
        'feed_mappings': len(feed_map),
        'recent_activity': [],
        'feed_health': {},
        'hourly_stats': defaultdict(int),
        'daily_stats': defaultdict(int)
    }
    
    # Analyze seen items for recent activity
    recent_cutoff = now - timedelta(hours=24)
    recent_items = 0
    
    # Handle both list and dict formats for seen_data
    if isinstance(seen_data, list):
        # Legacy format - just count items
        stats['recent_items_24h'] = 0  # Can't determine timing from list format
    else:
        # New format with timestamps
        for item_id, item_data in seen_data.items():
            try:
                if isinstance(item_data, dict) and 'timestamp' in item_data:
                    timestamp = datetime.fromisoformat(item_data['timestamp'].replace('Z', '+00:00'))
                    if timestamp > recent_cutoff:
                        recent_items += 1
                        
                        # Add to hourly/daily stats
                        hour_key = timestamp.strftime('%Y-%m-%d %H:00')
                        day_key = timestamp.strftime('%Y-%m-%d')
                        stats['hourly_stats'][hour_key] += 1
                        stats['daily_stats'][day_key] += 1
            except Exception as e:
                continue
        
        stats['recent_items_24h'] = recent_items
    
    # Convert defaultdicts to regular dicts for JSON serialization
    stats['hourly_stats'] = dict(stats['hourly_stats'])
    stats['daily_stats'] = dict(stats['daily_stats'])
    
    # Analyze feed health
    for feed_url in feeds:
        try:
            # Check if feed has metadata
            has_meta = feed_url in feed_meta
            
            # Get live feed data for current entry count
            print(f"  Checking feed: {feed_url[:60]}...")
            import feedparser
            feed = feedparser.parse(feed_url)
            current_entry_count = len(feed.entries) if not feed.bozo else 0
            
            # Quick feed check
            feed_check = {
                'url': feed_url,
                'has_metadata': has_meta,
                'last_check': now.isoformat(),
                'status': 'unknown',
                'entry_count': current_entry_count
            }
            
            if has_meta:
                meta = feed_meta[feed_url]
                feed_check['title'] = meta.get('title', 'Unknown')
                feed_check['description'] = meta.get('description', '')
                feed_check['last_post'] = meta.get('last_post')
                # If metadata contains a page URL, propagate it here
                if 'page_url' in meta:
                    feed_check['page_url'] = meta.get('page_url')
                elif 'page' in meta:
                    feed_check['page_url'] = meta.get('page')
                elif 'pageUrl' in meta:
                    feed_check['page_url'] = meta.get('pageUrl')
                
            # Determine status based on current data
            if feed.bozo:
                feed_check['status'] = 'error'
                feed_check['error'] = str(feed.bozo_exception) if hasattr(feed, 'bozo_exception') else 'Parse error'
            elif current_entry_count > 0:
                feed_check['status'] = 'healthy'
            else:
                feed_check['status'] = 'no_entries'
            
            # If we don't have metadata title, get it from the feed
            if not has_meta or not feed_check.get('title'):
                try:
                    feed_check['title'] = getattr(feed.feed, 'title', 'Unknown Feed')
                    feed_check['description'] = getattr(feed.feed, 'description', '')
                    # Try to capture the canonical page URL from the feed (often feed.feed.link)
                    page_link = getattr(feed.feed, 'link', None)
                    if page_link:
                        feed_check.setdefault('page_url', page_link)
                except Exception:
                    feed_check['title'] = 'Unknown Feed'
                    feed_check['description'] = ''

            # Attach any channel mapping we know from feed_map (may be id or name)
            try:
                channel_map = feed_map.get(feed_url)
                if channel_map:
                    feed_check['channel'] = channel_map
            except Exception:
                pass
            
            stats['feed_health'][feed_url] = feed_check
            
        except Exception as e:
            print(f"    Error checking feed {feed_url}: {e}")
            stats['feed_health'][feed_url] = {
                'url': feed_url,
                'status': 'error',
                'error': str(e),
                'last_check': now.isoformat(),
                'entry_count': 0
            }
    
    return stats

def generate_feeds_data(stats=None):
    """Generate feeds data for the dashboard"""
    print("📡 Generating feeds data...")
    
    feed_meta = load_json_file('feed_meta.json', {})
    feed_map = load_json_file('dashboard/data/feed_map.json', {})
    
    feeds_data = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'feeds': [],
        'mappings': feed_map
    }
    
    # Load feeds list
    feeds = []
    if os.path.exists('feeds.txt'):
        with open('feeds.txt', 'r') as f:
            feeds = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    for feed_url in feeds:
        # Build canonical feed object with fallbacks from stats and feed_meta
        feed_info = {
            'url': feed_url,
            'title': 'Unknown Feed',
            'description': '',
            'entry_count': 0,
            # canonical last_post field (prefer stats.feed_health > feed_meta)
            'last_post': None,
            'last_updated': None,
            'has_metadata': feed_url in feed_meta,
            # optional channel mapping (feed_map), may be id or name
            'channel': feed_map.get(feed_url)
        }
        
        # Merge feed_meta values if present
        if feed_url in feed_meta:
            meta = feed_meta[feed_url]
            feed_info.update({
                'title': meta.get('title', 'Unknown Feed'),
                'description': meta.get('description', ''),
                'entry_count': meta.get('entry_count', 0),
                'last_updated': meta.get('last_updated'),
                # prefer explicit page_url from metadata
                'page_url': meta.get('page_url') or meta.get('pageUrl') or meta.get('page')
            })

        # If stats were provided, prefer last_post from stats.feed_health
        try:
            if stats and isinstance(stats, dict):
                fh = stats.get('feed_health', {})
                stat_entry = fh.get(feed_url) if fh else None
                if stat_entry:
                    # prefer last_post from stats health
                    lp = stat_entry.get('last_post') or stat_entry.get('lastPost') or stat_entry.get('last_post')
                    if lp:
                        feed_info['last_post'] = lp
                    # if page_url missing, try title/url from stats entry
                    if not feed_info.get('page_url'):
                        feed_info['page_url'] = stat_entry.get('page_url') or stat_entry.get('page')
                    # merge entry_count if available
                    if 'entry_count' in stat_entry and (not feed_info.get('entry_count')):
                        feed_info['entry_count'] = stat_entry.get('entry_count')
        except Exception:
            pass
        
        feeds_data['feeds'].append(feed_info)
    
    return feeds_data

def generate_meta_data():
    """Generate metadata for the dashboard"""
    print("🔍 Generating meta data...")
    
    channels = load_json_file('channels.json', [])
    groups = load_json_file('groups.json', {})
    system_prompt = load_json_file('system_prompt.json', {})
    
    meta_data = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'version': '1.0.0',
        'channels': channels,
        'groups': groups,
        'system_prompt': system_prompt,
        'configuration': {
            'max_age_hours': os.getenv('MAX_AGE_HOURS', '36'),
            'fallback_enabled': os.getenv('FALLBACK_ENABLED', 'true'),
            'has_discord_token': bool(os.getenv('DISCORD_BOT_TOKEN')),
            'has_gemini_key': bool(os.getenv('GEMINI_API_KEY')),
            'has_webhook': bool(os.getenv('DISCORD_WEBHOOK_URL')),
            'channel_id': os.getenv('CHANNEL_ID'),
            'summary_channel_id': os.getenv('SUMMARY_CHANNEL_ID')
        }
    }
    
    return meta_data

def main():
    """Generate all dashboard data files"""
    print("🚀 Generating dashboard data...")
    print("=" * 50)
    
    # Ensure docs/data directory exists
    os.makedirs('docs/data', exist_ok=True)
    
    try:
        # Generate stats
        stats = generate_stats()
        save_json_file('docs/data/stats.json', {'stats': stats})

        # Generate feeds data (pass stats so feeds can inherit canonical fields)
        feeds_data = generate_feeds_data(stats=stats)
        save_json_file('docs/data/feeds.json', feeds_data)

        # Generate meta data
        meta_data = generate_meta_data()
        save_json_file('docs/data/meta.json', meta_data)

        # Ensure the authoritative feed_map is published into docs/data so it gets uploaded
        # to R2 under the dashboard prefix (dashboard/data/feed_map.json).
        try:
            feed_map_root = load_json_file('dashboard/data/feed_map.json', {})
            # Enrich the feed_map for dashboard consumption with channel name/type
            # without changing the root dashboard/data/feed_map.json (which other components may rely on).
            channels = load_json_file('channels.json', [])
            # Build lookup by id
            channels_by_id = {str(ch.get('id')): {'id': str(ch.get('id')), 'name': ch.get('name'), 'type': ch.get('type')} for ch in channels if ch.get('id')}

            def enrich_value(v):
                # If mapping is a list of ids/names, enrich each item
                if isinstance(v, list):
                    out = []
                    for item in v:
                        sid = str(item) if item is not None else None
                        if sid and sid in channels_by_id:
                            out.append(channels_by_id[sid])
                        else:
                            out.append(item)
                    return out
                # If mapping is a single id-like value, try to enrich
                sid = str(v) if v is not None else None
                if sid and sid in channels_by_id:
                    return channels_by_id[sid]
                return v

            enriched = {}
            for k, v in feed_map_root.items():
                try:
                    enriched[k] = enrich_value(v)
                except Exception:
                    enriched[k] = v

            save_json_file('docs/data/feed_map.json', enriched)
        except Exception as e:
            print('❌ Failed to write docs/data/feed_map.json:', e)

        print("\n✅ Dashboard data generation completed!")
        print(f"📊 Generated stats for {stats['total_feeds']} feeds")
        print(f"📡 Processed {len(feeds_data['feeds'])} feed entries")
        print(f"🔍 Configured {len(meta_data['channels'])} channels")

    except Exception as e:
        print(f"❌ Error generating dashboard data: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
