#!/usr/bin/env python3
"""
Comprehensive Analysis Module
Analyzes trades, waivers, and manager performance using multiple metrics
"""

import statistics
import numpy as np
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional


def get_player_name_from_id(player_id, all_players=None):
    """Convert player ID to actual name using Sleeper player database"""
    if not player_id:
        return "Unknown Player"
    
    if all_players and str(player_id) in all_players:
        player_data = all_players[str(player_id)]
        first_name = player_data.get('first_name', '')
        last_name = player_data.get('last_name', '')
        full_name = f"{first_name} {last_name}".strip()
        if full_name:
            return full_name
    
    # Fallback to ID if name not found
    return f"Player_{player_id}"


def analyze_real_trades_only(transactions_data, team_power_data, roster_grade_data, user_lookup, roster_to_manager, all_players=None, output_dirs=None):
    """Analyze only actual trades (not waivers) with detailed player movement tracking"""
    print("🔄 Analyzing Real Trade Impacts Only...")
    
    trade_impacts = []
    
    for week_key, week_transactions in transactions_data.items():
        # Check if week_transactions is None or empty
        if not week_transactions or week_transactions is None:
            continue
            
        week_num = int(week_key.split()[1])
        
        for transaction in week_transactions:
            # Skip if transaction is None or invalid
            if not transaction or not isinstance(transaction, dict):
                continue
                
            # Only analyze actual trades, skip waivers/free agents
            if transaction.get('type') != 'trade':
                continue
                
            print(f"\n   📋 Analyzing Trade in Week {week_num}:")
            
            adds = transaction.get('adds', {}) or {}
            drops = transaction.get('drops', {}) or {}
            roster_ids = transaction.get('roster_ids', []) or []
            
            if len(roster_ids) != 2:
                print(f"     ⚠️  Skipping complex trade with {len(roster_ids)} teams")
                continue
                
            # Get the two managers involved
            manager_data = {}
            for roster_id in roster_ids:
                if roster_id in roster_to_manager:
                    manager_id = roster_to_manager[roster_id]
                    if manager_id in user_lookup:
                        manager_name = user_lookup[manager_id].get('display_name', f'Manager {manager_id}')
                        
                        # Find what this manager got and gave up
                        acquired = []
                        gave_up = []
                        
                        for player_id, receiving_roster in adds.items():
                            if receiving_roster == roster_id:
                                acquired.append(get_player_name_from_id(player_id, all_players))
                        
                        for player_id, giving_roster in drops.items():
                            if giving_roster == roster_id:
                                gave_up.append(get_player_name_from_id(player_id, all_players))
                        
                        manager_data[manager_id] = {
                            'name': manager_name,
                            'roster_id': roster_id,
                            'acquired': acquired,
                            'gave_up': gave_up
                        }
            
            if len(manager_data) != 2:
                print(f"     ⚠️  Could not identify both trading partners")
                continue
                
            # Calculate impact for each manager using improved methodology
            for manager_id, trade_info in manager_data.items():
                # Use improved calculation method
                impact_results = calculate_improved_trade_impact(
                    manager_id, week_num, team_power_data, roster_grade_data
                )
                
                other_manager = next(m for m in manager_data.values() if m['name'] != trade_info['name'])
                
                trade_impacts.append({
                    'week': week_num,
                    'manager_id': manager_id,
                    'manager_name': trade_info['name'],
                    'other_manager': other_manager['name'],
                    'acquired_players': trade_info['acquired'],
                    'gave_up_players': trade_info['gave_up'],
                    'other_acquired': other_manager['acquired'],
                    'other_gave_up': other_manager['gave_up'],
                    'power_impact': impact_results['power_impact'],
                    'grade_impact': impact_results['grade_impact'],
                    'record_impact': impact_results['record_impact'],
                    'combined_impact': impact_results['combined_impact'],
                    'normalized_power': impact_results['normalized_power'],
                    'normalized_grade': impact_results['normalized_grade'],
                    'normalized_record': impact_results['normalized_record']
                })
                
                print(f"     📈 {trade_info['name']}: Power {impact_results['power_impact']:+.1f}, Grade {impact_results['grade_impact']:+.1f}, Record {impact_results['record_impact']:+.1f}, Combined {impact_results['combined_impact']:+.1f}")
    
    return trade_impacts


def analyze_waiver_pickups(transactions_data, team_power_data, roster_grade_data, user_lookup, roster_to_manager, all_players=None, output_dirs=None):
    """Analyze waiver wire and free agent pickups with impact scoring"""
    print("\n📊 Analyzing Waiver Wire & Free Agent Impacts...")
    
    waiver_impacts = []
    
    for week_key, week_transactions in transactions_data.items():
        # Check if week_transactions is None or empty
        if not week_transactions or week_transactions is None:
            print(f"   ⚠️  Skipping week {week_key}: No transactions")
            continue
        
        # Handle different possible data structures
        if isinstance(week_key, str) and 'Week' in week_key:
            week_num = int(week_key.split()[1])
        elif isinstance(week_key, (int, float)):
            week_num = int(week_key)
        else:
            print(f"   ⚠️  Skipping invalid week key: {week_key}")
            continue
        
        # Ensure week_transactions is iterable
        if not hasattr(week_transactions, '__iter__'):
            print(f"   ⚠️  Skipping week {week_num}: transactions not iterable")
            continue
            
        for transaction in week_transactions:
            # Skip if transaction is None or invalid
            if not transaction or not isinstance(transaction, dict):
                continue
                
            # Only analyze waivers and free agent moves (skip trades)
            transaction_type = transaction.get('type', 'unknown')
            if transaction_type == 'trade':
                continue
                
            adds = transaction.get('adds', {}) or {}
            drops = transaction.get('drops', {}) or {}
            
            # Skip if no adds
            if not adds:
                continue
            
            for player_added, roster_id in adds.items():
                if roster_id in roster_to_manager:
                    manager_id = roster_to_manager[roster_id]
                    if manager_id in user_lookup:
                        manager_name = user_lookup[manager_id].get('display_name', f'Manager {manager_id}')
                        
                        # Find what player was dropped (if any)
                        player_dropped = None
                        for player_id, dropping_roster in drops.items():
                            if dropping_roster == roster_id:
                                player_dropped = get_player_name_from_id(player_id, all_players)
                                break
                        
                        if not player_dropped:
                            player_dropped = "None (roster space)"
                        
                        # Calculate impacts
                        power_impact = calculate_manager_power_impact(manager_id, week_num, team_power_data)
                        grade_impact = calculate_manager_grade_impact(manager_id, week_num, roster_grade_data)
                        
                        waiver_impacts.append({
                            'week': week_num,
                            'manager_id': manager_id,
                            'manager_name': manager_name,
                            'player_added': get_player_name_from_id(player_added, all_players),
                            'player_dropped': player_dropped,
                            'power_impact': power_impact,
                            'grade_impact': grade_impact,
                            'combined_impact': power_impact + grade_impact,
                            'transaction_type': transaction_type
                        })
    
    print(f"     📊 Analyzed {len(waiver_impacts)} waiver/FA transactions")
    return waiver_impacts


def calculate_manager_power_impact(manager_id, week_num, team_power_data, window_size=3):
    """Calculate power rating impact for a manager around a specific week (legacy function for waivers)"""
    if manager_id not in team_power_data:
        return 0.0
    
    power_data = team_power_data[manager_id]['weekly_power_ratings']
    
    # Get before and after windows
    before_weeks = [w for w in power_data.keys() if w < week_num]
    after_weeks = [w for w in power_data.keys() if w > week_num]
    
    if len(before_weeks) < 2 or len(after_weeks) < 2:
        return 0.0
    
    # Calculate averages
    recent_before = sorted(before_weeks)[-min(window_size, len(before_weeks)):]
    recent_after = sorted(after_weeks)[:min(window_size, len(after_weeks))]
    
    before_avg = statistics.mean([power_data[w] for w in recent_before])
    after_avg = statistics.mean([power_data[w] for w in recent_after])
    
    return after_avg - before_avg


