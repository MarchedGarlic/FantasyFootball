#!/usr/bin/env python3
"""
Comprehensive Analysis Module
Analyzes trades, waivers, and manager performance using multiple metrics
"""

import statistics
import numpy as np
import os
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from src.bokeh_mobile import make_bokeh_html_mobile_friendly
from src.utils import get_manager_name


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


def get_player_info_from_id(player_id, all_players=None):
    """Name + fantasy position for a player ID, used to value individual traded players
    (get_player_name_from_id alone isn't enough since grading needs the position too)."""
    name = get_player_name_from_id(player_id, all_players)
    position = 'Unknown'
    if all_players and str(player_id) in all_players:
        position = all_players[str(player_id)].get('position', 'Unknown')
    return {'name': name, 'position': position}


def calculate_player_value_trade_impact(acquired_player_infos, gave_up_player_infos, analyzer):
    """Value a trade by the actual players that moved, using the existing ESPN-tier
    grade_player() (~1-10 scale). This is the primary trade score - see CLAUDE.md section 4.1
    for why the old team-wide power/grade delta was replaced: it never looked at which players
    were actually traded.
    """
    value_acquired = sum(
        analyzer.grade_player(p['name'], p['position'])['grade'] for p in acquired_player_infos
    )
    value_given_up = sum(
        analyzer.grade_player(p['name'], p['position'])['grade'] for p in gave_up_player_infos
    )
    return {
        'value_acquired': round(value_acquired, 2),
        'value_given_up': round(value_given_up, 2),
        'net_player_value': round(value_acquired - value_given_up, 2),
    }


def _parse_week_num(week_key):
    """Accepts either 'Week N' string keys or bare week-number keys."""
    if isinstance(week_key, str) and 'Week' in week_key:
        return int(week_key.split()[1])
    elif isinstance(week_key, (int, float)):
        return int(week_key)
    return None


def _find_faab_event(faab_ledger, transaction_id, roster_id):
    """Look up the pre-scored FAAB event (see src/faab_analysis.py) for one roster's leg of a
    specific transaction. Returns None if the league isn't on FAAB or this transaction/roster
    didn't spend or receive FAAB."""
    if not faab_ledger or not faab_ledger.get('enabled') or not transaction_id:
        return None
    for event in faab_ledger.get('events', []):
        if event.get('transaction_id') == transaction_id and event.get('roster_id') == roster_id:
            return event
    return None


def _faab_fields(faab_event):
    if not faab_event:
        return {
            'faab_spent': None, 'faab_direction': None, 'faab_aggressiveness_score': None,
            'faab_commitment_ratio': None, 'faab_relative_scarcity': None,
        }
    return {
        'faab_spent': faab_event['amount'],
        'faab_direction': faab_event['direction'],
        'faab_aggressiveness_score': faab_event.get('aggressiveness_score'),
        'faab_commitment_ratio': faab_event.get('commitment_ratio'),
        'faab_relative_scarcity': faab_event.get('relative_scarcity'),
    }


def analyze_real_trades_only(transactions_data, team_power_data, roster_grade_data, user_lookup,
                              roster_to_manager, all_players=None, output_dirs=None,
                              faab_ledger=None, analyzer=None):
    """Analyze actual trades with player-value-based impact scoring (CLAUDE.md section 4.1).

    Trading partners are identified by roster_id/manager_id, not display-name equality (the old
    lookup crashed via StopIteration whenever two managers shared a display name). 3+ team
    trades are analyzed per-manager instead of being silently dropped - each manager's own
    acquired/given-up players are still correctly attributed from Sleeper's flat adds/drops maps.
    """
    print("Analyzing Real Trade Impacts Only...")

    trade_impacts = []

    for week_key, week_transactions in transactions_data.items():
        if not week_transactions:
            continue

        week_num = _parse_week_num(week_key)
        if week_num is None:
            continue

        for transaction in week_transactions:
            if not transaction or not isinstance(transaction, dict):
                continue

            if transaction.get('type') != 'trade':
                continue
            if transaction.get('status') not in (None, 'complete'):
                continue

            adds = transaction.get('adds', {}) or {}
            drops = transaction.get('drops', {}) or {}
            roster_ids = transaction.get('roster_ids', []) or []

            if len(roster_ids) < 2:
                continue

            print(f"\n   Analyzing Trade in Week {week_num}:")
            is_multi_team = len(roster_ids) > 2
            if is_multi_team:
                print(f"     ({len(roster_ids)}-team trade)")

            manager_data = {}
            for roster_id in roster_ids:
                if roster_id not in roster_to_manager:
                    continue
                manager_id = roster_to_manager[roster_id]
                if manager_id not in user_lookup:
                    continue

                manager_name = get_manager_name(user_lookup, manager_id)
                acquired_ids = [pid for pid, rid in adds.items() if rid == roster_id]
                gave_up_ids = [pid for pid, rid in drops.items() if rid == roster_id]

                manager_data[roster_id] = {
                    'manager_id': manager_id,
                    'name': manager_name,
                    'roster_id': roster_id,
                    'acquired': [get_player_name_from_id(pid, all_players) for pid in acquired_ids],
                    'gave_up': [get_player_name_from_id(pid, all_players) for pid in gave_up_ids],
                    'acquired_infos': [get_player_info_from_id(pid, all_players) for pid in acquired_ids],
                    'gave_up_infos': [get_player_info_from_id(pid, all_players) for pid in gave_up_ids],
                }

            if len(manager_data) < 2:
                print("     [WARNING] Could not identify at least 2 trading partners")
                continue

            for roster_id, trade_info in manager_data.items():
                manager_id = trade_info['manager_id']
                other_managers = [m for rid, m in manager_data.items() if rid != roster_id]
                other_manager_names = ', '.join(m['name'] for m in other_managers)
                other_acquired = [p for m in other_managers for p in m['acquired']]
                other_gave_up = [p for m in other_managers for p in m['gave_up']]

                if analyzer is not None:
                    player_value = calculate_player_value_trade_impact(
                        trade_info['acquired_infos'], trade_info['gave_up_infos'], analyzer
                    )
                else:
                    player_value = {'value_acquired': 0.0, 'value_given_up': 0.0, 'net_player_value': 0.0}

                # Team power/roster-grade trend around the trade date - supplementary context
                # only (correlation, not the trade's causal value), computed against the
                # manager's real historical roster now that main.py reconstructs it.
                team_trend = calculate_improved_trade_impact(
                    manager_id, week_num, team_power_data, roster_grade_data
                )

                faab_event = _find_faab_event(faab_ledger, transaction.get('transaction_id'), roster_id)

                trade_impacts.append({
                    'week': week_num,
                    'manager_id': manager_id,
                    'manager_name': trade_info['name'],
                    'other_manager': other_manager_names,
                    'acquired_players': trade_info['acquired'],
                    'gave_up_players': trade_info['gave_up'],
                    'other_acquired': other_acquired,
                    'other_gave_up': other_gave_up,
                    'is_multi_team_trade': is_multi_team,
                    'value_acquired': player_value['value_acquired'],
                    'value_given_up': player_value['value_given_up'],
                    'combined_impact': player_value['net_player_value'],
                    'team_trend_power_impact': team_trend['power_impact'],
                    'team_trend_grade_impact': team_trend['grade_impact'],
                    **_faab_fields(faab_event),
                })

                print(f"     {trade_info['name']}: Player Value {player_value['net_player_value']:+.1f} "
                      f"(Acquired {player_value['value_acquired']:.1f}, Gave up {player_value['value_given_up']:.1f}) | "
                      f"Team Trend: Power {team_trend['power_impact']:+.1f}, Grade {team_trend['grade_impact']:+.1f}")

    return trade_impacts


def _build_weekly_position_baselines(all_weekly_matchups, all_players):
    """League-wide, position-by-position weekly scoring baseline (mean + population stdev)
    across every rostered player's actual points that week (bench included - Sleeper's
    players_points only ever contains players who were on somebody's roster that week). This is
    the yardstick a waiver pickup's own points get compared against - see the waiver-scoring
    rewrite note on analyze_waiver_pickups() below.
    """
    baselines = {}
    for week, matchups in (all_weekly_matchups or {}).items():
        points_by_position = defaultdict(list)
        for team in matchups or []:
            for player_id, points in (team.get('players_points') or {}).items():
                if points is None:
                    continue
                position = (all_players or {}).get(player_id, {}).get('position')
                if not position:
                    continue
                points_by_position[position].append(float(points))

        baselines[week] = {
            position: {
                'mean': statistics.mean(values),
                'stdev': statistics.pstdev(values) if len(values) > 1 else 0.0,
                'n': len(values),
            }
            for position, values in points_by_position.items()
        }
    return baselines


def _build_player_weekly_points(all_weekly_matchups):
    """player_id -> {week: points actually scored that week}, flattened from every roster's
    matchup data - main.py's weekly_top_players is trimmed to the league-wide top 25/week and
    isn't enough here, since most waiver pickups never crack that list.
    """
    player_points = defaultdict(dict)
    for week, matchups in (all_weekly_matchups or {}).items():
        for team in matchups or []:
            for player_id, points in (team.get('players_points') or {}).items():
                if points is None:
                    continue
                player_points[player_id][week] = float(points)
    return player_points


def _build_drop_index(transactions_data):
    """(roster_id, player_id) -> sorted weeks that roster gave up that player, across every
    transaction type - a trade's own 'drops' map represents 'traded away' the same shape a
    waiver transaction's does, so one pass over all transactions covers both. Used to find when
    a waiver pickup's rostered window ends.
    """
    drop_weeks = defaultdict(list)
    for week_key, transactions in (transactions_data or {}).items():
        week_num = _parse_week_num(week_key)
        if week_num is None:
            continue
        for transaction in transactions or []:
            if not transaction or not isinstance(transaction, dict):
                continue
            if transaction.get('status') not in (None, 'complete'):
                continue
            for player_id, roster_id in (transaction.get('drops') or {}).items():
                drop_weeks[(roster_id, player_id)].append(week_num)

    for key in drop_weeks:
        drop_weeks[key].sort()
    return drop_weeks


