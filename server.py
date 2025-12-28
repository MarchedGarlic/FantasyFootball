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
import openai
import re

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
        
        # Server-side input validation
        if len(username) > 30:
            return jsonify({"error": "Username must be 30 characters or less"}), 400
        
        # Check for alphanumeric characters only (English letters and numbers)
        if not re.match(r'^[a-zA-Z0-9]+$', username):
            return jsonify({"error": "Username can only contain English letters (a-z, A-Z) and numbers (0-9)"}), 400
        
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
            # Define progress stages with more specific descriptions
            progress_stages = [
                (5, "Initializing analysis..."),
                (10, "Loading league configuration..."),
                (15, "Connecting to ESPN API..."),
                (20, "Fetching Sleeper league data..."),
                (25, "Pulling ESPN stat leaders..."),
                (30, "Loading NFL player database..."),
                (35, "Getting league rosters and users..."),
                (40, "Fetching weekly matchups..."),
                (45, "Analyzing trade transactions..."),
                (50, "Calculating power rankings..."),
                (60, "Computing median records..."),
                (70, "Grading team rosters..."),
                (75, "Analyzing trade impacts..."),
                (80, "Processing waiver pickups..."),
                (85, "Creating interactive visualizations..."),
                (90, "Generating HTML reports..."),
                (95, "Saving JSON data files..."),
                (100, "Analysis completed successfully!")
            ]
            
            try:
                current_stage = 0
                
                def update_progress(stage_index):
                    if stage_index < len(progress_stages):
                        progress, message = progress_stages[stage_index]
                        analysis_status[analysis_id].update({
                            "status": "running",
                            "progress": progress,
                            "message": message
                        })
                        return True
                    return False
                
                # Start with first stage
                update_progress(current_stage)
                current_stage += 1
                
                # Import and run the main analysis directly instead of subprocess
                import sys
                import os
                import time
                
                update_progress(current_stage)
                current_stage += 1
                
                # Save current argv to restore later
                original_argv = sys.argv[:]
                
                # Set up argv for main.py
                sys.argv = ['main.py']
                
                # Change to the correct directory
                original_cwd = os.getcwd()
                script_dir = os.path.dirname(os.path.abspath(__file__))
                os.chdir(script_dir)
                
                try:
                    # Import and run main.py directly with progress tracking
                    import main
                    
                    # Hook into the main analysis flow with progress updates
                    original_print = print
                    
                    def progress_aware_print(*args, **kwargs):
                        nonlocal current_stage
                        message = ' '.join(str(arg) for arg in args)
                        
                        # Track progress based on key messages from main.py
                        if "Initializing API connections" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Fetching Sleeper league data" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Fetching ESPN stat leaders" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Fetching NFL player database" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Getting rosters and user data" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Fetching all weekly matchups" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Fetching league transactions" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Calculating Power Ratings" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Calculating Median-Based Combined Records" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Calculating Weekly Roster Grades" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Starting Comprehensive Analysis" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "analyze_waiver_pickups" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Creating Interactive Visualizations" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        elif "Generating JSON output files" in message and current_stage < len(progress_stages):
                            update_progress(current_stage)
                            current_stage += 1
                        
                        return original_print(*args, **kwargs)
                    
                    # Temporarily replace print function
                    import builtins
                    builtins.print = progress_aware_print
                    
                    # If main.py has a main function, call it
                    if hasattr(main, 'main'):
                        main.main()
                    
                    # Restore original print
                    builtins.print = original_print
                    
                    # Final completion update
                    analysis_status[analysis_id].update({
                        "status": "completed",
                        "progress": 100,
                        "message": "Analysis completed successfully!"
                    })
                    
                except Exception as e:
                    print(f"Error running analysis: {e}")
                    analysis_status[analysis_id].update({
                        "status": "error",
                        "progress": 100,
                        "message": f"Analysis failed: {str(e)}"
                    })
                finally:
                    # Restore original state
                    sys.argv = original_argv
                    os.chdir(original_cwd)
                    # Ensure print is restored
                    import builtins
                    builtins.print = original_print
                    
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

