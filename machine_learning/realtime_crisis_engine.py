# realtime_crisis_engine.py

import pandas as pd
import joblib
import time
from datetime import datetime, timezone
import os
import numpy as np
import smtplib
from email.mime.text import MIMEText

# ============================
# CONFIG
# ============================

MODEL_PATH = "../models/gb_model.pkl"
FEATURES_PATH = "../data/hourly_features.csv"
COUNTRY_FEATURES_PATH = "../data/country_features.csv"
LOG_DIR = "../logs"

ALERT_THRESHOLD_HIGH = 0.75
ALERT_THRESHOLD_MED = 0.40
CHECK_INTERVAL = 3600  # 1 hour

# ---- EMAIL CONFIG ----
EMAIL_ALERT = False   # turn True when SMTP ready
EMAIL_TO = "you@example.com"
EMAIL_FROM = "worldpulse.ai@example.com"
SMTP_SERVER = "smtp.example.com"
SMTP_PORT = 587
SMTP_USER = "smtp_user"
SMTP_PASS = "smtp_password"

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
# AUTO COUNTRY DATA GENERATOR (OPTION 2)
# ============================

def generate_fake_country_data():
    print("⚠️ country_features.csv not found — generating fake country data...")
    rows = []
    for c in COUNTRIES:
        rows.append({
            "country": c,
            "news_sentiment": np.random.uniform(-1, 1),
            "gdelt_sentiment": np.random.uniform(-1, 1),
            "crypto_return": np.random.uniform(-0.05, 0.05),
            "crypto_volatility": np.random.uniform(0, 0.2),
            "stock_return": np.random.uniform(-0.05, 0.05),
            "stock_volatility": np.random.uniform(0, 0.2),
            "weather_anomaly": np.random.uniform(0, 1),
        })

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(COUNTRY_FEATURES_PATH), exist_ok=True)
    df.to_csv(COUNTRY_FEATURES_PATH, index=False)
    print("✅ Fake country_features.csv created")

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

def load_latest_features():
    if not os.path.exists(FEATURES_PATH):
        print("❌ No hourly_features.csv found")
        return None
    df = pd.read_csv(FEATURES_PATH)
    if df.empty:
        print("❌ hourly_features.csv is empty")
        return None
    return df.iloc[-1], df

def load_country_features():
    if not os.path.exists(COUNTRY_FEATURES_PATH):
        generate_fake_country_data()
    return pd.read_csv(COUNTRY_FEATURES_PATH)

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
# ALERT SYSTEM
# ============================

def send_email(subject, body):
    if not EMAIL_ALERT:
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print("📧 Email alert sent!")
    except Exception as e:
        print(f"❌ Email alert failed: {e}")

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
    return pd.DataFrame(forecasts)

# ============================
# ANOMALY DETECTION
# ============================

def detect_anomalies(df):
    anomalies = {}
    for col in FEATURE_COLUMNS:
        z = (df[col] - df[col].mean()) / (df[col].std() + 1e-9)
        anomalies[col] = df[col][abs(z) > 2].tolist()
    return anomalies

# ============================
# REALTIME ENGINE LOOP
# ============================

def realtime_loop():
    print("\n🌍 World Pulse AI Core — Real-Time Crisis Engine Started")
    print("===============================================")

    model = load_model()

    while True:
        try:
            latest, history_df = load_latest_features()
            if latest is None:
                time.sleep(CHECK_INTERVAL)
                continue

            X = pd.DataFrame([latest[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
            prob = model.predict_proba(X)[0][1]
            level, message = classify_risk(prob)

            # ---- 7 DAY FORECAST ----
            forecast_df = compute_forecast(latest, days=7)
            forecast_probs = []
            for i in range(len(forecast_df)):
                Xf = pd.DataFrame([forecast_df.iloc[i][FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
                forecast_probs.append(float(model.predict_proba(Xf)[0][1]))

            # ---- COUNTRY RISKS ----
            country_df = load_country_features()
            country_risks = {}
            for _, row in country_df.iterrows():
                Xc = pd.DataFrame([row[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
                p = float(model.predict_proba(Xc)[0][1])
                country_risks[row["country"]] = round(p, 3)

            # ---- ANOMALIES ----
            anomalies = detect_anomalies(history_df)

            ts = datetime.now(timezone.utc).isoformat()

            log_event(f"Time: {ts}")
            log_event(f"Crisis Probability: {prob:.4f} | Risk Level: {level}")
            log_event(f"7-Day Forecast: {[round(p,3) for p in forecast_probs]}")
            log_event(f"Country Risks: {country_risks}")
            log_event(f"Anomalies: {anomalies}")
            log_event(f"System Status: {message}\n")

            # ---- ALERT ----
            if level == "🔴 CRITICAL":
                send_email(
                    "🚨 GLOBAL CRISIS ALERT",
                    f"Crisis Probability: {prob:.2f}\n\nCountry Risks:\n{country_risks}"
                )

        except Exception as e:
            log_event(f"ENGINE ERROR: {str(e)}")

        time.sleep(CHECK_INTERVAL)

# ============================
# ENTRY POINT
# ============================

if __name__ == "__main__":
    realtime_loop()
