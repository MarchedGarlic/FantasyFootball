#!/usr/bin/env python3
"""Test the specific ESPN Core API data structure"""

import requests
import json

def test_core_api_structure():
    print("Testing ESPN Core API data structure for leaders...")
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    
    url = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2025/types/2/leaders"
    response = session.get(url)
    
    if response.status_code == 200:
        data = response.json()
        print("API Response successful!")
        print(f"Keys: {list(data.keys())}")
        
        if 'categories' in data:
            categories = data['categories']
            print(f"\nFound {len(categories)} categories:")
            
            for i, category in enumerate(categories[:5]):  # Show first 5 categories
                print(f"\n{i+1}. {category.get('displayName', 'Unknown')}")
                print(f"   Category keys: {list(category.keys())}")
                
                leaders = category.get('leaders', [])
                print(f"   Leaders count: {len(leaders)}")
                
                if leaders:
                    # Show first leader structure
                    first_leader = leaders[0]
                    print(f"   First leader keys: {list(first_leader.keys())}")
                    
                    if 'athlete' in first_leader:
                        athlete = first_leader['athlete']
                        print(f"   Athlete keys: {list(athlete.keys())}")
                        print(f"   Name: {athlete.get('displayName', 'Unknown')}")
                        print(f"   Position: {athlete.get('position', {}).get('abbreviation', 'Unknown')}")
                        print(f"   Team: {athlete.get('team', {}).get('abbreviation', 'Unknown')}")
                        print(f"   Value: {first_leader.get('displayValue', 'Unknown')}")
                    
                    # Show top 3 players in this category
                    print(f"   Top 3:")
                    for j, leader in enumerate(leaders[:3]):
                        athlete = leader.get('athlete', {})
                        name = athlete.get('displayName', 'Unknown')
                        value = leader.get('displayValue', 'Unknown')
                        pos = athlete.get('position', {}).get('abbreviation', 'Unknown')
                        team = athlete.get('team', {}).get('abbreviation', 'Unknown')
                        print(f"     {j+1}. {name} ({pos}, {team}): {value}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    test_core_api_structure()