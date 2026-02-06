import requests
from datetime import datetime, timezone
import json
from database.mongo import insert
from bson import ObjectId  # <-- handle MongoDB ObjectId

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
            standardized.append({
                "source": "frankfurter",
                "category": "finance",
                "collected_at": collected_at,
                "data": {
                    "base_currency": base_currency,
                    "currency": currency,
                    "rate": rate
                }
            })

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

if __name__ == "__main__":
    data = fetch_exchange_rates("USD")
    if data:
        insert("economics", data)  # Insert raw data into MongoDB

        # Convert any datetime objects and Mongo ObjectIds to strings for safe printing
        safe_data = convert_for_json(data)
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))
