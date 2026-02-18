# collectors/wiki.py

import requests
import json
from datetime import datetime, timezone, timedelta
from database.mongo import insert
from bson import ObjectId  # handle Mongo ObjectId
from backend.kafka_client import send_to_kafka  # Kafka producer integration

BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"

def fetch_pageviews(article="Earthquake", days=7):
    """
    Fetch Wikipedia pageviews and return standardized records.
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    start = start_date.strftime("%Y%m%d")
    end = end_date.strftime("%Y%m%d")

    url = f"{BASE_URL}/en.wikipedia/all-access/all-agents/{article}/daily/{start}/{end}"

    headers = {
        "User-Agent": "world_pulse_app (research project)"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"Error fetching Wikipedia data for '{article}':", e)
        return []

    collected_at = datetime.now(timezone.utc).isoformat()
    records = []

    for item in data.get("items", []):
        record = {
            "source": "wikipedia",
            "category": "public_attention",
            "collected_at": collected_at,
            "data": {
                "article": article,
                "date": item["timestamp"][:8],
                "views": item["views"]
            }
        }

        # Send to Kafka
        send_to_kafka("wiki_pageviews", record)

        # Insert into MongoDB
        insert("wiki", record)

        # Optionally print for debugging
        print(json.dumps(convert_for_json(record), indent=2, ensure_ascii=False))

        records.append(record)

    return records

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
    print("Running Wikipedia pageviews collector...")
    fetch_pageviews("Earthquake", days=5)
    print("Wikipedia collector finished.")
