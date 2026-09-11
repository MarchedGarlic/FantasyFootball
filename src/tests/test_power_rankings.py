#!/usr/bin/env python3
"""Regression test for src/power_rankings.py's handling of future/unplayed weeks."""

from src.power_rankings import calculate_weekly_power_ratings


def test_future_placeholder_weeks_are_not_counted_as_played():
    # Sleeper pre-fills every future week's matchup data with 0.0 points for every rostered
    # player rather than omitting it - confirmed against a real in-season league where only
    # week 1 had actually been played but weeks 2-17 were already present in the fetched data,
    # every one of them scored 0-0. Before this was fixed, every one of those phantom weeks
    # still landed in weekly_scores/cumulative_scores, dragging a manager's season-long rating
    # toward zero for a season that had barely started.
    rosters = [
        {'roster_id': 1, 'owner_id': 'u1'},
        {'roster_id': 2, 'owner_id': 'u2'},
    ]
    user_lookup = {
        'u1': {'display_name': 'Manager1'},
        'u2': {'display_name': 'Manager2'},
    }
    all_weekly_matchups = {
        1: [
            {'roster_id': 1, 'matchup_id': 1, 'points': 110.0},
            {'roster_id': 2, 'matchup_id': 1, 'points': 90.0},
        ],
        2: [
            {'roster_id': 1, 'matchup_id': 1, 'points': 0.0},
            {'roster_id': 2, 'matchup_id': 1, 'points': 0.0},
        ],
        3: [
            {'roster_id': 1, 'matchup_id': 1, 'points': 0.0},
            {'roster_id': 2, 'matchup_id': 1, 'points': 0.0},
        ],
    }
    result = calculate_weekly_power_ratings(all_weekly_matchups, rosters, user_lookup)
    assert result['u1']['total_weeks'] == 1
    assert list(result['u1']['weekly_power_ratings'].keys()) == [1]
    assert result['u2']['total_weeks'] == 1
