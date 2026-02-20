# dry_run_orchestrator.py
import os
import pandas as pd
from datetime import datetime, timezone
from orchestrator import (
    load_model, run_ml_engine, update_dashboard, FEATURE_COLUMNS,
    HOURLY_FEATURES_CSV, fs, db, update_global_features
)
import logging

logging.basicConfig(level=logging.INFO)

def dry_run():
    print("🚀 Starting Orchestrator Dry Run...")

    # -------------------------------
    # 1️⃣ Test ML model loading
    # -------------------------------
    try:
        models = load_model()
        print("✅ Models loaded:", list(models.keys()))
    except Exception as e:
        print("❌ Model loading failed:", e)
        return

    # -------------------------------
    # 2️⃣ Test features CSV
    # -------------------------------
    if not os.path.exists(HOURLY_FEATURES_CSV):
        print(f"⚠️ {HOURLY_FEATURES_CSV} not found. Creating mock features...")
        mock_data = {col: [0.0] for col in FEATURE_COLUMNS}
        df_mock = pd.DataFrame(mock_data)
        df_mock.to_csv(HOURLY_FEATURES_CSV, index=False)

    df_features = pd.read_csv(HOURLY_FEATURES_CSV)
    print(f"✅ Loaded features CSV with {len(df_features)} rows")

    # -------------------------------
    # 3️⃣ Run single ML engine cycle
    # -------------------------------
    try:
        print("🔄 Running ML engine (single cycle)...")
        run_ml_engine()
        print("✅ ML engine cycle completed")
    except Exception as e:
        print("❌ ML engine failed:", e)

    # -------------------------------
    # 4️⃣ Update dashboard with latest features
    # -------------------------------
    try:
        latest_doc = db.get_collection("hourly_features").find_one(sort=[("timestamp", -1)])
        if latest_doc:
            update_dashboard(latest_doc)
            print("✅ Dashboard updated with latest hourly features")
        else:
            print("⚠️ No hourly features found to update dashboard")
    except Exception as e:
        print("❌ Dashboard update failed:", e)

    # -------------------------------
    # 5️⃣ Test AI summary update
    # -------------------------------
    try:
        summary_text = update_global_features(db)
        print("✅ AI summary updated:", summary_text)
    except Exception as e:
        print("❌ AI summary update failed:", e)

    print("🎉 Dry run complete! No infinite loops started.")

if __name__ == "__main__":
    dry_run()