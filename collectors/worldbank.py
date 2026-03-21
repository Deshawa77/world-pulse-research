import json
from datetime import datetime, timezone

import requests
from bson import ObjectId

from backend.kafka_client import send_to_kafka
from collectors.network_resilience import is_name_resolution_error, summarize_request_exception, warn_once
from database.mongo import insert

BASE_URL = "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD"


def fetch_worldbank_data(date="2020:2025", per_page=5):
    """
    Fetch global GDP data from World Bank API and return standardized records.
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    params = {
        "format": "json",
        "date": date,
        "per_page": per_page,
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        if response.status_code != 200:
            print(f"[worldbank] HTTP Error: {response.status_code}")
            return []

        data = response.json()
        if len(data) <= 1 or not data[1]:
            print(f"[worldbank] Error or empty response: {data}")
            return []

        records = []
        for item in data[1]:
            record = {
                "source": "worldbank",
                "category": "economy",
                "collected_at": collected_at,
                "data": {
                    "country": item["country"]["value"],
                    "country_code": item["country"]["id"],
                    "year": item["date"],
                    "gdp": item["value"],
                },
            }
            records.append(record)
            send_to_kafka("worldbank_data", record)
            print("Sent to Kafka:", record)

        return records

    except requests.RequestException as exc:
        if is_name_resolution_error(exc):
            warn_once("worldbank:dns", summarize_request_exception("worldbank", exc))
        else:
            print(summarize_request_exception("worldbank", exc))
        return []


def convert_for_json(obj):
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
    print("Fetching World Bank data...")
    data = fetch_worldbank_data(date="2020:2025", per_page=5)

    if data:
        insert("worldbank", data)
        safe_data = convert_for_json(data)
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))
    else:
        print("No data fetched.")
