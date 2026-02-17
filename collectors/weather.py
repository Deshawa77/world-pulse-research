# collectors/weather_collector.py

import requests
import os
import time
import pandas as pd
from datetime import datetime
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
API_KEY = os.getenv("WEATHER_API_KEY")
PROCESSED_CSV = "processed_weather.csv"

TOP_100_CITIES = [
    "New York", "Los Angeles", "Chicago", "Houston", "Toronto",
    "Vancouver", "Mexico City", "Montreal", "Miami", "San Francisco",
    "São Paulo", "Rio de Janeiro", "Buenos Aires", "Lima", "Bogotá",
    "Santiago", "Caracas", "Quito", "La Paz", "Montevideo",
    "London", "Paris", "Berlin", "Madrid", "Rome",
    "Amsterdam", "Brussels", "Vienna", "Prague", "Warsaw",
    "Budapest", "Stockholm", "Oslo", "Copenhagen", "Helsinki",
    "Athens", "Lisbon", "Dublin", "Zurich", "Moscow",
    "Cairo", "Lagos", "Johannesburg", "Cape Town", "Nairobi",
    "Addis Ababa", "Accra", "Casablanca", "Algiers", "Tunis",
    "Dubai", "Abu Dhabi", "Doha", "Riyadh", "Jeddah",
    "Kuwait City", "Manama", "Muscat", "Tehran", "Jerusalem",
    "Delhi", "Mumbai", "Bangalore", "Chennai", "Kolkata",
    "Karachi", "Lahore", "Dhaka", "Colombo", "Kathmandu",
    "Tokyo", "Osaka", "Seoul", "Beijing", "Shanghai",
    "Hong Kong", "Taipei", "Bangkok", "Singapore", "Kuala Lumpur",
    "Jakarta", "Manila", "Hanoi", "Ho Chi Minh City", "Phnom Penh",
    "Yangon", "Sydney", "Melbourne", "Brisbane", "Perth",
    "Auckland", "Wellington"
]

# ----------------------------
# Fetch weather
# ----------------------------
def fetch_weather(city, retries=3, wait_seconds=2):
    collected_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": API_KEY, "units": "metric"}

    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 429:
                print(f"Rate limit hit for {city}. Retrying in {wait_seconds}s...")
                time.sleep(wait_seconds)
                continue

            if response.status_code != 200:
                print(f"Error {response.status_code} for city: {city}")
                return None

            data = response.json()
            temp = data.get("main", {}).get("temp", 0.0)
            humidity = data.get("main", {}).get("humidity", 0.0)
            weather_desc = data.get("weather", [{}])[0].get("description", "unknown")

            return {
                "_id": generate_uuid(),
                "source": "openweathermap",
                "category": "weather",
                "collected_at": collected_at,
                "data_city": data.get("name", city),
                "data_country": data.get("sys", {}).get("country", ""),
                "data_temperature": temp,
                "data_temperature_normalized": normalize(temp),
                "data_humidity": humidity,
                "data_weather": weather_desc
            }

        except Exception as e:
            print(f"Exception fetching {city}: {e}")
            time.sleep(wait_seconds)

    return None

# ----------------------------
# Save to CSV
# ----------------------------
def append_to_csv(row):
    df = pd.read_csv(PROCESSED_CSV) if os.path.exists(PROCESSED_CSV) else pd.DataFrame()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(PROCESSED_CSV, index=False)

# ----------------------------
# Main collector
# ----------------------------
def collect_weather():
    print("Starting global weather collection...")
    success = 0

    for city in TOP_100_CITIES:
        data = fetch_weather(city)
        if data:
            insert("weather", data)
            append_to_csv(data)
            send_to_kafka(data)
            print(f"Processed: {city}")
            success += 1

        time.sleep(1)

    print(f"\nWeather collection complete. {success} cities collected.")

# ----------------------------
# Run if main
# ----------------------------
if __name__ == "__main__":
    collect_weather()
