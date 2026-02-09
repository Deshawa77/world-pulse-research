from database.mongo import db
from datetime import datetime
import pandas as pd
import os

# Paths for CSV backup 
DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
HOURLY_FEATURES_CSV = os.path.join(DATA_DIR, "hourly_features.csv")

# Ensure data folder exists
os.makedirs(DATA_DIR, exist_ok=True)

# -------------------------
# Helper: Load processed CSVs
# -------------------------
def load_processed_csv(filename):
    path = os.path.join(os.path.dirname(__file__), "../", filename)
    if os.path.exists(path):
        return pd.read_csv(path)
    else:
        return pd.DataFrame()


# -------------------------
# Numeric feature helpers
# -------------------------
def compute_crypto_features(df):
    if df.empty:
        return {"crypto_return": 0.0, "crypto_volatility": 0.0}
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
    if "timestamp" not in df.columns:
        df["timestamp"] = pd.NaT
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return {"weather_anomaly": 0.0}

    df = df.sort_values("timestamp")
    return {
        "weather_anomaly": df["temperature_normalized"].iloc[-1] if "temperature_normalized" in df.columns else 0.0
    }


# -------------------------
# Sentiment helpers (hourly)
# -------------------------
def compute_hourly_sentiment(collection_name):
    cursor = db[collection_name].find({}, {"data.sentiment.vader.compound": 1, "data.processed_at": 1})
    rows = []
    for doc in cursor:
        sentiment = doc.get("data", {}).get("sentiment", {}).get("vader", {}).get("compound")
        ts = doc.get("data", {}).get("processed_at")
        if sentiment is None or not ts:
            continue
        try:
            ts = datetime.fromisoformat(ts)
        except:
            continue
        rows.append({"timestamp": ts, "polarity": sentiment})

    if not rows:
        return 0.0, 0.0

    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp")
    hourly_avg = df.groupby(df['timestamp'].dt.hour)['polarity'].mean()
    avg_sentiment = hourly_avg.mean()
    sentiment_std = df['polarity'].std() if len(df) > 1 else 0.0
    return avg_sentiment, sentiment_std


# -------------------------
# Global risk helper
# -------------------------
from processing.global_risk import compute_global_risk


# -------------------------
# Main: Build Hourly Feature Row
# -------------------------
def build_hourly_features():
    now = datetime.utcnow()
    hour_str = now.strftime("%Y-%m-%d %H:00")

    # Load processed CSVs
    crypto_df = load_processed_csv("processed_crypto.csv")
    stocks_df = load_processed_csv("processed_stocks.csv")
    weather_df = load_processed_csv("processed_weather.csv")

    # Compute numeric features
    crypto_feats = compute_crypto_features(crypto_df)
    stock_feats = compute_stock_features(stocks_df)
    weather_feats = compute_weather_features(weather_df)

    # Compute hourly sentiment
    news_sentiment, news_std = compute_hourly_sentiment("news")
    gdelt_sentiment, gdelt_std = compute_hourly_sentiment("gdelt")

    # Compute dynamic global risk
    global_risk_score, top_topics = compute_global_risk()

    # Compose feature row
    feature_row = {
        "timestamp": hour_str,
        "news_sentiment": news_sentiment,
        "news_sentiment_std": news_std,
        "gdelt_sentiment": gdelt_sentiment,
        "gdelt_sentiment_std": gdelt_std,
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
        {"timestamp": hour_str},
        {"$set": feature_row},
        upsert=True
    )

    # Append to CSV (hourly)
    if os.path.exists(HOURLY_FEATURES_CSV):
        df = pd.read_csv(HOURLY_FEATURES_CSV)
        if hour_str not in df["timestamp"].values:
            df = pd.concat([df, pd.DataFrame([feature_row])], ignore_index=True)
            df.to_csv(HOURLY_FEATURES_CSV, index=False)
    else:
        pd.DataFrame([feature_row]).to_csv(HOURLY_FEATURES_CSV, index=False)

    print(f"[HOURLY FEATURE] {hour_str} saved → Global Risk: {global_risk_score}")
    return feature_row


if __name__ == "__main__":
    build_hourly_features()

    # Also print current risk immediately
    try:
        risk, topics = compute_global_risk()
        print(f"[GLOBAL RISK] {datetime.utcnow()}: {risk} → Top Topics: {topics}")
    except Exception as e:
        print(f"Could not compute global risk: {e}")
