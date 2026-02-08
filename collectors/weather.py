# collectors/weather_collector.py

import requests
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
import json
import time
from database.mongo import insert
from bson import ObjectId

# Load API key
load_dotenv()
API_KEY = os.getenv("WEATHER_API_KEY")

# ----------------------------
# Top 100 Global Cities
# Optimized for global coverage
# ----------------------------
TOP_100_CITIES = [
    # North America
    "New York", "Los Angeles", "Chicago", "Houston", "Toronto",
    "Vancouver", "Mexico City", "Montreal", "Miami", "San Francisco",

    # South America
    "São Paulo", "Rio de Janeiro", "Buenos Aires", "Lima", "Bogotá",
    "Santiago", "Caracas", "Quito", "La Paz", "Montevideo",

    # Europe
    "London", "Paris", "Berlin", "Madrid", "Rome",
    "Amsterdam", "Brussels", "Vienna", "Prague", "Warsaw",
    "Budapest", "Stockholm", "Oslo", "Copenhagen", "Helsinki",
    "Athens", "Lisbon", "Dublin", "Zurich", "Moscow",

    # Africa
    "Cairo", "Lagos", "Johannesburg", "Cape Town", "Nairobi",
    "Addis Ababa", "Accra", "Casablanca", "Algiers", "Tunis",

    # Middle East
    "Dubai", "Abu Dhabi", "Doha", "Riyadh", "Jeddah",
    "Kuwait City", "Manama", "Muscat", "Tehran", "Jerusalem",

    # South Asia
    "Delhi", "Mumbai", "Bangalore", "Chennai", "Kolkata",
    "Karachi", "Lahore", "Dhaka", "Colombo", "Kathmandu",

    # East Asia
    "Tokyo", "Osaka", "Seoul", "Beijing", "Shanghai",
    "Hong Kong", "Taipei",

    # Southeast Asia
    "Bangkok", "Singapore", "Kuala Lumpur", "Jakarta", "Manila",
    "Hanoi", "Ho Chi Minh City", "Phnom Penh", "Yangon",

    # Oceania
    "Sydney", "Melbourne", "Brisbane", "Perth", "Auckland",
    "Wellington"
]

# (Total ≈ 100 cities)


# ----------------------------
# Fetch weather for a city
# ----------------------------
def fetch_weather(city):
    collected_at = datetime.now(timezone.utc).isoformat()

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": API_KEY,
        "units": "metric"
    }

    try:
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 429:
            print(f"Rate limit hit while fetching {city}")
            return None

        if response.status_code != 200:
            print(f"Error {response.status_code} for city: {city}")
            return None

        data = response.json()

        standardized = {
            "source": "openweathermap",
            "category": "weather",
            "collected_at": collected_at,
            "data": {
                "city": data.get("name"),
                "country": data.get("sys", {}).get("country"),
                "temperature": data.get("main", {}).get("temp"),
                "feels_like": data.get("main", {}).get("feels_like"),
                "humidity": data.get("main", {}).get("humidity"),
                "pressure": data.get("main", {}).get("pressure"),
                "weather": data.get("weather", [{}])[0].get("description"),
                "wind_speed": data.get("wind", {}).get("speed")
            }
        }

        return standardized

    except Exception as e:
        print(f"Exception for {city}: {e}")
        return None


# ----------------------------
# JSON safe conversion
# ----------------------------
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


# ----------------------------
# Main collector
# ----------------------------
def main():
    print("Starting global weather collection...")

    success = 0

    for city in TOP_100_CITIES:
        data = fetch_weather(city)

        if data:
            insert("weather", data)
            safe_data = convert_for_json(data)
            print(json.dumps(safe_data, indent=2, ensure_ascii=False))
            success += 1

        # Delay to avoid rate limits (Free plan safe)
        time.sleep(1)

    print(f"\nWeather collection complete. {success} cities collected.")


if __name__ == "__main__":
    main()
