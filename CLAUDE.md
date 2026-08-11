# CLAUDE.md — Fantasy Football Analysis App

This file is the living architecture + plan document for this repo. It records what the app
actually does, the problems found in the 2026-08 audit, the decisions made to fix them, and the
exact formulas/data model so future changes stay consistent. Update it whenever the architecture
or a scoring formula changes — treat it as more durable than a commit message.

## 0. What this app is

A single-season fantasy football analysis tool for **Sleeper** leagues (no dynasty/keeper support —
every league is analyzed independently, one season at a time). A user enters their Sleeper
username, picks a season and a league, and the app pulls that league's full season of data
(rosters, matchups, transactions) and produces power rankings, roster grades, trade/waiver
analysis, and an AI-style overview, rendered as interactive HTML (Bokeh) + a JSON API.

Two deployment shapes exist side by side today: a static export to Netlify (analysis pre-run,
HTML/JSON committed/built) and a live Flask server on Render (analysis on demand). Azure is the
next candidate host — see §6.

### 0.1 Key files

| File | Purpose |
|---|---|
| `main.py` | `run_analysis(username, season, league_id, storage, progress_cb)` — the full pipeline, called by both the CLI (`main()`) and `server.py`. No longer reads a shared config file mid-run. |
| `server.py` | Flask app. Season/league now travel explicitly through every route (query params / POST body) instead of being hardcoded or read from a shared file. |
| `src/storage.py` | `AnalysisStorage` — every artifact keyed by `(league_id, season)`; also the cross-league disk cache (`players.json`, ESPN rankings) and the per-`(league_id, season)` analysis lock. |
| `src/api_clients.py` | Sleeper/ESPN HTTP clients — timeouts, retry/backoff, and the bulk (`ThreadPoolExecutor`-backed) weekly matchup/transaction fetchers. |
| `src/roster_grading.py` | ESPN-tier player grading; athlete/team/position `$ref` lookups are now parallelized and memoized. |
| `src/power_rankings.py` | Weekly power ratings + `compute_power_rank_history()` (persisted per-week rank series, used by the AI Overview). |
| `src/faab_analysis.py` | FAAB ledger reconstruction + relative-scarcity scoring (§4.3). Returns `{'enabled': False}` for non-FAAB leagues. |
| `src/trade_analysis.py` | Trade/waiver impact scoring (§4.1) plus the Bokeh chart builders (chart *chrome* mostly untouched — only the data feeding it changed). |
| `src/ai_overview.py` | The six deterministic AI Overview sections (§5) + HTML rendering. No LLM call. |
| `src/median_record_calculator.py` | Median-based record calculation (unchanged logic; O(n²) lookups fixed, dead standalone `main()` removed). |

## 1. Audit findings (2026-08) — why this rewrite happened

A full code audit turned up five categories of problems, in order of how much they drove the
redesign below:

1. **Season/league isolation was effectively absent.** `server.py` hardcoded `season = 2025` in
   two places. Every analysis run wrote to one fixed, shared directory
   (`fantasy_analysis_output/`) that got `shutil.rmtree()`'d and rebuilt on *every* run, with no
   league_id or season in the path. Two analyses (different users, different leagues, or the same
   league a year apart) run back to back would silently overwrite each other. Sleeper gives every
   season of a league a **different `league_id`** (chained via `previous_league_id`); the code
   never used that field and had no per-season data model at all.
2. **Performance.** A single full-season run made **~750 sequential HTTP requests**, ~720 of them
   one-at-a-time ESPN athlete-detail lookups inside `roster_grading.py`, with zero concurrency, no
   timeouts, no retries, and no caching — including re-fetching Sleeper's ~5MB `/players/nfl`
   payload on every run despite Sleeper's own docs saying to cache it once a day.
3. **Trade analysis didn't look at the players traded.** It scored a trade by the whole team's
   power-rating/roster-grade delta from the week before to the week of the trade — a signal
   dominated by bye weeks, injuries, and ordinary variance, not the trade itself. The "roster
   grade" half of that delta was mostly `random.uniform()` noise seeded with Python's per-process
   `hash()` (non-reproducible). FAAB was **never read anywhere** in the codebase. 3+ team trades
   were silently dropped. The trading partner was looked up by display-name equality (crashes on
   duplicate names). Waiver impact double-counted multi-add transactions. Three different
   "combined impact" formulas coexisted and none matched the methodology text shown to users.
