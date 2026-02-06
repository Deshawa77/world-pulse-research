import requests
from datetime import datetime, timezone
import json
from database.mongo import insert
from bson import ObjectId  # <-- handle Mongo ObjectId

BASE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"

def fetch_earthquakes():
    """
    Fetch recent earthquakes from USGS and return standardized records.
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    response = requests.get(BASE_URL)

    if response.status_code != 200:
        print("HTTP Error:", response.status_code)
        return []

    data = response.json()
    earthquakes = []

    for feature in data.get("features", []):
        prop = feature.get("properties", {})
        earthquakes.append({
            "source": "usgs",
            "category": "disaster",
            "collected_at": collected_at,
            "data": {
                "place": prop.get("place"),
                "magnitude": prop.get("mag"),
                "time": datetime.fromtimestamp(prop.get("time") / 1000, tz=timezone.utc).isoformat() if prop.get("time") else None,
                "url": prop.get("url")
            }
        })

    return earthquakes


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
    data = fetch_earthquakes()
    insert("earthquakes", data)

    safe_data = convert_for_json(data)
    print(json.dumps(safe_data, indent=2, ensure_ascii=False))
