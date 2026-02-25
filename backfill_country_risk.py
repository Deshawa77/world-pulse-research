#!/usr/bin/env python3
"""
Backfill script to add risk scores to existing country documents in MongoDB.
This ensures the map displays properly with existing data.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from pymongo import MongoClient, DESCENDING
from datetime import datetime
import traceback

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["world_pulse"]

# Feature columns used for risk calculation
FEATURE_COLUMNS = [
    "news_sentiment", "gdelt_sentiment", "crypto_return", "crypto_volatility",
    "stock_return", "stock_volatility", "weather_anomaly"
]

def load_models():
    """Load ML models for risk scoring"""
    try:
        from feature_store.load_models import load_all_models
        models = load_all_models()
        print(f"✅ Loaded {len(models)} models")
        return models
    except Exception as e:
        print(f"❌ Failed to load models: {e}")
        return None

def compute_risk_score(models, features):
    """Compute risk score using ML models"""
    try:
        from orchestrator import compute_model_risk_score
        return compute_model_risk_score(models, features)
    except Exception as e:
        # Fallback calculation
        try:
            row = {}
            for col in FEATURE_COLUMNS:
                value = features.get(col, 0.0)
                row[col] = 0.0 if value is None or pd.isna(value) else float(value)
            
            X = pd.DataFrame([row], columns=FEATURE_COLUMNS)
            probs = [m.predict_proba(X)[0, 1] for m in models.values() if hasattr(m, "predict_proba")]
            if not probs:
                return 50.0
            return round(float(np.mean(probs) * 100), 2)
        except Exception as e2:
            print(f"   Risk calculation failed: {e2}")
            return 50.0

def backfill_country_risk():
    """Add risk scores to country documents that don't have them"""
    print("="*70)
    print("COUNTRY RISK BACKFILL SCRIPT")
    print("="*70)
    print(f"Started at: {datetime.now().isoformat()}")
    
    # Load models
    models = load_models()
    if not models:
        print("❌ Cannot proceed without models")
        return False
    
    # Find all country documents without global_risk_score
    print("\n1. Finding country documents without risk scores...")
    
    # Get all unique countries
    pipeline = [
        {"$match": {"mode": "online"}},
        {"$group": {"_id": "$country", "count": {"$sum": 1}}}
    ]
    countries = list(db.country_features.aggregate(pipeline))
    print(f"   Found {len(countries)} unique countries")
    
    updated_count = 0
    failed_count = 0
    
    for country_info in countries:
        country_code = country_info["_id"]
        
        # Get the latest document for this country
        doc = db.country_features.find_one(
            {"country": country_code, "mode": "online"},
            sort=[("timestamp", DESCENDING)]
        )
        
        if not doc:
            continue
        
        features = doc.get("features", {})
        
        # Check if already has risk score
        if features.get("global_risk_score") is not None:
            continue
        
        # Compute risk score
        try:
            risk_score = compute_risk_score(models, features)
            
            # Update the document
            result = db.country_features.update_one(
                {"_id": doc["_id"]},
                {"$set": {"features.global_risk_score": risk_score}}
            )
            
            if result.modified_count > 0:
                print(f"   ✅ {country_code}: risk={risk_score}")
                updated_count += 1
            else:
                print(f"   ⚠️  {country_code}: no update needed")
                
        except Exception as e:
            print(f"   ❌ {country_code}: failed - {e}")
            failed_count += 1
    
    print(f"\n2. Backfill complete!")
    print(f"   - Updated: {updated_count} countries")
    print(f"   - Failed: {failed_count} countries")
    
    # Verify the fix
    print("\n3. Verifying fix...")
    test_doc = db.country_features.find_one(
        {"mode": "online", "features.global_risk_score": {"$exists": True}},
        sort=[("timestamp", DESCENDING)]
    )
    
    if test_doc:
        print(f"   ✅ Sample document now has risk score:")
        print(f"      Country: {test_doc.get('country')}")
        print(f"      Risk: {test_doc.get('features', {}).get('global_risk_score')}")
    else:
        print(f"   ⚠️  No documents with risk score found yet")
    
    # Test the API
    print("\n4. Testing API...")
    import requests
    try:
        response = requests.get(
            "http://127.0.0.1:8000/dashboard/risk-map",
            headers={"x-api-key": "super_secure_api_key"},
            params={"mode": "online"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            valid_countries = [c for c in data if c.get('risk') is not None]
            print(f"   ✅ API returns {len(data)} countries")
            print(f"   ✅ {len(valid_countries)} have valid risk scores")
            
            if valid_countries:
                print(f"\n   Sample with risk score:")
                sample = valid_countries[0]
                print(f"   - {sample.get('country')}: risk={sample.get('risk')}")
        else:
            print(f"   ❌ API error: {response.status_code}")
    except Exception as e:
        print(f"   ❌ API test failed: {e}")
    
    print("\n" + "="*70)
    print("BACKFILL COMPLETE")
    print("="*70)
    print(f"Finished at: {datetime.now().isoformat()}")
    
    return updated_count > 0

if __name__ == "__main__":
    try:
        success = backfill_country_risk()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)
