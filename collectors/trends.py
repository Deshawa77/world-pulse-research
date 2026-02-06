from pytrends.request import TrendReq
from datetime import datetime, timezone
import time
import random
import json
from database.mongo import insert
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

def convert_datetimes(obj):
    """Recursively convert all datetime objects in a dict/list to ISO strings"""
    if isinstance(obj, dict):
        return {k: convert_datetimes(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_datetimes(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj

if __name__ == "__main__":
    data = fetch_trends("earthquake")
    if data:
        insert("trends", data)
        safe_data = convert_datetimes(data)
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))