def _rostered_window_end(drop_index, roster_id, player_id, add_week, last_week):
    """Last week this roster still had this player, starting from add_week: the week before
    their next drop of this exact player, or the last analyzed week if they never gave them up.
    """
    future_drops = [w for w in drop_index.get((roster_id, player_id), []) if w >= add_week]
    if not future_drops:
        return last_week
    return max(add_week, future_drops[0] - 1)


def calculate_pickup_points_impact(player_ids, roster_id, add_week, last_week,
                                    player_weekly_points, position_baselines,
                                    drop_index, all_players):
    """Score a waiver/FA pickup by the points the added player(s) actually scored while
    rostered, position-adjusted against the league-wide weekly average at that position (see
    CLAUDE.md's waiver-scoring rewrite: this replaces a team-wide power/grade delta, which
    measured bye weeks, injuries, and ordinary variance instead of the pickup itself, and
    couldn't distinguish a league-winning stash from a bench-warmer added the same week).

    For each week the player was rostered (from the pickup through the week before their next
    drop, or the end of the analyzed season), their points that week become a z-score against
    every rostered player at that position league-wide that same week. The pickup's score is
    the average of those z-scores: how many standard deviations above/below a typical rostered
    player at that position this pickup performed, per week they were held. A transaction with
    multiple simultaneous adds gets one score averaged across all of them, matching the
    one-entry-per-transaction design (CLAUDE.md section 4.4).
    """
    z_scores = []
    total_points = 0.0
    weeks_scored = 0

    for player_id in player_ids:
        position = (all_players or {}).get(player_id, {}).get('position')
        end_week = _rostered_window_end(drop_index, roster_id, player_id, add_week, last_week)

        for week in range(add_week, end_week + 1):
            points = player_weekly_points.get(player_id, {}).get(week)
            if points is None:
                continue  # bye week, inactive, or game data not yet available
            baseline = (position_baselines.get(week) or {}).get(position)
            if not baseline or baseline['n'] < 2:
                continue  # too few rostered players at this position that week to compare against

            mean, stdev = baseline['mean'], baseline['stdev']
            z_scores.append((points - mean) / stdev if stdev > 0 else 0.0)
            total_points += points
            weeks_scored += 1

    position_adjusted_score = round(sum(z_scores) / len(z_scores), 3) if z_scores else 0.0
    return {
        'combined_impact': position_adjusted_score,
        'weeks_rostered_scored': weeks_scored,
        'total_points_while_rostered': round(total_points, 1),
    }


def analyze_waiver_pickups(transactions_data, user_lookup, roster_to_manager,
                            all_weekly_matchups, all_players=None, output_dirs=None, faab_ledger=None):
    """Analyze waiver wire and free agent pickups with position-adjusted points impact scoring.

    One entry per (transaction, roster) - not per added player. The old version created a
    separate entry per player added within a single transaction, each carrying the *same*
    team-level power/grade impact, which double- (or triple-) counted that manager's weekly
    impact and 'total moves' whenever they batched multiple simultaneous adds into one waiver
    run (see CLAUDE.md section 4.4). combined_impact now comes from
    calculate_pickup_points_impact() - the added player(s)' own actual performance while
    rostered, not a team-wide delta.
    """
    print("\nAnalyzing Waiver Wire & Free Agent Impacts...")

    if not all_weekly_matchups:
        print("     No weekly matchup data available - skipping waiver impact scoring")
        return []

    last_week = max(all_weekly_matchups.keys())
    position_baselines = _build_weekly_position_baselines(all_weekly_matchups, all_players)
    player_weekly_points = _build_player_weekly_points(all_weekly_matchups)
    drop_index = _build_drop_index(transactions_data)

    waiver_impacts = []

    for week_key, week_transactions in transactions_data.items():
        if not week_transactions:
            continue

        week_num = _parse_week_num(week_key)
        if week_num is None:
            print(f"   [WARNING] Skipping invalid week key: {week_key}")
            continue

        for transaction in week_transactions:
            if not transaction or not isinstance(transaction, dict):
                continue

            transaction_type = transaction.get('type', 'unknown')
            if transaction_type == 'trade':
                continue
            if transaction.get('status') not in (None, 'complete'):
                continue

            adds = transaction.get('adds', {}) or {}
            drops = transaction.get('drops', {}) or {}
            if not adds:
                continue

            rosters_involved = set(adds.values()) | set(drops.values())

            for roster_id in rosters_involved:
                if roster_id not in roster_to_manager:
                    continue
                manager_id = roster_to_manager[roster_id]
                if manager_id not in user_lookup:
                    continue

                manager_name = get_manager_name(user_lookup, manager_id)
                player_ids_added = [pid for pid, rid in adds.items() if rid == roster_id]
                players_added = [get_player_name_from_id(pid, all_players) for pid in player_ids_added]
                players_dropped = [get_player_name_from_id(pid, all_players) for pid, rid in drops.items() if rid == roster_id]

                if not players_added:
                    continue

                impact = calculate_pickup_points_impact(
                    player_ids_added, roster_id, week_num, last_week,
                    player_weekly_points, position_baselines, drop_index, all_players,
                )
                faab_event = _find_faab_event(faab_ledger, transaction.get('transaction_id'), roster_id)

                waiver_impacts.append({
                    'week': week_num,
                    'manager_id': manager_id,
                    'manager_name': manager_name,
                    'transaction_id': transaction.get('transaction_id'),
                    'players_added': players_added,
                    'players_dropped': players_dropped or ['None (roster space)'],
                    'player_added': ', '.join(players_added),
                    'player_dropped': ', '.join(players_dropped) if players_dropped else 'None (roster space)',
                    'transaction_type': transaction_type,
                    **impact,
                    **_faab_fields(faab_event),
                })

    print(f"     Analyzed {len(waiver_impacts)} waiver/FA transactions")
    return waiver_impacts


