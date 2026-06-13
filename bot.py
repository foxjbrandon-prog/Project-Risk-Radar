from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus
import hashlib
import re

import feedparser
import pandas as pd
import requests
import yaml
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ROOT = Path(__file__).parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
MENTIONS_CSV = DATA / "mentions.csv"
SOCIAL_CSV = DATA / "social_risk_findings.csv"
PROJECTS_YAML = ROOT / "projects.yaml"
DATA.mkdir(exist_ok=True)
REPORTS.mkdir(exist_ok=True)

analyzer = SentimentIntensityAnalyzer()

OPPOSITION_TERMS = [
    "opposition", "oppose", "concerns", "concerned", "petition", "protest", "controversy",
    "lawsuit", "appeal", "delegation", "public meeting", "angry", "backlash", "residents oppose",
    "stop the", "save our", "not in my backyard", "NIMBY", "environmental concerns", "health concerns",
]

TRIGGER_TERMS = {
    "Tree clearing / vegetation loss": ["tree", "trees", "clearing", "vegetation", "woodlot", "forest"],
    "Wetlands / water / habitat": ["wetland", "watercourse", "lake", "shoreline", "habitat", "species", "wildlife", "fish"],
    "Property value / compensation": ["property value", "compensation", "expropriation", "buyout", "landowner", "easement"],
    "Visual impact / community character": ["visual", "views", "character", "aesthetic", "tower", "height", "landscape"],
    "Traffic / construction disruption": ["traffic", "construction", "truck", "road closure", "detour", "dust", "noise"],
    "Health / safety / EMF": ["health", "safety", "EMF", "electromagnetic", "risk", "unsafe"],
    "Indigenous consultation / rights": ["Indigenous", "First Nation", "Métis", "rights", "consultation", "treaty", "archaeology"],
    "Transparency / trust": ["transparency", "trust", "lack of consultation", "behind closed doors", "not consulted", "misleading"],
    "Growth pressure / cumulative effects": ["growth", "sprawl", "cumulative", "overdevelopment", "density", "development pressure"],
    "Cost / need / alternatives": ["cost", "need", "alternative", "route", "option", "why", "expensive"],
}

SOURCE_PATTERNS = {
    "Municipal / council": ["council", "agenda", "minutes", "committee", "municipal", "city", "township"],
    "Petition / campaign": ["petition", "change.org", "save our", "stop the"],
    "News / media": ["news", "article", "reported", "newspaper", "cbc", "ctv", "global"],
    "Regulatory / approval": ["environmental registry", "oeb", "iaac", "meep", "mecp", "approval", "class ea"],
    "Community / social": ["facebook", "reddit", "community", "residents", "neighbourhood"],
}


