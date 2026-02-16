import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timezone
import json
from database.mongo import insert
from bson import ObjectId
from backend.kafka_client import send_to_kafka  # Make sure this exists

load_dotenv()

API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BASE_URL = "https://api.twelvedata.com/time_series"

def fetch_stock(symbol="AAPL", interval="1day", outputsize=5):
    """
    Fetch recent stock data from Twelve Data and return standardized records.
    """
    collected_at = datetime.now(timezone.utc).isoformat()

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": API_KEY
    }

    try:
        response = requests.get(BASE_URL, params=params)
        if response.status_code != 200:
            print(f"HTTP Error: {response.status_code}")
            return []

        data = response.json()

        if "values" not in data:
            print("Error:", data)
            return []

        results = []
        for item in data["values"]:
            results.append({
                "source": "twelvedata",
                "category": "finance",
                "collected_at": collected_at,
                "data": {
                    "symbol": symbol,
                    "datetime": item.get("datetime"),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "close": item.get("close"),
                    "volume": item.get("volume")
                }
            })

        return results

    except Exception as e:
        print("Error fetching stock data:", e)
        return []

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

def collect_stock(symbol="AAPL", interval="1day", outputsize=5):
    """
    Fetch stock data, send to Kafka, and insert into MongoDB.
    """
    data = fetch_stock(symbol, interval, outputsize)
    if not data:
        print("No stock data fetched.")
        return

    # Insert into MongoDB (warehouse)
    insert("stocks", data)

    # Send each record to Kafka
    for record in data:
        record_json_safe = convert_for_json(record)
        send_to_kafka(record_json_safe)
        print(f"Sent to Kafka: {record['data']['symbol']} @ {record['data']['datetime']}")

    print(f"Twelve Data collector finished. {len(data)} records processed.")

if __name__ == "__main__":
    collect_stock("AAPL", "1day", 5)
