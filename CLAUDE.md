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
| `src/api_clients.py` | Sleeper/ESPN HTTP clients — timeouts, retry/backoff, the bulk (`ThreadPoolExecutor`-backed) weekly matchup/transaction fetchers, draft-picks fetchers, and `ESPNAPI.get_preseason_draft_ranks()` (§5, Draft Rating). |
| `src/roster_grading.py` | ESPN-tier player grading; athlete/team/position `$ref` lookups are now parallelized and memoized. |
| `src/power_rankings.py` | Weekly power ratings + `compute_power_rank_history()` (persisted per-week rank series, used by the AI Overview). |
| `src/faab_analysis.py` | FAAB ledger reconstruction + relative-scarcity scoring (§4.3). Returns `{'enabled': False}` for non-FAAB leagues. |
| `src/trade_analysis.py` | Trade (§4.1) and waiver (§4.5) impact scoring plus the Bokeh chart builders — chart chrome dark-themed and reworked in the 2026-09 v2 redesign (§10). |
| `src/bokeh_theme.py` | Shared dark-theme styling for every Bokeh report (§10) — figure/legend colors, button/select stylesheets (the real shadow-DOM-reaching mechanism), the dark-optimized categorical palette. |
| `src/draft_analysis.py` | Draft Rating + Biggest Steals scoring (§5) — reconstructs actual draft results from Sleeper and scores them against ESPN's preseason rank. Rendered as its own "Draft Info" report/tab (§10), not part of the AI Overview. |
| `src/ai_overview.py` | The seven deterministic AI Overview sections (§5) + HTML rendering, plus `build_draft_info()`/`render_draft_info_html()` for the separate Draft Info report. No LLM call. |
| `src/median_record_calculator.py` | Median-based record calculation (unchanged logic; O(n²) lookups fixed, dead standalone `main()` removed). |
| `src/trade_value.py` | Hypothetical Trade Analyzer (§12) — values any currently-rostered player/FAAB for "what if" trades and renders the interactive `trade_analyzer.html` builder. Separate from `trade_analysis.py`, which scores trades that already happened. |

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

### 4.5 Waiver pickup scoring rewrite (2026-09) — position-adjusted points, not team-wide delta

**The problem.** `analyze_waiver_pickups()` originally scored every pickup with the exact
team-wide power-rating/roster-grade delta methodology that §1's audit called out and replaced for
trades (§4.1) — but that fix was never applied to waivers. `calculate_manager_power_impact()` /
`calculate_manager_grade_impact()` measured the *whole team's* trend in a window around the
transaction week, not anything about the player added: a great pickup and a bench stash scored
identically if the team's rating moved for unrelated reasons (bye week, blowout, injury) that
week; simultaneous moves in one week got the same number; pickups in a season's last 1-2 weeks
silently scored `0.0` (not enough before/after data) — indistinguishable from "did nothing." The
FAAB leaderboard's "$/point of impact" efficiency column inherited the same noise. Both helper
functions are now deleted.

**The fix.** `combined_impact` is now the actual fantasy points the added player(s) scored while
rostered, position-adjusted against the league-wide weekly average at that position — the
industry-standard "points over positional average" approach, not team noise:

1. **Rostered window** (`_build_drop_index()`, `_rostered_window_end()`): from the pickup's add
   week through the week before that same roster's next drop of that exact player (a trade's own
   `drops` map counts the same as a waiver drop — both mean "gave the player up"), or the last
   analyzed week if never given up.
2. **Position baseline** (`_build_weekly_position_baselines()`): for every week, the mean and
   population stdev of every rostered player's actual points at each position, league-wide —
   built from Sleeper's `players_points` (already flowing through `all_weekly_matchups`, previously
   discarded past the top-25/week trim used for the AI Overview's top-performers section).
3. **Per-player points lookup** (`_build_player_weekly_points()`): every player's points for every
   week, not just weeks they cracked a top-N list.
4. **Score** (`calculate_pickup_points_impact()`): for each week in the rostered window, weekly
   z-score `= (points - position_mean) / position_stdev` that week; `combined_impact` is the
   average z-score across every scored week (weeks with no data — bye/inactive/not yet played —
   are skipped, not treated as zero). A transaction with multiple simultaneous adds gets one score
   averaged across all of them, preserving the one-entry-per-transaction fix in §4.4. This also
   fixes the "can't score the last 1-2 weeks" bug — no *before* data is required anymore, only
   weeks the player was actually held.

