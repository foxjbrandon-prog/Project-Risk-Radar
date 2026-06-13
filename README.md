# Project Risk Radar

An iPad-friendly MVP for monitoring public sentiment, issue themes, and risk signals for Environmental Assessment / infrastructure projects.

This version is designed to run in a browser on your iPad by hosting it with **Streamlit Community Cloud** or another Python web host. An iPad cannot normally run a Streamlit server directly like a laptop can, but it can use the hosted app perfectly through Safari.

## What it does

- Tracks project names, aliases, locations, and issue keywords.
- Collects public mentions from:
  - Google News RSS search
  - configured RSS feeds
  - optional public Reddit search
  - optional municipal RSS feeds
  - sample data for testing
- Classifies each mention by:
  - sentiment
  - issue theme
  - risk score
  - risk level
- Displays a dashboard.
- Exports a weekly risk brief in Markdown.
- Saves results to `data/mentions.csv`.

## iPad setup option 1: Streamlit Community Cloud

1. Create a GitHub account if you do not already have one.
2. Create a new GitHub repository called `project-risk-radar`.
3. Upload all files in this folder to that repository.
4. Go to Streamlit Community Cloud in Safari.
5. Choose **New app**.
6. Connect your GitHub repository.
7. Set the main file path to:

```text
app.py
```

8. Deploy.
9. Open the Streamlit app link on your iPad.
10. Save it to your iPad Home Screen.

## iPad setup option 2: GitHub Codespaces

This is better if your company does not want a public Streamlit deployment.

1. Upload the folder to GitHub.
2. Open the repository on your iPad.
3. Start a Codespace.
4. In the terminal, run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

5. Open the forwarded port URL in Safari.

## Laptop setup

```bash
cd project-risk-radar
pip install -r requirements.txt
streamlit run app.py
```

## Configure your project

Edit `config.yaml`, or use the sidebar in the app.

Important fields:

```yaml
project:
  name: "Example Transmission Line"
  aliases:
    - "Example Tx Line"
  locations:
    - "St. Thomas"
  issue_keywords:
    - "trees"
    - "wetlands"
    - "property values"
    - "EMF"
```

## Adding municipal sources

If a municipality provides an RSS feed for council agendas/news, add it to `config.yaml`:

```yaml
sources:
  municipal_rss_feeds:
    - "https://example.ca/council/rss"
```

Many municipalities do not provide usable RSS. For those, the next version should use targeted web scraping or a paid search API.

## Data/privacy caution

Use this only for public information. Do not scrape private groups, closed communities, or personal accounts. Treat outputs as intelligence prompts that require human verification, not as final evidence.

## Suggested next upgrades

- Add NewsAPI, SerpAPI, or Google Custom Search API.
- Add YouTube comments for public meeting videos.
- Add a municipal agenda/minutes scraper.
- Add LLM-based issue summaries.
- Add a misinformation/watch-list detector.
- Add email alerts for new high-risk mentions.
- Add a project-specific risk scoring matrix aligned with your EA practice.
