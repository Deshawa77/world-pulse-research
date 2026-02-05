import os
import praw
from dotenv import load_dotenv

load_dotenv()

reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent="world_pulse_app"
)

def fetch_reddit_posts(query, limit=5):
    posts = []

    for submission in reddit.subreddit("all").search(query, limit=limit, sort="new"):
        posts.append({
            "title": submission.title,
            "score": submission.score,
            "subreddit": str(submission.subreddit),
            "url": submission.url,
            "created_utc": submission.created_utc
        })

    return posts


if __name__ == "__main__":
    data = fetch_reddit_posts("earthquake", limit=5)
    for d in data:
        print(d)
