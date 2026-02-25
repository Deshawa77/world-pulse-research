"""
Messari API Collector
Fetches cryptocurrency on-chain analytics, market data, and research
"""
import os
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("MESSARI_API_KEY")
BASE_URL = "https://data.messari.io/api/v1"

def fetch_asset_metrics(asset: str = "bitcoin") -> Optional[Dict[str, Any]]:
    """
    Fetch on-chain and market metrics for a cryptocurrency
    """
    if not API_KEY:
        print("Messari API key not configured")
        return None
    
    url = f"{BASE_URL}/assets/{asset}/metrics"
    
    headers = {
        "x-messari-api-key": API_KEY
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("data"):
            return None
        
        metrics = data.get("data", {})
        market_data = metrics.get("market_data", {})
        on_chain = metrics.get("on_chain_data", {})
        supply = metrics.get("supply", {})
        
        collected_at = datetime.now(timezone.utc).isoformat()
        
        return {
            "id": f"messari_{asset}_{collected_at}",
            "source": "messari",
            "category": "crypto",
            "collected_at": collected_at,
            "data": {
                "asset": asset,
                "symbol": metrics.get("symbol"),
                "name": metrics.get("name"),
                "price_usd": market_data.get("price_usd"),
                "price_btc": market_data.get("price_btc"),
                "volume_last_24h": market_data.get("volume_last_24_hours"),
                "real_volume_last_24h": market_data.get("real_volume_last_24_hours"),
                "percent_change_usd_last_24h": market_data.get("percent_change_usd_last_24_hours"),
                "percent_change_btc_last_24h": market_data.get("percent_change_btc_last_24_hours"),
                "market_cap": market_data.get("market_cap"),
                "rank": market_data.get("rank"),
                "circulating_supply": supply.get("circulating"),
                "max_supply": supply.get("max"),
                "active_addresses": on_chain.get("active_addresses"),
                "transaction_volume": on_chain.get("transaction_volume"),
                "hash_rate": on_chain.get("hash_rate"),
                "mining_revenue": on_chain.get("mining_revenue"),
                "type": "asset_metrics"
            }
        }
        
    except requests.RequestException as e:
        print(f"Messari Asset Metrics API error: {e}")
        return None

def fetch_market_data(asset: str = "bitcoin") -> Optional[Dict[str, Any]]:
    """
    Fetch market data for a cryptocurrency
    """
    if not API_KEY:
        return None
    
    url = f"{BASE_URL}/assets/{asset}/market-data"
    
    headers = {
        "x-messari-api-key": API_KEY
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("data"):
            return None
        
        market_data = data.get("data", {})
        collected_at = datetime.now(timezone.utc).isoformat()
        
        return {
            "id": f"messari_market_{asset}_{collected_at}",
            "source": "messari",
            "category": "crypto",
            "collected_at": collected_at,
            "data": {
                "asset": asset,
                "price": market_data.get("price"),
                "volume": market_data.get("volume"),
                "market_cap": market_data.get("market_cap"),
                "percent_change_24h": market_data.get("percent_change_24h"),
                "percent_change_7d": market_data.get("percent_change_7d"),
                "percent_change_30d": market_data.get("percent_change_30d"),
                "type": "market_data"
            }
        }
        
    except requests.RequestException as e:
        print(f"Messari Market Data API error: {e}")
        return None

def fetch_news(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch crypto news from Messari
    """
    if not API_KEY:
        return []
    
    url = f"{BASE_URL}/news"
    
    headers = {
        "x-messari-api-key": API_KEY
    }
    
    params = {
        "limit": limit
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for news in data.get("data", []):
            record = {
                "id": f"messari_news_{news.get('id')}_{collected_at}",
                "source": "messari",
                "category": "crypto",
                "collected_at": collected_at,
                "data": {
                    "news_id": news.get("id"),
                    "title": news.get("title"),
                    "content": news.get("content", "")[:1000],
                    "author": news.get("author", {}).get("name"),
                    "tags": [t.get("name") for t in news.get("tags", [])],
                    "published_at": news.get("published_at"),
                    "url": news.get("url"),
                    "type": "crypto_news"
                }
            }
            records.append(record)
        
        print(f"Messari: Fetched {len(records)} news articles")
        return records
        
    except requests.RequestException as e:
        print(f"Messari News API error: {e}")
        return []

def fetch_all_assets(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch list of all tracked assets
    """
    if not API_KEY:
        return []
    
    url = f"{BASE_URL}/assets"
    
    headers = {
        "x-messari-api-key": API_KEY
    }
    
    params = {
        "limit": limit,
        "fields": "id,symbol,name,metrics/market_data/price_usd,metrics/market_data/market_cap"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for asset in data.get("data", []):
            metrics = asset.get("metrics", {})
            market_data = metrics.get("market_data", {})
            
            record = {
                "id": f"messari_asset_{asset.get('symbol')}_{collected_at}",
                "source": "messari",
                "category": "crypto",
                "collected_at": collected_at,
                "data": {
                    "asset_id": asset.get("id"),
                    "symbol": asset.get("symbol"),
                    "name": asset.get("name"),
                    "slug": asset.get("slug"),
                    "price_usd": market_data.get("price_usd"),
                    "market_cap": market_data.get("market_cap"),
                    "type": "asset_listing"
                }
            }
            records.append(record)
        
        print(f"Messari: Fetched {len(records)} assets")
        return records
        
    except requests.RequestException as e:
        print(f"Messari Assets API error: {e}")
        return []

def fetch_messari_data() -> List[Dict[str, Any]]:
    """
    Main collector function - comprehensive crypto analytics
    """
    all_records = []
    
    # Major cryptocurrencies to track
    assets = ["bitcoin", "ethereum", "cardano", "solana", "polkadot", "chainlink"]
    
    # Fetch metrics for each asset
    for asset in assets:
        metrics = fetch_asset_metrics(asset)
        if metrics:
            all_records.append(metrics)
        
        market = fetch_market_data(asset)
        if market:
            all_records.append(market)
    
    # Fetch news
    news = fetch_news(limit=10)
    all_records.extend(news)
    
    # Fetch asset listings
    assets_list = fetch_all_assets(limit=20)
    all_records.extend(assets_list)
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_messari_data()
    print(f"Total records collected: {len(data)}")
    if data:
        print(f"Sample record: {data[0]}")
