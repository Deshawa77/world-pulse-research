#!/usr/bin/env python3
"""
Test script to verify the 422 error fix on /features/global/history endpoint.
Tests various date format scenarios.
"""

import requests
import sys
from datetime import datetime, timedelta

# Configuration
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "super_secure_api_key"  # Default key from the project

HEADERS = {
    "x-api-key": API_KEY
}

def test_endpoint(name, params, expected_status):
    """Test the endpoint with given parameters."""
    url = f"{BASE_URL}/features/global/history"
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        status = "✅ PASS" if response.status_code == expected_status else "❌ FAIL"
        print(f"{status} | {name}")
        print(f"       URL: {url}")
        print(f"       Params: {params}")
        print(f"       Expected: {expected_status}, Got: {response.status_code}")
        if response.status_code != expected_status:
            print(f"       Response: {response.text[:200]}")
        print()
        return response.status_code == expected_status
    except Exception as e:
        print(f"❌ FAIL | {name}")
        print(f"       Error: {str(e)}")
        print()
        return False

def run_tests():
    """Run all test cases."""
    print("=" * 70)
    print("Testing /features/global/history endpoint - 422 Error Fix")
    print("=" * 70)
    print()

    results = []

    # Test 1: Original problematic date format with milliseconds (2026 dates)
    results.append(test_endpoint(
        "Original issue - Future dates with milliseconds",
        {
            "limit": 2000,
            "start_date": "2026-02-18T23:18:26.035Z",
            "end_date": "2026-02-25T23:18:26.035Z"
        },
        200  # Should now return 200 instead of 422
    ))

    # Test 2: Current date with milliseconds
    now = datetime.utcnow()
    results.append(test_endpoint(
        "Current date with milliseconds",
        {
            "limit": 100,
            "start_date": (now - timedelta(days=7)).isoformat() + ".123Z",
            "end_date": now.isoformat() + ".456Z"
        },
        200
    ))

    # Test 3: Standard ISO format without milliseconds
    results.append(test_endpoint(
        "Standard ISO format without milliseconds",
        {
            "limit": 100,
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-12-31T23:59:59Z"
        },
        200
    ))

    # Test 4: ISO format with timezone offset
    results.append(test_endpoint(
        "ISO format with timezone offset",
        {
            "limit": 100,
            "start_date": "2024-01-01T00:00:00+00:00",
            "end_date": "2024-12-31T23:59:59+00:00"
        },
        200
    ))

    # Test 5: Only limit parameter (no dates)
    results.append(test_endpoint(
        "Only limit parameter (no dates)",
        {"limit": 100},
        200
    ))

    # Test 6: Invalid date format - should return 400
    results.append(test_endpoint(
        "Invalid date format (should return 400)",
        {
            "limit": 100,
            "start_date": "not-a-valid-date",
            "end_date": "2024-01-01T00:00:00Z"
        },
        400
    ))

    # Test 7: Another invalid date format
    results.append(test_endpoint(
        "Another invalid date format (should return 400)",
        {
            "limit": 100,
            "start_date": "2024/01/01",  # Wrong separator
            "end_date": "2024-01-01T00:00:00Z"
        },
        400
    ))

    # Test 8: Empty date strings
    results.append(test_endpoint(
        "Empty date strings (should be ignored)",
        {
            "limit": 100,
            "start_date": "",
            "end_date": ""
        },
        200
    ))

    # Test 9: Very high limit value
    results.append(test_endpoint(
        "Very high limit value (within bounds)",
        {"limit": 10000},
        200
    ))

    # Test 10: Limit exceeding maximum (should fail validation)
    results.append(test_endpoint(
        "Limit exceeding maximum (should return 422)",
        {"limit": 10001},
        422
    ))

    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(run_tests())