@app.route('/api/ai-overview')
def generate_ai_overview():
    """Generate AI-powered team overview"""
    try:
        # Check if analysis files exist
        fantasy_json_path = 'fantasy_analysis_output/json_data/fantasy_analysis.json'
        roster_json_path = 'fantasy_analysis_output/json_data/roster_data.json'
        
        if not os.path.exists(fantasy_json_path) or not os.path.exists(roster_json_path):
            return jsonify({"error": "Analysis data not found. Please run an analysis first."}), 404
        
        # Read analysis data
        with open(fantasy_json_path, 'r') as f:
            fantasy_data = json.load(f)
        
        with open(roster_json_path, 'r') as f:
            roster_data = json.load(f)
            
        # Try to read detailed analysis if it exists
        detailed_json_path = 'fantasy_analysis_output/json_data/detailed_analysis.json'
        detailed_data = {}
        if os.path.exists(detailed_json_path):
            with open(detailed_json_path, 'r') as f:
                detailed_data = json.load(f)
        
        # Generate AI overview
        ai_overview = create_ai_team_overview(fantasy_data, roster_data, detailed_data)
        
        return jsonify({"overview": ai_overview})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def create_ai_team_overview(fantasy_data, roster_data, detailed_data):
    """Create AI-powered team overview using OpenAI"""
    try:
        # Set up OpenAI client (you'll need to set OPENAI_API_KEY environment variable)
        client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY', 'dummy-key'))
        
        # Prepare comprehensive data summary for AI
        league_info = fantasy_data.get('analysis_info', {})
        power_ratings = fantasy_data.get('power_ratings', {})
        managers = roster_data.get('managers', {})
        trade_analysis = fantasy_data.get('trade_analysis', {})
        rosters = roster_data.get('rosters', [])
        
        # Create comprehensive prompt for AI
        prompt = f"""
        Create an in-depth fantasy football league analysis with detailed team profiles:
        
        League: {league_info.get('league_name', 'Unknown')}
        Season: {league_info.get('season', 'Unknown')}
        Teams: {league_info.get('total_managers', 'Unknown')}
        Weeks Analyzed: {league_info.get('total_weeks_analyzed', 'Unknown')}
        Total Trades: {league_info.get('total_trades_found', 0)}
        
        For each team, write 3-4 detailed paragraphs covering:
        1. Team Overview & Performance Trends
        2. Key Players & Roster Analysis
        3. Notable Trades & Decisions
        4. Standout Weeks & Critical Moments
        
        POWER RATING DATA:
        """
        
        # Add detailed power rating and performance data
        for user_id, data in power_ratings.items():
            manager_name = data.get('manager_name', 'Unknown')
            weekly_ratings = data.get('weekly_ratings', {})
            current_rating = data.get('current_rating', 0)
            average_rating = data.get('average_rating', 0)
            trend = data.get('rating_trend', 'stable')
            highest = data.get('highest_rating', 0)
            lowest = data.get('lowest_rating', 0)
            
            # Find roster data for this manager
            manager_roster = None
            for roster in rosters:
                if roster.get('owner_id') == user_id:
                    manager_roster = roster
                    break
            
            record = "Unknown"
            if manager_roster and manager_roster.get('metadata', {}).get('record'):
                record_str = manager_roster['metadata']['record']
                wins = record_str.count('W')
                losses = record_str.count('L')
                record = f"{wins}-{losses}"
            
            # Calculate week-to-week changes
            rating_changes = []
            prev_rating = None
            for week, rating in sorted(weekly_ratings.items(), key=lambda x: int(x[0])):
                if prev_rating is not None:
                    change = rating - prev_rating
                    rating_changes.append(f"Week {week}: {rating:.1f} ({'+' if change >= 0 else ''}{change:.1f})")
                else:
                    rating_changes.append(f"Week {week}: {rating:.1f}")
                prev_rating = rating
            
            prompt += f"""
            
            === {manager_name.upper()} ===
            Record: {record}
            Current Power Rating: {current_rating:.1f}
            Average Rating: {average_rating:.1f}
            Season High: {highest:.1f}
            Season Low: {lowest:.1f}
            Trend: {trend}
            
            Weekly Performance:
            {chr(10).join(rating_changes[-8:])}  # Last 8 weeks
            """
        
        # Add trade analysis
        if trade_analysis and 'trade_impacts' in trade_analysis:
            prompt += "\n\nTRADE ANALYSIS:\n"
            for trade in trade_analysis['trade_impacts'][:10]:  # Limit to prevent overflow
                manager_name = trade.get('manager_name', 'Unknown')
                week = trade.get('week', 'Unknown')
                acquired = ', '.join(trade.get('acquired_players', []))
                gave_up = ', '.join(trade.get('gave_up_players', []))
                impact = trade.get('power_impact', 0)
                other_manager = trade.get('other_manager', 'Unknown')
                
                prompt += f"""
                Week {week}: {manager_name} traded {gave_up} to {other_manager} for {acquired}
                Power Impact: {impact:+.1f} points
                """
        
        prompt += """
        
        ANALYSIS REQUIREMENTS:
        - Write in an engaging, storytelling style
        - Use fantasy football terminology and humor
        - Reference specific player names when available
        - Highlight dramatic moments and turning points
        - Discuss team strategies and decision-making
        - Compare teams to each other
        - Make predictions or observations about playoff chances
        - Keep each team analysis to 3-4 substantial paragraphs
        - Format in clean HTML with proper styling
        """
        
        # Try to use OpenAI (will fallback to mock if no API key)
        try:
            if os.environ.get('OPENAI_API_KEY') and os.environ.get('OPENAI_API_KEY') != 'dummy-key':
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are an expert fantasy football analyst who writes detailed, entertaining team profiles with specific insights about performance, trades, and key moments."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4000,
                    temperature=0.8
                )
                ai_content = response.choices[0].message.content
            else:
                # Enhanced fallback mock content
                ai_content = create_detailed_mock_overview(power_ratings, managers, trade_analysis, rosters)
        except Exception as e:
            print(f"OpenAI API error: {e}")
            # Fallback to enhanced mock content on any API error
            ai_content = create_detailed_mock_overview(power_ratings, managers, trade_analysis, rosters)
        
        return ai_content
        
    except Exception as e:
        return f"<p>Error generating AI overview: {str(e)}</p>"

