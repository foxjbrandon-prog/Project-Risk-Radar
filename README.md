# Portfolio Social Risk Radar V4

A Streamlit-based public issues monitoring and social risk assessment app for environmental assessment / infrastructure portfolios.

## What it does

1. **Live Monitoring**
   - Monitors public Google News RSS results and configured RSS feeds.
   - Looks for project names, aliases, and issue terms.
   - Scores sentiment, issue themes, and risk level.

2. **Social Risk Assessment**
   - Searches for historical public opposition patterns in each project study area.
   - Looks for recurring triggers such as tree clearing, wetlands, property values, traffic, visual impact, distrust, petitions, and council controversy.
   - Produces a Social Sensitivity Score and recommended engagement actions.

3. **Portfolio Dashboard**
   - Filters by project, source type, issue, sentiment, and risk level.
   - Shows current project risk and study-area social sensitivity.

## Files

- `app.py` - Streamlit dashboard and social risk assessment interface.
- `bot.py` - Scheduled scanner for GitHub Actions.
- `projects.yaml` - Edit this to add all your projects.
- `requirements.txt` - Python packages.
- `.github/workflows/scan.yml` - Runs the bot every 6 hours.
- `data/` - CSV data storage.
- `reports/` - Generated social risk reports.

## iPad / GitHub / Streamlit setup

1. Upload all visible files to your GitHub repository:
   - `app.py`
   - `bot.py`
   - `projects.yaml`
   - `requirements.txt`
   - `README.md`

2. The `.github` folder may be hidden on iPad. If it does not upload, create this file manually in GitHub:

   `.github/workflows/scan.yml`

   Use the contents from this package if visible, or ask ChatGPT to recreate it.

3. In Streamlit Community Cloud, point the app to:

   `app.py`

4. Edit `projects.yaml` to add your full project portfolio.

## Important use notes

This tool should only use public information. It is intended for engagement intelligence, issue tracking, and EA risk planning. It should not be used to monitor private individuals or closed/private communities.
