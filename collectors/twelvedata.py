import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BASE_URL = "https://api.twelvedata.com/time_series"

def fetch_stock(symbol="AAPL", interval="1day", outputsize=5):
    """
    Fetch recent stock data from Twelve Data.
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": API_KEY
    }
    response = requests.get(BASE_URL, params=params)
    data = response.json()
    
    if "values" in data:
        for item in data["values"]:
            print(item)
        return data["values"]
    else:
        print("Error:", data)
        return []

if __name__ == "__main__":
    fetch_stock()
