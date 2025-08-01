import html
import time
import re
import datetime as dt
import feedparser
import calendar  # <-- Required for the fix
from itertools import chain
from bs4 import BeautifulSoup
from bot.config import FEED_LIST

def _get_cleaned_text(entry: dict) -> str:
    """Extracts and cleans the text content from a post's summary."""
    html_content = entry.get('summary', '')
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    fetchrss_pattern = re.compile("Feed generated with.*?FetchRSS", re.IGNORECASE | re.DOTALL)
    footer_tag = soup.find(lambda tag: not isinstance(tag, str) and fetchrss_pattern.search(tag.get_text()))
    if footer_tag:
        footer_tag.decompose()
    for br in soup.find_all('br'):
        br.replace_with('\n')
    text = soup.get_text(strip=True)
    return text

def _media_list(e: dict) -> list[str]:
    """Return all image/video URLs from a feed entry."""
    media_urls: list[str] = []
    # Get media from the standard media:content tag
    for m in e.get("media_content", []):
        if m.get("url") and m.get("url") not in media_urls:
            media_urls.append(m.get("url"))
    
    # Scrape any <img> tags from the description
    desc_html = e.get("description", "") or e.get("summary", "") or ""
    for url in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', desc_html):
        url = html.unescape(url)
        if url and url not in media_urls:
            media_urls.append(url)

    # Add the main post link if it appears to be a video page
    if "/videos/" in e.link and e.link not in media_urls:
        media_urls.append(e.link)
        
    return media_urls

def _dt(t: time.struct_time) -> dt.datetime | None:
    """
    Correctly converts a naive time.struct_time from feedparser (assumed to be UTC)
    into a timezone-aware datetime object.
    """
    if not t:
        return None
    
    # --- CORRECTED LOGIC ---
    # `calendar.timegm` correctly treats the input struct_time as UTC and converts
    # it to a proper timestamp, avoiding local system timezone interference.
    utc_timestamp = calendar.timegm(t)
    return dt.datetime.fromtimestamp(utc_timestamp, tz=dt.timezone.utc)
    # --- END CORRECTION ---

def _strip_fb(text: str) -> str:
    """Removes 'on Facebook' from page titles."""
    return text.replace("on Facebook", "").strip(" -–—").strip()

def _clean_title(t: str, page: str) -> str:
    """Cleans up post titles."""
    title = html.unescape(t).strip()
    lower_title = title.lower()
    if lower_title == page.lower():
        return ""
    if lower_title.startswith("photos from") or lower_title == "timeline photos":
        return ""
    return title

def iter_entries():
    """Iterates through all entries from all feeds in feeds.txt."""
    total = 0
    if not FEED_LIST.exists():
        print("Error: feeds.txt not found!")
        return
    for url in FEED_LIST.read_text().splitlines():
        if not url.strip(): continue
        try:
            feed = feedparser.parse(url)
            if feed.bozo:
                print(f"⚠️ Warning: Malformed feed at {url}. Reason: {feed.bozo_exception}")
                continue
        except Exception as e:
            print(f"🚨 Error: Could not fetch or parse feed at {url}. Reason: {e}")
            continue
        page  = _strip_fb(feed.feed.get("title", ""))
        about = _strip_fb(feed.feed.get("description", ""))
        for e in feed.entries:
            total += 1
            yield {
                "guid":       e.get("id") or e.link,
                "page_name":  page,
                "title":      _clean_title(e.get("title", ""), page),
                "link":       e.link,
                "raw":        _get_cleaned_text(e),
                "media_all":  _media_list(e),
                "published":  _dt(e.get("published_parsed")), # This now uses the corrected _dt function
                "about":      about,
                "feed":       url,
            }
    print(f"Parsed {total} entries from {len(list(FEED_LIST.read_text().splitlines()))} feeds")
