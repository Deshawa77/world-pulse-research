import os
import pandas as pd
import numpy as np
import logging
import uuid
from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError
from database.mongo import db

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
HOURLY_FEATURES_CSV = os.path.join(DATA_DIR, "hourly_features.csv")
os.makedirs(DATA_DIR, exist_ok=True)

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
        return df
    return pd.DataFrame()


def load_hourly_features():
    """Load hourly features CSV safely, skipping bad lines and logging malformed rows."""
    if not os.path.exists(HOURLY_FEATURES_CSV):
        return pd.DataFrame()

    # Inspect problematic lines (optional debug)
    with open(HOURLY_FEATURES_CSV, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if 15 <= i <= 25:  # check lines around the error (line 21)
                if line.count(",") != 104:  # assuming 104 expected columns
                    logging.warning(f"Malformed line {i}: {line.strip()}")

    # Read CSV safely, skipping bad lines
    try:
        df = pd.read_csv(HOURLY_FEATURES_CSV, on_bad_lines="skip")
    except pd.errors.EmptyDataError:
        logging.warning(f"{HOURLY_FEATURES_CSV} is empty or unreadable.")
        return pd.DataFrame()

    numeric_cols = [
        "news_sentiment", "news_sentiment_std",
        "gdelt_sentiment", "gdelt_sentiment_std",
        "crypto_return", "crypto_volatility",
        "stock_return", "stock_volatility",
        "weather_anomaly", "global_risk_score"
    ]
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df.dropna(subset=numeric_cols, how="all", inplace=True)
    return df

# -------------------------
# Numeric feature helpers
# -------------------------
def get_return_volatility(df, value_col, ts_col, window=5):
    if df.empty or value_col not in df.columns or ts_col not in df.columns:
        return 0.0, 0.0

    df = df.dropna(subset=[value_col, ts_col]).copy()
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    df["hour"] = df[ts_col].dt.floor("h")
    df = df.groupby("hour").agg({value_col: "last"}).sort_index()

    if len(df) < 2:
        return 0.0, 0.0

    returns = df[value_col].pct_change()
    rolling_returns = returns.rolling(window=window, min_periods=2)
    latest_ret = rolling_returns.mean().iloc[-1]
    latest_vol = rolling_returns.std().iloc[-1]
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

# -------------------------
# Build Hourly Features
# -------------------------
def build_hourly_features(db,
                          crypto_df: pd.DataFrame | None = None,
                          stocks_df: pd.DataFrame | None = None,
                          weather_df: pd.DataFrame | None = None) -> dict:
    """
    Compute hourly features and return them as a dict.
    Safe defaults are used to avoid undefined variable issues.
    """

    # --- Ensure DataFrames are not None ---
    crypto_df = crypto_df if crypto_df is not None else pd.DataFrame()
    stocks_df = stocks_df if stocks_df is not None else pd.DataFrame()
    weather_df = weather_df if weather_df is not None else pd.DataFrame()

    # --- UTC-aware timestamp ---
    hour_str = datetime.now(timezone.utc).isoformat()

    # --- Defaults to avoid undefined variable warnings ---
    crypto_return, crypto_vol = 0.0, 0.0
    stock_return, stock_vol = 0.0, 0.0
    weather_feats = {"weather_anomaly": 0.0}
    news_sentiment, news_std = 0.0, 0.0
    gdelt_sentiment, gdelt_std = 0.0, 0.0
    global_risk_score, top_topics = 0.0, []

    # --- Safe computation helper ---
    def safe_compute(func, *args, default=None, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.warning(f"Error computing {func.__name__}: {e}")
            return default


    # --- Load historical CSVs if available ---
    crypto_df = safe_compute(load_processed_csv, "crypto_data.csv", ts_cols=["data_timestamp"], default=pd.DataFrame())
    stocks_df = safe_compute(load_processed_csv, "stocks_data.csv", ts_cols=["data_datetime"], default=pd.DataFrame())
    weather_df = safe_compute(load_processed_csv, "weather_data.csv", ts_cols=["collected_at"], default=pd.DataFrame())

    # --- Compute numeric features safely ---
    crypto_return, crypto_vol = safe_compute(compute_crypto_features, crypto_df, default=(0.0, 0.0))
    stock_return, stock_vol = safe_compute(compute_stock_features, stocks_df, default=(0.0, 0.0))
    weather_feats = safe_compute(compute_weather_features, weather_df, default={"weather_anomaly": 0.0})

    # --- Compute sentiment features safely ---
    news_sentiment, news_std = safe_compute(compute_hourly_sentiment, "news", default=(0.0, 0.0))
    gdelt_sentiment, gdelt_std = safe_compute(compute_hourly_sentiment, "gdelt", default=(0.0, 0.0))

    # --- Compute global risk safely ---
    from processing.global_risk import compute_global_risk
    global_risk_score, top_topics = safe_compute(compute_global_risk, default=(0.0, []))

    # --- Build feature row ---
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
        "top_topics": ", ".join(top_topics) if top_topics else "no data",
    }

    logging.debug(f"[SAFE FEATURES] {feature_row}")

    return feature_row
# -------------------------
# Run if main
# -------------------------
if __name__ == "__main__":
    # Example usage with empty dataframes
    feature_row = build_hourly_features(db)
    print("Hourly features computed:", feature_row)
