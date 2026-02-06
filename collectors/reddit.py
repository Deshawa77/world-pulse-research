import os
import json
from datetime import datetime, timezone
import praw
from bson import ObjectId
from dotenv import load_dotenv
from database.mongo import insert

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
                ).isoformat()
            }
        })

    return records

def convert_datetimes(obj):
    """Recursively convert all datetime objects in a dict/list to ISO strings and ObjectId to str"""
    if isinstance(obj, dict):
        return {k: convert_datetimes(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_datetimes(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj

if __name__ == "__main__":
    data = fetch_reddit_posts("earthquake", limit=5)
    
    # Insert into MongoDB
    insert("reddit", data)

    # Convert datetimes and ObjectId for safe printing
    safe_data = convert_datetimes(data)
    print(json.dumps(safe_data, indent=2, ensure_ascii=False))
