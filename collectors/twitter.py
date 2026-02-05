import tweepy
import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

# App-only credentials
BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")

# Set up client
client = tweepy.Client(bearer_token=BEARER_TOKEN)

def fetch_tweets(query, max_results=10):
    response = client.search_recent_tweets(query=query, max_results=max_results, tweet_fields=['created_at'])
    tweets = []
    if response.data:
        for tweet in response.data:
            tweets.append({
                "text": tweet.text,
                "created_at": tweet.created_at
            })
    return tweets

if __name__ == "__main__":
    data = fetch_tweets("earthquake", max_results=5)
    print(data)
