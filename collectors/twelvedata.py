import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timezone
import json
from database.mongo import insert
from bson import ObjectId  # <-- handle Mongo ObjectId

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
    """Recursively convert datetime and ObjectId for JSON serialization"""
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
    data = fetch_stock("AAPL", "1day", 5)
    insert("stocks", data)

    safe_data = convert_for_json(data)
    print(json.dumps(safe_data, indent=2, ensure_ascii=False))