**Downstream recalibration** (the new score is a z-score, typically roughly ±2.5, not the old
team-delta's tens-scale number):
- `calculate_manager_grades()`'s waiver-grade formula changed from `5 + impact / 3` to
  `5 + impact * 2.5` (so +1 std dev above a typical rostered player at that position swings the
  grade by 2.5).
- `create_waiver_visualization()`'s y-axis/reset-zoom range changed from `(-20, 25)` to `(-4, 4)`;
  the `power_impact`/`grade_impact` hover fields and chart columns were replaced with
  `weeks_rostered`/`total_points`; the methodology explanation panel and "how it's calculated"
  step list were rewritten to match the real formula (kept in sync per this file's own stated
  principle — see §4.1's "no more three divergent formulas/descriptions").
- The FAAB leaderboard's "Impact/$" efficiency ratio formula is unchanged (`total impact / total
  FAAB spent`) — same ratio semantics, just smaller displayed numbers now that the numerator is a
  z-score sum instead of a tens-scale delta sum.

## 5. AI Overview (deterministic)

New module `src/ai_overview.py` replaces `server.py`'s `create_ai_team_overview` /
`create_detailed_mock_overview` / `create_mock_ai_overview` and the dead `openai` import entirely.
Sections, each backed by data that is now actually persisted (previously fetched-then-discarded).
Items 1-7 render on the Overview report/tab (`ai_overview.html`); items 8-9 were split into their
own **Draft Info** report/tab (`draft_info.html`) in the 2026-09 v2 nav redesign (§10) — listed
here together since they're computed by the same module and documented as one unit:

1. **Top performers (week-interactive)** — head-to-head matchup winners for a selected week
   (manager vs. manager, not individual NFL players), ranked by winning score. Replaces the
   original "top individual NFL players" framing per explicit user feedback ("I don't care abt
   the highest scoring football players, I care about the head to head matchup winners").
2. **Biggest upsets** — each week's head-to-head margin compared against the two teams' power
   rank entering that week (from the newly-persisted per-week rank history, §5 data model below);
   a win by the lower-ranked team, weighted by rank gap and margin, is an upset.
3. **Power ranking movers: last week vs. this week** — a rank-delta table built directly from the
   per-week power-rating series already computed by `power_rankings.py` (previously computed
   ad hoc inside a Bokeh hover tooltip and never persisted; now extracted into its own
   `power_rank_by_week` structure saved to JSON).
4. **Matchups to watch** — the next unplayed week's pairings, scored by standings stakes (e.g. two
   teams within the playoff cutoff facing each other, or the current bubble teams — cutoff comes
   from the league's real `settings.playoff_teams`). Always about the real upcoming week, not
   week-interactive (see below for why this differs from the other week-based sections).
5. **Projected playoff bracket & standings (week-interactive)** — a seeded single-elimination
   bracket ("if the season ended after the selected week") plus the standings table it's seeded
   from. Supports Sleeper's three documented playoff field sizes (4/6/8 teams) with the correct
   bye placement (`nextPow2 - N` byes to the top seeds) and standard tournament seeding (e.g. for
   6 teams: round 1 is 3v6 and 4v5, round 2 is 1-vs-winner(4v5) and 2-vs-winner(3v6), keeping the
   top two seeds apart until the final). Any other field size falls back to a flat seed list
   instead of a fabricated bracket tree. Explicitly labeled as a snapshot projection, not a
   playoff-odds simulation.
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
8. **Draft Rating** (added 2026-09) — a per-manager 0-10 leaderboard of the actual startup draft,
   reconstructed from Sleeper's own draft-picks endpoint. `draft_rating = 0.7 * quality_score +
   0.3 * value_score` (weighted toward quality per explicit user direction). `quality_score` is
   `grade_roster()`'s `overall_grade` run on every player the manager drafted — the same
   ESPN-tier grading already used for weekly roster grades and trade valuation, so this reuses
   one consistent quality signal app-wide instead of introducing a new one. `value_score` is each
   manager's average (actual pick number − expected rank) discrepancy, z-scored against the rest
   of the league and mapped onto the 0-10 scale the same way the waiver rewrite (§4.5) maps
   z-scores to grades (`5 + z * 2.5`, clamped). "Expected rank" is documented in the note below.
9. **Biggest Steals** — the largest gaps, league-wide, between a player's actual draft pick number
   and their expected rank: `discrepancy = actual_pick_no − expected_rank`, so a large positive
   number means the player was still on the board long after they were expected to be gone.
   Players Sleeper's own data currently marks with any `injury_status` are excluded entirely, per
   explicit user request. `src/draft_analysis.py`'s `calculate_biggest_steals()` /
   `calculate_draft_ratings()` back both this and Draft Rating above from the same reconstructed
   draft + expected-rank data.

**"Expected rank" is ESPN's preseason expert-consensus rank, not real ADP — and that substitution
was deliberate, not a shortcut.** The user asked specifically for a player's ADP (average draft
position) vs. actual draft spot. ESPN's fantasy API (`lm-api-reads.fantasy.espn.com/apis/v3/...`,
the same provider already used for `grade_player()`'s rankings) does expose a public,
unauthenticated `ownership.averageDraftPosition` field — but it was checked against live data
before use and found broken: it returns a flat `170.0` placeholder for every player queried,
including consensus top overall picks, so it carries no real signal. The same response's
`draftRanksByRankType.STANDARD`/`.PPR` field was checked the same way and confirmed correct
(properly ordered, season-accurate preseason ranks). `ESPNAPI.get_preseason_draft_ranks()` in
`src/api_clients.py` uses that field, cached 7 days (preseason ranks don't change once a season
starts). The app's own UI text says "ESPN preseason rank," never "ADP," so this stays honest about
what the number actually is instead of mislabeling a proxy as the real thing. `main.py` picks
STANDARD vs. PPR rank per league based on `league_info['scoring_settings']['rec']`.

Sleeper's draft data itself comes from two new `SleeperAPI` methods: `get_league_drafts()` (a
normal redraft league has exactly one — no dynasty/keeper support, see §0) and
`get_draft_picks(draft_id)` (round, overall pick number, player, and the drafting roster for
every pick). `get_primary_draft()` in `src/draft_analysis.py` picks the completed one if more
than one draft object exists. Both sections degrade to an empty state (never a hard failure) if
the league didn't use Sleeper's own draft tool, or ESPN's preseason data isn't available for that
season.

**Week-interactive sections and the client-side rendering model:** Top Performers and the
Playoff Bracket/Standings need a "view this as of week N" picker (explicit user request). Rather
than round-trip to the server per week (there is no server for the static Netlify build — it's
just a generated HTML file), every week's match results (`matchup_results`, already collected in
`main.py`) are embedded as a JSON blob directly in `ai_overview.html`, and a small vanilla-JS layer
(no framework, no build step) recomputes standings-through-week and re-renders both sections
in-browser when the `<select>` changes. "Matchups to Watch" deliberately stays server-rendered and
non-interactive since it's inherently about the real upcoming week, not a historical one — making
it week-interactive too would need a different question ("what was upcoming as of week N")
that nobody asked for.

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
- Python version handling for **Netlify** vs. **Render** is not symmetric - they don't read the
  same file the same way, and mixing up their formats is exactly what broke both deploys in
  practice, twice:
  - **Netlify**: `runtime.txt` takes priority over everything else (over the `PYTHON_VERSION`
    build environment variable and over `Pipfile`). Its documented format is the **bare `X.Y`
    version with no `python-` prefix and no trailing newline** (e.g. a 4-byte file containing
    exactly `3.11`). This repo's `runtime.txt` had the Heroku/pyenv-style format
    (`python-3.11.*`, later `python-3.11.9`) left over from before this rewrite - Netlify's
    `mise`-based build image passed that literal string straight to `python-build`, which has no
    "python-3.11.*" or "python-3.11.9" definition, so the build failed with "definition not
    found" both times. `netlify.toml`'s `PYTHON_VERSION` was never actually the problem - it was
    always being silently overridden by the malformed `runtime.txt`.
  - **Render**: does not read `runtime.txt` at all. It only honors the `PYTHON_VERSION`
    environment variable (must be fully qualified, e.g. `3.11.9`) or a `.python-version` file.
    `render.yaml`'s `envVars: PYTHON_VERSION: 3.11.9` is correct as-is and unaffected by whatever
    `runtime.txt` contains.
  - Net result: `runtime.txt` = `3.11` (bare, Netlify's format), `render.yaml`'s `PYTHON_VERSION`
    = `3.11.9` (fully qualified, Render's format) - these look inconsistent side by side but each
    is correct for the platform that reads it.
- `league_config.json` contains real personal data (a real Sleeper username and league ID). It was
  tracked in git with the `.gitignore` rule for it commented out; both are now fixed (`git rm
  --cached` + uncommented the rule), so it stops being tracked going forward. Past commits still
  contain it — scrubbing git history was considered and explicitly declined (would need a
  history rewrite + force-push), so anyone with an existing clone can still see the old values in
  history.

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
  the app, since that's presentation, not the analysis logic. That same chrome's *mobile*
  responsiveness was fixed in a later pass — see the note in §9 below, which also covers a real
  architectural discovery (Bokeh's Shadow DOM) worth knowing before touching this chrome again.
- **JoeyBot** — a bot "similar to Sleeperbot" that shows up inside the Sleeper app itself. Not
  feasible as asked: Sleeper's API is explicitly documented as **read-only** ("you cannot modify
  contents via this API"), and there's no public/documented way for a third party to post into
  Sleeper's native in-app chat or league feed the way Sleeper's own first-party bot does — that
  surface simply isn't exposed to outside developers. The realistic version of "JoeyBot" is a
  **Discord bot** that lives in the league's Discord server (most fantasy leagues already have
  one) and posts/responds using the same data this app already computes — e.g. `/standings`,
  `/topperformers <week>`, `/bracket`, a weekly auto-post of the League Overview highlights — built
  as its own small service (a Discord gateway process, likely `discord.py` or `discord.js`) that
  calls this app's existing analysis output (JSON under `fantasy_analysis_output/`, or a small
  read-only API added to `server.py`) rather than recomputing anything. Deferred until the rest of
  this pass is live in production, per user ("eventually"); not started.

## 9. Results page UX (index.html / results_template.html)

Every generated report (League Overview, Draft Info, Power Rankings, Roster Grades, Luck Analysis,
Trade Analysis, Waiver Analysis, Manager Grades, Worst Trades) is its own standalone HTML file
under `html_reports/`, same as before. **As of the 2026-09 v2 redesign (§10), presentation is a
sidebar/tab-panel shell, not a scrolling stack** — the "one scrollable page with a sticky pill nav"
model described in older versions of this section is superseded:

- **A left rail (desktop) / slide-in drawer (mobile), one report visible at a time**, not a grid
  of links or an infinite scroll. `index.html`'s `#step4`/`.results-view` and the whole of
  `results_template.html` both build their nav + `.tab-panel`s from the same `NAV_GROUPS`
  structure (three labeled groups — see §10) and embed each report via `<iframe>` inside the
  active panel, same as before. Every panel also keeps an "Open full size ↗" link for when a
  chart wants more room than the iframe gives it.
- `NAV_GROUPS` in `index.html` (and the matching structure in `results_template.html`) is the
  canonical mapping from filename → display title/group. Add a new report there when adding a new
  report type — it needs an `id`, `title`, `file`, and (in `results_template.html`) a
  `description` shown above the embedded iframe.
- `results_template.html`'s version checks each file exists (`fetch(..., {method: 'HEAD'})`)
  before embedding it, since a static build won't have every report for every league (e.g. no
  trades this season → no `trade_analysis_latest.html`) — shows a plain "not generated" note
  instead of a broken iframe.
- The Step 3 progress bar's text is deliberately *not* the literal backend status message
  anymore — `FUN_LOADING_MESSAGES` in `index.html` maps the same real progress-percent
  checkpoints to football-themed phrases ("Going for it on 4th down...", etc.) per explicit user
  request; the real message is still logged to the console for anyone who wants it.
- **Mobile scrolling fix:** each embedded report's `<iframe>` used to have a fixed height (820px
  desktop / 600px mobile). Any report taller than that got its *own* internal scrollbar, and on
  mobile a finger-swipe that starts over the iframe rectangle scrolls the iframe instead of the
  outer page — this is what made scrolling through results "look like crap" on a phone. Fixed by
  `wireIframeAutosize()` in both `index.html` and `results_template.html`: on load (and via
  `ResizeObserver` afterward, since Bokeh content can reflow asynchronously), it reads the
  iframe's own `contentDocument.documentElement.scrollHeight` (same-origin, no postMessage needed)
  and sets `iframe.style.height` to match exactly — so the iframe never has internal vertical
  overflow to trap a swipe, and the outer page is the only scrollable container. `html, body` also
  got `overflow-x: hidden` as a safety net against any one wide element (a chart, a table) causing
  the whole page to scroll sideways; every individual wide element has its own `overflow-x: auto`
  container so it scrolls in place instead of being clipped by that safety net —
  `.result-section-frame-wrap` for embedded reports, `.bracket` for the playoff bracket, and
  `.table-scroll` (wrapping every `<table>` `ai_overview.py` generates, both server-rendered and
  the week-interactive client-side ones) discovered while verifying real league data on a 375px
  viewport: a wide table (long player names, a 5-6 column waiver/median-standings table) was
  measurably wider than its card and got silently clipped by the new page-level
  `overflow-x: hidden` before `.table-scroll` was added.
