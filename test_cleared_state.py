#!/usr/bin/env python3
"""
Simple test script to demonstrate the cleared state functionality
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:5001"

def test_endpoint(endpoint, description):
    """Test an API endpoint and show the response"""
    print(f"\n--- Testing {endpoint} ({description}) ---")
    try:
        response = requests.get(f"{BASE_URL}{endpoint}")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            # Show relevant fields based on endpoint
            if endpoint == "/api/advisories":
                print(f"Advisories count: {len(data.get('advisories', []))}")
                print(f"Message: {data.get('message', 'N/A')}")
                print(f"Cleared: {data.get('cleared', False)}")
            elif endpoint == "/api/forecast":
                print(f"Forecast points: {len(data.get('points', []))}")
                print(f"Total forecast: {data.get('total_forecast', 0)}")
                print(f"Message: {data.get('message', 'N/A')}")
                print(f"Cleared: {data.get('cleared', False)}")
            elif endpoint == "/api/daily-plan":
                print(f"Daily plan days: {data.get('total_days', 0)}")
                print(f"Message: {data.get('message', 'N/A')}")
                print(f"Cleared: {data.get('cleared', False)}")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Request failed: {e}")

def main():
    print("=== Testing API Endpoints with Cleared State ===")
    
    # Test all endpoints
    test_endpoint("/api/advisories", "Advisories")
    test_endpoint("/api/forecast", "Forecast")
    test_endpoint("/api/daily-plan", "Daily Plan")
    
    print("\n=== Summary ===")
    print("All endpoints should return empty data with 'cleared': true")
    print("This demonstrates that the cleared state prevents demo data from showing")

if __name__ == "__main__":
    main()
