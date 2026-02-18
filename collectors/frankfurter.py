import requests
from datetime import datetime, timezone
import json
from bson import ObjectId
from backend.kafka_client import send_to_kafka
from database.mongo import insert

BASE_URL = "https://api.frankfurter.app/latest"

def fetch_exchange_rates(base_currency="USD"):
    """
    Fetch exchange rates relative to a base currency and return standardized records.
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    url = f"{BASE_URL}?base={base_currency}"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"HTTP Error: {response.status_code}")
            return []

        data = response.json()
        rates = data.get("rates", {})

        standardized = []
        for currency, rate in rates.items():
            record = {
                "source": "frankfurter",
                "category": "finance",
                "collected_at": collected_at,
                "data": {
                    "base_currency": base_currency,
                    "currency": currency,
                    "rate": rate
                }
            }
            standardized.append(record)

            # Send to Kafka immediately
            send_to_kafka("finance", record)
            print(f"Sent to Kafka: {currency} → {rate}")

        # Insert all records into MongoDB (warehouse)
        if standardized:
            insert("economics", standardized)
            print(f"Inserted {len(standardized)} records into MongoDB")

        return standardized

    except Exception as e:
        print("Error fetching exchange rates:", e)
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

# Optional main for standalone testing
if __name__ == "__main__":
    data = fetch_exchange_rates("USD")
    if data:
        safe_data = convert_for_json(data)
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))