- **The Bokeh chart chrome's mobile fix, and why it's done the way it is.** A background audit
  found 18 confirmed mobile-responsiveness bugs across `src/trade_analysis.py`,
  `src/power_rankings.py`, and `src/visualizations.py`'s HTML/CSS chrome (fixed-width `Div`
  panels, a leaderboard-beside-chart `row()` that never fit a 375-414px phone, button toolbars
  that overflowed and were under the ~44px touch-target minimum). Fixing this took two rounds,
  and the second round is the load-bearing lesson:
  1. **First attempt (didn't work): fix it with a `<style>` block.** The obvious approach —
     inject CSS targeting `.bk-root`, `.bk-btn`, `.bk-root table`, etc. after the fact (this is
     what `visualizations.py`'s old private `_make_html_mobile_friendly()` did, and it was never
     even applied to the other two files). **This doesn't work at all against the Bokeh version
     actually installed (3.9.2, satisfying the `bokeh>=2.4.0` pin).** Confirmed empirically by
     walking the real rendered DOM of a generated report: it has **72 shadow roots** — Bokeh 3.x
     renders every widget (buttons, Divs, layouts) inside Shadow DOM. `document.querySelector('.bk-root')`
     returns `null`; the only `bk-*` classes present anywhere are `bk-Column`/`bk-Notifications`.
     A `<style>` tag in the page's light-DOM `<head>` cannot style anything inside a shadow root,
     so every one of those selectors was a dead rule - not "slightly wrong class name for this
     Bokeh version", genuinely unreachable by design.
  2. **What actually works:** set `sizing_mode="stretch_width"` and `height=44` directly on the
     Bokeh models in Python (`Div`, `Button`, `row`/`column`), and change the
     chart-beside-leaderboard `row(chart, leaderboard)` to `column(chart, leaderboard)` (always
     stacked, not just below a breakpoint - Bokeh has no CSS-media-query-driven "become a column
     under 768px" concept to hook into, and guessing at its internal grid/flex class names to fake
     one is exactly the dead-end above). These are real Bokeh model properties, rendered by
     Bokeh's own internal (shadow-scoped) styling — not external CSS trying to reach in — so they
     work regardless of the shadow DOM boundary. Verified by measuring real rendered output: both
     toggle buttons at exactly `height: 44`, the outer layout's real computed
     `display:flex; flex-direction:column` with width matching the viewport exactly.
  3. **The one remaining wrinkle: leaderboard tables wider than their card.** Even after the
     above, a table with enough columns/content (e.g. the trade-performance leaderboard) can still
     be wider than its `Div`. The fix has to live *inside the Div's own HTML string* (the one
     place a shadow root doesn't block anything, since it's content Bokeh renders as-is) - wrap the
     table in `<div style="...overflow-x:auto...">` at the point each file builds `leaderboard_html`.
     The wrapper's width can't be `100%`: its real parent turned out to be Bokeh's own
     `.bk-clearfix` (also shadow-scoped), which is `display: inline-block` and shrinks to fit its
     content - so a percentage width has no real containing block to resolve against and silently
     collapses back to the table's own (too-wide) size. `width: 100vw` sidesteps that circularity
     entirely (viewport units don't need a containing block) and is a safe proxy here specifically
     because the column-stacking fix above means this Div always ends up spanning the full
     available width. Verified: the wrapper now measures `clientWidth` matching the viewport with
     a genuinely larger `scrollWidth`, i.e. real, working internal horizontal scroll.
  4. `src/bokeh_mobile.py` is what's left of the CSS-based approach - a shared
     `make_bokeh_html_mobile_friendly()` (replacing the old duplicated/broken per-file version)
     that only sets a viewport meta tag and `overflow-x: hidden` on `html`/`body`, since those two
     elements are one level *above* Bokeh's own root and are genuinely light-DOM.
  5. `create_worst_trades_html_report()` in `trade_analysis.py` is a fully separate code path -
     hand-authored static HTML via an f-string, not Bokeh's `output_file()`/`show()` - so it has no
     shadow DOM at all, and a normal `.table-scroll { overflow-x: auto }` CSS class (plus
     `.impact-stats { flex-wrap: wrap }` at the existing mobile breakpoint) works exactly as
     expected there.
  All of the above was verified against a real full pipeline run (`python main.py` equivalent)
  against real league data, not synthetic fixtures, rendered at a real 375px viewport.

## 10. Visual theme

**Design system v2 (2026-09 "broadcast scoreboard" redesign)** replaced the earlier light
Apple-style pass entirely, per explicit user direction: less white, a real navigation shell, more
readable/relocated chart chrome, mobile as the primary target. This section describes the current
theme; v1's light-canvas Apple-reference approach (alternating white/gray bands, `--color-ink`
navy-on-white, Inter-only type) is superseded, not layered on top of.

