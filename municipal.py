from __future__ import annotations
from datetime import datetime
import feedparser


def collect_municipal_rss(feed_urls: list[str], max_per_feed: int = 25) -> list[dict]:
    rows = []
    for feed_url in feed_urls:
        feed = feedparser.parse(feed_url)
        source_title = getattr(feed.feed, "title", "Municipal feed") if getattr(feed, "feed", None) else "Municipal feed"
        for entry in feed.entries[:max_per_feed]:
            title = getattr(entry, "title", "Untitled")
            summary = getattr(entry, "summary", "")
            link = getattr(entry, "link", "")
            rows.append({
                "date": datetime.now().isoformat(timespec="seconds"),
                "source": source_title,
                "source_type": "municipal",
                "title": title,
                "text": f"{title}\n{summary}",
                "url": link,
            })
    return rows
