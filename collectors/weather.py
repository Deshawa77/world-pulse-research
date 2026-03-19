# collectors/weather_collector.py

import requests
import os
import time
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from bson import ObjectId
from database.mongo import insert
from backend.kafka_client import send_to_kafka
import uuid

# ----------------------------
# Utility functions
# ----------------------------
def generate_uuid():
    return str(uuid.uuid4())

def normalize(value, min_val=-50, max_val=50):
    return (value - min_val) / (max_val - min_val)

# ----------------------------
# Config
# ----------------------------
load_dotenv()
def _resolve_weather_api_key():
    return (
        os.getenv("WEATHER_API_KEY")
        or os.getenv("OPENWEATHER_KEY")
        or os.getenv("OPENWEATHER_API_KEY")
    )


API_KEY = _resolve_weather_api_key()
PROCESSED_CSV = "processed_weather.csv"
_MISSING_KEY_WARNED = False
_AUTH_FAIL_WARNED = False

TOP_100_CITIES = [
    {"name": "New York", "lat": 40.7128, "lon": -74.0060},
    {"name": "Los Angeles", "lat": 34.0522, "lon": -118.2437},
    {"name": "Chicago", "lat": 41.8781, "lon": -87.6298},
    {"name": "Houston", "lat": 29.7604, "lon": -95.3698},
    {"name": "Toronto", "lat": 43.6532, "lon": -79.3832},
    {"name": "Vancouver", "lat": 49.2827, "lon": -123.1207},
    {"name": "Mexico City", "lat": 19.4326, "lon": -99.1332},
    {"name": "Montreal", "lat": 45.5017, "lon": -73.5673},
    {"name": "Miami", "lat": 25.7617, "lon": -80.1918},
    {"name": "San Francisco", "lat": 37.7749, "lon": -122.4194},

    {"name": "São Paulo", "lat": -23.5505, "lon": -46.6333},
    {"name": "Rio de Janeiro", "lat": -22.9068, "lon": -43.1729},
    {"name": "Buenos Aires", "lat": -34.6037, "lon": -58.3816},
    {"name": "Lima", "lat": -12.0464, "lon": -77.0428},
    {"name": "Bogotá", "lat": 4.7110, "lon": -74.0721},
    {"name": "Santiago", "lat": -33.4489, "lon": -70.6693},
    {"name": "Caracas", "lat": 10.4806, "lon": -66.9036},
    {"name": "Quito", "lat": -0.1807, "lon": -78.4678},
    {"name": "La Paz", "lat": -16.4897, "lon": -68.1193},
    {"name": "Montevideo", "lat": -34.9011, "lon": -56.1645},

    {"name": "London", "lat": 51.5074, "lon": -0.1278},
    {"name": "Paris", "lat": 48.8566, "lon": 2.3522},
    {"name": "Berlin", "lat": 52.5200, "lon": 13.4050},
    {"name": "Madrid", "lat": 40.4168, "lon": -3.7038},
    {"name": "Rome", "lat": 41.9028, "lon": 12.4964},
    {"name": "Amsterdam", "lat": 52.3676, "lon": 4.9041},
    {"name": "Brussels", "lat": 50.8503, "lon": 4.3517},
    {"name": "Vienna", "lat": 48.2082, "lon": 16.3738},
    {"name": "Prague", "lat": 50.0755, "lon": 14.4378},
    {"name": "Warsaw", "lat": 52.2297, "lon": 21.0122},

    {"name": "Budapest", "lat": 47.4979, "lon": 19.0402},
    {"name": "Stockholm", "lat": 59.3293, "lon": 18.0686},
    {"name": "Oslo", "lat": 59.9139, "lon": 10.7522},
    {"name": "Copenhagen", "lat": 55.6761, "lon": 12.5683},
    {"name": "Helsinki", "lat": 60.1699, "lon": 24.9384},
    {"name": "Athens", "lat": 37.9838, "lon": 23.7275},
    {"name": "Lisbon", "lat": 38.7223, "lon": -9.1393},
    {"name": "Dublin", "lat": 53.3498, "lon": -6.2603},
    {"name": "Zurich", "lat": 47.3769, "lon": 8.5417},
    {"name": "Moscow", "lat": 55.7558, "lon": 37.6173},

    {"name": "Cairo", "lat": 30.0444, "lon": 31.2357},
    {"name": "Lagos", "lat": 6.5244, "lon": 3.3792},
    {"name": "Johannesburg", "lat": -26.2041, "lon": 28.0473},
    {"name": "Cape Town", "lat": -33.9249, "lon": 18.4241},
    {"name": "Nairobi", "lat": -1.2921, "lon": 36.8219},
    {"name": "Addis Ababa", "lat": 8.9806, "lon": 38.7578},
    {"name": "Accra", "lat": 5.6037, "lon": -0.1870},
    {"name": "Casablanca", "lat": 33.5731, "lon": -7.5898},
    {"name": "Algiers", "lat": 36.7538, "lon": 3.0588},
    {"name": "Tunis", "lat": 36.8065, "lon": 10.1815},

    {"name": "Dubai", "lat": 25.2048, "lon": 55.2708},
    {"name": "Abu Dhabi", "lat": 24.4539, "lon": 54.3773},
    {"name": "Doha", "lat": 25.2854, "lon": 51.5310},
    {"name": "Riyadh", "lat": 24.7136, "lon": 46.6753},
    {"name": "Jeddah", "lat": 21.4858, "lon": 39.1925},
    {"name": "Kuwait City", "lat": 29.3759, "lon": 47.9774},
    {"name": "Manama", "lat": 26.2235, "lon": 50.5876},
    {"name": "Muscat", "lat": 23.5880, "lon": 58.3829},
    {"name": "Tehran", "lat": 35.6892, "lon": 51.3890},
    {"name": "Jerusalem", "lat": 31.7683, "lon": 35.2137},

    {"name": "Delhi", "lat": 28.7041, "lon": 77.1025},
    {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777},
    {"name": "Bangalore", "lat": 12.9716, "lon": 77.5946},
    {"name": "Chennai", "lat": 13.0827, "lon": 80.2707},
    {"name": "Kolkata", "lat": 22.5726, "lon": 88.3639},
    {"name": "Karachi", "lat": 24.8607, "lon": 67.0011},
    {"name": "Lahore", "lat": 31.5204, "lon": 74.3587},
    {"name": "Dhaka", "lat": 23.8103, "lon": 90.4125},
    {"name": "Colombo", "lat": 6.9271, "lon": 79.8612},
    {"name": "Kathmandu", "lat": 27.7172, "lon": 85.3240},

    {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503},
    {"name": "Osaka", "lat": 34.6937, "lon": 135.5023},
    {"name": "Seoul", "lat": 37.5665, "lon": 126.9780},
    {"name": "Beijing", "lat": 39.9042, "lon": 116.4074},
    {"name": "Shanghai", "lat": 31.2304, "lon": 121.4737},
    {"name": "Hong Kong", "lat": 22.3193, "lon": 114.1694},
    {"name": "Taipei", "lat": 25.0330, "lon": 121.5654},
    {"name": "Bangkok", "lat": 13.7563, "lon": 100.5018},
    {"name": "Singapore", "lat": 1.3521, "lon": 103.8198},
    {"name": "Kuala Lumpur", "lat": 3.1390, "lon": 101.6869},

    {"name": "Jakarta", "lat": -6.2088, "lon": 106.8456},
    {"name": "Manila", "lat": 14.5995, "lon": 120.9842},
    {"name": "Hanoi", "lat": 21.0278, "lon": 105.8342},
    {"name": "Ho Chi Minh City", "lat": 10.8231, "lon": 106.6297},
    {"name": "Phnom Penh", "lat": 11.5564, "lon": 104.9282},
    {"name": "Yangon", "lat": 16.8409, "lon": 96.1735},

    {"name": "Sydney", "lat": -33.8688, "lon": 151.2093},
    {"name": "Melbourne", "lat": -37.8136, "lon": 144.9631},
    {"name": "Brisbane", "lat": -27.4698, "lon": 153.0251},
    {"name": "Perth", "lat": -31.9505, "lon": 115.8605},
    {"name": "Auckland", "lat": -36.8485, "lon": 174.7633},
    {"name": "Wellington", "lat": -41.2866, "lon": 174.7756}
]


