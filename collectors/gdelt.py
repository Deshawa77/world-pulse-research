import requests

BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

def fetch_gdelt_articles(query="earthquake", max_records=10):
    # Wrap OR clauses in parentheses
    if "OR" in query.upper() and not query.startswith("("):
        query = f"({query})"

    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max_records
    }

    response = requests.get(BASE_URL, params=params)

    print("HTTP Status:", response.status_code)
    print("Response snippet:", response.text[:500])  # for debugging

    try:
        data = response.json()
    except ValueError:
        print("Invalid JSON response from GDELT — probably an error message.")
        return []

    articles = []
    for item in data.get("articles", []):
        articles.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "language": item.get("language"),
            "seendate": item.get("seendate")
        })
    return articles

if __name__ == "__main__":
    results = fetch_gdelt_articles("(earthquake OR flood)", max_records=5)
    print(results)
