#!/usr/bin/env python3
"""Unit tests for src/trade_value.py's hypothetical-trade valuation math (CLAUDE.md section 12)."""

from src.trade_value import (
    calculate_faab_value_per_dollar,
    calculate_faab_trade_value,
    calculate_player_trade_values,
    build_trade_analyzer_data,
    DEFAULT_FAAB_VALUE_PER_DOLLAR,
    MIN_FAAB_SPENT_TO_CALIBRATE,
)


class _FakeAnalyzer:
    """Stand-in for FantasyAnalyzer - returns a fixed grade per player name so tests don't
    depend on real ESPN ranking data."""

    def __init__(self, grades):
        self.grades = grades

    def grade_player(self, name, position):
        return {'grade': self.grades.get(name, 5.0)}


def test_faab_value_per_dollar_falls_back_when_no_history():
    assert calculate_faab_value_per_dollar([]) == DEFAULT_FAAB_VALUE_PER_DOLLAR
    assert calculate_faab_value_per_dollar(None) == DEFAULT_FAAB_VALUE_PER_DOLLAR


def test_faab_value_per_dollar_falls_back_when_spending_too_thin():
    # Below MIN_FAAB_SPENT_TO_CALIBRATE even though the observed rate itself would be positive.
    impacts = [{'faab_spent': MIN_FAAB_SPENT_TO_CALIBRATE - 1, 'combined_impact': 10.0}]
    assert calculate_faab_value_per_dollar(impacts) == DEFAULT_FAAB_VALUE_PER_DOLLAR


def test_faab_value_per_dollar_never_negative():
    # A league whose FAAB spends scored below average on balance shouldn't make FAAB a trade
    # liability - the observed (negative) rate must be discarded in favor of the fallback.
    impacts = [{'faab_spent': 50.0, 'combined_impact': -20.0}]
    rate = calculate_faab_value_per_dollar(impacts)
    assert rate > 0
    assert rate == DEFAULT_FAAB_VALUE_PER_DOLLAR


def test_faab_value_per_dollar_uses_league_observed_rate_when_trustworthy():
    impacts = [
        {'faab_spent': 30.0, 'combined_impact': 6.0},
        {'faab_spent': 20.0, 'combined_impact': 2.0},
    ]
    # total_impact / total_spent = 8 / 50 = 0.16
    assert calculate_faab_value_per_dollar(impacts) == 0.16


def test_faab_trade_value_scales_with_amount_and_rate():
    assert calculate_faab_trade_value(0, 0.1) == 0
    assert calculate_faab_trade_value(10, 0.1) == round(10 * 0.1 * 2.5, 2)


def test_player_trade_values_excludes_non_tradable_positions():
    rosters = [{'roster_id': 1, 'owner_id': 'u1', 'players': ['k1', 'p1']}]
    all_players = {
        'k1': {'full_name': 'Some Kicker', 'position': 'K', 'team': 'KC'},
        'p1': {'full_name': 'Some Runner', 'position': 'RB', 'team': 'KC'},
    }
    all_weekly_matchups = {1: [{'roster_id': 1, 'players_points': {'k1': 9.0, 'p1': 10.0}}]}
    values = calculate_player_trade_values(
        rosters, all_players, all_weekly_matchups, _FakeAnalyzer({}),
        roster_to_manager={1: 'u1'}, user_lookup={'u1': {'display_name': 'Manager1'}},
    )
    assert 'k1' not in values
    assert 'p1' in values


def test_player_trade_values_falls_back_to_espn_grade_with_no_recent_games():
    rosters = [{'roster_id': 1, 'owner_id': 'u1', 'players': ['p1']}]
    all_players = {'p1': {'full_name': 'Injured Guy', 'position': 'WR', 'team': 'KC'}}
    # This player has no entry at all in players_points for the only week played.
    all_weekly_matchups = {1: [{'roster_id': 1, 'players_points': {}}]}
    analyzer = _FakeAnalyzer({'Injured Guy': 7.5})
    values = calculate_player_trade_values(
        rosters, all_players, all_weekly_matchups, analyzer,
        roster_to_manager={1: 'u1'}, user_lookup={'u1': {'display_name': 'Manager1'}},
    )
    assert values['p1']['trade_value'] == 7.5
    assert values['p1']['espn_grade'] == 7.5
    assert values['p1']['floor'] == 0.0
    assert values['p1']['ceiling'] == 0.0


def test_player_trade_values_rewards_recent_form_above_position_baseline():
    rosters = [{'roster_id': 1, 'owner_id': 'u1', 'players': ['star', 'dud']}]
    all_players = {
        'star': {'full_name': 'Star Player', 'position': 'WR', 'team': 'KC'},
        'dud': {'full_name': 'Dud Player', 'position': 'WR', 'team': 'KC'},
    }
    # Same position baseline both weeks; 'star' consistently outscores it, 'dud' consistently
    # underperforms it.
    all_weekly_matchups = {
        1: [{'roster_id': 1, 'points': 27.0, 'players_points': {'star': 25.0, 'dud': 2.0}}],
        2: [{'roster_id': 1, 'points': 26.0, 'players_points': {'star': 23.0, 'dud': 3.0}}],
    }
    analyzer = _FakeAnalyzer({'Star Player': 5.0, 'Dud Player': 5.0})  # identical ESPN grade
    values = calculate_player_trade_values(
        rosters, all_players, all_weekly_matchups, analyzer,
        roster_to_manager={1: 'u1'}, user_lookup={'u1': {'display_name': 'Manager1'}},
    )
    # Same season-long grade, but recent form should clearly separate them.
    assert values['star']['trade_value'] > values['dud']['trade_value']
    assert values['star']['floor'] > values['dud']['ceiling']


