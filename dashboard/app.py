import streamlit as st
import pandas as pd
import joblib
import os
import numpy as np
from datetime import datetime, timezone

# ============================
# PATHS (FIXED FOR dashboard/)
# ============================

MODEL_PATH = "../models/gb_model.pkl"
FEATURES_PATH = "../data/hourly_features.csv"
COUNTRY_FEATURES_PATH = "../data/country_features.csv"
LOG_PATH = "../logs/crisis_predictions.log"

# ============================
# CONFIG
# ============================

FEATURE_COLUMNS = [
    "news_sentiment",
    "gdelt_sentiment",
    "crypto_return",
    "crypto_volatility",
    "stock_return",
    "stock_volatility",
    "weather_anomaly"
]

ALERT_HIGH = 0.75
ALERT_MED = 0.40

# ============================
# LOAD MODEL
# ============================

@st.cache_resource
def load_model():
    return joblib.load(MODEL_PATH)

model = load_model()

# ============================
# DATA LOADERS
# ============================

def load_features():
    if not os.path.exists(FEATURES_PATH):
        return pd.DataFrame()
    return pd.read_csv(FEATURES_PATH)

def load_country_data():
    if not os.path.exists(COUNTRY_FEATURES_PATH):
        return pd.DataFrame()
    return pd.read_csv(COUNTRY_FEATURES_PATH)

def load_logs():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        return f.readlines()[-200:]

# ============================
# AI LOGIC
# ============================

def classify_risk(prob):
    if prob >= ALERT_HIGH:
        return "🔴 CRITICAL"
    elif prob >= ALERT_MED:
        return "🟠 ELEVATED"
    else:
        return "🟢 LOW"

def compute_forecast(latest_row, days=7):
    forecasts = []
    for _ in range(days):
        row = latest_row.copy()
        for col in FEATURE_COLUMNS:
            row[col] += np.random.normal(0, 0.02)
        forecasts.append(row)
    return pd.DataFrame(forecasts)

def detect_anomalies(df):
    anomalies = {}
    for col in FEATURE_COLUMNS:
        if col in df.columns:
            z = (df[col] - df[col].mean()) / (df[col].std() + 1e-9)
            anomalies[col] = df[col][abs(z) > 2].tolist()
    return anomalies

# ============================
# UI
# ============================

st.set_page_config(page_title="World Pulse AI", layout="wide")
st.title("🌍 World Pulse AI — Global Crisis Intelligence Platform")
st.markdown("**Live AI-driven global risk monitoring system**")

# ============================
# LOAD DATA
# ============================

df = load_features()
country_df = load_country_data()

if df.empty:
    st.error("No hourly_features.csv found. Engine not producing data yet.")
    st.stop()

latest = df.iloc[-1]
X = pd.DataFrame([latest[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
prob = model.predict_proba(X)[0][1]
risk = classify_risk(prob)

# ============================
# TOP METRICS
# ============================

col1, col2, col3, col4 = st.columns(4)

col1.metric("🌍 Global Crisis Probability", f"{prob:.3f}")
col2.metric("🚦 Risk Level", risk)
col3.metric("📅 Timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
col4.metric("🧠 Model", "GradientBoosting AI")

st.divider()

# ============================
# FORECAST
# ============================

st.subheader("📈 7-Day Crisis Forecast")

forecast_df = compute_forecast(latest, days=7)
forecast_probs = [
    model.predict_proba(pd.DataFrame([forecast_df.iloc[i][FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS))[0][1]
    for i in range(len(forecast_df))
]

forecast_chart = pd.DataFrame({
    "Day": [f"Day {i+1}" for i in range(7)],
    "Crisis Probability": forecast_probs
})

st.line_chart(forecast_chart.set_index("Day"))

# ============================
# COUNTRY RISKS
# ============================

st.subheader("🌐 Country-Level Risk")

if not country_df.empty:
    country_results = []
    for _, row in country_df.iterrows():
        Xc = pd.DataFrame([row[FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS)
        p = model.predict_proba(Xc)[0][1]
        country_results.append({
            "Country": row.get("country", "Unknown"),
            "Risk Probability": round(p, 3),
            "Risk Level": classify_risk(p)
        })

    country_table = pd.DataFrame(country_results).sort_values(by="Risk Probability", ascending=False)
    st.dataframe(country_table, use_container_width=True)
else:
    st.info("No country_features.csv found yet.")

# ============================
# ANOMALIES
# ============================

st.subheader("🧬 Signal Anomalies")

anomalies = detect_anomalies(df)

for k, v in anomalies.items():
    if v:
        st.warning(f"{k}: {len(v)} anomalies detected")

if not any(len(v) > 0 for v in anomalies.values()):
    st.success("No anomalies detected")

# ============================
# TIMELINE
# ============================

st.subheader("🕒 Crisis Timeline")

if "global_risk_score" in df.columns:
    timeline = df[["global_risk_score"]].tail(200)
    st.line_chart(timeline)

# ============================
# ALERT PANEL
# ============================

st.subheader("🚨 Alert Panel")

if risk == "🔴 CRITICAL":
    st.error("🚨 GLOBAL CRISIS IMMINENT — Immediate action required")
elif risk == "🟠 ELEVATED":
    st.warning("⚠️ Elevated global instability detected")
else:
    st.success("🟢 System stable — no immediate threats detected")

# ============================
# LOG VIEWER
# ============================

st.subheader("📜 System Logs")

logs = load_logs()
st.text_area("Engine Logs", "".join(logs), height=300)

# ============================
# FOOTER
# ============================

st.markdown("---")
st.markdown("**World Pulse AI Core 🧠🌍** — Global Intelligence Platform")
