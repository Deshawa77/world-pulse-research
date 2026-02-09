from database.mongo import db
from datetime import datetime
import pandas as pd
import os

# Paths for CSV backup 
DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
DAILY_FEATURES_CSV = os.path.join(DATA_DIR, "daily_features.csv")

# Ensure data folder exists
os.makedirs(DATA_DIR, exist_ok=True)

# Helper: Load processed CSVs
def load_processed_csv(filename):
    path = os.path.join(os.path.dirname(__file__), "../", filename)
    if os.path.exists(path):
        return pd.read_csv(path)
    else:
        return pd.DataFrame()


# Helper: Compute numeric features
def compute_crypto_features(df):
    if df.empty:
        return {"crypto_return": 0.0, "crypto_volatility": 0.0}

    # --- SAFE TIMESTAMP HANDLING ---
    if "timestamp" not in df.columns:
        df["timestamp"] = pd.NaT
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return {"crypto_return": 0.0, "crypto_volatility": 0.0}

    df = df.sort_values("timestamp")
    df["price_change"] = df["price"].pct_change()
    return {
        "crypto_return": df["price_change"].iloc[-1] if len(df) > 1 else 0.0,
        "crypto_volatility": df["price_change"].std() if len(df) > 1 else 0.0
    }

def compute_stock_features(df):
    if df.empty:
        return {"stock_return": 0.0, "stock_volatility": 0.0}

    # --- SAFE TIMESTAMP HANDLING ---
    if "timestamp" not in df.columns:
        df["timestamp"] = pd.NaT
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return {"stock_return": 0.0, "stock_volatility": 0.0}

    df = df.sort_values("timestamp")
    df["close_change"] = df["close"].pct_change()
    return {
        "stock_return": df["close_change"].iloc[-1] if len(df) > 1 else 0.0,
        "stock_volatility": df["close_change"].std() if len(df) > 1 else 0.0
    }

def compute_weather_features(df):
    if df.empty:
        return {"weather_anomaly": 0.0}

    # --- SAFE TIMESTAMP HANDLING ---
    if "timestamp" not in df.columns:
        df["timestamp"] = pd.NaT
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return {"weather_anomaly": 0.0}

    df = df.sort_values("timestamp")
    return {
        "weather_anomaly": df["temperature_normalized"].iloc[-1] if "temperature_normalized" in df.columns else 0.0
    }

# Helper: Compute sentiment averages
def compute_sentiment_average(collection_name):
    today = datetime.utcnow().date()
    weighted_sentiments = []

    cursor = db[collection_name].find(
        {}, {"data.sentiment.vader.compound": 1, "data.processed_at": 1}
    )

    for doc in cursor:
        sentiment = doc.get("data", {}).get("sentiment", {}).get("vader", {}).get("compound")
        processed_time = doc.get("data", {}).get("processed_at")
        if sentiment is None or not processed_time:
            continue
        try:
            doc_date = datetime.fromisoformat(processed_time).date()
        except:
            continue
        if doc_date == today:
            weighted_sentiments.append(sentiment)

    if weighted_sentiments:
        return sum(weighted_sentiments) / len(weighted_sentiments)
    return 0.0


# Helper: Get Global Risk from global_risk.py
from processing.global_risk import compute_global_risk

# Main: Build Daily Feature Row
def build_daily_features():
    today = datetime.utcnow().date().isoformat()

    # Load processed CSVs
    crypto_df = load_processed_csv("processed_crypto.csv")
    stocks_df = load_processed_csv("processed_stocks.csv")
    weather_df = load_processed_csv("processed_weather.csv")

    # Numeric features
    crypto_feats = compute_crypto_features(crypto_df)
    stock_feats = compute_stock_features(stocks_df)
    weather_feats = compute_weather_features(weather_df)

    # Sentiment features
    news_sentiment = compute_sentiment_average("news")
    gdelt_sentiment = compute_sentiment_average("gdelt")

    # Global risk
    global_risk_score, top_topics = compute_global_risk()

    # Compose daily feature row
    feature_row = {
        "date": today,
        "news_sentiment": news_sentiment,
        "gdelt_sentiment": gdelt_sentiment,
        "crypto_return": crypto_feats["crypto_return"],
        "crypto_volatility": crypto_feats["crypto_volatility"],
        "stock_return": stock_feats["stock_return"],
        "stock_volatility": stock_feats["stock_volatility"],
        "weather_anomaly": weather_feats["weather_anomaly"],
        "global_risk_score": global_risk_score,
        "top_topics": ", ".join(top_topics)
    }

    # Save to Mongo
    db.features_history.update_one(
        {"date": today},
        {"$set": feature_row},
        upsert=True
    )

    # Append to CSV (for backup / ML)
    if os.path.exists(DAILY_FEATURES_CSV):
        df = pd.read_csv(DAILY_FEATURES_CSV)
        if today not in df["date"].values:
            df = pd.concat([df, pd.DataFrame([feature_row])], ignore_index=True)
            df.to_csv(DAILY_FEATURES_CSV, index=False)
    else:
        pd.DataFrame([feature_row]).to_csv(DAILY_FEATURES_CSV, index=False)

    print(f"[DAILY FEATURE] {today} saved → Global Risk: {global_risk_score}")
    return feature_row


if __name__ == "__main__":
    # Build daily features safely
    build_daily_features()

    # Also print today's global risk immediately
    try:
        risk, topics = compute_global_risk()
        print(f"[GLOBAL RISK] {datetime.utcnow().date()}: {risk} → Top Topics: {topics}")
    except Exception as e:
        print(f"Could not compute global risk: {e}")
