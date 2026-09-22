# Handoff — 2026-09-21

Context for the next chat session picking up this repo. Read [CLAUDE.md](CLAUDE.md) first — this
file is just "what happened most recently and what's next," not durable architecture doc (that's
what CLAUDE.md is for, and this session updated it too — see its new §4.6).

## What just happened

The user reported the start/sit feature on joeyfantasy.com "isn't working right now." Investigated
and found the Manager Grades panel's "start/sit accuracy (15%)" component was never actually
implemented — `calculate_manager_grades()` in `src/trade_analysis.py` faked it from team-wide power
rating vs. league average, completely disconnected from any real lineup decision, despite the
panel's own on-page text promising "optimal lineup decisions vs. actual ones." An unused
`matchup_data` parameter (never even passed from `main.py`) was the tell that this was dead code,
not a working feature with a bug.

Fixed it for real, verified against the user's own real 2025 league data
(`league_config.json` → league `1257055438235516928`, fetched directly from Sleeper's public API,
not synthetic fixtures):

- **New file:** `src/lineup_analysis.py` — solves each manager's actual-best-possible lineup per
  week (Hungarian algorithm via `scipy.optimize.linear_sum_assignment`, using the league's real
  `roster_positions` including FLEX-type slots) and compares it to what they actually started.
- **Verified correctness by hand** before trusting it: manually computed one real week's optimal
  lineup from raw Sleeper JSON (128.1 optimal vs. 108.4 actual — a real "should've started Javonte
  Williams over Tee Higgins/Nico Collins" mistake) and confirmed the solver reproduced it exactly.
  Then ran the full season across all 12 real managers and got a plausible 78.9%–91.6% efficiency
  spread (matches published "lineup efficiency" ranges from other fantasy tools).
- **Found and fixed a second, subtler bug** while verifying: the season-summary score was
  averaging each week's *already-clamped* 0-10 grade, which let one catastrophic week (e.g. a
  near-empty lineup) get "forgiven" at the clamp floor — a manager with real 83.5% season
  efficiency was outranking one at 87.8% until this was fixed. Fixed by averaging the *raw,
  unclamped* per-week z-scores first and clamping once at the end, matching how waiver z-scores
  are already (correctly) handled elsewhere in the same file.
- Wired into `main.py` (`calculate_lineup_efficiency()` called right before
  `calculate_manager_grades()`, replacing the dead `matchup_data` param with real
  `lineup_efficiency_data`).
- Manager Grades chart (`create_manager_grade_visualization()`) now shows the real number, not
  just a derived grade: new "Start/Sit %" leaderboard column and hover tooltip field
  (`@lineup_efficiency_pct` → "NN.N% of optimal points started"), plus an explanation line in the
  methodology panel. This follows the same "never collapse a score to something opaque — show the
  raw components too" philosophy CLAUDE.md already documents for FAAB (§4.3).
- Added `scipy` as an explicit `requirements.txt` dependency (was only present transitively via
  scikit-learn before — fragile to rely on that staying true).
- Documented all of this as new CLAUDE.md §4.6, and added `src/lineup_analysis.py` to the §0.1 key
  files table.

**Full detail — formulas, the exact bugs, why each fix works — is in CLAUDE.md §4.6, not repeated
here.** This file is a pointer, not a duplicate.

## Verification performed this session

- `python -m py_compile` on all changed files — clean.
- Existing test suite re-run and still passes unchanged: `src/tests/test_manager_grades.py`,
  `src/tests/test_new_system.py` (both call `calculate_manager_grades()` without the new
  `lineup_efficiency_data` arg — confirms the default-`None` path still works for callers that
  don't pass it).
- Ad hoc scripts (not committed — were run from the scratchpad temp dir and cleaned up) pulled
  real data directly from Sleeper's public API for the league in `league_config.json` and ran the
  new module end-to-end, including generating a real `manager_grades.html` Bokeh chart and
  visually confirming the hover tooltip and leaderboard column render correctly in-browser.
- Did **not** run the full `main.py`/`server.py` pipeline end-to-end (that needs ESPN rankings +
  all the other pipeline stages, not just this one). The manager-grades slice was tested in
  isolation with real Sleeper data; worth a full pipeline run before the next deploy if one hasn't
  happened since this landed.

## Not done / possibly worth flagging to the user

- Did not touch `trade_performance`/`waiver_performance` season summaries, which have the *same*
  "average pre-clamped per-item scores" pattern that was wrong for lineup — except there the unit
  being averaged is "per trade" / "per waiver transaction," not "per week," so a single outlier
  transaction hitting the clamp floor is far less likely to swing the average the way an entire
   0%-efficiency *week* can. Not in scope for this fix (user asked specifically about start/sit),
  but if a similar "my grade looks wrong" report comes in about trade/waiver performance specifically,
  this is the first place to look.
- The `create_manager_grade_visualization()` leaderboard's "Grade" column sorts by `enhanced_overall`
  (a display-only z-score-amplified transform of `weekly_grades`, unrelated to the
  `lineup_performance` stat this session fixed) — two managers can appear in a slightly
  counterintuitive order there when their real grades are within ~0.01 of each other. Not a bug,
  just a pre-existing display quirk noticed in passing; not changed.

## Repo state

All changes are **uncommitted in the working tree as of this handoff being written** — this
session's user message asked to commit this work and write this file in the same step, so by the
time you're reading this from git history, they're already committed. If for some reason they're
not (e.g. this file survived but the commit didn't), the diff is: `CLAUDE.md`, `main.py`,
`requirements.txt`, `src/trade_analysis.py` modified, `src/lineup_analysis.py` new.

Branch: `frontend/apple-redesign`. Working tree was clean before this session started.
