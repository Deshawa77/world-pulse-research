import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
import json
from database.mongo import insert
from bson import ObjectId
from backend.kafka_client import send_to_kafka  # send messages to Kafka

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
        response.raise_for_status()
        data = response.json()

        standardized = []
        for obs in data.get("observations", []):
            record = {
                "source": "fred",
                "category": "macro",
                "collected_at": collected_at,
                "data": {
                    "series_id": series_id,
                    "date": obs.get("date"),
                    "value": obs.get("value")
                }
            }
            standardized.append(record)

            # ✅ Send each record to Kafka in real-time
            send_to_kafka("macro", record)
            # Optionally print for debugging
            print(f"Sent to Kafka: {record}")

        return standardized

    except requests.RequestException as e:
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
        # Insert all fetched data into MongoDB (warehouse)
        insert("economics", data)

        # Print safe JSON for verification
        safe_data = convert_for_json(data)
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))
