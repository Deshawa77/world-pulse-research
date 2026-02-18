from pytrends.request import TrendReq
from datetime import datetime, timezone
import time
import random
import json
from database.mongo import insert
from backend.kafka_client import send_to_kafka  # Make sure this exists
from pytrends.exceptions import TooManyRequestsError

def fetch_trends(keyword="football", max_retries=5):
    """
    Fetch Google Trends data for the past 7 days and return standardized records.
    Handles rate limiting (429) with retries and random delays.
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    pytrends = TrendReq(hl='en-US', tz=360, timeout=(10, 25))

    for attempt in range(max_retries):
        try:
            pytrends.build_payload(kw_list=[keyword], timeframe='now 7-d', geo='', gprop='')
            time.sleep(random.uniform(5, 10))  # Random delay to avoid rate limits
            df = pytrends.interest_over_time()
            break
        except TooManyRequestsError:
            wait_time = 30 + random.randint(0, 10)  # wait 30–40 sec before retry
            print(f"[Attempt {attempt+1}] Rate limited by Google. Waiting {wait_time} seconds...")
            time.sleep(wait_time)
    else:
        print("Failed to fetch trends data after multiple attempts.")
        return []

    if df.empty:
        print(f"No Google Trends data returned for '{keyword}'")
        return []

    records = []
    for idx, row in df.iterrows():
        records.append({
            "source": "google_trends",
            "category": "public_interest",
            "collected_at": collected_at,
            "data": {
                "keyword": keyword,
                "date": idx.strftime("%Y-%m-%d %H:%M:%S"),
                "interest": int(row[keyword])
            }
        })

    return records

def convert_for_json(obj):
    """Recursively convert datetimes and MongoDB ObjectIds to strings"""
    from bson import ObjectId
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

def collect_trends(keyword="earthquake"):
    """
    Fetch Google Trends data, send each record to Kafka, insert into MongoDB.
    """
    data = fetch_trends(keyword)
    if not data:
        print("No data fetched from Google Trends.")
        return

    # Insert into MongoDB (warehouse)
    insert("trends", data)

    # Send each record to Kafka (make JSON-safe)
    for record in data:
        record_json_safe = convert_for_json(record)
        send_to_kafka("trends", record_json_safe)
        print(f"Sent to Kafka: {record['data']['keyword']} - {record['data']['date']}")

    print(f"Google Trends collector finished. {len(data)} records processed.")


if __name__ == "__main__":
    collect_trends("earthquake")
