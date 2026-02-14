from fastapi import FastAPI, HTTPException, Query
from pymongo import MongoClient
from processing.ai_summary import generate_summary
from processing.global_risk import compute_global_risk
from bson import ObjectId  # For JSON serialization

app = FastAPI(title="World Pulse API")

# ----------------------------
# MongoDB Connection
# ----------------------------
db = MongoClient("mongodb://localhost:27017/")["world_pulse"]

# ----------------------------
# Helper: Serialize MongoDB document
# ----------------------------
def serialize_doc(doc):
    """Convert MongoDB ObjectId to string for JSON serialization."""
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc

# ----------------------------
# Root Endpoint
# ----------------------------
@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "World Pulse backend running"
    }

# ----------------------------
# Existing Data Endpoints
# ----------------------------
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

@app.get("/health")
def get_health():
    return [serialize_doc(d) for d in db.health.find().limit(10)]

@app.get("/stocks")
def get_stocks():
    return [serialize_doc(d) for d in db.stocks.find().limit(10)]

@app.get("/worldbank")
def get_worldbank():
    return [serialize_doc(d) for d in db.worldbank.find().limit(10)]

@app.get("/risk_score")
def risk_score():
    score = compute_global_risk()
    return {"risk_score": score}

@app.get("/summary")
def summary():
    summary_text = generate_summary()
    return {"summary": summary_text}

# ----------------------------
# Feature Store Endpoints
# ----------------------------

# Global Features
@app.get("/features/global/latest")
def get_latest_global(mode: str = Query("online", description="Mode: online or offline")):
    doc = db.global_features.find({"mode": mode}).sort("timestamp", -1).limit(1)
    docs = list(doc)
    if not docs:
        raise HTTPException(status_code=404, detail="No global features found")
    return serialize_doc(docs[0])

@app.get("/features/global/{version}")
def get_global_by_version(version: int, mode: str = Query("online")):
    doc = db.global_features.find_one({"version": version, "mode": mode})
    if not doc:
        raise HTTPException(status_code=404, detail=f"No global features found for version {version}")
    return serialize_doc(doc)

# Country Features
@app.get("/features/country/{country}/latest")
def get_latest_country(country: str, mode: str = Query("online")):
    doc = db.country_features.find({"country": country, "mode": mode}).sort("timestamp", -1).limit(1)
    docs = list(doc)
    if not docs:
        raise HTTPException(status_code=404, detail=f"No features found for country {country}")
    return serialize_doc(docs[0])

@app.get("/features/country/{country}")
def get_country_versions(country: str, limit: int = Query(10, ge=1), mode: str = Query("online")):
    cursor = db.country_features.find({"country": country, "mode": mode}).sort("timestamp", -1).limit(limit)
    docs = list(cursor)
    if not docs:
        raise HTTPException(status_code=404, detail=f"No features found for country {country}")
    return [serialize_doc(d) for d in docs]

# ----------------------------
# ✅ Monitoring / Health Endpoint
# ----------------------------
@app.get("/health")
def health():
    """
    Health check for MongoDB connectivity.
    Returns "healthy" if the database responds to ping.
    """
    try:
        db.command("ping")
        return {"status": "healthy"}
    except Exception:
        return {"status": "unhealthy"}
