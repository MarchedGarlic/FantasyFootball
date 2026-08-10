#!/usr/bin/env python3
"""
Fantasy Football Analysis Server
Web server to handle league/season selection and analysis generation.

Every analysis is keyed by (league_id, season) end to end - see CLAUDE.md sections 1 and 3.
This file intentionally no longer imports `openai`: the AI Overview is fully deterministic
(built inside main.run_analysis(), see src/ai_overview.py) and never called an LLM in the first
place despite the dependency being present - see CLAUDE.md section 1, finding 4.
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import re
import threading
from datetime import datetime

from src.api_clients import SleeperAPI
from src.storage import AnalysisStorage, get_analysis_lock
import main as analysis_main

app = Flask(__name__)
CORS(app)

sleeper_api = SleeperAPI()
storage = AnalysisStorage()

# analysis_id -> {status, progress, message, timestamp, league_id, season}
analysis_status = {}
# (league_id, season) -> analysis_id currently running for that league+season, so a second
# request for the SAME league+season attaches to the in-progress run instead of racing it.
active_analyses = {}
_active_analyses_guard = threading.Lock()

PROGRESS_STAGES = [
    (5, "Initializing API connections"),
    (10, "Resolving league"),
    (20, "Fetching ESPN stat leaders"),
    (28, "Fetching NFL player database"),
    (35, "Getting league information"),
    (42, "Getting rosters and user data"),
    (50, "Fetching weekly matchups"),
    (58, "Fetching league transactions"),
    (63, "Reconstructing FAAB ledger"),
    (67, "Output directory ready"),
    (72, "Calculating Power Ratings"),
    (76, "Calculating Median-Based Combined Records"),
    (82, "Calculating weekly roster grades"),
    (87, "Starting Comprehensive Analysis"),
    (92, "Creating interactive visualizations"),
    (95, "Collecting weekly player/matchup data"),
    (97, "Generating JSON output files"),
    (99, "Building AI overview"),
    (100, "Analysis complete"),
]


@app.route('/')
def serve_index():
    """Serve the main index page"""
    return send_from_directory('.', 'index.html')


@app.route('/api/current-season')
def get_current_season():
    """Current NFL season, used to default the frontend's season picker instead of a
    hardcoded year that goes stale every offseason."""
    season = analysis_main.get_current_season(sleeper_api)
    return jsonify({"season": season})


@app.route('/api/user/<username>')
def get_user_leagues(username):
    """Get all leagues for a given Sleeper username in a given season (defaults to current)."""
    try:
        if not username or not username.strip():
            return jsonify({"error": "Username is required"}), 400

        username = username.strip()

        if len(username) > 30:
            return jsonify({"error": "Username must be 30 characters or less"}), 400

        if not re.match(r'^[a-zA-Z0-9]+$', username):
            return jsonify({"error": "Username can only contain English letters (a-z, A-Z) and numbers (0-9)"}), 400

        season_param = request.args.get('season')
        try:
            season = int(season_param) if season_param else analysis_main.get_current_season(sleeper_api)
        except ValueError:
            return jsonify({"error": "season must be a year, e.g. 2025"}), 400

        user = sleeper_api.get_user_by_username(username)
        if not user:
            return jsonify({"error": f"Sleeper user '{username}' not found. Please check the username and try again."}), 404

        user_id = user.get('user_id')
        if not user_id:
            return jsonify({"error": "Invalid user data received from Sleeper"}), 400

        leagues = sleeper_api.get_user_leagues(user_id, season)

        if not leagues:
            return jsonify({
                "user": {
                    "username": user.get('username'),
                    "display_name": user.get('display_name'),
                    "user_id": user_id
                },
                "season": season,
                "leagues": [],
                "message": f"No leagues found for {username} in the {season} season."
            })

        formatted_leagues = []
        for league in leagues:
            formatted_leagues.append({
                'league_id': league.get('league_id'),
                'name': league.get('name'),
                'total_rosters': league.get('total_rosters'),
                'status': league.get('status'),
                'season': league.get('season', season),
                'settings': {
                    'playoff_teams': league.get('settings', {}).get('playoff_teams'),
                    'league_average_match': league.get('settings', {}).get('league_average_match'),
                    'waiver_type': league.get('settings', {}).get('waiver_type'),
                }
            })

        return jsonify({
            "user": {
                "username": user.get('username'),
                "display_name": user.get('display_name'),
                "user_id": user_id
            },
            "season": season,
            "leagues": formatted_leagues
        })

    except Exception as e:
        print(f"Unexpected error in get_user_leagues: {e}")
        return jsonify({"error": "An unexpected error occurred. Please try again."}), 500


@app.route('/api/seasons/<league_id>')
def get_analyzed_seasons(league_id):
    """Seasons of this league that have already been analyzed and are available to view
    without re-running analysis."""
    return jsonify({"league_id": league_id, "seasons": storage.list_analyzed_seasons(league_id)})


def _make_progress_callback(analysis_id):
    stage_index = {"value": 0}

    def callback(message):
        while stage_index["value"] < len(PROGRESS_STAGES):
            progress, keyword = PROGRESS_STAGES[stage_index["value"]]
            if keyword in message:
                analysis_status[analysis_id].update({
                    "status": "running",
                    "progress": progress,
                    "message": message,
                })
                stage_index["value"] += 1
                return
            break

    return callback


RECENT_ANALYSIS_MAX_AGE_SECONDS = 15 * 60


@app.route('/api/analyze', methods=['POST'])
def start_analysis():
    """Start analysis for a selected league+season.

    If a completed analysis for this exact (league_id, season) finished within the last 15
    minutes and the caller didn't pass force_refresh, skip re-running the whole pipeline and
    hand back a synthetic 'completed' status pointing at the existing results - CLAUDE.md
    section 6. Re-running the full Sleeper/ESPN fetch for a league someone just analyzed
    seconds ago is exactly the kind of wasted work the performance pass targeted.
    """
    try:
        data = request.get_json() or {}
        username = data.get('username')
        league_id = data.get('league_id')
        league_name = data.get('league_name')
        season = data.get('season')
        force_refresh = bool(data.get('force_refresh'))

        if not all([username, league_id, league_name, season]):
            return jsonify({"error": "Missing required parameters (username, league_id, league_name, season)"}), 400

        try:
            season = int(season)
        except (TypeError, ValueError):
            return jsonify({"error": "season must be a year, e.g. 2025"}), 400

        if not force_refresh:
            meta = storage.read_meta(league_id, season)
            if meta and meta.get('generated_at'):
                age = (datetime.now() - datetime.fromisoformat(meta['generated_at'])).total_seconds()
                if age < RECENT_ANALYSIS_MAX_AGE_SECONDS:
                    cached_id = f"cached_{league_id}_{season}"
                    analysis_status[cached_id] = {
                        "status": "completed",
                        "progress": 100,
                        "message": f"Using results from {round(age)}s ago - pass force_refresh to re-run",
                        "timestamp": datetime.now().isoformat(),
                        "league_id": league_id,
                        "season": season,
                    }
                    return jsonify({
                        "analysis_id": cached_id,
                        "status": "started",
                        "message": "Using recently cached analysis"
                    })

        key = (str(league_id), str(season))

        with _active_analyses_guard:
            existing_id = active_analyses.get(key)
            if existing_id and analysis_status.get(existing_id, {}).get("status") in ("starting", "running"):
                return jsonify({
                    "analysis_id": existing_id,
                    "status": "already_running",
                    "message": f"Analysis for this league+season is already running (started as {existing_id})"
                })

            analysis_id = f"{username}_{league_id}_{season}_{int(datetime.now().timestamp())}"
            active_analyses[key] = analysis_id

        analysis_status[analysis_id] = {
            "status": "starting",
            "progress": 0,
            "message": "Initializing analysis...",
            "timestamp": datetime.now().isoformat(),
            "league_id": league_id,
            "season": season,
        }

        def run():
            lock = get_analysis_lock(league_id, season)
            with lock:
                try:
                    analysis_main.run_analysis(
                        username, season, league_id,
                        storage=storage,
                        progress_cb=_make_progress_callback(analysis_id),
                    )
                    analysis_status[analysis_id].update({
                        "status": "completed",
                        "progress": 100,
                        "message": "Analysis completed successfully!",
                    })
                except Exception as e:
                    print(f"Error running analysis: {e}")
                    import traceback
                    traceback.print_exc()
                    analysis_status[analysis_id].update({
                        "status": "error",
                        "progress": 100,
                        "message": f"Analysis failed: {str(e)}",
                    })
                finally:
                    with _active_analyses_guard:
                        if active_analyses.get(key) == analysis_id:
                            del active_analyses[key]

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        return jsonify({
            "analysis_id": analysis_id,
            "status": "started",
            "message": "Analysis started successfully"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/status/<analysis_id>')
def get_analysis_status(analysis_id):
    """Get the status of a running analysis"""
    if analysis_id not in analysis_status:
        return jsonify({"error": "Analysis not found"}), 404

    return jsonify(analysis_status[analysis_id])


def _require_league_season_params():
    league_id = request.args.get('league_id')
    season = request.args.get('season')
    if not league_id or not season:
        return None, None, (jsonify({"error": "league_id and season query parameters are required"}), 400)
    return league_id, season, None


@app.route('/api/results')
def get_analysis_results():
    """List available analysis results for a specific league+season."""
    league_id, season, error = _require_league_season_params()
    if error:
        return error

    try:
        return jsonify({
            "html_reports": storage.list_html_reports(league_id, season),
            "json_data": storage.list_json_data(league_id, season),
            "meta": storage.read_meta(league_id, season),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/results/<path:filename>')
def serve_results(filename):
    """Serve one analysis result file, scoped to a specific league+season."""
    league_id, season, error = _require_league_season_params()
    if error:
        return error

    html_path = storage.html_report_path(league_id, season, filename)
    if html_path:
        return send_from_directory(os.path.dirname(html_path), filename)

    json_path = storage.json_data_path(league_id, season, filename)
    if json_path:
        return send_from_directory(os.path.dirname(json_path), filename)

    return jsonify({"error": "File not found"}), 404


if __name__ == '__main__':
    print("Starting Fantasy Football Analysis Server...")
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    # Single-process, multi-threaded: analysis_status/active_analyses are in-memory and must
    # stay on one process. See Procfile/render.yaml (gunicorn --workers 1 --threads 8) and
    # AZURE_MIGRATION.md for why this constraint matters when choosing a host.
    app.run(debug=debug_mode, host='0.0.0.0', port=port, threaded=True)
