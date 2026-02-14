# -*- coding: utf-8 -*-
"""
World Pulse Orchestrator
Integrated ML Engine + Feature Store + Model Registry
Phase 6+7 (MLOps Architecture)
"""

import sys, os, time, traceback, logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import joblib
from email.mime.text import MIMEText
import smtplib

# -------------------------------
# Safe UTF-8 stdout/stderr
# -------------------------------
try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
except Exception:
    pass

print("🚀 World Pulse Orchestrator starting with MLOps stack...", flush=True)

# -------------------------------
# CONFIG
# -------------------------------
FEATURES_PATH = "./data/hourly_features.csv"
COUNTRY_FEATURES_PATH = "./data/country_features.csv"
LOG_DIR = "./logs"
LOG_FILE = os.path.join(LOG_DIR, "orchestrator.log")
os.makedirs(LOG_DIR, exist_ok=True)

ALERT_THRESHOLD_HIGH = 0.75
ALERT_THRESHOLD_MED = 0.40
CHECK_INTERVAL = 60*60  # 1 hour

EMAIL_ALERT = False
EMAIL_TO = "you@example.com"
EMAIL_FROM = "worldpulse.ai@example.com"
SMTP_SERVER = "smtp.example.com"
SMTP_PORT = 587
SMTP_USER = "smtp_user"
SMTP_PASS = "smtp_password"

FEATURE_COLUMNS = [
    "news_sentiment",
    "gdelt_sentiment",
    "crypto_return",
    "crypto_volatility",
    "stock_return",
    "stock_volatility",
    "weather_anomaly"
]

