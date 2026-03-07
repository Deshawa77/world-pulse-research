import requests
from datetime import datetime, timezone
import json
import os
from bson import ObjectId
from database.mongo import insert, db
from backend.kafka_client import send_to_kafka  # Make sure this exists
import time


BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

def fetch_gdelt_articles(
    query="earthquake",
    max_records=10,
    retries=3,
    wait_seconds=5,
    startdatetime=None,
    enddatetime=None,
    sort="datedesc",
):
    """
    Fetch global news articles from GDELT and return standardized records.
    Retries on 429 errors.
    """
    if "OR" in query.upper() and not query.strip().startswith("("):
        query = f"({query})"

    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max_records,
        "sort": sort,
    }
    if startdatetime:
        params["startdatetime"] = startdatetime
    if enddatetime:
        params["enddatetime"] = enddatetime

    for attempt in range(retries):
        try:
            response = requests.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params=params,
                timeout=(10, 30)
            )
            if response.status_code == 429:
                print(f"Rate limit hit, retrying in {wait_seconds}s... (attempt {attempt+1}/{retries})")
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            data = response.json()
            break
        except requests.RequestException as e:
            print("Error fetching GDELT data:", e)
            time.sleep(wait_seconds)
        except ValueError:
            print("Invalid JSON response from GDELT")
            return []
    else:
        # All retries exhausted
        print("Failed to fetch GDELT data after retries.")
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

def collect_gdelt(query="earthquake OR flood", max_records=10):
    """
    Fetch GDELT data and send to Kafka + MongoDB automatically.
    """
    data = fetch_gdelt_articles(query=query, max_records=max_records)
    if not data:
        print("No data fetched from GDELT.")
        return

    # Insert into MongoDB (warehouse)
    insert("gdelt", data)

    # Send each record to Kafka (after converting datetimes to strings)
    for record in data:
        record_json_safe = convert_for_json(record)  # <-- convert datetime/ObjectId
        send_to_kafka("news", record_json_safe)
        print(f"Sent to Kafka: {record['data']['title']}")

    print(f"GDELT collector finished. {len(data)} records processed.")



if __name__ == "__main__":
    collect_gdelt()
