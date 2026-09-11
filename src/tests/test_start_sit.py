#!/usr/bin/env python3
"""Unit tests for src/start_sit.py's matchup/injury scoring (CLAUDE.md section 13)."""

from src.start_sit import (
    build_defense_vs_position,
    calculate_start_sit_recommendations,
    _opportunity_boost,
    _build_depth_charts,
)


class _FakeAnalyzer:
    def __init__(self, grades):
        self.grades = grades

    def grade_player(self, name, position):
        return {'grade': self.grades.get(name, 5.0)}


def test_defense_vs_position_flags_a_weak_defense():
    all_players = {
        'rb_a': {'full_name': 'RB A', 'position': 'RB', 'team': 'KC'},
        'rb_b': {'full_name': 'RB B', 'position': 'RB', 'team': 'BUF'},
        'rb_c': {'full_name': 'RB C', 'position': 'RB', 'team': 'DEN'},
    }
    # CAR's defense faces rb_a and rb_b across two weeks and allows big games both times;
    # the rest of the league (facing DEN) allows much less.
    all_weekly_matchups = {
        1: [{'roster_id': 1, 'points': 30.0, 'players_points': {'rb_a': 30.0}}],
        2: [{'roster_id': 1, 'points': 28.0, 'players_points': {'rb_b': 28.0}}],
        3: [{'roster_id': 1, 'points': 8.0, 'players_points': {'rb_c': 8.0}}],
    }
    schedule_by_week = {
        1: {'KC': 'CAR', 'CAR': 'KC'},
        2: {'BUF': 'CAR', 'CAR': 'BUF'},
        3: {'DEN': 'SEA', 'SEA': 'DEN'},
    }
    dvp = build_defense_vs_position(all_weekly_matchups, all_players, schedule_by_week)
    assert dvp['CAR']['RB']['avg_allowed'] == 29.0
    assert dvp['CAR']['RB']['z_score'] > dvp['SEA']['RB']['z_score']


def test_defense_vs_position_ignores_future_placeholder_weeks():
    # Regression: ESPN's real schedule for a future week is already known (published months
    # ahead), but Sleeper still pre-fills that week's players_points with 0.0 for every
    # rostered player. Before this was fixed, every future week attributed a fake "allowed 0
    # points" game to whoever's on the schedule that week, diluting every real defense's
    # points-allowed average toward zero long before those games were played.
    all_players = {'rb_a': {'full_name': 'RB A', 'position': 'RB', 'team': 'KC'}}
    all_weekly_matchups = {
        1: [{'roster_id': 1, 'points': 30.0, 'players_points': {'rb_a': 30.0}}],
        2: [{'roster_id': 1, 'points': 0.0, 'players_points': {'rb_a': 0.0}}],
    }
    schedule_by_week = {
        1: {'KC': 'CAR', 'CAR': 'KC'},
        2: {'KC': 'SEA', 'SEA': 'KC'},  # not played yet
    }
    dvp = build_defense_vs_position(all_weekly_matchups, all_players, schedule_by_week)
    assert dvp['CAR']['RB']['avg_allowed'] == 30.0
    assert 'SEA' not in dvp


def test_out_player_always_sits_regardless_of_matchup():
    player_values = {
        'p1': {
            'name': 'Hurt Star', 'position': 'RB', 'team': 'KC', 'roster_id': 1,
            'manager_name': 'M1', 'trade_value': 4.5, 'trade_value_pre_injury': 9.0,
            'floor': 10.0, 'ceiling': 20.0, 'recent_avg': 15.0, 'espn_grade': 9.0,
            'injury_status': 'Out',
        },
    }
    all_players = {'p1': {'team': 'KC', 'position': 'RB', 'injury_status': 'Out'}}
    # Extremely favorable matchup shouldn't be enough to overcome an Out status.
    dvp = {'CAR': {'RB': {'avg_allowed': 100, 'z_score': 5.0, 'games': 10}}}
    schedule_this_week = {'KC': 'CAR'}
    recs = calculate_start_sit_recommendations(player_values, all_players, schedule_this_week, dvp)
    assert recs['p1']['verdict'] == 'Sit'


