#!/usr/bin/env python3
"""Unit tests for src/weekly_awards.py's per-week award scoring (CLAUDE.md section 15)."""

from src.weekly_awards import (
    _optimal_lineup_points,
    _bench_points_by_roster,
    build_weekly_awards_for_week,
    build_weekly_awards_data,
)

ROSTER_POSITIONS = ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'K', 'DEF', 'BN', 'BN', 'BN']


def test_optimal_lineup_finds_a_better_bench_player():
    # Started rb_b (8 pts) over the bench's rb_c (20 pts) at the FLEX spot - a real bench blunder.
    all_players = {
        'qb1': {'position': 'QB'}, 'rb_a': {'position': 'RB'}, 'rb_b': {'position': 'RB'},
        'wr_a': {'position': 'WR'}, 'wr_b': {'position': 'WR'}, 'te1': {'position': 'TE'},
        'k1': {'position': 'K'}, 'def1': {'position': 'DEF'}, 'rb_c': {'position': 'RB'},
    }
    team = {
        'players': ['qb1', 'rb_a', 'rb_b', 'wr_a', 'wr_b', 'te1', 'k1', 'def1', 'rb_c'],
        'starters': ['qb1', 'rb_a', 'rb_b', 'wr_a', 'wr_b', 'te1', 'k1', 'def1'],
        'players_points': {
            'qb1': 20.0, 'rb_a': 10.0, 'rb_b': 8.0, 'wr_a': 12.0, 'wr_b': 11.0,
            'te1': 6.0, 'k1': 7.0, 'def1': 9.0, 'rb_c': 20.0,
        },
        'points': 83.0,  # sum of starters
    }
    optimal = _optimal_lineup_points(team, all_players, ROSTER_POSITIONS)
    # True optimum uses all three RBs (two dedicated RB slots + FLEX), not just a 1-for-1 swap:
    # 20 (QB) + 10 + 20 (RB slots: rb_a, rb_c) + 12 + 11 (WR) + 6 (TE) + 8 (FLEX: rb_b) + 7 (K) + 9 (DEF).
    assert optimal == 103.0


def test_optimal_lineup_matches_actual_when_already_optimal():
    all_players = {
        'qb1': {'position': 'QB'}, 'rb_a': {'position': 'RB'}, 'rb_b': {'position': 'RB'},
        'rb_c': {'position': 'RB'}, 'wr_a': {'position': 'WR'}, 'wr_b': {'position': 'WR'},
        'te1': {'position': 'TE'}, 'k1': {'position': 'K'}, 'def1': {'position': 'DEF'},
        'bench_wr': {'position': 'WR'},
    }
    team = {
        # rb_c starts at FLEX (5 pts) over bench_wr (2 pts) - already the best possible lineup.
        'players': ['qb1', 'rb_a', 'rb_b', 'rb_c', 'wr_a', 'wr_b', 'te1', 'k1', 'def1', 'bench_wr'],
        'players_points': {
            'qb1': 20.0, 'rb_a': 10.0, 'rb_b': 8.0, 'rb_c': 5.0, 'wr_a': 12.0, 'wr_b': 11.0,
            'te1': 6.0, 'k1': 7.0, 'def1': 9.0, 'bench_wr': 2.0,
        },
        'points': 88.0,
    }
    optimal = _optimal_lineup_points(team, all_players, ROSTER_POSITIONS)
    assert optimal == 88.0


def test_optimal_lineup_returns_none_without_roster_positions():
    assert _optimal_lineup_points({'players': [], 'players_points': {}}, {}, []) is None
    assert _optimal_lineup_points({'players': [], 'players_points': {}}, {}, None) is None


def test_bench_points_by_roster_clamps_at_zero_and_skips_missing_data():
    all_players = {'qb1': {'position': 'QB'}}
    all_weekly_matchups = {
        1: [
            {'roster_id': 1, 'players': ['qb1'], 'players_points': {'qb1': 20.0}, 'points': 20.0},
            {'roster_id': 2, 'players': [], 'players_points': {}, 'points': 0.0},
        ]
    }
    result = _bench_points_by_roster(all_weekly_matchups, all_players, ROSTER_POSITIONS, 1)
    assert result[1] == {'actual': 20.0, 'optimal': 20.0, 'bench_points': 0.0}
    assert result[2]['bench_points'] == 0.0


def _matchup(uids, names, scores):
    winner_uid = uids[0] if scores[0] > scores[1] else (uids[1] if scores[1] > scores[0] else None)
    return {
        'matchup_id': 1, 'roster_ids': [10, 20], 'user_ids': uids, 'manager_names': names,
        'scores': scores, 'winner_roster_id': None, 'winner_user_id': winner_uid,
        'margin': round(abs(scores[0] - scores[1]), 2),
    }


