#!/usr/bin/env python3
"""
Comprehensive API test simulating frontend dashboard calls
Tests all endpoints the dashboard uses including the map
"""

import requests
import json
import sys
from datetime import datetime

API_URL = "http://127.0.0.1:8000"
API_KEY = "super_secure_api_key"
HEADERS = {"x-api-key": API_KEY}

def test_endpoint(name, method, path, expected_status=200, params=None, data=None):
    """Test a single API endpoint"""
    url = f"{API_URL}{path}"
    try:
        if method == "GET":
            response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=HEADERS, json=data, timeout=10)
        else:
            return False, f"Unknown method: {method}"
        
        success = response.status_code == expected_status
        if success:
            return True, response.json()
        else:
            return False, f"Status {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, str(e)

def test_dashboard_flow():
    """Test the complete dashboard data flow"""
    print("\n" + "="*70)
    print("FRONTEND DASHBOARD API FLOW TEST")
    print("="*70)
    print(f"Testing against: {API_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    
    results = {}
    
    # Test 1: Health check
    print("\n1. Health Check (/health)")
    print("-" * 40)
    ok, data = test_endpoint("health", "GET", "/health")
    if ok:
        print(f"   ✅ Backend healthy")
        print(f"   - Database: {data.get('database', 'unknown')}")
        print(f"   - Model loaded: {data.get('model_loaded', 'unknown')}")
    else:
        print(f"   ❌ Health check failed: {data}")
    results["health"] = ok
    
    # Test 2: Live feed (for incidents and heartbeat)
    print("\n2. Live Feed (/dashboard/live-feed)")
    print("-" * 40)
    ok, data = test_endpoint("live-feed", "GET", "/dashboard/live-feed", params={"mode": "online"})
    if ok:
        print(f"   ✅ Live feed working")
        print(f"   - Incidents: {len(data.get('incidents', []))}")
        print(f"   - Heartbeat: {data.get('ingestionHeartbeatSec', 'N/A')}s")
        print(f"   - Model drift: {data.get('modelDrift', 'N/A')}")
        print(f"   - Last updated: {data.get('lastUpdated', 'N/A')}")
    else:
        print(f"   ❌ Live feed failed: {data}")
    results["live_feed"] = ok
    
    # Test 3: Risk Map (THE KEY TEST FOR COUNTRIES)
    print("\n3. Risk Map (/dashboard/risk-map) - CRITICAL FOR MAP DISPLAY")
    print("-" * 40)
    ok, data = test_endpoint("risk-map", "GET", "/dashboard/risk-map", params={"mode": "online"})
    if ok:
        print(f"   ✅ Risk map API working")
        print(f"   - Countries returned: {len(data)}")
        
        if len(data) > 0:
            print(f"\n   Country data sample:")
            for i, country in enumerate(data[:3]):
                print(f"   [{i+1}] {country.get('country', 'N/A')}: risk={country.get('risk', 'N/A')}")
            
            # Check data quality
            valid_countries = [c for c in data if c.get('country') and c.get('risk') is not None]
            print(f"\n   Data quality:")
            print(f"   - Valid country entries: {len(valid_countries)}/{len(data)}")
            
            if len(valid_countries) == 0:
                print(f"   ⚠️  WARNING: No valid country data with risk scores!")
                print(f"   The map will NOT display properly without risk values.")
        else:
            print(f"   ⚠️  WARNING: No countries returned - map will be empty!")
    else:
        print(f"   ❌ Risk map failed: {data}")
    results["risk_map"] = ok and len(data) > 0
    
    # Test 4: Governance data
    print("\n4. Governance (/dashboard/governance)")
    print("-" * 40)
    ok, data = test_endpoint("governance", "GET", "/dashboard/governance", params={"mode": "online"})
    if ok:
        print(f"   ✅ Governance API working")
        print(f"   - Models: {len(data.get('models', []))}")
        print(f"   - Disagreements: {len(data.get('disagreement', []))}")
    else:
        print(f"   ❌ Governance failed: {data}")
    results["governance"] = ok
    
    # Test 5: Country drilldown (for a specific country)
    print("\n5. Country Drilldown (/dashboard/country/{country})")
    print("-" * 40)
    # First get a country from the risk map
    ok_map, map_data = test_endpoint("risk-map", "GET", "/dashboard/risk-map", params={"mode": "online"})
    if ok_map and map_data:
        test_country = map_data[0].get('country', 'US')
        ok, data = test_endpoint("country-drilldown", "GET", f"/dashboard/country/{test_country}", params={"mode": "online"})
        if ok:
            print(f"   ✅ Country drilldown working for {test_country}")
            print(f"   - Risk: {data.get('risk', 'N/A')}")
            print(f"   - Trend points: {len(data.get('trend', []))}")
            print(f"   - Drivers: {len(data.get('drivers', []))}")
            print(f"   - Events: {len(data.get('events', []))}")
        else:
            print(f"   ❌ Country drilldown failed: {data}")
        results["country_drilldown"] = ok
    else:
        print(f"   ⚠️  Skipped (no countries available to test)")
        results["country_drilldown"] = False
    
    # Test 6: Global features history (for time series chart)
    print("\n6. Global History (/features/global/history)")
    print("-" * 40)
    ok, data = test_endpoint("global-history", "GET", "/features/global/history", 
                          params={"mode": "online", "limit": 100})
    if ok:
        print(f"   ✅ Global history API working")
        print(f"   - Data points: {len(data)}")
        if data:
            print(f"   - Latest risk: {data[-1].get('risk_score', 'N/A')}")
    else:
        print(f"   ❌ Global history failed: {data}")
    results["global_history"] = ok
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status}: {test_name}")
    
    all_passed = all(results.values())
    critical_passed = results.get("risk_map", False) and results.get("live_feed", False)
    
    print("\n" + "="*70)
    if all_passed:
        print("🎉 ALL TESTS PASSED")
        print("="*70)
        print("\nThe dashboard should display correctly including:")
        print("✓ Map with country risk data")
        print("✓ Live incident feed")
        print("✓ Model governance panel")
        print("✓ Time series charts")
        print("✓ Country drilldown on click")
    elif critical_passed:
        print("⚠️  CRITICAL FUNCTIONS WORKING (some non-critical tests failed)")
        print("="*70)
        print("\nThe map and main dashboard should work.")
        print("Some secondary features may have issues.")
    else:
        print("❌ CRITICAL TESTS FAILED")
        print("="*70)
        print("\nThe dashboard will NOT work properly.")
        print("Issues to fix:")
        if not results.get("risk_map"):
            print("  - Risk map API failing or returning no data")
        if not results.get("live_feed"):
            print("  - Live feed API failing")
        if not results.get("health"):
            print("  - Backend not responding")
    
    return all_passed

if __name__ == "__main__":
    success = test_dashboard_flow()
    sys.exit(0 if success else 1)
