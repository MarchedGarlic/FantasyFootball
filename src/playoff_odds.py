#!/usr/bin/env python3
"""
Playoff Odds / Championship Odds - a Monte Carlo simulation of the rest of the regular season
plus the playoff bracket, run from data this app already has: real results so far, plus each
manager's own actual weekly scoring distribution (mean/stdev) for the games that haven't been
played yet. Explicit user request, one of the "what do other fantasy sites have" brainstorm
ideas the user picked to build out.

Deliberately a fixed-seed simulation, not per-run randomness: this app's own stated principle
(CLAUDE.md section 1) is that non-reproducible randomness (the old trade-analysis
`random.uniform()` bug) is a bug, not a feature - re-running the same analysis for the same
league/week should show the same odds, not jitter around because of an unseeded RNG.

Reuses the same bracket seeding/pairing structure as the AI Overview's client-side projected
bracket (section 5's BRACKET_TEMPLATES, ported here from JS to Python) so the two features never
disagree about how a 4/6/8-team field is seeded, and the same wins-desc/points-for-desc standings
tiebreak the client-side standings table already uses.
"""

import random
import statistics
from collections import defaultdict

DEFAULT_TRIALS = 10000
SIMULATION_SEED = 20260910  # fixed for reproducibility - see module docstring
MIN_STDEV_FLOOR = 5.0  # keeps a team with only 0-1 real data points from simulating as a lock

# Seed pairings for Sleeper's three documented playoff field sizes, ported from the same
# BRACKET_TEMPLATES the AI Overview's client-side projected bracket uses (src/ai_overview.py) -
# 'seed' is a 1-indexed standings position, 'winner_of' is (round_index, match_index) into
# already-simulated rounds. Any other field size has no bracket tree (matches the client-side
# fallback) - only the playoff-odds (making the field) numbers are meaningful for those leagues.
BRACKET_TEMPLATES = {
    4: [
        [{'a': {'seed': 1}, 'b': {'seed': 4}}, {'a': {'seed': 2}, 'b': {'seed': 3}}],
        [{'a': {'winner_of': (0, 0)}, 'b': {'winner_of': (0, 1)}}],
    ],
    6: [
        [{'a': {'seed': 3}, 'b': {'seed': 6}}, {'a': {'seed': 4}, 'b': {'seed': 5}}],
        [{'a': {'seed': 1}, 'b': {'winner_of': (0, 1)}}, {'a': {'seed': 2}, 'b': {'winner_of': (0, 0)}}],
        [{'a': {'winner_of': (1, 0)}, 'b': {'winner_of': (1, 1)}}],
    ],
    8: [
        [{'a': {'seed': 1}, 'b': {'seed': 8}}, {'a': {'seed': 4}, 'b': {'seed': 5}},
         {'a': {'seed': 3}, 'b': {'seed': 6}}, {'a': {'seed': 2}, 'b': {'seed': 7}}],
        [{'a': {'winner_of': (0, 0)}, 'b': {'winner_of': (0, 1)}},
         {'a': {'winner_of': (0, 2)}, 'b': {'winner_of': (0, 3)}}],
        [{'a': {'winner_of': (1, 0)}, 'b': {'winner_of': (1, 1)}}],
    ],
}


def _next_pow2(n):
    p = 1
    while p < n:
        p *= 2
    return p


def _team_score_stats(matchup_results, completed_week, manager_names):
    """{user_id: {'mean', 'stdev'}} from real weekly scores through completed_week - the
    distribution each manager's remaining/playoff games are simulated from. A manager with too
    little real data (new-ish league, or simulating from week 1) falls back to the league-wide
    mean/stdev rather than a zero-variance guess."""
    scores_by_user = defaultdict(list)
    for week, matchups in (matchup_results or {}).items():
        if completed_week is not None and week > completed_week:
            continue
        for m in matchups or []:
            for uid, score in zip(m.get('user_ids', []), m.get('scores', [])):
                if uid is not None and score and score > 0:
                    scores_by_user[uid].append(score)

    all_scores = [s for scores in scores_by_user.values() for s in scores]
    league_mean = statistics.mean(all_scores) if all_scores else 100.0
    league_stdev = statistics.pstdev(all_scores) if len(all_scores) > 1 else MIN_STDEV_FLOOR

    stats = {}
    for uid in manager_names:
        scores = scores_by_user.get(uid, [])
        if len(scores) >= 2:
            stats[uid] = {'mean': statistics.mean(scores), 'stdev': max(statistics.pstdev(scores), 1.0)}
        elif len(scores) == 1:
            stats[uid] = {'mean': scores[0], 'stdev': league_stdev}
        else:
            stats[uid] = {'mean': league_mean, 'stdev': league_stdev}
    return stats


def _current_standings(matchup_results, completed_week, manager_names):
    """{user_id: {'wins', 'losses', 'ties', 'points_for'}} through completed_week - the real
    record every simulated trial starts from."""
    standings = {uid: {'wins': 0, 'losses': 0, 'ties': 0, 'points_for': 0.0} for uid in manager_names}
    for week, matchups in (matchup_results or {}).items():
        if completed_week is not None and week > completed_week:
            continue
        for m in matchups or []:
            uids = m.get('user_ids', [])
            scores = m.get('scores', [])
            if len(uids) != 2 or len(scores) != 2:
                continue
            u1, u2 = uids
            s1, s2 = scores or (0, 0)
            if u1 not in standings or u2 not in standings:
                continue
            standings[u1]['points_for'] += s1 or 0
            standings[u2]['points_for'] += s2 or 0
            if not s1 and not s2:
                continue  # unplayed/forfeited matchup - not a real result either way
            if s1 > s2:
                standings[u1]['wins'] += 1
                standings[u2]['losses'] += 1
            elif s2 > s1:
                standings[u2]['wins'] += 1
                standings[u1]['losses'] += 1
            else:
                standings[u1]['ties'] += 1
                standings[u2]['ties'] += 1
    return standings


