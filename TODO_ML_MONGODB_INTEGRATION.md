# TODO: Connect Advanced ML Features to MongoDB

## Problem Statement
The 5 advanced ML features are implemented but loading data from CSV files instead of MongoDB's real-time data. This means:
- LSTM Predictor reads from `data/hourly_features.csv`
- Anomaly Detector reads from `data/hourly_features.csv`
- Causal Discovery reads from `data/hourly_features.csv`
- AI Report Generator reads from `data/hourly_features.csv`
- Sentiment Momentum reads from `data/hourly_features.csv`

## Current Architecture

### Data Flow (Broken)
```
MongoDB (global_features collection)
    ↓
[No connection - ML modules don't use MongoDB]
    ↓
CSV Files (data/hourly_features.csv)
    ↓
ML Modules (lstm_predictor, anomaly_detector, etc.)
```

### MongoDB Data Structure
From `database/mongo.py`:
```
python
# Collection: global_features
{
    "timestamp": datetime,
    "version": int,
    "mode": "online" | "offline",
    "features": {
        "timestamp": datetime,
        "news_sentiment": float,
        "news_sentiment_std": float,
        "gdelt_sentiment": float,
        "gdelt_sentiment_std": float,
        "crypto_return": float,
        "crypto_volatility": float,
        "stock_return": float,
        "stock_volatility": float,
        "weather_anomaly": float,
        "global_risk_score": float,
        "top_topics": list
    }
}
```

## Implementation Plan

### Phase 1: Update Data Loading Functions
**Files to modify:**
- `machine_learning/advanced_analytics.py` - Main integration module

**Changes:**
1. Add MongoDB connection import
2. Create `load_features_from_mongodb()` function
3. Convert nested MongoDB documents to flat DataFrame
4. Add fallback to CSV if MongoDB is empty
5. Update all sub-module loaders to use new function

### Phase 2: Test Data Pipeline
**Actions:**
1. Verify MongoDB connection works
2. Test data extraction from `global_features` collection
3. Validate DataFrame conversion
4. Check for missing/null values

### Phase 3: Update Individual ML Modules (if needed)
**Files to check:**
- `machine_learning/lstm_predictor.py` - Update `load_features_data()`
- `machine_learning/anomaly_detector.py` - Update `load_features_data()`
- `machine_learning/causal_discovery.py` - Update data loader
- `processing/ai_report_generator.py` - Update data loader
- `processing/sentiment_momentum.py` - Update data loader

### Phase 4: Backend API Integration
**File:** `backend/main.py` or `backend/advanced_integration.py`

**Actions:**
1. Add new endpoint `/api/advanced-analytics/mongodb`
2. Connect to MongoDB-based ML pipeline
3. Test end-to-end flow

## Detailed Changes

### Step 1: Modify `machine_learning/advanced_analytics.py`

```
python
# Add to imports
from database.mongo import get_historical_global_features
import pandas as pd

# New function to add:
def load_features_from_mongodb(limit=500, mode="online") -> pd.DataFrame:
    """Load features from MongoDB global_features collection"""
    try:
        docs = get_historical_global_features(limit=limit, mode=mode)
        if not docs:
            return None
        
        # Extract features from nested structure
        rows = []
        for doc in docs:
            features = doc.get("features", doc)
            row = {
                "timestamp": doc.get("timestamp"),
                "news_sentiment": features.get("news_sentiment"),
                "gdelt_sentiment": features.get("gdelt_sentiment"),
                "crypto_return": features.get("crypto_return"),
                "crypto_volatility": features.get("crypto_volatility"),
                "stock_return": features.get("stock_return"),
                "stock_volatility": features.get("stock_volatility"),
                "weather_anomaly": features.get("weather_anomaly"),
                "global_risk_score": features.get("global_risk_score"),
            }
            rows.append(row)
        
        df = pd.DataFrame(rows)
        return df
    except Exception as e:
        print(f"MongoDB load error: {e}")
        return None
```

### Step 2: Update Data Loading Logic

Replace the CSV loader with:
```
python
def load_features_data() -> pd.DataFrame:
    """Load hourly features - prefers MongoDB, falls back to CSV"""
    # Try MongoDB first
    df = load_features_from_mongodb(limit=500)
    if df is not None and len(df) > 10:
        return df
    
    # Fallback to CSV
    # ... existing CSV loading code
```

## Dependencies
- `pymongo` - Already in requirements.txt
- `database.mongo` - Already exists

## Testing Checklist
- [ ] MongoDB connection works
- [ ] Data loads from `global_features` collection
- [ ] DataFrame has correct columns
- [ ] ML modules run with MongoDB data
- [ ] Frontend displays results from real data

## Expected Result
```
MongoDB (global_features collection)
    ↓
load_features_from_mongodb()
    ↓
pandas DataFrame
    ↓
ML Modules (all 5 features)
    ↓
Real-time predictions & analysis
```

## Files to Modify
1. `machine_learning/advanced_analytics.py` - PRIMARY (add MongoDB loader)
2. `machine_learning/lstm_predictor.py` - May need minor update
3. `machine_learning/anomaly_detector.py` - May need minor update
4. `backend/main.py` - Add API endpoint (optional)

## Follow-up Steps After Implementation
1. Run ML pipeline with MongoDB data
2. Verify predictions are based on real data
3. Monitor for data quality issues
4. Add data validation checks
5. Set up periodic model retraining with new data
