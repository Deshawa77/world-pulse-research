import requests

BASE_URL = "https://api.coingecko.com/api/v3"

def fetch_crypto(coin_id="bitcoin", vs_currency="usd", days=5):
    """
    Fetch crypto price history from CoinGecko.
    """
    url = f"{BASE_URL}/coins/{coin_id}/market_chart"
    params = {"vs_currency": vs_currency, "days": days}
    response = requests.get(url, params=params)
    data = response.json()
    
    if "prices" in data:
        for timestamp, price in data["prices"]:
            print(f"Time: {timestamp}, Price: {price}")
        return data["prices"]
    else:
        print("Error:", data)
        return []

if __name__ == "__main__":
    fetch_crypto()