def test_player_trade_values_ignores_future_placeholder_weeks():
    # Regression: only week 1 has actually been played, but weeks 2-4 are already present in
    # the fetched data (Sleeper pre-fills the whole season's matchup skeleton up front) with
    # every player at a 0.0 placeholder. Before this was fixed, "last 4 weeks" resolved to
    # weeks 2-4 (all zeros) instead of the one real played week, so every player's floor/
    # ceiling/recent_avg silently came out as 0.0 regardless of how they actually played.
    rosters = [{'roster_id': 1, 'owner_id': 'u1', 'players': ['p1']}]
    all_players = {'p1': {'full_name': 'Real Player', 'position': 'WR', 'team': 'KC'}}
    all_weekly_matchups = {
        1: [{'roster_id': 1, 'points': 20.0, 'players_points': {'p1': 20.0}}],
        2: [{'roster_id': 1, 'points': 0.0, 'players_points': {'p1': 0.0}}],
        3: [{'roster_id': 1, 'points': 0.0, 'players_points': {'p1': 0.0}}],
        4: [{'roster_id': 1, 'points': 0.0, 'players_points': {'p1': 0.0}}],
    }
    analyzer = _FakeAnalyzer({'Real Player': 5.0})
    values = calculate_player_trade_values(
        rosters, all_players, all_weekly_matchups, analyzer,
        roster_to_manager={1: 'u1'}, user_lookup={'u1': {'display_name': 'Manager1'}},
    )
    # A single real data point falls back to a +/-30% stdev heuristic (see calculate_player_
    # trade_values' recent_stdev branch) rather than 0 - the point of this test is that the
    # real week 1 score drives these numbers at all, not that they exactly equal 20.0.
    assert values['p1']['recent_avg'] == 20.0
    assert values['p1']['floor'] == 14.0
    assert values['p1']['ceiling'] == 26.0


def test_player_trade_values_discounts_injured_players():
    rosters = [{'roster_id': 1, 'owner_id': 'u1', 'players': ['healthy', 'hurt_mild', 'hurt_severe']}]
    all_players = {
        'healthy': {'full_name': 'Healthy Guy', 'position': 'RB', 'team': 'KC'},
        'hurt_mild': {'full_name': 'Mild Guy', 'position': 'RB', 'team': 'KC', 'injury_status': 'Questionable'},
        'hurt_severe': {'full_name': 'Severe Guy', 'position': 'RB', 'team': 'KC', 'injury_status': 'Out'},
    }
    all_weekly_matchups = {1: [{'roster_id': 1, 'players_points': {
        'healthy': 10.0, 'hurt_mild': 10.0, 'hurt_severe': 10.0,
    }}]}
    analyzer = _FakeAnalyzer({'Healthy Guy': 6.0, 'Mild Guy': 6.0, 'Severe Guy': 6.0})
    values = calculate_player_trade_values(
        rosters, all_players, all_weekly_matchups, analyzer,
        roster_to_manager={1: 'u1'}, user_lookup={'u1': {'display_name': 'Manager1'}},
    )
    # Identical underlying performance/grade - only the injury status differs.
    assert values['healthy']['trade_value_pre_injury'] == values['hurt_mild']['trade_value_pre_injury']
    assert values['healthy']['trade_value'] > values['hurt_mild']['trade_value'] > values['hurt_severe']['trade_value']
    # Floor/ceiling/espn_grade describe real performance and shouldn't be touched by the discount.
    assert values['healthy']['espn_grade'] == values['hurt_severe']['espn_grade']
    assert values['healthy']['floor'] == values['hurt_severe']['floor']


def test_build_trade_analyzer_data_non_faab_league():
    rosters = [{'roster_id': 1, 'owner_id': 'u1', 'players': ['p1']}]
    all_players = {'p1': {'full_name': 'Some Runner', 'position': 'RB', 'team': 'KC'}}
    all_weekly_matchups = {1: [{'roster_id': 1, 'players_points': {'p1': 12.0}}]}
    data = build_trade_analyzer_data(
        rosters, all_players, all_weekly_matchups, _FakeAnalyzer({}),
        roster_to_manager={1: 'u1'}, user_lookup={'u1': {'display_name': 'Manager1'}},
        faab_ledger={'enabled': False}, waiver_impacts=[],
    )
    assert data['faab_enabled'] is False
    assert data['faab_grade_points_per_dollar'] == 0.0
    assert data['teams'][1]['faab_balance'] is None
    assert 'p1' in data['players']
