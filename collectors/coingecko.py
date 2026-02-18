import requests
from datetime import datetime, timezone
import pandas as pd
import os
from backend.kafka_client import send_to_kafka  # send each record to Kafka
from database.mongo import insert
from bson import ObjectId
import uuid

BASE_URL = "https://api.coingecko.com/api/v3"
PROCESSED_CSV = "processed_crypto.csv"
ROLLING_WINDOW = 5  # hours for rolling return/volatility

def generate_uuid():
    return str(uuid.uuid4())

def normalize(price, max_price=100000):
    """Simple normalization: scale 0-1"""
    return float(price) / max_price

def fetch_crypto(coin_id="bitcoin", vs_currency="usd", days=1):
    """
    Fetch crypto price history from CoinGecko, standardize, save to CSV, send to Kafka and MongoDB.
    Fetches last 24 hours (1 day) for better rolling statistics.
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    url = f"{BASE_URL}/coins/{coin_id}/market_chart"
    params = {"vs_currency": vs_currency, "days": days}


    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "prices" not in data:
            print("CoinGecko error:", data)
            return []

        # Load existing CSV or create empty DataFrame
        df = pd.read_csv(PROCESSED_CSV) if os.path.exists(PROCESSED_CSV) else pd.DataFrame()
        new_records = []

        for ts_ms, price in data.get("prices", []):
            data_timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            record = {
                "_id": generate_uuid(),
                "source": "coingecko",
                "category": "crypto",
                "collected_at": collected_at,
                "data_coin_id": coin_id,
                "data_vs_currency": vs_currency,
                "data_timestamp": data_timestamp.isoformat(),
                "data_price": float(price),
                "data_price_normalized": normalize(price)
            }

            new_records.append(record)

            # --- Send to Kafka ---
            send_to_kafka("crypto_topic", record)
            print(f"Sent to Kafka: {record['data_coin_id']} @ {record['data_price']} USD")

        # --- Append to CSV ---
        if new_records:
            df = pd.concat([df, pd.DataFrame(new_records)], ignore_index=True)
            df.drop_duplicates(subset=["data_coin_id", "data_timestamp"], inplace=True)
            df.to_csv(PROCESSED_CSV, index=False)
            print(f"Saved {len(new_records)} crypto records to {PROCESSED_CSV}")

        # --- Insert into MongoDB ---
        if new_records:
            insert("crypto", new_records)
            print(f"Inserted {len(new_records)} records into MongoDB")

        # --- Compute rolling return & volatility for latest records ---
        if df.empty:
            return new_records

        df["data_timestamp"] = pd.to_datetime(df["data_timestamp"], errors="coerce")
        df = df.sort_values("data_timestamp")
        df["return"] = df["data_price"].pct_change(periods=ROLLING_WINDOW)
        df["volatility"] = df["return"].rolling(window=ROLLING_WINDOW).std()

        latest_stats = df.iloc[-1][["return", "volatility"]].to_dict()
        print(f"[Rolling Stats] Last {ROLLING_WINDOW} hours → Return: {latest_stats.get('return', 0.0):.6f}, Volatility: {latest_stats.get('volatility', 0.0):.6f}")

        return new_records

    except requests.RequestException as e:
        print("Error fetching crypto data:", e)
        return []

def convert_for_json(obj):
    """Recursively convert datetimes and MongoDB ObjectIds to strings"""
    if isinstance(obj, dict):
        return {k: convert_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_for_json(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj

# --- Standalone testing ---
if __name__ == "__main__":
    data = fetch_crypto("bitcoin", "usd", days=1)
    if data:
        safe_data = convert_for_json(data)
        import json
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))