# -------------------------------
# Logging
# -------------------------------
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def log_event(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {msg}\n")

# -------------------------------
# Email Alert
# -------------------------------
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
        log_event("📧 Email alert sent!")
    except Exception as e:
        log_event(f"❌ Failed to send email: {e}")

# -------------------------------
# Feature Store
# -------------------------------
from feature_store.feature_store import FeatureStore
fs = FeatureStore()

# -------------------------------
# Model Registry (NEW)
# -------------------------------
from feature_store.model_registry import get_production_model

# -------------------------------
# ML Engine
# -------------------------------
def load_model():
    """
    Load production model from Model Registry
    """
    prod_model_path = get_production_model()

    # Fallback safety
    if prod_model_path is None or not os.path.exists(prod_model_path):
        log_event("⚠️ No production model in registry. Falling back to ./models/gb_model.pkl")
        fallback = "./models/gb_model.pkl"
        if not os.path.exists(fallback):
            raise FileNotFoundError("No production model and no fallback model found")
        model = joblib.load(fallback)
        return model

    log_event(f"🧠 Loading Production Model: {prod_model_path}")
    model = joblib.load(prod_model_path)
    log_event("✅ Production model loaded")
    return model

def classify_risk(prob):
    if prob >= ALERT_THRESHOLD_HIGH:
        return "🔴 CRITICAL", "GLOBAL CRISIS IMMINENT"
    elif prob >= ALERT_THRESHOLD_MED:
        return "🟠 ELEVATED", "INSTABILITY DETECTED"
    else:
        return "🟢 LOW", "STABLE SYSTEM"

def compute_forecast(latest, days=7):
    forecasts = []
    for _ in range(days):
        row = latest.copy()
        for col in FEATURE_COLUMNS:
            row[col] += np.random.normal(0, 0.02)
        forecasts.append(row)
    return pd.DataFrame(forecasts)

def detect_anomalies(df):
    anomalies = {}
    for col in FEATURE_COLUMNS:
        if col in df.columns:
            z_scores = (df[col] - df[col].mean()) / (df[col].std() + 1e-9)
            anomalies[col] = df[col][abs(z_scores) > 2].tolist()
    return anomalies

def run_ml_engine():
    try:
        model = load_model()

        # --- Load latest features ---
        try:
            df_features = fs.read_global()
            if not df_features.empty:
                latest = df_features.iloc[-1]
                log_event("✅ Loaded latest features from Feature Store")
            else:
                latest = pd.read_csv(FEATURES_PATH).iloc[-1]
                log_event("⚠️ Feature Store empty, loaded CSV features")
        except Exception as e:
            latest = pd.read_csv(FEATURES_PATH).iloc[-1]
            log_event(f"⚠️ Feature Store read failed: {e}")

        if latest is None:
            log_event("❌ Latest features not available")
            return

        X = pd.DataFrame([latest[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
        prob = model.predict_proba(X)[0][1]
        level, message = classify_risk(prob)

        # Forecast
        forecast_df = compute_forecast(latest, days=7)
        forecast_probs = [model.predict_proba(forecast_df.iloc[[i]][FEATURE_COLUMNS])[0,1] for i in range(len(forecast_df))]

        # Country risk
        try:
            country_df = fs.read_country()
            if country_df.empty:
                country_df = pd.read_csv(COUNTRY_FEATURES_PATH)
        except Exception:
            country_df = pd.read_csv(COUNTRY_FEATURES_PATH)

        country_risks = {}
        for _, row in country_df.iterrows():
            x_country = row[FEATURE_COLUMNS].values.reshape(1,-1)
            p = model.predict_proba(x_country)[0,1]
            country_risks[row["country"]] = round(float(p), 3)

        # Anomalies
        df_history = pd.read_csv(FEATURES_PATH)
        anomalies = detect_anomalies(df_history)

        # Logging
        ts = datetime.now(timezone.utc).isoformat()
        log_event(f"Time: {ts}")
        log_event(f"Crisis Probability: {prob:.4f} | Risk Level: {level}")
        log_event(f"7-Day Forecast: {[round(p,3) for p in forecast_probs]}")
        log_event(f"Country Risks: {country_risks}")
        log_event(f"Anomalies: {anomalies}")
        log_event(f"System Status: {message}")

        # Save to Feature Store
        try:
            fs.write_global(df_history)
            log_event("✅ Features saved to Feature Store")
        except Exception as e:
            log_event(f"⚠️ Failed to save features: {e}")

        if level == "🔴 CRITICAL":
            send_email("🚨 GLOBAL CRISIS ALERT", f"Crisis probability: {prob:.2f}\n{country_risks}")

    except Exception as e:
        log_event(f"❌ ML Engine error: {e}")
        traceback.print_exc()

# -------------------------------
# Orchestrator Pipeline
# -------------------------------
def run_pipeline():
    log_event("Starting World Pulse Pipeline...")

    try:
        from processing import preprocess_data
        preprocess_data.main()
    except Exception as e:
        log_event(f"Preprocessing error: {e}")

    try:
        from processing import nlp_analysis
        nlp_analysis.main()
    except Exception as e:
        log_event(f"NLP error: {e}")

    try:
        from processing.daily_feature_builder import build_hourly_features
        build_hourly_features()
    except Exception as e:
        log_event(f"Daily features error: {e}")

    try:
        from processing import topic_modeling_with_nlp
        topic_modeling_with_nlp.main()
    except Exception as e:
        log_event(f"Topic modeling error: {e}")

    try:
        from processing.global_crisis_detector import detect_crisis
        detect_crisis(email_alert_func=send_email)
    except Exception as e:
        log_event(f"Crisis detector error: {e}")

    run_ml_engine()

# -------------------------------
# Main Loop
# -------------------------------
if __name__ == "__main__":
    print("🧠 World Pulse Autonomous AI System running...", flush=True)
    while True:
        try:
            run_pipeline()
        except Exception as e:
            log_event(f"Monitoring pipeline error: {e}")
        print(f"Sleeping for {CHECK_INTERVAL/60:.0f} minutes...\n", flush=True)
        time.sleep(CHECK_INTERVAL)
