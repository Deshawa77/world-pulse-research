import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
import json
from database.mongo import insert
from bson import ObjectId  # <-- handle MongoDB ObjectId

# Load environment variables
load_dotenv()

API_KEY = os.getenv("FRED_API_KEY")
BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

def fetch_indicator(series_id="GDP", start_date="2025-01-01", end_date="2026-01-01"):
    """
    Fetch macroeconomic data from FRED and return standardized records.
    """
    collected_at = datetime.now(timezone.utc).isoformat()

    params = {
        "series_id": series_id,
        "api_key": API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        if response.status_code != 200:
            print("HTTP Error:", response.status_code)
            return []

        data = response.json()

        standardized = []
        for obs in data.get("observations", []):
            standardized.append({
                "source": "fred",
                "category": "macro",
                "collected_at": collected_at,
                "data": {
                    "series_id": series_id,
                    "date": obs.get("date"),
                    "value": obs.get("value")
                }
            })

        return standardized

    except Exception as e:
        print("Error fetching FRED data:", e)
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
    data = fetch_indicator("GDP", "2020-01-01", "2025-01-01")
    if data:
        insert("economics", data)  # Insert raw data into MongoDB

        # Convert any datetime objects and Mongo ObjectIds to strings for safe printing
        safe_data = convert_for_json(data)
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))
