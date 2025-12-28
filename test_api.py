#!/usr/bin/env python3
"""
Test script to verify API functionality
"""

import requests
import json

def test_api():
    try:
        print("🔍 Testing API endpoint...")
        url = "http://localhost:5000/api/user/joeyscott31"
        
        response = requests.get(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Found {len(data.get('leagues', []))} leagues")
        else:
            print(f"❌ Error: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - is the server running?")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_api()