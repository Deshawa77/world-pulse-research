from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://localhost:27017/')
db = client['world_pulse']

# Check country_features collection
print('=== Country Features Collection ===')
count = db.country_features.count_documents({})
print(f'Total documents: {count}')

# Get latest documents with their timestamps
latest = list(db.country_features.find().sort('timestamp', -1).limit(5))
print(f'\nLatest 5 documents:')
for doc in latest:
    ts = doc.get('timestamp', 'N/A')
    country = doc.get('country', 'Unknown')
    print(f'  {country}: {ts}')

# Get oldest documents
oldest = list(db.country_features.find().sort('timestamp', 1).limit(5))
print(f'\nOldest 5 documents:')
for doc in oldest:
    ts = doc.get('timestamp', 'N/A')
    country = doc.get('country', 'Unknown')
    print(f'  {country}: {ts}')

# Check global_features collection
print('\n=== Global Features Collection ===')
global_count = db.global_features.count_documents({})
print(f'Total documents: {global_count}')

global_latest = list(db.global_features.find().sort('timestamp', -1).limit(3))
print(f'\nLatest 3 global features:')
for doc in global_latest:
    ts = doc.get('timestamp', 'N/A')
    print(f'  {ts}')

