# realtime_crisis_engine.py
import os
import sys
import time
import traceback
from datetime import datetime, timezone

# Add project root to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import joblib
import numpy as np
import smtplib
from email.mime.text import MIMEText
import pandas as pd


# ---------------------------
# INITIAL GLOBAL FEATURES
# ---------------------------
initial_global_features = {
    "news_sentiment": 0.12,
    "gdelt_sentiment": -0.05,
    "crypto_return": 0.03,
    "crypto_volatility": 0.1,
    "stock_return": -0.02,
    "stock_volatility": 0.08,
    "weather_anomaly": 0.15
}

# ============================
# MONGO IMPORT
# ============================
from database.mongo import (
    write_global_features_v2,
    write_country_features_v2,
    db
)

# ============================
# CONFIG
# ============================
MODEL_PATH = "../models/gb_model.pkl"
LOG_DIR = "../logs"

ALERT_THRESHOLD_HIGH = 0.75
ALERT_THRESHOLD_MED = 0.40
CHECK_INTERVAL = 3600  # 1 hour

EMAIL_ALERT = False

os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "crisis_predictions.log")

FEATURE_COLUMNS = [
    "news_sentiment",
    "gdelt_sentiment",
    "crypto_return",
    "crypto_volatility",
    "stock_return",
    "stock_volatility",
    "weather_anomaly"
]

COUNTRIES = ["US", "UK", "DE", "IN", "JP", "CN", "BR"]

# ============================
# UTILITIES
# ============================
def log_event(message):
    ts = datetime.now(timezone.utc).isoformat()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {message}\n")
    print(message)

# ============================
# SAFE WRITE WRAPPERS
# ============================
def safe_write_global(features, mode="online"):
    try:
        write_global_features_v2(features, mode)
    except Exception as e:
        db.pipeline_errors.insert_one({
            "type": "global_feature_write_error",
            "error": str(e),
            "timestamp": datetime.utcnow(),
            "traceback": traceback.format_exc()
        })
        log_event("❌ Global feature write failed")


def safe_write_country(country, features, mode="online"):
    try:
        write_country_features_v2(country, features, mode)
    except Exception as e:
        db.pipeline_errors.insert_one({
            "type": "country_feature_write_error",
            "country": country,
            "error": str(e),
            "timestamp": datetime.utcnow(),
            "traceback": traceback.format_exc()
        })
        log_event(f"❌ Country feature write failed for {country}")

# ============================
# FEATURE RETENTION CLEANUP
# ============================
def cleanup_old_global_features(mode="online", keep_last=100):
    cursor = db.global_features.find(
        {"mode": mode}
    ).sort("version", -1)

    versions = [doc["version"] for doc in cursor if "version" in doc]

    if len(versions) > keep_last:
        versions_to_delete = versions[keep_last:]
        result = db.global_features.delete_many({
            "mode": mode,
            "version": {"$in": versions_to_delete}
        })
        log_event(f"🧹 Deleted {result.deleted_count} old GLOBAL versions")


def cleanup_old_country_features(country, mode="online", keep_last=100):
    cursor = db.country_features.find(
        {"country": country, "mode": mode}
    ).sort("version", -1)

    versions = [doc["version"] for doc in cursor if "version" in doc]

    if len(versions) > keep_last:
        versions_to_delete = versions[keep_last:]
        result = db.country_features.delete_many({
            "country": country,
            "mode": mode,
            "version": {"$in": versions_to_delete}
        })
        log_event(f"🧹 Deleted {result.deleted_count} old versions for {country}")

# ============================
# MODEL LOAD
# ============================
def load_model():
    print("🧠 Loading Global Crisis Model...")
    model = joblib.load(MODEL_PATH)
    print("✅ Model loaded")
    return model

# ============================
# DATA LOADERS
# ============================
def load_latest_global():
    """
    Load the latest global features from Mongo.

    Supports both:
    1. Nested 'features' document
    2. Flat old-style documents
    Fills missing keys with 0.0
    """
    doc = db.global_features.find({"mode": "online"}).sort("timestamp", -1).limit(1)
    docs = list(doc)
    if not docs:
        return None

    latest = docs[0]

    # Extract features
    if "features" in latest:
        features = latest["features"]
    else:
        # Old-style flat document: only keep FEATURE_COLUMNS
        features = {k: v for k, v in latest.items() if k in FEATURE_COLUMNS}

    # Fill missing keys with 0.0
    for col in FEATURE_COLUMNS:
        if col not in features:
            log_event(f"⚠️ Key '{col}' missing in Mongo document — filling with default 0.0")
            features[col] = 0.0

    return features


