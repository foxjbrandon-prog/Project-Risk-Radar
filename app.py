from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import yaml
import plotly.express as px

from sample_data import sample_mentions
from rss_news import collect_rss_feeds, collect_google_news
from reddit import collect_reddit_public
from municipal import collect_municipal_rss
def calculate_risk(sentiment, issues, source=""):
    score = 10

    if sentiment == "Negative":
        score += 30
    elif sentiment == "Neutral":
        score += 10

    high_risk_terms = ["wetland", "trees", "property", "Indigenous", "lawsuit", "health", "traffic", "noise", "farmland"]
    issue_text = str(issues).lower()

    for term in high_risk_terms:
        if term.lower() in issue_text:
            score += 8

    if "council" in str(source).lower() or "news" in str(source).lower():
        score += 10

    score = min(score, 100)

    if score >= 75:
        level = "Critical"
    elif score >= 50:
        level = "High"
    elif score >= 25:
        level = "Medium"
    else:
        level = "Low"

    return level, score
    
ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data" / "mentions.csv"
CONFIG_PATH = ROOT / "config.yaml"
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

st.set_page_config(page_title="Project Risk Radar", layout="wide")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True)


def project_terms(config: dict) -> list[str]:
    p = config.get("project", {})
    terms = [p.get("name", "")]
    terms += p.get("aliases", []) or []
    terms += p.get("locations", []) or []
    return [t for t in terms if str(t).strip()]


def load_data() -> pd.DataFrame:
    if DATA_PATH.exists():
        return pd.read_csv(DATA_PATH)
    return pd.DataFrame()


def save_data(df: pd.DataFrame) -> None:
    DATA_PATH.parent.mkdir(exist_ok=True)
    df.to_csv(DATA_PATH, index=False)


def classify_and_score(rows: list[dict], config: dict) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["date", "source", "source_type", "title", "text", "url"]:
        if col not in df:
            df[col] = ""

    issue_keywords = config["project"].get("issue_keywords", [])
    high = config.get("risk", {}).get("high_severity_issues", [])
    medium = config.get("risk", {}).get("medium_severity_issues", [])

    results = df["text"].fillna("").apply(lambda x: classify_mention(x, issue_keywords))
    df["sentiment"] = results.apply(lambda r: r.sentiment)
    df["sentiment_score"] = results.apply(lambda r: r.sentiment_score)
    df["issue_theme"] = results.apply(lambda r: r.issue_theme)
    df["matched_keywords"] = results.apply(lambda r: r.matched_keywords)

    df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
    recent_count = int((df["date_dt"] >= (datetime.now() - timedelta(days=7))).sum())
    scored = df.apply(
        lambda row: calculate_risk(
            row.get("sentiment", "neutral"),
            row.get("issue_theme", "general project discussion"),
            row.get("source_type", "web"),
            recent_count,
            high,
            medium,
        ),
        axis=1,
    )
    df["risk_level"] = [x[0] for x in scored]
    df["risk_score"] = [x[1] for x in scored]
    df = df.drop(columns=["date_dt"])
    df["fingerprint"] = (df["title"].fillna("") + "|" + df["url"].fillna("")).str.lower()
    return df.drop_duplicates(subset=["fingerprint"])


def append_rows(new_df: pd.DataFrame) -> pd.DataFrame:
    old = load_data()
    combined = pd.concat([old, new_df], ignore_index=True) if not old.empty else new_df
    if "fingerprint" not in combined:
        combined["fingerprint"] = (combined["title"].fillna("") + "|" + combined["url"].fillna("")).str.lower()
    combined = combined.drop_duplicates(subset=["fingerprint"], keep="last")
    save_data(combined)
    return combined


config = load_config()
project = config.get("project", {})

st.title("Project Risk Radar")
st.caption("EA-focused public sentiment, issue, and risk monitoring MVP. Use public sources only and verify outputs before relying on them.")

