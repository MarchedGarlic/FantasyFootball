#!/usr/bin/env python3
"""
Test script to check AI Overview functionality
"""

import requests
import json

def test_ai_overview():
    try:
        print("🔍 Testing AI Overview endpoint...")
        url = "http://localhost:5000/api/ai-overview"
        
        response = requests.get(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text[:500]}...")  # First 500 chars
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ Success! AI Overview generated")
                print(f"Overview length: {len(data.get('overview', ''))}")
            except json.JSONDecodeError:
                print("❌ Response is not valid JSON")
        else:
            print(f"❌ Error: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - is the server running on port 5000?")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_ai_overview()