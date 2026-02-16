# backend/observability.py

from datetime import datetime
from pymongo import MongoClient
import os

# ==========================================
# Mongo Connection
# ==========================================

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)

db = client["world_pulse_db"]
prediction_collection = db["prediction_logs"]

# ==========================================
# Log Prediction
# ==========================================

def log_prediction(model_version, features, prediction, probability):
    document = {
        "timestamp": datetime.utcnow(),
        "model_version": model_version,
        "features": features,
        "prediction": prediction,
        "probability": probability
    }

    prediction_collection.insert_one(document)
