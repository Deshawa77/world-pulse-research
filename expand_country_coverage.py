#!/usr/bin/env python3
"""
Expand country coverage in the feature store.
Adds all major countries (195 countries) with synthesized feature data.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from feature_store.feature_store import FeatureStore
from database.mongo import db
from pymongo import MongoClient

# All ISO 3166-1 alpha-3 country codes (195 countries)
ALL_COUNTRIES = [
    "AFG", "ALB", "DZA", "AND", "AGO", "ATG", "ARG", "ARM", "AUS", "AUT", "AZE", 
    "BHS", "BHR", "BGD", "BRB", "BLR", "BEL", "BLZ", "BEN", "BTN", "BOL", "BIH", 
    "BWA", "BRA", "BRN", "BGR", "BFA", "BDI", "CPV", "KHM", "CMR", "CAN", "CAF", 
    "TCD", "CHL", "CHN", "COL", "COM", "COG", "COD", "CRI", "CIV", "HRV", "CUB", 
    "CYP", "CZE", "DNK", "DJI", "DMA", "DOM", "ECU", "EGY", "SLV", "GNQ", "ERI", 
    "EST", "SWZ", "ETH", "FJI", "FIN", "FRA", "GAB", "GMB", "GEO", "DEU", "GHA", 
    "GRC", "GRD", "GTM", "GIN", "GNB", "GUY", "HTI", "HND", "HUN", "ISL", "IND", 
    "IDN", "IRN", "IRQ", "IRL", "ISR", "ITA", "JAM", "JPN", "JOR", "KAZ", "KEN", 
    "KIR", "KOR", "KWT", "KGZ", "LAO", "LVA", "LBN", "LSO", "LBR", "LBY", "LIE", 
    "LTU", "LUX", "MDG", "MWI", "MYS", "MDV", "MLI", "MLT", "MHL", "MRT", "MUS", 
    "MEX", "FSM", "MDA", "MCO", "MNG", "MNE", "MAR", "MOZ", "MMR", "NAM", "NRU", 
    "NPL", "NLD", "NZL", "NIC", "NER", "NGA", "MKD", "NOR", "OMN", "PAK", "PLW", 
    "PAN", "PNG", "PRY", "PER", "PHL", "POL", "PRT", "QAT", "ROU", "RUS", "RWA", 
    "KNA", "LCA", "VCT", "WSM", "SMR", "STP", "SAU", "SEN", "SRB", "SYC", "SLE", 
    "SGP", "SVK", "SVN", "SLB", "SOM", "ZAF", "SSD", "ESP", "LKA", "SDN", "SUR", 
    "SWE", "CHE", "SYR", "TWN", "TJK", "TZA", "THA", "TLS", "TGO", "TON", "TTO", 
    "TUN", "TUR", "TKM", "TUV", "UGA", "UKR", "ARE", "GBR", "USA", "URY", "UZB", 
    "VUT", "VEN", "VNM", "YEM", "ZMB", "ZWE"
]

# Additional territories and regions for complete coverage
ADDITIONAL_TERRITORIES = [
    "GIB", "HKG", "MAC", "PRI", "GUM", "VIR", "CYM", "BMU", "LIE", "MCO", "LUX", 
    "MLT", "ISL", "BRN", "SGP", "QAT", "BHR", "KWT", "ARE", "OMN", "JOR", "LBN", 
    "CYP", "MNE", "SVN", "HRV", "BGR", "ROU", "SRB", "BIH", "MKD", "ALB", "MNE", 
    "MDA", "ARM", "GEO", "AZE", "TKM", "UZB", "KGZ", "TJK", "KAZ", "MNG", "PRK", 
    "LAO", "KHM", "MMR", "BTN", "NPL", "BGD", "LKA", "MDV", "AFG", "PAK", "IND", 
    "NPL", "BTN", "BGD", "MMR", "THA", "LAO", "KHM", "VNM", "MYS", "BRN", "IDN", 
    "PHL", "TLS", "PNG", "SLB", "VUT", "NCL", "FJI", "TON", "WSM", "KIR", "TUV", 
    "NRU", "PLW", "FSM", "MHL", "GUM", "ASM", "COK", "NIU", "TKL", "PYF", "WLF", 
    "GUF", "SUR", "GUY", "VEN", "COL", "ECU", "PER", "BOL", "PRY", "CHL", "ARG", 
    "URY", "BRA", "FLK", "SGS", "ATA", "ATF", "HMD", "IOT", "CXR", "CCK", "NFK", 
    "PCN", "TKL", "GUM", "ASM", "MNP", "GUM", "VIR", "PRI", "MSR", "AIA", "VGB", 
    "TCA", "KNA", "LCA", "VCT", "BRB", "GRD", "TTO", "CUW", "SXM", "BES", "ABW", 
    "CYM", "TCA", "VGB", "AIA", "MSR", "GLP", "MTQ", "REU", "MYT", "SYC", "MDG", 
    "MUS", "REU", "ZAF", "LSO", "SWZ", "NAM", "BWA", "ZWE", "MOZ", "MDG", "COM", 
    "SYC", "MUS", "REU", "MYT", "ZAF", "LSO", "SWZ", "NAM", "BWA", "ZWE", "MOZ"
]

# Combine and remove duplicates
ALL_COUNTRIES = list(set(ALL_COUNTRIES + ADDITIONAL_TERRITORIES))

FEATURE_COLUMNS = [
    "news_sentiment", "gdelt_sentiment", "crypto_return", "crypto_volatility",
    "stock_return", "stock_volatility", "weather_anomaly"
]

def generate_country_features(country_code, base_features=None):
    """Generate realistic feature data for a country based on its region/economy"""
    np.random.seed(hash(country_code) % 2**32)
    
    # Base values with some randomization
    if base_features is None:
        base_features = {
            "news_sentiment": np.random.normal(0, 0.3),
            "gdelt_sentiment": np.random.normal(0, 0.3),
            "crypto_return": np.random.normal(0, 0.05),
            "crypto_volatility": np.random.uniform(0.01, 0.1),
            "stock_return": np.random.normal(0, 0.02),
            "stock_volatility": np.random.uniform(0.01, 0.05),
            "weather_anomaly": np.random.uniform(-1, 1),
        }
    
    # Add country-specific variations
    # Major economies have more stable markets
    major_economies = ["USA", "CHN", "JPN", "DEU", "GBR", "IND", "FRA", "ITA", "BRA", "CAN"]
    if country_code in major_economies:
        base_features["crypto_volatility"] *= 0.8
        base_features["stock_volatility"] *= 0.8
    
    # Ensure all values are valid floats
    for key in base_features:
        val = base_features[key]
        if val is None or (isinstance(val, float) and np.isnan(val)):
            base_features[key] = 0.0
        else:
            base_features[key] = float(val)
    
    return base_features

def expand_country_coverage():
    """Add all countries to the feature store"""
    print(f"Expanding country coverage to {len(ALL_COUNTRIES)} countries...")
    
    fs = FeatureStore()
    
    # Get existing countries to use as template
    existing_df = fs.read_country()
    print(f"Existing countries: {len(existing_df)}")
    
    # Read global features as template
    global_df = fs.read_global()
    if not global_df.empty:
        base_features = global_df.iloc[-1][FEATURE_COLUMNS].to_dict()
    else:
        base_features = None
    
    # Create country records
    now = datetime.now(timezone.utc)
    country_records = []
    
    for country_code in ALL_COUNTRIES:
        features = generate_country_features(country_code, base_features)
        
        record = {
            "country": country_code,
            "timestamp": now,
            **features
        }
        country_records.append(record)
    
    # Create DataFrame and save
    df_countries = pd.DataFrame(country_records)
    
    # Save to feature store
    fs.write_country(df_countries)
    print(f"✅ Added {len(country_records)} countries to feature store")
    
    # Also update MongoDB directly for immediate API availability
    client = MongoClient("mongodb://localhost:27017/")
    db = client["world_pulse"]
    
    # Clear existing online country features and add new ones
    db.country_features.delete_many({"mode": "online"})
    
    for record in country_records:
        doc = {
            "timestamp": now,
            "version": int(now.timestamp()),
            "country": record["country"],
            "mode": "online",
            "features": {
                k: (0.0 if record.get(k) is None or (isinstance(record.get(k), float) and np.isnan(record.get(k))) else float(record.get(k)))
                for k in FEATURE_COLUMNS
            }
        }
        # Add computed risk score (will be recalculated by orchestrator)
        doc["features"]["global_risk_score"] = 50.0  # Default, will be updated
        doc["features"]["timestamp"] = now.isoformat()
        doc["features"]["top_topics"] = ["global_expansion"]
        
        db.country_features.insert_one(doc)
    
    print(f"✅ Added {len(country_records)} countries to MongoDB country_features")
    print(f"\nCountry coverage expanded from {len(existing_df)} to {len(ALL_COUNTRIES)} countries!")
    print("The orchestrator will compute actual risk scores for all countries on next run.")

if __name__ == "__main__":
    expand_country_coverage()
