import json
import os
from datetime import datetime, timezone

import requests
from bson import ObjectId
from dotenv import load_dotenv

from backend.kafka_client import send_to_kafka
from collectors.network_resilience import is_name_resolution_error, summarize_request_exception, warn_once
from database.mongo import insert

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
        "observation_end": end_date,
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
                    "value": obs.get("value"),
                },
            }
            standardized.append(record)
            send_to_kafka("macro", record)
            print(f"Sent to Kafka: {record}")

        return standardized

    except requests.RequestException as exc:
        if is_name_resolution_error(exc):
            warn_once("fred:dns", summarize_request_exception("fred", exc))
        else:
            print(summarize_request_exception("fred", exc))
        return []


def convert_for_json(obj):
    if isinstance(obj, dict):
        return {k: convert_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_for_json(i) for i in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj


if __name__ == "__main__":
    data = fetch_indicator("GDP", "2020-01-01", "2025-01-01")
    if data:
        insert("economics", data)
        safe_data = convert_for_json(data)
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))
