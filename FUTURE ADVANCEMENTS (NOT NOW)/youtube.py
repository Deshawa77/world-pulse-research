"""
YouTube Data API Collector
Fetches trending videos, comments sentiment, and search trends
"""
import os
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")
BASE_URL = "https://www.googleapis.com/youtube/v3"

def fetch_trending_videos(region_code: str = "US", max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch trending YouTube videos for sentiment analysis
    """
    if not API_KEY:
        print("YouTube API key not configured")
        return []
    
    url = f"{BASE_URL}/videos"
    params = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": region_code,
        "maxResults": max_results,
        "key": API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            
            record = {
                "id": item.get("id"),
                "source": "youtube",
                "category": "social_media",
                "collected_at": collected_at,
                "data": {
                    "title": snippet.get("title"),
                    "description": snippet.get("description"),
                    "channel": snippet.get("channelTitle"),
                    "published_at": snippet.get("publishedAt"),
                    "tags": snippet.get("tags", []),
                    "category_id": snippet.get("categoryId"),
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "region": region_code,
                    "url": f"https://youtube.com/watch?v={item.get('id')}"
                }
            }
            records.append(record)
        
        print(f"YouTube: Fetched {len(records)} trending videos for {region_code}")
        return records
        
    except requests.RequestException as e:
        print(f"YouTube API error: {e}")
        return []

def fetch_video_comments(video_id: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch comments for sentiment analysis
    """
    if not API_KEY:
        return []
    
    url = f"{BASE_URL}/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": max_results,
        "order": "relevance",
        "key": API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for item in data.get("items", []):
            snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            
            record = {
                "id": item.get("id"),
                "source": "youtube_comments",
                "category": "social_media",
                "collected_at": collected_at,
                "data": {
                    "video_id": video_id,
                    "text": snippet.get("textDisplay"),
                    "author": snippet.get("authorDisplayName"),
                    "like_count": snippet.get("likeCount", 0),
                    "published_at": snippet.get("publishedAt"),
                    "url": f"https://youtube.com/watch?v={video_id}"
                }
            }
            records.append(record)
        
        return records
        
    except requests.RequestException as e:
        print(f"YouTube Comments API error: {e}")
        return []

def search_videos(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Search YouTube videos by query (e.g., 'earthquake', 'crisis', 'economy')
    """
    if not API_KEY:
        return []
    
    url = f"{BASE_URL}/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "relevance",
        "maxResults": max_results,
        "key": API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            
            record = {
                "id": item.get("id", {}).get("videoId"),
                "source": "youtube_search",
                "category": "social_media",
                "collected_at": collected_at,
                "data": {
                    "query": query,
                    "title": snippet.get("title"),
                    "description": snippet.get("description"),
                    "channel": snippet.get("channelTitle"),
                    "published_at": snippet.get("publishedAt"),
                    "url": f"https://youtube.com/watch?v={item.get('id', {}).get('videoId')}"
                }
            }
            records.append(record)
        
        print(f"YouTube: Searched '{query}' - found {len(records)} videos")
        return records
        
    except requests.RequestException as e:
        print(f"YouTube Search API error: {e}")
        return []

def fetch_youtube_data() -> List[Dict[str, Any]]:
    """
    Main collector function - fetches trending and crisis-related content
    """
    all_records = []
    
    # Fetch trending videos from multiple regions
    regions = ["US", "GB", "CA", "AU", "IN"]
    for region in regions:
        trending = fetch_trending_videos(region, max_results=5)
        all_records.extend(trending)
    
    # Search for crisis-related content
    crisis_queries = ["earthquake", "flood", "crisis", "economy", "war", "pandemic"]
    for query in crisis_queries:
        search_results = search_videos(query, max_results=3)
        all_records.extend(search_results)
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_youtube_data()
    print(f"Total records collected: {len(data)}")
    if data:
        print(f"Sample record: {data[0]}")
