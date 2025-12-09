#!/usr/bin/env python3
"""
Roster Grading Module
Handles ESPN-based player ranking and roster analysis
"""

import statistics
from datetime import datetime
from typing import Dict, List, Optional


class FantasyAnalyzer:
    """Analyzes fantasy football data and provides grades"""
    
    # Position rankings and expectations - Extended for deeper fantasy relevance
    POSITION_TIERS = {
        'QB': {
            'elite': [1, 2, 3, 4],      # Top-tier QBs (MVP candidates)
            'solid': [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],  # Reliable starters
            'streamer': [17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]  # Streamable/backup QBs
        },
        'RB': {
            'elite': [1, 2, 3, 4, 5, 6, 7, 8],  # Workhorse backs with volume
            'solid': [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30],  # Startable RBs
            'flex': [31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60]  # Depth/handcuffs
        },
        'WR': {
            'elite': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],  # Alpha WR1s
            'solid': [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36],  # WR2/3 with targets
            'flex': [37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70]  # Depth/bye week fills
        },
        'TE': {
            'elite': [1, 2, 3, 4],      # Elite fantasy TEs (rare commodities)
            'solid': [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],  # Startable TEs
            'streamer': [19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]  # Waiver wire TEs
        }
    }
    
    def __init__(self, espn_api):
        self.espn_api = espn_api
        self.position_rankings = {}
        self.nfl_leaders = None
    
    def initialize_rankings(self, season="2025"):
        """Initialize player rankings from ESPN data"""
        print(f"🏈 Initializing ESPN player rankings for {season} season...")
        self.nfl_leaders = self.espn_api.get_nfl_leaders(season)
        self._build_position_rankings()
    
    def _build_position_rankings(self):
        """Build position rankings from NFL leaders data"""
        if not self.nfl_leaders:
            return
        
        # Initialize position rankings
        for position in ['QB', 'RB', 'WR', 'TE']:
            self.position_rankings[position] = {}
        
        # Process each category from Core API
        for category in self.nfl_leaders.get('categories', []):
            category_name = category.get('displayName', '')
            leaders = category.get('leaders', [])
            
            print(f"  Processing {category_name}: {len(leaders)} leaders")
            
            if 'passing' in category_name.lower() and 'yards' in category_name.lower():
                # Process QB passing yards
                self._process_position_leaders(leaders, 'QB', max_count=30)
            
            elif 'rushing' in category_name.lower() and 'yards' in category_name.lower():
                # Process RB rushing yards
                self._process_position_leaders(leaders, 'RB', max_count=60, filter_positions=['RB', 'FB'])
            
            elif 'receiving' in category_name.lower() and 'yards' in category_name.lower():
                # Process WR/TE receiving yards
                self._process_receiving_leaders(leaders)
    
    def _process_position_leaders(self, leaders, target_position, max_count=50, filter_positions=None):
        """Process position-specific leaders with optional filtering"""
        rank = 0
        
        for leader in leaders[:80]:  # Take more than we need to account for filtering
            try:
                athlete_data = self._fetch_athlete_details(leader)
                if not athlete_data:
                    continue
                
                name = athlete_data.get('displayName', '')
                position = athlete_data.get('position_abbrev', '')
                
                # Filter by position if specified
                if filter_positions and position not in filter_positions:
                    continue
                
                # Only process if it matches our target position
                if position == target_position:
                    rank += 1
                    if rank > max_count:
                        break
                    
                    name_key = name.lower()
                    self.position_rankings[target_position][name_key] = {
                        'rank': rank,
                        'grade': self._calculate_position_grade(target_position, rank),
                        'espn_id': athlete_data.get('id', ''),
                        'stat_value': leader.get('displayValue', '0'),
                        'position': position,
                        'team': athlete_data.get('team_abbrev', 'Unknown')
                    }
                    
            except Exception as e:
                print(f"     Warning: Error processing leader: {e}")
                continue
    
    def _process_receiving_leaders(self, leaders):
        """Process receiving yards leaders for WR and TE"""
        wr_rank = 0
        te_rank = 0
        
        for leader in leaders[:80]:  # Top 80 receivers
            try:
                athlete_data = self._fetch_athlete_details(leader)
                if not athlete_data:
                    continue
                
                name = athlete_data.get('displayName', '')
                position = athlete_data.get('position_abbrev', '')
                
                if position == 'WR':
                    wr_rank += 1
                    if wr_rank <= 48:  # Top 48 WRs
                        name_key = name.lower()
                        self.position_rankings['WR'][name_key] = {
                            'rank': wr_rank,
                            'grade': self._calculate_position_grade('WR', wr_rank),
                            'espn_id': athlete_data.get('id', ''),
                            'stat_value': leader.get('displayValue', '0'),
                            'position': position,
                            'team': athlete_data.get('team_abbrev', 'Unknown')
                        }
                        
                elif position == 'TE':
                    te_rank += 1
                    if te_rank <= 24:  # Top 24 TEs
                        name_key = name.lower()
                        self.position_rankings['TE'][name_key] = {
                            'rank': te_rank,
                            'grade': self._calculate_position_grade('TE', te_rank),
                            'espn_id': athlete_data.get('id', ''),
                            'stat_value': leader.get('displayValue', '0'),
                            'position': position,
                            'team': athlete_data.get('team_abbrev', 'Unknown')
                        }
                        
            except Exception as e:
                print(f"     Warning: Error processing receiver: {e}")
                continue
    
    def _fetch_athlete_details(self, leader):
        """Fetch athlete details from ESPN Core API"""
        try:
            athlete = leader.get('athlete', {})
            
            if '$ref' in athlete:
                # Fetch detailed athlete data
                athlete_response = self.espn_api.session.get(athlete['$ref'])
                if athlete_response.status_code == 200:
                    athlete_data = athlete_response.json()
                    
                    result = {
                        'id': athlete_data.get('id', ''),
                        'displayName': athlete_data.get('displayName', ''),
                        'fullName': athlete_data.get('fullName', '')
                    }
                    
                    # Handle position reference or direct data
                    if 'position' in athlete_data:
                        pos = athlete_data['position']
                        if isinstance(pos, dict) and '$ref' in pos:
                            pos_response = self.espn_api.session.get(pos['$ref'])
                            if pos_response.status_code == 200:
                                pos_data = pos_response.json()
                                result['position_abbrev'] = pos_data.get('abbreviation', 'Unknown')
                        elif isinstance(pos, dict):
                            result['position_abbrev'] = pos.get('abbreviation', 'Unknown')
                    
                    # Handle team reference or direct data
                    if 'team' in athlete_data:
                        team = athlete_data['team']
                        if isinstance(team, dict) and '$ref' in team:
                            team_response = self.espn_api.session.get(team['$ref'])
                            if team_response.status_code == 200:
                                team_data = team_response.json()
                                result['team_abbrev'] = team_data.get('abbreviation', 'Unknown')
                        elif isinstance(team, dict):
                            result['team_abbrev'] = team.get('abbreviation', 'Unknown')
                    
                    return result
                    
            else:
                # Use direct athlete data
                return {
                    'id': athlete.get('id', ''),
                    'displayName': athlete.get('displayName', ''),
                    'position_abbrev': athlete.get('position', {}).get('abbreviation', 'Unknown'),
                    'team_abbrev': athlete.get('team', {}).get('abbreviation', 'Unknown')
                }
                
        except Exception as e:
            print(f"       Error fetching athlete details: {e}")
            return None
    
    def _calculate_position_grade(self, position: str, rank: int) -> float:
        """Calculate numerical grade based on position and rank"""
        if position not in self.POSITION_TIERS:
            return 5.0  # Default grade
        
        tiers = self.POSITION_TIERS[position]
        
        if rank in tiers.get('elite', []):
            # Elite tier: 9.0-10.0 points
            elite_ranks = tiers['elite']
            position_in_tier = elite_ranks.index(rank)
            max_in_tier = len(elite_ranks)
            return 10.0 - (position_in_tier / max_in_tier) * 1.0
            
        elif rank in tiers.get('solid', []):
            # Solid tier: 7.0-8.9 points
            solid_ranks = tiers['solid']
            position_in_tier = solid_ranks.index(rank)
            max_in_tier = len(solid_ranks)
            return 8.9 - (position_in_tier / max_in_tier) * 1.9
            
        elif rank in tiers.get('flex', []):
            # Flex tier: 5.0-6.9 points
            flex_ranks = tiers['flex']
            position_in_tier = flex_ranks.index(rank)
            max_in_tier = len(flex_ranks)
            return 6.9 - (position_in_tier / max_in_tier) * 1.9
            
        elif rank in tiers.get('streamer', []):
            # Streamer tier: 4.0-5.9 points
            streamer_ranks = tiers['streamer']
            position_in_tier = streamer_ranks.index(rank)
            max_in_tier = len(streamer_ranks)
            return 5.9 - (position_in_tier / max_in_tier) * 1.9
            
        else:
            # Unranked/deep bench: 1.0-3.9 points
            if rank <= 100:
                return max(1.0, 4.0 - (rank - max(max(tiers.values(), key=len))) * 0.05)
            else:
                return 1.0
    
    def grade_player(self, player_name: str, position: str) -> Dict:
        """Grade individual player based on ESPN rankings"""
        if position not in self.position_rankings:
            return {
                'name': player_name,
                'position': position,
                'rank': None,
                'grade': 5.0,  # Default grade
                'tier': 'unranked',
                'espn_id': None,
                'stat_value': None,
                'team': 'Unknown'
            }
        
        name_key = player_name.lower()
        player_data = self.position_rankings[position].get(name_key)
        
        if player_data:
            return {
                'name': player_name,
                'position': position,
                'rank': player_data['rank'],
                'grade': player_data['grade'],
                'tier': self._get_tier_name(position, player_data['rank']),
                'espn_id': player_data.get('espn_id'),
                'stat_value': player_data.get('stat_value'),
                'team': player_data.get('team', 'Unknown')
            }
        else:
            # Player not found in rankings
            return {
                'name': player_name,
                'position': position,
                'rank': None,
                'grade': 3.0,  # Below average for unranked
                'tier': 'unranked',
                'espn_id': None,
                'stat_value': None,
                'team': 'Unknown'
            }
    
    def _get_tier_name(self, position: str, rank: int) -> str:
        """Get tier name for a position rank"""
        if position not in self.POSITION_TIERS:
            return 'unranked'
        
        tiers = self.POSITION_TIERS[position]
        
        for tier_name, tier_ranks in tiers.items():
            if rank in tier_ranks:
                return tier_name
        
        return 'unranked'
    
    def grade_roster(self, players: List[Dict]) -> Dict:
        """Grade entire roster and return comprehensive analysis"""
        if not players:
            return {
                'overall_grade': 0.0,
                'position_grades': {},
                'player_grades': [],
                'total_players': 0,
                'tier_distribution': {}
            }
        
        player_grades = []
        position_grades = {'QB': [], 'RB': [], 'WR': [], 'TE': [], 'Other': []}
        tier_counts = {'elite': 0, 'solid': 0, 'flex': 0, 'streamer': 0, 'unranked': 0}
        
        # Grade each player
        for player in players:
            player_name = player.get('name', '')
            position = player.get('position', '')
            
            # Map fantasy positions to our grading positions
            if position in ['QB']:
                grade_position = 'QB'
            elif position in ['RB', 'FB']:
                grade_position = 'RB'
            elif position in ['WR']:
                grade_position = 'WR'
            elif position in ['TE']:
                grade_position = 'TE'
            else:
                grade_position = 'Other'
            
            if grade_position != 'Other':
                grade_data = self.grade_player(player_name, grade_position)
                player_grades.append(grade_data)
                position_grades[grade_position].append(grade_data['grade'])
                tier_counts[grade_data['tier']] += 1
            else:
                # Handle kickers, defenses, etc.
                grade_data = {
                    'name': player_name,
                    'position': position,
                    'rank': None,
                    'grade': 5.0,
                    'tier': 'other',
                    'espn_id': None,
                    'stat_value': None,
                    'team': 'Unknown'
                }
                player_grades.append(grade_data)
                position_grades['Other'].append(5.0)
        
        # Calculate position averages
        position_averages = {}
        for pos, grades in position_grades.items():
            if grades:
                position_averages[pos] = round(statistics.mean(grades), 1)
            else:
                position_averages[pos] = 0.0
        
        # Calculate overall grade (weighted average)
        weights = {'QB': 0.15, 'RB': 0.30, 'WR': 0.35, 'TE': 0.15, 'Other': 0.05}
        overall_grade = 0.0
        
        for pos, weight in weights.items():
            if position_averages[pos] > 0:
                overall_grade += position_averages[pos] * weight
        
        return {
            'overall_grade': round(overall_grade, 1),
            'position_grades': position_averages,
            'player_grades': player_grades,
            'total_players': len(players),
            'tier_distribution': tier_counts,
            'position_counts': {pos: len(grades) for pos, grades in position_grades.items()},
            'highest_graded_player': max(player_grades, key=lambda x: x['grade']) if player_grades else None,
            'lowest_graded_player': min(player_grades, key=lambda x: x['grade']) if player_grades else None
        }


