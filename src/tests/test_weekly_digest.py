#!/usr/bin/env python3
"""Unit tests for src/weekly_digest.py's Markdown formatting (CLAUDE.md section 14)."""

from src.weekly_digest import (
    _format_matchups_md,
    _format_upsets_md,
    _format_trades_md,
    _format_injury_notes_md,
    _format_playoff_odds_md,
    render_weekly_digest_html,
)


def test_format_matchups_shows_winner_first_by_score():
    matchup_results = {
        5: [
            {'user_ids': ['a', 'b'], 'manager_names': ['Alice', 'Bob'], 'scores': [90.0, 100.0],
             'winner_user_id': 'b', 'margin': 10.0},
            {'user_ids': ['c', 'd'], 'manager_names': ['Cara', 'Dan'], 'scores': [150.0, 60.0],
             'winner_user_id': 'c', 'margin': 90.0},
        ]
    }
    text = _format_matchups_md(matchup_results, 5)
    lines = text.split("\n")
    assert "Cara" in lines[0]  # highest winning score sorts first
    assert "Bob" in lines[1]


def test_format_matchups_handles_no_completed_games():
    assert "No completed" in _format_matchups_md({5: []}, 5)
    assert "No completed" in _format_matchups_md({}, 5)


def test_format_upsets_filters_to_current_week_only():
    upsets = [
        {'week': 3, 'winner': 'A', 'loser': 'B', 'winner_rank_entering': 5, 'loser_rank_entering': 1, 'margin': 10.0, 'upset_score': 8.0},
        {'week': 5, 'winner': 'C', 'loser': 'D', 'winner_rank_entering': 6, 'loser_rank_entering': 2, 'margin': 20.0, 'upset_score': 9.0},
    ]
    text = _format_upsets_md(upsets, 5)
    assert 'C' in text and 'A' not in text.replace('week', '')


def test_format_trades_shows_none_when_no_trades_this_week():
    trade_impacts = [{'week': 3, 'manager_name': 'A', 'other_manager': 'B', 'acquired_players': ['X'], 'gave_up_players': ['Y'], 'combined_impact': 1.0}]
    assert "No trades" in _format_trades_md(trade_impacts, 5)


def test_format_injury_notes_lists_notable_and_boosted_separately():
    players = {
        'p1': {'name': 'Hurt Guy', 'position': 'RB', 'manager_name': 'Alice', 'injury_status': 'Out', 'reasoning': []},
        'p2': {'name': 'Healthy Backup', 'position': 'RB', 'manager_name': 'Alice', 'injury_status': None,
               'reasoning': ['Hurt Guy (Out) is ahead of Healthy Backup on the depth chart and banged up, which should mean expanded opportunity this week.']},
        'p3': {'name': 'Fine Guy', 'position': 'WR', 'manager_name': 'Bob', 'injury_status': None, 'reasoning': []},
    }
    text = _format_injury_notes_md(players)
    assert 'Hurt Guy' in text
    assert 'Healthy Backup' in text
    assert 'Fine Guy' not in text


def test_format_injury_notes_handles_no_data():
    assert 'not available' in _format_injury_notes_md(None)
    assert 'not available' in _format_injury_notes_md({})


def test_format_injury_notes_shows_no_significant_when_league_is_healthy():
    players = {'p1': {'name': 'Fine Guy', 'position': 'WR', 'manager_name': 'Bob', 'injury_status': None, 'reasoning': []}}
    assert 'No significant' in _format_injury_notes_md(players)


def test_format_playoff_odds_includes_championship_column_when_bracket_available():
    playoff_odds = {
        'has_bracket_template': True,
        'teams': [
            {'manager_name': 'Alice', 'current_record': '5-1', 'playoff_odds': 92.5, 'championship_odds': 30.0},
            {'manager_name': 'Bob', 'current_record': '2-4', 'playoff_odds': 10.0, 'championship_odds': 1.0},
        ],
    }
    text = _format_playoff_odds_md(playoff_odds)
    assert 'Championship Odds' in text
    assert 'Alice' in text and '92.5%' in text and '30.0%' in text


def test_format_playoff_odds_omits_championship_column_without_bracket_template():
    playoff_odds = {
        'has_bracket_template': False,
        'teams': [{'manager_name': 'Alice', 'current_record': '5-1', 'playoff_odds': 92.5, 'championship_odds': None}],
    }
    text = _format_playoff_odds_md(playoff_odds)
    assert 'Championship Odds' not in text


def test_format_playoff_odds_handles_no_data():
    assert 'Not enough data' in _format_playoff_odds_md(None)
    assert 'Not enough data' in _format_playoff_odds_md({})


def test_render_html_escapes_special_characters_in_manager_names():
    # A real Sleeper display name could contain HTML-significant characters this app doesn't
    # control - confirms they land in the <textarea> escaped rather than breaking the markup.
    markdown_text = "## Results\n- **Team <Bold> & Friends** def. Someone"
    html_page = render_weekly_digest_html(markdown_text, {'league_name': 'Test League', 'season': 2025}, 'digest.md')
    assert '<Bold>' not in html_page
    assert '&lt;Bold&gt;' in html_page
    assert '&amp; Friends' in html_page