4. **The "AI Overview" had no AI in it**, and not by a defensible design choice — `openai` was
   imported, `OPENAI_API_KEY` was read, and then a hardcoded line
   (`# Always use mock content for now to avoid OpenAI issues`) always called the mock generator
   instead. The mock output was 12 generic template paragraphs per manager built from season
   high/low power rating only. None of the sections the user actually wants (top players of the
   week, upsets, week-over-week rank movement, upcoming matchups, playoff projections, waiver
   pickups) existed, and the per-player weekly scores and per-matchup pairings needed for most of
   them were fetched from Sleeper and then discarded before ever reaching a JSON file.
5. **Azure readiness.** Local-disk output, an in-memory `analysis_status` dict, and a shared
   `league_config.json` file are all incompatible with App Service's scale-out/ephemeral-instance
   model and with Azure Functions' stateless model as-is. CORS is wide open, `/api/analyze` has no
   auth/rate limiting, and the Netlify/Render configs disagree on Python version (3.9 vs 3.11).

## 2. Decisions made (confirmed with user before implementation)

| Question | Decision |
|---|---|
| Season/league model | **Simple**: user picks a season, then a league for that season. Every stored artifact is keyed by `(league_id, season)`. No automatic cross-season "league family" linking via `previous_league_id` (deferred — see §7). |
| FAAB valuation | **Relative scarcity model** (§4.3): a spend is valued by how much of the spender's own remaining budget it consumed, contextualized against what everyone else in the league had left at that moment. |
| AI Overview engine | **Fully deterministic, no LLM call.** All sections are computed from real data and templated into HTML. No API key, no external dependency, no per-run cost/latency. |
| Azure scope | **Code/config prep only.** Storage abstraction, Dockerfile, GitHub Actions workflow, migration checklist. No live Azure resources are created by this work — no Azure credentials are available in this environment. |

## 3. Data model & season/league isolation

### 3.1 Storage layout

All generated artifacts move from one shared `fantasy_analysis_output/` blob into a structure keyed
by league and season, managed by a small storage abstraction (`src/storage.py`) so the on-disk
implementation can later be swapped for Azure Blob Storage without touching calling code:

```
fantasy_analysis_output/
  leagues/
    <league_id>/
      <season>/
        html_reports/*.html
        json_data/*.json          # fantasy_analysis.json, detailed_analysis.json, roster_data.json
        text_reports/*.txt
        meta.json                 # {league_name, analysis_id, generated_at, weeks_analyzed}
  cache/
    players.json + players_meta.json      # Sleeper /players/nfl, 24h TTL
    espn_rankings_<season>.json           # ESPN stat leaders, 24h TTL
```

`AnalysisStorage` (in `src/storage.py`) exposes `paths_for(league_id, season)`, `write_json`,
`read_json`, `list_analyzed_seasons(league_id)`, `cache_get(key, max_age_s)`, `cache_set(key,
data)`. Only the specific `leagues/<league_id>/<season>/` directory is cleared before a fresh run
— never the shared `cache/` directory, and never another league's or season's data.

### 3.2 Season selection

- `GET /api/user/<username>?season=<year>` — season is now a required/explicit query param (was
  hardcoded to 2025). The frontend defaults it to the current NFL season, discovered via Sleeper's
  `GET /v1/state/nfl` (`league_season` field) instead of a hardcoded literal.
- `POST /api/analyze` accepts `{username, league_id, league_name, season}` — season now travels
  with the request instead of being hardcoded into the config it writes.
- `main.py`'s analysis entry point becomes a function that takes an explicit config dict rather
  than only reading the shared `league_config.json` — the web server no longer depends on a
  file-based side channel to pass `(league_id, season)` into the pipeline. `league_config.json`
  is still supported for the standalone CLI/local workflow.
- A per-`(league_id, season)` `threading.Lock` prevents two concurrent runs of the *same*
  league+season from racing; different leagues/seasons run fully independently since they now
  write to disjoint directories.

