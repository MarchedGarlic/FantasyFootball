#!/usr/bin/env python3
"""Test alternative ESPN API endpoints for player stats"""

import requests
import json

def test_alternative_endpoints():
    print("Testing alternative ESPN API endpoints for player stats...")
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    
    # Try different approaches
    endpoints = [
        {
            'name': 'Core API Leaders 2025',
            'url': 'https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2025/types/2/leaders',
            'params': {}
        },
        {
            'name': 'Core API Leaders 2024', 
            'url': 'https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2024/types/2/leaders',
            'params': {}
        },
        {
            'name': 'Site API without season param',
            'url': 'https://site.api.espn.com/apis/site/v3/sports/football/nfl/leaders',
            'params': {}
        },
        {
            'name': 'Athletes Core API',
            'url': 'https://sports.core.api.espn.com/v3/sports/football/nfl/athletes',
            'params': {'limit': 10}
        },
        {
            'name': 'NFL Current Season Info',
            'url': 'https://site.api.espn.com/apis/common/v3/sports/football/nfl/season',
            'params': {}
        }
    ]
    
    for endpoint in endpoints:
        print(f"\n{'='*60}")
        print(f"Testing: {endpoint['name']}")
        print(f"URL: {endpoint['url']}")
        
        try:
            response = session.get(endpoint['url'], params=endpoint['params'])
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Print structure info
                if isinstance(data, dict):
                    print(f"Top-level keys: {list(data.keys())}")
                    
                    # Look for interesting data
                    if 'categories' in data:
                        print(f"Categories: {len(data['categories'])}")
                        for cat in data['categories'][:2]:
                            print(f"  - {cat.get('displayName', 'Unknown')}: {len(cat.get('leaders', []))} leaders")
                    
                    elif 'items' in data:
                        print(f"Items: {len(data['items'])}")
                        if data['items']:
                            first_item = data['items'][0]
                            if '$ref' in first_item:
                                print(f"  First item ref: {first_item['$ref']}")
                    
                    elif 'athletes' in data:
                        athletes = data['athletes']
                        print(f"Athletes: {len(athletes)}")
                        for athlete in athletes[:3]:
                            name = athlete.get('displayName', 'Unknown')
                            pos = athlete.get('position', {}).get('abbreviation', 'Unknown')
                            team = athlete.get('team', {}).get('abbreviation', 'Unknown')
                            print(f"  {name} ({pos}, {team})")
                    
                    elif 'year' in data or 'type' in data:
                        print(f"Season info - Year: {data.get('year', 'N/A')}, Type: {data.get('type', 'N/A')}")
                        print(f"Active: {data.get('hasGroups', 'N/A')}")
                
            else:
                print(f"Error: {response.status_code}")
                if response.text:
                    try:
                        error_data = response.json()
                        print(f"Error details: {error_data}")
                    except:
                        print(f"Error text: {response.text[:200]}...")
                        
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    test_alternative_endpoints()