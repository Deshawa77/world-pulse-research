#!/usr/bin/env python3
"""
Test script to verify country map data flow:
1. Check MongoDB country_features collection
2. Test /dashboard/risk-map API endpoint
3. Verify data structure
"""

import requests
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Test configuration
API_URL = "http://127.0.0.1:8000"
API_KEY = "super_secure_api_key"
HEADERS = {"x-api-key": API_KEY}

def test_mongodb_connection():
    """Test direct MongoDB connection to check country_features collection"""
    print("\n" + "="*60)
    print("TEST 1: MongoDB Connection - Checking country_features collection")
    print("="*60)
    
    try:
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client["world_pulse"]
        
        # Check country_features collection
        country_count = db.country_features.count_documents({})
        print(f"✅ MongoDB connected")
        print(f"   - country_features collection: {country_count} documents")
        
        # Show sample documents
        if country_count > 0:
            sample = db.country_features.find_one({"mode": "online"}, sort=[("timestamp", -1)])
            if sample:
                print(f"\n   Sample country document:")
                print(f"   - Country: {sample.get('country', 'N/A')}")
                print(f"   - Timestamp: {sample.get('timestamp', 'N/A')}")
                features = sample.get('features', {})
                print(f"   - Risk Score: {features.get('global_risk_score', 'N/A')}")
                print(f"   - Top Topics: {features.get('top_topics', 'N/A')}")
        
        # Check global_features for comparison
        global_count = db.global_features.count_documents({})
        print(f"\n   - global_features collection: {global_count} documents")
        
        # Check dashboard_features
        dashboard_count = db.dashboard_features.count_documents({})
        print(f"   - dashboard_features collection: {dashboard_count} documents")
        
        client.close()
        return country_count > 0
        
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return False

def test_api_risk_map():
    """Test the /dashboard/risk-map API endpoint"""
    print("\n" + "="*60)
    print("TEST 2: API Endpoint - /dashboard/risk-map")
    print("="*60)
    
    try:
        response = requests.get(
            f"{API_URL}/dashboard/risk-map",
            headers=HEADERS,
            params={"mode": "online"},
            timeout=10
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API call successful")
            print(f"   - Countries returned: {len(data)}")
            
            if data:
                print(f"\n   Sample country from API:")
                sample = data[0]
                print(f"   - Country: {sample.get('country', 'N/A')}")
                print(f"   - Risk: {sample.get('risk', 'N/A')}")
                print(f"   - Timestamp: {sample.get('timestamp', 'N/A')}")
                
                # Validate data structure
                required_fields = ['country', 'risk']
                missing = [f for f in required_fields if f not in sample]
                if missing:
                    print(f"   ⚠️  Missing fields: {missing}")
                else:
                    print(f"   ✅ Data structure valid")
            else:
                print(f"   ⚠️  No country data returned - map will be empty!")
            
            return len(data) > 0
        else:
            print(f"❌ API call failed: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to API at {API_URL}")
        print(f"   Is the backend server running?")
        return False
    except Exception as e:
        print(f"❌ API test failed: {e}")
        return False

def test_api_live_feed():
    """Test the /dashboard/live-feed API endpoint"""
    print("\n" + "="*60)
    print("TEST 3: API Endpoint - /dashboard/live-feed")
    print("="*60)
    
    try:
        response = requests.get(
            f"{API_URL}/dashboard/live-feed",
            headers=HEADERS,
            params={"mode": "online"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Live feed API working")
            print(f"   - Incidents: {len(data.get('incidents', []))}")
            print(f"   - Heartbeat: {data.get('ingestionHeartbeatSec', 'N/A')}s")
            print(f"   - Model Drift: {data.get('modelDrift', 'N/A')}")
            return True
        else:
            print(f"❌ Live feed API failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Live feed test failed: {e}")
        return False

def test_orchestrator_syntax():
    """Test that orchestrator.py has valid Python syntax"""
    print("\n" + "="*60)
    print("TEST 4: Orchestrator Syntax Check")
    print("="*60)
    
    try:
        import py_compile
        py_compile.compile('orchestrator.py', doraise=True)
        print("✅ orchestrator.py syntax is valid")
        return True
    except py_compile.PyCompileError as e:
        print(f"❌ Syntax error in orchestrator.py: {e}")
        return False

def main():
    print("\n" + "="*60)
    print("WORLD PULSE MAP DATA FLOW TEST")
    print("="*60)
    print(f"Started at: {datetime.now().isoformat()}")
    
    results = {
        "mongodb": test_mongodb_connection(),
        "api_risk_map": test_api_risk_map(),
        "api_live_feed": test_api_live_feed(),
        "orchestrator_syntax": test_orchestrator_syntax(),
    }
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status}: {test_name}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED - Map should display country data!")
        print("="*60)
        print("\nNext steps:")
        print("1. Restart the orchestrator to apply changes")
        print("2. Wait 1-2 minutes for data collection")
        print("3. Check the dashboard map - countries should appear with risk colors")
    else:
        print("⚠️  SOME TESTS FAILED - See details above")
        print("="*60)
        if not results["mongodb"]:
            print("\nFix: Ensure MongoDB is running and has country data")
        if not results["api_risk_map"]:
            print("\nFix: Check backend is running and country_features has data")
        if not results["orchestrator_syntax"]:
            print("\nFix: Fix syntax errors in orchestrator.py")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