def load_projects() -> list[dict]:
    with open(PROJECTS_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("projects", [])


def stable_id(*parts: str) -> str:
    raw = "|".join([str(p) for p in parts])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def sentiment_label(text: str) -> tuple[str, float]:
    score = analyzer.polarity_scores(text).get("compound", 0.0)
    if score <= -0.25:
        return "Negative", score
    if score >= 0.25:
        return "Positive", score
    return "Neutral", score


def detect_triggers(text: str, issue_keywords: list[str] | None = None) -> list[str]:
    lower = text.lower()
    found = []
    for trigger, words in TRIGGER_TERMS.items():
        if any(w.lower() in lower for w in words):
            found.append(trigger)
    for kw in issue_keywords or []:
        if kw.lower() in lower and kw not in found:
            found.append(kw)
    return found or ["General project concern"]


def detect_source_type(title: str, link: str, summary: str) -> str:
    text = f"{title} {link} {summary}".lower()
    for source_type, words in SOURCE_PATTERNS.items():
        if any(w.lower() in text for w in words):
            return source_type
    return "Public web / unknown"


def risk_score(sentiment: str, triggers: list[str], title: str, summary: str, source_type: str) -> tuple[str, int]:
    text = f"{title} {summary}".lower()
    score = 10
    if sentiment == "Negative":
        score += 25
    elif sentiment == "Neutral":
        score += 8
    score += min(len(triggers) * 7, 35)
    if any(term.lower() in text for term in OPPOSITION_TERMS):
        score += 20
    if source_type in ["Municipal / council", "Petition / campaign", "Regulatory / approval"]:
        score += 12
    score = min(score, 100)
    if score >= 75:
        return "Critical", score
    if score >= 55:
        return "High", score
    if score >= 30:
        return "Medium", score
    return "Low", score


def google_news_url(query: str) -> str:
    return "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-CA&gl=CA&ceid=CA:en"


def read_feed(url: str, project: dict, mode: str) -> list[dict]:
    rows = []
    try:
        feed = feedparser.parse(url)
    except Exception:
        return rows
    for entry in feed.entries[:25]:
        title = clean_text(getattr(entry, "title", ""))
        link = clean_text(getattr(entry, "link", ""))
        summary = clean_text(getattr(entry, "summary", ""))
        published = clean_text(getattr(entry, "published", ""))
        text = f"{title} {summary}"
        sent, sent_score = sentiment_label(text)
        triggers = detect_triggers(text, project.get("issue_keywords", []))
        source_type = detect_source_type(title, link, summary)
        level, score = risk_score(sent, triggers, title, summary, source_type)
        rows.append({
            "id": stable_id(project.get("id", project.get("name", "project")), link, title, mode),
            "scan_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "project_id": project.get("id", ""),
            "project_name": project.get("name", ""),
            "mode": mode,
            "source_type": source_type,
            "title": title,
            "summary": summary,
            "url": link,
            "published": published,
            "sentiment": sent,
            "sentiment_score": sent_score,
            "triggers": "; ".join(triggers),
            "risk_level": level,
            "risk_score": score,
        })
    return rows


def live_queries(project: dict) -> list[str]:
    names = [project.get("name", "")] + project.get("aliases", [])
    issue_terms = ["opposition", "concerns", "petition", "council", "environmental concerns"]
    queries = []
    for name in names:
        if name:
            queries.append(f'"{name}"')
            for issue in issue_terms:
                queries.append(f'"{name}" {issue}')
    return queries[:15]


def social_risk_queries(project: dict) -> list[str]:
    locations = project.get("locations", [])
    similar = project.get("similar_project_types", []) or [project.get("type", "infrastructure")]
    triggers = ["opposition", "petition", "concerns", "controversy", "public meeting", "residents oppose"]
    queries = []
    for loc in locations:
        for ptype in similar[:6]:
            for trig in triggers[:4]:
                queries.append(f'"{loc}" "{ptype}" {trig}')
    for loc in locations[:6]:
        for topic in ["tree clearing", "wetland", "property values", "traffic", "visual impact", "Indigenous consultation"]:
            queries.append(f'"{loc}" "{topic}" opposition')
    return queries[:30]


def append_unique(csv_path: Path, rows: list[dict]) -> pd.DataFrame:
    new_df = pd.DataFrame(rows)
    if new_df.empty:
        return pd.DataFrame()
    if csv_path.exists():
        old = pd.read_csv(csv_path)
        combined = pd.concat([old, new_df], ignore_index=True)
    else:
        combined = new_df
    combined = combined.drop_duplicates(subset=["id"], keep="last")
    combined.to_csv(csv_path, index=False)
    return combined


def summarize_social_risk(project: dict, findings: pd.DataFrame) -> dict:
    project_findings = findings[findings["project_id"] == project.get("id", "")].copy() if not findings.empty else pd.DataFrame()
    if project_findings.empty:
        return {
            "project_id": project.get("id", ""),
            "project_name": project.get("name", ""),
            "assessment_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "finding_count": 0,
            "social_sensitivity_score": 0,
            "social_sensitivity_level": "No findings yet",
            "top_triggers": "",
            "recommended_actions": "Run the social risk assessment again after adding more study area locations and similar project types.",
        }
    avg = float(project_findings["risk_score"].mean())
    count_bonus = min(len(project_findings) * 2, 25)
    high_bonus = min(len(project_findings[project_findings["risk_level"].isin(["High", "Critical"])]) * 5, 30)
    score = int(min(avg + count_bonus + high_bonus, 100))
    if score >= 75:
        level = "High social sensitivity"
    elif score >= 50:
        level = "Moderate-high social sensitivity"
    elif score >= 25:
        level = "Moderate social sensitivity"
    else:
        level = "Low social sensitivity"
    trigger_counts = {}
    for cell in project_findings["triggers"].fillna(""):
        for t in str(cell).split(";"):
            t = t.strip()
            if t:
                trigger_counts[t] = trigger_counts.get(t, 0) + 1
    top = sorted(trigger_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    top_txt = "; ".join([f"{k} ({v})" for k, v in top])
    actions = recommended_actions([k for k, _ in top])
    return {
        "project_id": project.get("id", ""),
        "project_name": project.get("name", ""),
        "assessment_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "finding_count": int(len(project_findings)),
        "social_sensitivity_score": score,
        "social_sensitivity_level": level,
        "top_triggers": top_txt,
        "recommended_actions": actions,
    }


def recommended_actions(top_triggers: list[str]) -> str:
    actions = [
        "Prepare a plain-language project need and alternatives rationale.",
        "Track municipal council agendas and local media weekly.",
        "Create an issue-response log before the first public engagement milestone.",
    ]
    joined = " ".join(top_triggers).lower()
    if "tree" in joined or "vegetation" in joined:
        actions.append("Prepare vegetation clearing visuals, mitigation commitments, and restoration examples.")
    if "wetland" in joined or "habitat" in joined:
        actions.append("Prepare a natural heritage constraints summary and explain avoidance/minimization measures.")
    if "property" in joined or "compensation" in joined:
        actions.append("Prepare a landowner FAQ covering easements, compensation, access, and property impacts.")
    if "visual" in joined:
        actions.append("Prepare visual simulations or structure-height comparisons early.")
    if "indigenous" in joined:
        actions.append("Coordinate early Indigenous engagement strategy with project-specific rights, interests, and routing sensitivities.")
    if "transparency" in joined or "trust" in joined:
        actions.append("Publish route-selection criteria and decision points in an accessible format.")
    return " ".join(actions)


def run_scan() -> None:
    projects = load_projects()
    live_rows = []
    social_rows = []
    for project in projects:
        urls = list(project.get("source_urls", []) or [])
        for q in live_queries(project):
            urls.append(google_news_url(q))
        for url in urls[:25]:
            live_rows.extend(read_feed(url, project, mode="Live Monitoring"))
        for q in social_risk_queries(project):
            social_rows.extend(read_feed(google_news_url(q), project, mode="Social Risk Assessment"))

    append_unique(MENTIONS_CSV, live_rows)
    social_df = append_unique(SOCIAL_CSV, social_rows)
    if social_df.empty and SOCIAL_CSV.exists():
        social_df = pd.read_csv(SOCIAL_CSV)
    summaries = [summarize_social_risk(p, social_df) for p in projects]
    pd.DataFrame(summaries).to_csv(DATA / "social_risk_summary.csv", index=False)

    for summary in summaries:
        report_path = REPORTS / f"{summary['project_id']}_social_risk_report.md"
        report_path.write_text(
            f"# Social Risk Assessment: {summary['project_name']}\n\n"
            f"Assessment time: {summary['assessment_time_utc']}\n\n"
            f"## Sensitivity\n\n{summary['social_sensitivity_level']} ({summary['social_sensitivity_score']}/100)\n\n"
            f"## Findings reviewed\n\n{summary['finding_count']} public-source findings.\n\n"
            f"## Top triggers\n\n{summary['top_triggers'] or 'No recurring triggers detected yet.'}\n\n"
            f"## Recommended actions\n\n{summary['recommended_actions']}\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    run_scan()
    print("Portfolio social risk scan complete.")