### 3.3 Stop hardcoding the schedule

`league_info['settings']` (fetched today and then discarded) now drives the actual week range —
`playoff_week_start` / last scored week — instead of `max_week = 15 if SEASON >= 2021 else 16`.
This also fixes leagues with 14, 16, or 17-week regular seasons, which previously had their last
1-2 weeks of data silently dropped from every calculation.

## 4. Trade analysis & FAAB

### 4.1 Trade scoring redesign

Old model: team-wide power-rating/roster-grade delta, week-before vs. week-of-trade. New model:
**value the specific players that moved.**

- Each traded player is graded with the existing ESPN-tier `grade_player()` (already used for
  roster grading, ~1.0–10.0 scale). `value_acquired = sum(grade for players received)`,
  `value_given_up = sum(grade for players sent away)`, `net_player_value = value_acquired -
  value_given_up`. This directly reflects what was actually exchanged, unlike the old delta.
- Team power-rating/roster-grade trend around the trade date is kept as *supplementary context*
  ("this manager was already trending up/down going into the trade"), never as the primary score,
  and is now computed against the manager's **actual reconstructed historical roster** for that
  week (see below) instead of the current-day roster.
- The trading partner is identified by `manager_id`/`roster_id`, not display-name equality — fixes
  a crash on duplicate display names.
