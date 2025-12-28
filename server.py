#!/usr/bin/env python3
"""
Fantasy Football Analysis Server
Web server to handle league selection and analysis generation
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import json
import subprocess
import threading
from datetime import datetime
import requests

app = Flask(__name__)
CORS(app)

# Store analysis status
analysis_status = {}

class SleeperAPI:
    """Sleeper API wrapper to fetch user leagues"""
    
    def __init__(self):
        self.base_url = "https://api.sleeper.app/v1"
        
    def get_user_by_username(self, username):
        """Get user info by username"""
        try:
            response = requests.get(f"{self.base_url}/user/{username}")
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    # Response is not valid JSON
                    print(f"Invalid JSON response for user {username}")
                    return None
            elif response.status_code == 404:
                print(f"User {username} not found")
                return None
            else:
                print(f"API error {response.status_code} for user {username}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Network error fetching user {username}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error fetching user {username}: {e}")
            return None
    
    def get_user_leagues(self, user_id, season):
        """Get all leagues for a user in a given season"""
        try:
            response = requests.get(f"{self.base_url}/user/{user_id}/leagues/nfl/{season}")
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    # Response is not valid JSON
                    print(f"Invalid JSON response for leagues {user_id}")
                    return []
            elif response.status_code == 404:
                print(f"No leagues found for user {user_id} in season {season}")
                return []
            else:
                print(f"API error {response.status_code} for user {user_id} leagues")
                return []
        except requests.exceptions.RequestException as e:
            print(f"Network error fetching leagues for {user_id}: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error fetching leagues for {user_id}: {e}")
            return []

sleeper_api = SleeperAPI()

@app.route('/')
def serve_index():
    """Serve the main index page"""
    return send_from_directory('.', 'index.html')

@app.route('/api/user/<username>')
def get_user_leagues(username):
    """Get all leagues for a given Sleeper username"""
    try:
        # Validate username
        if not username or not username.strip():
            return jsonify({"error": "Username is required"}), 400
        
        username = username.strip()
        
        # Get user info first
        user = sleeper_api.get_user_by_username(username)
        if not user:
            return jsonify({"error": f"Sleeper user '{username}' not found. Please check the username and try again."}), 404
        
        user_id = user.get('user_id')
        if not user_id:
            return jsonify({"error": "Invalid user data received from Sleeper"}), 400
        
        # Get leagues for current season (2025)
        current_season = 2025
        leagues = sleeper_api.get_user_leagues(user_id, current_season)
        
        # Check if user has any leagues
        if not leagues:
            return jsonify({
                "user": {
                    "username": user.get('username'),
                    "display_name": user.get('display_name'),
                    "user_id": user_id
                },
                "leagues": [],
                "message": f"No leagues found for {username} in the {current_season} season."
            })
        
        # Format league data for frontend
        formatted_leagues = []
        for league in leagues:
            formatted_leagues.append({
                'league_id': league.get('league_id'),
                'name': league.get('name'),
                'total_rosters': league.get('total_rosters'),
                'status': league.get('status'),
                'season': league.get('season'),
                'settings': {
                    'playoff_teams': league.get('settings', {}).get('playoff_teams'),
                    'league_average_match': league.get('settings', {}).get('league_average_match')
                }
            })
        
        return jsonify({
            "user": {
                "username": user.get('username'),
                "display_name": user.get('display_name'),
                "user_id": user_id
            },
            "leagues": formatted_leagues
        })
        
    except Exception as e:
        print(f"Unexpected error in get_user_leagues: {e}")
        return jsonify({"error": "An unexpected error occurred. Please try again."}), 500

@app.route('/api/analyze', methods=['POST'])
def start_analysis():
    """Start analysis for a selected league"""
    try:
        data = request.get_json()
        username = data.get('username')
        league_id = data.get('league_id')
        league_name = data.get('league_name')
        
        if not all([username, league_id, league_name]):
            return jsonify({"error": "Missing required parameters"}), 400
        
        # Create a unique analysis ID
        analysis_id = f"{username}_{league_id}_{int(datetime.now().timestamp())}"
        
        # Update config file with selected league
        config = {
            "sleeper_username": username,
            "target_season": 2025,
            "league_name": league_name,
            "league_id": league_id,
            "auto_select": True
        }
        
        with open('league_config.json', 'w') as f:
            json.dump(config, f, indent=2)
        
        # Set initial status
        analysis_status[analysis_id] = {
            "status": "starting",
            "progress": 0,
            "message": "Initializing analysis...",
            "timestamp": datetime.now().isoformat()
        }
        
        # Start analysis in background thread
        def run_analysis():
            try:
                analysis_status[analysis_id].update({
                    "status": "running",
                    "progress": 25,
                    "message": "Running Python analysis script..."
                })
                
                # Run the main Python analysis
                result = subprocess.run(['python', 'main.py'], 
                                      capture_output=True, text=True)
                
                if result.returncode == 0:
                    analysis_status[analysis_id].update({
                        "status": "building",
                        "progress": 75,
                        "message": "Building frontend assets..."
                    })
                    
                    # Run the build process
                    build_result = subprocess.run(['npm', 'run', 'build'], 
                                                capture_output=True, text=True)
                    
                    if build_result.returncode == 0:
                        analysis_status[analysis_id].update({
                            "status": "completed",
                            "progress": 100,
                            "message": "Analysis completed successfully!"
                        })
                    else:
                        analysis_status[analysis_id].update({
                            "status": "error",
                            "progress": 100,
                            "message": f"Build failed: {build_result.stderr}"
                        })
                else:
                    analysis_status[analysis_id].update({
                        "status": "error",
                        "progress": 100,
                        "message": f"Analysis failed: {result.stderr}"
                    })
                    
            except Exception as e:
                analysis_status[analysis_id].update({
                    "status": "error",
                    "progress": 100,
                    "message": f"Unexpected error: {str(e)}"
                })
        
        # Start analysis thread
        thread = threading.Thread(target=run_analysis)
        thread.daemon = True
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

@app.route('/api/results')
def get_analysis_results():
    """Get available analysis results"""
    try:
        results = {}
        
        # Check for HTML reports
        html_dir = 'fantasy_analysis_output/html_reports'
        if os.path.exists(html_dir):
            html_files = [f for f in os.listdir(html_dir) if f.endswith('.html')]
            results['html_reports'] = html_files
        
        # Check for JSON data
        json_dir = 'fantasy_analysis_output/json_data'
        if os.path.exists(json_dir):
            json_files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
            results['json_data'] = json_files
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/results/<path:filename>')
def serve_results(filename):
    """Serve analysis result files"""
    # Check if it's an HTML report
    html_path = f'fantasy_analysis_output/html_reports/{filename}'
    if os.path.exists(html_path):
        return send_from_directory('fantasy_analysis_output/html_reports', filename)
    
    # Check if it's JSON data
    json_path = f'fantasy_analysis_output/json_data/{filename}'
    if os.path.exists(json_path):
        return send_from_directory('fantasy_analysis_output/json_data', filename)
    
    return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    print("🚀 Starting Fantasy Football Analysis Server...")
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)