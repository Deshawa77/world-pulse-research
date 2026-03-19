import os
import pandas as pd
import numpy as np
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pymongo.errors import DuplicateKeyError
from database.mongo import db
from processing.sentiment_features import extract_sentiment_signal, parse_doc_timestamp

# -------------------------
# Logging setup
# -------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/debug.log",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# -------------------------
# Data paths
# -------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
os.makedirs(DATA_DIR, exist_ok=True)
HOURLY_FEATURES_CSV = os.path.join(DATA_DIR, "hourly_features.csv")

# -------------------------
# CSV Loader
# -------------------------
def load_processed_csv(filename, ts_cols=None):
    path = os.path.join(os.path.dirname(__file__), "../", filename)
    if os.path.exists(path):
        df = pd.read_csv(path)
        ts_cols = ts_cols or []
        for col in df.columns:
            if col in ts_cols or "timestamp" in col or "datetime" in col or "collected_at" in col:
                df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
        df = df.drop_duplicates(subset=ts_cols or df.columns.tolist())
        df = df.sort_values(ts_cols[0] if ts_cols else df.columns[0])
        logging.debug(f"CSV {filename} loaded with {len(df)} rows")
        return df
    return pd.DataFrame()

def load_hourly_features():
    """Fallback CSV loader for precomputed hourly features."""
    if not os.path.exists(HOURLY_FEATURES_CSV):
        return pd.DataFrame()
    try:
        df = pd.read_csv(HOURLY_FEATURES_CSV, on_bad_lines="skip")
        return df
    except Exception as e:
        logging.warning(f"Error loading hourly features CSV: {e}")
        return pd.DataFrame()

# -------------------------
# Numeric feature helpers
# -------------------------
def get_return_volatility(df, value_col, ts_col, window=5):
    if df.empty or value_col not in df.columns or ts_col not in df.columns:
        return 0.0, 0.0

    df = df.dropna(subset=[value_col, ts_col]).copy()
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    df = df.sort_values(ts_col)
    df["hour"] = df[ts_col].dt.floor("h")
    df = df.groupby("hour").agg({value_col: "last"}).sort_index()

    if len(df) < 1:
        return 0.0, 0.0

    returns = df[value_col].pct_change()
    rolling_mean = returns.rolling(window=window, min_periods=1).mean()
    rolling_std = returns.rolling(window=window, min_periods=1).std()
    latest_ret = rolling_mean.iloc[-1] if not rolling_mean.empty and not np.isnan(rolling_mean.iloc[-1]) else 0.0
    latest_vol = rolling_std.iloc[-1] if not rolling_std.empty and not np.isnan(rolling_std.iloc[-1]) else 0.0
    return float(latest_ret), float(latest_vol)

def compute_crypto_features(df):
    return get_return_volatility(df, value_col="data_price", ts_col="data_timestamp", window=5)

def compute_stock_features(df):
    return get_return_volatility(df, value_col="data_close", ts_col="data_datetime", window=5)

def compute_weather_features(df):
    if df.empty or "data_temperature_normalized" not in df.columns or "data_city" not in df.columns:
        return {"weather_anomaly": 0.0}
    df = df.dropna(subset=["data_temperature_normalized", "data_city", "collected_at"]).copy()
    df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce", utc=True)
    df["hour"] = df["collected_at"].dt.floor("h")
    anomalies = []
    for city, group in df.groupby("data_city"):
        if len(group) < 2:
            continue
        group = group.sort_values("hour")
        current = group["data_temperature_normalized"].iloc[-1]
        avg = group["data_temperature_normalized"].mean()
        anomalies.append(current - avg)
    return {"weather_anomaly": float(np.mean(anomalies)) if anomalies else 0.0}

# -------------------------
# Sentiment helpers
# -------------------------
def compute_hourly_sentiment(collection_name, hours=72, doc_limit=6000):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    cursor = db[collection_name].find(
        {},
        {
            "data": 1,
            "text_en": 1,
            "text_original": 1,
            "collected_at": 1,
            "processed_at": 1,
            "timestamp": 1,
        },
    ).sort("_id", -1).limit(doc_limit)

    rows = []
    for doc in cursor:
        sentiment = extract_sentiment_signal(doc)
        if sentiment is None:
            continue

        ts = parse_doc_timestamp(doc)
        if ts is None:
            continue

        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        if ts < cutoff:
            continue

        rows.append({"timestamp": ts, "polarity": float(sentiment)})

    if not rows:
        return 0.0, 0.0

    df = pd.DataFrame(rows).sort_values("timestamp")
    df["hour"] = df["timestamp"].dt.floor("h")
    hourly_avg = df.groupby("hour")["polarity"].mean()
    return float(hourly_avg.mean()), float(df["polarity"].std()) if len(df) > 1 else 0.0