def calculate_improved_trade_impact(manager_id, trade_week, team_power_data, roster_grade_data, matchup_data=None):
    """
    Calculate trade impact using improved methodology:
    - Power rating: Week before trade vs Week of trade
    - Roster grade: Week before trade vs Week of trade  
    - Record impact: Simulated based on performance
    - All weighted equally (33.33% each)
    """
    power_impact = 0.0
    grade_impact = 0.0
    record_impact = 0.0
    
    # 1. Power Rating Impact (Week before vs Week of trade)
    if manager_id in team_power_data:
        power_data = team_power_data[manager_id]['weekly_power_ratings']
        
        week_before = trade_week - 1
        week_of_trade = trade_week
        
        if week_before in power_data and week_of_trade in power_data:
            power_before = power_data[week_before]
            power_after = power_data[week_of_trade]
            power_impact = power_after - power_before
    
    # 2. Roster Grade Impact (Week before vs Week of trade)
    if manager_id in roster_grade_data:
        grade_data = roster_grade_data[manager_id]['weekly_roster_grades']
        
        week_before = trade_week - 1
        week_of_trade = trade_week
        
        if week_before in grade_data and week_of_trade in grade_data:
            grade_before = grade_data[week_before]
            grade_after = grade_data[week_of_trade]
            grade_impact = grade_after - grade_before
    
    # 3. Record Impact (Simulated based on performance improvement)
    # Convert power/grade improvements to estimated record impact
    combined_performance_change = (power_impact + grade_impact) / 2
    
    # Estimate record impact: significant improvements (~10+ points) = ~0.5 win equivalent
    # Moderate improvements (5-10 points) = ~0.25 win equivalent
    # Small changes (<5 points) = minimal record impact
    if abs(combined_performance_change) >= 10:
        record_impact = 0.5 if combined_performance_change > 0 else -0.5
    elif abs(combined_performance_change) >= 5:
        record_impact = 0.25 if combined_performance_change > 0 else -0.25
    else:
        record_impact = combined_performance_change * 0.05  # Small linear scaling
    
    # Scale to make impacts comparable (normalize to similar ranges)
    normalized_power = power_impact * 0.5   # Power ratings typically 100-200, scale down
    normalized_grade = grade_impact * 2.0   # Roster grades typically 20-35, scale up  
    normalized_record = record_impact * 20  # Record impact 0-1, scale up significantly
    
    # Equal weighting: 33.33% each
    total_impact = (normalized_power + normalized_grade + normalized_record) / 3
    
    return {
        'power_impact': power_impact,
        'grade_impact': grade_impact,
        'record_impact': record_impact,
        'normalized_power': normalized_power,
        'normalized_grade': normalized_grade,
        'normalized_record': normalized_record,
        'combined_impact': total_impact
    }


def calculate_manager_grade_impact(manager_id, week_num, roster_grade_data, window_size=2):
    """Calculate roster grade impact for a manager around a specific week"""
    if manager_id not in roster_grade_data:
        return 0.0
    
    grade_data = roster_grade_data[manager_id]['weekly_roster_grades']
    
    # Get before and after windows
    before_weeks = [w for w in grade_data.keys() if w < week_num]
    after_weeks = [w for w in grade_data.keys() if w > week_num]
    
    if len(before_weeks) < 1 or len(after_weeks) < 1:
        return 0.0
    
    # Calculate averages
    recent_before = sorted(before_weeks)[-min(window_size, len(before_weeks)):]
    recent_after = sorted(after_weeks)[:min(window_size, len(after_weeks))]
    
    before_avg = statistics.mean([grade_data[w] for w in recent_before])
    after_avg = statistics.mean([grade_data[w] for w in recent_after])
    
    return after_avg - before_avg


