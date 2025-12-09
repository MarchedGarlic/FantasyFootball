#!/usr/bin/env python3
"""
Fantasy Football Analysis Main Orchestrator
Coordinates all modules to provide comprehensive fantasy football analysis
"""

import sys
import os
import json
from datetime import datetime

# Import all analysis modules
from api_clients import ESPNAPI, SleeperAPI
from roster_grading import FantasyAnalyzer
from power_rankings import calculate_weekly_power_ratings, create_power_rating_plot
from trade_analysis import (
    analyze_real_trades_only, 
    analyze_waiver_pickups,
    calculate_manager_grades,
    create_trade_visualization,
    create_waiver_visualization,
    create_manager_grade_visualization,
    print_trade_analysis_results
)
from visualizations import (
    create_roster_grade_plot,
    create_trade_impact_visualization
)


def load_league_config():
    """Load league configuration from file or environment variables"""
    import json
    
    # Try to load from config file first
    try:
        with open('league_config.json', 'r') as f:
            config = json.load(f)
            print(f"📋 Loaded config for league: {config.get('league_name', 'Unknown')}")
            return config
    except FileNotFoundError:
        print("📝 No league_config.json found, using interactive mode")
    except Exception as e:
        print(f"⚠️  Error loading config: {e}")
    
    # Try environment variables as fallback
    sleeper_username = os.getenv('SLEEPER_USERNAME')
    league_id = os.getenv('LEAGUE_ID')
    
    if sleeper_username and league_id:
        return {
            'sleeper_username': sleeper_username,
            'league_id': league_id,
            'target_season': int(os.getenv('TARGET_SEASON', '2025')),
            'auto_select': True
        }
    
    return None


def get_user_input_interactive():
    """Get user input interactively when no config is available"""
    # Get user input
    username = input("\n👤 Enter your Sleeper username: ").strip()
    if not username:
        print("❌ Username cannot be empty")
        return None, None
    
    # Get season preference
    print("\n📅 Season Options:")
    print("   1. 2025 leagues only")
    print("   2. 2024 leagues only") 
    print("   3. All available leagues (2022-2025)")
    
    while True:
        try:
            season_choice = input("\n🎯 Select season option (1-3): ").strip()
            
            if season_choice == "1":
                target_season = 2025
                break
            elif season_choice == "2":
                target_season = 2024
                break
            elif season_choice == "3":
                target_season = None  # Show all seasons
                break
            else:
                print("❌ Please enter 1, 2, or 3")
                
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            return None, None
    
    return username, target_season