**Palette** — dark navy void, not neutral charcoal (stays recognizably "Bears," not a generic dark
dashboard): `--void: #070D18` (page background), `--surface: #101B2D` (cards/panels),
`--surface-raised: #18283F` (hover/active state), `--ink: #F4F6FA` / `--ink-muted: #8DA0BC` (text),
`--accent: #FF6A2B` (brightened Bears orange — the original `#C83803` loses contrast on navy;
`#C83803` survives as `--accent-deep` for gradients), `--line: rgba(255,255,255,0.08–0.14)`
(hairlines), `--good: #34D399` / `--bad: #F87171` (stat deltas, tuned for dark backgrounds). A
background layer (`body::before` in `index.html`/`results_template.html`) adds two soft radial
accent glows plus a very-low-opacity diagonal hash pattern — a quiet yard-line nod, not literal —
per explicit user request to add background depth instead of a flat void.

**Type** — two faces with distinct jobs, not one face doing everything: **Oswald** (condensed,
weight 600) for headlines, nav labels, and section titles; **Inter** for body copy, tables, and
data (small-size legibility). Both loaded via Google Fonts in every page/report that renders text
(`index.html`, `results_template.html`, `src/ai_overview.py`, and — since the worst-trades report
is hand-authored HTML, not Bokeh — `create_worst_trades_html_report()` in `trade_analysis.py`).

