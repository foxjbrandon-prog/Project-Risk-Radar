# Portfolio Risk Radar V3

A multi-project public-source monitoring bot for EA / infrastructure project risk tracking.

## What it does

- Tracks multiple projects from `projects.yaml`
- Searches Google News RSS for each project and criticism terms
- Scores sentiment, issues, and EA-style risk
- Saves mentions to `data/mentions.csv`
- Displays a Streamlit dashboard
- Includes a GitHub Actions workflow to scan every 6 hours

## Files

- `app.py` — dashboard
- `bot.py` — scanner and risk classifier
- `projects.yaml` — portfolio configuration
- `requirements.txt` — Python dependencies
- `.github/workflows/scan.yml` — scheduled scan
- `data/` — mention storage

## Setup

1. Upload all files and folders to your GitHub repository.
2. Confirm these appear in GitHub:
   - `app.py`
   - `bot.py`
   - `projects.yaml`
   - `requirements.txt`
   - `.github/workflows/scan.yml`
   - `data/.gitkeep`
3. In Streamlit Community Cloud, deploy `app.py`.
4. In GitHub, open **Actions** and enable workflows if prompted.
5. Use **Run workflow** to test the scheduled scanner.

## Editing projects

Edit `projects.yaml` in GitHub. Each project needs:

```yaml
- id: short_unique_id
  name: "Project Name"
  aliases:
    - "Alternate Name"
  locations:
    - "Location Ontario"
  issue_keywords:
    - "wetland"
    - "traffic"
  source_urls: []
```

## Notes

This is an MVP. It uses public Google News RSS and optional RSS feeds. For a production consulting-firm version, add:

- Bing Search API or SerpAPI
- municipal agenda/minutes connectors
- regulator registry connectors
- email alerts
- Supabase/Postgres database
- user authentication

Use public sources only and verify results before relying on them.