def _remaining_regular_season_weeks(matchup_results, completed_week, playoff_week_start):
    if not matchup_results:
        return []
    last_regular_week = (playoff_week_start - 1) if playoff_week_start else max(matchup_results.keys())
    start_week = (completed_week + 1) if completed_week is not None else min(matchup_results.keys())
    return [w for w in sorted(matchup_results.keys()) if start_week <= w <= last_regular_week]


def _remaining_matchups_by_week(matchup_results, remaining_weeks):
    by_week = {}
    for week in remaining_weeks:
        pairs = []
        for m in matchup_results.get(week, []) or []:
            uids = m.get('user_ids', [])
            if len(uids) == 2 and uids[0] is not None and uids[1] is not None:
                pairs.append((uids[0], uids[1]))
        by_week[week] = pairs
    return by_week


def _resolve_slot(slot, seeds, round_winners):
    if 'seed' in slot:
        return seeds[slot['seed'] - 1]
    r, i = slot['winner_of']
    return round_winners[r][i]


def _draw_score(user_id, score_stats, rng):
    return max(0.0, rng.gauss(score_stats[user_id]['mean'], score_stats[user_id]['stdev']))


def _simulate_bracket(seeds, score_stats, rng):
    """seeds: ordered list of user_id, index 0 = the #1 seed. Returns the champion's user_id, or
    just the #1 seed if this field size has no bracket template (matches the client-side
    projected bracket's own fallback for an unsupported field size)."""
    template = BRACKET_TEMPLATES.get(len(seeds))
    if not template:
        return seeds[0] if seeds else None

    round_winners = []
    for round_matches in template:
        this_round = []
        for match in round_matches:
            a = _resolve_slot(match['a'], seeds, round_winners)
            b = _resolve_slot(match['b'], seeds, round_winners)
            score_a, score_b = _draw_score(a, score_stats, rng), _draw_score(b, score_stats, rng)
            this_round.append(a if score_a >= score_b else b)
        round_winners.append(this_round)
    return round_winners[-1][0]


def simulate_playoff_odds(matchup_results, manager_names, playoff_teams_count, playoff_week_start,
                           completed_week, trials=DEFAULT_TRIALS, seed=SIMULATION_SEED):
    """Run the Monte Carlo simulation and return a JSON-serializable summary, one row per
    manager, sorted by playoff odds descending."""
    score_stats = _team_score_stats(matchup_results, completed_week, manager_names)
    base_standings = _current_standings(matchup_results, completed_week, manager_names)
    remaining_weeks = _remaining_regular_season_weeks(matchup_results, completed_week, playoff_week_start)
    remaining_matchups = _remaining_matchups_by_week(matchup_results, remaining_weeks)

    num_byes = max(0, _next_pow2(playoff_teams_count) - playoff_teams_count) if playoff_teams_count else 0
    has_bracket_template = playoff_teams_count in BRACKET_TEMPLATES

    rng = random.Random(seed)
    playoff_count = defaultdict(int)
    bye_count = defaultdict(int)
    seed_sum = defaultdict(float)
    champ_count = defaultdict(int)

    for _ in range(trials):
        wins = {uid: base_standings[uid]['wins'] for uid in manager_names}
        points = {uid: base_standings[uid]['points_for'] for uid in manager_names}

        for week in remaining_weeks:
            for u1, u2 in remaining_matchups.get(week, []):
                s1, s2 = _draw_score(u1, score_stats, rng), _draw_score(u2, score_stats, rng)
                points[u1] += s1
                points[u2] += s2
                if s1 > s2:
                    wins[u1] += 1
                elif s2 > s1:
                    wins[u2] += 1

        ranked = sorted(manager_names.keys(), key=lambda uid: (-wins[uid], -points[uid]))
        seeds = ranked[:playoff_teams_count]
        for i, uid in enumerate(seeds):
            playoff_count[uid] += 1
            seed_sum[uid] += (i + 1)
            if i < num_byes:
                bye_count[uid] += 1

        if has_bracket_template and len(seeds) == playoff_teams_count:
            champion = _simulate_bracket(seeds, score_stats, rng)
            if champion:
                champ_count[champion] += 1

    results = []
    for uid, name in manager_names.items():
        record = base_standings[uid]
        record_str = f"{record['wins']}-{record['losses']}" + (f"-{record['ties']}" if record['ties'] else "")
        results.append({
            'user_id': uid,
            'manager_name': name,
            'current_record': record_str,
            'points_for': round(record['points_for'], 1),
            'playoff_odds': round(100.0 * playoff_count[uid] / trials, 1),
            'bye_odds': round(100.0 * bye_count[uid] / trials, 1) if num_byes else None,
            'avg_seed': round(seed_sum[uid] / playoff_count[uid], 1) if playoff_count[uid] else None,
            'championship_odds': round(100.0 * champ_count[uid] / trials, 1) if has_bracket_template else None,
        })
    results.sort(key=lambda r: (r['playoff_odds'], r['championship_odds'] or 0), reverse=True)

    return {
        'trials': trials,
        'completed_week': completed_week,
        'remaining_weeks': remaining_weeks,
        'playoff_teams_count': playoff_teams_count,
        'has_bracket_template': has_bracket_template,
        'teams': results,
    }
