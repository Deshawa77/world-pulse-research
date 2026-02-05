import requests

BASE_URL = "http://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD"

def fetch_worldbank_data(date="2020:2025", per_page=5):
    """
    Fetch global GDP data from World Bank API.
    """
    params = {
        "format": "json",
        "date": date,
        "per_page": per_page
    }
    response = requests.get(BASE_URL, params=params)
    data = response.json()
    
    if len(data) > 1:
        for item in data[1]:
            print(f"Country: {item['country']['value']}, Year: {item['date']}, GDP: {item['value']}")
        return data[1]
    else:
        print("Error or empty response:", data)
        return []

if __name__ == "__main__":
    fetch_worldbank_data()
