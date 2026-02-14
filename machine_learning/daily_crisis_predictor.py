# -*- coding: utf-8 -*-
"""
World Pulse Orchestrator with all ML Engines Integrated
- Realtime Crisis Engine
- Daily Crisis Predictor
- Live Predictor
Phase 6+
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
# UTF-8 stdout/stderr for Windows
# -------------------------------
try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
except Exception:
    pass

print("🚀 World Pulse Orchestrator starting with ML Engines...", flush=True)

# -------------------------------
# CONFIG
# -------------------------------
MODEL_DIR = "./models"
DATA_DIR = "./data"
LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)

MODEL_REALTIME = os.path.join(MODEL_DIR, "gb_model.pkl")
MODEL_DAILY = os.path.join(MODEL_DIR, "daily_model.pkl")
MODEL_LIVE = os.path.join(MODEL_DIR, "live_model.pkl")

FEATURES_PATH = os.path.join(DATA_DIR, "hourly_features.csv")
COUNTRY_FEATURES_PATH = os.path.join(DATA_DIR, "country_features.csv")
LOG_FILE = os.path.join(LOG_DIR, "orchestrator.log")

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
# Email Alerts
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
# Risk Classification
# -------------------------------
def classify_risk(prob):
    if prob >= ALERT_THRESHOLD_HIGH:
        return "🔴 CRITICAL", "GLOBAL CRISIS IMMINENT"
    elif prob >= ALERT_THRESHOLD_MED:
        return "🟠 ELEVATED", "INSTABILITY DETECTED"
    else:
        return "🟢 LOW", "STABLE SYSTEM"

# -------------------------------
# ML Engine Utilities
# -------------------------------
def load_model(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found")
    model = joblib.load(path)
    log_event(f"✅ Loaded model: {os.path.basename(path)}")
    return model

def load_latest_features():
    if not os.path.exists(FEATURES_PATH):
        log_event("❌ No feature file found")
        return None
    df = pd.read_csv(FEATURES_PATH)
    if df.empty:
        log_event("❌ Feature file empty")
        return None
    return df.iloc[-1]

def load_country_features():
    if not os.path.exists(COUNTRY_FEATURES_PATH):
        log_event("⚠️ country_features.csv not found — generating fake data...")
        countries = ["US","UK","DE","IN","JP","CN","BR"]
        fake_data = pd.DataFrame(np.random.rand(len(countries), len(FEATURE_COLUMNS)), columns=FEATURE_COLUMNS)
        fake_data["country"] = countries
        fake_data.to_csv(COUNTRY_FEATURES_PATH, index=False)
        log_event("✅ Fake country_features.csv created")
    return pd.read_csv(COUNTRY_FEATURES_PATH)

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

# -------------------------------
# ML Engine Runs
# -------------------------------
def run_realtime_engine():
    try:
        model = load_model(MODEL_REALTIME)
        latest = load_latest_features()
        if latest is None:
            return
        X = pd.DataFrame([latest[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
        prob = model.predict_proba(X)[0][1]
        level, message = classify_risk(prob)

        forecast_df = compute_forecast(latest, days=7)
        forecast_probs = [model.predict_proba(forecast_df.iloc[[i]][FEATURE_COLUMNS])[0,1] for i in range(len(forecast_df))]

        country_df = load_country_features()
        country_risks = {}
        for _, row in country_df.iterrows():
            x_country = row[FEATURE_COLUMNS].values.reshape(1,-1)
            p = model.predict_proba(x_country)[0,1]
            country_risks[row["country"]] = round(float(p), 3)

        df_history = pd.read_csv(FEATURES_PATH)
        anomalies = detect_anomalies(df_history)

        log_event(f"[REALTIME] Crisis Prob: {prob:.4f} | Risk: {level}")
        log_event(f"[REALTIME] 7-Day Forecast: {[round(p,3) for p in forecast_probs]}")
        log_event(f"[REALTIME] Country Risks: {country_risks}")
        log_event(f"[REALTIME] Anomalies: {anomalies}")
        if level=="🔴 CRITICAL":
            send_email("🚨 REALTIME CRISIS ALERT", f"Crisis probability: {prob:.2f}\n{country_risks}")

    except Exception as e:
        log_event(f"❌ Realtime engine error: {e}")
        traceback.print_exc()

def run_daily_predictor():
    try:
        model = load_model(MODEL_DAILY)
        latest = load_latest_features()
        if latest is None:
            return
        X = pd.DataFrame([latest[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
        prob = model.predict_proba(X)[0][1]
        level, message = classify_risk(prob)
        log_event(f"[DAILY] Crisis Prob: {prob:.4f} | Risk: {level}")
        if level=="🔴 CRITICAL":
            send_email("🚨 DAILY CRISIS ALERT", f"Crisis probability: {prob:.2f}")
    except Exception as e:
        log_event(f"❌ Daily predictor error: {e}")
        traceback.print_exc()

def run_live_predictor():
    try:
        model = load_model(MODEL_LIVE)
        latest = load_latest_features()
        if latest is None:
            return
        X = pd.DataFrame([latest[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
        prob = model.predict_proba(X)[0][1]
        level, message = classify_risk(prob)
        log_event(f"[LIVE] Crisis Prob: {prob:.4f} | Risk: {level}")
        if level=="🔴 CRITICAL":
            send_email("🚨 LIVE CRISIS ALERT", f"Crisis probability: {prob:.2f}")
    except Exception as e:
        log_event(f"❌ Live predictor error: {e}")
        traceback.print_exc()

# -------------------------------
# Orchestrator Pipeline
# -------------------------------
def run_pipeline():
    log_event("Starting World Pulse Pipeline...")

    # --- Preprocessing ---
    try:
        print("\nPreprocessing...", flush=True)
        from processing import preprocess_data
        preprocess_data.main()
    except Exception as e:
        log_event(f"Preprocessing error: {e}")

    # --- NLP ---
    try:
        print("\nRunning NLP...", flush=True)
        from processing import nlp_analysis
        nlp_analysis.main()
    except Exception as e:
        log_event(f"NLP error: {e}")

    # --- Daily Features ---
    try:
        print("\nBuilding daily features...", flush=True)
        from processing.daily_feature_builder import build_hourly_features
        build_hourly_features()
    except Exception as e:
        log_event(f"Daily features error: {e}")

    # --- Topic Modeling ---
    try:
        print("\nTopic modeling...", flush=True)
        from processing import topic_modeling_with_nlp
        topic_modeling_with_nlp.main()
    except Exception as e:
        log_event(f"Topic modeling error: {e}")

    # --- Global Crisis Detector ---
    try:
        print("\nRunning Global Crisis Detector...", flush=True)
        from processing.global_crisis_detector import detect_crisis
        detect_crisis(email_alert_func=send_email)
    except Exception as e:
        log_event(f"Crisis detector error: {e}")

    # --- ML Predictions ---
    run_realtime_engine()
    run_daily_predictor()
    run_live_predictor()

# -------------------------------
# Main Loop
# -------------------------------
if __name__ == "__main__":
    print("Starting hourly World Pulse monitoring...", flush=True)
    while True:
        try:
            run_pipeline()
        except Exception as e:
            log_event(f"Monitoring pipeline error: {e}")
        print(f"Sleeping for {CHECK_INTERVAL/60:.0f} minutes...\n", flush=True)
        time.sleep(CHECK_INTERVAL)
