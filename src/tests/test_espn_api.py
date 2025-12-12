#!/usr/bin/env python3
"""Quick test of ESPN API to see what data is available"""

import requests
import json

def test_espn_api():
    print("Testing ESPN API for 2025 NFL season data...")
    
    # Test different endpoints
    endpoints = [
        {
            'name': 'NFL Leaders 2025',
            'url': 'https://site.api.espn.com/apis/site/v3/sports/football/nfl/leaders',
            'params': {'season': '2025', 'seasontype': 2}
        },
        {
            'name': 'NFL Leaders 2024', 
            'url': 'https://site.api.espn.com/apis/site/v3/sports/football/nfl/leaders',
            'params': {'season': '2024', 'seasontype': 2}
        },
        {
            'name': 'NFL Scoreboard Current',
            'url': 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
            'params': {}
        },
        {
            'name': 'NFL Teams',
            'url': 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams',
            'params': {}
        }
    ]
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    
    for endpoint in endpoints:
        print(f"\n{'='*50}")
        print(f"Testing: {endpoint['name']}")
        print(f"URL: {endpoint['url']}")
        print(f"Params: {endpoint['params']}")
        
        try:
            response = session.get(endpoint['url'], params=endpoint['params'])
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if 'leaders' in endpoint['name'].lower():
                    # Handle leaders endpoint
                    categories = data.get('categories', [])
                    print(f"Categories found: {len(categories)}")
                    
                    for i, category in enumerate(categories[:3]):  # Show first 3
                        print(f"\nCategory {i+1}: {category.get('displayName', 'Unknown')}")
                        leaders = category.get('leaders', [])
                        print(f"  Leaders: {len(leaders)}")
                        
                        if leaders:
                            for j, leader in enumerate(leaders[:3]):  # Show top 3
                                athlete = leader.get('athlete', {})
                                name = athlete.get('displayName', 'Unknown')
                                value = leader.get('displayValue', 'N/A')
                                position = athlete.get('position', {}).get('abbreviation', 'Unknown')
                                team = athlete.get('team', {}).get('abbreviation', 'Unknown')
                                print(f"    {j+1}. {name} ({position}, {team}): {value}")
                
                elif 'teams' in endpoint['name'].lower():
                    teams = data.get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', [])
                    print(f"Teams found: {len(teams)}")
                    if teams:
                        for team in teams[:3]:  # Show first 3
                            team_data = team.get('team', {})
                            print(f"  {team_data.get('displayName', 'Unknown')} ({team_data.get('abbreviation', 'Unknown')})")
                
                elif 'scoreboard' in endpoint['name'].lower():
                    events = data.get('events', [])
                    print(f"Games found: {len(events)}")
                    if events:
                        for event in events[:2]:  # Show first 2
                            name = event.get('name', 'Unknown')
                            date = event.get('date', 'Unknown')
                            print(f"  {name} on {date}")
                
            else:
                print(f"Error: {response.status_code}")
                print(f"Response: {response.text[:200]}...")
                
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    test_espn_api()