def calculate_improved_trade_impact(manager_id, trade_week, team_power_data, roster_grade_data, matchup_data=None):
    """
    Team-wide power rating / roster grade trend around a trade - SUPPLEMENTARY CONTEXT ONLY,
    not the trade's score (see CLAUDE.md section 4.1). analyze_real_trades_only() uses only this
    function's 'power_impact'/'grade_impact' fields to show "this manager was already trending
    up/down going into the trade"; the trade's actual combined_impact score comes from
    calculate_player_value_trade_impact() instead, which values the specific players traded.
    roster_grade_data now reflects each manager's real historical roster per week (reconstructed
    in main.py), so this trend is meaningful context rather than the random-noise signal it used
    to be layered on top of.
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


def calculate_manager_grades(trade_impacts, waiver_impacts, team_power_data, roster_grade_data, user_lookup, matchup_data=None, weeks=None):
    """Calculate comprehensive manager grades based on trades, waivers, and lineup decisions"""
    print("\nCalculating Manager Performance Grades...")
    
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
            # combined_impact is now a position-adjusted z-score (typically roughly -2.5..+2.5,
            # not the old team-delta's tens-scale), so it's a multiplier here, not a divisor:
            # +1 std dev above a typical rostered player at that position swings the grade by 2.5.
            waiver_score = max(0, min(10, 5 + impact['combined_impact'] * 2.5))
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
    
    # Calculate weekly manager grades and records using real data. `weeks` should be the
    # league's real analyzed range (main.py's _determine_analysis_weeks()) - falling back to
    # 1-15 only protects callers that don't pass it, not this pipeline's real run.
    for week in (weeks or range(1, 16)):
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
            
            # Use real win/loss records from power data if available. Only overwrite the
            # running record on a week that actually has real cumulative win/loss data for
            # this manager - a bye/eliminated-from-playoffs week (common once the real
            # analyzed range extends into the fantasy playoffs, weeks 16+) has no matchup, and
            # unconditionally doing `.get(week, 0)` on those weeks was resetting an otherwise
            # correct record back to 0-0 whenever such a week was the last one processed.
            power_team_data = team_power_data.get(manager_id, {})
            cumulative_wins_by_week = power_team_data.get('cumulative_wins', {})
            cumulative_losses_by_week = power_team_data.get('cumulative_losses', {})

            if week in cumulative_wins_by_week and week in cumulative_losses_by_week:
                week_wins = cumulative_wins_by_week[week]
                week_losses = cumulative_losses_by_week[week]

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
            elif not cumulative_wins_by_week:
                # No real power data for this manager for any week (not just this one) -
                # fall back to a performance-based simulation rather than leaving their
                # record at 0-0 for the whole season.
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
        print(f"     {manager_name}: Overall Grade {data['overall_grade']:.1f}/10 " +
              f"(Record: {data['record']['wins']}-{data['record']['losses']})")
    
    return manager_grades


def create_trade_visualization(trade_impacts, transactions_data=None, output_dirs=None):
    """Create enhanced trade visualization with clean data, leaderboard, and detailed explanations"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import (ColumnDataSource, HoverTool, Legend, LegendItem,
                                Button, CustomJS, Div, LabelSet)
        from bokeh.layouts import column as bokeh_column, row as bokeh_row
        from sklearn.linear_model import LinearRegression
        import numpy as np
        from src.bokeh_theme import (
            style_figure, style_legend, legend_toggle_button, button_stylesheet, dark_palette,
            SURFACE, SURFACE_RAISED, LINE, INK, INK_MUTED, ACCENT,
            PANEL_STYLE, CALLOUT_STYLE, HEADING_STYLE, DESCRIPTION_STYLE, LABEL_STYLE,
        )
    except ImportError:
        print("\n⚠️  Bokeh and/or sklearn not available for trade visualization")
        return
    
    if not trade_impacts:
        print("\n⚠️  No trade data for visualization")
        return

    # Real last analyzed week, not a hardcoded "assume 15 weeks" guess.
    last_week = max((impact['week'] for impact in trade_impacts), default=15)

    if output_dirs:
        plot_filename = os.path.join(output_dirs['html'], "trade_analysis.html")
    else:
        plot_filename = "trade_analysis.html"
    output_file(plot_filename)
    
    # Create individual trade transactions with unique identifiers
    individual_trades = []
    trade_id = 1
    
    for impact in trade_impacts:
        # Create unique identifier for each trade transaction.
        # 'power_impact'/'grade_impact' here are the team-wide TREND around the trade date -
        # supplementary context, not the trade's score. 'combined_impact' is the actual trade
        # score: net player value of who was acquired vs. given up (CLAUDE.md section 4.1).
        individual_trades.append({
            'trade_id': trade_id,
            'manager_name': impact['manager_name'],
            'week': impact['week'],
            'power_impact': impact.get('team_trend_power_impact', 0.0),
            'grade_impact': impact.get('team_trend_grade_impact', 0.0),
            'combined_impact': impact['combined_impact'],
            'value_acquired': impact.get('value_acquired', 0.0),
            'value_given_up': impact.get('value_given_up', 0.0),
            'acquired_players': impact['acquired_players'],
            'gave_up_players': impact['gave_up_players'],
            'other_manager': impact['other_manager'],
            'faab_note': (f"${impact['faab_spent']:.0f} FAAB {impact['faab_direction']}"
                          if impact.get('faab_spent') else 'No FAAB'),
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
                'trade_ids': [],
                'faab_notes': [],
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
        manager_data[manager]['faab_notes'].append(trade.get('faab_note', 'No FAAB'))
    
    # Color mapping with legend (dark-optimized palette - see src/bokeh_theme.py)
    unique_managers = sorted(all_managers)
    colors_palette = dark_palette(len(unique_managers))
    color_map = {manager: colors_palette[i % len(colors_palette)] for i, manager in enumerate(unique_managers)}

    # Create leaderboard of worst trades. There is exactly one impact formula in this codebase
    # now (CLAUDE.md section 4.1): combined_impact = net player value acquired vs. given up.
    # The old version ranked this leaderboard by a *different* ad hoc formula than the one
    # shown on the chart/report, which never matched the methodology text either.
    worst_trades = []
    for trade in individual_trades:
        worst_trades.append({
            'manager': trade['manager_name'],
            'week': trade['week'],
            'combined_impact': trade['combined_impact'],
            'value_acquired': trade.get('value_acquired', 0.0),
            'value_given_up': trade.get('value_given_up', 0.0),
            'acquired': ', '.join([p.strip() for p in trade['acquired_players']]) if trade['acquired_players'] else 'None',
            'gave_up': ', '.join([p.strip() for p in trade['gave_up_players']]) if trade['gave_up_players'] else 'None',
            'other_manager': trade['other_manager'],
            'power_impact': trade['power_impact'],
            'grade_impact': trade['grade_impact'],
            'faab_note': trade.get('faab_note', 'No FAAB'),
        })

    # Sort by worst (most negative) net player value and create both text and HTML reports
    worst_trades.sort(key=lambda x: x['combined_impact'])

    # Print worst trades summary to terminal
    print("\n" + "="*65)
    print("WORST TRADES ANALYSIS (Net Player Value)")
    print("="*65)
    print(f"Total Trades Analyzed: {len(worst_trades)}")
    if worst_trades:
        print(f"Worst Net Player Value: {worst_trades[0]['combined_impact']:+.1f} ({worst_trades[0]['manager']})")
        print("\nTOP 5 WORST TRADES (Net Player Value):")
        print(f"{'Rank':<4} {'Manager':<15} {'Week':<4} {'Net Value':<9} {'Trade Summary':<30}")
        print("-" * 70)
        for i, trade in enumerate(worst_trades[:5]):
            trade_summary = f"Got {trade['acquired'][:15]}..." if len(trade['acquired']) > 15 else trade['acquired']
            print(f"{i+1:<4} {trade['manager'][:14]:<15} {trade['week']:<4} {trade['combined_impact']:+8.1f} {trade_summary:<30}")
        
        # Show worst power impact trades
        power_sorted = sorted(worst_trades, key=lambda x: x['power_impact'])
        print(f"\nTOP 5 WORST POWER IMPACT TRADES:")
        print(f"{'Rank':<4} {'Manager':<15} {'Week':<4} {'Power':<8} {'Trade Summary':<30}")
        print("-" * 65)
        for i, trade in enumerate(power_sorted[:5]):
            trade_summary = f"Got {trade['acquired'][:15]}..." if len(trade['acquired']) > 15 else trade['acquired']
            print(f"{i+1:<4} {trade['manager'][:14]:<15} {trade['week']:<4} {trade['power_impact']:+7.1f} {trade_summary:<30}")
        
        # Show worst roster grade impact trades
        grade_sorted = sorted(worst_trades, key=lambda x: x['grade_impact'])
        print(f"\nTOP 5 WORST ROSTER GRADE IMPACT TRADES:")
        print(f"{'Rank':<4} {'Manager':<15} {'Week':<4} {'Grade':<8} {'Trade Summary':<30}")
        print("-" * 65)
        for i, trade in enumerate(grade_sorted[:5]):
            trade_summary = f"Got {trade['acquired'][:15]}..." if len(trade['acquired']) > 15 else trade['acquired']
            print(f"{i+1:<4} {trade['manager'][:14]:<15} {trade['week']:<4} {trade['grade_impact']:+7.1f} {trade_summary:<30}")
    
    # Save text file
    if output_dirs:
        worst_trades_filename = os.path.join(output_dirs['text'], "worst_trades_report.txt")
    else:
        worst_trades_filename = "worst_trades_report.txt"
    
    with open(worst_trades_filename, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("WORST TRADES ANALYSIS REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("METHODOLOGY:\n")
        f.write("- Combined Impact = Net Player Value = Value Acquired - Value Given Up\n")
        f.write("- Each traded player is graded on ESPN's season stat-leader tiers (~1-10 scale)\n")
        f.write("- Power/Grade Impact below are supplementary context (team trend around the\n")
        f.write("  trade date), not part of the Combined Impact score\n")
        f.write("- Negative Combined Impact means this manager gave up more value than they received\n")
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
    
    # Create HTML report
    html_content = create_worst_trades_html_report(worst_trades, output_dirs)
    
    if output_dirs:
        html_filename = os.path.join(output_dirs['html'], "worst_trades_report.html")
    else:
        html_filename = "worst_trades_report.html"
    
    with open(html_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Worst trades text report saved as: {worst_trades_filename}")
    print(f"Worst trades HTML report saved as: {html_filename}")
    
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
        sizing_mode="stretch_width",
        title="Trade Impact Analysis: Individual Transaction Performance",
        x_axis_label="Week",
        y_axis_label="Combined Impact Score",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        x_range=(0.5, last_week + 0.5),
        y_range=(-30, 45)
    )
    style_figure(p)

    # Add zero reference line
    p.line([0.5, last_week + 0.5], [0, 0], line_color=LINE, line_width=1, line_dash='dashed', alpha=0.8)

    # Create collapsible explanation panel
    explanation_text = f"""
    <div style="{PANEL_STYLE}">
        <h3 style="{HEADING_STYLE}">Trade Impact Analysis Methodology</h3>
        <h4 style="{HEADING_STYLE}font-size:15px;">Data Collection &amp; Processing</h4>
        <p style="{LABEL_STYLE}"><strong>Trade Detection:</strong> Real fantasy football trades identified from league transaction data</p>
        <p style="{LABEL_STYLE}"><strong>Individual Transactions:</strong> Each trade shown as separate data point (no aggregation)</p>
        <p style="{LABEL_STYLE}"><strong>Multi-Manager Trades:</strong> Complex trades broken down by individual manager perspective</p>
        <p style="{LABEL_STYLE}"><strong>Time Analysis:</strong> Before/after trade performance comparison with 2-week windows</p>

        <h4 style="{HEADING_STYLE}font-size:15px;margin-top:15px;">Impact Calculation Formula</h4>
        <p style="{LABEL_STYLE}"><strong>Combined Impact (the plotted score):</strong> Net player value = value of players acquired minus value of players given up, each player graded on ESPN's season stat-leader tiers (~1-10 scale)</p>
        <p style="{LABEL_STYLE}"><strong>Team Trend (context only, shown on hover):</strong> This manager's weekly power rating / roster grade change from the week before the trade to the week of the trade - correlation, not the trade's cause</p>
        <p style="{LABEL_STYLE}"><strong>FAAB:</strong> Shown on hover when the trade also included a FAAB budget transfer</p>

        <h4 style="{HEADING_STYLE}font-size:15px;margin-top:15px;">Impact Scale &amp; Interpretation</h4>
        <p style="{LABEL_STYLE}"><strong>Excellent Trade (+15+):</strong> Significantly improved team strength and performance</p>
        <p style="{LABEL_STYLE}"><strong>Good Trade (+5 to +15):</strong> Solid improvement with positive team impact</p>
        <p style="{LABEL_STYLE}"><strong>Neutral Trade (-5 to +5):</strong> Minimal impact, roughly equal value exchange</p>
        <p style="{LABEL_STYLE}"><strong>Poor Trade (-5 to -15):</strong> Negative impact, team likely weakened</p>
        <p style="{LABEL_STYLE}"><strong>Terrible Trade (-15+):</strong> Significant team damage, very poor value</p>

        <h4 style="{HEADING_STYLE}font-size:15px;margin-top:15px;">Technical Features</h4>
        <p style="{LABEL_STYLE}"><strong>Hover Details:</strong> Teams involved, players exchanged, impact breakdown</p>
        <p style="{LABEL_STYLE}"><strong>Color Legend:</strong> Each manager assigned unique color for easy identification</p>
        <p style="{LABEL_STYLE}"><strong>Jitter Positioning:</strong> Overlapping trades separated slightly for visibility</p>
        <p style="{LABEL_STYLE}"><strong>Worst Trades Report:</strong> Text file generated with detailed analysis of poor trades</p>
    </div>
    """

    explanation_div = Div(text=explanation_text, sizing_mode="stretch_width", max_width=1200, height=0, visible=False)

    # Create leaderboard
    leaderboard_html = f"""
    <h3 style="{HEADING_STYLE}">Trade Performance Leaderboard</h3>
    <table style="border-collapse: collapse; width: 100%; font-size: 13px; margin: 5px 0; color: {INK};">
    <tr style="background-color: {SURFACE_RAISED};">
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">#</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: left; color: {INK_MUTED};">Manager</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Avg Impact</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Total Gain</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Total Trades</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Success Rate</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Trend</th>
    </tr>
    """

    for row in leaderboard_data:
        rank = int(row[0])
        row_bg = SURFACE if rank % 2 == 0 else "transparent"
        rank_color = ACCENT if rank <= 3 else INK
        leaderboard_html += f"""
        <tr style="background-color: {row_bg};">
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; font-weight: 700; color: {rank_color};">{row[0]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px;">{row[1]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center;">{row[2]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center;">{row[3]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">{row[4]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">{row[5]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center;">{row[6]}</td>
        </tr>"""

    leaderboard_html += f"""
    </table>
    <div style="margin-top: 10px; font-size: 12px; color: {INK_MUTED};">
        <strong>Legend:</strong> Avg Impact = average net effect per trade &middot; Total Gain = sum of all trade impacts &middot;
        Success Rate = % of trades with positive impact &middot; Trend = overall performance direction
    </div>
    """
    # Wrapped in the leaderboard's own HTML (not an external stylesheet) because Bokeh 3.x
    # renders every Div inside a shadow root that external CSS can't reach - see
    # src/bokeh_mobile.py's module docstring for how this was confirmed empirically. Width is
    # `100vw`, not `100%`: the wrapper's real parent (Bokeh's own `.bk-clearfix`, also inside
    # the shadow root) is `display: inline-block` and shrinks to fit its content, so a
    # percentage width has no real containing block to resolve against and just falls back to
    # the table's own natural (too-wide) size - confirmed by measuring the actual rendered
    # boxes. Viewport units don't have that circularity, and since this Div always ends up
    # spanning the full stacked-column width (see the row-to-column fix above), the viewport
    # width is the right proxy for "however much horizontal room this report actually has".
    leaderboard_div = Div(
        text=f'<div style="display:block;width:100vw;overflow-x:auto;-webkit-overflow-scrolling:touch;background-color:{SURFACE};border:1px solid {LINE};border-radius:16px;padding:16px 18px;box-sizing:border-box;">{leaderboard_html}</div>',
        sizing_mode="stretch_width", max_width=600, height_policy="auto"
    )

    # Create calculation explanation panel (always visible - larger, higher-contrast
    # description text sits at the top of the page, explicit user request)
    calc_explanation_html = f"""
    <h3 style="{HEADING_STYLE}">How Trade Impact Is Calculated</h3>
    <div style="{CALLOUT_STYLE}">
        <p style="{DESCRIPTION_STYLE}"><strong>Step 1:</strong> Grade every player acquired and every player given up (ESPN season stat-leader tiers, ~1-10 scale)</p>
        <p style="{DESCRIPTION_STYLE}"><strong>Step 2:</strong> Value Acquired = sum of acquired players' grades</p>
        <p style="{DESCRIPTION_STYLE}"><strong>Step 3:</strong> Value Given Up = sum of given-up players' grades</p>
        <p style="{DESCRIPTION_STYLE}"><strong>Step 4:</strong> Combined Impact = Value Acquired - Value Given Up</p>
        <p style="{DESCRIPTION_STYLE}"><strong>Context only:</strong> Team Trend (hover) compares this manager's power rating/roster grade the week before vs. the week of the trade - it is not part of the score</p>
        <p style="{DESCRIPTION_STYLE} margin-top: 8px; font-style: italic;">Positive values mean the manager received more value than they gave up; negative values mean the opposite</p>
        <p style="{DESCRIPTION_STYLE} margin-top: 8px;">
            <strong style="color:{ACCENT};">What this means:</strong> a manager with several
            points above the zero line has consistently won their trades - they're finding
            value other managers are giving away. Well below zero means the opposite; it's worth
            a look at whether they're trading need over value, or getting outmaneuvered.
        </p>
    </div>
    """
    calc_explanation_div = Div(text=calc_explanation_html, sizing_mode="stretch_width", max_width=1200, height_policy="auto")

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
            'trade_id': data['trade_ids'],
            'faab_note': data['faab_notes'],
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

        # Manager name next to every trade point - a real season's trade count is small enough
        # (this league: 16) that labeling each one stays readable, unlike Waiver Analysis's
        # hundreds of points. Always visible regardless of legend toggle state (see
        # power_rankings.py's create_power_rating_plot for why: a LabelSet can't be wired into
        # a Legend item's renderer list).
        p.add_layout(LabelSet(
            x='week', y='combined_impact', text='manager', source=source,
            x_offset=8, y_offset=6, text_font_size='9px', text_color=color,
            background_fill_color=SURFACE, background_fill_alpha=0.65,
        ))

    # Legend renders *inside* the plot frame (not as an outside 'right' panel) - a side panel
    # adds its own fixed pixel width alongside the frame, which sizing_mode="stretch_width"
    # can't compensate for, pushing the whole figure wider than a phone viewport.
    data_legend = Legend(items=data_legend_items, location="top_left",
                        title="Manager Trade History", click_policy="hide")
    data_legend.title_text_font_size = "11pt"
    data_legend.label_text_font_size = "10pt"
    style_legend(data_legend)
    p.add_layout(data_legend)
    show_legend_button = legend_toggle_button(data_legend)

    # Clean hover tool - simplified
    hover = HoverTool(tooltips=[
        ("Manager", "@manager"),
        ("Week", "@week{0}"),
        ("Trading Partner", "@other_manager"),
        ("Acquired Players", "@acquired"),
        ("Traded Away", "@gave_up"),
        ("Combined Impact (Net Player Value)", "@combined_impact{+0.1f}"),
        ("FAAB", "@faab_note"),
        ("Team Trend: Power (context only)", "@power_impact{+0.1f}"),
        ("Team Trend: Grade (context only)", "@grade_impact{+0.1f}")
    ])
    p.add_tools(hover)
    
    # Create control buttons
    toggle_data_button = Button(label="Toggle All Data", sizing_mode="stretch_width", height=44,
                                 stylesheets=[button_stylesheet("primary")])
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

    show_explanation_button = Button(label="Show Calculation Details", sizing_mode="stretch_width", height=44,
                                      stylesheets=[button_stylesheet("muted")])
    show_explanation_button.js_on_event("button_click", CustomJS(args=dict(explanation_div=explanation_div), code="""
        explanation_div.visible = !explanation_div.visible;
        if (explanation_div.visible) {
            explanation_div.height = 900;
            cb_obj.label = "Hide Calculation Details";
        } else {
            explanation_div.height = 0;
            cb_obj.label = "Show Calculation Details";
        }
    """))

    reset_button = Button(label="Reset Zoom", sizing_mode="stretch_width", height=44,
                           stylesheets=[button_stylesheet("ghost")])
    reset_button.js_on_event("button_click", CustomJS(args=dict(plot=p, x_end=last_week + 0.5), code="""
        plot.x_range.start = 0.5;
        plot.x_range.end = x_end;
        plot.y_range.start = -30;
        plot.y_range.end = 45;
    """))

    # Create layout
    # Chart and leaderboard stack vertically instead of sitting side by side - see
    # src/bokeh_mobile.py's module docstring for why this is done unconditionally in Python
    # rather than via a CSS media query targeting Bokeh's (version-fragile) internal layout
    # classes.
    main_content = bokeh_column(leaderboard_div, p, sizing_mode="stretch_width")
    # Bokeh's row() has no flex-wrap - 3 buttons in one stretch_width row overlap rather than
    # wrap on a narrow phone screen (confirmed by rendering and screenshotting at 375px), so
    # this grids them 2-per-row instead, the same "stack unconditionally" philosophy already
    # used for chart-vs-leaderboard layout (see src/bokeh_mobile.py).
    button_row = bokeh_column(
        bokeh_row(toggle_data_button, show_explanation_button, sizing_mode="stretch_width"),
        bokeh_row(reset_button, show_legend_button, sizing_mode="stretch_width"),
        sizing_mode="stretch_width",
    )

    # Description first, then the relocated buttons, then the data - explicit user request to
    # move the built-in controls instead of leaving them buried at the very bottom of the page.
    layout = bokeh_column(calc_explanation_div, button_row, explanation_div, main_content, sizing_mode="stretch_width")

    # Style the plot title (grid/axis colors already set by style_figure())
    p.title.text_font_size = "15pt"
    p.title.align = "center"
    
    show(layout)
    make_bokeh_html_mobile_friendly(plot_filename)
    print(f"\nEnhanced trade analysis plot saved as: {plot_filename}")
    print("Features: Individual transactions, clean hover data, worst trades report")
    print("Interactive: Manager legend, explanation panel, data toggles")
    return plot_filename


def create_waiver_visualization(waiver_impacts, output_dirs=None):
    """Create enhanced waiver wire analysis visualization with individual transactions and leaderboard"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import (ColumnDataSource, HoverTool, Legend, LegendItem,
                                Button, CustomJS, Div)
        from bokeh.layouts import column as bokeh_column, row as bokeh_row
        import numpy as np
        from src.bokeh_theme import (
            style_figure, style_legend, legend_toggle_button, button_stylesheet, dark_palette,
            SURFACE, SURFACE_RAISED, LINE, INK, INK_MUTED, ACCENT,
            PANEL_STYLE, CALLOUT_STYLE, HEADING_STYLE, DESCRIPTION_STYLE, LABEL_STYLE,
        )
    except ImportError:
        print("\n⚠️  Bokeh not available for waiver visualization")
        return
    
    if not waiver_impacts:
        print("\n⚠️  No waiver data for visualization")
        return

    # Real last analyzed week, not a hardcoded "assume 15 weeks" guess.
    last_week = max((impact['week'] for impact in waiver_impacts), default=15)

    if output_dirs:
        plot_filename = os.path.join(output_dirs['html'], "waiver_analysis.html")
    else:
        plot_filename = "waiver_analysis.html"
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
            'weeks_rostered': impact.get('weeks_rostered_scored', 0),
            'total_points': impact.get('total_points_while_rostered', 0.0),
            'combined_impact': impact['combined_impact'],
            'player_added': impact.get('player_added', 'Unknown'),
            'player_dropped': impact.get('player_dropped', 'None'),
            'transaction_type': impact.get('transaction_type', 'Waiver'),
            'faab_spent': impact.get('faab_spent'),
            'faab_aggressiveness_score': impact.get('faab_aggressiveness_score'),
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
                'weeks_rostered': [],
                'total_points': [],
                'combined_impacts': [],
                'players_added': [],
                'players_dropped': [],
                'transaction_types': [],
                'waiver_ids': [],
                'faab_labels': [],
            }

        # Add small jitter to prevent exact overlap
        week_jitter = waiver['week'] + np.random.uniform(-0.15, 0.15)

        manager_data[manager]['weeks'].append(week_jitter)
        manager_data[manager]['weeks_rostered'].append(waiver['weeks_rostered'])
        manager_data[manager]['total_points'].append(waiver['total_points'])
        manager_data[manager]['combined_impacts'].append(waiver['combined_impact'])
        manager_data[manager]['players_added'].append(waiver['player_added'])
        manager_data[manager]['players_dropped'].append(waiver['player_dropped'])
        manager_data[manager]['transaction_types'].append(waiver['transaction_type'])
        manager_data[manager]['waiver_ids'].append(waiver['waiver_id'])
        manager_data[manager]['faab_labels'].append(
            f"${waiver['faab_spent']:.0f} (aggressiveness {waiver['faab_aggressiveness_score']:.0f}/100)"
            if waiver.get('faab_spent') else 'No FAAB / not a FAAB league'
        )
    
    # Color mapping with legend (dark-optimized palette - see src/bokeh_theme.py)
    unique_managers = sorted(all_managers)
    colors_palette = dark_palette(len(unique_managers))
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
                'best_pickup_impact': float('-inf'),
                'total_faab_spent': 0.0,
            }

        manager_stats[manager]['total_waivers'] += 1
        manager_stats[manager]['total_impact'] += waiver['combined_impact']
        manager_stats[manager]['impacts'].append(waiver['combined_impact'])
        manager_stats[manager]['total_faab_spent'] += waiver.get('faab_spent') or 0.0

        if waiver['combined_impact'] > 0:
            manager_stats[manager]['positive_waivers'] += 1
        elif waiver['combined_impact'] < 0:
            manager_stats[manager]['negative_waivers'] += 1

        # Track best pickup
        if waiver['combined_impact'] > manager_stats[manager]['best_pickup_impact']:
            manager_stats[manager]['best_pickup_impact'] = waiver['combined_impact']
            manager_stats[manager]['best_pickup'] = waiver['player_added']

    # Create leaderboard data. $/impact efficiency and FAAB total are only meaningful in FAAB
    # leagues - they'll be $0.00/0.0 for leagues on rolling/priority waivers, which is a
    # correct (not broken) representation since no FAAB was ever spent there.
    leaderboard_data = []
    for manager, stats in manager_stats.items():
        avg_impact = stats['total_impact'] / stats['total_waivers'] if stats['total_waivers'] > 0 else 0
        success_rate = (stats['positive_waivers'] / stats['total_waivers'] * 100) if stats['total_waivers'] > 0 else 0
        faab_efficiency = (stats['total_impact'] / stats['total_faab_spent']) if stats['total_faab_spent'] > 0 else 0.0

        leaderboard_data.append([
            manager,
            f"{avg_impact:+.2f}",
            f"{stats['total_impact']:+.1f}",
            str(stats['total_waivers']),
            f"{success_rate:.1f}%",
            stats['best_pickup'] or 'None',
            # avg_impact is a position-adjusted z-score now, so +-1 here is a literal +-1
            # standard deviation from the position's weekly average - still a sensible
            # "clearly above/below average" cutoff for the trend arrow.
            "📈" if avg_impact > 1 else "📉" if avg_impact < -1 else "➡️",
            f"${stats['total_faab_spent']:.0f}",
            f"{faab_efficiency:+.2f}" if stats['total_faab_spent'] > 0 else "-",
        ])
    
    # Sort by average impact
    leaderboard_data.sort(key=lambda x: float(x[1]), reverse=True)
    for i, row in enumerate(leaderboard_data):
        row.insert(0, str(i + 1))  # Add ranking
    
    # Create main plot
    p = figure(
        width=1200,
        height=700,
        sizing_mode="stretch_width",
        title="Waiver Wire & Free Agent Analysis: Individual Transaction Impact",
        x_axis_label="Week",
        y_axis_label="Position-Adjusted Score (std. deviations vs. position average)",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        x_range=(0.5, last_week + 0.5),
        y_range=(-4, 4)
    )
    style_figure(p)

    # Add zero reference line
    p.line([0.5, last_week + 0.5], [0, 0], line_color=LINE, line_width=1, line_dash='dashed', alpha=0.8)
    
    # Create collapsible explanation panel
    explanation_text = f"""
    <div style="{PANEL_STYLE}">
        <h3 style="{HEADING_STYLE}">Waiver Wire Impact Analysis Methodology</h3>
        <h4 style="{HEADING_STYLE}font-size:15px;">Data Collection &amp; Processing</h4>
        <p style="{LABEL_STYLE}"><strong>Transaction Detection:</strong> All waiver claims and free agent pickups identified</p>
        <p style="{LABEL_STYLE}"><strong>Individual Transactions:</strong> Each transaction (all players it added) shown as one data point, not one per player</p>
        <p style="{LABEL_STYLE}"><strong>Transaction Types:</strong> Waiver claims and free agent pickups tracked (trades are scored separately)</p>
        <p style="{LABEL_STYLE}"><strong>Rostered Window:</strong> The pickup's actual fantasy points are tracked from the week they were added through the week before you dropped them (or traded them away), or the end of the analyzed season if you never gave them up</p>

        <h4 style="{HEADING_STYLE}font-size:15px;margin-top:15px;">Impact Calculation Formula</h4>
        <p style="{LABEL_STYLE}"><strong>Position Baseline:</strong> Every rostered player's actual points at a given position, league-wide, for a given week</p>
        <p style="{LABEL_STYLE}"><strong>Weekly Score:</strong> The pickup's points that week, expressed as a z-score (standard deviations) against that week's position baseline</p>
        <p style="{LABEL_STYLE}"><strong>Position-Adjusted Score:</strong> The average of those weekly z-scores across every week you had them rostered</p>
        <p style="{LABEL_STYLE}"><strong>Why position-adjusted:</strong> A QB and a TE score on very different raw-point scales - z-scores make a great TE pickup comparable to a great RB pickup</p>

        <h4 style="{HEADING_STYLE}font-size:15px;margin-top:15px;">Impact Scale &amp; Interpretation</h4>
        <p style="{LABEL_STYLE}"><strong>Elite Pickup (+1.5 or higher):</strong> Consistently well above the average rostered player at their position</p>
        <p style="{LABEL_STYLE}"><strong>Good Pickup (+0.5 to +1.5):</strong> Solidly above average while rostered</p>
        <p style="{LABEL_STYLE}"><strong>Neutral Pickup (-0.5 to +0.5):</strong> Performed like a typical rostered player at that position</p>
        <p style="{LABEL_STYLE}"><strong>Poor Pickup (-1.5 to -0.5):</strong> Below average while rostered</p>
        <p style="{LABEL_STYLE}"><strong>Bust (below -1.5):</strong> Well below the position's average - likely dead roster weight</p>

        <h4 style="{HEADING_STYLE}font-size:15px;margin-top:15px;">Technical Features</h4>
        <p style="{LABEL_STYLE}"><strong>Hover Details:</strong> Manager, players involved, weeks rostered, points scored, and the position-adjusted score</p>
        <p style="{LABEL_STYLE}"><strong>Color Legend:</strong> Each manager assigned unique color</p>
        <p style="{LABEL_STYLE}"><strong>Transaction Separation:</strong> Overlapping pickups separated for visibility</p>
        <p style="{LABEL_STYLE}"><strong>Best Pickups Tracking:</strong> Leaderboard shows top waiver wire successes</p>
    </div>
    """

    explanation_div = Div(text=explanation_text, sizing_mode="stretch_width", max_width=1200, height=0, visible=False)

    # Create leaderboard
    leaderboard_html = f"""
    <h3 style="{HEADING_STYLE}">Waiver Wire Performance Leaderboard</h3>
    <table style="border-collapse: collapse; width: 100%; font-size: 13px; margin: 5px 0; color: {INK};">
    <tr style="background-color: {SURFACE_RAISED};">
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">#</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: left; color: {INK_MUTED};">Manager</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Avg Impact</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Total Gain</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Total Moves</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Success Rate</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: left; color: {INK_MUTED};">Best Pickup</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Trend</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">FAAB Spent</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Impact/$</th>
    </tr>
    """

    for row in leaderboard_data:
        rank = int(row[0])
        row_bg = SURFACE if rank % 2 == 0 else "transparent"
        rank_color = ACCENT if rank <= 3 else INK
        leaderboard_html += f"""
        <tr style="background-color: {row_bg};">
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; font-weight: 700; color: {rank_color};">{row[0]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px;">{row[1]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center;">{row[2]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center;">{row[3]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">{row[4]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">{row[5]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px;">{row[6]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center;">{row[7]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">{row[8]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">{row[9]}</td>
        </tr>"""

    leaderboard_html += f"""
    </table>
    <div style="margin-top: 10px; font-size: 12px; color: {INK_MUTED};">
        <strong>Legend:</strong> Avg Impact = average position-adjusted z-score per waiver move (std. deviations vs. the position's weekly average) &middot;
        Total Gain = sum of all pickups' position-adjusted scores &middot; Success Rate = % of moves with a positive score &middot;
        Best Pickup = highest-scoring player acquired &middot; FAAB Spent/Impact per $ only populate in leagues on FAAB bidding
    </div>
    """
    # Wrapped in the leaderboard's own HTML (not an external stylesheet) because Bokeh 3.x
    # renders every Div inside a shadow root that external CSS can't reach - see
    # src/bokeh_mobile.py's module docstring for how this was confirmed empirically. Width is
    # `100vw`, not `100%`: the wrapper's real parent (Bokeh's own `.bk-clearfix`, also inside
    # the shadow root) is `display: inline-block` and shrinks to fit its content, so a
    # percentage width has no real containing block to resolve against and just falls back to
    # the table's own natural (too-wide) size - confirmed by measuring the actual rendered
    # boxes. Viewport units don't have that circularity, and since this Div always ends up
    # spanning the full stacked-column width (see the row-to-column fix above), the viewport
    # width is the right proxy for "however much horizontal room this report actually has".
    leaderboard_div = Div(
        text=f'<div style="display:block;width:100vw;overflow-x:auto;-webkit-overflow-scrolling:touch;background-color:{SURFACE};border:1px solid {LINE};border-radius:16px;padding:16px 18px;box-sizing:border-box;">{leaderboard_html}</div>',
        sizing_mode="stretch_width", max_width=600, height_policy="auto"
    )

    # Create calculation explanation panel (always visible - larger, higher-contrast
    # description text sits at the top of the page, explicit user request)
    calc_explanation_html = f"""
    <h3 style="{HEADING_STYLE}">How Waiver Wire Impact Is Calculated</h3>
    <div style="{CALLOUT_STYLE}">
        <p style="{DESCRIPTION_STYLE}"><strong>Step 1:</strong> Find the weeks the pickup was actually rostered - from the week added through the week before you dropped or traded them (or the end of the season if you kept them)</p>
        <p style="{DESCRIPTION_STYLE}"><strong>Step 2:</strong> For each of those weeks, look up their actual fantasy points scored</p>
        <p style="{DESCRIPTION_STYLE}"><strong>Step 3:</strong> Compare that to every rostered player at the same position, league-wide, that same week (the mean and spread)</p>
        <p style="{DESCRIPTION_STYLE}"><strong>Step 4:</strong> Weekly Score = (their points - position mean) / position standard deviation, that week</p>
        <p style="{DESCRIPTION_STYLE}"><strong>Step 5:</strong> Position-Adjusted Score = the average of every Weekly Score across the weeks they were rostered</p>
        <p style="{DESCRIPTION_STYLE} margin-top: 8px; font-style: italic;">Positive values mean the pickup outperformed a typical rostered player at their position while you had them; negative values mean they underperformed</p>
        <p style="{DESCRIPTION_STYLE} margin-top: 8px;">
            <strong style="color:{ACCENT};">What this means:</strong> a manager showing up here
            often with positive scores has a good eye for the waiver wire - they're finding
            usable players before anyone else notices. A pile of pickups near zero or negative
            means those roster spots probably weren't worth the churn.
        </p>
    </div>
    """
    calc_explanation_div = Div(text=calc_explanation_html, sizing_mode="stretch_width", max_width=1200, height_policy="auto")

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
            'weeks_rostered': data['weeks_rostered'],
            'total_points': data['total_points'],
            'combined_impact': data['combined_impacts'],
            'player_added': data['players_added'],
            'player_dropped': data['players_dropped'],
            'transaction_type': data['transaction_types'],
            'manager': [manager] * len(data['weeks']),
            'waiver_id': data['waiver_ids'],
            'faab_label': data['faab_labels'],
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

    # Legend renders *inside* the plot frame (not as an outside 'right' panel) - see
    # create_trade_visualization above for why: a side panel adds its own fixed pixel width
    # alongside the frame, pushing the whole figure wider than a phone viewport.
    data_legend = Legend(items=data_legend_items, location="top_left",
                        title="Manager Waiver Activity", click_policy="hide")
    data_legend.title_text_font_size = "11pt"
    data_legend.label_text_font_size = "10pt"
    style_legend(data_legend)
    p.add_layout(data_legend)
    show_legend_button = legend_toggle_button(data_legend)
    
    # Clean hover tool
    hover = HoverTool(tooltips=[
        ("Manager", "@manager"),
        ("Week", "@week{0}"),
        ("Transaction Type", "@transaction_type"),
        ("Player Added", "@player_added"),
        ("Player Dropped", "@player_dropped"),
        ("Weeks Rostered", "@weeks_rostered"),
        ("Points While Rostered", "@total_points{0.1f}"),
        ("Position-Adjusted Score", "@combined_impact{+0.2f}"),
        ("FAAB", "@faab_label"),
    ])
    p.add_tools(hover)
    
    # Create control buttons
    toggle_data_button = Button(label="Toggle All Data", sizing_mode="stretch_width", height=44,
                                 stylesheets=[button_stylesheet("primary")])
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

    show_explanation_button = Button(label="Show Calculation Details", sizing_mode="stretch_width", height=44,
                                      stylesheets=[button_stylesheet("muted")])
    show_explanation_button.js_on_event("button_click", CustomJS(args=dict(explanation_div=explanation_div), code="""
        explanation_div.visible = !explanation_div.visible;
        if (explanation_div.visible) {
            explanation_div.height = 900;
            cb_obj.label = "Hide Calculation Details";
        } else {
            explanation_div.height = 0;
            cb_obj.label = "Show Calculation Details";
        }
    """))

    reset_button = Button(label="Reset Zoom", sizing_mode="stretch_width", height=44,
                           stylesheets=[button_stylesheet("ghost")])
    reset_button.js_on_event("button_click", CustomJS(args=dict(plot=p, x_end=last_week + 0.5), code="""
        plot.x_range.start = 0.5;
        plot.x_range.end = x_end;
        plot.y_range.start = -4;
        plot.y_range.end = 4;
    """))

    # Create layout
    # Chart and leaderboard stack vertically instead of sitting side by side - see
    # src/bokeh_mobile.py's module docstring for why this is done unconditionally in Python
    # rather than via a CSS media query targeting Bokeh's (version-fragile) internal layout
    # classes.
    main_content = bokeh_column(leaderboard_div, p, sizing_mode="stretch_width")
    # Bokeh's row() has no flex-wrap - 3 buttons in one stretch_width row overlap rather than
    # wrap on a narrow phone screen (confirmed by rendering and screenshotting at 375px), so
    # this grids them 2-per-row instead, the same "stack unconditionally" philosophy already
    # used for chart-vs-leaderboard layout (see src/bokeh_mobile.py).
    button_row = bokeh_column(
        bokeh_row(toggle_data_button, show_explanation_button, sizing_mode="stretch_width"),
        bokeh_row(reset_button, show_legend_button, sizing_mode="stretch_width"),
        sizing_mode="stretch_width",
    )

    # Description first, then the relocated buttons, then the data - explicit user request to
    # move the built-in controls instead of leaving them at the very bottom of the page.
    layout = bokeh_column(calc_explanation_div, button_row, explanation_div, main_content, sizing_mode="stretch_width")

    # Style the plot title (grid/axis colors already set by style_figure())
    p.title.text_font_size = "15pt"
    p.title.align = "center"
    
    show(layout)
    make_bokeh_html_mobile_friendly(plot_filename)
    print(f"\nWaiver analysis plot saved as: {plot_filename}")
    print("Features: Individual transactions, clean hover data, best pickups leaderboard")
    print("Interactive: Manager legend, explanation panel, data toggles")
    return plot_filename


def create_manager_grade_visualization(manager_grades, output_dirs=None):
    """Create comprehensive manager grade visualization with enhanced features"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import ColumnDataSource, HoverTool, Legend, Button, CustomJS, Div, DataTable, TableColumn, LabelSet
        from bokeh.layouts import column as bokeh_column, row as bokeh_row
        from sklearn.linear_model import LinearRegression
        import numpy as np
        from src.bokeh_theme import (
            style_figure, style_legend, legend_toggle_button, button_stylesheet, dark_palette,
            SURFACE, SURFACE_RAISED, LINE, INK, INK_MUTED, ACCENT,
            PANEL_STYLE, CALLOUT_STYLE, HEADING_STYLE, DESCRIPTION_STYLE, LABEL_STYLE,
        )
    except ImportError:
        print("\n⚠️  Bokeh or scikit-learn not available for manager grade visualization")
        return
    
    if not manager_grades:
        print("\n⚠️  No manager grade data for visualization")
        return

    # Real last analyzed week, not a hardcoded "assume 15 weeks" guess.
    last_week = max(
        (int(w) for data in manager_grades.values() for w in data.get('weekly_grades', {})),
        default=15
    )

    if output_dirs:
        plot_filename = os.path.join(output_dirs['html'], "manager_grades.html")
    else:
        plot_filename = "manager_grades.html"
    output_file(plot_filename)
    
    # Enhanced data preparation with better scaling (dark-optimized palette - see src/bokeh_theme.py)
    colors = dark_palette(len(manager_grades))
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
            
            # Extend trend line through the real last analyzed week
            trend_weeks = list(range(min(weeks), last_week + 1))
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
        sizing_mode="stretch_width",
        title="Manager Performance Grades: Enhanced Weekly Analysis",
        x_axis_label="Week",
        y_axis_label="Manager Grade (0-10 Scale)",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        x_range=(0.5, last_week + 0.5),
        y_range=(0, 10)
    )
    style_figure(p)
    
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
    
    for i, team in enumerate(team_data):
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

        # Manager name next to the most recent point only (see power_rankings.py's
        # create_power_rating_plot for why not every week). Always visible regardless of
        # legend toggle state - a LabelSet can't be wired into a Legend item's renderer list.
        last_point_source = ColumnDataSource(data={
            'week': [team['source'].data['week'][-1]],
            'grade': [team['source'].data['grade'][-1]],
            'name': [team['name']],
        })
        # Anchored to the right of the label (x_offset negative, text_align right) so the text
        # extends back toward the chart instead of off its right edge, where the season's final
        # week - and therefore every one of these labels - sits. y_offset cycles per manager
        # since every label shares that same final week and would otherwise stack on top of
        # each other for managers with a similar current grade.
        p.add_layout(LabelSet(
            x='week', y='grade', text='name', source=last_point_source,
            x_offset=-8, y_offset=[8, -20, 18, -32][i % 4], text_align='right',
            text_font_size='9px', text_color=team['color'],
            background_fill_color=SURFACE, background_fill_alpha=0.65,
        ))

        data_legend_items.append((f"{team['name']} ({team['enhanced_overall']:.1f})", [scatter, line]))
    
    # Legends render *inside* the plot frame (not as outside side panels) - a side panel adds
    # its own fixed pixel width alongside the frame, pushing the whole figure wider than a
    # phone viewport (see create_trade_visualization above for the same fix).
    data_legend = Legend(items=data_legend_items, location="top_left", title="Managers", click_policy="hide")
    style_legend(data_legend)
    p.add_layout(data_legend)

    if trend_legend_items:
        trend_legend = Legend(items=trend_legend_items, location="bottom_right", title="Trends", click_policy="hide")
        style_legend(trend_legend)
        p.add_layout(trend_legend)
        show_legend_button = legend_toggle_button(data_legend, trend_legend)
    else:
        show_legend_button = legend_toggle_button(data_legend)
    
    # Create leaderboard table
    leaderboard_html = f"""
    <h3 style="{HEADING_STYLE}">Manager Performance Leaderboard</h3>
    <table style="border-collapse: collapse; width: 100%; font-size: 13px; color: {INK};">
    <tr style="background-color: {SURFACE_RAISED};">
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">#</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: left; color: {INK_MUTED};">Manager</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Grade</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Trend</th>
        <th style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">Direction</th>
    </tr>
    """

    for row in leaderboard_data:
        row_bg = SURFACE if row[0] % 2 == 0 else "transparent"
        rank_color = ACCENT if row[0] <= 3 else INK
        leaderboard_html += f"""
        <tr style="background-color: {row_bg};">
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; font-weight: 700; color: {rank_color};">{row[0]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px;">{row[1]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; font-weight: 700;">{row[2]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center; color: {INK_MUTED};">{row[3]}</td>
            <td style="border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: center;">{row[4]}</td>
        </tr>"""

    leaderboard_html += "</table>"
    # Wrapped in the leaderboard's own HTML (not an external stylesheet) because Bokeh 3.x
    # renders every Div inside a shadow root that external CSS can't reach - see
    # src/bokeh_mobile.py's module docstring for how this was confirmed empirically. Width is
    # `100vw`, not `100%`: the wrapper's real parent (Bokeh's own `.bk-clearfix`, also inside
    # the shadow root) is `display: inline-block` and shrinks to fit its content, so a
    # percentage width has no real containing block to resolve against and just falls back to
    # the table's own natural (too-wide) size - confirmed by measuring the actual rendered
    # boxes. Viewport units don't have that circularity, and since this Div always ends up
    # spanning the full stacked-column width (see the row-to-column fix above), the viewport
    # width is the right proxy for "however much horizontal room this report actually has".
    leaderboard_div = Div(
        text=f'<div style="display:block;width:100vw;overflow-x:auto;-webkit-overflow-scrolling:touch;background-color:{SURFACE};border:1px solid {LINE};border-radius:16px;padding:16px 18px;box-sizing:border-box;">{leaderboard_html}</div>',
        sizing_mode="stretch_width", max_width=500, height_policy="auto"
    )

    # Create explanation panel (always visible - larger, higher-contrast description text,
    # explicit user request)
    explanation_text = f"""
    <div style="{PANEL_STYLE}">
        <h3 style="{HEADING_STYLE}">Manager Performance Grading Methodology</h3>
        <p style="{DESCRIPTION_STYLE}">
            Every manager gets a 0-10 overall grade blending four weighted components:
            <strong>performance</strong> (40% - weekly scores relative to league average plus
            consistency), <strong>trade analysis</strong> (25% - net impact of every trade),
            <strong>waiver analysis</strong> (20% - success rate and impact of pickups), and
            <strong>start/sit accuracy</strong> (15% - optimal lineup decisions vs. actual ones).
        </p>
        <p style="{LABEL_STYLE} margin-top: 8px;"><strong>Grade Scale:</strong> 8-10 Elite &middot; 6-8 Above Average &middot; 4-6 Average &middot; 2-4 Below Average &middot; 0-2 Poor</p>
        <p style="{LABEL_STYLE}"><strong>Trend Analysis:</strong> Linear regression showing management skill development trajectory</p>
        <p style="{DESCRIPTION_STYLE} margin-top: 8px;">
            <strong style="color:{ACCENT};">What this means:</strong> this grades how well a
            manager has <em>played</em> the game overall - lineup decisions, trades, and waivers
            combined - not just their win-loss record. A manager with a mediocre record but a
            high grade is doing the right things and should turn it around; a good record with a
            low grade suggests they're winning in spite of their own decisions.
        </p>
    </div>
    """

    explanation_div = Div(text=explanation_text, sizing_mode="stretch_width", max_width=1200, height_policy="auto")

    # Toggle controls, relocated above the chart - explicit user request to move the built-in
    # buttons instead of leaving them at the very bottom of the page
    toggle_managers_button = Button(label="Toggle All Data", sizing_mode="stretch_width", height=44,
                                     stylesheets=[button_stylesheet("primary")])
    toggle_trends_button = Button(label="Toggle All Trends", sizing_mode="stretch_width", height=44,
                                   stylesheets=[button_stylesheet("ghost")])
    reset_zoom_button = Button(label="Reset Zoom", sizing_mode="stretch_width", height=44,
                                stylesheets=[button_stylesheet("ghost")])
    
    # JavaScript callbacks
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
    
    reset_callback = CustomJS(args=dict(plot=p, x_end=last_week + 0.5), code="""
        plot.x_range.start = 0.5;
        plot.x_range.end = x_end;
        plot.y_range.start = 0;
        plot.y_range.end = 10;
    """)
    
    toggle_managers_button.js_on_click(managers_callback)
    toggle_trends_button.js_on_click(trends_callback)
    reset_zoom_button.js_on_click(reset_callback)

    # Leaderboard stacks above the plot instead of sitting side by side - see
    # src/bokeh_mobile.py's module docstring for why this is done unconditionally in Python
    # rather than via a CSS media query targeting Bokeh's (version-fragile) internal layout
    # classes.
    main_content = bokeh_column(leaderboard_div, p, spacing=10, sizing_mode="stretch_width")
    # Bokeh's row() has no flex-wrap - 3 buttons in one stretch_width row overlap rather than
    # wrap on a narrow phone screen (confirmed by rendering and screenshotting at 375px), so
    # this grids them 2-per-row instead.
    control_row = bokeh_column(
        bokeh_row(toggle_managers_button, toggle_trends_button, sizing_mode="stretch_width"),
        bokeh_row(reset_zoom_button, show_legend_button, sizing_mode="stretch_width"),
        sizing_mode="stretch_width",
    )

    # Description first, then the relocated buttons, then the data - explicit user request to
    # move the built-in controls instead of leaving them at the very bottom of the page.
    layout = bokeh_column(explanation_div, control_row, main_content, spacing=5, sizing_mode="stretch_width")

    show(layout)
    make_bokeh_html_mobile_friendly(plot_filename)

    print(f"\nManager grades analysis saved as: {plot_filename}")
    print(f"   Features: Enhanced calculations, leaderboard, toggleable explanation")
    print(f"   Interactive: Working toggles, proper hover data, trend analysis") 
    return plot_filename


def create_worst_trades_html_report(worst_trades, output_dirs=None):
    """Create an HTML report for the worst trades analysis"""
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Worst Trades Report - Fantasy Football Analysis</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        /* Dark "broadcast scoreboard" theme (2026-09) - kept in sync with index.html and
           src/ai_overview.py's generated CSS, so every report page matches the homepage. This
           page is hand-authored HTML (not Bokeh), so plain CSS applies with no shadow-DOM
           caveats - see src/bokeh_mobile.py's module docstring for why every *other* report in
           this file needs a different mechanism (src/bokeh_theme.py) instead. */
        html {{
            overflow-x: hidden;
        }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background: #070D18;
            color: #F4F6FA;
            min-height: 100vh;
            overflow-x: hidden;
            -webkit-font-smoothing: antialiased;
        }}
        h1, h2, h3, h4, h5 {{ font-family: 'Oswald', 'Arial Narrow', sans-serif; font-weight: 600; }}
        /* A trades-table wider than its card (long comma-joined player-name cells) scrolls in
           place within this wrapper instead of forcing the whole page to scroll sideways. */
        .table-scroll {{
            max-width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: #101B2D;
            border: 1px solid #22344E;
            border-radius: 20px;
            padding: 30px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 22px 20px;
            background: linear-gradient(135deg, #18283F, #101B2D);
            border: 1px solid #22344E;
            border-radius: 16px;
            color: #F4F6FA;
        }}
        .header h1 {{
            color: #F4F6FA;
            margin: 0;
            font-size: 2em;
        }}
        .header p {{
            color: #8DA0BC;
            margin: 10px 0 0 0;
            font-size: 1.1em;
        }}
        .methodology {{
            background: #18283F;
            border-left: 5px solid #FF6A2B;
            padding: 15px 20px;
            margin: 20px 0;
            border-radius: 12px;
        }}
        .methodology h3 {{
            color: #F4F6FA;
            margin-top: 0;
        }}
        .methodology li {{
            color: #8DA0BC;
            font-size: 16px;
            line-height: 1.55;
        }}
        .trades-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
            border: 1px solid #22344E;
            border-radius: 10px;
            overflow: hidden;
        }}
        .trades-table th {{
            background: #18283F;
            color: #8DA0BC;
            font-weight: 700;
            padding: 15px 10px;
            text-align: left;
        }}
        .trades-table td {{
            padding: 12px 10px;
            border-bottom: 1px solid #22344E;
            color: #F4F6FA;
        }}
        .trades-table tr:hover {{
            background: #18283F;
        }}
        .rank-1 {{
            background: rgba(255, 106, 43, 0.16);
            font-weight: bold;
        }}
        .rank-2 {{
            background: rgba(255, 106, 43, 0.11);
        }}
        .rank-3 {{
            background: rgba(255, 106, 43, 0.07);
        }}
        .impact-negative {{
            color: #F87171;
            font-weight: bold;
        }}
        .impact-positive {{
            color: #34D399;
            font-weight: bold;
        }}
        .detailed-section {{
            margin: 40px 0;
        }}
        .trade-card {{
            background: #18283F;
            border: 1px solid #22344E;
            border-radius: 14px;
            padding: 20px;
            margin: 15px 0;
        }}
        .trade-card h4 {{
            color: #FF6A2B;
            margin-top: 0;
            font-size: 1.3em;
        }}
        .trade-details {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 15px;
        }}
        .players-section {{
            background: #101B2D;
            padding: 15px;
            border-radius: 10px;
        }}
        .players-section h5 {{
            margin-top: 0;
            color: #F4F6FA;
        }}
        .impact-stats {{
            display: flex;
            justify-content: space-around;
            margin: 15px 0;
            text-align: center;
        }}
        .stat {{
            background: #101B2D;
            padding: 10px;
            border-radius: 10px;
            flex: 1;
            margin: 0 5px;
        }}
        .stat .label {{
            font-size: 0.9em;
            color: #8DA0BC;
        }}
        .stat .value {{
            font-size: 1.2em;
            font-weight: bold;
            color: #F4F6FA;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #22344E;
            color: #8DA0BC;
        }}
        @media (max-width: 768px) {{
            .container {{
                padding: 15px;
            }}
            .trades-table {{
                font-size: 12px;
            }}
            .trades-table th, .trades-table td {{
                padding: 8px 5px;
            }}
            .trade-details {{
                grid-template-columns: 1fr;
            }}
            .impact-stats {{
                flex-wrap: wrap;
            }}
            .stat {{
                flex: 1 1 40%;
                margin: 5px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Worst Trades Report</h1>
            <p>Fantasy Football Analysis - Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
        </div>
        
        <div class="methodology">
            <h3>Methodology</h3>
            <ul>
                <li><strong>Combined Impact</strong> = Net Player Value = Value Acquired − Value Given Up</li>
                <li><strong>Player value</strong> comes from ESPN's season stat-leader tiers (~1-10 scale per player)</li>
                <li><strong>Negative values</strong> mean this manager gave up more value than they received</li>
                <li><strong>Rankings</strong> based on most negative Combined Impact</li>
                <li><strong>Power/Grade Impact</strong> below are supplementary context only (this manager's team-wide trend around the trade date) - not part of the Combined Impact score</li>
                <li><strong>FAAB</strong> shown when the trade also included a FAAB budget transfer</li>
            </ul>
        </div>

        <h2>Top 10 Worst Trades (Net Player Value)</h2>
        <div class="table-scroll">
        <table class="trades-table">
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Manager</th>
                    <th>Week</th>
                    <th>Combined Impact</th>
                    <th>Acquired Players</th>
                    <th>Gave Up Players</th>
                    <th>Trading Partner</th>
                </tr>
            </thead>
            <tbody>
"""

    # Add top 10 worst trades to table
    for i, trade in enumerate(worst_trades[:10]):
        rank_class = f"rank-{min(i+1, 3)}"
        impact_class = "impact-negative" if trade['combined_impact'] < 0 else "impact-positive"

        html_content += f"""
                <tr class="{rank_class}">
                    <td>#{i+1}</td>
                    <td><strong>{trade['manager']}</strong></td>
                    <td>{trade['week']}</td>
                    <td class="{impact_class}">{trade['combined_impact']:+.1f}</td>
                    <td>{trade['acquired']}</td>
                    <td>{trade['gave_up']}</td>
                    <td>{trade['other_manager']}</td>
                </tr>"""

    html_content += """
            </tbody>
        </table>
        </div>

        <div class="detailed-section">
            <h2>Detailed Breakdown</h2>
"""

    # Add detailed breakdown cards for top 10
    for i, trade in enumerate(worst_trades[:10]):
        impact_color = "#C0392B" if trade['combined_impact'] < 0 else "#1B8A5A"

        html_content += f"""
            <div class="trade-card">
                <h4>#{i+1} - {trade['manager']} (Week {trade['week']})</h4>

                <div class="impact-stats">
                    <div class="stat">
                        <div class="label">Combined Impact (Net Player Value)</div>
                        <div class="value" style="color: {impact_color}">{trade['combined_impact']:+.1f}</div>
                    </div>
                    <div class="stat">
                        <div class="label">Team Trend: Power</div>
                        <div class="value">{trade['power_impact']:+.1f}</div>
                    </div>
                    <div class="stat">
                        <div class="label">Team Trend: Grade</div>
                        <div class="value">{trade['grade_impact']:+.1f}</div>
                    </div>
                    <div class="stat">
                        <div class="label">FAAB</div>
                        <div class="value">{trade.get('faab_note', 'No FAAB')}</div>
                    </div>
                </div>

                <div class="trade-details">
                    <div class="players-section">
                        <h5>📥 Acquired Players</h5>
                        <p>{trade['acquired']}</p>
                    </div>
                    <div class="players-section">
                        <h5>📤 Gave Up Players</h5>
                        <p>{trade['gave_up']}</p>
                    </div>
                </div>
                
                <p style="text-align: center; margin-top: 15px;">
                    <strong>Trading Partner:</strong> {trade['other_manager']}
                </p>
            </div>"""

    # Add Power Impact Rankings
    power_sorted = sorted(worst_trades, key=lambda x: x['power_impact'])
    html_content += f"""
        </div>

        <div class="detailed-section">
            <h2>Worst Power Impact Trades</h2>
            <p style="text-align: center; color: #52607A; margin-bottom: 20px;">
                Trades ranked by most negative impact on weekly scoring potential
            </p>
            <div class="table-scroll">
            <table class="trades-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Manager</th>
                        <th>Week</th>
                        <th>Power Impact</th>
                        <th>Acquired Players</th>
                        <th>Gave Up Players</th>
                        <th>Trading Partner</th>
                    </tr>
                </thead>
                <tbody>"""

    for i, trade in enumerate(power_sorted[:10]):
        rank_class = f"rank-{min(i+1, 3)}"
        impact_class = "impact-negative" if trade['power_impact'] < 0 else "impact-positive"
        
        html_content += f"""
                    <tr class="{rank_class}">
                        <td>#{i+1}</td>
                        <td><strong>{trade['manager']}</strong></td>
                        <td>{trade['week']}</td>
                        <td class="{impact_class}">{trade['power_impact']:+.1f}</td>
                        <td>{trade['acquired']}</td>
                        <td>{trade['gave_up']}</td>
                        <td>{trade['other_manager']}</td>
                    </tr>"""

    # Add Roster Grade Impact Rankings
    grade_sorted = sorted(worst_trades, key=lambda x: x['grade_impact'])
    html_content += f"""
                </tbody>
            </table>
            </div>
        </div>

        <div class="detailed-section">
            <h2>Worst Roster Grade Impact Trades</h2>
            <p style="text-align: center; color: #52607A; margin-bottom: 20px;">
                Trades ranked by most negative impact on roster construction quality
            </p>
            <div class="table-scroll">
            <table class="trades-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Manager</th>
                        <th>Week</th>
                        <th>Grade Impact</th>
                        <th>Acquired Players</th>
                        <th>Gave Up Players</th>
                        <th>Trading Partner</th>
                    </tr>
                </thead>
                <tbody>"""

    for i, trade in enumerate(grade_sorted[:10]):
        rank_class = f"rank-{min(i+1, 3)}"
        impact_class = "impact-negative" if trade['grade_impact'] < 0 else "impact-positive"
        
        html_content += f"""
                    <tr class="{rank_class}">
                        <td>#{i+1}</td>
                        <td><strong>{trade['manager']}</strong></td>
                        <td>{trade['week']}</td>
                        <td class="{impact_class}">{trade['grade_impact']:+.1f}</td>
                        <td>{trade['acquired']}</td>
                        <td>{trade['gave_up']}</td>
                        <td>{trade['other_manager']}</td>
                    </tr>"""

    html_content += """
                </tbody>
            </table>
            </div>
        </div>"""

    html_content += f"""
        </div>

        <div class="footer">
            <p>Analysis based on {len(worst_trades)} total trades</p>
            <p>Report generated by Fantasy Football Analysis Engine</p>
        </div>
    </div>
</body>
</html>"""
    
    return html_content


def print_trade_analysis_results(trade_impacts, waiver_impacts=None, combined_impacts=None):
    """Print comprehensive analysis results"""
    print("\n" + "="*65)
    print("COMPREHENSIVE FANTASY ANALYSIS RESULTS")
    print("="*65)
    
    if trade_impacts:
        print(f"\nTrade Analysis Summary:")
        print(f"   • Total Real Trades Analyzed: {len(trade_impacts)}")
        print(f"   • Average Trade Impact: {statistics.mean([t['combined_impact'] for t in trade_impacts]):+.1f}")
        
        # Top trades
        sorted_trades = sorted(trade_impacts, key=lambda x: abs(x['combined_impact']), reverse=True)[:5]
        print(f"\n   Most Impactful Trades:")
        for i, trade in enumerate(sorted_trades, 1):
            impact_type = "📈" if trade['combined_impact'] > 0 else "📉"
            print(f"   {i}. Week {trade['week']} - {trade['manager_name']}")
            print(f"      {impact_type} Combined Impact: {trade['combined_impact']:+.1f}")
            print(f"      Got: {', '.join(trade['acquired_players'])}")
            print(f"      Gave: {', '.join(trade['gave_up_players'])}")
    
    if waiver_impacts:
        print(f"\nWaiver Wire Analysis Summary:")
        print(f"   • Total Waiver Moves Analyzed: {len(waiver_impacts)}")
        print(f"   • Average Waiver Impact: {statistics.mean([w['combined_impact'] for w in waiver_impacts]):+.1f}")
    
    print("\n" + "="*65)