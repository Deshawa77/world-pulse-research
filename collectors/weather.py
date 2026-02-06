import requests
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
import json
from database.mongo import insert
from bson import ObjectId  # <-- handle Mongo ObjectId

# Load API key from .env
load_dotenv()
API_KEY = os.getenv("WEATHER_API_KEY")

def fetch_weather(city="Tokyo"):
    """
    Fetch current weather for a city and return standardized record.
    """
    collected_at = datetime.now(timezone.utc).isoformat()

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": API_KEY,
        "units": "metric"
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        print("HTTP Error:", response.status_code)
        return []

    data = response.json()

    standardized = {
        "source": "openweathermap",
        "category": "weather",
        "collected_at": collected_at,
        "data": {
            "city": data.get("name"),
            "temperature": data.get("main", {}).get("temp"),
            "weather": data.get("weather", [{}])[0].get("description"),
            "humidity": data.get("main", {}).get("humidity")
        }
    }

    return standardized


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
    data = fetch_weather("Tokyo")
    insert("weather", data)

    safe_data = convert_for_json(data)
    print(json.dumps(safe_data, indent=2, ensure_ascii=False))
