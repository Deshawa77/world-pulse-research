import json
from datetime import datetime, timezone

import requests
from bson import ObjectId

from backend.kafka_client import send_to_kafka
from collectors.network_resilience import summarize_request_exception, warn_once, is_name_resolution_error
from database.mongo import insert

BASE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"


def fetch_earthquakes():
    """
    Fetch recent earthquakes from USGS and return standardized records.
    """
    collected_at = datetime.now(timezone.utc).isoformat()

    try:
        response = requests.get(BASE_URL, timeout=(10, 30))
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        if is_name_resolution_error(exc):
            warn_once("usgs:dns", summarize_request_exception("usgs", exc))
        else:
            print(summarize_request_exception("usgs", exc))
        return []
    except ValueError:
        print("[usgs] Invalid JSON from USGS")
        return []

    earthquakes = []

    for feature in data.get("features", []):
        prop = feature.get("properties", {})
        earthquakes.append(
            {
                "source": "usgs",
                "category": "disaster",
                "collected_at": collected_at,
                "data": {
                    "place": prop.get("place"),
                    "magnitude": prop.get("mag"),
                    "time": datetime.fromtimestamp(prop.get("time") / 1000, tz=timezone.utc).isoformat() if prop.get("time") else None,
                    "url": prop.get("url"),
                },
            }
        )

    return earthquakes


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


def collect_earthquakes():
    data = fetch_earthquakes()
    if not data:
        print("No earthquake data fetched.")
        return

    insert("earthquakes", data)

    for record in data:
        record_json_safe = convert_for_json(record)
        send_to_kafka("earthquakes", record_json_safe)
        print(f"Sent to Kafka: {record['data']['place']} | M{record['data']['magnitude']}")

    print(f"USGS collector finished. {len(data)} records processed.")


if __name__ == "__main__":
    collect_earthquakes()
