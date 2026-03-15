import requests
from datetime import datetime, timezone
import json
from database.mongo import insert
from backend.kafka_client import send_to_kafka  # Kafka producer
from bson import ObjectId  # Handle MongoDB ObjectId

WHO_BASE_URL = "https://ghoapi.azureedge.net/api"

DEFAULT_WHO_INDICATORS = [
    "WHOSIS_000001",
]

def fetch_who_indicator(indicator_code, max_results=5):
    """
    Fetch WHO indicator data and return standardized records.
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    url = f"{WHO_BASE_URL}/{indicator_code}"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"HTTP Error: {response.status_code}")
            return []

        data = response.json()
        results = []

        for item in data.get("value", [])[:max_results]:
            record = {
                "source": "who",
                "category": "health",
                "collected_at": collected_at,
                "data": {
                    "country": item.get("SpatialDim"),
                    "year": item.get("TimeDim"),
                    "value": item.get("Value"),
                    "indicator": indicator_code
                }
            }
            results.append(record)

            # Send each record to Kafka immediately
            try:
                send_to_kafka("who_indicators", record)
            except Exception as e:
                print(f"Error sending record to Kafka: {e}")

        return results

    except Exception as e:
        print("Error fetching WHO data:", e)
        return []




def fetch_who_indicators(indicator_codes=None, max_results_per_indicator=20):
    """
    Fetch multiple WHO indicators and merge results for better dashboard diversity.
    """
    if indicator_codes is None:
        indicator_codes = DEFAULT_WHO_INDICATORS

    merged = []
    for code in indicator_codes:
        code_str = str(code or "").strip()
        if not code_str:
            continue
        merged.extend(fetch_who_indicator(code_str, max_results=max_results_per_indicator))
    return merged

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
    print("Starting WHO collector...")

    # Fetch and insert raw data into MongoDB
    data = fetch_who_indicators(DEFAULT_WHO_INDICATORS, max_results_per_indicator=5)
    if data:
        insert("health", data)

        # Safe copy for printing JSON
        safe_data = convert_for_json(data)
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))

    print("WHO collection finished.")