def test_bye_week_player_sits():
    player_values = {
        'p1': {
            'name': 'Bye Guy', 'position': 'WR', 'team': 'KC', 'roster_id': 1,
            'manager_name': 'M1', 'trade_value': 8.0, 'trade_value_pre_injury': 8.0,
            'floor': 10.0, 'ceiling': 20.0, 'recent_avg': 15.0, 'espn_grade': 8.0,
            'injury_status': None,
        },
    }
    all_players = {'p1': {'team': 'KC', 'position': 'WR'}}
    recs = calculate_start_sit_recommendations(player_values, all_players, {}, {})
    assert recs['p1']['verdict'] == 'Sit'
    assert 'Bye week' in recs['p1']['reasoning'][0]


def test_favorable_matchup_and_quality_produce_start():
    player_values = {
        'p1': {
            'name': 'Good Player', 'position': 'RB', 'team': 'KC', 'roster_id': 1,
            'manager_name': 'M1', 'trade_value': 8.0, 'trade_value_pre_injury': 8.0,
            'floor': 10.0, 'ceiling': 20.0, 'recent_avg': 15.0, 'espn_grade': 8.0,
            'injury_status': None,
        },
    }
    all_players = {'p1': {'team': 'KC', 'position': 'RB'}}
    dvp = {'CAR': {'RB': {'avg_allowed': 25.0, 'z_score': 1.2, 'games': 10}}}
    recs = calculate_start_sit_recommendations(player_values, all_players, {'KC': 'CAR'}, dvp)
    assert recs['p1']['verdict'] == 'Start'
    assert any('Favorable matchup' in r for r in recs['p1']['reasoning'])


def test_opportunity_boost_requires_healthy_candidate():
    all_players = {
        'starter': {'team': 'SF', 'position': 'WR', 'depth_chart_order': 1, 'injury_status': 'IR', 'full_name': 'Starter'},
        'backup_healthy': {'team': 'SF', 'position': 'WR', 'depth_chart_order': 2, 'injury_status': None, 'full_name': 'Backup Healthy'},
        'backup_also_hurt': {'team': 'SF', 'position': 'WR', 'depth_chart_order': 2, 'injury_status': 'IR', 'full_name': 'Backup Also Hurt'},
    }
    depth_charts = _build_depth_charts(all_players, set(all_players.keys()))

    boost, name, status = _opportunity_boost('backup_healthy', all_players, depth_charts)
    assert boost > 0
    assert name == 'Starter'

    # A player who is themselves on IR shouldn't show a "you get more opportunity" boost -
    # confirmed as a real bug against live data (a WR on IR was crediting a boost from a
    # teammate also on IR).
    boost2, name2, status2 = _opportunity_boost('backup_also_hurt', all_players, depth_charts)
    assert boost2 == 0.0
    assert name2 is None


def test_opportunity_boost_only_looks_at_immediately_ahead_player():
    all_players = {
        'rb1': {'team': 'SF', 'position': 'RB', 'depth_chart_order': 1, 'injury_status': 'Out', 'full_name': 'RB1'},
        'rb2': {'team': 'SF', 'position': 'RB', 'depth_chart_order': 2, 'injury_status': None, 'full_name': 'RB2'},
        'rb3': {'team': 'SF', 'position': 'RB', 'depth_chart_order': 3, 'injury_status': None, 'full_name': 'RB3'},
    }
    depth_charts = _build_depth_charts(all_players, set(all_players.keys()))
    # RB3's immediate predecessor (RB2) is healthy, even though RB1 (further up) is hurt.
    boost, name, status = _opportunity_boost('rb3', all_players, depth_charts)
    assert boost == 0.0