def calculate_manager_grades(trade_impacts, waiver_impacts, team_power_data, roster_grade_data, user_lookup, matchup_data=None):
    """Calculate comprehensive manager grades based on trades, waivers, and lineup decisions"""
    print("\n🏆 Calculating Manager Performance Grades...")
    
    manager_grades = {}
    
    # Validate input data
    if not user_lookup:
        print("   ⚠️  No user data available for manager grades")
        return manager_grades
    

    
    # Initialize manager data - only for managers with actual game data
    for manager_id, user_data in user_lookup.items():
        if not user_data or not isinstance(user_data, dict):
            continue
            
        # Only include managers who have power or roster data
        has_power_data = manager_id in team_power_data and team_power_data[manager_id].get('weekly_power_ratings')
        has_roster_data = manager_id in roster_grade_data and roster_grade_data[manager_id].get('weekly_roster_grades')
        
        if not has_power_data and not has_roster_data:

            continue  # Skip managers without any performance data
        
        manager_name = user_data.get('display_name', f'Manager {manager_id}')
        manager_grades[manager_id] = {
            'name': manager_name,
            'weekly_grades': {},
            'trade_performance': 0.0,
            'waiver_performance': 0.0,
            'lineup_performance': 0.0,
            'overall_grade': 0.0,
            'record': {'wins': 0, 'losses': 0},
            'combined_record': {'wins': 0, 'losses': 0}
        }

    
    # Calculate trade performance scores (weight: 25%)
    trade_scores = {}
    for impact in trade_impacts:
        manager_id = impact['manager_id']
        if manager_id in manager_grades:
            # Good trades = positive combined impact, scale to 0-10
            trade_score = max(0, min(10, 5 + impact['combined_impact'] / 4))
            if manager_id not in trade_scores:
                trade_scores[manager_id] = []
            trade_scores[manager_id].append(trade_score)
    
    # Calculate waiver performance scores (weight: 20%)
    waiver_scores = {}
    for impact in waiver_impacts:
        manager_id = impact['manager_id']
        if manager_id in manager_grades:
            # Good pickups = positive combined impact, scale to 0-10
            waiver_score = max(0, min(10, 5 + impact['combined_impact'] / 3))
            if manager_id not in waiver_scores:
                waiver_scores[manager_id] = []
            waiver_scores[manager_id].append(waiver_score)
    
    # Calculate lineup performance (start/sit accuracy) - weight: 15%
    # For now, simulate based on power rating performance vs league average
    lineup_scores = {}
    if team_power_data:
        all_power_ratings = []
        for manager_data in team_power_data.values():
            all_power_ratings.extend(manager_data.get('weekly_power_ratings', {}).values())
        
        if all_power_ratings:
            league_avg_power = sum(all_power_ratings) / len(all_power_ratings)
            
            for manager_id in manager_grades.keys():
                if manager_id in team_power_data:
                    manager_power_data = team_power_data[manager_id]['weekly_power_ratings']
                    lineup_scores[manager_id] = []
                    
                    for week, power_rating in manager_power_data.items():
                        # Lineup skill based on how well power translates to actual performance
                        # Higher than average = good lineup decisions
                        relative_performance = (power_rating - league_avg_power) / 20  # Normalize
                        lineup_score = max(0, min(10, 5 + relative_performance))
                        lineup_scores[manager_id].append(lineup_score)
    
    # Calculate weekly manager grades and records using real data
    for week in range(1, 15):  # Weeks 1-14
        # First pass: collect all scores for median calculation
        week_scores = []
        for manager_id in manager_grades.keys():
            power_weekly = team_power_data.get(manager_id, {}).get('weekly_power_ratings', {})
            power_data = power_weekly.get(week, power_weekly.get(str(week), None))
            if power_data is not None:
                week_scores.append(power_data)
        
        # Calculate median for combined record
        median_score = sorted(week_scores)[len(week_scores)//2] if week_scores else 100
        
        for manager_id in manager_grades.keys():
            # Get real performance data
            power_weekly = team_power_data.get(manager_id, {}).get('weekly_power_ratings', {})
            grade_weekly = roster_grade_data.get(manager_id, {}).get('weekly_roster_grades', {})
            
            power_data = power_weekly.get(week, power_weekly.get(str(week), None))
            grade_data = grade_weekly.get(week, grade_weekly.get(str(week), None))
            
            # Skip weeks where we have no meaningful data
            if power_data is None and grade_data is None:
                continue
            
            # Use defaults for missing data, but don't skip if we have at least one value
            power_data = power_data if power_data is not None else 100
            grade_data = grade_data if grade_data is not None else 25
            
            # Normalize to 0-10 scale using realistic ranges
            power_score = max(0, min(10, (power_data - 80) / 20)) if power_data else 5
            roster_score = max(0, min(10, (grade_data - 20) / 5)) if grade_data else 5
            base_score = (power_score + roster_score) / 2
            
            # Trade performance for this week
            week_trade_score = 5.0  # Default neutral
            if manager_id in trade_scores and trade_scores[manager_id]:
                week_trade_score = sum(trade_scores[manager_id]) / len(trade_scores[manager_id])
            
            # Waiver performance for this week
            week_waiver_score = 5.0  # Default neutral
            if manager_id in waiver_scores and waiver_scores[manager_id]:
                week_waiver_score = sum(waiver_scores[manager_id]) / len(waiver_scores[manager_id])
            
            # Lineup performance for this week
            week_lineup_score = 5.0  # Default neutral
            if manager_id in lineup_scores and week <= len(lineup_scores[manager_id]):
                week_lineup_score = lineup_scores[manager_id][week-1]
            
            # Calculate composite manager grade (0-10 scale)
            weekly_grade = (
                base_score * 0.4 +           # 40% base performance (power + roster)
                week_trade_score * 0.25 +    # 25% trade performance
                week_waiver_score * 0.20 +   # 20% waiver performance  
                week_lineup_score * 0.15     # 15% lineup performance
            )
            
            manager_grades[manager_id]['weekly_grades'][week] = max(0, min(10, weekly_grade))
            
            # Use real win/loss records from power data if available
            power_team_data = team_power_data.get(manager_id, {})
            if 'cumulative_wins' in power_team_data and 'cumulative_losses' in power_team_data:
                week_wins = power_team_data['cumulative_wins'].get(week, 0)
                week_losses = power_team_data['cumulative_losses'].get(week, 0)
                
                # Update real record
                manager_grades[manager_id]['record']['wins'] = week_wins
                manager_grades[manager_id]['record']['losses'] = week_losses
                
                # Use combined record if available
                combined_record = power_team_data.get('combined_record', {})
                if combined_record:
                    manager_grades[manager_id]['combined_record']['wins'] = combined_record.get('wins', week_wins)
                    manager_grades[manager_id]['combined_record']['losses'] = combined_record.get('losses', week_losses)
                else:
                    # Calculate combined record: real wins + theoretical wins vs median
                    theoretical_wins = 1 if power_data > median_score else 0
                    combined_wins = week_wins + (theoretical_wins * week)  # Add theoretical wins for each week
                    combined_losses = (week * 2) - combined_wins  # Total possible games minus wins
                    
                    manager_grades[manager_id]['combined_record']['wins'] = combined_wins
                    manager_grades[manager_id]['combined_record']['losses'] = combined_losses
            else:
                # Fallback to performance-based simulation
                if weekly_grade > 5.5:
                    manager_grades[manager_id]['record']['wins'] += 1
                    manager_grades[manager_id]['combined_record']['wins'] += 1
                else:
                    manager_grades[manager_id]['record']['losses'] += 1
                    manager_grades[manager_id]['combined_record']['losses'] += 1
    
    # Calculate overall grades
    for manager_id, data in manager_grades.items():
        if data['weekly_grades']:
            data['overall_grade'] = sum(data['weekly_grades'].values()) / len(data['weekly_grades'])
            
            # Calculate performance summaries
            if manager_id in trade_scores and trade_scores[manager_id]:
                data['trade_performance'] = sum(trade_scores[manager_id]) / len(trade_scores[manager_id])
            if manager_id in waiver_scores and waiver_scores[manager_id]:
                data['waiver_performance'] = sum(waiver_scores[manager_id]) / len(waiver_scores[manager_id])
            if manager_id in lineup_scores and lineup_scores[manager_id]:
                data['lineup_performance'] = sum(lineup_scores[manager_id]) / len(lineup_scores[manager_id])
        
        manager_name = data.get('name', manager_id)  # Get name or use ID as fallback
        print(f"     📋 {manager_name}: Overall Grade {data['overall_grade']:.1f}/10 " +
              f"(Record: {data['record']['wins']}-{data['record']['losses']})")
    
    return manager_grades


def create_trade_visualization(trade_impacts, transactions_data=None, output_dirs=None):
    """Create enhanced trade visualization with clean data, leaderboard, and detailed explanations"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import (ColumnDataSource, HoverTool, Legend, LegendItem, 
                                Button, CustomJS, Div)
        from bokeh.layouts import column as bokeh_column, row as bokeh_row
        from bokeh.palettes import Category20
        from sklearn.linear_model import LinearRegression
        import numpy as np
    except ImportError:
        print("\n⚠️  Bokeh and/or sklearn not available for trade visualization")
        return
    
    if not trade_impacts:
        print("\n⚠️  No trade data for visualization")
        return
    
    if output_dirs:
        plot_filename = os.path.join(output_dirs['html'], f"trade_analysis_{output_dirs['timestamp']}.html")
    else:
        plot_filename = f"trade_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    output_file(plot_filename)
    
    # Create individual trade transactions with unique identifiers
    individual_trades = []
    trade_id = 1
    
    for impact in trade_impacts:
        # Create unique identifier for each trade transaction
        individual_trades.append({
            'trade_id': trade_id,
            'manager_name': impact['manager_name'],
            'week': impact['week'],
            'power_impact': impact['power_impact'],
            'grade_impact': impact['grade_impact'],
            'combined_impact': impact['combined_impact'],
            'acquired_players': impact['acquired_players'],
            'gave_up_players': impact['gave_up_players'],
            'other_manager': impact['other_manager']
        })
        trade_id += 1
    
    # Prepare data by manager with jitter to separate overlapping trades
    manager_data = {}
    all_managers = set()
    
    for trade in individual_trades:
        manager = trade['manager_name']
        all_managers.add(manager)
        
        if manager not in manager_data:
            manager_data[manager] = {
                'weeks': [],
                'power_impacts': [],
                'grade_impacts': [],
                'combined_impacts': [],
                'acquired_players': [],
                'gave_up_players': [],
                'other_managers': [],
                'trade_ids': []
            }
        
        # Add small jitter to prevent exact overlap
        week_jitter = trade['week'] + np.random.uniform(-0.15, 0.15)
        
        manager_data[manager]['weeks'].append(week_jitter)
        manager_data[manager]['power_impacts'].append(trade['power_impact'])
        manager_data[manager]['grade_impacts'].append(trade['grade_impact'])
        manager_data[manager]['combined_impacts'].append(trade['combined_impact'])
        
        # Clean player name formatting
        acquired = ', '.join([p.strip() for p in trade['acquired_players']]) if trade['acquired_players'] else 'None'
        gave_up = ', '.join([p.strip() for p in trade['gave_up_players']]) if trade['gave_up_players'] else 'None'
        
        manager_data[manager]['acquired_players'].append(acquired)
        manager_data[manager]['gave_up_players'].append(gave_up)
        manager_data[manager]['other_managers'].append(trade['other_manager'])
        manager_data[manager]['trade_ids'].append(trade['trade_id'])
    
    # Color mapping with legend
    unique_managers = sorted(all_managers)
    colors_palette = Category20[max(3, min(20, len(unique_managers)))]
    color_map = {manager: colors_palette[i % len(colors_palette)] for i, manager in enumerate(unique_managers)}
    
    # Create leaderboard of worst trades
    worst_trades = []
    for trade in individual_trades:
        worst_trades.append({
            'manager': trade['manager_name'],
            'week': trade['week'],
            'combined_impact': trade['combined_impact'],
            'acquired': ', '.join([p.strip() for p in trade['acquired_players']]) if trade['acquired_players'] else 'None',
            'gave_up': ', '.join([p.strip() for p in trade['gave_up_players']]) if trade['gave_up_players'] else 'None',
            'other_manager': trade['other_manager'],
            'power_impact': trade['power_impact'],
            'grade_impact': trade['grade_impact']
        })
    
    # Sort by worst impact and save to text file
    worst_trades.sort(key=lambda x: x['combined_impact'])
    
    if output_dirs:
        worst_trades_filename = os.path.join(output_dirs['text'], f"worst_trades_report_{output_dirs['timestamp']}.txt")
    else:
        worst_trades_filename = f"worst_trades_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    with open(worst_trades_filename, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("WORST TRADES ANALYSIS REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("METHODOLOGY:\n")
        f.write("- Combined Impact = Power Rating Impact + Roster Grade Impact\n")
        f.write("- Negative values indicate trades that weakened the team\n")
        f.write("- Rankings based on most negative combined impact\n\n")
        
        f.write("TOP 10 WORST TRADES:\n")
        f.write("-" * 80 + "\n")
        f.write(f"{'Rank':<4} {'Manager':<15} {'Week':<4} {'Impact':<8} {'Acquired':<20} {'Gave Up':<20}\n")
        f.write("-" * 80 + "\n")
        
        for i, trade in enumerate(worst_trades[:10]):
            f.write(f"{i+1:<4} {trade['manager'][:14]:<15} {trade['week']:<4} {trade['combined_impact']:+7.1f} "
                   f"{trade['acquired'][:19]:<20} {trade['gave_up'][:19]:<20}\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("DETAILED BREAKDOWN OF WORST 10 TRADES:\n")
        f.write("=" * 80 + "\n")
        
        for i, trade in enumerate(worst_trades[:10]):
            f.write(f"\n{i+1}. {trade['manager']} (Week {trade['week']})\n")
            f.write(f"   Combined Impact: {trade['combined_impact']:+.1f}\n")
            f.write(f"   Power Impact: {trade['power_impact']:+.1f}\n")
            f.write(f"   Grade Impact: {trade['grade_impact']:+.1f}\n")
            f.write(f"   Acquired: {trade['acquired']}\n")
            f.write(f"   Gave Up: {trade['gave_up']}\n")
            f.write(f"   Trading Partner: {trade['other_manager']}\n")
    
    print(f"\n📝 Worst trades report saved as: {worst_trades_filename}")
    
    # Calculate leaderboard statistics
    manager_stats = {}
    for trade in individual_trades:
        manager = trade['manager_name']
        if manager not in manager_stats:
            manager_stats[manager] = {
                'total_trades': 0,
                'total_impact': 0,
                'impacts': [],
                'positive_trades': 0,
                'negative_trades': 0
            }
        
        manager_stats[manager]['total_trades'] += 1
        manager_stats[manager]['total_impact'] += trade['combined_impact']
        manager_stats[manager]['impacts'].append(trade['combined_impact'])
        
        if trade['combined_impact'] > 0:
            manager_stats[manager]['positive_trades'] += 1
        elif trade['combined_impact'] < 0:
            manager_stats[manager]['negative_trades'] += 1
    
    # Calculate averages and create leaderboard
    leaderboard_data = []
    for manager, stats in manager_stats.items():
        avg_impact = stats['total_impact'] / stats['total_trades'] if stats['total_trades'] > 0 else 0
        win_rate = (stats['positive_trades'] / stats['total_trades'] * 100) if stats['total_trades'] > 0 else 0
        
        leaderboard_data.append([
            manager,
            f"{avg_impact:+.2f}",
            f"{stats['total_impact']:+.1f}",
            str(stats['total_trades']),
            f"{win_rate:.1f}%",
            "📈" if avg_impact > 2 else "📉" if avg_impact < -2 else "➡️"
        ])
    
    # Sort by average impact
    leaderboard_data.sort(key=lambda x: float(x[1]), reverse=True)
    for i, row in enumerate(leaderboard_data):
        row.insert(0, str(i + 1))  # Add ranking
    
    # Create main plot
    p = figure(
        width=1200,
        height=700,
        title="Trade Impact Analysis: Individual Transaction Performance",
        x_axis_label="Week",
        y_axis_label="Combined Impact Score",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        x_range=(0.5, 15.5),
        y_range=(-30, 45)
    )
    
    # Add zero reference line
    p.line([0.5, 15.5], [0, 0], line_color='black', line_width=1, line_dash='dashed', alpha=0.5)
    
    # Create collapsible explanation panel
    explanation_text = """
    <h3 style="margin:10px 0 5px 0;">📊 Trade Impact Analysis Methodology</h3>
    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 5px 0;">
        <h4 style="margin: 0 0 10px 0; color: #2c3e50;">🔍 Data Collection & Processing</h4>
        <p style="margin: 3px 0;"><strong>Trade Detection:</strong> Real fantasy football trades identified from league transaction data</p>
        <p style="margin: 3px 0;"><strong>Individual Transactions:</strong> Each trade shown as separate data point (no aggregation)</p>
        <p style="margin: 3px 0;"><strong>Multi-Manager Trades:</strong> Complex trades broken down by individual manager perspective</p>
        <p style="margin: 3px 0;"><strong>Time Analysis:</strong> Before/after trade performance comparison with 2-week windows</p>
        
        <h4 style="margin: 15px 0 10px 0; color: #2c3e50;">📈 Impact Calculation Formula</h4>
        <p style="margin: 3px 0;"><strong>Power Rating Impact:</strong> Change in weekly power score (performance + wins)</p>
        <p style="margin: 3px 0;"><strong>Roster Grade Impact:</strong> Change in roster talent evaluation based on ESPN rankings</p>
        <p style="margin: 3px 0;"><strong>Combined Score:</strong> Power Impact + Roster Impact (equal 50/50 weighting)</p>
        <p style="margin: 3px 0;"><strong>Baseline Comparison:</strong> 2 weeks before trade vs 2 weeks after trade execution</p>
        
        <h4 style="margin: 15px 0 10px 0; color: #2c3e50;">🎯 Impact Scale & Interpretation</h4>
        <p style="margin: 3px 0;"><strong>Excellent Trade (+15+):</strong> Significantly improved team strength and performance</p>
        <p style="margin: 3px 0;"><strong>Good Trade (+5 to +15):</strong> Solid improvement with positive team impact</p>
        <p style="margin: 3px 0;"><strong>Neutral Trade (-5 to +5):</strong> Minimal impact, roughly equal value exchange</p>
        <p style="margin: 3px 0;"><strong>Poor Trade (-5 to -15):</strong> Negative impact, team likely weakened</p>
        <p style="margin: 3px 0;"><strong>Terrible Trade (-15+):</strong> Significant team damage, very poor value</p>
        
        <h4 style="margin: 15px 0 10px 0; color: #2c3e50;">🔧 Technical Features</h4>
        <p style="margin: 3px 0;"><strong>Hover Details:</strong> Teams involved, players exchanged, impact breakdown</p>
        <p style="margin: 3px 0;"><strong>Color Legend:</strong> Each manager assigned unique color for easy identification</p>
        <p style="margin: 3px 0;"><strong>Jitter Positioning:</strong> Overlapping trades separated slightly for visibility</p>
        <p style="margin: 3px 0;"><strong>Worst Trades Report:</strong> Text file generated with detailed analysis of poor trades</p>
    </div>
    """
    
    explanation_div = Div(text=explanation_text, width=1200, height=0, visible=False)
    
    # Create leaderboard
    leaderboard_html = """
    <h3 style="margin:10px 0 5px 0;">🏆 Trade Performance Leaderboard</h3>
    <table style="border-collapse: collapse; width: 100%; font-size: 12px; margin: 5px 0;">
    <tr style="background-color: #f0f0f0; font-weight: bold;">
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">#</th>
        <th style="border: 1px solid #ddd; padding: 8px;">Manager</th>
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Avg Impact</th>
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Total Gain</th>
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Total Trades</th>
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Success Rate</th>
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Trend</th>
    </tr>
    """
    
    for row in leaderboard_data:
        rank = int(row[0])
        color = "#e8f5e8" if rank <= 3 else "#fff5e6" if rank <= 6 else "#ffeaea"
        leaderboard_html += f"""
        <tr style="background-color: {color};">
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[0]}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row[1]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[2]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[3]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[4]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[5]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[6]}</td>
        </tr>"""
    
    leaderboard_html += """
    </table>
    <div style="margin-top: 10px; font-size: 11px; color: #666;">
        <strong>Legend:</strong> Avg Impact = Average net effect per trade | Total Gain = Sum of all trade impacts | 
        Success Rate = % of trades with positive impact | Trend = Overall performance direction
    </div>
    """
    leaderboard_div = Div(text=leaderboard_html, width=600, height=300)
    
    # Create calculation explanation panel (always visible)
    calc_explanation_html = """
    <h3 style="margin:10px 0 5px 0;">📋 How Trade Impact Is Calculated</h3>
    <div style="background-color: #e7f3ff; padding: 12px; border-radius: 5px; margin: 5px 0; border-left: 4px solid #2196F3;">
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 1:</strong> Identify the 2 weeks before and 2 weeks after each trade</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 2:</strong> Calculate average Power Rating for before/after periods</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 3:</strong> Calculate average Roster Grade for before/after periods</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 4:</strong> Power Impact = After Power - Before Power</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 5:</strong> Roster Impact = After Grade - Before Grade</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 6:</strong> Net Effect = Power Impact + Roster Impact</p>
        <p style="margin: 8px 0 5px 0; font-size: 12px; color: #555;"><em>Positive values mean the trade improved your team, negative values mean it hurt your team</em></p>
    </div>
    """
    calc_explanation_div = Div(text=calc_explanation_html, width=1200, height=120)
    
    # Create data sources and renderers for each manager
    data_legend_items = []
    data_renderers = []
    
    for manager in unique_managers:
        if manager not in manager_data:
            continue
            
        data = manager_data[manager]
        color = color_map[manager]
        
        # Create data source for this manager
        source = ColumnDataSource(data={
            'week': data['weeks'],
            'power_impact': data['power_impacts'],
            'grade_impact': data['grade_impacts'],
            'combined_impact': data['combined_impacts'],
            'acquired': data['acquired_players'],
            'gave_up': data['gave_up_players'],
            'other_manager': data['other_managers'],
            'manager': [manager] * len(data['weeks']),
            'trade_id': data['trade_ids']
        })
        
        # Add scatter plot
        scatter = p.scatter(
            x='week', y='combined_impact',
            source=source,
            size=12,
            color=color,
            alpha=0.8,
            line_color='white',
            line_width=1
        )
        
        data_renderers.append(scatter)
        data_legend_items.append(LegendItem(label=f"{manager} ({len(data['weeks'])} trades)", renderers=[scatter]))
    
    # Add interactive legend
    data_legend = Legend(items=data_legend_items, location="top_right", 
                        title="Manager Trade History", click_policy="hide")
    data_legend.title_text_font_size = "11pt"
    data_legend.label_text_font_size = "10pt"
    p.add_layout(data_legend, 'right')
    
    # Clean hover tool - simplified
    hover = HoverTool(tooltips=[
        ("Manager", "@manager"),
        ("Week", "@week{0}"),
        ("Trading Partner", "@other_manager"),
        ("Acquired Players", "@acquired"),
        ("Traded Away", "@gave_up"),
        ("Power Impact", "@power_impact{+0.1f}"),
        ("Roster Impact", "@grade_impact{+0.1f}"),
        ("Net Effect", "@combined_impact{+0.1f}")
    ])
    p.add_tools(hover)
    
    # Create control buttons
    toggle_data_button = Button(label="Toggle All Data", button_type="success", width=150)
    toggle_data_button.js_on_event("button_click", CustomJS(args=dict(renderers=data_renderers), code="""
        let any_visible = false;
        for (let i = 0; i < renderers.length; i++) {
            if (renderers[i].visible) {
                any_visible = true;
                break;
            }
        }
        
        for (let i = 0; i < renderers.length; i++) {
            renderers[i].visible = !any_visible;
        }
        
        cb_obj.label = any_visible ? "Show All Data" : "Hide All Data";
    """))
    
    show_explanation_button = Button(label="Show Calculation Details", button_type="warning", width=180)
    show_explanation_button.js_on_event("button_click", CustomJS(args=dict(explanation_div=explanation_div), code="""
        explanation_div.visible = !explanation_div.visible;
        if (explanation_div.visible) {
            explanation_div.height = 500;
            cb_obj.label = "Hide Calculation Details";
            cb_obj.button_type = "success";
        } else {
            explanation_div.height = 0;
            cb_obj.label = "Show Calculation Details";
            cb_obj.button_type = "warning";
        }
    """))
    
    reset_button = Button(label="Reset Zoom", button_type="danger", width=100)
    reset_button.js_on_event("button_click", CustomJS(args=dict(plot=p), code="""
        plot.x_range.start = 0.5;
        plot.x_range.end = 15.5;
        plot.y_range.start = -30;
        plot.y_range.end = 45;
    """))
    
    # Create layout
    top_row = bokeh_row(leaderboard_div, p)
    button_row = bokeh_row(toggle_data_button, show_explanation_button, reset_button)
    
    # Add spacing between explanation and leaderboard
    spacer_div = Div(text="<div style='height: 50px;'></div>", width=1200, height=50)
    layout = bokeh_column(calc_explanation_div, spacer_div, explanation_div, top_row, button_row)
    
    # Style the plot
    p.grid.grid_line_alpha = 0.3
    p.title.text_font_size = "14pt"
    p.title.align = "center"
    
    show(layout)
    print(f"\n📊 Enhanced trade analysis plot saved as: {plot_filename}")
    print("📈 Features: Individual transactions, clean hover data, worst trades report")
    print("🎮 Interactive: Manager legend, explanation panel, data toggles")
    return plot_filename


def create_waiver_visualization(waiver_impacts, output_dirs=None):
    """Create enhanced waiver wire analysis visualization with individual transactions and leaderboard"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import (ColumnDataSource, HoverTool, Legend, LegendItem, 
                                Button, CustomJS, Div)
        from bokeh.layouts import column as bokeh_column, row as bokeh_row
        from bokeh.palettes import Category20
        import numpy as np
    except ImportError:
        print("\n⚠️  Bokeh not available for waiver visualization")
        return
    
    if not waiver_impacts:
        print("\n⚠️  No waiver data for visualization")
        return
    
    if output_dirs:
        plot_filename = os.path.join(output_dirs['html'], f"waiver_analysis_{output_dirs['timestamp']}.html")
    else:
        plot_filename = f"waiver_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    output_file(plot_filename)
    
    # Create individual waiver transactions with unique identifiers
    individual_waivers = []
    waiver_id = 1
    
    for impact in waiver_impacts:
        # Create unique identifier for each waiver transaction
        individual_waivers.append({
            'waiver_id': waiver_id,
            'manager_name': impact['manager_name'],
            'week': impact['week'],
            'power_impact': impact['power_impact'],
            'grade_impact': impact['grade_impact'], 
            'combined_impact': impact['combined_impact'],
            'player_added': impact.get('player_added', 'Unknown'),
            'player_dropped': impact.get('player_dropped', 'None'),
            'transaction_type': impact.get('transaction_type', 'Waiver')
        })
        waiver_id += 1
    
    # Prepare data by manager with jitter to separate overlapping transactions
    manager_data = {}
    all_managers = set()
    
    for waiver in individual_waivers:
        manager = waiver['manager_name']
        all_managers.add(manager)
        
        if manager not in manager_data:
            manager_data[manager] = {
                'weeks': [],
                'power_impacts': [],
                'grade_impacts': [],
                'combined_impacts': [],
                'players_added': [],
                'players_dropped': [],
                'transaction_types': [],
                'waiver_ids': []
            }
        
        # Add small jitter to prevent exact overlap
        week_jitter = waiver['week'] + np.random.uniform(-0.15, 0.15)
        
        manager_data[manager]['weeks'].append(week_jitter)
        manager_data[manager]['power_impacts'].append(waiver['power_impact'])
        manager_data[manager]['grade_impacts'].append(waiver['grade_impact'])
        manager_data[manager]['combined_impacts'].append(waiver['combined_impact'])
        manager_data[manager]['players_added'].append(waiver['player_added'])
        manager_data[manager]['players_dropped'].append(waiver['player_dropped'])
        manager_data[manager]['transaction_types'].append(waiver['transaction_type'])
        manager_data[manager]['waiver_ids'].append(waiver['waiver_id'])
    
    # Color mapping with legend
    unique_managers = sorted(all_managers)
    colors_palette = Category20[max(3, min(20, len(unique_managers)))]
    color_map = {manager: colors_palette[i % len(colors_palette)] for i, manager in enumerate(unique_managers)}
    
    # Calculate leaderboard statistics
    manager_stats = {}
    for waiver in individual_waivers:
        manager = waiver['manager_name']
        if manager not in manager_stats:
            manager_stats[manager] = {
                'total_waivers': 0,
                'total_impact': 0,
                'impacts': [],
                'positive_waivers': 0,
                'negative_waivers': 0,
                'best_pickup': None,
                'best_pickup_impact': float('-inf')
            }
        
        manager_stats[manager]['total_waivers'] += 1
        manager_stats[manager]['total_impact'] += waiver['combined_impact']
        manager_stats[manager]['impacts'].append(waiver['combined_impact'])
        
        if waiver['combined_impact'] > 0:
            manager_stats[manager]['positive_waivers'] += 1
        elif waiver['combined_impact'] < 0:
            manager_stats[manager]['negative_waivers'] += 1
        
        # Track best pickup
        if waiver['combined_impact'] > manager_stats[manager]['best_pickup_impact']:
            manager_stats[manager]['best_pickup_impact'] = waiver['combined_impact']
            manager_stats[manager]['best_pickup'] = waiver['player_added']
    
    # Create leaderboard data
    leaderboard_data = []
    for manager, stats in manager_stats.items():
        avg_impact = stats['total_impact'] / stats['total_waivers'] if stats['total_waivers'] > 0 else 0
        success_rate = (stats['positive_waivers'] / stats['total_waivers'] * 100) if stats['total_waivers'] > 0 else 0
        
        leaderboard_data.append([
            manager,
            f"{avg_impact:+.2f}",
            f"{stats['total_impact']:+.1f}",
            str(stats['total_waivers']),
            f"{success_rate:.1f}%",
            stats['best_pickup'] or 'None',
            "📈" if avg_impact > 1 else "📉" if avg_impact < -1 else "➡️"
        ])
    
    # Sort by average impact
    leaderboard_data.sort(key=lambda x: float(x[1]), reverse=True)
    for i, row in enumerate(leaderboard_data):
        row.insert(0, str(i + 1))  # Add ranking
    
    # Create main plot
    p = figure(
        width=1200,
        height=700,
        title="Waiver Wire & Free Agent Analysis: Individual Transaction Impact",
        x_axis_label="Week", 
        y_axis_label="Combined Impact Score",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        x_range=(0.5, 15.5),
        y_range=(-20, 25)
    )
    
    # Add zero reference line
    p.line([0.5, 15.5], [0, 0], line_color='black', line_width=1, line_dash='dashed', alpha=0.5)
    
    # Create collapsible explanation panel
    explanation_text = """
    <h3 style="margin:10px 0 5px 0;">📊 Waiver Wire Impact Analysis Methodology</h3>
    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 5px 0;">
        <h4 style="margin: 0 0 10px 0; color: #2c3e50;">🔍 Data Collection & Processing</h4>
        <p style="margin: 3px 0;"><strong>Transaction Detection:</strong> All waiver claims and free agent pickups identified</p>
        <p style="margin: 3px 0;"><strong>Individual Transactions:</strong> Each pickup/drop shown as separate data point</p>
        <p style="margin: 3px 0;"><strong>Transaction Types:</strong> Waiver claims, free agent pickups, and drops tracked</p>
        <p style="margin: 3px 0;"><strong>Time Analysis:</strong> Before/after pickup performance comparison with 2-week windows</p>
        
        <h4 style="margin: 15px 0 10px 0; color: #2c3e50;">📈 Impact Calculation Formula</h4>
        <p style="margin: 3px 0;"><strong>Power Rating Impact:</strong> Change in weekly power score after pickup</p>
        <p style="margin: 3px 0;"><strong>Roster Grade Impact:</strong> Change in roster talent evaluation after pickup</p>
        <p style="margin: 3px 0;"><strong>Combined Score:</strong> Power Impact + Roster Impact (equal weighting)</p>
        <p style="margin: 3px 0;"><strong>Baseline Comparison:</strong> 2 weeks before pickup vs 2 weeks after pickup</p>
        
        <h4 style="margin: 15px 0 10px 0; color: #2c3e50;">🎯 Impact Scale & Interpretation</h4>
        <p style="margin: 3px 0;"><strong>Excellent Pickup (+10+):</strong> Significantly improved team strength</p>
        <p style="margin: 3px 0;"><strong>Good Pickup (+3 to +10):</strong> Solid improvement with positive impact</p>
        <p style="margin: 3px 0;"><strong>Neutral Pickup (-3 to +3):</strong> Minimal impact, depth/bye week move</p>
        <p style="margin: 3px 0;"><strong>Poor Pickup (-3 to -10):</strong> Negative impact, wasted claim/spot</p>
        <p style="margin: 3px 0;"><strong>Terrible Pickup (-10+):</strong> Significant team damage, very poor decision</p>
        
        <h4 style="margin: 15px 0 10px 0; color: #2c3e50;">🔧 Technical Features</h4>
        <p style="margin: 3px 0;"><strong>Hover Details:</strong> Manager, players involved, impact breakdown</p>
        <p style="margin: 3px 0;"><strong>Color Legend:</strong> Each manager assigned unique color</p>
        <p style="margin: 3px 0;"><strong>Transaction Separation:</strong> Overlapping pickups separated for visibility</p>
        <p style="margin: 3px 0;"><strong>Best Pickups Tracking:</strong> Leaderboard shows top waiver wire successes</p>
    </div>
    """
    
    explanation_div = Div(text=explanation_text, width=1200, height=0, visible=False)
    
    # Create leaderboard
    leaderboard_html = """
    <h3 style="margin:10px 0 5px 0;">🏆 Waiver Wire Performance Leaderboard</h3>
    <table style="border-collapse: collapse; width: 100%; font-size: 12px; margin: 5px 0;">
    <tr style="background-color: #f0f0f0; font-weight: bold;">
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">#</th>
        <th style="border: 1px solid #ddd; padding: 8px;">Manager</th>
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Avg Impact</th>
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Total Gain</th>
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Total Moves</th>
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Success Rate</th>
        <th style="border: 1px solid #ddd; padding: 8px;">Best Pickup</th>
        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Trend</th>
    </tr>
    """
    
    for row in leaderboard_data:
        rank = int(row[0])
        color = "#e8f5e8" if rank <= 3 else "#fff5e6" if rank <= 6 else "#ffeaea"
        leaderboard_html += f"""
        <tr style="background-color: {color};">
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[0]}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row[1]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[2]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[3]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[4]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[5]}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row[6]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[7]}</td>
        </tr>"""
    
    leaderboard_html += """
    </table>
    <div style="margin-top: 10px; font-size: 11px; color: #666;">
        <strong>Legend:</strong> Avg Impact = Average net effect per waiver move | Total Gain = Sum of all pickup impacts | 
        Success Rate = % of moves with positive impact | Best Pickup = Highest impact player acquired
    </div>
    """
    leaderboard_div = Div(text=leaderboard_html, width=600, height=350)
    
    # Create calculation explanation panel (always visible)
    calc_explanation_html = """
    <h3 style="margin:10px 0 5px 0;">📋 How Waiver Wire Impact Is Calculated</h3>
    <div style="background-color: #e7f3ff; padding: 12px; border-radius: 5px; margin: 5px 0; border-left: 4px solid #2196F3;">
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 1:</strong> Identify the 2 weeks before and 2 weeks after each pickup</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 2:</strong> Calculate average Power Rating for before/after periods</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 3:</strong> Calculate average Roster Grade for before/after periods</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 4:</strong> Power Impact = After Power - Before Power</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 5:</strong> Roster Impact = After Grade - Before Grade</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong>Step 6:</strong> Net Effect = Power Impact + Roster Impact</p>
        <p style="margin: 8px 0 5px 0; font-size: 12px; color: #555;"><em>Positive values mean the pickup helped your team, negative values mean it hurt or had no benefit</em></p>
    </div>
    """
    calc_explanation_div = Div(text=calc_explanation_html, width=1200, height=120)
    
    # Create data sources and renderers for each manager
    data_legend_items = []
    data_renderers = []
    
    for manager in unique_managers:
        if manager not in manager_data:
            continue
            
        data = manager_data[manager]
        color = color_map[manager]
        
        # Create data source for this manager
        source = ColumnDataSource(data={
            'week': data['weeks'],
            'power_impact': data['power_impacts'],
            'grade_impact': data['grade_impacts'],
            'combined_impact': data['combined_impacts'],
            'player_added': data['players_added'],
            'player_dropped': data['players_dropped'],
            'transaction_type': data['transaction_types'],
            'manager': [manager] * len(data['weeks']),
            'waiver_id': data['waiver_ids']
        })
        
        # Add scatter plot with triangles for waivers
        scatter = p.scatter(
            x='week', y='combined_impact',
            source=source,
            size=10,
            color=color,
            alpha=0.8,
            marker='triangle',
            line_color='white',
            line_width=1
        )
        
        data_renderers.append(scatter)
        data_legend_items.append(LegendItem(label=f"{manager} ({len(data['weeks'])} moves)", renderers=[scatter]))
    
    # Add interactive legend
    data_legend = Legend(items=data_legend_items, location="top_right", 
                        title="Manager Waiver Activity", click_policy="hide")
    data_legend.title_text_font_size = "11pt"
    data_legend.label_text_font_size = "10pt"
    p.add_layout(data_legend, 'right')
    
    # Clean hover tool
    hover = HoverTool(tooltips=[
        ("Manager", "@manager"),
        ("Week", "@week{0}"),
        ("Transaction Type", "@transaction_type"),
        ("Player Added", "@player_added"),
        ("Player Dropped", "@player_dropped"),
        ("Power Impact", "@power_impact{+0.1f}"),
        ("Roster Impact", "@grade_impact{+0.1f}"),
        ("Net Effect", "@combined_impact{+0.1f}")
    ])
    p.add_tools(hover)
    
    # Create control buttons
    toggle_data_button = Button(label="Toggle All Data", button_type="success", width=150)
    toggle_data_button.js_on_event("button_click", CustomJS(args=dict(renderers=data_renderers), code="""
        let any_visible = false;
        for (let i = 0; i < renderers.length; i++) {
            if (renderers[i].visible) {
                any_visible = true;
                break;
            }
        }
        
        for (let i = 0; i < renderers.length; i++) {
            renderers[i].visible = !any_visible;
        }
        
        cb_obj.label = any_visible ? "Show All Data" : "Hide All Data";
    """))
    
    show_explanation_button = Button(label="Show Calculation Details", button_type="warning", width=180)
    show_explanation_button.js_on_event("button_click", CustomJS(args=dict(explanation_div=explanation_div), code="""
        explanation_div.visible = !explanation_div.visible;
        if (explanation_div.visible) {
            explanation_div.height = 500;
            cb_obj.label = "Hide Calculation Details";
            cb_obj.button_type = "success";
        } else {
            explanation_div.height = 0;
            cb_obj.label = "Show Calculation Details";
            cb_obj.button_type = "warning";
        }
    """))
    
    reset_button = Button(label="Reset Zoom", button_type="danger", width=100)
    reset_button.js_on_event("button_click", CustomJS(args=dict(plot=p), code="""
        plot.x_range.start = 0.5;
        plot.x_range.end = 15.5;
        plot.y_range.start = -20;
        plot.y_range.end = 25;
    """))
    
    # Create layout
    top_row = bokeh_row(leaderboard_div, p)
    button_row = bokeh_row(toggle_data_button, show_explanation_button, reset_button)
    
    # Add spacing between explanation and leaderboard
    spacer_div = Div(text="<div style='height: 50px;'></div>", width=1200, height=50)
    layout = bokeh_column(calc_explanation_div, spacer_div, explanation_div, top_row, button_row)
    
    # Style the plot
    p.grid.grid_line_alpha = 0.3
    p.title.text_font_size = "14pt"
    p.title.align = "center"
    
    show(layout)
    print(f"\n📊 Waiver analysis plot saved as: {plot_filename}")
    print("📈 Features: Individual transactions, clean hover data, best pickups leaderboard")
    print("🎮 Interactive: Manager legend, explanation panel, data toggles")
    return plot_filename


