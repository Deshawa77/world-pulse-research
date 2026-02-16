import sys
import os
import logging
from datetime import datetime

# ----------------------------
# Ensure project root is importable
# ----------------------------
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from pymongo import MongoClient, ASCENDING, DESCENDING
import joblib

from processing.ai_summary import generate_summary
from processing.global_risk import compute_global_risk
from feature_store.model_registry import get_production_model, list_models

# =====================================================
# Logging Configuration (File-based backup audit)
# =====================================================
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/predictions.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =====================================================
# FastAPI app
# =====================================================
app = FastAPI(title="World Pulse API")

# =====================================================
# MongoDB Connection
# =====================================================
client = MongoClient("mongodb://localhost:27017/")
db = client["world_pulse"]

# Prediction audit collection
prediction_collection = db["prediction_logs"]

# Create indexes for scalable queries (run once)
prediction_collection.create_index([("timestamp", DESCENDING)])
prediction_collection.create_index([("model_version", ASCENDING)])

# =====================================================
# Model Cache
# =====================================================
model_cache = {"model": None, "version": None}

# =====================================================
# Helpers
# =====================================================
def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB ObjectId to string for JSON serialization."""
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc

def load_production_model():
    """Load and cache the current production model."""
    model_path = get_production_model()
    if not model_path or not os.path.exists(model_path):
        return None, None

    models = list_models()
    for version, info in models.items():
        if info.get("stage") == "production":
            if model_cache["version"] != version:
                model_cache["model"] = joblib.load(model_path)
                model_cache["version"] = version
            return model_cache["model"], version
    return None, None

def log_prediction_to_mongo(model_version, features, prediction, probability):
    """Store prediction in Mongo audit collection."""
    prediction_collection.insert_one({
        "timestamp": datetime.utcnow(),
        "model_version": model_version,
        "features": features,
        "prediction": int(prediction),
        "probability": float(probability)
    })

# =====================================================
# Request Schema
# =====================================================
class PredictionRequest(BaseModel):
    features: list[float]

# =====================================================
# ROOT
# =====================================================
@app.get("/")
def root():
    return {"status": "ok", "message": "World Pulse backend running"}

# =====================================================
# DATA ENDPOINTS
# =====================================================
@app.get("/news")
def get_news():
    return [serialize_doc(d) for d in db.news.find().limit(10)]

@app.get("/gdelt")
def get_gdelt():
    return [serialize_doc(d) for d in db.gdelt.find().limit(10)]

@app.get("/wiki")
def get_wiki():
    return [serialize_doc(d) for d in db.wiki.find().limit(10)]

@app.get("/trends")
def get_trends():
    return [serialize_doc(d) for d in db.trends.find().limit(10)]

@app.get("/earthquakes")
def get_earthquakes():
    return [serialize_doc(d) for d in db.earthquakes.find().limit(10)]

@app.get("/weather")
def get_weather():
    return [serialize_doc(d) for d in db.weather.find().limit(10)]

@app.get("/crypto")
def get_crypto():
    return [serialize_doc(d) for d in db.crypto.find().limit(10)]

@app.get("/economics")
def get_economics():
    return [serialize_doc(d) for d in db.economics.find().limit(10)]

@app.get("/health_data")
def get_health_data():
    return [serialize_doc(d) for d in db.health.find().limit(10)]

@app.get("/stocks")
def get_stocks():
    return [serialize_doc(d) for d in db.stocks.find().limit(10)]

@app.get("/worldbank")
def get_worldbank():
    return [serialize_doc(d) for d in db.worldbank.find().limit(10)]

# =====================================================
# FEATURE STORE ENDPOINTS
# =====================================================
@app.get("/features/global/latest")
def get_latest_global(mode: str = Query("online")):
    doc = list(db.global_features.find({"mode": mode}).sort("timestamp", -1).limit(1))
    if not doc:
        raise HTTPException(status_code=404, detail="No global features found")
    return serialize_doc(doc[0])

@app.get("/features/global/{version}")
def get_global_by_version(version: int, mode: str = Query("online")):
    doc = db.global_features.find_one({"version": version, "mode": mode})
    if not doc:
        raise HTTPException(status_code=404, detail="No global features found")
    return serialize_doc(doc)

@app.get("/features/country/{country}/latest")
def get_latest_country(country: str, mode: str = Query("online")):
    doc = list(db.country_features.find({"country": country, "mode": mode}).sort("timestamp", -1).limit(1))
    if not doc:
        raise HTTPException(status_code=404, detail=f"No features found for country {country}")
    return serialize_doc(doc[0])

@app.get("/features/country/{country}")
def get_country_versions(country: str, limit: int = Query(10, ge=1), mode: str = Query("online")):
    cursor = list(db.country_features.find({"country": country, "mode": mode}).sort("timestamp", -1).limit(limit))
    if not cursor:
        raise HTTPException(status_code=404, detail=f"No features found for country {country}")
    return [serialize_doc(d) for d in cursor]

# =====================================================
# RISK + SUMMARY
# =====================================================
@app.get("/risk_score")
def risk_score():
    return {"risk_score": compute_global_risk()}

@app.get("/summary")
def summary():
    return {"summary": generate_summary()}

# =====================================================
# MODEL REGISTRY ENDPOINTS
# =====================================================
@app.get("/model_info")
def model_info():
    models = list_models()
    for version, info in models.items():
        if info.get("stage") == "production":
            return {
                "version": version,
                "metrics": info.get("metrics"),
                "registered_at": info.get("registered_at"),
                "promoted_at": info.get("promoted_at")
            }
    raise HTTPException(status_code=404, detail="No production model found")

# =====================================================
# PREDICT ENDPOINT
# =====================================================
@app.post("/predict")
def predict(request: PredictionRequest):
    model, version = load_production_model()
    if model is None:
        raise HTTPException(status_code=404, detail="No production model available")

    # Feature validation
    expected_features = model.n_features_in_
    if len(request.features) != expected_features:
        raise HTTPException(
            status_code=400,
            detail=f"Model expects {expected_features} features"
        )

    try:
        prediction = model.predict([request.features])[0]
        probabilities = model.predict_proba([request.features])[0]
        confidence = float(probabilities[1])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Prediction failed: {str(e)}")

    # Log to MongoDB
    log_prediction_to_mongo(version, request.features, prediction, confidence)

    # Backup log to file
    logging.info(
        f"version={version} | features={request.features} | "
        f"prediction={int(prediction)} | confidence={confidence}"
    )

    return {
        "model_version": version,
        "prediction": int(prediction),
        "probability": confidence
    }

# =====================================================
# PREDICTION LOGS ENDPOINT
# =====================================================
@app.get("/prediction_logs")
def get_prediction_logs(limit: int = Query(50, ge=1)):
    logs = list(prediction_collection.find().sort("timestamp", -1).limit(limit))
    return [serialize_doc(log) for log in logs]

# =====================================================
# SYSTEM HEALTH
# =====================================================
@app.get("/health")
def health():
    try:
        db.command("ping")
        model, _ = load_production_model()
        return {
            "status": "healthy",
            "database": "connected",
            "model_loaded": model is not None
        }
    except Exception:
        return {"status": "unhealthy"}
