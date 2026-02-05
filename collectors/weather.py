import requests
import os
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv()

API_KEY = os.getenv("WEATHER_API_KEY")

def get_weather(city="Tokyo"):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": API_KEY,
        "units": "metric"
    }

    response = requests.get(url, params=params)
    return response.json()

if __name__ == "__main__":
    data = get_weather("Tokyo")

    print("\n--- Weather Data ---")
    print("City:", data["name"])
    print("Temperature:", data["main"]["temp"], "°C")
    print("Weather:", data["weather"][0]["description"])
    print("Humidity:", data["main"]["humidity"], "%")