with st.sidebar:
    st.header("Project setup")
    name = st.text_input("Project name", project.get("name", ""))
    aliases = st.text_area("Aliases / alternate names", "\n".join(project.get("aliases", []) or []))
    locations = st.text_area("Locations", "\n".join(project.get("locations", []) or []))
    issues = st.text_area("Issue keywords", "\n".join(project.get("issue_keywords", []) or []), height=180)
    if st.button("Save project setup"):
        config["project"]["name"] = name
        config["project"]["aliases"] = [x.strip() for x in aliases.splitlines() if x.strip()]
        config["project"]["locations"] = [x.strip() for x in locations.splitlines() if x.strip()]
        config["project"]["issue_keywords"] = [x.strip() for x in issues.splitlines() if x.strip()]
        save_config(config)
        st.success("Saved. Refresh or run a collection to use updated terms.")

    st.divider()
    st.header("Collect mentions")
    use_sample = st.checkbox("Add sample data", value=True)
    use_google = st.checkbox("Search Google News RSS", value=True)
    use_rss = st.checkbox("Configured RSS feeds", value=True)
    use_reddit = st.checkbox("Public Reddit search", value=False)
    use_municipal = st.checkbox("Municipal RSS feeds", value=False)

    if st.button("Run collection"):
        rows: list[dict] = []
        if use_sample:
            rows += sample_mentions()
        if use_google:
            rows += collect_google_news(project_terms(config), max_results=30)
        if use_rss:
            rows += collect_rss_feeds(config.get("sources", {}).get("rss_feeds", []), max_per_feed=20)
        if use_reddit:
            rows += collect_reddit_public(config.get("sources", {}).get("reddit_subreddits", []), project_terms(config), max_per_subreddit=10)
        if use_municipal:
            rows += collect_municipal_rss(config.get("sources", {}).get("municipal_rss_feeds", []), max_per_feed=20)
        new_df = classify_and_score(rows, config)
        all_df = append_rows(new_df) if not new_df.empty else load_data()
        st.success(f"Collection complete. Added/updated {len(new_df)} rows. Database now has {len(all_df)} rows.")

    if st.button("Clear local database"):
        if DATA_PATH.exists():
            DATA_PATH.unlink()
        st.warning("Local mentions database cleared.")


df = load_data()
if df.empty:
    st.info("No mentions yet. Use the sidebar to run a collection.")
    st.stop()

for col in ["date", "source", "source_type", "title", "text", "url", "sentiment", "issue_theme", "risk_level", "risk_score"]:
    if col not in df:
        df[col] = ""

df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
df = df.sort_values("date_dt", ascending=False)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Mentions", len(df))
c2.metric("Avg risk score", round(pd.to_numeric(df["risk_score"], errors="coerce").fillna(0).mean(), 1))
c3.metric("High/Critical", int(df["risk_level"].isin(["High", "Critical"]).sum()))
c4.metric("Negative", int((df["sentiment"] == "negative").sum()))

st.subheader("Risk Overview")
left, right = st.columns(2)
with left:
    counts = df["risk_level"].value_counts().reset_index()
    counts.columns = ["risk_level", "count"]
    st.plotly_chart(px.bar(counts, x="risk_level", y="count", title="Mentions by Risk Level"), use_container_width=True)
with right:
    issues_df = df["issue_theme"].value_counts().head(10).reset_index()
    issues_df.columns = ["issue_theme", "count"]
    st.plotly_chart(px.bar(issues_df, x="count", y="issue_theme", orientation="h", title="Top Issues"), use_container_width=True)

st.subheader("Sentiment Trend")
trend = df.dropna(subset=["date_dt"]).copy()
if not trend.empty:
    trend["day"] = trend["date_dt"].dt.date
    trend_df = trend.groupby(["day", "sentiment"]).size().reset_index(name="mentions")
    st.plotly_chart(px.line(trend_df, x="day", y="mentions", color="sentiment", markers=True), use_container_width=True)
else:
    st.write("No valid dates available for trend chart.")

st.subheader("Mention Explorer")
with st.expander("Filters", expanded=True):
    selected_risk = st.multiselect("Risk levels", sorted(df["risk_level"].dropna().unique()), default=list(sorted(df["risk_level"].dropna().unique())))
    selected_sentiment = st.multiselect("Sentiment", sorted(df["sentiment"].dropna().unique()), default=list(sorted(df["sentiment"].dropna().unique())))
    text_filter = st.text_input("Search text")

filtered = df[df["risk_level"].isin(selected_risk) & df["sentiment"].isin(selected_sentiment)].copy()
if text_filter:
    mask = filtered[["title", "text", "source", "issue_theme"]].fillna("").agg(" ".join, axis=1).str.contains(text_filter, case=False, regex=False)
    filtered = filtered[mask]

st.dataframe(
    filtered[["date", "risk_level", "risk_score", "sentiment", "issue_theme", "source", "title", "url"]],
    use_container_width=True,
    hide_index=True,
)

st.subheader("Weekly Brief")
brief_text = build_weekly_brief(filtered.drop(columns=["date_dt"], errors="ignore"), project.get("name", "Project"))
st.download_button("Download brief as Markdown", data=brief_text, file_name="project-risk-brief.md", mime="text/markdown")
st.text_area("Brief preview", brief_text, height=320)
