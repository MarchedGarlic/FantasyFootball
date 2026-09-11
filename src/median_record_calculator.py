#!/usr/bin/env python3
"""
Median Record Calculator
Calculates weekly median scores and determines wins/losses vs median,
then combines with regular record for comprehensive team evaluation.
"""

import statistics
from typing import Dict, List

from src.utils import get_manager_name, week_has_been_played


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
                'name': get_manager_name(user_lookup, user_id, prefix="User"),
                'regular_record': {'wins': 0, 'losses': 0, 'ties': 0},
                'median_record': {'wins': 0, 'losses': 0},
                'combined_record': {'wins': 0, 'losses': 0},
                'weekly_scores': {},
                'weekly_median_results': {}
            }

    # Reverse lookup built once, instead of linearly scanning user_to_roster for every
    # matchup/pairing below (previously O(teams) per matchup, every week).
    roster_to_user = {rid: uid for uid, rid in user_to_roster.items()}

    # Process each week
    for week, matchups in all_weekly_matchups.items():
        # A future/unplayed week isn't an empty list - Sleeper pre-fills every rostered player
        # with 0.0 points before kickoff - so it must be detected by score, not list length (see
        # week_has_been_played()). Without this, every team's score ties the week's "median" of
        # 0.0 for every unplayed week, which the exactly-at-median branch below scores as a free
        # win, and the identical head-to-head score is recorded as a free regular-season tie -
        # both compounding for every remaining week of the season before it's even played.
        if not matchups or not week_has_been_played(matchups):
            continue

        print(f"   Processing Week {week}...")
        
        # Collect all scores for this week
        week_scores = []
        week_data = {}  # user_id -> score
        
        for matchup in matchups:
            roster_id = matchup.get('roster_id')
            points = matchup.get('points', 0) or 0
            
            # Find user_id for this roster_id
            user_id = roster_to_user.get(roster_id)

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
                    team1_user = roster_to_user.get(team1.get('roster_id'))
                    team2_user = roster_to_user.get(team2.get('roster_id'))

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
            
            # Only apply a median result to teams that also had a real head-to-head matchup
            # this week - a team without a real paired opponent (a bye or an odd consolation
            # grouping during playoffs) shouldn't get a "free" median decision that week, or
            # its median-game count would drift ahead of its real-game count (the whole point
            # of this comparison is that both records cover the same games).
            teams_with_real_matchup = {
                roster_to_user.get(m.get('roster_id'))
                for teams in matchup_groups.values() if len(teams) == 2
                for m in teams
            }
            teams_with_real_matchup.discard(None)

            # Calculate median-based wins/losses
            teams_above_median = []
            teams_below_median = []

            for user_id, score in week_data.items():
                if user_id not in teams_with_real_matchup:
                    continue
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


