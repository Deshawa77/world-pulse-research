import requests

BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"

def fetch_pageviews(article, days=7):
    url = f"{BASE_URL}/en.wikipedia/all-access/all-agents/{article}/daily/20260101/20260131"

    headers = {
        "User-Agent": "world_pulse_app"
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print("HTTP Error:", response.status_code)
        return []

    data = response.json()

    results = []
    for item in data.get("items", [])[-days:]:
        results.append({
            "date": item["timestamp"][:8],
            "views": item["views"]
        })

    return results


if __name__ == "__main__":
    views = fetch_pageviews("Earthquake", days=5)
    for v in views:
        print(v)
