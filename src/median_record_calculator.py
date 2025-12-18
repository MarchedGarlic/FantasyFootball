#!/usr/bin/env python3
"""
Median Record Calculator
Calculates weekly median scores and determines wins/losses vs median,
then combines with regular record for comprehensive team evaluation.
"""

import statistics
from typing import Dict, List, Tuple
from .api_clients import SleeperAPI


def calculate_median_records(all_weekly_matchups: Dict, rosters: List, user_lookup: Dict) -> Dict:
    """
    Calculate median-based records and combine with regular records.
    
    Args:
        all_weekly_matchups: Dictionary of weekly matchup data
        rosters: List of roster data
        user_lookup: Dictionary mapping user IDs to user info
    
    Returns:
        Dictionary with regular, median, and combined records for each team
    """
    print("\nCalculating Median-Based Records...")
    
    # Initialize team records
    team_records = {}
    
    # Create user_id to roster_id mapping
    user_to_roster = {}
    for roster in rosters:
        user_id = roster.get('owner_id')
        roster_id = roster.get('roster_id')
        if user_id and roster_id:
            user_to_roster[user_id] = roster_id
            
            # Initialize team record
            team_records[user_id] = {
                'name': user_lookup.get(user_id, {}).get('display_name', f'User {user_id}'),
                'regular_record': {'wins': 0, 'losses': 0, 'ties': 0},
                'median_record': {'wins': 0, 'losses': 0},
                'combined_record': {'wins': 0, 'losses': 0},
                'weekly_scores': {},
                'weekly_median_results': {}
            }
    
    # Process each week
    for week, matchups in all_weekly_matchups.items():
        if not matchups:
            continue
            
        print(f"   Processing Week {week}...")
        
        # Collect all scores for this week
        week_scores = []
        week_data = {}  # user_id -> score
        
        for matchup in matchups:
            roster_id = matchup.get('roster_id')
            points = matchup.get('points', 0) or 0
            
            # Find user_id for this roster_id
            user_id = None
            for uid, rid in user_to_roster.items():
                if rid == roster_id:
                    user_id = uid
                    break
            
            if user_id:
                week_scores.append(points)
                week_data[user_id] = points
                team_records[user_id]['weekly_scores'][week] = points
        
        # Calculate median for this week
        if len(week_scores) >= 2:
            median_score = statistics.median(week_scores)
            print(f"     Week {week} Median: {median_score:.1f}")
            
            # Group matchups for head-to-head records
            matchup_groups = {}
            for matchup in matchups:
                matchup_id = matchup.get('matchup_id')
                if matchup_id:
                    if matchup_id not in matchup_groups:
                        matchup_groups[matchup_id] = []
                    matchup_groups[matchup_id].append(matchup)
            
            # Calculate head-to-head wins/losses
            for matchup_id, teams in matchup_groups.items():
                if len(teams) == 2:
                    team1, team2 = teams
                    team1_points = team1.get('points', 0) or 0
                    team2_points = team2.get('points', 0) or 0
                    
                    # Find user_ids
                    team1_user = None
                    team2_user = None
                    for uid, rid in user_to_roster.items():
                        if rid == team1.get('roster_id'):
                            team1_user = uid
                        elif rid == team2.get('roster_id'):
                            team2_user = uid
                    
                    if team1_user and team2_user:
                        # Record head-to-head results
                        if team1_points > team2_points:
                            team_records[team1_user]['regular_record']['wins'] += 1
                            team_records[team2_user]['regular_record']['losses'] += 1
                        elif team2_points > team1_points:
                            team_records[team2_user]['regular_record']['wins'] += 1
                            team_records[team1_user]['regular_record']['losses'] += 1
                        else:
                            team_records[team1_user]['regular_record']['ties'] += 1
                            team_records[team2_user]['regular_record']['ties'] += 1
            
            # Calculate median-based wins/losses
            teams_above_median = []
            teams_below_median = []
            
            for user_id, score in week_data.items():
                if score > median_score:
                    team_records[user_id]['median_record']['wins'] += 1
                    team_records[user_id]['weekly_median_results'][week] = 'W'
                    teams_above_median.append((team_records[user_id]['name'], score))
                elif score < median_score:
                    team_records[user_id]['median_record']['losses'] += 1
                    team_records[user_id]['weekly_median_results'][week] = 'L'
                    teams_below_median.append((team_records[user_id]['name'], score))
                else:
                    # Exactly at median - could be handled as tie or win, using win here
                    team_records[user_id]['median_record']['wins'] += 1
                    team_records[user_id]['weekly_median_results'][week] = 'W'
                    teams_above_median.append((team_records[user_id]['name'], score))
            
            print(f"     Above Median ({len(teams_above_median)}): {', '.join([f'{name} ({score:.1f})' for name, score in sorted(teams_above_median, key=lambda x: x[1], reverse=True)])}")
            print(f"     Below Median ({len(teams_below_median)}): {', '.join([f'{name} ({score:.1f})' for name, score in sorted(teams_below_median, key=lambda x: x[1], reverse=True)])}")
    
    # Calculate combined records
    for user_id, data in team_records.items():
        regular_wins = data['regular_record']['wins']
        regular_losses = data['regular_record']['losses']
        median_wins = data['median_record']['wins']
        median_losses = data['median_record']['losses']
        
        # Combined record = regular record + median record
        data['combined_record']['wins'] = regular_wins + median_wins
        data['combined_record']['losses'] = regular_losses + median_losses
    
    return team_records


