#!/usr/bin/env python3
"""Unit tests for src/playoff_odds.py's Monte Carlo simulation (CLAUDE.md section 15)."""

import random

from src.playoff_odds import (
    _team_score_stats,
    _current_standings,
    _remaining_regular_season_weeks,
    _simulate_bracket,
    simulate_playoff_odds,
)


def _matchup(uids, scores):
    return {'user_ids': uids, 'scores': scores}


def test_team_score_stats_uses_real_scores_and_league_fallback():
    matchup_results = {
        1: [_matchup(['a', 'b'], [100.0, 80.0])],
        2: [_matchup(['a', 'b'], [110.0, 90.0])],
    }
    manager_names = {'a': 'Alice', 'b': 'Bob', 'c': 'Cara'}  # 'c' never played - no real data
    stats = _team_score_stats(matchup_results, completed_week=2, manager_names=manager_names)
    assert stats['a']['mean'] == 105.0
    assert stats['b']['mean'] == 85.0
    # No data at all for 'c' - falls back to the league-wide mean of every real score seen.
    assert stats['c']['mean'] == sum([100.0, 80.0, 110.0, 90.0]) / 4


def test_team_score_stats_ignores_weeks_after_completed_week():
    matchup_results = {
        1: [_matchup(['a', 'b'], [100.0, 80.0])],
        2: [_matchup(['a', 'b'], [999.0, 999.0])],  # future/unplayed week - shouldn't count
    }
    stats = _team_score_stats(matchup_results, completed_week=1, manager_names={'a': 'A', 'b': 'B'})
    assert stats['a']['mean'] == 100.0


def test_current_standings_tracks_wins_losses_and_points():
    matchup_results = {
        1: [_matchup(['a', 'b'], [100.0, 80.0])],
        2: [_matchup(['a', 'b'], [90.0, 95.0])],
    }
    standings = _current_standings(matchup_results, completed_week=2, manager_names={'a': 'A', 'b': 'B'})
    assert standings['a'] == {'wins': 1, 'losses': 1, 'ties': 0, 'points_for': 190.0}
    assert standings['b'] == {'wins': 1, 'losses': 1, 'ties': 0, 'points_for': 175.0}


def test_current_standings_skips_unplayed_zero_zero_matchups():
    matchup_results = {1: [_matchup(['a', 'b'], [0.0, 0.0])]}
    standings = _current_standings(matchup_results, completed_week=1, manager_names={'a': 'A', 'b': 'B'})
    assert standings['a']['wins'] == 0 and standings['a']['losses'] == 0


def test_remaining_regular_season_weeks_excludes_playoff_weeks():
    matchup_results = {1: [], 2: [], 3: [], 4: []}
    remaining = _remaining_regular_season_weeks(matchup_results, completed_week=1, playoff_week_start=4)
    assert remaining == [2, 3]  # week 4+ is playoffs, excluded


def test_remaining_weeks_empty_when_season_already_over():
    matchup_results = {1: [], 2: []}
    remaining = _remaining_regular_season_weeks(matchup_results, completed_week=2, playoff_week_start=3)
    assert remaining == []


def test_simulate_bracket_is_deterministic_with_zero_stdev():
    # sigma=0 makes random.gauss(mu, 0) always return mu exactly - the #1 seed's mean crushes
    # everyone else's, so they should win every round regardless of RNG state.
    score_stats = {
        's1': {'mean': 200.0, 'stdev': 0.0}, 's2': {'mean': 10.0, 'stdev': 0.0},
        's3': {'mean': 10.0, 'stdev': 0.0}, 's4': {'mean': 10.0, 'stdev': 0.0},
    }
    champion = _simulate_bracket(['s1', 's2', 's3', 's4'], score_stats, random.Random(1))
    assert champion == 's1'


def test_simulate_bracket_falls_back_to_top_seed_for_unsupported_field_size():
    score_stats = {'s1': {'mean': 100.0, 'stdev': 5.0}, 's2': {'mean': 90.0, 'stdev': 5.0}, 's3': {'mean': 80.0, 'stdev': 5.0}}
    champion = _simulate_bracket(['s1', 's2', 's3'], score_stats, random.Random(1))
    assert champion == 's1'  # no 3-team template - matches the client-side bracket's own fallback


def test_simulate_playoff_odds_matches_real_standings_when_season_is_over():
    # Two completed weeks, no remaining regular season weeks (playoff_week_start=3) - the field
    # is fully decided already, so playoff odds should be exactly 100/0, not probabilistic.
    matchup_results = {
        1: [
            _matchup(['m1', 'm2'], [100.0, 80.0]),
            _matchup(['m3', 'm4'], [90.0, 85.0]),
            _matchup(['m5', 'm6'], [70.0, 60.0]),
        ],
        2: [
            _matchup(['m1', 'm3'], [110.0, 95.0]),
            _matchup(['m2', 'm4'], [88.0, 80.0]),
            _matchup(['m5', 'm6'], [75.0, 65.0]),
        ],
    }
    manager_names = {f'm{i}': f'Manager {i}' for i in range(1, 7)}
    result = simulate_playoff_odds(
        matchup_results, manager_names, playoff_teams_count=4, playoff_week_start=3,
        completed_week=2, trials=500,
    )
    assert result['remaining_weeks'] == []
    by_uid = {t['user_id']: t for t in result['teams']}

    # m1 (2-0, 210 pts) and m5 (2-0, 145 pts) lead on wins; m3 (1-1, 185) and m2 (1-1, 168) edge
    # out m4 (0-2, 165) and m6 (0-2, 125) on the wins-then-points tiebreak - see test docstring math.
    for uid in ('m1', 'm5', 'm3', 'm2'):
        assert by_uid[uid]['playoff_odds'] == 100.0
        assert by_uid[uid]['current_record'] in ('2-0', '1-1')
    for uid in ('m4', 'm6'):
        assert by_uid[uid]['playoff_odds'] == 0.0
        assert by_uid[uid]['championship_odds'] == 0.0

    # Exactly one champion per trial among the 4 playoff teams - percentages must sum to ~100.
    champ_sum = sum(by_uid[uid]['championship_odds'] for uid in ('m1', 'm5', 'm3', 'm2'))
    assert abs(champ_sum - 100.0) < 1.0


def test_simulate_playoff_odds_varies_with_remaining_weeks():
    # A dominant team (huge mean, tiny stdev) with games left to play should have both high
    # playoff odds and championship odds once the bracket is simulated.
    matchup_results = {
        1: [_matchup(['dominant', 'weak1'], [200.0, 50.0]), _matchup(['weak2', 'weak3'], [60.0, 55.0])],
        2: [_matchup(['dominant', 'weak2'], [0.0, 0.0]), _matchup(['weak1', 'weak3'], [0.0, 0.0])],  # unplayed
    }
    manager_names = {'dominant': 'D', 'weak1': 'W1', 'weak2': 'W2', 'weak3': 'W3'}
    result = simulate_playoff_odds(
        matchup_results, manager_names, playoff_teams_count=4, playoff_week_start=3,
        completed_week=1, trials=300,
    )
    by_uid = {t['user_id']: t for t in result['teams']}
    assert result['remaining_weeks'] == [2]
    assert by_uid['dominant']['playoff_odds'] == 100.0
    assert by_uid['dominant']['championship_odds'] > 50.0
