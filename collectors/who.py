import requests

WHO_BASE_URL = "https://ghoapi.azureedge.net/api"


def fetch_who_indicator(indicator_code, max_results=5):
    url = f"{WHO_BASE_URL}/{indicator_code}"

    response = requests.get(url, timeout=10)

    if response.status_code != 200:
        print(f"HTTP Error: {response.status_code}")
        return []

    try:
        data = response.json()
    except ValueError:
        print("Invalid JSON response")
        return []

    results = []

    for item in data.get("value", [])[:max_results]:
        results.append({
            "country": item.get("SpatialDim"),
            "year": item.get("TimeDim"),
            "value": item.get("Value"),
            "indicator": indicator_code
        })

    return results


if __name__ == "__main__":
    indicator = "WHOSIS_000001"  # Life expectancy
    records = fetch_who_indicator(indicator, max_results=5)

    for r in records:
        print(r)