**Navigation shell — the headline structural change.** The old model (every report stacked on one
long scroll, or a sticky pill nav that just smooth-scrolled down the same page) is replaced by a
real left rail (desktop, persistent, ≥960px) that collapses to a slide-in drawer (mobile, triggered
by a hamburger button in a sticky top bar) — "a card you hit on the left side to navigate tabs,"
per explicit user request. One report/tab-panel is visible at a time (`.tab-panel.active`), not an
infinite scroll. Both `index.html` (`#step4`/`.results-view`) and `results_template.html` implement
this with the same `NAV_GROUPS` structure: reports grouped into **Overview** (Overview, Draft Info),
**Team Analysis** (Power Rankings, Power Ranking Leaderboard, Roster Grades, Luck Analysis), and
**League Activity** (Trade Analysis, Waiver Analysis, Manager Grades, Worst Trades) — grouping ten
reports into three labeled clusters so the sidebar doesn't read as an undifferentiated wall, per
explicit "easy and not overwhelming to navigate" request. Clicking a nav item toggles which
`.tab-panel` has `.active` (CSS `display` + a `panelIn` fade/slide-up animation) and auto-closes
the mobile drawer. "Draft Info" is its own tab now (`src/ai_overview.py`'s `build_draft_info()` /
`render_draft_info_html()`, written to `draft_info.html`) — pulled out of the AI Overview page,
which used to bundle it in with Top Performers/Upsets/etc. (see §5).