- 3+ team trades are analyzed per-manager (each manager's own acquired/given-up players are still
  attributed correctly from Sleeper's flat `adds`/`drops` maps) instead of being silently dropped;
  the UI labels these "N-team trade" rather than hiding them.
- One "combined impact" formula, computed once, with the on-page methodology text generated from
  the same constants it's computed from — no more three divergent formulas/descriptions.

### 4.2 Historical roster reconstruction (also removes the fake randomness)

The old "weekly roster grade" was the *current* roster's static grade plus `random.uniform()`
jitter meant to simulate week-to-week change. That's replaced by reconstructing each manager's
actual roster as of a given week: start from the current roster and walk the season's transactions
backward, undoing each add/drop after the target week. The roster grade for week *N* is then the
real grade of the real roster that existed at week *N* — no randomness, and it only changes on
weeks where a real transaction changed that roster.

### 4.3 FAAB relative-scarcity valuation

Only computed for leagues where `league_info['settings']['waiver_type'] == 2` (Sleeper's FAAB
setting) — leagues on rolling/reverse-standings waivers never show FAAB sections.

**Ledger reconstruction:** every roster starts the season at `settings['waiver_budget']` (the
league's total FAAB budget, e.g. 100). Walk every transaction for the season in chronological
order (week, then `created` timestamp):
- Waiver transactions carrying `settings.waiver_bid` subtract that amount from the claiming
  roster's balance.
- Trade transactions carrying a non-empty `waiver_budget` array apply the sender/receiver deltas.

This produces, for every transaction, each roster's balance *immediately before* that transaction,
which is cross-checked at the end of the season against `roster.settings.waiver_budget_used`
(logged as a warning on mismatch — catches missed commissioner adjustments rather than failing
silently).

**Scoring a spend of amount `A` by manager `M` at time `T`:**

- `commitment_ratio = A / M's balance right before T` — how much of *their own* remaining budget
  this spend consumed. Spending $30 with $35 left (ratio ≈ 0.86) is a far bigger commitment than
  spending $30 with $90 left (ratio ≈ 0.33), even though the raw dollar amount is identical.
- `relative_scarcity = M's balance right before T ÷ average balance of every other roster at that
  same moment` — below 1.0 means `M` already had less cash than the league average when they
  spent it.
- Displayed per FAAB transaction: the raw `$` amount, `commitment_ratio` (as "% of your remaining
  budget"), and `relative_scarcity` (as "Nx the league's average remaining cash" at that time).
  These three numbers are always shown together — never collapsed into an opaque single score
  without the components alongside it.
- A derived **FAAB Aggressiveness Score** (0–100, `commitment_ratio` weighted by the inverse of
  `relative_scarcity`) is used only for leaderboard ranking, with the raw components shown next to
  it in the same row.
- Surfaced in: trade cards (when a trade includes a `waiver_budget` transfer), the waiver
  leaderboard (adds "$/point of impact" efficiency + aggressiveness score columns), and a new FAAB
  Tracker panel showing every manager's current remaining balance.

### 4.4 Other fixes bundled into this pass

- Waiver impact double-counting for multi-add transactions in a single transaction object — fixed
  by attributing impact once per transaction, not once per added player.
- Transaction `status` is checked — anything other than `complete` is excluded from scoring.

## 5. AI Overview (deterministic)

New module `src/ai_overview.py` replaces `server.py`'s `create_ai_team_overview` /
`create_detailed_mock_overview` / `create_mock_ai_overview` and the dead `openai` import entirely.
Sections, each backed by data that is now actually persisted (previously fetched-then-discarded):

1. **Top players of the week** — every rostered player's points for the most recently completed
   week (from Sleeper matchups' `players_points`), top 10 league-wide, with the manager who
   started/owned them.
2. **Biggest upsets** — each week's head-to-head margin compared against the two teams' power
   rank entering that week (from the newly-persisted per-week rank history, §5 data model below);
   a win by the lower-ranked team, weighted by rank gap and margin, is an upset.
3. **Power ranking movers: last week vs. this week** — a rank-delta table built directly from the
   per-week power-rating series already computed by `power_rankings.py` (previously computed
   ad hoc inside a Bokeh hover tooltip and never persisted; now extracted into its own
   `power_rank_by_week` structure saved to JSON).
4. **Matchups to watch** — the next unplayed week's pairings, scored by standings stakes (e.g. two
   teams within the playoff cutoff facing each other, or the current bubble teams — cutoff comes
   from the league's real `settings.playoff_teams`).
5. **Projected playoff teams** — "if the season ended today" standings (wins, then points as
   tiebreak) against the league's real `playoff_teams` count, with games-back-from-the-cutoff for
   the bubble teams. Explicitly labeled as a snapshot projection, not a playoff-odds simulation.
6. **Median standings** — "if a median-scoring rule had been in place all season": each week the
   top half of scorers league-wide get a bonus win against "the median" and the bottom half get
   a bonus loss, on top of the real head-to-head result (2-0 if you beat both your opponent and
   the median; 1-1 if you're the 2nd-highest score in a week the highest scorer also plays in).
   The per-week math already existed in `median_record_calculator.py` and fed the Luck Analysis
   Bokeh chart; this section just presents its manager-level season totals (real/median/combined
   record) as a standalone, easy-to-read table (`median_standings_table()` in `src/ai_overview.py`,
   sourced from `output_data['median_standings']`, built in `main.py`).
7. **Top waiver pickups** — season-to-date and this-week leaders from the (now de-duplicated,
   FAAB-efficiency-aware) waiver analysis in §4.

Rendering uses the same Bears navy/orange light theme as the rest of the app (§10).

## 6. Performance plan

- `src/api_clients.py`: every request gets a `timeout=` and a `Retry`-backed `HTTPAdapter`
  (backoff on 429/500/502/503/504).
- Weekly Sleeper calls (matchups, transactions) and ESPN per-athlete detail lookups are batched
  through a `ThreadPoolExecutor` instead of one-at-a-time blocking loops — the ~720 sequential
  ESPN calls were the single biggest contributor to run time.
- Sleeper's `/players/nfl` (~5MB) and the ESPN stat-leader rankings are disk-cached with a 24h TTL
  via `AnalysisStorage.cache_get/cache_set`, matching Sleeper's own guidance to fetch it at most
  once a day.
- A fresh cached analysis for the same `(league_id, season)` is served without re-running the full
  pipeline unless the caller explicitly requests a refresh.

## 7. Azure migration prep (code/config only — no resources created)

- `src/storage.py`'s interface is the swap point for Azure Blob Storage later (implement a second
  class with the same methods; nothing else changes).
- `Dockerfile` + `.dockerignore` for App Service (Linux) container deployment.
- `.github/workflows/azure-webapp.yml` — deploy workflow gated on secrets that don't exist yet
  (documented, not wired to a real subscription).
- `AZURE_MIGRATION.md` — checklist covering App Service settings, storage decision, CORS
  allowlist, and the env vars that need to move from ad hoc `.env`/platform config into Azure App
  Settings.
- Dead `openai` dependency and `OPENAI_API_KEY` removed (no longer used per §2's AI Overview
  decision) — one less secret to provision.
- Python version pin reconciled across `netlify.toml` (was 3.9), `render.yaml`/`runtime.txt`
  (3.11) — standardized on 3.11.
- `league_config.json` contains real personal data (a real Sleeper username and league ID) and is
  currently tracked in git (the `.gitignore` rule for it is commented out). This is not rewritten
  automatically — flagged for the user to decide whether to scrub history.

## 8. Explicitly deferred (not in this pass)

- Automatic `previous_league_id` "league family" linking across seasons (user chose the simpler
  per-season model, §2).
- Real LLM-generated narrative in the AI Overview (user chose deterministic-only, §2).
- Actual Azure resource provisioning/deployment (no credentials available in this environment,
  §2).
- Rewriting the Bokeh *chart-building logic itself* (the figure/data-source/hover-tool code in
  `src/trade_analysis.py`, `src/power_rankings.py`, `src/visualizations.py`) — only the
  underlying data/scoring feeding those charts changes. The HTML/CSS *chrome* around each chart
  (explanation panels, leaderboards, page background) was re-themed in §10 to match the rest of
  the app, since that's presentation, not the analysis logic.

## 9. Results page UX (index.html / results_template.html)

Every generated report (League Overview, Power Rankings, Roster Grades, Luck Analysis, Trade
Analysis, Waiver Analysis, Manager Grades, Worst Trades) is its own standalone HTML file under
`html_reports/`, same as before. What changed is how they're presented to the user:

- **One scrollable page, not a grid of links that open new tabs.** `index.html`'s step 4 (and
  `results_template.html` for the static/Netlify build) renders a sticky pill nav
  (`#resultsNav`) plus one `<section>` per report, each embedding that report via `<iframe>` so
  you can scroll straight down through everything or click a nav pill to smooth-scroll to one.
  Every section also keeps an "Open full size ↗" link for when a chart wants more room than the
  iframe gives it.
- `REPORT_META`/`REPORT_ORDER` in `index.html` (and the hardcoded section list in
  `results_template.html`) is the canonical mapping from filename → display title/icon/order.
  Add a new report there when adding a new report type.
- `results_template.html`'s version checks each file exists (`fetch(..., {method: 'HEAD'})`)
  before embedding it, since a static build won't have every report for every league (e.g. no
  trades this season → no `trade_analysis_latest.html`) — shows a plain "not generated" note
  instead of a broken iframe.
- The Step 3 progress bar's text is deliberately *not* the literal backend status message
  anymore — `FUN_LOADING_MESSAGES` in `index.html` maps the same real progress-percent
  checkpoints to football-themed phrases ("Going for it on 4th down...", etc.) per explicit user
  request; the real message is still logged to the console for anyone who wants it.

## 10. Visual theme

Chicago Bears palette (navy `#0B162A` + orange `#C83803`) on a light canvas, applied consistently
across every surface the app renders:

- `index.html`, `results_template.html`: CSS custom properties (`--color-ink`, `--color-accent`,
  etc.) — see the `:root` block in either file for the full token list.
- `src/ai_overview.py`'s `render_ai_overview_html()`: the same token values, inlined (this HTML
  is generated server-side, so it can't share a CSS file with the frontend — token *values* are
  kept in sync manually, not the mechanism).
- The Bokeh-generated reports' HTML/CSS chrome (explanation panels, leaderboard tables, the
  worst-trades standalone page) — updated to the same palette. The Category20 chart-data palette
  (the actual per-manager line/dot colors inside each chart) and the gold/silver/bronze
  rank-medal colors were deliberately left alone — those are functional data encoding and
  universal medal colors, not decorative theme choices that were clashing.

## 11. Dev workflow

```bash
pip install -r requirements.txt
npm install
python server.py         # Flask dev server on :5000
# or, for the CLI/offline path against league_config.json:
python main.py
```