def get_grade_tier(grade):
    """Get tier description from numerical grade"""
    if grade >= 9.0:
        return "Elite"
    elif grade >= 7.0:
        return "Solid"
    elif grade >= 5.0:
        return "Flex"
    else:
        return "Streamer"


def _calculate_manager_grade(roster, roster_analysis):
    """Calculate manager effectiveness grade"""
    wins = roster.get('settings', {}).get('wins', 0)
    losses = roster.get('settings', {}).get('losses', 0)
    total_games = wins + losses
    
    if total_games == 0:
        return "N/A - No games played"
    
    win_rate = wins / total_games
    roster_grade = roster_analysis.get('overall_grade', 5.0)
    
    # Expected wins based on roster grade
    # Grade 8.0+ should win 70%+, Grade 6.0-7.9 should win 50-70%, etc.
    if roster_grade >= 8.0:
        expected_win_rate = 0.70
    elif roster_grade >= 6.5:
        expected_win_rate = 0.60
    elif roster_grade >= 5.5:
        expected_win_rate = 0.50
    elif roster_grade >= 4.5:
        expected_win_rate = 0.40
    else:
        expected_win_rate = 0.30
    
    # Compare actual vs expected
    performance_ratio = win_rate / expected_win_rate if expected_win_rate > 0 else 1.0
    
    if performance_ratio >= 1.2:
        return "A - Overachieving"
    elif performance_ratio >= 1.0:
        return "B - Meeting Expectations"
    elif performance_ratio >= 0.8:
        return "C - Underperforming"
    else:
        return "D - Significantly Underperforming"


def _get_roster_construction_notes(roster_analysis):
    """Get roster construction insights"""
    notes = []
    tier_dist = roster_analysis.get('tier_distribution', {})
    pos_grades = roster_analysis.get('position_grades', {})
    
    # Strength analysis
    strong_positions = [pos for pos, grade in pos_grades.items() if grade >= 7.0 and pos != 'Other']
    weak_positions = [pos for pos, grade in pos_grades.items() if grade < 5.0 and pos != 'Other']
    
    if strong_positions:
        notes.append(f"Strong at: {', '.join(strong_positions)}")
    if weak_positions:
        notes.append(f"Weak at: {', '.join(weak_positions)}")
    
    # Tier distribution insights
    if tier_dist.get('elite', 0) >= 3:
        notes.append("Elite-heavy roster")
    if tier_dist.get('solid', 0) >= 6:
        notes.append("Deep and consistent")
    if tier_dist.get('unranked', 0) >= 5:
        notes.append("Many unproven players")
    
    return notes if notes else ["Balanced roster construction"]