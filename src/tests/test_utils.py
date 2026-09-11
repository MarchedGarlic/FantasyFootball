#!/usr/bin/env python3
"""Unit tests for src/utils.py's shared helpers."""

from src.utils import week_has_been_played


def test_week_has_been_played_true_when_any_team_scored():
    matchups = [
        {'roster_id': 1, 'points': 0.0},
        {'roster_id': 2, 'points': 24.5},
    ]
    assert week_has_been_played(matchups) is True


def test_week_has_been_played_false_when_every_team_is_a_zero_placeholder():
    # This is the real shape Sleeper returns for a future/unplayed week - every rostered
    # player's points pre-filled with 0.0, not omitted (confirmed against live data).
    matchups = [
        {'roster_id': 1, 'points': 0.0, 'players_points': {'p1': 0.0, 'p2': 0.0}},
        {'roster_id': 2, 'points': 0.0, 'players_points': {'p3': 0.0}},
    ]
    assert week_has_been_played(matchups) is False


def test_week_has_been_played_false_for_empty_or_missing_matchups():
    assert week_has_been_played([]) is False
    assert week_has_been_played(None) is False


def test_week_has_been_played_true_for_partially_started_week():
    # A real in-progress week (Thursday night game already final, Sunday's hasn't kicked off) -
    # some teams still legitimately show 0.0 so far, which must not be mistaken for "not played".
    matchups = [
        {'roster_id': 1, 'points': 18.4},
        {'roster_id': 2, 'points': 0.0},
    ]
    assert week_has_been_played(matchups) is True
