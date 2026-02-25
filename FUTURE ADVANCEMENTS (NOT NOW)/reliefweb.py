"""
ReliefWeb API Collector
Fetches humanitarian crisis data, disaster reports, and emergency updates
"""
import os
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.reliefweb.int/v1"
APP_NAME = os.getenv("RELIEFWEB_APP_NAME", "WorldPulseResearch")

def fetch_reports(
    query: Optional[str] = None,
    disaster_type: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Fetch humanitarian reports and updates
    
    Disaster types: earthquake, flood, tropical cyclone, drought, etc.
    """
    url = f"{BASE_URL}/reports"
    
    # Build filter
    filter_params = {}
    
    if disaster_type:
        filter_params["field"] = "disaster_type.name"
        filter_params["value"] = disaster_type
    
    if country:
        filter_params["field"] = "country.name"
        filter_params["value"] = country
    
    params = {
        "appname": APP_NAME,
        "profile": "full",
        "limit": limit,
        "sort[]": "date:desc"
    }
    
    if query:
        params["query[value]"] = query
    
    if filter_params:
        params["filter[field]"] = filter_params.get("field")
        params["filter[value]"] = filter_params.get("value")
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for report in data.get("data", []):
            fields = report.get("fields", {})
            
            # Extract countries
            countries = [
                c.get("name") 
                for c in fields.get("country", [])
            ]
            
            # Extract disasters
            disasters = [
                {
                    "name": d.get("name"),
                    "type": d.get("type", [{}])[0].get("name") if d.get("type") else None,
                    "status": d.get("status")
                }
                for d in fields.get("disaster", [])
            ]
            
            # Extract sources
            sources = [
                s.get("name")
                for s in fields.get("source", [])
            ]
            
            record = {
                "id": f"reliefweb_{report.get('id')}",
                "source": "reliefweb",
                "category": "humanitarian",
                "collected_at": collected_at,
                "data": {
                    "report_id": report.get("id"),
                    "title": fields.get("title"),
                    "body": fields.get("body", "")[:2000],  # Truncate
                    "summary": fields.get("summary"),
                    "date": {
                        "created": fields.get("date", {}).get("created"),
                        "changed": fields.get("date", {}).get("changed"),
                        "original": fields.get("date", {}).get("original")
                    },
                    "countries": countries,
                    "disasters": disasters,
                    "sources": sources,
                    "language": fields.get("language", [{}])[0].get("name") if fields.get("language") else None,
                    "url": fields.get("url"),
                    "file_urls": [f.get("url") for f in fields.get("file", [])],
                    "type": "humanitarian_report"
                }
            }
            records.append(record)
        
        print(f"ReliefWeb: Fetched {len(records)} reports")
        return records
        
    except requests.RequestException as e:
        print(f"ReliefWeb Reports API error: {e}")
        return []

def fetch_disasters(
    status: str = "current",
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Fetch active disasters
    """
    url = f"{BASE_URL}/disasters"
    
    params = {
        "appname": APP_NAME,
        "profile": "full",
        "limit": limit,
        "filter[field]": "status",
        "filter[value]": status,
        "sort[]": "date:desc"
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for disaster in data.get("data", []):
            fields = disaster.get("fields", {})
            
            # Extract countries
            countries = [
                c.get("name")
                for c in fields.get("country", [])
            ]
            
            # Extract disaster type
            disaster_type = None
            if fields.get("type"):
                disaster_type = fields.get("type")[0].get("name")
            
            record = {
                "id": f"reliefweb_disaster_{disaster.get('id')}",
                "source": "reliefweb",
                "category": "humanitarian",
                "collected_at": collected_at,
                "data": {
                    "disaster_id": disaster.get("id"),
                    "name": fields.get("name"),
                    "description": fields.get("description", "")[:1000],
                    "status": fields.get("status"),
                    "type": disaster_type,
                    "countries": countries,
                    "date": {
                        "created": fields.get("date", {}).get("created"),
                        "event": fields.get("date", {}).get("event")
                    },
                    "glide": fields.get("glide"),  # Global ID
                    "url": fields.get("url"),
                    "type": "disaster"
                }
            }
            records.append(record)
        
        print(f"ReliefWeb: Fetched {len(records)} disasters")
        return records
        
    except requests.RequestException as e:
        print(f"ReliefWeb Disasters API error: {e}")
        return []

def fetch_jobs(
    country: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Fetch humanitarian job postings (indicates crisis response activity)
    """
    url = f"{BASE_URL}/jobs"
    
    params = {
        "appname": APP_NAME,
        "profile": "full",
        "limit": limit,
        "sort[]": "date:desc"
    }
    
    if country:
        params["filter[field]"] = "country.name"
        params["filter[value]"] = country
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        
        for job in data.get("data", []):
            fields = job.get("fields", {})
            
            record = {
                "id": f"reliefweb_job_{job.get('id')}",
                "source": "reliefweb",
                "category": "humanitarian",
                "collected_at": collected_at,
                "data": {
                    "job_id": job.get("id"),
                    "title": fields.get("title"),
                    "body": fields.get("body", "")[:1000],
                    "organization": fields.get("source", [{}])[0].get("name") if fields.get("source") else None,
                    "career_categories": [c.get("name") for c in fields.get("career_categories", [])],
                    "theme": [t.get("name") for t in fields.get("theme", [])],
                    "country": [c.get("name") for c in fields.get("country", [])],
                    "closing_date": fields.get("date", {}).get("closing"),
                    "created_date": fields.get("date", {}).get("created"),
                    "url": fields.get("url"),
                    "type": "humanitarian_job"
                }
            }
            records.append(record)
        
        print(f"ReliefWeb: Fetched {len(records)} jobs")
        return records
        
    except requests.RequestException as e:
        print(f"ReliefWeb Jobs API error: {e}")
        return []

def fetch_reliefweb_data() -> List[Dict[str, Any]]:
    """
    Main collector function - comprehensive humanitarian data
    """
    all_records = []
    
    # Fetch recent reports
    reports = fetch_reports(limit=20)
    all_records.extend(reports)
    
    # Fetch current disasters
    disasters = fetch_disasters(status="current", limit=15)
    all_records.extend(disasters)
    
    # Fetch ongoing disasters
    ongoing = fetch_disasters(status="ongoing", limit=10)
    all_records.extend(ongoing)
    
    # Fetch recent jobs (indicates response activity)
    jobs = fetch_jobs(limit=10)
    all_records.extend(jobs)
    
    # Fetch crisis-specific reports
    crisis_reports = fetch_reports(
        query="emergency crisis disaster",
        limit=10
    )
    all_records.extend(crisis_reports)
    
    return all_records

if __name__ == "__main__":
    # Test the collector
    data = fetch_reliefweb_data()
    print(f"Total records collected: {len(data)}")
    if data:
        print(f"Sample record: {data[0]}")