# ----------------------------
# Fetch historical weather
# ----------------------------
def fetch_weather(city_name, lat, lon):
    global _MISSING_KEY_WARNED, _AUTH_FAIL_WARNED
    if not API_KEY:
        if not _MISSING_KEY_WARNED:
            print("Weather collector skipped: set WEATHER_API_KEY or OPENWEATHER_KEY in environment.")
            _MISSING_KEY_WARNED = True
        return []

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": API_KEY,
        "units": "metric"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            detail = ""
            try:
                payload = response.json()
                detail = str(payload.get("message") or "").strip()
            except Exception:
                detail = ""
            if response.status_code == 401 and not _AUTH_FAIL_WARNED:
                print("Weather collector unauthorized (401): verify your OpenWeather API key.")
                _AUTH_FAIL_WARNED = True
                # Stop repeated unauthorized calls for remaining cities in this run.
                globals()["API_KEY"] = None
            elif response.status_code != 401:
                suffix = f" - {detail}" if detail else ""
                print(f"Error {response.status_code} for city {city_name}{suffix}")
            return []

        data = response.json()

        temp = data.get("main", {}).get("temp", 0.0)
        humidity = data.get("main", {}).get("humidity", 0.0)
        weather_desc = data.get("weather", [{}])[0].get("description", "unknown")
        timestamp = datetime.now(timezone.utc).isoformat()

        record = {
            "_id": generate_uuid(),
            "source": "openweathermap",
            "category": "weather",
            "collected_at": timestamp,
            "data_city": city_name,
            "data_temperature": temp,
            "data_temperature_normalized": normalize(temp),
            "data_humidity": humidity,
            "data_weather": weather_desc,
            "data_timestamp": timestamp
        }

        return [record]

    except Exception as e:
        print(f"Exception fetching {city_name}: {e}")
        return []