def create_detailed_mock_overview(power_ratings, managers, trade_analysis, rosters):
    """Create detailed mock AI overview when OpenAI is not available"""
    html_content = "<div class='ai-overview'>"
    
    # Sort teams by current power rating
    sorted_teams = sorted(
        power_ratings.items(), 
        key=lambda x: x[1].get('current_rating', 0), 
        reverse=True
    )
    
    # Get trade data organized by manager
    manager_trades = {}
    if trade_analysis and 'trade_impacts' in trade_analysis:
        for trade in trade_analysis['trade_impacts']:
            manager_id = trade.get('manager_id')
            if manager_id not in manager_trades:
                manager_trades[manager_id] = []
            manager_trades[manager_id].append(trade)
    
    # Get roster records
    roster_records = {}
    for roster in rosters:
        owner_id = roster.get('owner_id')
        if roster.get('metadata', {}).get('record'):
            record_str = roster['metadata']['record']
            wins = record_str.count('W')
            losses = record_str.count('L')
            roster_records[owner_id] = f"{wins}-{losses}"
    
    for i, (user_id, data) in enumerate(sorted_teams):
        manager_name = data.get('manager_name', 'Unknown')
        current_rating = data.get('current_rating', 0)
        average_rating = data.get('average_rating', 0)
        trend = data.get('rating_trend', 'stable')
        highest = data.get('highest_rating', 0)
        lowest = data.get('lowest_rating', 0)
        weekly_ratings = data.get('weekly_ratings', {})
        record = roster_records.get(user_id, "Record Unknown")
        
        # Calculate detailed analytics
        rating_variance = highest - lowest
        recent_weeks = list(weekly_ratings.items())[-4:]  # Last 4 weeks
        recent_average = sum(float(week[1]) for week in recent_weeks) / len(recent_weeks) if recent_weeks else current_rating
        momentum = "gaining" if recent_average > average_rating else "losing" if recent_average < average_rating else "maintaining"
        
        # Find key weeks
        best_week = max(weekly_ratings.items(), key=lambda x: x[1]) if weekly_ratings else ("N/A", 0)
        worst_week = min(weekly_ratings.items(), key=lambda x: x[1]) if weekly_ratings else ("N/A", 0)
        
        # Analyze trades for this manager
        manager_trade_summary = ""
        if user_id in manager_trades:
            trades = manager_trades[user_id]
            total_impact = sum(trade.get('power_impact', 0) for trade in trades)
            best_trade = max(trades, key=lambda x: x.get('power_impact', 0)) if trades else None
            worst_trade = min(trades, key=lambda x: x.get('power_impact', 0)) if trades else None
            
            if best_trade:
                best_acquired = ', '.join(best_trade.get('acquired_players', [])[:2])
                best_gave = ', '.join(best_trade.get('gave_up_players', [])[:2])
                manager_trade_summary = f"Made {len(trades)} trade(s) this season. Best move: acquiring {best_acquired} for {best_gave} in Week {best_trade.get('week')} (+{best_trade.get('power_impact', 0):.1f} power points)."
            
        # Create detailed team narrative
        rank_emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
        
        # Performance tier analysis
        if current_rating >= 160:
            tier = "Championship Contender"
            tier_analysis = "This powerhouse team has established itself as a legitimate title threat with consistently dominant performances."
        elif current_rating >= 140:
            tier = "Playoff Hopeful"
            tier_analysis = "A solid team with playoff aspirations, showing the ability to compete with anyone on any given week."
        elif current_rating >= 120:
            tier = "Middle Tier Competitor"
            tier_analysis = "Right in the thick of things with potential for both breakthrough weeks and disappointing performances."
        else:
            tier = "Rebuilding Squad"
            tier_analysis = "Facing challenges this season but still capable of playing spoiler and building for the future."
        
        # Volatility analysis
        if rating_variance > 50:
            volatility_desc = "This team epitomizes the 'any given Sunday' mentality with explosive ceiling games balanced by concerning floor weeks. Fantasy managers facing this squad never know which version will show up."
        elif rating_variance > 30:
            volatility_desc = "Shows solid consistency with occasional spike weeks that can steal victories from higher-ranked opponents."
        else:
            volatility_desc = "The definition of reliability - you know exactly what you're getting week after week, making them a predictable but formidable opponent."
        
        # Momentum analysis
        momentum_desc = f"Currently {momentum} momentum with their recent stretch {'exceeding' if momentum == 'gaining' else 'falling short of' if momentum == 'losing' else 'matching'} their season average."
        
        html_content += f"""
        <div class='team-overview-card detailed-card'>
            <div class='team-header'>
                <h2>{rank_emoji} {manager_name}</h2>
                <div class='team-tier'>{tier}</div>
                <div class='team-record'>Record: {record} | Power Rating: {current_rating:.1f}</div>
            </div>
            
            <div class='analysis-section'>
                <h4>🎯 Season Overview</h4>
                <p>{tier_analysis} {momentum_desc} With a season-high of {highest:.1f} in Week {best_week[0]} and their lowest point of {lowest:.1f} in Week {worst_week[0]}, this team has shown a range of {rating_variance:.1f} points throughout the campaign.</p>
                
                <h4>📊 Performance Analysis</h4>
                <p>{volatility_desc} Their current trend is {trend}, which {'suggests they\'re peaking at the right time' if trend == 'improving' else 'indicates they may be struggling with recent roster decisions' if trend == 'declining' else 'shows remarkable consistency throughout the season'}. The team averages {average_rating:.1f} points but has proven they can reach {highest:.1f} when everything clicks.</p>
                
                <h4>💼 Strategic Decisions</h4>
                <p>{manager_trade_summary if manager_trade_summary else 'This manager has taken a patient approach, avoiding major trades and sticking with their drafted core.'} {'Their willingness to make moves has' if manager_trade_summary else 'Their conservative strategy has'} {'paid dividends' if current_rating > average_rating else 'been a mixed bag' if current_rating == average_rating else 'struggled to deliver results'} so far this season.</p>
                
                <h4>🔥 Key Moments & Outlook</h4>
                <p>Week {best_week[0]} stands out as their season-defining performance with a massive {best_week[1]:.1f} points, while Week {worst_week[0]} ({worst_week[1]:.1f} points) represents the type of showing they'll want to avoid in crunch time. {'As we head toward playoffs, this team has the momentum and talent to make noise' if trend == 'improving' and current_rating > 130 else 'They\'ll need to find their early-season form to make a playoff push' if trend == 'declining' else 'Consistency will be key as they look to maintain their position'}.</p>
            </div>
            
            <div class='team-stats-grid'>
                <div class='stat-item'>
                    <span class='stat-label'>Trend</span>
                    <span class='stat-value trend-{trend}'>{trend.title()}</span>
                </div>
                <div class='stat-item'>
                    <span class='stat-label'>Best Week</span>
                    <span class='stat-value best-week'>Week {best_week[0]}: {best_week[1]:.1f}</span>
                </div>
                <div class='stat-item'>
                    <span class='stat-label'>Worst Week</span>
                    <span class='stat-value worst-week'>Week {worst_week[0]}: {worst_week[1]:.1f}</span>
                </div>
                <div class='stat-item'>
                    <span class='stat-label'>Volatility</span>
                    <span class='stat-value'>{rating_variance:.1f} pts</span>
                </div>
            </div>
        </div>
        """
    
    html_content += "</div>"
    return html_content

