#!/usr/bin/env python3
"""
Test script for SENTINEL AI API endpoints
"""
import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "super_secure_api_key"
HEADERS = {"x-api-key": API_KEY}

def test_sentinel_latest():
    """Test GET /api/sentinel/latest endpoint"""
    print("\n" + "="*60)
    print("TEST 1: GET /api/sentinel/latest")
    print("="*60)
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/sentinel/latest",
            headers=HEADERS,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ SUCCESS! Response received")
            print(f"\nResponse Structure:")
            print(json.dumps(data, indent=2))
            
            # Validate required fields
            required_fields = [
                "timestamp", "risk_score", "risk_delta", "risk_trend",
                "threat_level", "top_drivers", "multi_domain_signal",
                "confidence", "analysis_text"
            ]
            
            missing = [f for f in required_fields if f not in data]
            if missing:
                print(f"\n❌ Missing fields: {missing}")
                return False
            
            # Validate threat level
            valid_levels = ["stable", "guarded", "elevated", "critical"]
            if data["threat_level"] not in valid_levels:
                print(f"\n❌ Invalid threat_level: {data['threat_level']}")
                return False
            
            # Validate risk trend
            valid_trends = ["increasing", "decreasing", "stable"]
            if data["risk_trend"] not in valid_trends:
                print(f"\n❌ Invalid risk_trend: {data['risk_trend']}")
                return False
            
            # Validate top_drivers structure
            if not isinstance(data["top_drivers"], list):
                print(f"\n❌ top_drivers should be a list")
                return False
            
            for driver in data["top_drivers"]:
                if "feature" not in driver or "impact" not in driver:
                    print(f"\n❌ Driver missing required fields: {driver}")
                    return False
            
            print(f"\n✅ All validations passed!")
            print(f"   - Threat Level: {data['threat_level']}")
            print(f"   - Risk Score: {data['risk_score']}")
            print(f"   - Risk Delta: {data['risk_delta']}")
            print(f"   - Confidence: {data['confidence']}")
            print(f"   - Top Drivers: {len(data['top_drivers'])}")
            print(f"   - Multi-Domain Signal: {data['multi_domain_signal']}")
            
            return True
        else:
            print(f"\n❌ FAILED! Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"\n❌ CONNECTION ERROR: Cannot connect to {BASE_URL}")
        print("   Is the backend server running?")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return False

def test_sentinel_history():
    """Test GET /api/sentinel/history endpoint"""
    print("\n" + "="*60)
    print("TEST 2: GET /api/sentinel/history")
    print("="*60)
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/sentinel/history",
            headers=HEADERS,
            params={"limit": 5},
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ SUCCESS! Response received")
            print(f"\nResponse Structure:")
            print(json.dumps(data, indent=2))
            
            if not isinstance(data, dict) or "history" not in data:
                print(f"\n❌ Response should be an object with 'history' key")
                return False
            
            history = data["history"]
            if not isinstance(history, list):
                print(f"\n❌ 'history' should be a list")
                return False
            
            print(f"\n✅ History endpoint working!")
            print(f"   - Records returned: {len(history)}")
            
            return True

        else:
            print(f"\n❌ FAILED! Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"\n❌ CONNECTION ERROR: Cannot connect to {BASE_URL}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return False

def test_threat_level_calculation():
    """Test threat level calculation logic"""
    print("\n" + "="*60)
    print("TEST 3: Threat Level Calculation Logic")
    print("="*60)
    
    # We need to check the sentinel_analysis module directly
    try:
        sys.path.insert(0, 'c:/Projects/world-pulse-research')
        from processing.sentinel_analysis import get_threat_level
        
        test_cases = [
            (45, "stable"),
            (55, "guarded"),
            (75, "elevated"),
            (90, "critical"),
            (30, "stable"),
            (50, "guarded"),
            (70, "elevated"),
            (85, "critical"),
            (100, "critical"),
        ]

        
        all_passed = True
        for risk_score, expected in test_cases:
            result = get_threat_level(risk_score)
            status = "✅" if result == expected else "❌"
            print(f"  {status} Risk {risk_score} -> {result} (expected: {expected})")
            if result != expected:
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"\n❌ ERROR testing threat level logic: {str(e)}")
        return False


def main():
    print("\n" + "="*60)
    print("SENTINEL AI API TEST SUITE")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Latest Endpoint", test_sentinel_latest()))
    results.append(("History Endpoint", test_sentinel_history()))
    results.append(("Threat Level Logic", test_threat_level_calculation()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print("\n⚠️  SOME TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
