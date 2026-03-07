"""
Script to fix country feature timestamps to current time.
This will refresh the timestamps for all 233 countries.
"""
from pymongo import MongoClient
from datetime import datetime

def fix_timestamps():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['world_pulse']
    
    # Get current timestamp
    now = datetime.utcnow()
    now_iso = now.isoformat()
    
    print(f"Current timestamp: {now_iso}")
    print("-" * 50)
    
    # Update all country features with current timestamp
    result = db.country_features.update_many(
        {},
        {"$set": {"timestamp": now_iso}}
    )
    
    print(f"Updated {result.modified_count} documents")
    
    # Verify the update
    latest = list(db.country_features.find().sort('timestamp', -1).limit(3))
    print(f"\nLatest timestamps after update:")
    for doc in latest:
        print(f"  {doc.get('country', 'Unknown')}: {doc.get('timestamp', 'N/A')}")
    
    return result.modified_count

if __name__ == "__main__":
    count = fix_timestamps()
    print(f"\n✅ Fixed timestamps for {count} countries")