**Bokeh chart chrome — no longer deferred.** §9's Shadow DOM finding (external `<style>` tags
can't reach Bokeh 3.x's internally-rendered widgets) is still true, but this pass discovered the
actual supported escape hatch: passing `stylesheets=[InlineStyleSheet(css=...)]` directly to a
Bokeh model injects CSS into *that model's own* shadow root and does work — verified empirically
(a themed Button/Select/figure rendered exactly as configured) before committing to it. That
unlocks real dark-theme restyling of every Button/Select/Legend, not just the Python
model-property tricks (`height`, `sizing_mode`) §9 already used. `src/bokeh_theme.py` centralizes
this: `style_figure()` (background/border/grid/axis colors — plain Bokeh model properties, always
worked, just weren't dark before), `style_legend()`, `button_stylesheet()` (`primary`/`ghost`/
`muted` variants), `select_stylesheet()`/`multiselect_stylesheet()`/`slider_stylesheet()` for
future selector widgets, `dark_palette()` (a curated 20-color categorical set — Bokeh's default
`Category20` is tuned for a white background and several of its hues are nearly invisible on navy;
this is a motivated exception to the "leave the chart-data palette alone" rule, since it was
written for a light-canvas page and the whole page changing to dark is exactly the kind of change
that rule anticipates revisiting), and shared Div-HTML style strings (`PANEL_STYLE`,
`CALLOUT_STYLE`, `HEADING_STYLE`, `DESCRIPTION_STYLE`, `LABEL_STYLE`) for the explanation/
leaderboard panels every chart builds as raw HTML (light-DOM content strings, never blocked by
shadow DOM — see §9). Applied across every chart-producing function actually wired into
`main.py`'s pipeline: `power_rankings.py::create_power_rating_plot`,
`visualizations.py::create_roster_grade_plot`/`create_luck_analysis_plot`/
`create_power_ranking_leaderboard`, and `trade_analysis.py::create_trade_visualization`/
`create_waiver_visualization`/`create_manager_grade_visualization`/
`create_worst_trades_html_report` (the last one is hand-authored HTML, not Bokeh, so it's a plain
CSS edit with none of the shadow-DOM caveats). `create_combined_analysis_plot` and
`create_trade_impact_visualization` in `visualizations.py` are dead code (not imported by
`main.py`) and were left untouched.

