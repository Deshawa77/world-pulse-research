# ===============================
# Live hourly prediction (robust version)
# ===============================
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression, LogisticRegression
from datetime import datetime
import time
import logging
import os

# Path to your CSV
hourly_features_path = "../data/daily_features.csv"

# Features to use for prediction
features = ["news_sentiment", "gdelt_sentiment", "crypto_return", "crypto_volatility",
            "stock_return", "stock_volatility", "weather_anomaly"]

# For testing: short interval and limited iterations
CHECK_INTERVAL = 5  # seconds
RUN_ITERATIONS = 10

def load_features():
    df = pd.read_csv(hourly_features_path)
    
    # Try to auto-detect datetime column
    datetime_cols = [c for c in df.columns if "time" in c.lower() or "date" in c.lower()]
    if not datetime_cols:
        raise ValueError("No datetime-like column found in CSV")
    
    datetime_col = datetime_cols[0]
    df[datetime_col] = pd.to_datetime(df[datetime_col], errors='coerce')
    df = df.dropna(subset=[datetime_col])
    
    df = df.sort_values(datetime_col)
    
    # Rename column to 'timestamp' for consistency
    df.rename(columns={datetime_col: "timestamp"}, inplace=True)
    return df

def prepare_targets(df):
    df["next_hour_risk"] = df["global_risk_score"].shift(-1)
    df["crisis_next_hour"] = (df["next_hour_risk"] > 70).astype(int)
    df = df.dropna(subset=["next_hour_risk"])
    return df

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

print("🚀 Starting robust live hourly retraining and prediction...")

for i in range(RUN_ITERATIONS):
    try:
        df = load_features()
        df = prepare_targets(df)

        logging.basicConfig(filename="../logs/live_prediction.log", level=logging.DEBUG)
        logging.debug(f"Features loaded: {latest.to_dict()}")

        if len(df) < 5 or df["crisis_next_hour"].nunique() < 2:
            clear_screen()
            print(f"[{datetime.utcnow()}] Not enough data or no crisis variation.")
            print(f"Rows: {len(df)}, Crisis classes: {df['crisis_next_hour'].nunique()}")
            time.sleep(CHECK_INTERVAL)
            continue



        # Train/test split (chronological)
        train_size = int(len(df) * 0.8)
        X_train, X_test = df[features].iloc[:train_size], df[features].iloc[train_size:]
        y_reg_train, y_reg_test = df["next_hour_risk"].iloc[:train_size], df["next_hour_risk"].iloc[train_size:]
        y_clf_train, y_clf_test = df["crisis_next_hour"].iloc[:train_size], df["crisis_next_hour"].iloc[train_size:]

        # Train models
        reg_model = LinearRegression()
        reg_model.fit(X_train, y_reg_train)

        clf_model = LogisticRegression(max_iter=1000)
        clf_model.fit(X_train, y_clf_train)

        # Predict next hour
        latest = df.iloc[-1]
        X_latest = latest[features].values.reshape(1, -1)

        risk_pred = reg_model.predict(X_latest)[0]
        crisis_pred = clf_model.predict(X_latest)[0]
        crisis_prob = clf_model.predict_proba(X_latest)[0, 1]

        clear_screen()
        print(f"⏰ {datetime.utcnow()} - Iteration {i+1}/{RUN_ITERATIONS}")
        print(f"Predicted next hour global risk: {risk_pred:.2f}")
        print(f"Predicted crisis: {crisis_pred} (probability={crisis_prob:.2f})\n")

        print("Last data rows:")
        print(df.tail(5)[["timestamp", "global_risk_score"] + features])

        time.sleep(CHECK_INTERVAL)

    except Exception as e:
        clear_screen()
        print(f"Error: {e}. Retrying in {CHECK_INTERVAL} seconds...")
        time.sleep(CHECK_INTERVAL)

print("✅ Live prediction loop finished.")