def load_country_features():
    """
    Load all country-level features from Mongo.
    If none exist, populate with random initial values.
    """
    docs = list(db.country_features.find({"mode": "online"}))

    if not docs:
        for c in COUNTRIES:
            features = {
                col: float(np.random.uniform(-1, 1))
                for col in FEATURE_COLUMNS
            }
            safe_write_country(c, features, mode="online")

        docs = list(db.country_features.find({"mode": "online"}))

    extracted = []
    for d in docs:
        f = d.get("features", d)
        f["country"] = d.get("country", "UNKNOWN")
        extracted.append(f)

    return extracted


# ============================
# LOAD LATEST GLOBAL FEATURES
# ============================
latest_features = load_latest_global()

# If nothing in Mongo, insert initial features
if latest_features is None:
    log_event("No global features found — inserting initial features")
    safe_write_global(initial_global_features, mode="online")
    latest_features = initial_global_features.copy()

# Only keep numeric ML features
latest_features = {k: v for k, v in latest_features.items() if k in FEATURE_COLUMNS}

# DEBUG log before ML
log_event(f"[DEBUG] Features used for realtime engine: {latest_features}")



# ============================
# RISK CLASSIFICATION
# ============================
def classify_risk(prob):
    if prob >= ALERT_THRESHOLD_HIGH:
        return "🔴 CRITICAL", "GLOBAL CRISIS IMMINENT"
    elif prob >= ALERT_THRESHOLD_MED:
        return "🟠 ELEVATED", "INSTABILITY DETECTED"
    else:
        return "🟢 LOW", "STABLE SYSTEM"

# ============================
# FORECAST ENGINE
# ============================
def compute_forecast(latest, days=7):
    forecasts = []
    base = latest.copy()
    for _ in range(days):
        row = base.copy()
        for col in FEATURE_COLUMNS:
            row[col] += np.random.normal(0, 0.02)
        forecasts.append(row)
    return forecasts

# ============================
# REALTIME ENGINE LOOP
# ============================
def realtime_loop():
    print("\n🌍 World Pulse AI Core — Real-Time Crisis Engine Started")
    print("===============================================")

    model = load_model()

    while True:
        try:
            latest_features = load_latest_global()

            if latest_features is None:
                log_event("No global features found — inserting initial features")
                safe_write_global(initial_global_features, mode="online")
                cleanup_old_global_features()
                time.sleep(CHECK_INTERVAL)
                continue

            # Save versioned snapshot safely
            safe_write_global(latest_features, mode="online")
            cleanup_old_global_features()

            X = pd.DataFrame([{k: latest_features[k] for k in FEATURE_COLUMNS}])
            prob = float(model.predict_proba(X)[0][1])
            level, message = classify_risk(prob)

            # Forecast
            forecast_rows = compute_forecast(latest_features, days=7)
            forecast_probs = [
                float(model.predict_proba(pd.DataFrame([row]))[0][1])
                for row in forecast_rows
            ]

            # Country risks
            country_docs = load_country_features()
            country_risks = {}

            for row in country_docs:
                safe_write_country(
                    row["country"],
                    {k: row[k] for k in FEATURE_COLUMNS},
                    mode="online"
                )

                cleanup_old_country_features(row["country"])

                Xc = pd.DataFrame([{k: row[k] for k in FEATURE_COLUMNS}])
                p = float(model.predict_proba(Xc)[0][1])
                country_risks[row["country"]] = round(p, 3)

            ts = datetime.now(timezone.utc).isoformat()
            log_event(f"Time: {ts}")
            log_event(f"Crisis Probability: {prob:.4f} | Risk Level: {level}")
            log_event(f"7-Day Forecast: {[round(p,3) for p in forecast_probs]}")
            log_event(f"Country Risks: {country_risks}")
            log_event(f"System Status: {message}\n")

        except Exception as e:
            db.pipeline_errors.insert_one({
                "type": "engine_runtime_error",
                "error": str(e),
                "timestamp": datetime.utcnow(),
                "traceback": traceback.format_exc()
            })
            log_event(f"ENGINE ERROR: {str(e)}")

        time.sleep(CHECK_INTERVAL)


# ============================
# ENTRY POINT
# ============================
if __name__ == "__main__":
    if load_latest_global() is None:
        safe_write_global(initial_global_features, mode="online")
        cleanup_old_global_features()

    realtime_loop()
