#!/usr/bin/env python3
"""
Draft analysis: reconstructs each manager's actual draft class from Sleeper's draft-picks
endpoint, and scores it two ways.

- Biggest Steals: how far below their ESPN preseason expert-consensus rank a player was
  actually drafted. This intentionally uses ESPN's `draftRanksByRankType` field, not real
  crowd-sourced ADP - ESPN's own `ownership.averageDraftPosition` field was checked against
  live data and confirmed broken (a flat 170.0 placeholder for every player, elite or not, as
  of 2026-09), while `draftRanksByRankType` was verified to return correctly-ordered,
  season-accurate preseason ranks. See CLAUDE.md's draft-rating section for the full writeup.
- Draft Rating: a per-manager 0-10 score combining the quality of the players drafted (the same
  ESPN-tier `grade_player()`/`grade_roster()` already used for roster/trade grading elsewhere in
  this app) with how much value they got relative to ESPN's preseason rank - weighted 70%
  quality / 30% value per explicit user direction (a team that drafted the best players should
  rate highest even if they didn't find many bargains along the way).

Both degrade gracefully to empty results if the league didn't use Sleeper's own draft tool (no
completed draft found) or ESPN's preseason rank data isn't available that season - never a hard
failure for the rest of the pipeline.
"""

import statistics

from src.utils import get_manager_name

VALUE_Z_SCORE_SCALE = 2.5  # matches the waiver-scoring z-to-grade mapping for consistency
QUALITY_WEIGHT = 0.7
VALUE_WEIGHT = 0.3


def get_primary_draft(drafts):
    """Pick the one real startup/rookie draft for this season out of Sleeper's drafts list (a
    normal redraft league has exactly one - see CLAUDE.md section 0, no dynasty/keeper support).
    Prefers a completed draft; falls back to whatever's there if none are marked complete."""
    if not drafts:
        return None
    completed = [d for d in drafts if d.get('status') == 'complete']
    return (completed or drafts)[0]


def reconstruct_draft_results(draft_picks, roster_to_manager, user_lookup, all_players):
    """Every pick, enriched with the player's name/position/current injury status and the
    manager who made it. Skips empty/forfeited slots and picks whose roster doesn't map to a
    known manager."""
    results = []
    for pick in draft_picks or []:
        player_id = pick.get('player_id')
        roster_id = pick.get('roster_id')
        pick_no = pick.get('pick_no')
        if not player_id or pick_no is None or roster_id not in roster_to_manager:
            continue
        manager_id = roster_to_manager[roster_id]
        if manager_id not in user_lookup:
            continue

        info = (all_players or {}).get(player_id, {})
        name = (info.get('full_name')
                or f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
                or f"Player_{player_id}")

        results.append({
            'player_id': player_id,
            'player_name': name,
            'position': info.get('position', 'Unknown'),
            'round': pick.get('round'),
            'pick_no': pick_no,
            'roster_id': roster_id,
            'manager_id': manager_id,
            'manager_name': get_manager_name(user_lookup, manager_id),
            'injury_status': info.get('injury_status'),
        })

    results.sort(key=lambda p: p['pick_no'])
    return results


def _expected_rank(player_name, espn_draft_ranks, scoring_type='standard'):
    ranks = (espn_draft_ranks or {}).get(player_name.lower())
    if not ranks:
        return None
    return ranks.get('ppr_rank') if scoring_type == 'ppr' else ranks.get('standard_rank')


def calculate_biggest_steals(draft_results, espn_draft_ranks, scoring_type='standard', limit=10):
    """The picks with the largest gap between where a player actually went and where ESPN's
    preseason rank said they should have gone: discrepancy = actual pick number - expected rank,
    so a large positive number means the player was still on the board long after experts
    expected them to be gone (a steal). Players Sleeper currently marks with any injury_status
    are excluded entirely, per explicit request - a 'steal' framed around someone currently
    hurt isn't a useful takeaway.
    """
    if not draft_results or not espn_draft_ranks:
        return []

    steals = []
    for pick in draft_results:
        if pick.get('injury_status'):
            continue
        expected = _expected_rank(pick['player_name'], espn_draft_ranks, scoring_type)
        if expected is None:
            continue
        steals.append({
            **pick,
            'expected_rank': expected,
            'discrepancy': pick['pick_no'] - expected,
        })

    steals.sort(key=lambda p: p['discrepancy'], reverse=True)
    return steals[:limit]


def _value_z_scores(draft_results, espn_draft_ranks, scoring_type='standard'):
    """Per-manager average (actual pick - expected rank) discrepancy, z-scored against the
    other managers in this same league - the 'value' half of Draft Rating. Unlike Biggest
    Steals, injured players are NOT excluded here - a manager's draft-value score should reflect
    every pick they made, not just the ones that are still healthy today."""
    per_manager = {}
    for pick in draft_results:
        expected = _expected_rank(pick['player_name'], espn_draft_ranks, scoring_type)
        if expected is None:
            continue
        per_manager.setdefault(pick['manager_id'], []).append(pick['pick_no'] - expected)

    manager_avgs = {mid: statistics.mean(vals) for mid, vals in per_manager.items() if vals}
    if not manager_avgs:
        return {}

    values = list(manager_avgs.values())
    mean = statistics.mean(values)
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0

    return {
        mid: ((avg - mean) / stdev if stdev > 0 else 0.0)
        for mid, avg in manager_avgs.items()
    }


def calculate_draft_ratings(draft_results, espn_draft_ranks, analyzer, scoring_type='standard'):
    """Per-manager 0-10 Draft Rating = 70% quality_score + 30% value_score.

    quality_score is grade_roster()'s overall_grade (already 0-10) run on every player the
    manager drafted - the same weighted ESPN-tier grading used for weekly roster grades and
    trade valuation elsewhere in this app, so 'how good was this draft' uses one consistent
    quality signal app-wide rather than a new one-off metric.

    value_score maps this manager's average pick-vs-expected-rank discrepancy, z-scored against
    the rest of the league, onto the same 0-10 scale used for the waiver-scoring rewrite
    (5 + z * 2.5, clamped) - a team that beat expected rank by a full standard deviation more
    than their league-mates gets a +2.5 bump.
    """
    if not draft_results:
        return []

    by_manager = {}
    for pick in draft_results:
        by_manager.setdefault(pick['manager_id'], {'manager_name': pick['manager_name'], 'picks': []})
        by_manager[pick['manager_id']]['picks'].append(pick)

    value_z_scores = _value_z_scores(draft_results, espn_draft_ranks, scoring_type)

    ratings = []
    for manager_id, data in by_manager.items():
        gradeable = [{'name': p['player_name'], 'position': p['position']} for p in data['picks']]
        roster_grade = analyzer.grade_roster(gradeable)
        quality_score = roster_grade['overall_grade']

        z = value_z_scores.get(manager_id, 0.0)
        value_score = round(max(0.0, min(10.0, 5.0 + z * VALUE_Z_SCORE_SCALE)), 1)

        draft_rating = round(quality_score * QUALITY_WEIGHT + value_score * VALUE_WEIGHT, 1)

        ratings.append({
            'manager_id': manager_id,
            'manager_name': data['manager_name'],
            'draft_rating': draft_rating,
            'quality_score': quality_score,
            'value_score': value_score,
            'num_picks': len(data['picks']),
            'position_grades': roster_grade['position_grades'],
        })

    ratings.sort(key=lambda r: r['draft_rating'], reverse=True)
    for i, r in enumerate(ratings):
        r['rank'] = i + 1
    return ratings
