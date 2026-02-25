#!/usr/bin/env python3
"""
Debug script to check the exact API response structure for the map
"""

import requests
import json

API_URL = "http://127.0.0.1:8000"
API_KEY = "super_secure_api_key"
HEADERS = {"x-api-key": API_KEY}

def debug_risk_map():
    print("="*70)
    print("DEBUG: /dashboard/risk-map API Response")
    print("="*70)
    
    try:
        response = requests.get(
            f"{API_URL}/dashboard/risk-map",
            headers=HEADERS,
            params={"mode": "online"},
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'unknown')}")
        print()
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response is array: {isinstance(data, list)}")
            print(f"Number of items: {len(data)}")
            print()
            
            if data:
                print("First item structure:")
                first = data[0]
                print(json.dumps(first, indent=2))
                print()
                
                # Check for required fields
                print("Field validation:")
                for i, item in enumerate(data[:3]):
                    country = item.get('country', 'MISSING')
                    risk = item.get('risk', 'MISSING')
                    risk_type = type(item.get('risk')).__name__
                    print(f"  [{i}] country={country}, risk={risk} (type: {risk_type})")
                
                # Check for null/undefined risks
                null_risks = [i for i, item in enumerate(data) if item.get('risk') is None]
                if null_risks:
                    print(f"\n⚠️  WARNING: {len(null_risks)} items have null/undefined risk!")
                else:
                    print(f"\n✅ All {len(data)} items have valid risk values")
            else:
                print("❌ Response is empty array - map will not render!")
        else:
            print(f"❌ API Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")

def check_cors_preflight():
    print("\n" + "="*70)
    print("DEBUG: CORS Preflight Check")
    print("="*70)
    
    try:
        response = requests.options(
            f"{API_URL}/dashboard/risk-map",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-api-key",
            },
            timeout=5
        )
        print(f"Preflight status: {response.status_code}")
        print(f"CORS headers: {dict(response.headers)}")
    except Exception as e:
        print(f"Preflight check failed: {e}")

def test_with_browser_headers():
    print("\n" + "="*70)
    print("DEBUG: Simulating Browser Request")
    print("="*70)
    
    browser_headers = {
        "x-api-key": API_KEY,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "http://localhost:5173",
        "Referer": "http://localhost:5173/dashboard",
    }
    
    try:
        response = requests.get(
            f"{API_URL}/dashboard/risk-map",
            headers=browser_headers,
            params={"mode": "online"},
            timeout=10
        )
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Items returned: {len(data)}")
        if data:
            print(f"Sample: {data[0]}")
    except Exception as e:
        print(f"Browser simulation failed: {e}")

if __name__ == "__main__":
    debug_risk_map()
    check_cors_preflight()
    test_with_browser_headers()
