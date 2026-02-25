"""
OpenAQ (Open Air Quality) API Collector
Fetches air quality data globally for environmental health monitoring
"""
import os
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# OpenAQ API v2
BASE_URL = "https://api.openaq.org/v2"
API_KEY = os.getenv("OPENAQ_API_KEY")  # Optional but recommended

def fetch_latest_measurements(
    country: Optional[str] = None,
    city: Optional[str] = None,
    parameter: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Fetch latest air quality measurements
    
    Parameters: pm25, pm10, o3, no2, so2, co, bc
    """
    url = f"{BASE_URL}/latest"
    
    params = {
        "limit": limit
    }
    
    if country:
        params["country"] = country
    
    if city:
        params["city"] = city
    
    if parameter:
        params["parameter"] = parameter
    
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for result in data.get("results", []):
            measurements = result.get("measurements", [])
            
            for measurement in measurements:
                record = {
                    "id": f"openaq_{result.get('location')}_{measurement.get('parameter')}_{collected_at}",
                    "source": "openaq",
                    "category": "environmental",
                    "collected_at": collected_at,
                    "data": {
                        "location": result.get("location"),
                        "city": result.get("city"),
                        "country": result.get("country"),
                        "coordinates": result.get("coordinates"),
                        "parameter": measurement.get("parameter"),
                        "value": measurement.get("value"),
                        "unit": measurement.get("unit"),
                        "last_updated": measurement.get("lastUpdated"),
                        "source_name": result.get("sourceName"),
                        "type": "air_quality"
                    }
                }
                records.append(record)
        
        print(f"OpenAQ: Fetched {len(records)} air quality measurements")
        return records
        
    except requests.RequestException as e:
        print(f"OpenAQ API error: {e}")
        return []

def fetch_locations(
    country: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Fetch monitoring locations
    """
    url = f"{BASE_URL}/locations"
    
    params = {
        "limit": limit
    }
    
    if country:
        params["country"] = country
    
    if city:
        params["city"] = city
    
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for result in data.get("results", []):
            record = {
                "id": f"openaq_loc_{result.get('id')}_{collected_at}",
                "source": "openaq",
                "category": "environmental",
                "collected_at": collected_at,
                "data": {
                    "location_id": result.get("id"),
                    "location": result.get("location"),
                    "city": result.get("city"),
                    "country": result.get("country"),
                    "coordinates": result.get("coordinates"),
                    "parameters": result.get("parameters", []),
                    "count": result.get("count"),
                    "first_updated": result.get("firstUpdated"),
                    "last_updated": result.get("lastUpdated"),
                    "type": "monitoring_location"
                }
            }
            records.append(record)
        
        print(f"OpenAQ: Fetched {len(records)} monitoring locations")
        return records
        
    except requests.RequestException as e:
        print(f"OpenAQ Locations API error: {e}")
        return []

def fetch_cities(country: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch cities with air quality monitoring
    """
    url = f"{BASE_URL}/cities"
    
    params = {
        "limit": limit
    }
    
    if country:
        params["country"] = country
    
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for result in data.get("results", []):
            record = {
                "id": f"openaq_city_{result.get('city')}_{collected_at}",
                "source": "openaq",
                "category": "environmental",
                "collected_at": collected_at,
                "data": {
                    "city": result.get("city"),
                    "country": result.get("country"),
                    "count": result.get("count"),
                    "locations": result.get("locations"),
                    "first_updated": result.get("firstUpdated"),
                    "last_updated": result.get("lastUpdated"),
                    "type": "city"
                }
            }
            records.append(record)
        
        print(f"OpenAQ: Fetched {len(records)} cities")
        return records
        
    except requests.RequestException as e:
        print(f"OpenAQ Cities API error: {e}")
        return []

def fetch_parameters() -> List[Dict[str, Any]]:
    """
    Fetch available measurement parameters
    """
    url = f"{BASE_URL}/parameters"
    
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for result in data.get("results", []):
            record = {
                "id": f"openaq_param_{result.get('id')}_{collected_at}",
                "source": "openaq",
                "category": "environmental",
                "collected_at": collected_at,
                "data": {
                    "parameter_id": result.get("id"),
                    "name": result.get("name"),
                    "description": result.get("description"),
                    "preferred_unit": result.get("preferredUnit"),
                    "type": "parameter"
                }
            }
            records.append(record)
        
        return records
        
    except requests.RequestException as e:
        print(f"OpenAQ Parameters API error: {e}")
        return []

def fetch_openaq_data() -> List[Dict[str, Any]]:
    """
    Main collector function - comprehensive air quality data
    """
    all_records = []
    
    # Major countries to monitor
    countries = ["US", "CN", "IN", "GB", "DE", "FR", "JP", "BR", "RU", "CA"]
    
    # Fetch latest measurements for PM2.5 (most important pollutant)
    for country in countries[:5]:  # Limit to avoid rate limits
        measurements = fetch_latest_measurements(
            country=country,
            parameter="pm25",
            limit=20
        )
        all_records.extend(measurements)
    
    # Fetch some locations
    locations = fetch_locations(limit=30)
    all_records.extend(locations)
    
    # Fetch cities
    cities = fetch_cities(limit=30)
    all_records.extend(cities)
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_openaq_data()
    print(f"Total records collected: {len(data)}")
    if data:
        print(f"Sample record: {data[0]}")
