from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus
import hashlib
import re

import feedparser
import pandas as pd
import plotly.express as px
import streamlit as st
import yaml
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ROOT = Path(__file__).parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
MENTIONS_CSV = DATA / "mentions.csv"
SOCIAL_CSV = DATA / "social_risk_findings.csv"
SUMMARY_CSV = DATA / "social_risk_summary.csv"
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
    "Regulatory / approval": ["environmental registry", "oeb", "iaac", "mecp", "approval", "class ea"],
    "Community / social": ["facebook", "reddit", "community", "residents", "neighbourhood"],
}

st.set_page_config(page_title="Portfolio Social Risk Radar", layout="wide")


def load_projects() -> tuple[list[dict], dict]:
    with open(PROJECTS_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("projects", []), cfg.get("settings", {})


def save_projects(projects: list[dict], settings: dict) -> None:
    with open(PROJECTS_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump({"projects": projects, "settings": settings}, f, sort_keys=False, allow_unicode=True)


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


def read_feed(url: str, project: dict, mode: str, max_items: int = 20) -> list[dict]:
    rows = []
    feed = feedparser.parse(url)
    for entry in feed.entries[:max_items]:
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


def append_unique(csv_path: Path, rows: list[dict]) -> pd.DataFrame:
    new_df = pd.DataFrame(rows)
    if csv_path.exists():
        old = pd.read_csv(csv_path)
        combined = pd.concat([old, new_df], ignore_index=True) if not new_df.empty else old
    else:
        combined = new_df
    if combined.empty:
        return combined
    combined = combined.drop_duplicates(subset=["id"], keep="last")
    combined.to_csv(csv_path, index=False)
    return combined


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def live_queries(project: dict) -> list[str]:
    names = [project.get("name", "")] + project.get("aliases", [])
    issue_terms = ["opposition", "concerns", "petition", "council", "environmental concerns"]
    queries = []
    for name in names:
        if name:
            queries.append(f'"{name}"')
            for issue in issue_terms:
                queries.append(f'"{name}" {issue}')
    return queries[:12]


def social_risk_queries(project: dict) -> list[str]:
    locations = project.get("locations", [])
    similar = project.get("similar_project_types", []) or [project.get("type", "infrastructure")]
    triggers = ["opposition", "petition", "concerns", "controversy"]
    queries = []
    for loc in locations:
        for ptype in similar[:5]:
            for trig in triggers:
                queries.append(f'"{loc}" "{ptype}" {trig}')
    for loc in locations[:6]:
        for topic in ["tree clearing", "wetland", "property values", "traffic", "visual impact", "Indigenous consultation"]:
            queries.append(f'"{loc}" "{topic}" opposition')
    return queries[:25]


def run_live_scan(project: dict) -> pd.DataFrame:
    rows = []
    urls = list(project.get("source_urls", []) or [])
    for q in live_queries(project):
        urls.append(google_news_url(q))
    for url in urls[:18]:
        rows.extend(read_feed(url, project, "Live Monitoring"))
    return append_unique(MENTIONS_CSV, rows)


def run_social_scan(project: dict) -> tuple[pd.DataFrame, dict]:
    rows = []
    for q in social_risk_queries(project):
        rows.extend(read_feed(google_news_url(q), project, "Social Risk Assessment", max_items=10))
    findings = append_unique(SOCIAL_CSV, rows)
    summary = summarize_social_risk(project, findings)
    update_summary(summary)
    write_report(summary)
    return findings, summary


def summarize_social_risk(project: dict, findings: pd.DataFrame) -> dict:
    if not findings.empty and "project_id" in findings.columns:
        project_findings = findings[findings["project_id"] == project.get("id", "")].copy()
    else:
        project_findings = pd.DataFrame()
    if project_findings.empty:
        return {
            "project_id": project.get("id", ""),
            "project_name": project.get("name", ""),
            "assessment_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "finding_count": 0,
            "social_sensitivity_score": 0,
            "social_sensitivity_level": "No findings yet",
            "top_triggers": "",
            "recommended_actions": "Run the social risk assessment after adding study area locations and similar project types.",
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


def update_summary(summary: dict) -> None:
    new = pd.DataFrame([summary])
    old = load_csv(SUMMARY_CSV)
    combined = pd.concat([old, new], ignore_index=True) if not old.empty else new
    combined = combined.drop_duplicates(subset=["project_id"], keep="last")
    combined.to_csv(SUMMARY_CSV, index=False)


def write_report(summary: dict) -> None:
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


def add_manual_mention(project: dict, title: str, url: str, summary: str, mode: str) -> None:
    text = f"{title} {summary}"
    sent, sent_score = sentiment_label(text)
    triggers = detect_triggers(text, project.get("issue_keywords", []))
    source_type = detect_source_type(title, url, summary)
    level, score = risk_score(sent, triggers, title, summary, source_type)
    row = {
        "id": stable_id(project.get("id", ""), url, title, mode),
        "scan_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project_id": project.get("id", ""),
        "project_name": project.get("name", ""),
        "mode": mode,
        "source_type": source_type,
        "title": clean_text(title),
        "summary": clean_text(summary),
        "url": clean_text(url),
        "published": "Manual entry",
        "sentiment": sent,
        "sentiment_score": sent_score,
        "triggers": "; ".join(triggers),
        "risk_level": level,
        "risk_score": score,
    }
    append_unique(MENTIONS_CSV if mode == "Live Monitoring" else SOCIAL_CSV, [row])


projects, settings = load_projects()
project_names = [p["name"] for p in projects]
project_map = {p["name"]: p for p in projects}

st.title("Portfolio Social Risk Radar")
st.caption("Live monitoring + study-area social risk assessment for public EA / infrastructure risk intelligence. Uses public-source information only.")

with st.sidebar:
    st.header("Project")
    selected_name = st.selectbox("Choose project", project_names if project_names else ["No projects configured"])
    selected_project = project_map.get(selected_name, {})
    st.divider()
    st.header("Run scans")
    if selected_project:
        if st.button("Run live monitoring scan", use_container_width=True):
            with st.spinner("Scanning project mentions..."):
                run_live_scan(selected_project)
            st.success("Live scan complete.")
        if st.button("Run social risk assessment", use_container_width=True):
            with st.spinner("Searching historical opposition patterns in the study area..."):
                _, summary = run_social_scan(selected_project)
            st.success(f"Social risk assessment complete: {summary['social_sensitivity_level']}")
    st.divider()
    st.header("Manual entry")
    manual_title = st.text_input("Title")
    manual_url = st.text_input("URL")
    manual_summary = st.text_area("Summary / note")
    manual_mode = st.selectbox("Entry type", ["Live Monitoring", "Social Risk Assessment"])
    if st.button("Add manual finding", use_container_width=True):
        if selected_project and manual_title:
            add_manual_mention(selected_project, manual_title, manual_url, manual_summary, manual_mode)
            st.success("Manual finding added.")
        else:
            st.warning("Add at least a title first.")

mentions = load_csv(MENTIONS_CSV)
social = load_csv(SOCIAL_CSV)
summary_df = load_csv(SUMMARY_CSV)

portfolio_tab, live_tab, social_tab, reports_tab, config_tab = st.tabs([
    "Portfolio Overview", "Live Monitoring", "Social Risk Assessment", "Project Brief", "Projects Config"
])

with portfolio_tab:
    st.subheader("Portfolio overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Projects", len(projects))
    c2.metric("Live mentions", 0 if mentions.empty else len(mentions))
    c3.metric("Social risk findings", 0 if social.empty else len(social))
    high_count = 0
    if not mentions.empty:
        high_count += len(mentions[mentions["risk_level"].isin(["High", "Critical"])])
    if not social.empty:
        high_count += len(social[social["risk_level"].isin(["High", "Critical"])])
    c4.metric("High / critical findings", high_count)

    if not summary_df.empty:
        st.subheader("Study-area social sensitivity")
        st.dataframe(summary_df[["project_name", "social_sensitivity_level", "social_sensitivity_score", "finding_count", "top_triggers"]], use_container_width=True)
        fig = px.bar(summary_df, x="project_name", y="social_sensitivity_score", title="Social sensitivity by project")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No social risk assessments have been run yet.")

with live_tab:
    st.subheader("Live monitoring")
    if mentions.empty:
        st.info("No live monitoring results yet. Run a live scan from the sidebar.")
    else:
        df = mentions.copy()
        df = df[df["project_name"] == selected_name] if selected_name in df["project_name"].unique() else df
        levels = st.multiselect("Risk level", sorted(df["risk_level"].dropna().unique()), default=list(sorted(df["risk_level"].dropna().unique())))
        if levels:
            df = df[df["risk_level"].isin(levels)]
        c1, c2, c3 = st.columns(3)
        c1.metric("Findings", len(df))
        c2.metric("Average risk", round(df["risk_score"].mean(), 1) if not df.empty else 0)
        c3.metric("Negative", len(df[df["sentiment"] == "Negative"]) if not df.empty else 0)
        if not df.empty:
            st.plotly_chart(px.histogram(df, x="risk_level", title="Live findings by risk level"), use_container_width=True)
            st.dataframe(df[["risk_level", "risk_score", "sentiment", "source_type", "title", "triggers", "url"]].sort_values("risk_score", ascending=False), use_container_width=True)

with social_tab:
    st.subheader("Social risk assessment")
    if social.empty:
        st.info("No social risk findings yet. Run a social risk assessment from the sidebar.")
    else:
        df = social.copy()
        df = df[df["project_name"] == selected_name] if selected_name in df["project_name"].unique() else df
        if not df.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Historical findings", len(df))
            c2.metric("Average risk", round(df["risk_score"].mean(), 1))
            c3.metric("High / critical", len(df[df["risk_level"].isin(["High", "Critical"])]))
            trigger_rows = []
            for cell in df["triggers"].fillna(""):
                for t in str(cell).split(";"):
                    t = t.strip()
                    if t:
                        trigger_rows.append(t)
            if trigger_rows:
                trigger_df = pd.DataFrame({"trigger": trigger_rows}).value_counts().reset_index(name="count")
                st.plotly_chart(px.bar(trigger_df.head(12), x="trigger", y="count", title="Most common opposition triggers"), use_container_width=True)
            st.dataframe(df[["risk_level", "risk_score", "source_type", "title", "triggers", "url"]].sort_values("risk_score", ascending=False), use_container_width=True)

with reports_tab:
    st.subheader("Project brief")
    project_summary = pd.DataFrame()
    if not summary_df.empty and selected_project:
        project_summary = summary_df[summary_df["project_id"] == selected_project.get("id", "")]
    if project_summary.empty:
        st.info("Run the social risk assessment first to generate a project brief.")
    else:
        s = project_summary.iloc[0].to_dict()
        st.metric("Social sensitivity", f"{s['social_sensitivity_score']}/100", s["social_sensitivity_level"])
        st.markdown("### Top opposition triggers")
        st.write(s.get("top_triggers") or "No recurring triggers detected yet.")
        st.markdown("### Recommended actions")
        st.write(s.get("recommended_actions", ""))
        report_path = REPORTS / f"{selected_project.get('id')}_social_risk_report.md"
        if report_path.exists():
            st.download_button("Download Markdown report", report_path.read_text(encoding="utf-8"), file_name=report_path.name)

with config_tab:
    st.subheader("Projects configuration")
    st.write("Edit `projects.yaml` in GitHub for permanent changes. This page shows the current loaded configuration.")
    st.code(yaml.safe_dump({"projects": projects, "settings": settings}, sort_keys=False, allow_unicode=True), language="yaml")
