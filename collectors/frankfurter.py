import requests

BASE_URL = "https://api.frankfurter.app/latest"

def fetch_exchange_rates(base_currency="USD"):
    """
    Fetch exchange rates relative to a base currency.
    Returns a dictionary of rates.
    """
    url = f"{BASE_URL}?base={base_currency}"
    try:
        response = requests.get(url)
        if response.status_code != 200:
            print(f"HTTP Error: {response.status_code}")
            return {}

        data = response.json()
        rates = data.get("rates", {})
        print(f"Exchange rates relative to 1 {base_currency}:")
        for currency, rate in rates.items():
            print(f"{currency}: {rate}")
        return rates

    except Exception as e:
        print("Error fetching exchange rates:", e)
        return {}

if __name__ == "__main__":
    # Example: fetch rates relative to USD
    fetch_exchange_rates("USD")
