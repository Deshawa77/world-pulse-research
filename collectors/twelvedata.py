import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timezone
import json
import pandas as pd
from database.mongo import insert
from bson import ObjectId
from backend.kafka_client import send_to_kafka  # Make sure this exists
import uuid

load_dotenv()

API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BASE_URL = "https://api.twelvedata.com/time_series"

HOURLY_CSV = "processed_stocks.csv"

# -------------------------
# Helpers
# -------------------------
def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def convert_for_json(obj):
    """Recursively convert datetime and MongoDB ObjectIds to strings"""
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

def generate_uuid():
    return str(uuid.uuid4())

def normalize(value, min_val=0, max_val=1000):
    """Simple normalization placeholder"""
    if value is None:
        return 0.0
    return (value - min_val) / (max_val - min_val)

# -------------------------
# Fetch and standardize stock data
# -------------------------
def fetch_stock(symbol="AAPL", interval="1day", outputsize=5):
    collected_at = datetime.now(timezone.utc).isoformat()

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": API_KEY
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Check for API errors
        if "code" in data or "values" not in data:
            print("TwelveData API error or no values returned:", data)
            return []

        results = []
        for item in data["values"]:
            close_price = safe_float(item.get("close"))
            # ✅ Skip records with invalid closing price
            if close_price <= 0:
                continue

            record = {
                "_id": generate_uuid(),
                "source": "twelvedata",
                "category": "finance",
                "collected_at": collected_at,
                "data_symbol": symbol,
                "data_datetime": item.get("datetime")[:10] if item.get("datetime") else collected_at[:10],
                "data_open": safe_float(item.get("open")),
                "data_high": safe_float(item.get("high")),
                "data_low": safe_float(item.get("low")),
                "data_close": close_price,
                "data_volume": safe_float(item.get("volume")),
                "data_close_normalized": normalize(close_price)
            }
            results.append(record)

        return results

    except requests.RequestException as e:
        print("Error fetching stock data:", e)
        return []

# -------------------------
# Collector pipeline
# -------------------------
def collect_stock(symbol="AAPL", interval="1day", outputsize=5):
    data = fetch_stock(symbol, interval, outputsize)
    if not data:
        print("No valid stock data fetched.")
        return

    # Insert into MongoDB
    insert("stocks", data)

    # Append to CSV
    df_existing = pd.read_csv(HOURLY_CSV) if os.path.exists(HOURLY_CSV) else pd.DataFrame()
    df_new = pd.DataFrame(data)
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)
    df_combined.to_csv(HOURLY_CSV, index=False)

    # Send to Kafka
    for record in data:
        record_json_safe = convert_for_json(record)
        send_to_kafka("stocks_topic", record_json_safe)
        print(f"Sent 1 stock record to Kafka: {record['data_symbol']} @ {record['data_datetime']}")

    print(f"Twelve Data collector finished. {len(data)} valid records processed.")

# -------------------------
# Run standalone
# -------------------------
if __name__ == "__main__":
    collect_stock("AAPL", "1day", 5)
