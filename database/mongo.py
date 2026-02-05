from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["world_pulse"]

def insert_data(collection_name, data):
    collection = db[collection_name]
    collection.insert_many(data)
