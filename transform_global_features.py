# transform_global_features.py
from pymongo import MongoClient
from datetime import datetime

# ---------------------------
# CONFIG
# ---------------------------
MONGO_URI = "mongodb://localhost:27017/"  # Change if needed
DB_NAME = "world_pulse"                   # <-- Replace with your actual DB name
FEATURE_COLUMNS = [
    "news_sentiment",
    "gdelt_sentiment",
    "crypto_return",
    "crypto_volatility",
    "stock_return",
    "stock_volatility",
    "weather_anomaly"
]

INITIAL_GLOBAL_FEATURES = {
    "news_sentiment": 0.12,
    "gdelt_sentiment": -0.05,
    "crypto_return": 0.03,
    "crypto_volatility": 0.1,
    "stock_return": -0.02,
    "stock_volatility": 0.08,
    "weather_anomaly": 0.15
}

# ---------------------------
# CONNECT TO MONGO
# ---------------------------
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db.global_features

# ---------------------------
# TRANSFORM OLD DOCUMENTS
# ---------------------------
for doc in collection.find():
    if "features" not in doc:
        features = {}
        for col in FEATURE_COLUMNS:
            features[col] = doc.get(col, 0.0)
            if col in doc:
                del doc[col]

        doc["features"] = features
        if "mode" not in doc:
            doc["mode"] = "online"
        if "timestamp" not in doc:
            doc["timestamp"] = datetime.utcnow()

        collection.replace_one({"_id": doc["_id"]}, doc)

print("✅ All existing global_features documents transformed successfully!")

# ---------------------------
# INSERT INITIAL DOCUMENT IF EMPTY
# ---------------------------
if collection.count_documents({}) == 0:
    initial_doc = {
        "features": INITIAL_GLOBAL_FEATURES,
        "mode": "online",
        "version": 1,
        "timestamp": datetime.utcnow()
    }
    collection.insert_one(initial_doc)
    print("✅ Initial global_features document inserted!")

print("🎉 Mongo transformation complete.")
