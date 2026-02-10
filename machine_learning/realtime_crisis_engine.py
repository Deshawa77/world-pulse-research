# realtime_crisis_engine.py
import pandas as pd
import joblib
import time
from datetime import datetime
import os

# ============================
# CONFIG
# ============================

MODEL_PATH = "../models/gb_model.pkl"
FEATURES_PATH = "../data/hourly_features.csv"
LOG_DIR = "../logs"
ALERT_THRESHOLD_HIGH = 0.75
ALERT_THRESHOLD_MED = 0.40
CHECK_INTERVAL = 3600  # seconds (1 hour)

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


# ============================
# LOAD MODEL
# ============================

def load_model():
    print("🧠 Loading Global Crisis Model...")
    model = joblib.load(MODEL_PATH)
    print("✅ Model loaded")
    return model

# ============================
# LOAD FEATURES
# ============================

def load_latest_features():
    if not os.path.exists(FEATURES_PATH):
        print("❌ No feature file found")
        return None

    df = pd.read_csv(FEATURES_PATH)
    if df.empty:
        print("❌ Feature file empty")
        return None

    latest = df.iloc[-1]
    return latest

# ============================
# RISK ENGINE
# ============================

def classify_risk(prob):
    if prob >= ALERT_THRESHOLD_HIGH:
        return "🔴 CRITICAL", "GLOBAL CRISIS IMMINENT"
    elif prob >= ALERT_THRESHOLD_MED:
        return "🟠 ELEVATED", "INSTABILITY DETECTED"
    else:
        return "🟢 LOW", "STABLE SYSTEM"

# ============================
# LOGGING
# ============================

def log_event(timestamp, prob, level, message):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {prob:.4f} | {level} | {message}\n")

# ============================
# INFERENCE LOOP
# ============================

def realtime_loop():
    print("\n🌍 World Pulse AI Core — Real-Time Crisis Engine Started")
    print("===============================================")

    model = load_model()

    while True:
        try:
            latest = load_latest_features()

            if latest is None:
                time.sleep(CHECK_INTERVAL)
                continue

            X = pd.DataFrame([latest[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)

            prob = model.predict_proba(X)[0][1]
            level, message = classify_risk(prob)

            ts = datetime.utcnow().isoformat()

            # Console output
            print("\n============================")
            print("🌍 LIVE GLOBAL INTELLIGENCE")
            print("============================")
            print(f"Time: {ts}")
            print(f"Crisis Probability: {prob:.4f}")
            print(f"Risk Level: {level}")
            print(f"System Status: {message}")

            # Logging
            log_event(ts, prob, level, message)

            # ALERT SYSTEM
            if level == "🔴 CRITICAL":
                print("🚨🚨🚨 GLOBAL CRISIS ALERT 🚨🚨🚨")
                print("Emergency protocols triggered")
            elif level == "🟠 ELEVATED":
                print("⚠️ Early Warning System Activated")

        except Exception as e:
            print("❌ Engine error:", e)

        time.sleep(CHECK_INTERVAL)

# ============================
# ENTRY POINT
# ============================

if __name__ == "__main__":
    realtime_loop()
