#!/usr/bin/env python3
"""
API Clients Module
Handles external API connections for ESPN and Sleeper data
"""

import requests
import time
from typing import Dict, List, Optional


class ESPNAPI:
    """ESPN API wrapper for NFL data and player analysis"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def get_nfl_scoreboard(self, week=None, season=None):
        """Get NFL scoreboard data"""
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        params = {}
        if week:
            params['week'] = week
        if season:
            params['season'] = season
        
        response = self.session.get(url, params=params)
        return response.json() if response.status_code == 200 else None
    
    def get_nfl_teams(self):
        """Get NFL teams data"""
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else None
    
    def get_nfl_leaders(self, season="2025"):
        """Get NFL statistical leaders using Core API"""
        url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{season}/types/2/leaders"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else None
    
    def get_player_stats(self, athlete_id, season="2024"):
        """Get specific player statistics"""
        url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{season}/athletes/{athlete_id}/statistics"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else None
    
    def search_player(self, query):
        """Search for players by name"""
        # Implementation would go here for player search
        pass


class SleeperAPI:
    """Sleeper API wrapper for fantasy football data"""
    
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://api.sleeper.app/v1"
        
    def get_user_by_username(self, username):
        """Get user by username"""
        url = f"{self.base_url}/user/{username}"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else None
    
    def get_user(self, user_id):
        """Get user by user_id"""
        url = f"{self.base_url}/user/{user_id}"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else None
    
    def get_user_leagues(self, user_id, season="2025", sport="nfl"):
        """Get leagues for a user"""
        url = f"{self.base_url}/user/{user_id}/leagues/{sport}/{season}"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else []
    
    def get_league_info(self, league_id):
        """Get detailed league information"""
        url = f"{self.base_url}/league/{league_id}"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else None
    
    def get_league_rosters(self, league_id):
        """Get all rosters for a league"""
        url = f"{self.base_url}/league/{league_id}/rosters"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else []
    
    def get_league_users(self, league_id):
        """Get all users in a league"""
        url = f"{self.base_url}/league/{league_id}/users"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else []
    
    def get_league_matchups(self, league_id, week):
        """Get matchups for a specific week"""
        url = f"{self.base_url}/league/{league_id}/matchups/{week}"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else []
    
    def get_all_players(self, sport="nfl"):
        """Get all players - large API call (~5MB)"""
        url = f"{self.base_url}/players/{sport}"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else {}
    
    def get_league_transactions(self, league_id, week):
        """Get transactions for a specific week"""
        url = f"{self.base_url}/league/{league_id}/transactions/{week}"
        response = self.session.get(url)
        return response.json() if response.status_code == 200 else []
    
    def get_all_league_transactions(self, league_id):
        """Get all transactions for a league across all weeks"""
        all_transactions = []
        
        for week in range(1, 19):  # NFL regular season + playoffs
            try:
                url = f"{self.base_url}/league/{league_id}/transactions/{week}"
                response = self.session.get(url)
                
                if response.status_code == 200:
                    week_transactions = response.json()
                    if week_transactions:
                        all_transactions.extend(week_transactions)
                        
                # Small delay to be respectful to API
                time.sleep(0.1)
                
            except Exception as e:
                print(f"   Warning: Error fetching week {week} transactions: {e}")
                continue
        
        print(f"   Fetched {len(all_transactions)} total transactions")
        return all_transactions