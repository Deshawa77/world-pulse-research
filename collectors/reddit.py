import os
import json
from datetime import datetime, timezone
import praw
from bson import ObjectId
from dotenv import load_dotenv
from database.mongo import insert
from backend.kafka_client import send_to_kafka  # Make sure this exists

# Load environment variables
load_dotenv()

reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent="world_pulse_app"
)

def fetch_reddit_posts(query: str, limit: int = 5):
    """
    Fetch recent Reddit posts and return standardized records.
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    records = []

    for submission in reddit.subreddit("all").search(
        query,
        limit=limit,
        sort="new"
    ):
        records.append({
            "source": "reddit",
            "category": "social",
            "collected_at": collected_at,
            "data": {
                "query": query,
                "title": submission.title,
                "text": submission.selftext,
                "score": submission.score,
                "subreddit": str(submission.subreddit),
                "url": submission.url,
                "created_utc": datetime.fromtimestamp(
                    submission.created_utc,
                    tz=timezone.utc
                )
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

def collect_reddit(query="earthquake", limit=5):
    """
    Fetch Reddit data, send to Kafka, and insert into MongoDB.
    """
    data = fetch_reddit_posts(query=query, limit=limit)
    if not data:
        print("No Reddit posts fetched.")
        return

    # Insert into MongoDB (warehouse)
    insert("reddit", data)

    # Send each record to Kafka
    for record in data:
        record_json_safe = convert_for_json(record)  # convert datetimes/ObjectId
        send_to_kafka(record_json_safe)
        print(f"Sent to Kafka: {record['data']['title']}")

    print(f"Reddit collector finished. {len(data)} records processed.")


if __name__ == "__main__":
    collect_reddit()