def create_mock_ai_overview(power_ratings, managers):
    """Create mock AI overview when OpenAI is not available"""
    html_content = "<div class='ai-overview'>"
    
    # Sort teams by current power rating
    sorted_teams = sorted(
        power_ratings.items(), 
        key=lambda x: x[1].get('current_rating', 0), 
        reverse=True
    )
    
    for i, (user_id, data) in enumerate(sorted_teams):
        manager_name = data.get('manager_name', 'Unknown')
        current_rating = data.get('current_rating', 0)
        average_rating = data.get('average_rating', 0)
        trend = data.get('rating_trend', 'stable')
        highest = data.get('highest_rating', 0)
        lowest = data.get('lowest_rating', 0)
        
        # Create team personality based on stats
        if trend == 'improving':
            personality = "📈 The Rising Phoenix"
            description = f"{manager_name} is on fire! This team has been climbing the power rankings with impressive consistency."
        elif trend == 'declining':
            personality = "📉 The Fallen Giant" 
            description = f"{manager_name} started strong but has hit some rough patches. Time for a comeback story!"
        else:
            personality = "⚖️ The Steady Hand"
            description = f"{manager_name} brings consistent performance week after week. A reliable force in the league."
        
        # Analyze boom/bust potential
        rating_variance = highest - lowest
        if rating_variance > 40:
            volatility = "High-risk, high-reward player with explosive potential! 💥"
        elif rating_variance > 20:
            volatility = "Balanced team with some exciting upside weeks. ⚡"
        else:
            volatility = "Rock-solid consistency - you know what you're getting. 🗿"
        
        rank_emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
        
        html_content += f"""
        <div class='team-overview-card'>
            <h3>{rank_emoji} {manager_name} - {personality}</h3>
            <div class='team-stats'>
                <span class='power-rating'>Power Rating: {current_rating:.1f}</span>
                <span class='trend trend-{trend}'>Trend: {trend.title()}</span>
            </div>
            <p class='team-description'>{description}</p>
            <p class='volatility'><strong>Playing Style:</strong> {volatility}</p>
            <div class='key-weeks'>
                <span class='best-week'>🔥 Best Week: {highest:.1f}</span>
                <span class='worst-week'>💀 Worst Week: {lowest:.1f}</span>
            </div>
        </div>
        """
    
    html_content += "</div>"
    return html_content

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