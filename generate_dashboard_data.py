#!/usr/bin/env python3
"""
Generate dashboard data for GitHub Pages deployment.
Creates stats, feeds, and meta JSON files for the web dashboard.
"""
import os
import json
import time
from datetime import datetime, timezone, timedelta
import datetime as dt
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
    # Prefer source folder where available
    seen_path_candidates = [
        'dashboard/data/source/seen.json',
        'dashboard/data/seen.json',
        'seen.json'
    ]
    seen_data = {}
    for cand in seen_path_candidates:
        seen_data = load_json_file(cand, {})
        if seen_data:
            break
    feed_meta = load_json_file('feed_meta.json', {})
    # Prefer authoritative configs from dashboard/data/source, with fallbacks for compatibility
    feed_map = (
        load_json_file('dashboard/data/source/feed_map.json', {}) or
        load_json_file('dashboard/data/feed_map.json', {})
    )
    channels = (
        load_json_file('dashboard/data/source/channels.json', []) or
        load_json_file('dashboard/data/channels.json', []) or
        load_json_file('channels.json', [])
    )
    
    # Load feeds list (prefer source folder)
    feeds = []
    for cand in ['dashboard/data/source/feeds.txt', 'dashboard/data/feeds.txt', 'feeds.txt']:
        if os.path.exists(cand):
            with open(cand, 'r', encoding='utf-8') as f:
                feeds = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            break
    
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

            # If last_post is still missing, try to infer from entries
            try:
                if not feed_check.get('last_post') and getattr(feed, 'entries', None):
                    def entry_ts(e):
                        for key in ('published_parsed','updated_parsed'):
                            t = getattr(e, key, None)
                            if t:
                                try:
                                    return dt.datetime(*t[:6], tzinfo=dt.timezone.utc)
                                except Exception:
                                    pass
                        for key in ('published','updated'):
                            v = getattr(e, key, None)
                            if v:
                                try:
                                    return dt.datetime.fromisoformat(v.replace('Z','+00:00'))
                                except Exception:
                                    pass
                        return None
                    dates = [entry_ts(e) for e in feed.entries]
                    dates = [d for d in dates if d]
                    if dates:
                        feed_check['last_post'] = max(dates).isoformat()
            except Exception:
                pass

            # Attach channel mapping and enrich with channel metadata
            try:
                channel_id = feed_map.get(feed_url)  # Now just a string ID
                if channel_id:
                    # Load channels data for enrichment
                    channels = (load_json_file('dashboard/data/channels.json', []) or (load_json_file('dashboard/data/channels.json', []) or load_json_file('channels.json', [])))
                    channel_info = next((ch for ch in channels if str(ch.get('id')) == str(channel_id)), None)
                    
                    if channel_info:
                        feed_check['channel'] = {
                            'id': str(channel_info.get('id')),
                            'name': channel_info.get('name', f'channel-{str(channel_id)[-4:]}'),
                            'type': channel_info.get('type', 'text')
                        }
                    else:
                        # Channel ID exists but no metadata - create minimal info
                        feed_check['channel'] = {
                            'id': str(channel_id),
                            'name': f'channel-{str(channel_id)[-4:]}',
                            'type': 'text'
                        }
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

def generate_meta_data():
    """Generate metadata for the dashboard"""
    print("🔍 Generating meta data...")
    
    channels = (
        load_json_file('dashboard/data/source/channels.json', []) or
        load_json_file('dashboard/data/channels.json', []) or
        load_json_file('channels.json', [])
    )
    # Prefer groups from source folder
    groups = (
        load_json_file('dashboard/data/source/groups.json', {}) or
        load_json_file('dashboard/data/groups.json', {}) or
        load_json_file('groups.json', {})
    )
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
        # Generate stats (now includes feed health with channel info)
        stats = generate_stats()
        save_json_file('docs/data/stats.json', {'stats': stats})

        # Generate meta data
        meta_data = generate_meta_data()
        save_json_file('docs/data/meta.json', meta_data)

        print("\n✅ Dashboard data generation completed!")
        print(f"📊 Generated stats for {stats['total_feeds']} feeds")
        print(f"📡 Processed {len(stats['feed_health'])} feed health entries")
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

