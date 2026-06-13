from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml

from bot import FIELDNAMES, MENTIONS_CSV, append_mentions, classify, collect_for_project, load_projects, make_id

ROOT = Path(__file__).parent
PROJECTS_YAML = ROOT / "projects.yaml"

st.set_page_config(page_title="Portfolio Risk Radar", layout="wide")


def save_projects(projects: list[dict]):
    with open(PROJECTS_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump({"projects": projects}, f, sort_keys=False, allow_unicode=True)


def load_mentions() -> pd.DataFrame:
    if not MENTIONS_CSV.exists():
        return pd.DataFrame(columns=FIELDNAMES)
    return pd.read_csv(MENTIONS_CSV).fillna("")


def add_manual_mention(project: dict, title: str, summary: str, url: str, source: str):
    now = datetime.now(timezone.utc).isoformat()
    sentiment, s_score, issues, risk_level, risk_score = classify(project, title, summary, source or "Manual")
    row = {
        "mention_id": make_id(project["id"], url, title),
        "collected_at": now,
        "published": now,
        "project_id": project["id"],
        "project_name": project["name"],
        "source_type": "Manual",
        "source": source or "Manual",
        "title": title,
        "summary": summary,
        "url": url,
        "query": "manual entry",
        "sentiment": sentiment,
        "sentiment_score": s_score,
        "issues": issues,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "new_item": "yes",
    }
    return append_mentions([row])


st.title("Portfolio Risk Radar")
st.caption("Public-source project monitoring for news, criticism, issues, and EA-style risk signals. Use public sources only and verify results before relying on them.")

projects = load_projects()
project_names = [p["name"] for p in projects]
project_lookup = {p["name"]: p for p in projects}

with st.sidebar:
    st.header("Controls")
    selected = st.selectbox("Project filter", ["All projects"] + project_names)
    risk_filter = st.multiselect("Risk filter", ["Low", "Medium", "High", "Critical"], default=["Medium", "High", "Critical"])

    st.divider()
    st.subheader("Run scanner now")
    scan_target = st.selectbox("Project to scan", project_names)
    if st.button("Scan selected project", type="primary"):
        with st.spinner("Scanning public news/RSS sources..."):
            rows = collect_for_project(project_lookup[scan_target])
            added = append_mentions(rows)
        st.success(f"Scan complete. Added {added} new mentions from {len(rows)} results checked.")
        st.rerun()

    if st.button("Scan all projects"):
        total = 0
        checked = 0
        with st.spinner("Scanning all projects..."):
            for p in projects:
                rows = collect_for_project(p)
                checked += len(rows)
                total += append_mentions(rows)
        st.success(f"Scan complete. Added {total} new mentions from {checked} results checked.")
        st.rerun()

    st.divider()
    st.subheader("Manual mention")
    manual_project = st.selectbox("Manual project", project_names, key="manual_project")
    manual_title = st.text_input("Title")
    manual_url = st.text_input("URL")
    manual_source = st.text_input("Source", value="Manual")
    manual_summary = st.text_area("Summary / text")
    if st.button("Add manual mention"):
        if manual_title.strip():
            added = add_manual_mention(project_lookup[manual_project], manual_title, manual_summary, manual_url, manual_source)
            st.success("Mention added." if added else "That mention already exists.")
            st.rerun()
        else:
            st.warning("Add a title first.")

    st.divider()
    st.subheader("Portfolio setup")
    st.caption("Edit projects.yaml in GitHub for bulk changes. This app reads that file.")


df = load_mentions()

if df.empty:
    st.info("No mentions yet. Use the sidebar to scan a project, scan all projects, or add a manual mention.")
    st.stop()

if selected != "All projects":
    df = df[df["project_name"] == selected]
if risk_filter:
    df = df[df["risk_level"].isin(risk_filter)]

if df.empty:
    st.warning("No mentions match the current filters.")
    st.stop()

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Mentions", len(df))
c2.metric("High/Critical", int(df["risk_level"].isin(["High", "Critical"]).sum()))
c3.metric("Negative", int((df["sentiment"] == "Negative").sum()))
c4.metric("Max risk score", int(pd.to_numeric(df["risk_score"], errors="coerce").max()))

st.subheader("Risk by project")
project_summary = df.groupby("project_name", as_index=False).agg(
    mentions=("mention_id", "count"),
    max_risk=("risk_score", "max"),
)
st.dataframe(project_summary.sort_values("max_risk", ascending=False), use_container_width=True)

st.subheader("Trends")
df_chart = df.copy()
df_chart["collected_date"] = pd.to_datetime(df_chart["collected_at"], errors="coerce").dt.date
trend = df_chart.groupby(["collected_date", "risk_level"], as_index=False).size()
if not trend.empty:
    fig = px.bar(trend, x="collected_date", y="size", color="risk_level", title="Mentions collected over time")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Latest mentions")
show_cols = ["collected_at", "project_name", "risk_level", "risk_score", "sentiment", "issues", "source", "title", "url"]
st.dataframe(df.sort_values("collected_at", ascending=False)[show_cols], use_container_width=True, height=420)

st.subheader("Brief")
high = df[df["risk_level"].isin(["High", "Critical"])].sort_values("risk_score", ascending=False).head(10)
if high.empty:
    st.write("No high or critical risks in the current filter.")
else:
    lines = ["# Portfolio Risk Brief", "", f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "", "## Top risks"]
    for _, row in high.iterrows():
        lines.append(f"- **{row['project_name']}** — {row['risk_level']} ({row['risk_score']}): {row['title']} | Issues: {row['issues']}")
    brief = "\n".join(lines)
    st.text_area("Copyable brief", brief, height=260)
    st.download_button("Download brief", brief, file_name="portfolio_risk_brief.md")

st.caption("Note: Google News RSS is useful but imperfect. For production use, add Bing Search, SerpAPI, municipal agenda APIs, and a persistent database such as Supabase/Postgres.")