def print_record_summary(team_records: Dict):
    """Print a summary of all team records"""
    print("\nRECORD SUMMARY")
    print("="*80)
    print(f"{'Team':<20} {'Regular':<10} {'vs Median':<10} {'Combined':<10} {'Combined %':<12}")
    print("="*80)
    
    # Sort teams by combined win percentage
    sorted_teams = []
    for user_id, data in team_records.items():
        combined_wins = data['combined_record']['wins']
        combined_total = data['combined_record']['wins'] + data['combined_record']['losses']
        win_pct = combined_wins / combined_total if combined_total > 0 else 0
        sorted_teams.append((data['name'], data, win_pct))
    
    sorted_teams.sort(key=lambda x: x[2], reverse=True)
    
    for name, data, win_pct in sorted_teams:
        regular = f"{data['regular_record']['wins']}-{data['regular_record']['losses']}"
        if data['regular_record']['ties'] > 0:
            regular += f"-{data['regular_record']['ties']}"
        
        median = f"{data['median_record']['wins']}-{data['median_record']['losses']}"
        combined = f"{data['combined_record']['wins']}-{data['combined_record']['losses']}"
        
        print(f"{name:<20} {regular:<10} {median:<10} {combined:<10} {win_pct:.1%}")


def analyze_median_performance(team_records: Dict):
    """Analyze which teams perform best vs median"""
    print("\nMEDIAN PERFORMANCE ANALYSIS")
    print("="*60)
    
    median_performers = []
    for user_id, data in team_records.items():
        median_wins = data['median_record']['wins']
        median_total = data['median_record']['wins'] + data['median_record']['losses']
        median_pct = median_wins / median_total if median_total > 0 else 0
        
        regular_wins = data['regular_record']['wins']
        regular_total = data['regular_record']['wins'] + data['regular_record']['losses']
        regular_pct = regular_wins / regular_total if regular_total > 0 else 0
        
        median_performers.append({
            'name': data['name'],
            'median_pct': median_pct,
            'regular_pct': regular_pct,
            'difference': median_pct - regular_pct,
            'median_record': f"{median_wins}-{data['median_record']['losses']}",
            'regular_record': f"{regular_wins}-{data['regular_record']['losses']}"
        })
    
    # Sort by median performance
    median_performers.sort(key=lambda x: x['median_pct'], reverse=True)
    
    print("🔥 Best vs Median:")
    for i, team in enumerate(median_performers[:3], 1):
        print(f"  {i}. {team['name']}: {team['median_record']} ({team['median_pct']:.1%})")
    
    print("\n❄️  Worst vs Median:")
    for i, team in enumerate(median_performers[-3:], 1):
        print(f"  {i}. {team['name']}: {team['median_record']} ({team['median_pct']:.1%})")
    
    print("\nBiggest Outperformers vs Regular Record:")
    outperformers = sorted(median_performers, key=lambda x: x['difference'], reverse=True)
    for i, team in enumerate(outperformers[:3], 1):
        diff = team['difference']
        print(f"  {i}. {team['name']}: {diff:+.1%} (Median: {team['median_pct']:.1%}, Regular: {team['regular_pct']:.1%})")
    
    print("\n📉 Biggest Underperformers vs Regular Record:")
    for i, team in enumerate(outperformers[-3:], 1):
        diff = team['difference']
        print(f"  {i}. {team['name']}: {diff:+.1%} (Median: {team['median_pct']:.1%}, Regular: {team['regular_pct']:.1%})")


def main():
    """Main function to demonstrate median record calculation"""
    try:
        # Load configuration
        import json
        import os
        
        config_file = 'league_config.json'
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            league_id = config['league_id']
            season = config.get('season', 2025)
            print(f"Using league: {config['league_name']} (ID: {league_id})")
        else:
            print("❌ No league configuration found. Please run main.py first.")
            return
        
        # Initialize API
        sleeper_api = SleeperAPI()
        
        # Get league data
        print("\nFetching league data...")
        rosters = sleeper_api.get_league_rosters(league_id)
        users = sleeper_api.get_league_users(league_id)
        
        if not rosters or not users:
            print("❌ Failed to get league data")
            return
        
        # Create user lookup
        user_lookup = {user['user_id']: user for user in users}
        
        # Get weekly matchups
        print("Fetching weekly matchups...")
        all_weekly_matchups = {}
        max_week = 15
        
        for week in range(1, max_week + 1):
            matchups = sleeper_api.get_league_matchups(league_id, week)
            if matchups:
                all_weekly_matchups[week] = matchups
        
        # Calculate median records
        team_records = calculate_median_records(all_weekly_matchups, rosters, user_lookup)
        
        # Display results
        print_record_summary(team_records)
        analyze_median_performance(team_records)
        
        # Save results to JSON for use by other scripts
        import json
        from datetime import datetime
        
        output_file = "median_records.json"
        with open(output_file, 'w') as f:
            # Convert for JSON serialization
            json_data = {}
            for user_id, data in team_records.items():
                json_data[user_id] = {
                    'name': data['name'],
                    'regular_record': data['regular_record'],
                    'median_record': data['median_record'],
                    'combined_record': data['combined_record'],
                    'weekly_scores': data['weekly_scores'],
                    'weekly_median_results': data['weekly_median_results']
                }
            
            json.dump(json_data, f, indent=2)
        
        print(f"\nResults saved to: {output_file}")
        print("Median record calculation complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()