import time
from datetime import datetime, timezone

import requests
from bson import ObjectId

from collectors.network_resilience import is_name_resolution_error, summarize_request_exception, warn_once
from database.mongo import db, insert
from backend.kafka_client import send_to_kafka

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
    Retries on 429 errors, but aborts early on DNS resolution failures.
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

    data = None
    for attempt in range(retries):
        try:
            response = requests.get(BASE_URL, params=params, timeout=(10, 30))
            if response.status_code == 429:
                print(f"[gdelt] Rate limit hit, retrying in {wait_seconds}s... (attempt {attempt + 1}/{retries})")
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            data = response.json()
            break
        except requests.RequestException as exc:
            if is_name_resolution_error(exc):
                warn_once("gdelt:dns", summarize_request_exception("gdelt", exc))
                return []
            print(f"[gdelt] {summarize_request_exception('gdelt', exc)}")
            time.sleep(wait_seconds)
        except ValueError:
            print("[gdelt] Invalid JSON response from GDELT")
            return []
    else:
        print("[gdelt] Failed to fetch GDELT data after retries.")
        return []

    collected_at = datetime.now(timezone.utc).isoformat()
    records = []

    for item in (data or {}).get("articles", []):
        records.append(
            {
                "source": "gdelt",
                "category": "global_news",
                "collected_at": collected_at,
                "data": {
                    "query": query,
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "language": item.get("language"),
                    "published_at": item.get("seendate"),
                },
            }
        )

    return records


def convert_for_json(obj):
    if isinstance(obj, dict):
        return {k: convert_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_for_json(i) for i in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj


def collect_gdelt(query="earthquake OR flood", max_records=10):
    data = fetch_gdelt_articles(query=query, max_records=max_records)
    if not data:
        print("[gdelt] No data fetched from GDELT.")
        return

    insert("gdelt", data)

    for record in data:
        record_json_safe = convert_for_json(record)
        send_to_kafka("news", record_json_safe)
        print(f"Sent to Kafka: {record['data']['title']}")

    print(f"GDELT collector finished. {len(data)} records processed.")


if __name__ == "__main__":
    collect_gdelt()
