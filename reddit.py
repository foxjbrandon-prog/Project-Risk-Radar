from __future__ import annotations
from datetime import datetime
import requests


def collect_reddit_public(subreddits: list[str], search_terms: list[str], max_per_subreddit: int = 10) -> list[dict]:
    """Collect public Reddit search results without OAuth. May be rate limited by Reddit."""
    headers = {"User-Agent": "ProjectRiskRadar/0.1 by environmental-assessment-tool"}
    query = " OR ".join([f'"{t}"' for t in search_terms if t])
    rows: list[dict] = []
    for subreddit in subreddits:
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {"q": query, "restrict_sr": 1, "sort": "new", "limit": max_per_subreddit}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            created = post.get("created_utc")
            date = datetime.fromtimestamp(created).isoformat(timespec="seconds") if created else datetime.now().isoformat(timespec="seconds")
            title = post.get("title", "Untitled")
            text = f"{title}\n{post.get('selftext', '')}"
            permalink = post.get("permalink", "")
            rows.append({
                "date": date,
                "source": f"r/{subreddit}",
                "source_type": "reddit",
                "title": title,
                "text": text,
                "url": "https://www.reddit.com" + permalink if permalink else "",
            })
    return rows
