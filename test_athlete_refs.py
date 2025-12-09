#!/usr/bin/env python3
"""Test fetching athlete details from ESPN Core API references"""

import requests
import json

def test_athlete_refs():
    print("Testing ESPN Core API athlete reference fetching...")
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    
    # First get the leaders
    url = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2025/types/2/leaders"
    response = session.get(url)
    
    if response.status_code == 200:
        data = response.json()
        
        # Get first category (passing yards)
        passing_category = None
        for cat in data.get('categories', []):
            if 'passing' in cat.get('displayName', '').lower():
                passing_category = cat
                break
        
        if passing_category:
            leaders = passing_category.get('leaders', [])
            if leaders:
                first_leader = leaders[0]
                athlete_ref = first_leader.get('athlete', {}).get('$ref')
                
                if athlete_ref:
                    print(f"🏈 Fetching athlete details from: {athlete_ref}")
                    
                    # Fetch athlete details
                    athlete_response = session.get(athlete_ref)
                    
                    if athlete_response.status_code == 200:
                        athlete_data = athlete_response.json()
                        print("✅ Athlete data fetched successfully!")
                        print(f"Keys: {list(athlete_data.keys())}")
                        
                        # Print athlete info
                        print(f"Name: {athlete_data.get('displayName', 'Unknown')}")
                        print(f"Full Name: {athlete_data.get('fullName', 'Unknown')}")
                        
                        if 'position' in athlete_data:
                            pos = athlete_data['position']
                            if isinstance(pos, dict):
                                if '$ref' in pos:
                                    print(f"Position ref: {pos['$ref']}")
                                else:
                                    print(f"Position: {pos.get('abbreviation', 'Unknown')}")
                            else:
                                print(f"Position: {pos}")
                        
                        if 'team' in athlete_data:
                            team = athlete_data['team']
                            if isinstance(team, dict):
                                if '$ref' in team:
                                    print(f"Team ref: {team['$ref']}")
                                else:
                                    print(f"Team: {team.get('abbreviation', 'Unknown')}")
                        
                        # Show some stats if available
                        if 'statistics' in athlete_data:
                            print(f"Has statistics: {athlete_data['statistics']}")
                        
                        # Try to get position details if it's a ref
                        if 'position' in athlete_data and isinstance(athlete_data['position'], dict):
                            if '$ref' in athlete_data['position']:
                                pos_ref = athlete_data['position']['$ref']
                                print(f"\\n🔍 Fetching position details from: {pos_ref}")
                                pos_response = session.get(pos_ref)
                                if pos_response.status_code == 200:
                                    pos_data = pos_response.json()
                                    print(f"Position: {pos_data.get('abbreviation', 'Unknown')} - {pos_data.get('displayName', 'Unknown')}")
                        
                        # Try to get team details if it's a ref  
                        if 'team' in athlete_data and isinstance(athlete_data['team'], dict):
                            if '$ref' in athlete_data['team']:
                                team_ref = athlete_data['team']['$ref']
                                print(f"\\n🔍 Fetching team details from: {team_ref}")
                                team_response = session.get(team_ref)
                                if team_response.status_code == 200:
                                    team_data = team_response.json()
                                    print(f"Team: {team_data.get('abbreviation', 'Unknown')} - {team_data.get('displayName', 'Unknown')}")
                    
                    else:
                        print(f"❌ Error fetching athlete: {athlete_response.status_code}")
                else:
                    print("❌ No athlete reference found")
            else:
                print("❌ No leaders found")
        else:
            print("❌ No passing category found")
    else:
        print(f"❌ Error: {response.status_code}")

if __name__ == "__main__":
    test_athlete_refs()