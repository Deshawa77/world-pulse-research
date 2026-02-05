import os
import requests
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Get the API key after loading .env
API_KEY = os.getenv("NEWS_API_KEY")
print("NEWS_API_KEY =", API_KEY)  # Should now print your actual key

BASE_URL = "https://newsapi.org/v2/everything"

def fetch_news(query, page_size=10):
    """
    Fetch recent news articles for a keyword.
    """
    params = {
        "q": query,
        "pageSize": page_size,
        "apiKey": API_KEY,
        "sortBy": "publishedAt",
        "language": "en"
    }

    response = requests.get(BASE_URL, params=params)
    data = response.json()

    articles = []
    if data.get("status") == "ok":
        for item in data.get("articles", []):
            articles.append({
                "title": item["title"],
                "description": item["description"],
                "url": item["url"],
                "published_at": item["publishedAt"]
            })
    else:
        print("Error:", data)

    return articles

if __name__ == "__main__":
    news_data = fetch_news("earthquake", page_size=5)
    for article in news_data:
        print(article)
