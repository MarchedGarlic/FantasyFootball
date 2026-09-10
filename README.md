# Fantasy Football Analysis

A single-season fantasy football analysis tool for **Sleeper** leagues. Enter a Sleeper username,
pick a season and league, and get power rankings, roster grades, trade/waiver analysis, draft
ratings, and a deterministic AI-style overview — rendered as interactive HTML (Bokeh) plus a JSON
API.

See [CLAUDE.md](CLAUDE.md) for the full architecture, data model, and scoring formulas behind each
report.

## Features

- **Power Rankings** — weekly team strength ratings with historical progression
- **Roster Grades** — ESPN-tier player grading rolled up per team
- **Trade Analysis** — per-player value scoring for every trade, with FAAB context where applicable
- **Waiver Analysis** — position-adjusted points-over-replacement scoring for every pickup, plus a
  FAAB tracker/leaderboard for FAAB leagues
- **Manager Grades** — season report cards
- **Luck Analysis / Median Standings** — real record vs. a median-scoring-rule record
- **Draft Info** — a 0–10 Draft Rating leaderboard and "Biggest Steals" vs. ESPN's preseason ranks
- **AI Overview** — top performers, upsets, power-ranking movers, upcoming matchups, and a
  projected playoff bracket, all computed deterministically (no LLM call)

## Quick start (interactive web app)

```bash
pip install -r requirements.txt
npm install
python server.py
```

Open `http://localhost:5000`, enter a Sleeper username, then pick a season and league. Analysis
runs on demand; results are cached per `(league_id, season)`.

## Alternative: CLI + static build

For a one-off analysis without the web UI:

```bash
cp league_config.json.template league_config.json   # fill in your username/league/season
python main.py
npm run build && npm run serve   # local static preview at http://localhost:3000
```

See [DEV_GUIDE.md](DEV_GUIDE.md) for the full set of `npm run` commands.

## Deployment

This app currently deploys two ways side by side:

| Target | Guide | Model |
|---|---|---|
| Netlify | [NETLIFY_DEPLOYMENT.md](NETLIFY_DEPLOYMENT.md) | Static: analysis pre-run, HTML/JSON committed/built |
| Render | [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) | Live Flask server, analysis on demand |

Azure App Service is prepped but not yet provisioned — see [AZURE_MIGRATION.md](AZURE_MIGRATION.md).

## Project structure

```
FantasyFootball/
├── main.py                  # Analysis pipeline (CLI entry point; also called by server.py)
├── server.py                 # Flask app — interactive web UI + JSON API
├── index.html / results_template.html   # Frontend shell
├── src/
│   ├── storage.py              # Per-(league_id, season) storage + disk cache
│   ├── api_clients.py           # Sleeper/ESPN HTTP clients
│   ├── roster_grading.py        # ESPN-tier player grading
│   ├── power_rankings.py        # Weekly power ratings
│   ├── trade_analysis.py        # Trade + waiver impact scoring, Bokeh charts
│   ├── faab_analysis.py         # FAAB ledger + relative-scarcity scoring
│   ├── draft_analysis.py        # Draft Rating + Biggest Steals
│   ├── ai_overview.py           # Deterministic AI Overview + Draft Info rendering
│   ├── median_record_calculator.py
│   ├── bokeh_theme.py / bokeh_mobile.py
│   └── tests/                   # Test suite
└── fantasy_analysis_output/
    └── leagues/<league_id>/<season>/   # Generated reports, keyed per league + season
```

See [CLAUDE.md](CLAUDE.md) §0.1 for what each `src/` module does, and §3.1 for the full storage
layout.

## API

- `GET /api/current-season` — current NFL season (from Sleeper)
- `GET /api/user/<username>?season=<year>` — a user's leagues for that season
- `GET /api/seasons/<league_id>` — seasons already analyzed for a league
- `POST /api/analyze` — start analysis for `{username, league_id, league_name, season}`
- `GET /api/status/<analysis_id>` — analysis progress
- `GET /api/results` — available reports for the current analysis
- `GET /results/<path:filename>` — serve a generated report file