Three concrete fixes came out of this pass, each explicitly requested:
- **Descriptions made larger and repositioned.** Every chart's methodology/explanation text moved
  from a small muted caption into a prominent, larger-font panel (`DESCRIPTION_STYLE`, 16px) placed
  at the top of the report, above the chart — not buried in a collapsed-by-default panel below it.
- **Built-in buttons relocated.** Every chart's toggle/reset button row moved from the bottom of
  the layout to directly under the description, above the chart/leaderboard.
- **A real mobile bug found and fixed along the way:** Bokeh's `row()` has no flex-wrap. A
  `sizing_mode="stretch_width"` row of 3+ buttons doesn't wrap on a narrow phone screen — the
  labels visually overlap instead (confirmed by rendering and screenshotting at 375px). Every
  3-or-4-button control row across all four affected functions was changed to a 2-per-row grid
  (nested `bokeh_column`/`bokeh_row`), the same "stack unconditionally, don't rely on breakpoints"
  philosophy §9 already used for chart-vs-leaderboard layout — Bokeh has no CSS-media-query
  concept to hook a real responsive breakpoint into, so a version-independent structural fix beats
  trying to detect viewport width from Python.
- Side-panel legends (`p.add_layout(legend, 'right')`) were moved to render *inside* the plot
  frame (`location="top_left"`/`"bottom_right"`, no side argument) instead — an outside side panel
  adds its own fixed pixel width alongside the frame that `stretch_width` can't compensate for,
  which was silently making every affected chart wider than a phone viewport.

The Category20-replacement (`dark_palette()`) and the gold/silver/bronze medal colors remain the
same category of exception noted in earlier passes: functional data encoding / universal medal
colors, not decorative theme choices — medal colors specifically were left as literal gold/silver/
bronze hex values even inside the new dark theme (`create_power_ranking_leaderboard`).

## 11. Dev workflow

```bash
pip install -r requirements.txt
npm install
python server.py         # Flask dev server on :5000
# or, for the CLI/offline path against league_config.json:
python main.py
npm run build && npm run serve   # static preview of the CLI output, on :3000
```

The `npm run build`/`serve` path exercises the same static-Netlify code path described in §0 —
`npm run build` runs `build.js` to copy `main.py`'s output into `dist/`, `npm run serve` serves
`dist/` locally. See [DEV_GUIDE.md](DEV_GUIDE.md) for the full set of `npm run` commands.

## 12. Hypothetical Trade Analyzer (2026-09)

A new report, `trade_analyzer.html`, distinct from everything else in §5/§9's report list: it
values a trade that **hasn't happened** — "is this worth it before I hit send" — rather than
scoring one that already did (that's `trade_analysis.py`, untouched by this work). Added per
explicit user request, modeled on how tools like RotoTrade, FantasyCalc, and DraftSharks'
trade calculators work (researched before building — see below), but computed entirely from
data this app already collects, with no new external API or paid projections dependency.

**Player value.** Established trade calculators converge on "Value Over Replacement" — a
player's recent/projected fantasy points compared against a position baseline — for player
value, and variance for floor/ceiling. `src/trade_value.py::calculate_player_trade_values()`
builds exactly that from data already flowing through `main.py`, reusing two helpers
`analyze_waiver_pickups()` already built rather than duplicating them:
`_build_player_weekly_points()` and `_build_weekly_position_baselines()` (both imported from
`trade_analysis.py`). For every currently-rostered QB/RB/WR/TE (kickers/DST have no ESPN-tier
grade or meaningful position baseline here, so they're excluded rather than given a fabricated
value):

- **Recent form** — the last 4 played weeks' points (`RECENT_WEEKS_WINDOW`), position-adjusted
  into a z-score against the league-wide weekly baseline at that position, the same way a
  waiver pickup is scored (§4.5). Mapped onto the familiar 0–10 scale via `5 + z × 2.5`, the
  same constant (`VALUE_Z_SCORE_SCALE`) waiver and draft scoring already use.
- **Season-long quality** — the player's existing ESPN-tier grade (`grade_player()`, the same
  1–10 scale used everywhere else in this app for roster/trade/draft grading).
