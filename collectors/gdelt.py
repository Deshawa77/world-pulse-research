import requests
from datetime import datetime, timezone
import json
from database.mongo import insert
from bson import ObjectId  # Handle MongoDB ObjectId

BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

def fetch_gdelt_articles(query="earthquake", max_records=10):
    """
    Fetch global news articles from GDELT and return standardized records.
    """
    if "OR" in query.upper() and not query.strip().startswith("("):
        query = f"({query})"

    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max_records
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=(10, 30))  # connect + read timeout
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print("Error fetching GDELT data:", e)
        return []
    except ValueError:
        print("Invalid JSON response from GDELT")
        return []

    collected_at = datetime.now(timezone.utc).isoformat()
    records = []

    for item in data.get("articles", []):
        records.append({
            "source": "gdelt",
            "category": "global_news",
            "collected_at": collected_at,
            "data": {
                "query": query,
                "title": item.get("title"),
                "url": item.get("url"),
                "language": item.get("language"),
                "published_at": item.get("seendate")
            }
        })

    return records

def convert_for_json(obj):
    """Recursively convert datetimes and MongoDB ObjectIds to strings"""
    if isinstance(obj, dict):
        return {k: convert_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_for_json(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj

if __name__ == "__main__":
    data = fetch_gdelt_articles("(earthquake OR flood)", max_records=5)
    if data:
        insert("gdelt", data)

        safe_data = convert_for_json(data)
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))
