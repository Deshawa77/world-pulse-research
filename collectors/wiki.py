import requests
import json
from datetime import datetime, timezone, timedelta
from database.mongo import insert
from bson import ObjectId  # handle Mongo ObjectId

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

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("HTTP Error:", response.status_code)
        return []

    data = response.json()
    collected_at = datetime.now(timezone.utc).isoformat()

    records = []
    for item in data.get("items", []):
        records.append({
            "source": "wikipedia",
            "category": "public_attention",
            "collected_at": collected_at,
            "data": {
                "article": article,
                "date": item["timestamp"][:8],
                "views": item["views"]
            }
        })

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
    # Fetch and insert raw data into MongoDB
    data = fetch_pageviews("Earthquake", days=5)
    insert("wiki", data)

    # Safe copy for printing JSON (handles datetime & ObjectId)
    safe_data = convert_for_json(data)
    print(json.dumps(safe_data, indent=2, ensure_ascii=False))