def test_top_and_low_score_awards():
    matchups = [
        _matchup(['a', 'b'], ['Alice', 'Bob'], [90.0, 100.0]),
        _matchup(['c', 'd'], ['Cara', 'Dan'], [150.0, 60.0]),
    ]
    awards = build_weekly_awards_for_week(matchups, {}, {}, {}, [], [], [])
    by_id = {a['id']: a for a in awards}
    assert by_id['top_score']['winner'] == 'Cara'
    assert by_id['low_score']['winner'] == 'Dan'
    assert by_id['blowout']['winner'] == 'Cara'
    assert by_id['nailbiter']['winner'] == 'Bob'


def test_zero_score_matchups_excluded_from_score_awards():
    # A forfeited/no-lineup-set matchup (a real Sleeper result between playoff byes) shouldn't
    # win "Ice Cold" just because nobody set a lineup.
    matchups = [
        _matchup(['a', 'b'], ['Alice', 'Bob'], [0.0, 0.0]),
        _matchup(['c', 'd'], ['Cara', 'Dan'], [80.0, 60.0]),
    ]
    awards = build_weekly_awards_for_week(matchups, {}, {}, {}, [], [], [])
    by_id = {a['id']: a for a in awards}
    assert by_id['low_score']['winner'] == 'Dan'


def test_upset_of_the_week_uses_highest_scored_upset_this_week():
    upsets = [
        {'week': 5, 'winner': 'Underdog', 'loser': 'Favorite', 'winner_rank_entering': 8,
         'loser_rank_entering': 1, 'margin': 12.0, 'upset_score': 9.0},
    ]
    awards = build_weekly_awards_for_week([], {}, {}, {}, upsets, [], [])
    by_id = {a['id']: a for a in awards}
    assert by_id['upset']['winner'] == 'Underdog'


def test_waiver_hero_skipped_when_no_positive_impact():
    waivers = [{'manager_name': 'Bob', 'players_added': ['Some Guy'], 'combined_impact': -0.5}]
    awards = build_weekly_awards_for_week([], {}, {}, {}, [], waivers, [])
    assert 'waiver_hero' not in {a['id'] for a in awards}

    waivers_positive = [{'manager_name': 'Bob', 'players_added': ['Some Guy'], 'combined_impact': 1.8}]
    awards2 = build_weekly_awards_for_week([], {}, {}, {}, [], waivers_positive, [])
    assert {a['id'] for a in awards2} == {'waiver_hero'}


def test_bench_blunder_and_lineup_ninja():
    bench_data = {
        10: {'actual': 80.0, 'optimal': 95.0, 'bench_points': 15.0},
        20: {'actual': 90.0, 'optimal': 90.2, 'bench_points': 0.2},
    }
    roster_to_manager = {10: 'uid_a', 20: 'uid_b'}
    user_lookup = {'uid_a': {'display_name': 'Alice'}, 'uid_b': {'display_name': 'Bob'}}
    awards = build_weekly_awards_for_week([], bench_data, roster_to_manager, user_lookup, [], [], [])
    by_id = {a['id']: a for a in awards}
    assert by_id['bench_blunder']['winner'] == 'Alice'
    assert by_id['lineup_ninja']['winner'] == 'Bob'


def test_bench_blunder_omitted_when_nobody_left_meaningful_points():
    bench_data = {10: {'actual': 90.0, 'optimal': 90.1, 'bench_points': 0.1}}
    awards = build_weekly_awards_for_week([], bench_data, {}, {}, [], [], [])
    ids = {a['id'] for a in awards}
    assert 'bench_blunder' not in ids
    assert 'lineup_ninja' in ids


def test_faab_splash_picks_biggest_spend():
    roster_to_manager = {10: 'uid_a', 20: 'uid_b'}
    user_lookup = {'uid_a': {'display_name': 'Alice'}, 'uid_b': {'display_name': 'Bob'}}
    faab_events = [
        {'roster_id': 10, 'amount': 15.0, 'commitment_ratio': 0.2},
        {'roster_id': 20, 'amount': 40.0, 'commitment_ratio': 0.8},
    ]
    awards = build_weekly_awards_for_week([], {}, roster_to_manager, user_lookup, [], [], faab_events)
    by_id = {a['id']: a for a in awards}
    assert by_id['faab_splash']['winner'] == 'Bob'


def test_build_weekly_awards_data_excludes_weeks_with_no_real_matchups():
    matchup_results = {
        1: [_matchup(['a', 'b'], ['Alice', 'Bob'], [90.0, 100.0])],
        2: [_matchup(['a', 'b'], ['Alice', 'Bob'], [0.0, 0.0])],
    }
    data = build_weekly_awards_data(
        rosters=[], all_players={}, all_weekly_matchups={}, matchup_results=matchup_results,
        roster_positions=ROSTER_POSITIONS, roster_to_manager={}, user_lookup={},
        power_rank_history={}, waiver_impacts=[], faab_ledger=None,
    )
    assert data['available_weeks'] == [1]
    assert data['default_week'] == 1
    assert 2 not in data['weeks']
