"""
Reddit Enhanced Collector
Extended Reddit data collection with sentiment analysis and multiple subreddits
"""
import os
import praw
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# Reddit API credentials
CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
USER_AGENT = os.getenv("REDDIT_USER_AGENT", "WorldPulse:v1.0 (by /u/worldpulse)")

def get_reddit_instance() -> Optional[praw.Reddit]:
    """Initialize Reddit API instance"""
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Reddit API credentials not configured")
        return None
    
    try:
        reddit = praw.Reddit(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            user_agent=USER_AGENT
        )
        return reddit
    except Exception as e:
        print(f"Reddit initialization error: {e}")
        return None

def fetch_subreddit_posts(
    subreddit_name: str,
    sort: str = "hot",
    limit: int = 10,
    time_filter: str = "day"
) -> List[Dict[str, Any]]:
    """
    Fetch posts from a specific subreddit
    """
    reddit = get_reddit_instance()
    if not reddit:
        return []
    
    try:
        subreddit = reddit.subreddit(subreddit_name)
        
        if sort == "hot":
            posts = subreddit.hot(limit=limit)
        elif sort == "new":
            posts = subreddit.new(limit=limit)
        elif sort == "top":
            posts = subreddit.top(time_filter=time_filter, limit=limit)
        elif sort == "rising":
            posts = subreddit.rising(limit=limit)
        else:
            posts = subreddit.hot(limit=limit)
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        for post in posts:

            record = {
                "id": f"reddit_{subreddit_name}_{post.id}",
                "source": "reddit_enhanced",
                "category": "social_media",
                "collected_at": collected_at,
                "data": {
                    "post_id": post.id,
                    "title": post.title,
                    "text": post.selftext[:2000] if post.selftext else "",
                    "author": str(post.author),
                    "subreddit": subreddit_name,
                    "score": post.score,
                    "upvote_ratio": post.upvote_ratio,
                    "num_comments": post.num_comments,
                    "url": post.url,
                    "permalink": f"https://reddit.com{post.permalink}",
                    "created_utc": datetime.fromtimestamp(
                        post.created_utc, 
                        tz=timezone.utc
                    ).isoformat(),
                    "is_self": post.is_self,
                    "over_18": post.over_18,
                    "spoiler": post.spoiler,
                    "stickied": post.stickied,
                    "sort_type": sort,
                    "type": "post"
                }
            }
            records.append(record)
        
        print(f"Reddit Enhanced: Fetched {len(records)} posts from r/{subreddit_name}")
        return records
        
    except Exception as e:
        print(f"Reddit API error for r/{subreddit_name}: {e}")
        return []

def fetch_post_comments(post_id: str, subreddit: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch comments from a specific post
    """
    reddit = get_reddit_instance()
    if not reddit:
        return []
    
    try:
        submission = reddit.submission(id=post_id)
        submission.comments.replace_more(limit=0)  # Remove MoreComments objects
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for comment in submission.comments.list()[:limit]:
            record = {
                "id": f"reddit_comment_{post_id}_{comment.id}",
                "source": "reddit_enhanced",
                "category": "social_media",
                "collected_at": collected_at,
                "data": {
                    "comment_id": comment.id,
                    "post_id": post_id,
                    "subreddit": subreddit,
                    "text": comment.body[:1000],
                    "author": str(comment.author),
                    "score": comment.score,
                    "created_utc": datetime.fromtimestamp(
                        comment.created_utc,
                        tz=timezone.utc
                    ).isoformat(),
                    "is_submitter": comment.is_submitter,
                    "parent_id": comment.parent_id,
                    "type": "comment"
                }
            }
            records.append(record)
        
        print(f"Reddit Enhanced: Fetched {len(records)} comments from post {post_id}")
        return records
        
    except Exception as e:
        print(f"Reddit Comments API error: {e}")
        return []

def search_reddit(query: str, subreddit: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search Reddit for specific topics
    """
    reddit = get_reddit_instance()
    if not reddit:
        return []
    
    try:
        if subreddit:
            results = reddit.subreddit(subreddit).search(query, limit=limit, sort="relevance")
        else:
            results = reddit.subreddit("all").search(query, limit=limit, sort="relevance")
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for post in results:
            record = {
                "id": f"reddit_search_{post.id}_{collected_at}",
                "source": "reddit_enhanced",
                "category": "social_media",
                "collected_at": collected_at,
                "data": {
                    "post_id": post.id,
                    "title": post.title,
                    "text": post.selftext[:1000] if post.selftext else "",
                    "subreddit": str(post.subreddit),
                    "score": post.score,
                    "num_comments": post.num_comments,
                    "url": post.url,
                    "query": query,
                    "created_utc": datetime.fromtimestamp(
                        post.created_utc,
                        tz=timezone.utc
                    ).isoformat(),
                    "type": "search_result"
                }
            }
            records.append(record)
        
        print(f"Reddit Enhanced: Found {len(records)} results for '{query}'")
        return records
        
    except Exception as e:
        print(f"Reddit Search API error: {e}")
        return []

def fetch_reddit_enhanced_data() -> List[Dict[str, Any]]:
    """
    Main collector function - comprehensive Reddit data
    """
    all_records = []
    
    # Financial and market subreddits
    financial_subreddits = [
        "wallstreetbets",
        "investing",
        "stocks",
        "StockMarket",
        "CryptoCurrency",
        "Bitcoin",
        "ethereum"
    ]
    
    # News and world events
    news_subreddits = [
        "worldnews",
        "news",
        "politics",
        "science",
        "technology"
    ]
    
    # Crisis and emergency
    crisis_subreddits = [
        "collapse",
        "preppers",
        "survival",
        "ClimateChange",
        "environment"
    ]
    
    # Fetch from financial subreddits
    for subreddit in financial_subreddits[:4]:
        posts = fetch_subreddit_posts(subreddit, sort="hot", limit=5)
        all_records.extend(posts)
    
    # Fetch from news subreddits
    for subreddit in news_subreddits[:3]:
        posts = fetch_subreddit_posts(subreddit, sort="top", time_filter="day", limit=5)
        all_records.extend(posts)
    
    # Search for crisis-related content
    crisis_queries = ["crisis", "recession", "inflation", "war", "disaster"]
    for query in crisis_queries[:3]:
        search_results = search_reddit(query, limit=5)
        all_records.extend(search_results)
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_reddit_enhanced_data()
    print(f"Total records collected: {len(data)}")
    if data:
        print(f"Sample record: {data[0]}")
