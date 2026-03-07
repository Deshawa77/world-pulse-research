Stack Overflow API Collector
Fetches developer sentiment, technology trends, and tech industry health
"""
import os
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# Stack Overflow API (public, no key required for basic usage)
API_KEY = os.getenv("STACKOVERFLOW_API_KEY")  # Optional, increases quota
BASE_URL = "https://api.stackexchange.com/2.3"

def fetch_questions(
    tag: str = "python",
    sort: str = "creation",
    order: str = "desc",
    pagesize: int = 10
) -> List[Dict[str, Any]]:
    """
    Fetch recent questions for a specific tag
    """
    url = f"{BASE_URL}/questions"
    
    params = {
        "order": order,
        "sort": sort,
        "tagged": tag,
        "site": "stackoverflow",
        "pagesize": pagesize,
        "filter": "withbody"
    }
    
    if API_KEY:
        params["key"] = API_KEY
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for item in data.get("items", []):
            owner = item.get("owner", {})
            
            record = {
                "id": f"so_q_{item.get('question_id')}",
                "source": "stackoverflow",
                "category": "tech_community",
                "collected_at": collected_at,
                "data": {
                    "question_id": item.get("question_id"),
                    "title": item.get("title"),
                    "body": item.get("body", "")[:1000],  # Truncate
                    "tags": item.get("tags", []),
                    "score": item.get("score", 0),
                    "view_count": item.get("view_count", 0),
                    "answer_count": item.get("answer_count", 0),
                    "creation_date": datetime.fromtimestamp(
                        item.get("creation_date", 0), 
                        tz=timezone.utc
                    ).isoformat() if item.get("creation_date") else None,
                    "last_activity_date": datetime.fromtimestamp(
                        item.get("last_activity_date", 0),
                        tz=timezone.utc
                    ).isoformat() if item.get("last_activity_date") else None,
                    "is_answered": item.get("is_answered", False),
                    "link": item.get("link"),
                    "author_reputation": owner.get("reputation", 0),
                    "author_name": owner.get("display_name"),
                    "search_tag": tag,
                    "type": "question"
                }
            }
            records.append(record)
        
        print(f"Stack Overflow: Fetched {len(records)} questions for tag '{tag}'")
        return records
        
    except requests.RequestException as e:
        print(f"Stack Overflow API error: {e}")
        return []

def fetch_trending_tags() -> List[Dict[str, Any]]:
    """
    Fetch trending tags on Stack Overflow
    """
    url = f"{BASE_URL}/tags"
    
    params = {
        "order": "desc",
        "sort": "popular",
        "site": "stackoverflow",
        "pagesize": 30
    }
    
    if API_KEY:
        params["key"] = API_KEY
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for item in data.get("items", []):
            record = {
                "id": f"so_tag_{item.get('name')}_{collected_at}",
                "source": "stackoverflow",
                "category": "tech_community",
                "collected_at": collected_at,
                "data": {
                    "tag_name": item.get("name"),
                    "count": item.get("count", 0),
                    "type": "trending_tag"
                }
            }
            records.append(record)
        
        print(f"Stack Overflow: Fetched {len(records)} trending tags")
        return records
        
    except requests.RequestException as e:
        print(f"Stack Overflow Tags API error: {e}")
        return []

def fetch_tag_info(tag: str) -> Optional[Dict[str, Any]]:
    """
    Fetch detailed info about a specific tag
    """
    url = f"{BASE_URL}/tags/{tag}/info"
    
    params = {
        "site": "stackoverflow"
    }
    
    if API_KEY:
        params["key"] = API_KEY
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("items", [])
        if not items:
            return None
        
        item = items[0]
        collected_at = datetime.now(timezone.utc).isoformat()
        
        return {
            "id": f"so_taginfo_{tag}_{collected_at}",
            "source": "stackoverflow",
            "category": "tech_community",
            "collected_at": collected_at,
            "data": {
                "tag_name": item.get("name"),
                "count": item.get("count", 0),
                "excerpt": item.get("excerpt"),
                "tag_wiki": item.get("wiki_body", "")[:500],
                "type": "tag_info"
            }
        }
        
    except requests.RequestException as e:
        print(f"Stack Overflow Tag Info API error: {e}")
        return None

def fetch_stackoverflow_data() -> List[Dict[str, Any]]:
    """
    Main collector function - comprehensive tech community data
    """
    all_records = []
    
    # Technology tags to monitor
    tech_tags = [
        "python", "javascript", "react", "docker", "kubernetes",
        "machine-learning", "artificial-intelligence", "cloud",
        "security", "blockchain", "rust", "go"
    ]
    
    # Fetch questions for key technologies
    for tag in tech_tags[:6]:  # Limit to avoid rate limits
        questions = fetch_questions(tag=tag, pagesize=5)
        all_records.extend(questions)
    
    # Fetch trending tags
    trending = fetch_trending_tags()
    all_records.extend(trending)
    
    # Fetch info for important tags
    important_tags = ["python", "javascript", "ai", "cloud"]
    for tag in important_tags:
        info = fetch_tag_info(tag)
        if info:
            all_records.append(info)
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_stackoverflow_data()
    print(f"Total records collected: {len(data)}")
    if data:
        print(f"Sample record: {data[0]}")
