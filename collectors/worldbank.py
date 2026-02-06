import requests
from datetime import datetime, timezone
import json
from database.mongo import insert
from bson import ObjectId  # <- Add this to handle ObjectId

BASE_URL = "http://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD"

def fetch_worldbank_data(date="2020:2025", per_page=5):
    """
    Fetch global GDP data from World Bank API and return standardized records.
    """
    collected_at = datetime.now(timezone.utc).isoformat()

    params = {
        "format": "json",
        "date": date,
        "per_page": per_page
    }

    try:
        response = requests.get(BASE_URL, params=params)
        if response.status_code != 200:
            print(f"HTTP Error: {response.status_code}")
            return []

        data = response.json()
        if len(data) <= 1 or not data[1]:
            print("Error or empty response:", data)
            return []

        results = []
        for item in data[1]:
            results.append({
                "source": "worldbank",
                "category": "economy",
                "collected_at": collected_at,
                "data": {
                    "country": item['country']['value'],
                    "country_code": item['country']['id'],
                    "year": item['date'],
                    "gdp": item['value']
                }
            })

        return results

    except Exception as e:
        print("Error fetching World Bank data:", e)
        return []

def convert_for_json(obj):
    """
    Recursively convert datetime and ObjectId to strings in dicts/lists.
    """
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
    data = fetch_worldbank_data(date="2020:2025", per_page=5)
    insert("worldbank", data)

    safe_data = convert_for_json(data)
    print(json.dumps(safe_data, indent=2, ensure_ascii=False))