# ----------------------------
# Save to CSV
# ----------------------------
def append_to_csv(rows):
    df = pd.read_csv(PROCESSED_CSV) if os.path.exists(PROCESSED_CSV) else pd.DataFrame()
    df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    df.to_csv(PROCESSED_CSV, index=False)

# ----------------------------
# Main collector
# ----------------------------
def collect_weather():
    print("Starting global weather collection...")
    success = 0

    for city in TOP_100_CITIES:
        city_name = city["name"]
        lat = city["lat"]
        lon = city["lon"]

        data_rows = fetch_weather(city_name, lat, lon)
        if data_rows:
            insert("weather", data_rows)
            append_to_csv(data_rows)
            for row in data_rows:
                send_to_kafka("weather_topic", row)
            print(f"Processed {len(data_rows)} rows for: {city_name}")
            success += 1

        time.sleep(1)  # avoid API rate limits

    print(f"\nWeather collection complete. {success} cities collected.")

def collect_weather_for_orchestrator():
    """
    Collect weather for all 100 cities, return a flat list of records
    for orchestrator. No Mongo/CVS/Kafka side-effects.
    """
    all_records = []
    for city in TOP_100_CITIES:
        city_name = city["name"]
        lat = city["lat"]
        lon = city["lon"]

        try:
            records = fetch_weather(city_name, lat, lon)
            if records:
                # Remove Mongo _id to avoid conflicts
                for rec in records:
                    rec.pop("_id", None)
                all_records.extend(records)
        except Exception as e:
            print(f"Error fetching weather for {city_name}: {e}")

    return all_records


# ----------------------------
# Run if main
# ----------------------------
if __name__ == "__main__":
    collect_weather()
