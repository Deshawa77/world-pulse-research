import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FRED_API_KEY")
BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

def fetch_indicator(series_id="GDP", start_date="2025-01-01", end_date="2026-01-01"):
    """
    Fetch macroeconomic data from FRED.
    """
    params = {
        "series_id": series_id,
        "api_key": API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date
    }
    response = requests.get(BASE_URL, params=params)
    data = response.json()
    
    if "observations" in data:
        for obs in data["observations"]:
            print(obs)
        return data["observations"]
    else:
        print("Error:", data)
        return []

if __name__ == "__main__":
    fetch_indicator()
