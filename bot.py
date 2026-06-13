from __future__ import annotations

import csv
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import requests
import yaml
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
MENTIONS_CSV = DATA_DIR / "mentions.csv"
PROJECTS_YAML = ROOT / "projects.yaml"

CRITICISM_TERMS = [
    "opposition", "concerns", "petition", "protest", "lawsuit", "residents",
    "council", "environmental concerns", "Indigenous consultation", "property values",
    "wetland", "trees", "noise", "traffic", "health", "route", "construction"
]

FIELDNAMES = [
    "mention_id", "collected_at", "published", "project_id", "project_name", "source_type",
    "source", "title", "summary", "url", "query", "sentiment", "sentiment_score",
    "issues", "risk_level", "risk_score", "new_item"
]


def load_projects() -> list[dict]:
    with open(PROJECTS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("projects", [])


def clean_text(value: str | None) -> str:
    value = value or ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def make_id(project_id: str, url: str, title: str) -> str:
    base = f"{project_id}|{url}|{title}".lower().encode("utf-8", errors="ignore")
    return hashlib.sha256(base).hexdigest()[:16]


def existing_ids() -> set[str]:
    if not MENTIONS_CSV.exists():
        return set()
    with open(MENTIONS_CSV, "r", encoding="utf-8", newline="") as f:
        return {row.get("mention_id", "") for row in csv.DictReader(f)}


def append_mentions(rows: list[dict]) -> int:
    existing = existing_ids()
    new_rows = []
    for row in rows:
        if row["mention_id"] not in existing:
            row["new_item"] = "yes"
            new_rows.append(row)
            existing.add(row["mention_id"])
    if not new_rows:
        return 0
    file_exists = MENTIONS_CSV.exists()
    with open(MENTIONS_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)
    return len(new_rows)


def classify(project: dict, title: str, summary: str, source: str) -> tuple[str, float, str, str, int]:
    text = f"{title} {summary}".lower()
    analyzer = SentimentIntensityAnalyzer()
    score = analyzer.polarity_scores(text)["compound"]
    if score <= -0.15:
        sentiment = "Negative"
    elif score >= 0.15:
        sentiment = "Positive"
    else:
        sentiment = "Neutral"

    issues = []
    for kw in project.get("issue_keywords", []):
        if kw.lower() in text:
            issues.append(kw)
    for kw in CRITICISM_TERMS:
        if kw.lower() in text and kw not in issues:
            issues.append(kw)
    if not issues:
        issues = ["General"]

    risk_score = 10
    if sentiment == "Negative":
        risk_score += 30
    elif sentiment == "Neutral":
        risk_score += 10

    issue_text = " ".join(issues).lower()
    high_terms = ["petition", "protest", "lawsuit", "indigenous", "wetland", "health", "property", "council", "erosion"]
    risk_score += sum(8 for t in high_terms if t in issue_text)

    if source.lower() in ["google news", "rss feed"]:
        risk_score += 10

    risk_score = min(100, risk_score)
    if risk_score >= 75:
        level = "Critical"
    elif risk_score >= 50:
        level = "High"
    elif risk_score >= 25:
        level = "Medium"
    else:
        level = "Low"
    return sentiment, round(score, 3), "; ".join(issues), level, risk_score


def google_news_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-CA&gl=CA&ceid=CA:en"


def fetch_rss(url: str, timeout: int = 20):
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "PortfolioRiskRadar/1.0"})
        resp.raise_for_status()
        return feedparser.parse(resp.text).entries
    except Exception as e:
        print(f"RSS fetch failed: {url} | {e}")
        return []


def build_queries(project: dict) -> list[str]:
    names = [project.get("name", "")] + project.get("aliases", [])
    queries = []
    for name in names:
        if not name:
            continue
        queries.append(f'"{name}"')
        for term in ["opposition", "concerns", "petition", "council", "environmental", "residents"]:
            queries.append(f'"{name}" {term}')
    return queries[:20]


def collect_for_project(project: dict) -> list[dict]:
    rows = []
    now = datetime.now(timezone.utc).isoformat()

    for query in build_queries(project):
        entries = fetch_rss(google_news_url(query))
        for entry in entries[:10]:
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", ""))
            url = getattr(entry, "link", "")
            published = clean_text(getattr(entry, "published", ""))
            sentiment, s_score, issues, risk_level, risk_score = classify(project, title, summary, "Google News")
            rows.append({
                "mention_id": make_id(project["id"], url, title),
                "collected_at": now,
                "published": published,
                "project_id": project["id"],
                "project_name": project["name"],
                "source_type": "News",
                "source": "Google News",
                "title": title,
                "summary": summary,
                "url": url,
                "query": query,
                "sentiment": sentiment,
                "sentiment_score": s_score,
                "issues": issues,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "new_item": "yes",
            })

    for url in project.get("source_urls", []) or []:
        entries = fetch_rss(url)
        for entry in entries[:20]:
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            published = clean_text(getattr(entry, "published", ""))
            sentiment, s_score, issues, risk_level, risk_score = classify(project, title, summary, "RSS Feed")
            rows.append({
                "mention_id": make_id(project["id"], link, title),
                "collected_at": now,
                "published": published,
                "project_id": project["id"],
                "project_name": project["name"],
                "source_type": "RSS",
                "source": "RSS Feed",
                "title": title,
                "summary": summary,
                "url": link,
                "query": url,
                "sentiment": sentiment,
                "sentiment_score": s_score,
                "issues": issues,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "new_item": "yes",
            })
    return rows


def main():
    projects = load_projects()
    all_rows = []
    for project in projects:
        print(f"Scanning: {project.get('name')}")
        all_rows.extend(collect_for_project(project))
    added = append_mentions(all_rows)
    print(f"Collected {len(all_rows)} possible mentions. Added {added} new mentions.")


if __name__ == "__main__":
    main()
