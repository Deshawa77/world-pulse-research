import os
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from database.mongo import insert
from bson import ObjectId  # handle MongoDB ObjectId
from backend.kafka_client import send_to_kafka

# Load environment variables
load_dotenv()

API_KEY = os.getenv("NEWS_API_KEY")
BASE_URL = "https://newsapi.org/v2/everything"

def fetch_news(query: str, page_size: int = 10):
    """
    Fetch recent news articles from NewsAPI and return standardized records.
    """
    collected_at = datetime.now(timezone.utc).isoformat()

    params = {
        "q": query,
        "pageSize": page_size,
        "apiKey": API_KEY,
        "sortBy": "publishedAt",
        "language": "en"
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "ok":
            print(f"NewsAPI returned error: {payload}")
            return []

        records = []
        for item in payload.get("articles", []):
            record = {
                "source": "newsapi",
                "category": "media",
                "collected_at": collected_at,
                "data": {
                    "query": query,
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "url": item.get("url"),
                    "published_at": item.get("publishedAt"),
                    "source_name": item.get("source", {}).get("name")
                }
            }
            records.append(record)

            # Send each record to Kafka in real-time
            send_to_kafka("media", record)

        return records

    except requests.RequestException as e:
        print("Error fetching NewsAPI data:", e)
        return []

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

def collect_news(query="earthquake", page_size=10, save_to_mongo=True):
    """
    Fetch news, send to Kafka, and optionally save to MongoDB.
    """
    data = fetch_news(query, page_size=page_size)
    if not data:
        return

    if save_to_mongo:
        insert("news", data)  # Insert raw data into MongoDB

    # Safe JSON conversion for logging/printing
    safe_data = convert_for_json(data)
    print(json.dumps(safe_data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    # Example: fetch 5 news articles about earthquakes
    collect_news(query="earthquake", page_size=5)


#Real-time Kafka streaming: every news item is sent via send_to_kafka(record).
#MongoDB backup: keeps your raw data in your warehouse.
#Safe JSON printing: converts datetimes and ObjectIds to strings.
#Flexible collector function: collect_news() can now be called from your orchestrator for different queries.