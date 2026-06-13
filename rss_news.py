from __future__ import annotations
from datetime import datetime
from urllib.parse import quote_plus
import feedparser


def _entry_date(entry) -> str:
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6]).isoformat(timespec="seconds")
    if getattr(entry, "updated_parsed", None):
        return datetime(*entry.updated_parsed[:6]).isoformat(timespec="seconds")
    return datetime.now().isoformat(timespec="seconds")


def collect_rss_feeds(feed_urls: list[str], max_per_feed: int = 25) -> list[dict]:
    rows: list[dict] = []
    for feed_url in feed_urls:
        feed = feedparser.parse(feed_url)
        source_title = getattr(feed.feed, "title", "RSS feed") if getattr(feed, "feed", None) else "RSS feed"
        for entry in feed.entries[:max_per_feed]:
            title = getattr(entry, "title", "Untitled")
            summary = getattr(entry, "summary", "")
            link = getattr(entry, "link", "")
            rows.append({
                "date": _entry_date(entry),
                "source": source_title,
                "source_type": "news",
                "title": title,
                "text": f"{title}\n{summary}",
                "url": link,
            })
    return rows


def collect_google_news(project_terms: list[str], max_results: int = 20) -> list[dict]:
    # No API key required. Works well for a simple MVP.
    query = quote_plus(' OR '.join([f'"{t}"' for t in project_terms if t]))
    feed_url = f"https://news.google.com/rss/search?q={query}&hl=en-CA&gl=CA&ceid=CA:en"
    return collect_rss_feeds([feed_url], max_per_feed=max_results)
