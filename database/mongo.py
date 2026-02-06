from pymongo import MongoClient
from datetime import datetime

client = MongoClient("mongodb://localhost:27017/")
db = client["world_pulse"]

def insert(collection_name, data):
    if isinstance(data, list):
        for d in data:
            d["collected_at"] = datetime.utcnow()
        db[collection_name].insert_many(data)
    else:
        data["collected_at"] = datetime.utcnow()
        db[collection_name].insert_one(data)
