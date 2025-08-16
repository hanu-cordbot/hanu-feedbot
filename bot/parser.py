import html
import time
import re
import datetime as dt
import feedparser
import calendar  # <-- Required for the fix
from itertools import chain
from bs4 import BeautifulSoup, NavigableString
from typing import Any, Dict
from bot.config import FEED_LIST

def _get_cleaned_text(entry: dict) -> str:
    """Extracts and cleans the text content from a post's summary."""
    html_content = entry.get('summary', '')
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    fetchrss_pattern = re.compile("Feed generated with.*?FetchRSS", re.IGNORECASE | re.DOTALL)
    # type: ignore allows callable filter
    footer_tag = soup.find(lambda tag: not isinstance(tag, str) and fetchrss_pattern.search(tag.get_text()))  # type: ignore
    if footer_tag:
        footer_tag.decompose()
    for br in soup.find_all('br'):
        # replace text node with NavigableString to satisfy type requirements
        br.replace_with(NavigableString('\n'))
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
    link = e.get('link', '')
    if "/videos/" in link and link not in media_urls:
        media_urls.append(link)
        
    return media_urls

def _dt(t: Any) -> dt.datetime | None:
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

def _clean_title(t: Any, page: str) -> str:
    """Cleans up post titles."""
    title = html.unescape(t).strip()
    lower_title = title.lower()
    if lower_title == page.lower():
        return ""
    if lower_title.startswith("photos from") or lower_title == "timeline photos":
        return ""
    return title

def iter_entries():
    """Iterates through all entries from all feeds in feeds.txt, with progress logs."""
    total = 0
    if not FEED_LIST.exists():
        print("Error: feeds.txt not found!")
        return
    # Load and display feeds to process
    feeds = [f.strip() for f in FEED_LIST.read_text().splitlines() if f.strip()]
    print(f"[IMPORT] [parser] Processing {len(feeds)} feeds in parallel")
    # Parallel feed parsing using ThreadPool
    import concurrent.futures
    from rich.progress import Progress
    from rich.console import Console
    max_workers = min(10, len(feeds))
    console = Console()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(feedparser.parse, url): url for url in feeds}
        # Show rich progress bar for parsing feeds
        with Progress("[cyan]Parsing feeds...", transient=True, console=console) as progress:
            task = progress.add_task("Parsing feeds", total=len(feeds))
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                progress.advance(task)
                try:
                    feed = future.result()
                    entries = feed.entries or []
                    print(f"   ? [parser] {url} -> {len(entries)} entries")
                except Exception as e:
                    print(f"[CRITICAL] Error parsing {url}: {e}")
                    continue
                # Extract feed metadata
                feed_info = feed.feed if isinstance(feed.feed, dict) else {}
                page = _strip_fb(feed_info.get("title", "") or "")
                about = _strip_fb(feed_info.get("description", "") or "")
                for entry in entries:
                    total += 1
                    yield {
                        "guid":      entry.get("id") or entry.get("link", ""),
                        "page_name": page,
                        "title":     _clean_title(entry.get("title", "") or "", page),
                        "link":      entry.get("link", ""),
                        "raw":       _get_cleaned_text(entry),
                        "media_all": _media_list(entry),
                        # type: ignore: published_parsed may vary
                        "published": _dt(entry.get("published_parsed")),
                        "about":     about,
                        "feed":      url,
                    }
    print(f"[OK] [parser] Completed: parsed total {total} entries from {len(feeds)} feeds")
