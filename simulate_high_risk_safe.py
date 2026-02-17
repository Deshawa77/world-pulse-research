# simulate_critical_alert.py
import pandas as pd
from orchestrator import run_ml_engine, EMAIL_ALERT
from feature_store.feature_store import FeatureStore
import orchestrator

# 1️⃣ Enable email alerts temporarily
orchestrator.EMAIL_ALERT = True

# 2️⃣ Load FeatureStore
fs = FeatureStore()
df_global = fs.read_global()

# 3️⃣ Define all feature columns used by ML engine
FEATURE_COLUMNS = [
    "news_sentiment","gdelt_sentiment","crypto_return","crypto_volatility",
    "stock_return","stock_volatility","weather_anomaly"
]

# 4️⃣ Create a “max risk” record
if df_global.empty:
    latest = pd.Series({col: 100.0 for col in FEATURE_COLUMNS})  # exaggerated values
else:
    latest = df_global.iloc[-1].copy()
    for col in FEATURE_COLUMNS:
        latest[col] = 100.0  # exaggerate all features to force high probability

# 5️⃣ Temporarily override fs.read_global to return only this row
original_read_global = fs.read_global
fs.read_global = lambda: pd.DataFrame([latest])

# 6️⃣ Run ML engine
print("🚨 Running high-risk simulation to trigger CRITICAL alert...")
run_ml_engine()

# 7️⃣ Restore original function
fs.read_global = original_read_global

print("✅ Critical alert simulation complete. Check your email for the alert!")