def create_manager_grade_visualization(manager_grades, output_dirs=None):
    """Create comprehensive manager grade visualization with enhanced features"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import ColumnDataSource, HoverTool, Legend, Button, CustomJS, Div, DataTable, TableColumn
        from bokeh.layouts import column as bokeh_column, row as bokeh_row
        from bokeh.palettes import Category20
        from sklearn.linear_model import LinearRegression
        import numpy as np
    except ImportError:
        print("\n⚠️  Bokeh or scikit-learn not available for manager grade visualization")
        return
    
    if not manager_grades:
        print("\n⚠️  No manager grade data for visualization")
        return
    
    if output_dirs:
        plot_filename = os.path.join(output_dirs['html'], f"manager_grades_{output_dirs['timestamp']}.html")
    else:
        plot_filename = f"manager_grades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    output_file(plot_filename)
    
    # Enhanced data preparation with better scaling
    colors = Category20[20] if len(manager_grades) <= 20 else Category20[20] * 2
    team_data = []
    
    # Calculate league averages for more significant differences
    all_weekly_grades = []
    for data in manager_grades.values():
        all_weekly_grades.extend(data['weekly_grades'].values())
    
    league_avg = sum(all_weekly_grades) / len(all_weekly_grades) if all_weekly_grades else 5.0
    league_std = np.std(all_weekly_grades) if all_weekly_grades else 1.0
    
    for i, (manager_id, data) in enumerate(manager_grades.items()):
        if not data['weekly_grades']:
            continue
            
        manager_name = data.get('name', manager_id)  # Get manager name
        weeks = sorted([int(w) for w in data['weekly_grades'].keys()])
        
        # Enhanced grade calculation for more significant differences
        raw_grades = []
        for week in weeks:
            # Check both integer and string keys for compatibility
            if week in data['weekly_grades']:
                raw_grades.append(data['weekly_grades'][week])
            elif str(week) in data['weekly_grades']:
                raw_grades.append(data['weekly_grades'][str(week)])
            else:
                print(f"   ⚠️ Warning: Missing grade data for {manager_name} week {week}")
                continue
        
        # Apply z-score normalization then scale to 0-10 with more spread
        enhanced_grades = []
        for grade in raw_grades:
            z_score = (grade - league_avg) / max(league_std, 0.5)
            enhanced_grade = max(0, min(10, 5 + z_score * 2))  # More spread
            enhanced_grades.append(enhanced_grade)
        
        if not raw_grades:
            print(f"   ⚠️ Warning: No weekly grade data for {manager_name}, skipping...")
            continue
            
        # Update weeks to match available data
        weeks = weeks[:len(raw_grades)]
        
        # Add jitter for better visualization
        jittered_weeks = [w + np.random.uniform(-0.08, 0.08) for w in weeks]
        
        # Calculate trend line and slope
        slope = 0
        trend_weeks = []
        trend_grades = []
        
        if len(weeks) >= 3:
            X = np.array(weeks).reshape(-1, 1)
            y = np.array(enhanced_grades)
            
            model = LinearRegression()
            model.fit(X, y)
            slope = model.coef_[0]
            
            # Extend trend line through week 14
            trend_weeks = list(range(min(weeks), 15))
            trend_grades = model.predict(np.array(trend_weeks).reshape(-1, 1)).tolist()
        
        # Calculate proper records using actual data structure
        avg_grades = [statistics.mean(enhanced_grades[:i+1]) for i in range(len(enhanced_grades))]
        
        # Use actual record data from manager_grades structure
        actual_wins = data.get('record', {}).get('wins', 0)
        actual_losses = data.get('record', {}).get('losses', 0)
        combined_wins = data.get('combined_record', {}).get('wins', actual_wins)
        combined_losses = data.get('combined_record', {}).get('losses', actual_losses)
        
        # Build weekly record progression from actual data
        records = []
        combined_records = []
        
        # Get power data for real records if available
        power_data = None
        for pid, pdata in manager_grades.items():
            if pdata.get('name') == manager_name:
                # Found matching manager, get their power data for records
                for key, value in manager_grades.items():
                    if key == pid:
                        break
                break
        
        for j, week in enumerate(weeks):
            # Calculate cumulative records through this week
            weeks_played = j + 1
            wins_through_week = min(actual_wins, weeks_played)  
            losses_through_week = weeks_played - wins_through_week
            
            combined_wins_through_week = min(combined_wins, weeks_played * 2)  # Max 2 per week
            combined_losses_through_week = (weeks_played * 2) - combined_wins_through_week
            
            records.append(f"{wins_through_week}-{losses_through_week}")
            combined_records.append(f"{combined_wins_through_week}-{combined_losses_through_week}")
        
        team_data.append({
            'name': manager_name,
            'color': colors[i % len(colors)],
            'slope': slope,
            'overall_grade': data.get('overall_grade', 0),
            'enhanced_overall': sum(enhanced_grades) / len(enhanced_grades),
            'source': ColumnDataSource(data={
                'week': jittered_weeks,
                'grade': enhanced_grades,
                'team': [manager_name] * len(enhanced_grades),
                'original_week': weeks,
                'original_grade': enhanced_grades,
                'avg_grade': avg_grades,
                'record': records,
                'combined_record': combined_records,
                'overall_grade': [data.get('overall_grade', 0)] * len(enhanced_grades),
                'trade_performance': [data.get('trade_performance', 0)] * len(enhanced_grades),
                'waiver_performance': [data.get('waiver_performance', 0)] * len(enhanced_grades),
                'lineup_performance': [data.get('lineup_performance', 0)] * len(enhanced_grades)
            }),
            'trend_source': ColumnDataSource(data={
                'trend_week': trend_weeks,
                'trend_grade': trend_grades,
                'team_name': [manager_name] * len(trend_weeks),
                'slope': [slope] * len(trend_weeks),
                'slope_display': [f"{slope:+.3f}" if slope != 0 else "0.000"] * len(trend_weeks)
            }) if trend_weeks else None
        })
    
    if not team_data:
        print("   • No manager grade data available for visualization")
        return
    
    # Sort by enhanced overall grade for leaderboard
    team_data.sort(key=lambda x: x['enhanced_overall'], reverse=True)
    
    # Create leaderboard
    leaderboard_data = []
    for i, team in enumerate(team_data):
        trend_icon = "📈" if team['slope'] > 0.1 else "📉" if team['slope'] < -0.1 else "➡️"
        leaderboard_data.append([
            i + 1,
            team['name'],
            f"{team['enhanced_overall']:.2f}",
            f"{team['slope']:+.3f}",
            trend_icon
        ])
    
    # Create plot
    p = figure(
        width=1200,
        height=700,
        title="Manager Performance Grades: Enhanced Weekly Analysis",
        x_axis_label="Week",
        y_axis_label="Manager Grade (0-10 Scale)",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        x_range=(0.5, 14.5),
        y_range=(0, 10)
    )
    
    # Create enhanced hover with proper data
    hover_data = HoverTool(tooltips=[
        ("Manager", "@team"),
        ("Week", "@original_week"),
        ("Manager Grade", "@grade{0.2f}/10"),
        ("Season Average", "@avg_grade{0.2f}/10"),
        ("Regular Record", "@record"),
        ("Combined Record", "@combined_record"),
        ("Overall Grade", "@overall_grade{0.2f}/10"),
        ("Trade Performance", "@trade_performance{0.2f}/10"),
        ("Waiver Performance", "@waiver_performance{0.2f}/10"),
        ("Lineup Performance", "@lineup_performance{0.2f}/10")
    ])
    
    # Separate hover for trend lines
    trend_hover = HoverTool(tooltips=[
        ("Manager", "@team_name"),
        ("Week", "@trend_week"),
        ("Trend Grade", "@trend_grade{0.2f}/10"),
        ("Trend Slope", "@slope_display pts/week")
    ], renderers=[])
    
    p.add_tools(hover_data, trend_hover)
    
    # Plot data points and lines
    data_renderers = []
    trend_renderers = []
    data_legend_items = []
    trend_legend_items = []
    
    for team in team_data:
        # Main data points and connecting lines
        scatter = p.scatter(
            x='week', y='grade',
            source=team['source'],
            color=team['color'],
            size=9,
            alpha=0.8,
            line_color='white',
            line_width=1
        )
        
        line = p.line(
            x='week', y='grade',
            source=team['source'],
            line_color=team['color'],
            line_width=2,
            line_alpha=0.7
        )
        
        data_renderers.extend([scatter, line])
        
        # Trend lines with proper hover
        if team['trend_source']:
            trend_direction = "↗" if team['slope'] > 0.05 else "↘" if team['slope'] < -0.05 else "→"
            trend = p.line(
                x='trend_week', y='trend_grade',
                source=team['trend_source'],
                line_color=team['color'],
                line_width=3,
                line_alpha=0.6,
                line_dash='dashed'
            )
            
            trend_renderers.append(trend)
            trend_hover.renderers.append(trend)
            trend_legend_items.append((f"{team['name']} {trend_direction} ({team['slope']:+.3f}/wk)", [trend]))
        
        data_legend_items.append((f"{team['name']} ({team['enhanced_overall']:.1f})", [scatter, line]))
    
    # Create legends
    data_legend = Legend(items=data_legend_items, location="center", title="Manager Performance")
    data_legend.click_policy = "hide"
    p.add_layout(data_legend, 'right')
    
    if trend_legend_items:
        trend_legend = Legend(items=trend_legend_items, location="center", title="Trend Analysis")
        trend_legend.click_policy = "hide"
        p.add_layout(trend_legend, 'left')
    
    # Create leaderboard table
    leaderboard_html = """
    <h3 style="margin:10px 0 5px 0;">Manager Performance Leaderboard</h3>
    <table style="border-collapse: collapse; width: 100%; font-size: 12px;">
    <tr style="background-color: #f0f0f0; font-weight: bold;">
        <th style="border: 1px solid #ddd; padding: 8px;">#</th>
        <th style="border: 1px solid #ddd; padding: 8px;">Manager</th>
        <th style="border: 1px solid #ddd; padding: 8px;">Grade</th>
        <th style="border: 1px solid #ddd; padding: 8px;">Trend</th>
        <th style="border: 1px solid #ddd; padding: 8px;">Direction</th>
    </tr>
    """
    
    for row in leaderboard_data:
        color = "#e8f5e8" if row[0] <= 3 else "#fff5e6" if row[0] <= 6 else "#ffeaea"
        leaderboard_html += f"""
        <tr style="background-color: {color};">
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[0]}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row[1]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[2]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[3]}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[4]}</td>
        </tr>"""
    
    leaderboard_html += "</table>"
    leaderboard_div = Div(text=leaderboard_html, width=500, height=300)
    
    # Create explanation panel (toggleable)
    explanation_text = """
    <h3 style="margin:5px 0;">Manager Performance Grading Methodology</h3>
    <p style="margin:2px;"><b>Enhanced Calculation:</b> Z-score normalization for greater differentiation between managers</p>
    <p style="margin:2px;"><b>Formula Components:</b></p>
    <ul style="margin:5px 0; padding-left:20px;">
        <li><b>Performance (40%):</b> Weekly scores relative to league average + consistency metrics</li>
        <li><b>Trade Analysis (25%):</b> Net impact of all trade transactions on team improvement</li>
        <li><b>Waiver Analysis (20%):</b> Success rate and impact of waiver wire acquisitions</li>
        <li><b>Start/Sit Accuracy (15%):</b> Optimal lineup decisions vs actual lineup choices</li>
    </ul>
    <p style="margin:2px;"><b>Grade Scale:</b> 8-10 Elite • 6-8 Above Average • 4-6 Average • 2-4 Below Average • 0-2 Poor</p>
    <p style="margin:2px;"><b>Trend Analysis:</b> Linear regression showing management skill development trajectory</p>
    <p style="margin:2px;"><b>Records:</b> Simulated based on weekly performance relative to league average</p>
    """
    
    explanation_div = Div(text=explanation_text, width=1200, height=180)
    
    # Enhanced toggle controls at bottom
    show_explanation_button = Button(label="Show/Hide Explanation", button_type="light", width=180)
    toggle_managers_button = Button(label="Toggle All Data", button_type="success", width=120)
    toggle_trends_button = Button(label="Toggle All Trends", button_type="primary", width=120)
    reset_zoom_button = Button(label="Reset Zoom", button_type="warning", width=100)
    
    # JavaScript callbacks
    explanation_callback = CustomJS(args=dict(explanation=explanation_div), code="""
        explanation.visible = !explanation.visible;
    """)
    
    managers_callback = CustomJS(args=dict(renderers=data_renderers), code="""
        var all_visible = renderers.every(r => r.visible);
        for (var r of renderers) {
            r.visible = !all_visible;
        }
        cb_obj.label = all_visible ? "Show All Data" : "Hide All Data";
    """)
    
    trends_callback = CustomJS(args=dict(renderers=trend_renderers), code="""
        var all_visible = renderers.every(r => r.visible);
        for (var r of renderers) {
            r.visible = !all_visible;
        }
        cb_obj.label = all_visible ? "Show All Trends" : "Hide All Trends";
    """)
    
    reset_callback = CustomJS(args=dict(plot=p), code="""
        plot.x_range.start = 0.5;
        plot.x_range.end = 14.5;
        plot.y_range.start = 0;
        plot.y_range.end = 10;
    """)
    
    show_explanation_button.js_on_click(explanation_callback)
    toggle_managers_button.js_on_click(managers_callback)
    toggle_trends_button.js_on_click(trends_callback)
    reset_zoom_button.js_on_click(reset_callback)
    
    # Layout: leaderboard on left, plot on right, controls at bottom
    top_row = bokeh_row(leaderboard_div, p, spacing=10)
    control_row = bokeh_row(show_explanation_button, toggle_managers_button, toggle_trends_button, reset_zoom_button)
    
    # Start with explanation hidden
    explanation_div.visible = False
    
    layout = bokeh_column(explanation_div, top_row, control_row, spacing=5)
    
    show(layout)
    
    print(f"\n📊 Manager grades analysis saved as: {plot_filename}")
    print(f"   📈 Features: Enhanced calculations, leaderboard, toggleable explanation")
    print(f"   🎮 Interactive: Working toggles, proper hover data, trend analysis") 
    return plot_filename


# Legacy support functions for backward compatibility
def calculate_combined_trade_impact(trade_impacts, roster_grade_impacts=None):
    """Backward compatibility for existing main.py calls"""
    return trade_impacts  # New system already combines impacts


def print_trade_analysis_results(trade_impacts, waiver_impacts=None, combined_impacts=None):
    """Print comprehensive analysis results"""
    print("\n" + "="*65)
    print("📊 COMPREHENSIVE FANTASY ANALYSIS RESULTS")
    print("="*65)
    
    if trade_impacts:
        print(f"\n📈 Trade Analysis Summary:")
        print(f"   • Total Real Trades Analyzed: {len(trade_impacts)}")
        print(f"   • Average Trade Impact: {statistics.mean([t['combined_impact'] for t in trade_impacts]):+.1f}")
        
        # Top trades
        sorted_trades = sorted(trade_impacts, key=lambda x: abs(x['combined_impact']), reverse=True)[:5]
        print(f"\n   🏆 Most Impactful Trades:")
        for i, trade in enumerate(sorted_trades, 1):
            impact_type = "📈" if trade['combined_impact'] > 0 else "📉"
            print(f"   {i}. Week {trade['week']} - {trade['manager_name']}")
            print(f"      {impact_type} Combined Impact: {trade['combined_impact']:+.1f}")
            print(f"      Got: {', '.join(trade['acquired_players'])}")
            print(f"      Gave: {', '.join(trade['gave_up_players'])}")
    
    if waiver_impacts:
        print(f"\n📊 Waiver Wire Analysis Summary:")
        print(f"   • Total Waiver Moves Analyzed: {len(waiver_impacts)}")
        print(f"   • Average Waiver Impact: {statistics.mean([w['combined_impact'] for w in waiver_impacts]):+.1f}")
    
    print("\n" + "="*65)


def categorize_trade_significance(impact_score):
    """Categorize trade significance for compatibility"""
    abs_impact = abs(impact_score)
    if abs_impact >= 15:
        return "Critical"
    elif abs_impact >= 8:
        return "Major"
    elif abs_impact >= 3:
        return "Moderate"
    elif abs_impact >= 1:
        return "Minor"
    else:
        return "Minimal"