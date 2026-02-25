"""
ACLED (Armed Conflict Location & Event Data Project) Collector
Fetches armed conflict, political violence, and protest data globally
"""
import os
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# ACLED API requires authentication
API_KEY = os.getenv("ACLED_API_KEY")
EMAIL = os.getenv("ACLED_EMAIL")
BASE_URL = "https://api.acleddata.com/acled/read"

def fetch_acled_events(
    country: Optional[str] = None,
    event_type: Optional[str] = None,
    days_back: int = 7,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Fetch armed conflict and political violence events
    
    Args:
        country: ISO country code (e.g., 'UKR', 'SYR')
        event_type: Type of event (e.g., 'Battles', 'Protests', 'Riots')
        days_back: Number of days to look back
        limit: Maximum number of records
    """
    if not API_KEY or not EMAIL:
        print("ACLED API credentials not configured")
        return []
    
    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days_back)
    
    params = {
        "key": API_KEY,
        "email": EMAIL,
        "format": "json",
        "limit": limit,
        "event_date": f"{start_date.strftime('%Y-%m-%d')}|{end_date.strftime('%Y-%m-%d')}",
        "event_date_where": "BETWEEN"
    }
    
    if country:
        params["iso"] = country
    
    if event_type:
        params["event_type"] = event_type
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for event in data.get("data", []):
            record = {
                "id": f"acled_{event.get('event_id_cnty', event.get('event_id_no_cnty'))}",
                "source": "acled",
                "category": "conflict",
                "collected_at": collected_at,
                "data": {
                    "event_id": event.get("event_id_cnty"),
                    "event_date": event.get("event_date"),
                    "year": event.get("year"),
                    "time_precision": event.get("time_precision"),
                    "event_type": event.get("event_type"),
                    "sub_event_type": event.get("sub_event_type"),
                    "actor1": event.get("actor1"),
                    "actor2": event.get("actor2"),
                    "country": event.get("country"),
                    "iso3": event.get("iso3"),
                    "region": event.get("region"),
                    "admin1": event.get("admin1"),
                    "admin2": event.get("admin2"),
                    "admin3": event.get("admin3"),
                    "location": event.get("location"),
                    "latitude": float(event.get("latitude", 0)) if event.get("latitude") else None,
                    "longitude": float(event.get("longitude", 0)) if event.get("longitude") else None,
                    "geo_precision": event.get("geo_precision"),
                    "source": event.get("source"),
                    "source_scale": event.get("source_scale"),
                    "notes": event.get("notes"),
                    "fatalities": int(event.get("fatalities", 0)) if event.get("fatalities") else 0,
                    "tags": event.get("tags"),
                    "timestamp": event.get("timestamp")
                }
            }
            records.append(record)
        
        print(f"ACLED: Fetched {len(records)} conflict events")
        return records
        
    except requests.RequestException as e:
        print(f"ACLED API error: {e}")
        return []

def fetch_crisis_hotspots(days_back: int = 7) -> List[Dict[str, Any]]:
    """
    Fetch events from current crisis hotspots
    """
    # Current conflict zones
    hotspots = [
        "UKR",  # Ukraine
        "GAZ",  # Gaza/Palestine
        "SYR",  # Syria
        "YEM",  # Yemen
        "ETH",  # Ethiopia
        "MLI",  # Mali
        "BFA",  # Burkina Faso
        "SDN",  # Sudan
        "MMR",  # Myanmar
        "AFG",  # Afghanistan
    ]
    
    all_records = []
    for country in hotspots:
        events = fetch_acled_events(country=country, days_back=days_back, limit=50)
        all_records.extend(events)
    
    return all_records

def fetch_protests_and_riots(days_back: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch protest and riot events globally
    """
    protests = fetch_acled_events(
        event_type="Protests",
        days_back=days_back,
        limit=limit
    )
    
    riots = fetch_acled_events(
        event_type="Riots",
        days_back=days_back,
        limit=limit
    )
    
    return protests + riots

def fetch_battles_and_violence(days_back: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch battles and violence against civilians
    """
    battles = fetch_acled_events(
        event_type="Battles",
        days_back=days_back,
        limit=limit
    )
    
    violence = fetch_acled_events(
        event_type="Violence against civilians",
        days_back=days_back,
        limit=limit
    )
    
    return battles + violence

def fetch_acled_data() -> List[Dict[str, Any]]:
    """
    Main collector function - comprehensive conflict data
    """
    all_records = []
    
    # Fetch crisis hotspots
    hotspots = fetch_crisis_hotspots(days_back=7)
    all_records.extend(hotspots)
    
    # Fetch protests and riots
    unrest = fetch_protests_and_riots(days_back=3, limit=50)
    all_records.extend(unrest)
    
    # Fetch battles
    battles = fetch_battles_and_violence(days_back=3, limit=50)
    all_records.extend(battles)
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_acled_data()
    print(f"Total records collected: {len(data)}")
    if data:
        print(f"Sample record: {data[0]}")