- **Trade value** blends the two, `0.6 × recent-form-grade + 0.4 × ESPN-tier-grade`
  (`RECENT_FORM_WEIGHT`) — recency weighted higher than Draft Rating's 0.7/0.3 quality/value
  split (§5 item 8), since Draft Rating is a preseason snapshot where quality should dominate,
  while an in-season trade should care more about how someone's playing right now — but not
  entirely, so one flukey week can't fully override an established quality level.
- A player with zero recorded points across every recent week (hurt/inactive the whole window)
  falls back to their ESPN-tier grade alone rather than being zeroed out, which would
  undervalue a good player who has simply been out.
- **Floor/ceiling** are that same player's recent-weeks points, mean ± one population standard
  deviation — a real volatility measure from their own actual game log, not a projected range.

**FAAB value.** Converted into the same grade-point scale so it can be added directly into a
trade leg's value, using *this league's own* empirically observed "value per dollar spent" —
`calculate_faab_value_per_dollar()` divides the total scored impact of every FAAB-funded waiver
pickup this season (already computed by `analyze_waiver_pickups()`) by the total FAAB spent on
them, rather than an arbitrary flat conversion. Falls back to a documented constant
(`DEFAULT_FAAB_VALUE_PER_DOLLAR = 0.05`) when a league hasn't spent enough yet to trust its own
rate (`MIN_FAAB_SPENT_TO_CALIBRATE = $20` total), or when that observed rate would be
non-positive — a league whose FAAB spends happened to score below average on balance says
something about that league's bidding, not about the intrinsic value of holding FAAB, so it's
never allowed to make FAAB a trade *liability*. Only computed/shown for FAAB leagues
(`is_faab_league()`, same gate as §4.3).

**Multi-team trades.** Sleeper supports 3+ team trades, so the builder does too (2–5 teams, one
card per team). Fairness is just each team's own net value — value received minus value given
up, players and FAAB together — the same per-manager attribution `trade_analysis.py` already
uses for real 3+ team trades (§4.1), not a bespoke N-way fairness algorithm. Every asset (a
player checkbox, a FAAB amount) gets its own "send to" destination picker so an arbitrary
routing between any number of teams is representable, not just "the rest of the trade."

**Architecture.** A `<select>`-and-checkbox builder, entirely client-side and self-contained —
`build_trade_analyzer_data()` embeds every tradable player's value/floor/ceiling and every
team's roster/FAAB balance as one JSON blob directly in the page, and vanilla JS (no framework,
no build step) does the routing math and re-renders live as selections change. This is the same
pattern §5 already established for the AI Overview's week-interactive sections, for the same
reason: it has to work on the static Netlify build too, where there's no server to round-trip
to. Rendering (`render_trade_analyzer_html()`) reuses `ai_overview.py`'s `_page_shell()` for
page chrome, so it matches the rest of the app's look with no duplicated boilerplate. Wired into
`main.py`'s pipeline the same way Draft Info is — written to `trade_analyzer.html`, wrapped in a
try/except so a failure here never breaks the rest of the run — and added to both `index.html`
and `results_template.html`'s `NAV_GROUPS` under a new **Tools** group (distinct from **League
Activity**, since this is an interactive tool, not a computed report about what already
happened).

**Mobile.** Built mobile-first from the start rather than retrofitted: team cards stack full
width (never side-by-side), the roster checklist has its own `overflow-y: auto` so a 15-player
list doesn't blow out the page, a search box filters that list for a long roster, and every
value/floor/ceiling/destination-picker row was verified at a real 375px viewport during
development, not just assumed to reflow correctly.

**What was checked before building this:** RotoTrade.com's actual page couldn't be fetched
directly (blocks automated requests), so its documented behavior and the broader trade-calculator
landscape (FantasyCalc, DraftSharks, KeepTradeCut, DynastyCalc/RedraftCalc's multi-team support)
were researched via search instead — the Value-Over-Replacement/variance-for-volatility approach
above is what that research converged on, not a guess.
