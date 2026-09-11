#!/usr/bin/env python3
"""Regression test for src/median_record_calculator.py's handling of future/unplayed weeks."""

from src.median_record_calculator import calculate_median_records


def test_future_placeholder_weeks_dont_grant_free_ties_or_median_wins():
    # Sleeper pre-fills every future week's matchup data with 0.0 for every rostered player
    # rather than omitting it. Before this was fixed, every team tied its opponent 0-0 (a free
    # regular-season tie) and tied the week's "median" of 0.0, which the exactly-at-median
    # branch scores as a free win - both piling up for every remaining week of the season
    # before it was ever played.
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
    result = calculate_median_records(all_weekly_matchups, rosters, user_lookup)
    assert result['u1']['regular_record'] == {'wins': 1, 'losses': 0, 'ties': 0}
    assert result['u2']['regular_record'] == {'wins': 0, 'losses': 1, 'ties': 0}
    assert result['u1']['median_record']['wins'] + result['u1']['median_record']['losses'] == 1
    assert result['u2']['median_record']['wins'] + result['u2']['median_record']['losses'] == 1
