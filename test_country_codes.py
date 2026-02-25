#!/usr/bin/env python3
"""
Test to check country code formats in MongoDB vs what Plotly expects
"""

from pymongo import MongoClient, DESCENDING

client = MongoClient("mongodb://localhost:27017/")
db = client["world_pulse"]

# Get sample country documents
print("="*60)
print("Country Codes in MongoDB")
print("="*60)

pipeline = [
    {"$match": {"mode": "online"}},
    {"$group": {"_id": "$country", "doc": {"$first": "$$ROOT"}}},
    {"$limit": 10}
]

countries = list(db.country_features.aggregate(pipeline))

print(f"\nFound {len(countries)} unique countries:")
for c in countries:
    code = c["_id"]
    risk = c["doc"].get("features", {}).get("global_risk_score", "N/A")
    print(f"  - {code} (length: {len(code)}): risk={risk}")

print("\n" + "="*60)
print("Analysis")
print("="*60)

two_letter = [c for c in countries if len(c["_id"]) == 2]
three_letter = [c for c in countries if len(c["_id"]) == 3]

print(f"\n2-letter codes: {len(two_letter)}")
print(f"3-letter codes: {len(three_letter)}")

if two_letter:
    print(f"\n⚠️  WARNING: Found {len(two_letter)} countries with 2-letter codes!")
    print("Plotly choropleth with locationmode='ISO-3' expects 3-letter codes.")
    print("This will cause the map to NOT display these countries!")
    print("\nCountries affected:")
    for c in two_letter[:5]:
        print(f"  - {c['_id']}")

print("\n" + "="*60)
print("Solution Options")
print("="*60)
print("""
1. Change backend to store 3-letter ISO codes (e.g., 'GBR' instead of 'UK')
2. Change frontend to convert 2-letter to 3-letter codes
3. Change frontend to use locationmode='country names' with full names
4. Add a mapping in the API to convert codes before returning

Recommended: Option 1 - Store proper 3-letter ISO codes in MongoDB
""")
