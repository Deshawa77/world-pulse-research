"""
NASA Earth Data API Collector
Fetches climate anomalies, natural disasters, and environmental data from NASA
"""
import os
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# NASA APIs
EONET_API = "https://eonet.gsfc.nasa.gov/api/v3"  # Earth Observatory Natural Event Tracker
POWER_API = "https://power.larc.nasa.gov/api/temporal/daily/point"  # Climate data
API_KEY = os.getenv("NASA_API_KEY")  # Optional for some endpoints

def fetch_natural_events(
    days: int = 7,
    category: Optional[str] = None,
    status: str = "open"
) -> List[Dict[str, Any]]:
    """
    Fetch natural events from NASA EONET (earthquakes, wildfires, storms, etc.)
    
    Categories: wildfires, severeStorms, volcanoes, icebergs, drought, dustHaze, 
                floods, landslides, manmade, seaLakeIce, snow, tempExtremes
    """
    url = f"{EONET_API}/events"
    
    params = {
        "days": days,
        "status": status
    }
    
    if category:
        params["category"] = category
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for event in data.get("events", []):
            # Get geometry (location data)
            geometries = event.get("geometries", [])
            if geometries:
                geometry = geometries[0]  # Use first geometry
                coordinates = geometry.get("coordinates", [None, None])
                date = geometry.get("date")
            else:
                coordinates = [None, None]
                date = None
            
            record = {
                "id": f"nasa_eonet_{event.get('id')}",
                "source": "nasa_eonet",
                "category": "environmental",
                "collected_at": collected_at,
                "data": {
                    "event_id": event.get("id"),
                    "title": event.get("title"),
                    "description": event.get("description"),
                    "link": event.get("link"),
                    "categories": [cat.get("title") for cat in event.get("categories", [])],
                    "sources": [src.get("url") for src in event.get("sources", [])],
                    "longitude": coordinates[0],
                    "latitude": coordinates[1],
                    "date": date,
                    "status": status,
                    "type": "natural_event"
                }
            }
            records.append(record)
        
        print(f"NASA EONET: Fetched {len(records)} natural events")
        return records
        
    except requests.RequestException as e:
        print(f"NASA EONET API error: {e}")
        return []

def fetch_climate_data(
    latitude: float,
    longitude: float,
    parameters: List[str] = None,
    days: int = 7
) -> Optional[Dict[str, Any]]:
    """
    Fetch climate data from NASA POWER API
    
    Parameters: T2M (temperature), PRECTOT (precipitation), WS10M (wind speed),
                RH2M (humidity), ALLSKY_SFC_SW_DWN (solar radiation)
    """
    if parameters is None:
        parameters = ["T2M", "PRECTOT", "WS10M", "RH2M"]
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    params = {
        "parameters": ",".join(parameters),
        "community": "RE",  # Renewable Energy
        "longitude": longitude,
        "latitude": latitude,
        "start": start_date.strftime("%Y%m%d"),
        "end": end_date.strftime("%Y%m%d"),
        "format": "JSON"
    }
    
    try:
        response = requests.get(POWER_API, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        
        # Extract properties
        properties = data.get("properties", {})
        parameter_data = properties.get("parameter", {})
        
        record = {
            "id": f"nasa_climate_{latitude}_{longitude}_{collected_at}",
            "source": "nasa_power",
            "category": "environmental",
            "collected_at": collected_at,
            "data": {
                "latitude": latitude,
                "longitude": longitude,
                "location": properties.get("location"),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "parameters": {
                    param: {
                        "avg": sum(values.values()) / len(values) if values else 0,
                        "max": max(values.values()) if values else 0,
                        "min": min(values.values()) if values else 0,
                        "unit": self._get_unit(param)
                    }
                    for param, values in parameter_data.items()
                },
                "type": "climate_data"
            }
        }
        
        return record
        
    except requests.RequestException as e:
        print(f"NASA POWER API error: {e}")
        return None

def _get_unit(parameter: str) -> str:
    """Get unit for NASA POWER parameter"""
    units = {
        "T2M": "C",
        "PRECTOT": "mm/day",
        "WS10M": "m/s",
        "RH2M": "%",
        "ALLSKY_SFC_SW_DWN": "kW-hr/m^2/day"
    }
    return units.get(parameter, "unknown")

def fetch_wildfires(days: int = 7) -> List[Dict[str, Any]]:
    """Fetch wildfire events"""
    return fetch_natural_events(days=days, category="wildfires")

def fetch_severe_storms(days: int = 7) -> List[Dict[str, Any]]:
    """Fetch severe storm events"""
    return fetch_natural_events(days=days, category="severeStorms")

def fetch_floods(days: int = 7) -> List[Dict[str, Any]]:
    """Fetch flood events"""
    return fetch_natural_events(days=days, category="floods")

def fetch_volcanoes(days: int = 7) -> List[Dict[str, Any]]:
    """Fetch volcanic activity"""
    return fetch_natural_events(days=days, category="volcanoes")

def fetch_icebergs(days: int = 7) -> List[Dict[str, Any]]:
    """Fetch iceberg events"""
    return fetch_natural_events(days=days, category="icebergs")

def fetch_nasa_earth_data() -> List[Dict[str, Any]]:
    """
    Main collector function - comprehensive NASA Earth data
    """
    all_records = []
    
    # Fetch various natural events
    wildfires = fetch_wildfires(days=7)
    all_records.extend(wildfires)
    
    storms = fetch_severe_storms(days=7)
    all_records.extend(storms)
    
    floods = fetch_floods(days=7)
    all_records.extend(floods)
    
    volcanoes = fetch_volcanoes(days=30)  # Volcanoes less frequent
    all_records.extend(volcanoes)
    
    icebergs = fetch_icebergs(days=30)
    all_records.extend(icebergs)
    
    # Fetch climate data for major cities
    major_cities = [
        (40.7128, -74.0060),   # New York
        (51.5074, -0.1278),    # London
        (35.6762, 139.6503),   # Tokyo
        (28.6139, 77.2090),    # Delhi
        (-33.8688, 151.2093),  # Sydney
        (55.7558, 37.6173),    # Moscow
        (19.4326, -99.1332),   # Mexico City
        (1.3521, 103.8198),    # Singapore
    ]
    
    for lat, lon in major_cities[:4]:  # Limit to avoid rate limits
        climate = fetch_climate_data(lat, lon, days=7)
        if climate:
            all_records.append(climate)
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_nasa_earth_data()
    print(f"Total records collected: {len(data)}")
    if data:
        print(f"Sample record: {data[0]}")
