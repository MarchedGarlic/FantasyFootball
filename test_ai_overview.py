#!/usr/bin/env python3
"""
Manual smoke test for the AI Overview against a running local server (python server.py).

The AI Overview is no longer served by a live /api/ai-overview endpoint - it's a static HTML
file (ai_overview.html) generated during analysis and served like any other report through
/results/<filename>?league_id=&season=. This checks that flow instead of the removed endpoint.

Usage: python test_ai_overview.py <league_id> <season>
(defaults to the league_id/season in league_config.json if omitted)
"""

import sys
import json
import requests

EXPECTED_SECTION_TITLES = [
    "Top Players of the Week",
    "Biggest Upsets",
    "Power Ranking Movers",
    "Matchups to Watch",
    "Projected Playoff Picture",
    "Top Waiver Pickups",
]


def _default_league_season():
    try:
        with open('league_config.json') as f:
            config = json.load(f)
        return config.get('league_id'), config.get('target_season')
    except (FileNotFoundError, json.JSONDecodeError):
        return None, None


def test_ai_overview(league_id, season):
    base_url = "http://localhost:5000"

    print(f"Checking /api/results for league_id={league_id}, season={season}...")
    try:
        results = requests.get(f"{base_url}/api/results", params={"league_id": league_id, "season": season}, timeout=10)
    except requests.exceptions.ConnectionError:
        print("Connection failed - is the server running on port 5000? (python server.py)")
        return False

    if results.status_code != 200:
        print(f"/api/results returned {results.status_code}: {results.text[:300]}")
        return False

    html_reports = results.json().get('html_reports', [])
    if 'ai_overview.html' not in html_reports:
        print(f"ai_overview.html not found in html_reports: {html_reports}")
        print("(Run an analysis for this league+season first.)")
        return False

    print("Fetching ai_overview.html...")
    overview = requests.get(
        f"{base_url}/results/ai_overview.html",
        params={"league_id": league_id, "season": season},
        timeout=10,
    )
    if overview.status_code != 200:
        print(f"Fetching ai_overview.html returned {overview.status_code}")
        return False

    body = overview.text
    missing = [title for title in EXPECTED_SECTION_TITLES if title not in body]
    if missing:
        print(f"ai_overview.html is missing expected sections: {missing}")
        return False

    print(f"Success - all {len(EXPECTED_SECTION_TITLES)} sections present ({len(body)} bytes).")
    return True


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        league_id, season = sys.argv[1], sys.argv[2]
    else:
        league_id, season = _default_league_season()

    if not league_id or not season:
        print("Usage: python test_ai_overview.py <league_id> <season>")
        print("(or set league_id/target_season in league_config.json)")
        sys.exit(1)

    success = test_ai_overview(league_id, season)
    sys.exit(0 if success else 1)
