import requests
from datetime import datetime, timezone
import json
from backend.kafka_client import send_to_kafka  # send each record to Kafka
from database.mongo import insert
from bson import ObjectId

BASE_URL = "https://api.coingecko.com/api/v3"

def fetch_crypto(coin_id="bitcoin", vs_currency="usd", days=5):
    """
    Fetch crypto price history from CoinGecko and return standardized records.
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    url = f"{BASE_URL}/coins/{coin_id}/market_chart"
    params = {"vs_currency": vs_currency, "days": days}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        standardized = []

        for timestamp, price in data.get("prices", []):
            record = {
                "source": "coingecko",
                "category": "crypto",
                "collected_at": collected_at,
                "data": {
                    "coin_id": coin_id,
                    "vs_currency": vs_currency,
                    "timestamp": int(timestamp),
                    "price": price
                }
            }
            standardized.append(record)

            # --- Send to Kafka in real-time ---
            send_to_kafka(record)
            print(f"Sent to Kafka: {record['data']}")  # optional debug/log

        # --- Also insert all records to MongoDB ---
        if standardized:
            insert("crypto", standardized)
            print(f"Inserted {len(standardized)} records into MongoDB")

        return standardized

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

# --- For standalone testing ---
if __name__ == "__main__":
    data = fetch_crypto("bitcoin", "usd", 5)
    if data:
        safe_data = convert_for_json(data)
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))
