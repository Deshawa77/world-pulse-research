import requests
from datetime import datetime, timezone
import json
from bson import ObjectId
from database.mongo import insert
from backend.kafka_client import send_to_kafka  # make sure this exists

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
    except requests.RequestException as e:
        print("Error fetching USGS data:", e)
        return []
    except ValueError:
        print("Invalid JSON from USGS")
        return []

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
    """Recursively convert datetime and MongoDB ObjectIds to strings"""
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

def collect_earthquakes():
    """
    Fetch USGS data and send to Kafka + MongoDB automatically.
    """
    data = fetch_earthquakes()
    if not data:
        print("No earthquake data fetched.")
        return

    # Insert into MongoDB (warehouse)
    insert("earthquakes", data)

    # Send each record to Kafka (convert datetime/ObjectId first)
    for record in data:
        record_json_safe = convert_for_json(record)
        send_to_kafka("earthquakes", record_json_safe)
        print(f"Sent to Kafka: {record['data']['place']} | M{record['data']['magnitude']}")

    print(f"USGS collector finished. {len(data)} records processed.")


if __name__ == "__main__":
    collect_earthquakes()