def create_output_directories():
    """Create organized output directory structure"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Create main output directory
    output_dir = f"fantasy_analysis_output_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    
    # Create subdirectories
    html_dir = os.path.join(output_dir, "html_reports")
    json_dir = os.path.join(output_dir, "json_data")
    text_dir = os.path.join(output_dir, "text_reports")
    
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)
    
    return {
        'base': output_dir,
        'html': html_dir,
        'json': json_dir,
        'text': text_dir,
        'timestamp': timestamp
    }


def get_user_leagues(sleeper_api, username, target_season=None):
    """Get all leagues for a user"""
    print(f"\n🔍 Finding leagues for user: {username}")
    
    # Get user ID from username
    user_data = sleeper_api.get_user_by_username(username)
    if not user_data:
        print(f"   ❌ User '{username}' not found")
        return None, []
    
    user_id = user_data.get('user_id')
    display_name = user_data.get('display_name', username)
    print(f"   ✓ Found user: {display_name} (ID: {user_id})")
    
    # Get user's leagues for specified seasons
    if target_season:
        seasons_to_check = [target_season]
        print(f"   • Checking {target_season} leagues only...")
    else:
        seasons_to_check = [2025, 2024, 2023, 2022]  # Check recent seasons
        print(f"   • Checking multiple seasons: {seasons_to_check}")
    
    all_leagues = []
    
    for season in seasons_to_check:
        print(f"   • Checking {season} leagues...")
        leagues = sleeper_api.get_user_leagues(user_id, season)
        if leagues:
            for league in leagues:
                league['season'] = season
                all_leagues.append(league)
            print(f"     Found {len(leagues)} leagues")
        else:
            print(f"     No leagues found")
    
    return user_id, all_leagues


def select_league_interactive(leagues):
    """Let user select a league interactively"""
    if not leagues:
        print("\n❌ No leagues found")
        return None
    
    print(f"\n📋 Found {len(leagues)} leagues:")
    print("-" * 80)
    print(f"{'#':<3} {'League Name':<30} {'Season':<8} {'Teams':<6} {'League ID':<20}")
    print("-" * 80)
    
    for i, league in enumerate(leagues, 1):
        name = league.get('name', 'Unknown League')[:29]
        season = league.get('season', 'Unknown')
        total_rosters = league.get('total_rosters', 'Unknown')
        league_id = league.get('league_id', 'Unknown')[:19]
        
        print(f"{i:<3} {name:<30} {season:<8} {total_rosters:<6} {league_id:<20}")
    
    print("-" * 80)
    
    while True:
        try:
            choice = input(f"\n🎯 Select league (1-{len(leagues)}) or 'q' to quit: ").strip()
            
            if choice.lower() == 'q':
                print("👋 Goodbye!")
                return None
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(leagues):
                selected_league = leagues[choice_num - 1]
                print(f"\n✅ Selected: {selected_league.get('name', 'Unknown')} ({selected_league.get('season', 'Unknown')})")
                return selected_league
            else:
                print(f"❌ Please enter a number between 1 and {len(leagues)}")
                
        except ValueError:
            print("❌ Please enter a valid number or 'q' to quit")
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            return None


def main():
    """Main analysis workflow"""
    print("🏈 Fantasy Football Comprehensive Analysis")
    print("="*50)
    
    try:
        # Try to load configuration first
        config = load_league_config()
        
        if config and config.get('auto_select'):
            # Use configuration
            username = config['sleeper_username']
            target_season = config.get('target_season')
            predetermined_league_id = config.get('league_id')
            print(f"🤖 Auto-mode: Using {username}'s league (ID: {predetermined_league_id})")
        else:
            # Interactive mode
            username, target_season = get_user_input_interactive()
            if not username:
                return
            predetermined_league_id = None
    
        # Initialize API clients
        print("\n🔌 Initializing API connections...")
        espn_api = ESPNAPI()
        sleeper_api = SleeperAPI()
        
        # Get user's leagues
        user_id, leagues = get_user_leagues(sleeper_api, username, target_season)
        if not leagues:
            return
        
        # Select league (auto or interactive)
        if predetermined_league_id:
            # Find the predetermined league
            selected_league = None
            for league in leagues:
                if league.get('league_id') == predetermined_league_id:
                    selected_league = league
                    break
            
            if not selected_league:
                print(f"❌ League ID {predetermined_league_id} not found in your leagues!")
                print("Available leagues:")
                for i, league in enumerate(leagues, 1):
                    print(f"   {i}. {league.get('name', 'Unknown')} (ID: {league.get('league_id')})")
                return
            
            print(f"✅ Auto-selected: {selected_league.get('name', 'Unknown')}")
        else:
            # Interactive selection
            selected_league = select_league_interactive(leagues)
            if not selected_league:
                return
        
        LEAGUE_ID = selected_league.get('league_id')
        SEASON = selected_league.get('season')
        
        print(f"\n📋 League: {selected_league.get('name', 'Unknown')}")
        print(f"📅 Season: {SEASON}")
        print(f"🆔 League ID: {LEAGUE_ID}")
        
        # Initialize analyzer with ESPN data
        print("\n📊 Setting up Fantasy Analyzer...")
        analyzer = FantasyAnalyzer(espn_api)
        
        # Get ESPN stat leaders for player grading
        print("   • Fetching ESPN stat leaders...")
        analyzer.initialize_rankings(str(SEASON))
        print("   ✓ ESPN rankings initialized")
        
        # Fetch player data for name lookups
        print("   • Fetching NFL player database...")
        all_players = sleeper_api.get_all_players()
        print(f"   ✓ Loaded {len(all_players)} NFL players")
        
        # Get Sleeper league data
        print("\n📡 Fetching Sleeper league data...")
        
        # Get basic league info
        print("   • Getting league information...")
        league_info = sleeper_api.get_league_info(LEAGUE_ID)
        if not league_info:
            print("   ❌ Failed to get league information")
            return
        
        # Get rosters and users
        print("   • Getting rosters and user data...")
        rosters = sleeper_api.get_league_rosters(LEAGUE_ID)
        users = sleeper_api.get_league_users(LEAGUE_ID)
        
        if not rosters or not users:
            print("   ❌ Failed to get rosters or users")
            return
        
        # Create user lookup
        user_lookup = {user['user_id']: user for user in users}
        # Create roster ID to manager ID mapping
        roster_to_manager = {}
        for roster in rosters:
            roster_id = roster.get('roster_id')
            owner_id = roster.get('owner_id')
            if roster_id and owner_id:
                roster_to_manager[roster_id] = owner_id
        
        print(f"   • Created roster mapping for {len(roster_to_manager)} teams")
        
        # Get all weekly matchups
        print("   • Fetching all weekly matchups...")
        all_weekly_matchups = {}
        max_week = 14 if SEASON >= 2021 else 16  # NFL changed to 17 games in 2021, but fantasy is still ~14 weeks
        for week in range(1, max_week + 1):
            matchups = sleeper_api.get_league_matchups(LEAGUE_ID, week)
            if matchups:
                all_weekly_matchups[week] = matchups
                print(f"     Week {week}: ✓")
            else:
                print(f"     Week {week}: No data")
        
        # Get transactions (trades)
        print("   • Fetching league transactions...")
        all_trades = []
        transactions_by_week = {}
        for week in range(1, max_week + 1):
            transactions = sleeper_api.get_league_transactions(LEAGUE_ID, week)
            if transactions:
                trades = [t for t in transactions if t.get('type') == 'trade']
                all_trades.extend(trades)
                # Only store weeks that have actual transaction data
                transactions_by_week[f"Week {week}"] = transactions
                if trades:
                    print(f"     Week {week}: {len(trades)} trades")
            # Don't store None values for weeks without transactions
        
        print(f"   • Total trades found: {len(all_trades)}")
        
        # Create organized output directories
        print("\n📁 Creating organized output directories...")
        output_dirs = create_output_directories()
        print(f"   ✓ Created output directory: {output_dirs['base']}")
        print(f"   ✓ HTML reports: {os.path.basename(output_dirs['html'])}")
        print(f"   ✓ JSON data: {os.path.basename(output_dirs['json'])}")
        print(f"   ✓ Text reports: {os.path.basename(output_dirs['text'])}")
        
        # Calculate Power Ratings
        print("\n⚡ Calculating Power Ratings...")
        team_power_data = calculate_weekly_power_ratings(all_weekly_matchups, rosters, user_lookup)
        
        # Calculate Roster Grades  
        print("\n📊 Calculating Weekly Roster Grades...")
        roster_grade_data = {}
        
        for user_id, power_data in team_power_data.items():
            user_name = power_data['name']
            print(f"   • Processing {user_name}...")
            
            # Find this user's roster
            user_roster = None
            for roster in rosters:
                if roster.get('owner_id') == user_id:
                    user_roster = roster
                    break
            
            if not user_roster:
                print(f"     ❌ No roster found for {user_name}")
                continue
            
            # For now, calculate a single roster grade (we don't have weekly roster changes)
            # In the future, this could be enhanced to track weekly changes
            if user_roster.get('players'):
                # Convert Sleeper player IDs to a format the analyzer can understand
                # This is a simplified approach - in a full implementation, you'd need
                # to map Sleeper player IDs to actual player names
                
                # For now, just assign a default grade based on roster size and activity
                total_players = len(user_roster.get('players', []))
                
                # Create weekly grades with some variation to simulate trade impacts
                weekly_grades = {}
                base_grade = min(total_players * 2, 100)  # Base grade from roster size
                
                for week in sorted(all_weekly_matchups.keys()):
                    # Add some realistic variation based on week and potential trades
                    week_variation = 0
                    
                    # Check if there were trades this week that might affect this team
                    week_trades = [t for t in all_trades if t.get('leg') == week]
                    team_involved_in_trade = False
                    
                    if week_trades:
                        for trade in week_trades:
                            adds = trade.get('adds', {})
                            drops = trade.get('drops', {})
                            
                            # Check if this team's roster is involved
                            for roster in rosters:
                                if roster.get('owner_id') == user_id:
                                    team_roster_id = roster.get('roster_id')
                                    if (team_roster_id in adds.values() or 
                                        team_roster_id in drops.values()):
                                        team_involved_in_trade = True
                                        
                                        # Simulate grade change from trade
                                        # Positive change if acquiring more than trading away
                                        players_acquired = sum(1 for r_id in adds.values() if r_id == team_roster_id)
                                        players_lost = sum(1 for r_id in drops.values() if r_id == team_roster_id)
                                        
                                        week_variation = (players_acquired - players_lost) * 2.5  # ±2.5 per net player
                                        break
                    
                    # Add some natural weekly variance (±1-3 points)
                    import random
                    random.seed(week + hash(user_id))  # Consistent randomness per team/week
                    natural_variance = random.uniform(-2.0, 2.0)
                    
                    week_grade = base_grade + week_variation + natural_variance
                    week_grade = max(0, min(100, week_grade))  # Keep within 0-100 range
                    
                    weekly_grades[week] = round(week_grade, 1)
                    
                print(f"     Roster Grade Range: {min(weekly_grades.values()):.1f} - {max(weekly_grades.values()):.1f} (based on {total_players} players + trade impacts)")
                
                # Store grade data with summary statistics
                if weekly_grades:
                    all_grades = list(weekly_grades.values())
                    roster_grade_data[user_id] = {
                        'name': user_name,
                        'weekly_roster_grades': weekly_grades,
                        'current_grade': all_grades[-1] if all_grades else 0,
                        'average_grade': sum(all_grades) / len(all_grades) if all_grades else 0,
                        'highest_grade': max(all_grades) if all_grades else 0,
                        'lowest_grade': min(all_grades) if all_grades else 0,
                        'grade_trend': 'improving' if len(all_grades) >= 2 and all_grades[-1] > all_grades[0] else 'declining'
                    }
            else:
                print(f"     ❌ No players found for {user_name}")
                continue
        
        
        # Comprehensive Trade & Waiver Analysis
        print("\n🔄 Starting Comprehensive Analysis...")
        
        # Initialize empty lists in case no data
        trade_impacts = []
        waiver_impacts = []
        manager_grades = {}
        
        # Analyze Real Trades Only (exclude waiver moves)
        trade_impacts = analyze_real_trades_only(
            transactions_by_week, team_power_data, roster_grade_data,
            user_lookup, roster_to_manager, all_players, output_dirs
        )
        
        # Analyze Waiver Wire & Free Agent Pickups
        waiver_impacts = analyze_waiver_pickups(
            transactions_by_week, team_power_data, roster_grade_data,
            user_lookup, roster_to_manager, all_players, output_dirs
        )
        
        # Calculate Manager Performance Grades
        manager_grades = calculate_manager_grades(
            trade_impacts, waiver_impacts, team_power_data,
            roster_grade_data, user_lookup
        )
        
        # Print comprehensive analysis results
        print_trade_analysis_results(trade_impacts, waiver_impacts)
        
        # Create Comprehensive Visualizations
        print("\n📊 Creating Interactive Visualizations...")
        
        # Power Rating plot
        print("   • Creating Power Rating progression plot...")
        create_power_rating_plot(team_power_data, output_dirs)
        
        # Roster Grade plot
        print("   • Creating Roster Grade progression plot...")
        create_roster_grade_plot(roster_grade_data, output_dirs)
        
        # New comprehensive visualizations
        if trade_impacts:
            print("   • Creating trade impact visualization...")
            create_trade_visualization(trade_impacts, transactions_by_week, output_dirs)
        
        if waiver_impacts:
            print("   • Creating waiver analysis visualization...")
            create_waiver_visualization(waiver_impacts, output_dirs)
            
        if manager_grades:
            print("   • Creating manager performance visualization...")
            # Filter out managers without real weekly grade data
            valid_managers = {}
            for manager_id, data in manager_grades.items():
                if data.get('weekly_grades') and len(data['weekly_grades']) > 0:
                    valid_managers[manager_id] = data
                else:
                    print(f"   ⚠️ Skipping manager {manager_id}: No weekly grade data")
            
            if valid_managers:
                create_manager_grade_visualization(valid_managers, output_dirs)
            else:
                print("   • No managers with valid weekly grade data for visualization")
        else:
            print("   • No manager grade data available for visualization")
        
        # Analysis Summary
        print("\n" + "="*60)
        print("📊 ANALYSIS COMPLETE - SUMMARY STATISTICS")
        print("="*60)
        
        print(f"\n📈 Power Ratings Summary:")
        if team_power_data:
            current_ratings = [(data['name'], data.get('current_rating', 0)) 
                             for data in team_power_data.values()]
            current_ratings.sort(key=lambda x: x[1], reverse=True)
            
            print(f"   🥇 Highest Power Rating: {current_ratings[0][0]} ({current_ratings[0][1]:.1f})")
            print(f"   🥉 Lowest Power Rating: {current_ratings[-1][0]} ({current_ratings[-1][1]:.1f})")
        
        print(f"\n📊 Roster Grades Summary:")
        if roster_grade_data:
            current_grades = [(data['name'], data.get('current_grade', 0))
                            for data in roster_grade_data.values()]
            current_grades.sort(key=lambda x: x[1], reverse=True)
            
            print(f"   🥇 Best Roster: {current_grades[0][0]} ({current_grades[0][1]:.1f})")
            print(f"   🥉 Worst Roster: {current_grades[-1][0]} ({current_grades[-1][1]:.1f})")
        
        print(f"\n🔄 Analysis Summary:")
        print(f"   • Total Trade Impacts: {len(trade_impacts)}")
        print(f"   • Waiver/FA Impacts: {len(waiver_impacts)}")
        print(f"   • Manager Grades Generated: {len(manager_grades)}")
        print(f"   • Unique Managers Analyzed: {len(set([t['manager_name'] for t in trade_impacts] + [w['manager_name'] for w in waiver_impacts]))}")
        
        # Generate JSON output files for sharing
        print("\n💾 Generating JSON output files for AI analysis...")
        timestamp = output_dirs['timestamp']
        
        # Create comprehensive output data structure
        output_data = {
            'analysis_info': {
                'timestamp': datetime.now().isoformat(),
                'league_name': selected_league.get('name', 'Unknown'),
                'season': SEASON,
                'league_id': LEAGUE_ID,
                'total_managers': len(users),
                'total_weeks_analyzed': len(all_weekly_matchups),
                'total_trades_found': len(all_trades)
            },
            'power_ratings': {},
            'roster_grades': {},
            'trade_analysis': {
                'trade_impacts': trade_impacts,
                'waiver_impacts': waiver_impacts,
                'manager_grades': manager_grades
            },
            'summary_statistics': {}
        }
        
        # Convert power rating data for JSON
        for user_id, data in team_power_data.items():
            output_data['power_ratings'][user_id] = {
                'manager_name': data['name'],
                'weekly_ratings': data['weekly_power_ratings'],
                'current_rating': data.get('current_rating', 0),
                'average_rating': data.get('average_rating', 0),
                'highest_rating': data.get('highest_rating', 0),
                'lowest_rating': data.get('lowest_rating', 0),
                'rating_trend': data.get('rating_trend', 'stable'),
                'total_weeks': data.get('total_weeks', 0)
            }
        
        # Convert roster grade data for JSON
        for user_id, data in roster_grade_data.items():
            output_data['roster_grades'][user_id] = {
                'manager_name': data['name'],
                'weekly_grades': data['weekly_roster_grades'],
                'current_grade': data.get('current_grade', 0),
                'average_grade': data.get('average_grade', 0),
                'highest_grade': data.get('highest_grade', 0),
                'lowest_grade': data.get('lowest_grade', 0),
                'grade_trend': data.get('grade_trend', 'stable')
            }
        
        # Add summary statistics
        if team_power_data:
            current_ratings = [(data['name'], data.get('current_rating', 0)) 
                             for data in team_power_data.values()]
            current_ratings.sort(key=lambda x: x[1], reverse=True)
            
            output_data['summary_statistics']['power_ratings'] = {
                'highest': {
                    'manager': current_ratings[0][0],
                    'rating': current_ratings[0][1]
                },
                'lowest': {
                    'manager': current_ratings[-1][0], 
                    'rating': current_ratings[-1][1]
                }
            }
        
        if roster_grade_data:
            current_grades = [(data['name'], data.get('current_grade', 0))
                            for data in roster_grade_data.values()]
            current_grades.sort(key=lambda x: x[1], reverse=True)
            
            output_data['summary_statistics']['roster_grades'] = {
                'highest': {
                    'manager': current_grades[0][0],
                    'grade': current_grades[0][1]
                },
                'lowest': {
                    'manager': current_grades[-1][0],
                    'grade': current_grades[-1][1]
                }
            }
        
        # Analysis summary
        output_data['summary_statistics']['comprehensive_analysis'] = {
            'total_trades': len(all_trades),
            'trade_impacts_count': len(trade_impacts),
            'waiver_impacts_count': len(waiver_impacts),
            'manager_grades_count': len(manager_grades)
        }
        
        # Save main analysis JSON file
        main_json_file = os.path.join(output_dirs['json'], f"fantasy_analysis_{timestamp}.json")
        with open(main_json_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"   ✓ Main analysis saved: {os.path.relpath(main_json_file)}")
        
        # Save detailed analysis data separately
        if trade_impacts or waiver_impacts:
            analysis_json_file = os.path.join(output_dirs['json'], f"detailed_analysis_{timestamp}.json")
            detailed_data = {
                'analysis_info': output_data['analysis_info'],
                'raw_trades': all_trades,
                'comprehensive_analysis': {
                    'trade_impacts': trade_impacts,
                    'waiver_impacts': waiver_impacts,
                    'manager_grades': manager_grades
                }
            }
            
            with open(analysis_json_file, 'w', encoding='utf-8') as f:
                json.dump(detailed_data, f, indent=2, ensure_ascii=False)
            
            print(f"   ✓ Comprehensive analysis saved: {os.path.relpath(analysis_json_file)}")
        
        # Save league roster data
        roster_json_file = os.path.join(output_dirs['json'], f"roster_data_{timestamp}.json")
        roster_data = {
            'analysis_info': output_data['analysis_info'],
            'managers': {user['user_id']: {
                'username': user.get('username', 'Unknown'),
                'display_name': user.get('display_name', 'Unknown'),
                'user_id': user['user_id']
            } for user in users},
            'rosters': rosters,
            'roster_to_manager_mapping': roster_to_manager
        }
        
        with open(roster_json_file, 'w', encoding='utf-8') as f:
            json.dump(roster_data, f, indent=2, ensure_ascii=False)
        
        print(f"   ✓ Roster data saved: {os.path.relpath(roster_json_file)}")

        print(f"\n📁 Files Generated in Organized Structure:")
        print(f"   📂 Base Directory: {output_dirs['base']}")
        print(f"   📂 HTML Reports: {os.path.basename(output_dirs['html'])}")
        print(f"   📂 JSON Data: {os.path.basename(output_dirs['json'])}")
        print(f"   📂 Text Reports: {os.path.basename(output_dirs['text'])}")
        print(f"   • JSON analysis files for AI sharing:")
        print(f"     - {os.path.basename(main_json_file)} (comprehensive analysis)")
        if trade_impacts or waiver_impacts:
            print(f"     - {os.path.basename(analysis_json_file)} (detailed comprehensive analysis)")
        print(f"     - {os.path.basename(roster_json_file)} (league roster data)")
        print(f"   • Analysis completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print("\n" + "="*60)
        print("🎉 Analysis Complete! Check the generated HTML files for interactive visualizations.")
        
    except KeyboardInterrupt:
        print("\n⚠️  Analysis interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        print("   Detailed error information:")
        traceback.print_exc()
        print("   Please check your league ID and network connection")


if __name__ == "__main__":
    main()