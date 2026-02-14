import sys
import os

# Fix Python path so 'feature_store' sibling folder is importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd
import joblib
import numpy as np
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh
from database.mongo import get_latest_global_features

# Only import model registry if it exists
try:
    from feature_store.model_registry import get_production_model, metadata
    MODEL_REGISTRY_AVAILABLE = True
except ModuleNotFoundError:
    MODEL_REGISTRY_AVAILABLE = False
    st.warning("feature_store module not found. Dashboard will use default model.")

# ============================
# CONFIG
# ============================
DEFAULT_MODEL_PATH = "../models/gb_model.pkl"
COUNTRY_FEATURES_PATH = "../data/country_features.csv"  # fallback
LOG_PATH = "../logs/crisis_predictions.log"

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
    if MODEL_REGISTRY_AVAILABLE:
        prod_model_path = get_production_model()
        if prod_model_path is None or not os.path.exists(prod_model_path):
            st.warning("No production model found. Using default model.")
            prod_model_path = DEFAULT_MODEL_PATH
    else:
        prod_model_path = DEFAULT_MODEL_PATH

    model = joblib.load(prod_model_path)
    return model, prod_model_path

model, model_path = load_model()

# ============================
# MODEL METADATA
# ============================
model_info_str = "Unknown"
if MODEL_REGISTRY_AVAILABLE:
    version_info = next((v for v in metadata.values() if v["file"] == model_path), None)
    if version_info:
        model_info_str = f"Stage: {version_info.get('stage', 'unknown')} | Metrics: {version_info.get('metrics', {})}"

# ============================
# STREAMLIT UI
# ============================
st.set_page_config(page_title="World Pulse AI", layout="wide")
st.title("🌍 World Pulse AI — Global Crisis Intelligence Platform")
st.markdown("**Live AI-driven global risk monitoring system**")

# ============================
# AUTO REFRESH (every 60 seconds)
# ============================
st_autorefresh(interval=60 * 1000, key="refresh")

# ============================
# DATA LOADERS
# ============================
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

def detect_anomalies(df_list):
    df = pd.DataFrame(df_list)
    anomalies = {}
    for col in FEATURE_COLUMNS:
        if col in df.columns:
            z = (df[col] - df[col].mean()) / (df[col].std() + 1e-9)
            anomalies[col] = df[col][abs(z) > 2].tolist()
    return anomalies

# ============================
# LOAD DATA FROM MONGODB
# ============================
doc = get_latest_global_features()
if doc is None:
    st.error("No global features found in MongoDB.")
    st.stop()

latest_features = doc["features"]
X = pd.DataFrame([latest_features])
prob = model.predict_proba(X)[0][1]
risk = classify_risk(prob)

country_df = load_country_data()  # optional fallback for now

# ============================
# TOP METRICS
# ============================
col1, col2, col3, col4 = st.columns(4)
col1.metric("🌍 Global Crisis Probability", f"{prob:.3f}")
col2.metric("🚦 Risk Level", risk)
col3.metric("📅 Timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
col4.metric("🧠 Model Info", model_info_str)

st.divider()

# ============================
# FORECAST
# ============================
st.subheader("📈 7-Day Crisis Forecast")
forecast_df = compute_forecast(latest_features, days=7)
forecast_probs = [
    model.predict_proba(pd.DataFrame([forecast_df.iloc[i][FEATURE_COLUMNS].values], columns=FEATURE_COLUMNS))[0][1]
    for i in range(len(forecast_df))
]
forecast_chart = pd.DataFrame({"Day": [f"Day {i+1}" for i in range(7)], "Crisis Probability": forecast_probs})
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
        country_results.append({"Country": row.get("country", "Unknown"), "Risk Probability": round(p, 3), "Risk Level": classify_risk(p)})
    country_table = pd.DataFrame(country_results).sort_values(by="Risk Probability", ascending=False)
    st.dataframe(country_table, use_container_width=True)
else:
    st.info("No country features found yet.")

# ============================
# ANOMALIES
# ============================
st.subheader("🧬 Signal Anomalies")
anomalies = detect_anomalies([latest_features])
for k, v in anomalies.items():
    if v:
        st.warning(f"{k}: {len(v)} anomalies detected")
if not any(len(v) > 0 for v in anomalies.values()):
    st.success("No anomalies detected")

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