# -------------------------
# Mongo-safe dict
# -------------------------
def safe_mongo_dict(d):
    if isinstance(d, dict):
        return {k.replace(".", "_"): safe_mongo_dict(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [safe_mongo_dict(x) for x in d]
    else:
        return d

def upsert_safe(collection, record, unique_key="_id"):
    if unique_key not in record or not record[unique_key]:
        record[unique_key] = str(uuid.uuid4())
    query = {unique_key: record[unique_key]}
    try:
        collection.update_one(query, {"$set": safe_mongo_dict(record)}, upsert=True)
        logging.info(f"Record {record[unique_key]} upserted successfully.")
        return True
    except DuplicateKeyError as e:
        logging.warning(f"Duplicate key for {record[unique_key]} skipped. Error: {e}")
        return False



def compute_behavior_aggregates(db) -> dict:
    pipeline = [
        {"$sort": {"_id": -1}},
        {"$group": {"_id": "$country", "doc": {"$first": "$$ROOT"}}},
    ]
    docs = list(db.country_features.aggregate(pipeline))
    if not docs:
        return {
            "global_behavior_index": 0.0,
            "global_context_index": 0.0,
            "global_attention_index": 0.0,
            "global_disruption_index": 0.0,
            "global_economic_stress_index": 0.0,
        }
    features = [dict((doc.get("doc") or {}).get("features") or {}) for doc in docs]
    def avg(key: str) -> float:
        vals = [float(item.get(key) or 0.0) for item in features]
        return float(np.mean(vals)) if vals else 0.0
    return {
        "global_behavior_index": round(avg("direct_behavior_score"), 4),
        "global_context_index": round(avg("contextual_pressure_score"), 4),
        "global_attention_index": round(np.mean([avg("public_attention_score") * 100.0, avg("narrative_velocity_score") * 100.0]), 4),
        "global_disruption_index": round(np.mean([avg("mobility_disruption_score") * 100.0, avg("logistics_stress_score") * 100.0]), 4),
        "global_economic_stress_index": round(np.mean([avg("household_stress_score") * 100.0, avg("energy_stress_score") * 100.0, avg("remittance_stress_score") * 100.0]), 4),
    }

# -------------------------
# Build Hourly Features
# -------------------------
def build_hourly_features(db) -> dict:
    """Compute hourly features from Mongo (CSV fallback) and return as dict."""
    hour_str = datetime.now(timezone.utc).isoformat()

    # --- Load data from Mongo first (top-level schema used by collectors) ---
    try:
        crypto_docs = list(db.crypto.find({}, {"_id": 0, "data_price": 1, "data_timestamp": 1}))
        crypto_df = pd.DataFrame(
            [{"data_price": d.get("data_price"), "data_timestamp": d.get("data_timestamp")} for d in crypto_docs]
        )

        stocks_docs = list(db.stocks.find({}, {"_id": 0, "data_close": 1, "data_datetime": 1}))
        stocks_df = pd.DataFrame(
            [{"data_close": d.get("data_close"), "data_datetime": d.get("data_datetime")} for d in stocks_docs]
        )

        weather_docs = list(db.weather.find({}, {"_id": 0, "data_city": 1, "data_temperature_normalized": 1, "collected_at": 1, "data": 1}))
        weather_rows = []
        for d in weather_docs:
            nested = d.get("data", {}) if isinstance(d.get("data"), dict) else {}
            weather_rows.append(
                {
                    "data_temperature_normalized": d.get("data_temperature_normalized", nested.get("temperature_normalized")),
                    "data_city": d.get("data_city", nested.get("city")),
                    "collected_at": d.get("collected_at", nested.get("collected_at")),
                }
            )
        weather_df = pd.DataFrame(weather_rows)

        logging.debug(f"Mongo rows loaded: crypto={len(crypto_df)}, stocks={len(stocks_df)}, weather={len(weather_df)}")
    except Exception as e:
        logging.warning(f"Error loading data from Mongo: {e}")
        crypto_df, stocks_df, weather_df = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # --- Fallback to CSV ---
    if crypto_df.empty:
        crypto_df = load_processed_csv("processed_crypto.csv", ts_cols=["data_timestamp"])
    if stocks_df.empty:
        stocks_df = load_processed_csv("processed_stocks.csv", ts_cols=["data_datetime"])
    if weather_df.empty:
        weather_df = load_processed_csv("processed_weather.csv", ts_cols=["collected_at"])

    # --- Compute features safely ---
    def safe_compute(func, *args, default=None, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.warning(f"Error computing {func.__name__}: {e}")
            return default

    crypto_return, crypto_vol = safe_compute(compute_crypto_features, crypto_df, default=(0.0, 0.0))
    stock_return, stock_vol = safe_compute(compute_stock_features, stocks_df, default=(0.0, 0.0))
    weather_feats = safe_compute(compute_weather_features, weather_df, default={"weather_anomaly": 0.0})
    news_sentiment, news_std = safe_compute(compute_hourly_sentiment, "news", default=(0.0, 0.0))
    gdelt_sentiment, gdelt_std = safe_compute(compute_hourly_sentiment, "gdelt", default=(0.0, 0.0))

    # --- Global risk ---
    from processing.global_risk import compute_global_risk
    global_risk_score, top_topics = safe_compute(compute_global_risk, default=(0.0, []))
    if top_topics is None:
        top_topics = []

    behavior_aggregates = safe_compute(compute_behavior_aggregates, db, default={}) or {}

    # --- Feature row ---
    feature_row = {
        "_id": str(uuid.uuid4()),
        "timestamp": hour_str,
        "news_sentiment": news_sentiment or 0.0,
        "news_sentiment_std": news_std or 0.0,
        "gdelt_sentiment": gdelt_sentiment or 0.0,
        "gdelt_sentiment_std": gdelt_std or 0.0,
        "crypto_return": crypto_return or 0.0,
        "crypto_volatility": crypto_vol or 0.0,
        "stock_return": stock_return or 0.0,
        "stock_volatility": stock_vol or 0.0,
        "weather_anomaly": weather_feats.get("weather_anomaly", 0.0),
        "global_risk_score": global_risk_score or 0.0,
        "top_topics": top_topics,  # keep as list
        **behavior_aggregates,
    }

    logging.debug(f"[SAFE FEATURES] {feature_row}")
    return feature_row

# -------------------------
# Run if main
# -------------------------
if __name__ == "__main__":
    feature_row = build_hourly_features(db)
    print("Hourly features computed:", feature_row)


