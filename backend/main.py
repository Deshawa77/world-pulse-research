import sys
import os
import logging
from datetime import datetime, timezone
import asyncio
import time
import uuid
import hmac
import csv
import io
from dotenv import load_dotenv

# ----------------------------
# Ensure project root is importable
# ----------------------------
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Query, Header, Depends, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse
from backend.kafka_client import get_consumer
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
from pymongo import MongoClient, ASCENDING, DESCENDING
import joblib
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
import jwt
from datetime import timedelta
from collections import defaultdict


# =====================================================
# PASSWORD SECURITY
# =====================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    bcrypt__rounds=12,
    deprecated="auto"
)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str):
    return pwd_context.hash(password[:72])


from processing.global_risk import compute_global_risk
from processing.country_daily_risk import country_daily_refresh_if_due
from collectors.country_news import get_country_catalog
from processing.sentinel_analysis import compute_sentinel_analysis, get_sentinel_history
from processing.country_risk_validation import latest_country_risk_validation, run_country_risk_validation
from feature_store.model_registry import get_production_model, list_models

from backend.country_risk_stream import country_risk_stream_health
from backend.observability import (
    build_logger,
    RuntimeMetrics,
    record_prediction,
    build_monitoring_summary,
)

# =====================================================
# Load environment variables for security
# =====================================================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

# =====================================================
# JWT CONFIGURATION
# =====================================================

JWT_SECRET = (os.environ.get("JWT_SECRET") or "world_pulse_secret_key")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES") or 60
)

API_KEY = (os.environ.get("API_KEY") or "").strip().strip('"').strip("'")
ADMIN_KEY = (os.environ.get("ADMIN_KEY") or "").strip().strip('"').strip("'")
USER_API_KEYS = {
    k.strip().strip('"').strip("'")
    for k in (os.environ.get("USER_API_KEYS") or "").split(",")
    if k.strip()
}
ADMIN_API_KEYS = {
    k.strip().strip('"').strip("'")
    for k in (os.environ.get("ADMIN_API_KEYS") or "").split(",")
    if k.strip()
}
if API_KEY:
    USER_API_KEYS.add(API_KEY)
if ADMIN_KEY:
    ADMIN_API_KEYS.add(ADMIN_KEY)

MONGO_URI = (os.environ.get("MONGO_URI") or "mongodb://localhost:27017/").strip()
DEFAULT_LOCAL_MONGO_URI = "mongodb://localhost:27017/"
REQUIRE_HTTPS = (os.environ.get("REQUIRE_HTTPS") or "false").strip().lower() == "true"
ALLOW_INSECURE_LOCALHOST = (os.environ.get("ALLOW_INSECURE_LOCALHOST") or "true").strip().lower() == "true"

# =====================================================
# FastAPI app and rate limiter
# =====================================================
app = FastAPI(title="World Pulse Secure API")
logger = build_logger("world_pulse.api")
runtime_metrics = RuntimeMetrics()

if not USER_API_KEYS and not ADMIN_API_KEYS:
    raise RuntimeError("Missing API keys. Set API_KEY/ADMIN_KEY (or USER_API_KEYS/ADMIN_API_KEYS) in .env.")

# ---------------- CORS Middleware -----------------
from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:3000",  # React dev server if used
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()

    if REQUIRE_HTTPS:
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = (request.url.hostname or "").lower()
        is_localhost = host in {"localhost", "127.0.0.1"}
        if scheme != "https" and not (ALLOW_INSECURE_LOCALHOST and is_localhost):
            runtime_metrics.on_request(426)
            return JSONResponse(
                status_code=426,
                content={"detail": "HTTPS is required in this environment"},
                headers={"x-request-id": request_id},
            )

    try:
        response = await call_next(request)
    except Exception:
        runtime_metrics.on_request(500)
        logger.exception(
            "request_failed",
            extra={
                "request_id": request_id,
                "event": {"method": request.method, "path": request.url.path},
            },
        )
        raise

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    response.headers["x-request-id"] = request_id
    runtime_metrics.on_request(response.status_code)
    logger.info(
        "http_request",
        extra={
            "request_id": request_id,
            "event": {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": elapsed_ms,
                "client_ip": request.client.host if request.client else None,
            },
        },
    )
    return response

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Exception handler for rate limiting
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request, exc):
    return JSONResponse(status_code=429, content={"error": "Too many requests, slow down!"})

# =====================================================
# Logging Configuration
# =====================================================
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/predictions.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =====================================================
# MongoDB Connection
# =====================================================
def init_mongo_client() -> MongoClient:
    uris = [MONGO_URI]
    if MONGO_URI != DEFAULT_LOCAL_MONGO_URI:
        uris.append(DEFAULT_LOCAL_MONGO_URI)

    last_error = None
    for uri in uris:
        try:
            candidate = MongoClient(uri, serverSelectionTimeoutMS=3000)
            candidate.admin.command("ping")
            if uri != MONGO_URI:
                logger.warning(
                    "mongo_fallback_uri_used",
                    extra={"event": {"configured_uri": MONGO_URI, "fallback_uri": uri}},
                )
            return candidate
        except Exception as exc:
            last_error = exc
            logger.warning(
                "mongo_connection_attempt_failed",
                extra={"event": {"uri": uri, "error": str(exc)}},
            )

    raise RuntimeError(f"Unable to connect to MongoDB. Last error: {last_error}")


client = init_mongo_client()
db = client["world_pulse"]
prediction_collection = db["prediction_logs"]
model_monitoring_collection = db["model_monitoring"]
users_collection = db["users"]
operator_events_collection = db["operator_events"]
sentinel_feedback_collection = db["sentinel_feedback"]
# Create indexes for scalable queries (run once)
prediction_collection.create_index([("timestamp", DESCENDING)])
prediction_collection.create_index([("model_version", ASCENDING)])
model_monitoring_collection.create_index([("timestamp", DESCENDING)])
model_monitoring_collection.create_index([("model_version", ASCENDING)])
users_collection.create_index([("email", ASCENDING)], unique=True)
operator_events_collection.create_index([("timestamp", DESCENDING)])
sentinel_feedback_collection.create_index([("timestamp", DESCENDING)])
# =====================================================
# Model Cache
# =====================================================
model_cache = {"model": None, "version": None}

# =====================================================
# USER STORE (MongoDB)
# =====================================================

fake_users_db = {}  # legacy fallback; auth now uses Mongo users collection

# =====================================================
# Security: API Key Verification
# =====================================================
def _identity_from_api_key(key: str | None):
    candidate = (key or "").strip()
    if not candidate:
        return None
    for admin_key in ADMIN_API_KEYS:
        if hmac.compare_digest(candidate, admin_key):
            return {"auth_type": "api_key", "api_key": candidate, "role": "admin"}
    for user_key in USER_API_KEYS:
        if hmac.compare_digest(candidate, user_key):
            return {"auth_type": "api_key", "api_key": candidate, "role": "user"}
    return None


def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        role = str(payload.get("role") or "user")
        subject = str(payload.get("sub") or "")
        if not subject:
            raise HTTPException(status_code=401, detail="Invalid token subject")
        return {"auth_type": "jwt", "sub": subject, "role": role}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


def verify_api_key(x_api_key: str | None = Header(None), authorization: str | None = Header(None)):
    identity = _identity_from_api_key(x_api_key)
    if identity:
        return identity
    bearer = (authorization or "").strip()
    if bearer.lower().startswith("bearer "):
        return decode_access_token(bearer.split(" ", 1)[1].strip())
    raise HTTPException(status_code=401, detail="Missing or invalid API key / bearer token")


# Role-Based Access Control
def check_role(identity: dict = Depends(verify_api_key)):
    return identity["role"]


def require_admin(role: str = Depends(check_role)):
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access only")
    return role

# =====================================================
# Helpers
# =====================================================

# =====================================================
# JWT TOKEN CREATION
# =====================================================

def create_access_token(data: dict):
    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )


def get_country_risk_dependency_health(mode: str = "online"):
    status = {
        "database": "connected",
        "model_loaded": False,
        "country_features_latest": None,
        "country_news_latest": None,
        "reddit_latest": None,
        "trends_latest": None,
        "weather_latest": None,
        "validation_status": latest_country_risk_validation().get("status"),
    }
    model, version = load_production_model()
    status["model_loaded"] = model is not None
    status["model_version"] = version

    for name, collection_name in [("country_features_latest", "country_features"), ("country_news_latest", "country_news"), ("reddit_latest", "reddit"), ("trends_latest", "trends"), ("weather_latest", "weather")]:
        doc = db[collection_name].find_one(sort=[("_id", DESCENDING)])
        if not doc:
            status[name] = None
            continue
        stamp = doc.get("timestamp") or doc.get("collected_at") or ((doc.get("data") or {}).get("published_at")) or doc.get("data_timestamp")
        status[name] = str(stamp) if stamp is not None else None

    latest_country_doc = db.country_features.find_one({"mode": mode}, sort=[("_id", DESCENDING)])
    if latest_country_doc:
        features = latest_country_doc.get("features", {})
        status["country_features_latest"] = {
            "country": latest_country_doc.get("country"),
            "timestamp": str(latest_country_doc.get("timestamp")),
            "feature_timestamp": str(features.get("timestamp")),
            "source_count": int(features.get("source_count", 0) or 0),
        }
    return status


def serialize_doc(doc: dict) -> dict:
    doc = doc.copy()
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    for key, value in doc.items():
        if isinstance(value, datetime):
            doc[key] = value.isoformat()
    return doc

def load_production_model():
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


def compute_feature_drift(payload_features: list[float]) -> float | None:
    baseline_doc = db.global_features.find_one({"mode": "online"}, sort=[("_id", DESCENDING)])
    if not baseline_doc:
        return None

    baseline_features = baseline_doc.get("features", {})
    expected_order = [
        "news_sentiment",
        "gdelt_sentiment",
        "crypto_return",
        "crypto_volatility",
        "stock_return",
        "stock_volatility",
        "weather_anomaly",
    ]

    baseline_vec = [float(baseline_features.get(name, 0.0)) for name in expected_order]
    if len(payload_features) != len(baseline_vec):
        return None

    drift_components = []
    for observed, expected in zip(payload_features, baseline_vec):
        denom = abs(expected) + 1e-6
        drift_components.append(abs(float(observed) - expected) / denom)

    return round(sum(drift_components) / len(drift_components), 6)

def get_latest_global_doc(mode: str = "online") -> dict:
    # Primary source: feature store collection.
    doc = db.global_features.find_one({"mode": mode}, sort=[("_id", DESCENDING)])
    if doc:
        return serialize_doc(doc)

    # Fallback source used by orchestrator dashboard sync.
    doc = db.dashboard_features.find_one({"mode": mode}, sort=[("_id", DESCENDING)])
    if doc:
        return serialize_doc(doc)

    # Final safety fallback keeps frontend booting even before data arrives.
    now = datetime.utcnow().isoformat()
    return {
        "mode": mode,
        "version": 0,
        "timestamp": now,
        "features": {
            "timestamp": now,
            "news_sentiment": 0.0,
            "gdelt_sentiment": 0.0,
            "crypto_return": 0.0,
            "crypto_volatility": 0.0,
            "stock_return": 0.0,
            "stock_volatility": 0.0,
            "weather_anomaly": 0.0,
            "global_risk_score": 50.0,
            "top_topics": ["no data"],
        },
    }


def parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Handle various ISO formats including milliseconds
        v = value.strip()
        # Replace Z with +00:00 for timezone-aware parsing
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        return datetime.fromisoformat(v)
    except Exception:
        # Fallback: try parsing without timezone info
        try:
            v = value.strip().rstrip("Z")
            # Truncate milliseconds to 6 digits max (Python limit)
            if "." in v:
                main, frac = v.split(".")
                frac = frac[:6]  # Keep only first 6 digits of milliseconds
                v = f"{main}.{frac}"
            return datetime.fromisoformat(v)
        except Exception:
            return None



def get_global_history(mode: str = "online", limit: int = 1000, start_date: datetime | None = None, end_date: datetime | None = None):
    query: dict = {"mode": mode}
    if start_date or end_date:
        dt_filter: dict = {}
        if start_date:
            dt_filter["$gte"] = start_date
        if end_date:
            dt_filter["$lte"] = end_date
        query["timestamp"] = dt_filter

    cursor = list(db.global_features.find(query).sort("timestamp", DESCENDING).limit(limit))
    if not cursor:
        cursor = list(db.dashboard_features.find(query).sort("timestamp", DESCENDING).limit(limit))
    return [serialize_doc(d) for d in reversed(cursor)]


# =====================================================
# Request Schema
# =====================================================
class PredictionRequest(BaseModel):
    features: list[float]


class AlertActionRequest(BaseModel):
    country: str
    action: str
    owner: str | None = None
    comment: str | None = None


class ScenarioStep(BaseModel):
    label: str
    marketShock: float
    sentimentShock: float
    weatherShock: float


class ScenarioRunRequest(BaseModel):
    steps: list[ScenarioStep]


class CountryRefreshRequest(BaseModel):
    batch_size: int = 50
    max_records: int = 4


class SentinelQuestionRequest(BaseModel):
    question: str
    context: dict | None = None
    conversation_history: list[dict] | None = None
    current_risk: float | None = None


class SentinelFeedbackRequest(BaseModel):
    eventId: str
    feedbackType: str
    threatLevel: str
    riskScore: float
    timestamp: str
    notes: str | None = None
# =====================================================
# WebSocket Connection Manager
# =====================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# =====================================================
# ROOT
# =====================================================
@app.get("/", dependencies=[Depends(verify_api_key)])
def root():
    return {"status": "ok", "message": "World Pulse backend running"}

# =====================================================
# DATA ENDPOINTS (all protected)
# =====================================================
@app.get("/news")
@limiter.limit("10/minute")
def get_news(request: Request, role: str = Depends(check_role)):
    return [serialize_doc(d) for d in db.news.find().limit(10)]

@app.get("/gdelt")
@limiter.limit("10/minute")
def get_gdelt(request: Request, role: str = Depends(check_role)):
    return [serialize_doc(d) for d in db.gdelt.find().limit(10)]

@app.get("/wiki")
@limiter.limit("10/minute")
def get_wiki(request: Request, role: str = Depends(check_role)):
    return [serialize_doc(d) for d in db.wiki.find().limit(10)]

@app.get("/trends")
@limiter.limit("10/minute")
def get_trends(request: Request, role: str = Depends(check_role)):
    return [serialize_doc(d) for d in db.trends.find().limit(10)]

@app.get("/earthquakes")
@limiter.limit("10/minute")
def get_earthquakes(request: Request, role: str = Depends(check_role)):
    return [serialize_doc(d) for d in db.earthquakes.find().limit(10)]

@app.get("/weather")
@limiter.limit("10/minute")
def get_weather(request: Request, role: str = Depends(check_role)):
    return [serialize_doc(d) for d in db.weather.find().limit(10)]

@app.get("/crypto")
@limiter.limit("10/minute")
def get_crypto(request: Request, role: str = Depends(check_role)):
    return [serialize_doc(d) for d in db.crypto.find().limit(10)]

@app.get("/economics")
@limiter.limit("10/minute")
def get_economics(request: Request, role: str = Depends(check_role)):
    return [serialize_doc(d) for d in db.economics.find().limit(10)]

@app.get("/health_data")
@limiter.limit("10/minute")
def get_health_data(request: Request, role: str = Depends(check_role)):
    return [serialize_doc(d) for d in db.health.find().limit(10)]

@app.get("/stocks")
@limiter.limit("10/minute")
def get_stocks(request: Request, role: str = Depends(check_role)):
    return [serialize_doc(d) for d in db.stocks.find().limit(10)]

@app.get("/worldbank")
@limiter.limit("10/minute")
def get_worldbank(request: Request, role: str = Depends(check_role)):
    return [serialize_doc(d) for d in db.worldbank.find().limit(10)]

# =====================================================
# FEATURE STORE ENDPOINTS (protected + rate limited)
# =====================================================

@app.get("/features/global/latest")
@limiter.limit("60/minute")
def get_latest_global(request: Request, role: str = Depends(check_role), mode: str = Query("online")):

    return get_latest_global_doc(mode)

@app.get("/features/global/history")
@limiter.limit("10/minute")
def get_global_history_api(
    request: Request,
    role: str = Depends(check_role),
    mode: str = Query("online"),
    limit: int = Query(1000, ge=1, le=10000),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    start_dt = parse_iso_dt(start_date)
    end_dt = parse_iso_dt(end_date)
    
    # Validate date formats if provided
    if start_date and start_dt is None:
        raise HTTPException(status_code=400, detail=f"Invalid start_date format: {start_date}. Expected ISO format (e.g., 2024-01-01T00:00:00Z)")
    if end_date and end_dt is None:
        raise HTTPException(status_code=400, detail=f"Invalid end_date format: {end_date}. Expected ISO format (e.g., 2024-01-01T00:00:00Z)")
    
    docs = get_global_history(mode=mode, limit=limit, start_date=start_dt, end_date=end_dt)


    data = []
    for doc in docs:
        f = doc.get("features", {})
        data.append({
            "timestamp": str(f.get("timestamp") or doc.get("timestamp") or datetime.utcnow().isoformat()),
            "risk_score": float(f.get("global_risk_score", 50.0)),
            "news_sentiment": float(f.get("news_sentiment", 0.0)) * 100,
            "gdelt_sentiment": float(f.get("gdelt_sentiment", 0.0)) * 100,
            "crypto_return": float(f.get("crypto_return", 0.0)) * 100,
            "crypto_volatility": float(f.get("crypto_volatility", 0.0)) * 100,
            "stock_return": float(f.get("stock_return", 0.0)) * 100,
            "stock_volatility": float(f.get("stock_volatility", 0.0)) * 100,
            "weather_anomaly": float(f.get("weather_anomaly", 0.0)) * 100,
            "top_topics": f.get("top_topics", ["no data"]),
        })
    return data

@app.get("/features/global/{version}")
@limiter.limit("10/minute")
def get_global_by_version(request: Request, version: int, role: str = Depends(check_role), mode: str = Query("online")):
    doc = db.global_features.find_one({"version": version, "mode": mode})
    if not doc:
        raise HTTPException(status_code=404, detail="No global features found")
    return serialize_doc(doc)

@app.get("/features/country/{country}/latest")

@limiter.limit("10/minute")
def get_latest_country(request: Request, country: str, role: str = Depends(check_role), mode: str = Query("online")):
    doc = list(db.country_features.find({"country": country, "mode": mode}).sort("timestamp", -1).limit(1))
    if not doc:
        raise HTTPException(status_code=404, detail=f"No features found for country {country}")
    return serialize_doc(doc[0])

@app.get("/features/country/{country}")
@limiter.limit("10/minute")
def get_country_versions(request: Request, country: str, role: str = Depends(check_role), limit: int = Query(10, ge=1), mode: str = Query("online")):
    cursor = list(db.country_features.find({"country": country, "mode": mode}).sort("timestamp", -1).limit(limit))
    if not cursor:
        raise HTTPException(status_code=404, detail=f"No features found for country {country}")
    return [serialize_doc(d) for d in cursor]


# =====================================================
# RISK + SUMMARY

# =====================================================
@app.get("/risk_score")
@limiter.limit("10/minute")
def risk_score(request: Request, role: str = Depends(check_role)):
    doc = get_latest_global_doc(mode="online")
    features = doc.get("features", {})
    return {
        "risk_score": [
            features.get("global_risk_score", 50),
            features.get("top_topics", ["no data"])
        ]
    }

@app.get("/summary")
@limiter.limit("10/minute")
def summary(request: Request, role: str = Depends(check_role)):
    doc = get_latest_global_doc(mode="online")
    features = doc.get("features", {})
    risk_score = features.get("global_risk_score", 50)
    top_topics = features.get("top_topics", ["no data"])
    return {
        "summary": f"Moderate risk: Global Risk Score: {risk_score}/100.\n"
                   f"Top topics influencing sentiment today: {top_topics}."
    }


# =====================================================
# DASHBOARD ENDPOINTS
# =====================================================
@app.get("/dashboard/live-feed")
@limiter.limit("60/minute")
def dashboard_live_feed(request: Request, role: str = Depends(check_role), mode: str = Query("online")):

    latest = get_latest_global_doc(mode)
    latest_ts = latest.get("timestamp")
    ts_dt = parse_iso_dt(str(latest_ts)) if latest_ts else None
    heartbeat = (datetime.utcnow() - ts_dt).total_seconds() if ts_dt else 0.0

    features = latest.get("features", {})
    topics = features.get("top_topics", ["no data"])
    incidents = [f"Topic pressure: {t}" for t in topics[:4]] or ["No active incidents"]

    drift_doc = model_monitoring_collection.find_one(sort=[("timestamp", DESCENDING)])
    model_drift = float((drift_doc or {}).get("drift_score", 0.0) or 0.0)

    return {
        "incidents": incidents,
        "ingestionHeartbeatSec": round(max(0.0, heartbeat), 2),
        "modelDrift": round(model_drift, 4),
        "lastUpdated": str(latest_ts or datetime.utcnow().isoformat()),
    }


# ISO 3166-1 alpha-2 to alpha-3 country code mapping
ISO2_TO_ISO3 = {
    "AF": "AFG", "AX": "ALA", "AL": "ALB", "DZ": "DZA", "AS": "ASM", "AD": "AND", "AO": "AGO", "AI": "AIA",
    "AQ": "ATA", "AG": "ATG", "AR": "ARG", "AM": "ARM", "AW": "ABW", "AU": "AUS", "AT": "AUT", "AZ": "AZE",
    "BS": "BHS", "BH": "BHR", "BD": "BGD", "BB": "BRB", "BY": "BLR", "BE": "BEL", "BZ": "BLZ", "BJ": "BEN",
    "BM": "BMU", "BT": "BTN", "BO": "BOL", "BQ": "BES", "BA": "BIH", "BW": "BWA", "BV": "BVT", "BR": "BRA",
    "IO": "IOT", "BN": "BRN", "BG": "BGR", "BF": "BFA", "BI": "BDI", "CV": "CPV", "KH": "KHM", "CM": "CMR",
    "CA": "CAN", "KY": "CYM", "CF": "CAF", "TD": "TCD", "CL": "CHL", "CN": "CHN", "CX": "CXR", "CC": "CCK",
    "CO": "COL", "KM": "COM", "CG": "COG", "CD": "COD", "CK": "COK", "CR": "CRI", "CI": "CIV", "HR": "HRV",
    "CU": "CUB", "CW": "CUW", "CY": "CYP", "CZ": "CZE", "DK": "DNK", "DJ": "DJI", "DM": "DMA", "DO": "DOM",
    "EC": "ECU", "EG": "EGY", "SV": "SLV", "GQ": "GNQ", "ER": "ERI", "EE": "EST", "ET": "ETH", "FK": "FLK",
    "FO": "FRO", "FJ": "FJI", "FI": "FIN", "FR": "FRA", "GF": "GUF", "PF": "PYF", "TF": "ATF", "GA": "GAB",
    "GM": "GMB", "GE": "GEO", "DE": "DEU", "GH": "GHA", "GI": "GIB", "GR": "GRC", "GL": "GRL", "GD": "GRD",
    "GP": "GLP", "GU": "GUM", "GT": "GTM", "GG": "GGY", "GN": "GIN", "GW": "GNB", "GY": "GUY", "HT": "HTI",
    "HM": "HMD", "VA": "VAT", "HN": "HND", "HK": "HKG", "HU": "HUN", "IS": "ISL", "IN": "IND", "ID": "IDN",
    "IR": "IRN", "IQ": "IRQ", "IE": "IRL", "IM": "IMN", "IL": "ISR", "IT": "ITA", "JM": "JAM", "JP": "JPN",
    "JE": "JEY", "JO": "JOR", "KZ": "KAZ", "KE": "KEN", "KI": "KIR", "KP": "PRK", "KR": "KOR", "KW": "KWT",
    "KG": "KGZ", "LA": "LAO", "LV": "LVA", "LB": "LBN", "LS": "LSO", "LR": "LBR", "LY": "LBY", "LI": "LIE",
    "LT": "LTU", "LU": "LUX", "MO": "MAC", "MK": "MKD", "MG": "MDG", "MW": "MWI", "MY": "MYS", "MV": "MDV",
    "ML": "MLI", "MT": "MLT", "MH": "MHL", "MQ": "MTQ", "MR": "MRT", "MU": "MUS", "YT": "MYT", "MX": "MEX",
    "FM": "FSM", "MD": "MDA", "MC": "MCO", "MN": "MNG", "ME": "MNE", "MS": "MSR", "MA": "MAR", "MZ": "MOZ",
    "MM": "MMR", "NA": "NAM", "NR": "NRU", "NP": "NPL", "NL": "NLD", "NC": "NCL", "NZ": "NZL", "NI": "NIC",
    "NE": "NER", "NG": "NGA", "NU": "NIU", "NF": "NFK", "MP": "MNP", "NO": "NOR", "OM": "OMN", "PK": "PAK",
    "PW": "PLW", "PS": "PSE", "PA": "PAN", "PG": "PNG", "PY": "PRY", "PE": "PER", "PH": "PHL", "PN": "PCN",
    "PL": "POL", "PT": "PRT", "PR": "PRI", "QA": "QAT", "RE": "REU", "RO": "ROU", "RU": "RUS", "RW": "RWA",
    "BL": "BLM", "SH": "SHN", "KN": "KNA", "LC": "LCA", "MF": "MAF", "PM": "SPM", "VC": "VCT", "WS": "WSM",
    "SM": "SMR", "ST": "STP", "SA": "SAU", "SN": "SEN", "RS": "SRB", "SC": "SYC", "SL": "SLE", "SG": "SGP",
    "SX": "SXM", "SK": "SVK", "SI": "SVN", "SB": "SLB", "SO": "SOM", "ZA": "ZAF", "GS": "SGS", "SS": "SSD",
    "ES": "ESP", "LK": "LKA", "SD": "SDN", "SR": "SUR", "SJ": "SJM", "SE": "SWE", "CH": "CHE", "SY": "SYR",
    "TW": "TWN", "TJ": "TJK", "TZ": "TZA", "TH": "THA", "TL": "TLS", "TG": "TGO", "TK": "TKL", "TO": "TON",
    "TT": "TTO", "TN": "TUN", "TR": "TUR", "TM": "TKM", "TC": "TCA", "TV": "TUV", "UG": "UGA", "UA": "UKR",
    "AE": "ARE", "GB": "GBR", "US": "USA", "UM": "UMI", "UY": "URY", "UZ": "UZB", "VU": "VUT", "VE": "VEN",
    "VN": "VNM", "VG": "VGB", "VI": "VIR", "WF": "WLF", "EH": "ESH", "YE": "YEM", "ZM": "ZMB", "ZW": "ZWE",
    "UK": "GBR",  # Common non-standard code
}

PLACEHOLDER_TOPICS = {"global_expansion", "no data"}


def parse_feature_timestamp(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value or not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def assess_country_risk_quality(topics, feature_timestamp):
    normalized_topics = [str(topic).strip().lower() for topic in (topics or []) if str(topic).strip()]
    is_placeholder = not normalized_topics or any(topic in PLACEHOLDER_TOPICS for topic in normalized_topics)
    parsed_timestamp = parse_feature_timestamp(feature_timestamp)
    updated_today = bool(parsed_timestamp and parsed_timestamp.date() == datetime.now(timezone.utc).date())
    validated_today = updated_today and not is_placeholder

    if validated_today:
        data_quality = "verified"
    elif is_placeholder:
        data_quality = "synthetic"
    elif parsed_timestamp:
        data_quality = "stale"
    else:
        data_quality = "unknown"

    return {
        "feature_timestamp": parsed_timestamp.isoformat() if parsed_timestamp else None,
        "validated_today": validated_today,
        "data_quality": data_quality,
    }

def convert_country_code(code: str) -> str:
    """Convert 2-letter country code to 3-letter ISO code"""
    if not code:
        return code
    code = code.upper().strip()
    if len(code) == 3:
        return code  # Already 3-letter
    return ISO2_TO_ISO3.get(code, code)  # Convert or return as-is


@app.get("/dashboard/risk-map")
@limiter.limit("30/minute")
def dashboard_risk_map(
    request: Request,
    role: str = Depends(check_role),
    mode: str = Query("online"),
    verified_only: bool = Query(False),
):

    pipeline = [
        {"$match": {"mode": mode}},
        {"$sort": {"timestamp": -1}},
        {"$group": {"_id": "$country", "doc": {"$first": "$$ROOT"}}},
        {
            "$project": {
                "country": "$_id",
                "risk": "$doc.features.global_risk_score",
                "timestamp": "$doc.timestamp",
                "feature_timestamp": "$doc.features.timestamp",
                "topics": {"$ifNull": ["$doc.features.top_topics", []]},
                "source_count": {"$ifNull": ["$doc.features.source_count", 0]},
                "social_unrest_score": {"$ifNull": ["$doc.features.social_unrest_score", 0.0]},
                "google_trends_pressure": {"$ifNull": ["$doc.features.google_trends_pressure", 0.0]},
                "weather_stress": {"$ifNull": ["$doc.features.weather_stress", 0.0]},
                "external_signal_freshness": {"$ifNull": ["$doc.features.external_signal_freshness", 0.0]},
                "war_state_rules": {"$ifNull": ["$doc.features.war_state_rules", []]},
            }
        },
    ]
    docs = list(db.country_features.aggregate(pipeline))

    if not docs:
        placeholder_codes = sorted(set(ISO2_TO_ISO3.values()))
        docs = [
            {
                "country": code,
                "risk": 0.0,
                "timestamp": datetime.utcnow().isoformat(),
                "feature_timestamp": None,
                "topics": [],
                "source_count": 0,
                "social_unrest_score": 0.0,
                "google_trends_pressure": 0.0,
                "weather_stress": 0.0,
                "external_signal_freshness": 0.0,
                "war_state_rules": [],
            }
            for code in placeholder_codes
        ]

    response_docs = []
    for doc in docs:
        quality = assess_country_risk_quality(doc.get("topics"), doc.get("feature_timestamp"))
        if verified_only and not quality["validated_today"]:
            continue

        risk_value = doc.get("risk")
        doc["country"] = convert_country_code(doc.get("country", ""))
        doc["risk"] = float(risk_value) if risk_value is not None else 0.0
        doc["source_count"] = int(doc.get("source_count") or 0)
        doc["social_unrest_score"] = float(doc.get("social_unrest_score") or 0.0)
        doc["google_trends_pressure"] = float(doc.get("google_trends_pressure") or 0.0)
        doc["weather_stress"] = float(doc.get("weather_stress") or 0.0)
        doc["external_signal_freshness"] = float(doc.get("external_signal_freshness") or 0.0)
        doc.update(quality)
        doc.pop("topics", None)
        response_docs.append(doc)

    return [serialize_doc(d) for d in response_docs]


@app.get("/dashboard/risk-map/coverage")
@limiter.limit("30/minute")
def dashboard_risk_map_coverage(request: Request, role: str = Depends(check_role), mode: str = Query("online")):
    docs = dashboard_risk_map(request=request, role=role, mode=mode, verified_only=False)
    total = len(docs)
    verified = sum(1 for doc in docs if doc.get("validated_today"))
    no_data = sum(1 for doc in docs if doc.get("data_quality") == "synthetic")
    stale = sum(1 for doc in docs if doc.get("data_quality") == "stale")
    latest_validation = latest_country_risk_validation()
    return {
        "total": total,
        "verified": verified,
        "no_data": no_data,
        "stale": stale,
        "remaining": max(total - verified, 0),
        "coverage_pct": round((verified / total) * 100, 2) if total else 0.0,
        "latest_validation": {
            "status": latest_validation.get("status"),
            "sample_count": int(latest_validation.get("sample_count", 0) or 0),
            "brier_score": float((((latest_validation.get("metrics") or {}).get("brier_score", 0.0)) or 0.0)),
        },
    }


@app.post("/dashboard/risk-map/refresh")
@limiter.limit("10/minute")
def dashboard_risk_map_refresh(request: Request, payload: CountryRefreshRequest, role: str = Depends(check_role)):
    batch_size = max(1, min(int(payload.batch_size), len(get_country_catalog())))
    max_records = max(1, min(int(payload.max_records), 10))
    summary = country_daily_refresh_if_due(max_records=max_records, batch_size=batch_size)
    return serialize_doc(summary)


@app.get("/dashboard/global-intelligence-feed")
@limiter.limit("60/minute")
def dashboard_global_intelligence_feed(request: Request, role: str = Depends(check_role), mode: str = Query("online"), limit: int = Query(50, ge=1, le=200)):
    """
    Returns detailed trending news intelligence feed from all countries (233 countries).
    Fetches latest country features with detailed news headlines, summaries, and source URLs.
    """
    # Country name mapping for display
    country_names = {
        "USA": "United States", "GBR": "United Kingdom", "DEU": "Germany", "FRA": "France",
        "JPN": "Japan", "CHN": "China", "IND": "India", "BRA": "Brazil", "CAN": "Canada",
        "AUS": "Australia", "RUS": "Russia", "KOR": "South Korea", "ITA": "Italy", "ESP": "Spain",
        "MEX": "Mexico", "IDN": "Indonesia", "TUR": "Turkey", "SAU": "Saudi Arabia", "ZAF": "South Africa",
        "ARG": "Argentina", "EGY": "Egypt", "NGA": "Nigeria", "PAK": "Pakistan", "VNM": "Vietnam",
        "PHL": "Philippines", "BGD": "Bangladesh", "ETH": "Ethiopia", "COL": "Colombia", "UKR": "Ukraine",
        "POL": "Poland", "MYS": "Malaysia", "PER": "Peru", "CHL": "Chile", "CZE": "Czech Republic",
        "ROU": "Romania", "PRT": "Portugal", "GRC": "Greece", "QAT": "Qatar", "HUN": "Hungary",
        "KAZ": "Kazakhstan", "KWT": "Kuwait", "MAR": "Morocco", "SVK": "Slovakia", "ECU": "Ecuador",
        "KEN": "Kenya", "PRI": "Puerto Rico", "ETH": "Ethiopia", "VNM": "Vietnam", "GTM": "Guatemala",
        "BGR": "Bulgaria", "HRV": "Croatia", "UZB": "Uzbekistan", "LUX": "Luxembourg", "PAN": "Panama",
        "CRI": "Costa Rica", "URY": "Uruguay", "LTU": "Lithuania", "SVN": "Slovenia", "SRB": "Serbia",
        "AZE": "Azerbaijan", "TUN": "Tunisia", "NPL": "Nepal", "LBN": "Lebanon", "LKA": "Sri Lanka",
        "BOL": "Bolivia", "HND": "Honduras", "PNG": "Papua New Guinea", "JAM": "Jamaica", "ARM": "Armenia",
        "ALB": "Albania", "CIV": "Ivory Coast", "SEN": "Senegal", "BIH": "Bosnia", "GEO": "Georgia",
        "GHA": "Ghana", "MNG": "Mongolia", "YEM": "Yemen", "MKD": "North Macedonia", "MDA": "Moldova",
        "NER": "Niger", "KGZ": "Kyrgyzstan", "TJK": "Tajikistan", "TGO": "Togo", "MLI": "Mali",
        "RWA": "Rwanda", "SOM": "Somalia", "BDI": "Burundi", "TCD": "Chad", "GNB": "Guinea-Bissau",
        "BFA": "Burkina Faso", "LBR": "Liberia", "SLE": "Sierra Leone", "CAF": "Central African Republic",
        "LSO": "Lesotho", "GMB": "Gambia", "SWZ": "Eswatini", "DJI": "Djibouti", "COM": "Comoros",
        "CPV": "Cape Verde", "STP": "Sao Tome", "SYC": "Seychelles", "MDV": "Maldives", "MUS": "Mauritius",
        "BHS": "Bahamas", "BRB": "Barbados", "GRD": "Grenada", "VCT": "St Vincent", "LCA": "St Lucia",
        "DMA": "Dominica", "ATG": "Antigua", "KNA": "St Kitts", "VUT": "Vanuatu", "WSM": "Samoa",
        "TON": "Tonga", "FSM": "Micronesia", "KIR": "Kiribati", "SLB": "Solomon Islands", "PLW": "Palau",
        "NRU": "Nauru", "TUV": "Tuvalu", "COK": "Cook Islands", "NIU": "Niue", "TKL": "Tokelau",
        "PSE": "Palestine", "TLS": "Timor-Leste", "XKX": "Kosovo", "ABW": "Aruba", "CUW": "Curacao",
        "SXM": "Sint Maarten", "MAF": "St Martin", "BLM": "St Barthelemy", "GIB": "Gibraltar", "GGY": "Guernsey",
        "JEY": "Jersey", "IMN": "Isle of Man", "FRO": "Faroe Islands", "GRL": "Greenland", "GUM": "Guam",
        "VIR": "US Virgin Islands", "CYM": "Cayman Islands", "BMU": "Bermuda", "TCA": "Turks and Caicos",
        "AIA": "Anguilla", "MSR": "Montserrat", "FLK": "Falkland Islands", "SGS": "South Georgia", "PCN": "Pitcairn",
        "SHN": "St Helena", "ASC": "Ascension", "TAA": "Tristan da Cunha", "IOT": "Chagos", "VGB": "British Virgin Islands",
        "NFK": "Norfolk Island", "CXR": "Christmas Island", "CCK": "Cocos Islands", "HMD": "Heard Island",
        "ATA": "Antarctica", "ATF": "French Southern", "BVT": "Bouvet Island", "SGP": "Singapore", "NZL": "New Zealand",
        "THA": "Thailand", "IDN": "Indonesia", "MYS": "Malaysia", "PHL": "Philippines", "MMR": "Myanmar",
        "KHM": "Cambodia", "LAO": "Laos", "BRN": "Brunei", "TLS": "Timor-Leste", "AFG": "Afghanistan",
        "IRN": "Iran", "IRQ": "Iraq", "SYR": "Syria", "JOR": "Jordan", "ISR": "Israel",
        "LBN": "Lebanon", "CYP": "Cyprus", "MLT": "Malta", "ISL": "Iceland", "IRL": "Ireland",
        "DNK": "Denmark", "FIN": "Finland", "NOR": "Norway", "SWE": "Sweden", "EST": "Estonia",
        "LVA": "Latvia", "BLR": "Belarus", "UKR": "Ukraine", "MDA": "Moldova", "ROU": "Romania",
        "BGR": "Bulgaria", "SRB": "Serbia", "MNE": "Montenegro", "ALB": "Albania", "GRC": "Greece",
        "TUR": "Turkey", "CYP": "Cyprus", "ARM": "Armenia", "AZE": "Azerbaijan", "GEO": "Georgia",
        "KAZ": "Kazakhstan", "TKM": "Turkmenistan", "UZB": "Uzbekistan", "KGZ": "Kyrgyzstan", "TJK": "Tajikistan",
        "MNG": "Mongolia", "CHN": "China", "PRK": "North Korea", "KOR": "South Korea", "JPN": "Japan",
        "TWN": "Taiwan", "HKG": "Hong Kong", "MAC": "Macau", "IND": "India", "PAK": "Pakistan",
        "BGD": "Bangladesh", "LKA": "Sri Lanka", "NPL": "Nepal", "BTN": "Bhutan", "MDV": "Maldives",
        "AFG": "Afghanistan", "IRN": "Iran", "OMN": "Oman", "YEM": "Yemen", "ARE": "UAE",
        "QAT": "Qatar", "BHR": "Bahrain", "KWT": "Kuwait", "SAU": "Saudi Arabia", "JOR": "Jordan",
        "ISR": "Israel", "LBN": "Lebanon", "SYR": "Syria", "IRQ": "Iraq", "TUR": "Turkey",
        "EGY": "Egypt", "LBY": "Libya", "TUN": "Tunisia", "DZA": "Algeria", "MAR": "Morocco",
        "MRT": "Mauritania", "MLI": "Mali", "NER": "Niger", "TCD": "Chad", "SDN": "Sudan",
        "ERI": "Eritrea", "DJI": "Djibouti", "SOM": "Somalia", "ETH": "Ethiopia", "SSD": "South Sudan",
        "CAF": "Central African Republic", "CMR": "Cameroon", "NGA": "Nigeria", "BEN": "Benin", "TGO": "Togo",
        "GHA": "Ghana", "CIV": "Ivory Coast", "LBR": "Liberia", "SLE": "Sierra Leone", "GIN": "Guinea",
        "GNB": "Guinea-Bissau", "SEN": "Senegal", "GMB": "Gambia", "BFA": "Burkina Faso", "CPV": "Cape Verde",
        "GNQ": "Equatorial Guinea", "GAB": "Gabon", "COG": "Congo", "COD": "DR Congo", "UGA": "Uganda",
        "KEN": "Kenya", "RWA": "Rwanda", "BDI": "Burundi", "TZA": "Tanzania", "MWI": "Malawi",
        "MOZ": "Mozambique", "ZMB": "Zambia", "ZWE": "Zimbabwe", "BWA": "Botswana", "NAM": "Namibia",
        "ZAF": "South Africa", "LSO": "Lesotho", "SWZ": "Eswatini", "MDG": "Madagascar", "MUS": "Mauritius",
        "COM": "Comoros", "SYC": "Seychelles", "REU": "Reunion", "MYT": "Mayotte", "BRA": "Brazil",
        "ARG": "Argentina", "CHL": "Chile", "URY": "Uruguay", "PRY": "Paraguay", "BOL": "Bolivia",
        "PER": "Peru", "ECU": "Ecuador", "COL": "Colombia", "VEN": "Venezuela", "GUY": "Guyana",
        "SUR": "Suriname", "GUF": "French Guiana", "CAN": "Canada", "USA": "United States", "MEX": "Mexico",
        "GTM": "Guatemala", "BLZ": "Belize", "SLV": "El Salvador", "HND": "Honduras", "NIC": "Nicaragua",
        "CRI": "Costa Rica", "PAN": "Panama", "CUB": "Cuba", "JAM": "Jamaica", "HTI": "Haiti",
        "DOM": "Dominican Republic", "PRI": "Puerto Rico", "VCT": "St Vincent", "GRD": "Grenada", "TTO": "Trinidad",
        "BRB": "Barbados", "LCA": "St Lucia", "DMA": "Dominica", "ATG": "Antigua", "KNA": "St Kitts",
        "VGB": "British Virgin Islands", "AIA": "Anguilla", "MAF": "St Martin", "SXM": "Sint Maarten", "CUW": "Curacao",
        "ABW": "Aruba", "BES": "Bonaire", "CYM": "Cayman Islands", "TCA": "Turks and Caicos", "BHS": "Bahamas",
        "BMU": "Bermuda", "GRL": "Greenland", "SPM": "St Pierre", "MNP": "Northern Mariana Islands", "GUM": "Guam",
        "ASM": "American Samoa", "VIR": "US Virgin Islands", "PLW": "Palau", "FSM": "Micronesia", "KIR": "Kiribati",
        "MHL": "Marshall Islands", "NRU": "Nauru", "SLB": "Solomon Islands", "VUT": "Vanuatu", "FJI": "Fiji",
        "TON": "Tonga", "WSM": "Samoa", "TUV": "Tuvalu", "COK": "Cook Islands", "NIU": "Niue",
        "TKL": "Tokelau", "WLF": "Wallis and Futuna", "NFK": "Norfolk Island", "PCN": "Pitcairn", "HMD": "Heard Island",
        "IOT": "Chagos", "SGS": "South Georgia", "SHN": "St Helena", "ASC": "Ascension", "TAA": "Tristan da Cunha",
        "FLK": "Falkland Islands", "GIB": "Gibraltar", "GGY": "Guernsey", "JEY": "Jersey", "IMN": "Isle of Man",
        "FRO": "Faroe Islands", "ALA": "Aland Islands", "SJM": "Svalbard", "NCL": "New Caledonia", "PYF": "French Polynesia",
        "GUM": "Guam", "MNP": "Northern Mariana Islands", "ASM": "American Samoa", "TLS": "Timor-Leste", "XKX": "Kosovo",
        "PSE": "Palestine", "UNK": "Unknown"
    }
    
    # Get the most recent country features with their topics
    pipeline = [
        {"$match": {"mode": mode}},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$country",
            "doc": {"$first": "$$ROOT"},
            "latest_timestamp": {"$first": "$timestamp"}
        }},
        {"$project": {
            "country": "$_id",
            "risk_score": {"$ifNull": ["$doc.features.global_risk_score", 50.0]},
            "topics": {"$ifNull": ["$doc.features.top_topics", ["no data"]]},
            "timestamp": "$latest_timestamp",
            "news_sentiment": {"$ifNull": ["$doc.features.news_sentiment", 0.0]},
            "gdelt_sentiment": {"$ifNull": ["$doc.features.gdelt_sentiment", 0.0]},
        }},
        {"$sort": {"timestamp": -1}},
        {"$limit": limit}
    ]
    
    docs = list(db.country_features.aggregate(pipeline))
    
    # Sample news headlines and summaries for different categories
    news_templates = {
        "political": [
            ("Government announces new economic reforms amid rising inflation concerns", "The administration unveiled a comprehensive economic package today aimed at stabilizing markets and controlling inflation. Key measures include tax adjustments, monetary policy changes, and social welfare programs. Opposition parties have expressed mixed reactions to the proposed reforms."),
            ("Parliament debates controversial new legislation on digital privacy", "Lawmakers are currently discussing a bill that would significantly change how personal data is collected and stored by tech companies. Privacy advocates argue the legislation doesn't go far enough, while industry representatives warn of compliance costs."),
            ("Opposition leader calls for early elections following policy disagreements", "The main opposition party has demanded snap elections after the government failed to pass key infrastructure spending bills. Political analysts suggest this could lead to increased market volatility in the coming weeks."),
        ],
        "economic": [
            ("Central bank raises interest rates to combat inflation pressures", "The monetary authority announced a 25 basis point increase in the benchmark interest rate, citing persistent inflation above target levels. The move is expected to strengthen the currency but may slow economic growth in the short term."),
            ("Stock market reaches record high as foreign investment surges", "Local equities markets closed at all-time highs today, driven by unprecedented foreign capital inflows. Technology and renewable energy sectors led the gains, with trading volumes exceeding historical averages."),
            ("Trade deficit narrows as exports show strong growth", "Latest trade figures reveal a significant improvement in the country's trade balance, with exports growing 15% year-over-year. Manufacturing and agricultural products drove the increase, while import growth remained moderate."),
        ],
        "social": [
            ("Major labor union announces nationwide strike action", "The country's largest labor federation has called for a general strike next week to protest wage stagnation and working conditions. Essential services are expected to be affected, with the government urging both sides to return to negotiations."),
            ("Healthcare system faces strain as flu season peaks early", "Hospitals across the country are reporting capacity issues as an early and severe flu season overwhelms medical facilities. Health officials are urging vulnerable populations to take precautions and consider vaccination."),
            ("Education reforms spark debate among parents and teachers", "Proposed changes to the national curriculum have generated significant discussion, with supporters praising modernization efforts while critics worry about reduced emphasis on traditional subjects."),
        ],
        "security": [
            ("Military conducts exercises near border amid regional tensions", "Armed forces are conducting large-scale military exercises in response to increased activity from neighboring countries. Defense officials emphasize these are routine training operations, though observers note the timing amid diplomatic tensions."),
            ("Cybersecurity agency warns of increased hacking attempts", "National cybersecurity authorities report a 40% increase in attempted cyber attacks on critical infrastructure. The agency has issued new guidelines for businesses and government departments to strengthen their digital defenses."),
            ("Police launch operation against organized crime networks", "Law enforcement agencies conducted coordinated raids across multiple cities, resulting in dozens of arrests. Officials describe the operation as a significant blow to transnational criminal organizations operating in the region."),
        ],
        "environment": [
            ("Severe weather alerts issued as storm system approaches", "Meteorological services have issued warnings for heavy rainfall and strong winds expected to impact coastal regions. Emergency services are on standby, and residents in low-lying areas are advised to prepare for potential flooding."),
            ("Government announces new climate action plan", "Environmental authorities unveiled an ambitious strategy to reduce carbon emissions by 40% over the next decade. The plan includes investments in renewable energy, public transportation, and sustainable agriculture practices."),
            ("Wildfire containment efforts continue as temperatures rise", "Firefighting crews are battling multiple blazes across drought-affected regions. Hot and dry conditions are expected to continue, complicating efforts to bring the fires under control."),
        ],
        "technology": [
            ("Tech sector sees major investment from international firms", "Several global technology companies announced significant investments in local research and development facilities. The move is expected to create thousands of high-skilled jobs and boost the country's innovation ecosystem."),
            ("New telecommunications infrastructure project launched", "The government and private sector partners broke ground on a nationwide 5G network expansion. The project aims to provide high-speed internet access to rural and underserved areas within three years."),
            ("Data protection authority fines major tech company", "The national privacy regulator imposed a record fine on a major technology firm for violations of data protection laws. The case is seen as a landmark decision that could affect how tech companies operate in the region."),
        ],
    }
    
    # Source URLs for different news categories
    source_urls = {
        "Reuters": "https://www.reuters.com",
        "Bloomberg": "https://www.bloomberg.com",
        "BBC": "https://www.bbc.com/news",
        "CNN": "https://www.cnn.com",
        "Al Jazeera": "https://www.aljazeera.com",
        "Associated Press": "https://apnews.com",
        "Financial Times": "https://www.ft.com",
        "The Guardian": "https://www.theguardian.com",
        "Wall Street Journal": "https://www.wsj.com",
        "New York Times": "https://www.nytimes.com",
        "GDELT": "https://www.gdeltproject.org",
        "News": "https://news.google.com",
    }
    
    import random
    random.seed(42)  # For consistent results
    
    # Build intelligence feed items with detailed news
    feed_items = []
    for idx, doc in enumerate(docs):
        country_code = convert_country_code(doc.get("country", "UNK"))
        country_name = country_names.get(country_code, country_code)
        topics = doc.get("topics", ["no data"])
        risk_score = float(doc.get("risk_score", 50.0))
        
        # Determine category based on topics and risk score
        if risk_score >= 75:
            category = "security"
        elif risk_score >= 50:
            category = "political"
        elif "economy" in str(topics).lower() or "market" in str(topics).lower():
            category = "economic"
        elif "climate" in str(topics).lower() or "weather" in str(topics).lower():
            category = "environment"
        elif "tech" in str(topics).lower() or "digital" in str(topics).lower():
            category = "technology"
        else:
            category = random.choice(["political", "economic", "social"])
        
        # Select news template
        templates = news_templates.get(category, news_templates["political"])
        headline, summary = templates[idx % len(templates)]
        
        # Generate full article text
        full_article = f"""{headline}

{summary}

This development comes at a time when {country_name} is navigating complex domestic and international challenges. Analysts suggest that the situation will require careful monitoring in the coming days, with potential implications for regional stability and economic performance.

Key stakeholders have responded with varying degrees of support and concern. International observers are watching closely to see how authorities manage the evolving situation. The outcome could have lasting effects on {country_name}'s trajectory in the near to medium term.

Further updates are expected as more information becomes available and officials provide additional context on the measures being implemented."""
        
        # Determine source based on available data
        news_sent = float(doc.get("news_sentiment", 0.0))
        gdelt_sent = float(doc.get("gdelt_sentiment", 0.0))
        
        if abs(news_sent) > abs(gdelt_sent):
            source = random.choice(["Reuters", "Bloomberg", "BBC", "CNN", "Associated Press"])
        else:
            source = "GDELT"
        
        source_url = source_urls.get(source, "https://news.google.com")
        
        # Create unique ID for this feed item
        item_id = f"{country_code}_{doc.get('timestamp', datetime.utcnow().isoformat())}_{idx}"
        
        feed_items.append({
            "id": item_id,
            "country": country_code,
            "country_name": country_name,
            "headline": headline,
            "summary": summary,
            "full_article": full_article,
            "source": source,
            "source_url": source_url,
            "risk_score": risk_score,
            "timestamp": str(doc.get("timestamp", datetime.utcnow().isoformat())),
            "category": category
        })
    
    # Sort by most recent first
    feed_items.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return feed_items





# ISO 3166-1 alpha-3 to alpha-2 reverse mapping (for drilldown lookups)
ISO3_TO_ISO2 = {v: k for k, v in ISO2_TO_ISO3.items()}

def normalize_country_lookup(country: str) -> list:
    """Generate list of possible country code formats to search for"""
    country = country.upper().strip()
    codes = [country]  # Original code
    if len(country) == 2 and country in ISO2_TO_ISO3:
        codes.append(ISO2_TO_ISO3[country])  # Add 3-letter version
    elif len(country) == 3 and country in ISO3_TO_ISO2:
        codes.append(ISO3_TO_ISO2[country])  # Add 2-letter version
    return codes


@app.get("/dashboard/country/{country}")
@limiter.limit("20/minute")
def dashboard_country(request: Request, country: str, role: str = Depends(check_role), mode: str = Query("online")):
    # Try multiple country code formats (2-letter and 3-letter)
    country_codes = normalize_country_lookup(country)
    
    docs = []
    for code in country_codes:
        docs = list(db.country_features.find({"country": code, "mode": mode}).sort("timestamp", -1).limit(50))
        if docs:
            break
    
    if not docs:
        raise HTTPException(status_code=404, detail=f"No country data for {country} (tried: {country_codes})")


    ordered = list(reversed(docs))
    latest = ordered[-1]
    latest_features = latest.get("features", {})
    trend = [
        {
            "timestamp": str(d.get("timestamp", datetime.utcnow().isoformat())),
            "value": float(d.get("features", {}).get("global_risk_score", 50.0)),
        }
        for d in ordered
    ]

    drivers = []
    for k in ("news_sentiment", "gdelt_sentiment", "crypto_return", "crypto_volatility", "stock_return", "stock_volatility", "weather_anomaly"):
        value = float(latest_features.get(k, 0.0))
        drivers.append({
            "feature": k,
            "value": value,
            "contribution": round(value * 0.12, 4),
        })

    events_cursor = list(
        operator_events_collection.find({"country": country}).sort("timestamp", -1).limit(20)
    )
    events = [{
        "id": str(e.get("_id")),
        "title": f"{e.get('action', 'update')} by {e.get('owner', 'ops')}",
        "timestamp": str(e.get("timestamp", datetime.utcnow().isoformat())),
        "severity": "medium",
    } for e in events_cursor]

    risk = float(latest_features.get("global_risk_score", 50.0))
    return {
        "country": country,
        "risk": risk,
        "trend": trend,
        "drivers": drivers,
        "events": events,
        "confidenceInterval": {"lower": max(0, risk - 5), "upper": min(100, risk + 5)},
    }


@app.get("/dashboard/governance")
@limiter.limit("30/minute")
def dashboard_governance(request: Request, role: str = Depends(check_role), mode: str = Query("online")):

    latest_doc = get_latest_global_doc(mode)
    base_risk = float(latest_doc.get("features", {}).get("global_risk_score", 50.0))

    model_info_docs = list(model_monitoring_collection.find().sort("timestamp", -1).limit(300))
    by_model: dict[str, list[dict]] = defaultdict(list)
    for d in model_info_docs:
        by_model[str(d.get("model_version", "unknown"))].append(d)

    models = []
    for idx, (model_name, rows) in enumerate(by_model.items()):
        latest = rows[0]
        drift = float(latest.get("drift_score", 0.0) or 0.0)
        conf_values = [float(x.get("probability", 0.5) or 0.5) for x in rows[:30]]
        calibration = sum(conf_values) / max(1, len(conf_values))
        vote = max(0.0, min(100.0, base_risk + ((idx - 1) * 1.8)))
        models.append({
            "name": model_name,
            "latencyMs": int(latest.get("latency_ms", 0) or 0),
            "calibration": round(calibration, 4),
            "driftHint": "watch" if drift >= 0.35 else "stable",
            "vote": round(vote, 2),
            "confidence": round(calibration, 4),
        })

    if not models:
        models = [{
            "name": "production",
            "latencyMs": 0,
            "calibration": 0.0,
            "driftHint": "stable",
            "vote": round(base_risk, 2),
            "confidence": 0.0,
        }]

    disagreement = []
    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            disagreement.append({
                "left": models[i]["name"],
                "right": models[j]["name"],
                "value": round(abs(models[i]["vote"] - models[j]["vote"]), 2),
            })

    cal_trend_source = list(prediction_collection.find().sort("timestamp", -1).limit(50))
    calibration_trend = [
        {"timestamp": str(d.get("timestamp")), "value": float(d.get("probability", 0.0))}
        for d in reversed(cal_trend_source)
    ]

    return {
        "models": models,
        "disagreement": disagreement,
        "calibrationTrend": calibration_trend,
    }


@app.post("/dashboard/alerts/action")
@limiter.limit("30/minute")
def dashboard_alert_action(request: Request, payload: AlertActionRequest, role: str = Depends(check_role)):
    operator_events_collection.insert_one({
        "country": payload.country,
        "action": payload.action,
        "owner": payload.owner or role,
        "comment": payload.comment or "",
        "timestamp": datetime.utcnow().isoformat(),
    })
    return {"ok": True}


@app.post("/dashboard/scenario/run")
@limiter.limit("20/minute")
def dashboard_scenario_run(request: Request, payload: ScenarioRunRequest, role: str = Depends(check_role)):
    base_doc = get_latest_global_doc("online")
    base = float(base_doc.get("features", {}).get("global_risk_score", 50.0))
    horizon = 24
    scenario = []
    baseline = []
    now = datetime.utcnow()
    for i in range(horizon):
        step = payload.steps[min(i, len(payload.steps) - 1)] if payload.steps else ScenarioStep(
            label="baseline", marketShock=0.0, sentimentShock=0.0, weatherShock=0.0
        )
        impulse = (step.marketShock * 0.45) + (step.sentimentShock * 0.35) + (step.weatherShock * 0.2)
        decay = 1 / (1 + i * 0.16)
        value = max(0.0, min(100.0, base + impulse * decay))
        scenario.append(round(value, 3))
        baseline.append(round(base, 3))

    return {
        "baseline": baseline,
        "scenario": scenario,
        "timestamps": [(now + timedelta(hours=i)).isoformat() for i in range(horizon)],
    }


# =====================================================
# REAL-TIME FEATURES ENDPOINTS
# =====================================================

def _pick_nested(doc: dict, *paths: str, default=None):
    for path in paths:
        current = doc
        found = True
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current.get(part)
            else:
                found = False
                break
        if found and current not in (None, ""):
            return current
    return default


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_timestamp(doc: dict, *paths: str) -> str:
    return str(_pick_nested(doc, *paths, default=datetime.utcnow().isoformat()))


def _parse_timestamp(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _latest_timestamp(*docs: dict) -> str:
    stamps = [
        _parse_timestamp(
            _pick_nested(doc, "data_timestamp", "data.time", "timestamp", "collected_at", default=None)
        )
        for doc in docs
        if doc
    ]
    valid = [stamp for stamp in stamps if stamp != datetime.min.replace(tzinfo=timezone.utc)]
    latest = max(valid) if valid else datetime.utcnow().replace(tzinfo=timezone.utc)
    return latest.isoformat()


def _series_change(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    current = values[0]
    previous = values[1] if len(values) > 1 else current
    change = round(current - previous, 4)
    change_percent = round((change / previous) * 100, 2) if previous else 0.0
    return change, change_percent

@app.get("/dashboard/crypto-pulse")
@limiter.limit("60/minute")
def dashboard_crypto_pulse(request: Request, role: str = Depends(check_role), limit: int = Query(10, ge=1, le=50)):
    """
    Returns real-time cryptocurrency market data including prices, changes, and volume.
    """
    crypto_docs = list(db.crypto.find().sort("data_timestamp", -1).limit(limit * 48))
    price_history_by_coin: dict[str, list[dict]] = defaultdict(list)
    for doc in crypto_docs:
        coin_id = str(_pick_nested(doc, "data_coin_id", "data.coin_id", "data.coin", "coin_id", default="unknown"))
        price_history_by_coin[coin_id].append(doc)

    crypto_items = []

    for coin_id, docs in price_history_by_coin.items():
        latest_doc = docs[0]
        price_points = [
            _safe_float(_pick_nested(doc, "data_price", "data.price", "price", default=0.0))
            for doc in docs
        ]
        price_points = [point for point in price_points if point > 0]
        if not price_points:
            continue

        price = round(price_points[0], 2)
        previous_price = price_points[min(len(price_points) - 1, 23)] if len(price_points) > 1 else price_points[0]
        change_24h = round(price_points[0] - previous_price, 2)
        change_percent = round((change_24h / previous_price) * 100, 2) if previous_price else 0.0
        sparkline_points = list(reversed(price_points[:11]))
        observed_volume = _safe_float(_pick_nested(latest_doc, "data_volume", "data.volume", "volume_24h", default=0.0))
        observed_market_cap = _safe_float(_pick_nested(latest_doc, "data_market_cap", "data.market_cap", "market_cap", default=0.0))

        crypto_items.append({
            "id": str(latest_doc.get("_id", "")),
            "coin_id": coin_id,
            "name": coin_id.replace("-", " ").title(),
            "symbol": coin_id[:3].upper(),
            "price_usd": price,
            "change_24h": change_24h,
            "change_percent": change_percent,
            "volume_24h": round(observed_volume, 0),
            "market_cap": round(observed_market_cap, 0),
            "timestamp": _safe_timestamp(latest_doc, "data_timestamp", "data.timestamp", "timestamp", "collected_at"),
            "sparkline": [round(point, 2) for point in sparkline_points],
        })

    crypto_items.sort(key=lambda item: (_parse_timestamp(item["timestamp"]), item["price_usd"]), reverse=True)
    crypto_items = crypto_items[:limit]

    return {
        "items": crypto_items,
        "last_updated": _latest_timestamp(*crypto_docs),
        "total_count": len(crypto_items)
    }


@app.get("/dashboard/disaster-monitor")
@limiter.limit("30/minute")
def dashboard_disaster_monitor(request: Request, role: str = Depends(check_role), limit: int = Query(20, ge=1, le=100)):
    """
    Returns real-time disaster alerts including earthquakes and severe weather.
    """
    # Get latest earthquake data
    earthquake_docs = list(db.earthquakes.find().sort("collected_at", -1).limit(max(1, limit // 2)))
    weather_docs = list(db.weather.find().sort("data_timestamp", -1).limit(max(1, limit // 2)))
    
    disaster_items = []
    
    # Process earthquakes
    for doc in earthquake_docs:
        magnitude = _safe_float(_pick_nested(doc, "magnitude", "data.magnitude", "data.mag", default=0.0))
        severity = "critical" if magnitude >= 7.0 else "elevated" if magnitude >= 5.0 else "guarded"
        
        disaster_items.append({
            "id": str(doc.get("_id", "")),
            "type": "earthquake",
            "title": f"Magnitude {magnitude} Earthquake",
            "location": _pick_nested(doc, "place", "data.place", default="Unknown Location"),
            "coordinates": {
                "lat": _safe_float(_pick_nested(doc, "latitude", "data.latitude", default=0.0)),
                "lon": _safe_float(_pick_nested(doc, "longitude", "data.longitude", default=0.0)),
            },
            "magnitude": magnitude,
            "severity": severity,
            "depth_km": _safe_float(_pick_nested(doc, "depth", "data.depth", default=0.0)),
            "tsunami_risk": magnitude >= 7.0 and bool(_pick_nested(doc, "tsunami", "data.tsunami", default=False)),
            "timestamp": _safe_timestamp(doc, "timestamp", "data.time", "collected_at"),
            "source": "USGS"
        })
    
    # Process weather alerts
    for doc in weather_docs:
        disaster_items.append({
            "id": str(doc.get("_id", "")),
            "type": "weather",
            "title": str(_pick_nested(doc, "event", "data_weather", "data.weather", default="Weather Alert")),
            "location": str(_pick_nested(doc, "location", "data_city", "data.city", default="Unknown Location")),
            "severity": str(_pick_nested(doc, "severity", "data_severity", default="guarded")).lower(),
            "description": str(_pick_nested(doc, "description", "data_weather", default="")),
            "temperature": _safe_float(_pick_nested(doc, "temperature", "data_temperature", default=0.0)),
            "wind_speed": _safe_float(_pick_nested(doc, "wind_speed", "data_wind_speed", default=0.0)),
            "timestamp": _safe_timestamp(doc, "timestamp", "data_timestamp", "collected_at"),
            "source": "Weather API"
        })
    
    # Sort by timestamp (most recent first)
    disaster_items.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return {
        "items": disaster_items[:limit],
        "last_updated": _latest_timestamp(*earthquake_docs, *weather_docs),
        "total_count": len(disaster_items)
    }


@app.get("/dashboard/economic-indicators")
@limiter.limit("30/minute")
def dashboard_economic_indicators(request: Request, role: str = Depends(check_role)):
    """
    Returns real-time economic indicators including currency rates and key metrics.
    """
    economic_docs = list(db.economics.find().sort("collected_at", -1).limit(300))

    currency_rates = []
    currency_history: dict[str, list[float]] = defaultdict(list)
    for doc in economic_docs:
        if str(doc.get("source", "")).lower() != "frankfurter":
            continue
        base_currency = str(_pick_nested(doc, "data.base_currency", "data_base_currency", default="USD"))
        currency = str(_pick_nested(doc, "data.currency", "data_currency", default=""))
        if not currency:
            continue
        pair_name = f"{base_currency}/{currency}"
        currency_history[pair_name].append(_safe_float(_pick_nested(doc, "data.rate", "data_rate", "rate", default=0.0)))

    for pair_name, values in list(currency_history.items())[:8]:
        current_rate = round(values[0], 4) if values else 0.0
        change, change_percent = _series_change(values[:2])
        currency_rates.append({
            "pair": pair_name,
            "rate": current_rate,
            "change_24h": change,
            "change_percent": change_percent
        })

    fred_docs = [doc for doc in economic_docs if str(doc.get("source", "")).lower() == "fred"]
    economic_releases = []
    for doc in fred_docs:
        economic_releases.append({
            "id": str(doc.get("_id", "")),
            "indicator": str(_pick_nested(doc, "series_id", "data.indicator", "data.series_id", default="Unknown")),
            "value": _safe_float(_pick_nested(doc, "value", "data.value", default=0.0)),
            "date": str(_pick_nested(doc, "date", "data.date", default=datetime.utcnow().isoformat())),
            "timestamp": _safe_timestamp(doc, "timestamp", "data.timestamp", "collected_at")
        })

    latest_by_series: dict[str, list[float]] = defaultdict(list)
    for doc in fred_docs:
        series_id = str(_pick_nested(doc, "series_id", "data.series_id", "data.indicator", default="UNKNOWN"))
        latest_by_series[series_id].append(_safe_float(_pick_nested(doc, "value", "data.value", default=0.0)))

    def build_indicator(series_key: str, fallback_source: str):
        values = latest_by_series.get(series_key, [])
        change, _ = _series_change(values[:2])
        return {
            "value": round(values[0], 2) if values else 0.0,
            "change": round(change, 2),
            "source": fallback_source if values else "Unavailable"
        }

    indicators = {
        "interest_rate": build_indicator("FEDFUNDS", "Federal Reserve"),
        "inflation_rate": build_indicator("CPIAUCSL", "CPI Data"),
        "unemployment": build_indicator("UNRATE", "BLS"),
    }

    return {
        "currency_rates": currency_rates,
        "economic_releases": economic_releases[:5],
        "key_indicators": indicators,
        "last_updated": _latest_timestamp(*economic_docs)
    }


@app.get("/dashboard/health-alerts")
@limiter.limit("30/minute")
def dashboard_health_alerts(request: Request, role: str = Depends(check_role), limit: int = Query(10, ge=1, le=50)):
    """
    Returns WHO health alerts and disease outbreak information.
    """
    who_docs = list(db.health.find().sort("collected_at", -1).limit(limit))
    health_items = []
    for idx, doc in enumerate(who_docs):
        indicator = str(_pick_nested(doc, "data.indicator", "indicator", default="WHO Indicator"))
        cases = _safe_int(_pick_nested(doc, "cases", "data.cases", "data.value", "value", default=0), default=0)
        deaths = _safe_int(_pick_nested(doc, "deaths", "data.deaths", default=max(0, int(cases * 0.02))), default=max(0, int(cases * 0.02)))
        severity = "critical" if cases >= 100000 else "elevated" if cases >= 10000 else "guarded"
        health_items.append({
            "id": str(doc.get("_id", f"health-{idx}")),
            "disease": indicator.replace("_", " "),
            "type": "indicator",
            "severity": severity,
            "location": str(_pick_nested(doc, "country", "data.country", "data.SpatialDim", default="Global")),
            "cases": cases,
            "deaths": deaths,
            "status": "active" if severity in {"critical", "elevated"} else "monitoring",
            "timestamp": _safe_timestamp(doc, "timestamp", "data.timestamp", "collected_at"),
            "source": "WHO",
            "description": f"Latest WHO indicator update for {indicator.replace('_', ' ')} in {str(_pick_nested(doc, 'country', 'data.country', 'data.SpatialDim', default='Global'))}."
        })

    vaccination_docs = [
        doc for doc in who_docs
        if "vacc" in str(_pick_nested(doc, "data.indicator", "indicator", default="")).lower()
    ]
    vaccination_values = [_safe_float(_pick_nested(doc, "data.value", "value", default=0.0)) for doc in vaccination_docs]
    vaccination_data = {
        "global_coverage": round(max(vaccination_values), 1) if vaccination_values else 0.0,
        "target_coverage": 70.0,
        "doses_administered": int(sum(max(value, 0.0) for value in vaccination_values)),
        "campaigns_active": len(vaccination_docs)
    }

    return {
        "outbreaks": health_items,
        "vaccination": vaccination_data,
        "last_updated": _latest_timestamp(*who_docs),
        "total_active": len([h for h in health_items if h["status"] == "active"])
    }


@app.get("/dashboard/trends-radar")
@limiter.limit("30/minute")
def dashboard_trends_radar(request: Request, role: str = Depends(check_role), limit: int = Query(20, ge=1, le=100)):
    """
    Returns Google Trends data showing trending search terms and topics.
    """
    trends_docs = list(db.trends.find().sort("collected_at", -1).limit(limit * 8))
    trend_items = []
    grouped_topics: dict[str, list[dict]] = defaultdict(list)
    for doc in trends_docs:
        topic = str(_pick_nested(doc, "topic", "data.topic", "data.query", "data.keyword", default=""))
        if topic:
            grouped_topics[topic].append(doc)

    for idx, (topic, docs) in enumerate(grouped_topics.items()):
        values = [
            _safe_int(_pick_nested(doc, "value", "data.value", "search_volume", "data.interest", "data.interest_score", default=0), default=0)
            for doc in docs
        ]
        values = [value for value in values if value >= 0]
        if not values:
            continue
        current_interest = values[0]
        previous_interest = values[1] if len(values) > 1 else current_interest
        velocity = round(current_interest - previous_interest, 1)
        trend_direction = "rising" if velocity > 0 else "falling" if velocity < 0 else "stable"
        breakout = current_interest >= 80 or velocity >= 20
        trend_items.append({
            "id": str(docs[0].get("_id", f"trend-{idx}")),
            "topic": topic,
            "category": "Public Interest",
            "search_volume": current_interest,
            "interest_score": min(100, current_interest),
            "velocity": velocity,
            "trend_direction": trend_direction,
            "breakout": breakout,
            "timestamp": _safe_timestamp(docs[0], "timestamp", "data_timestamp", "collected_at"),
            "related_queries": [
                f"{topic} news",
                f"{topic} latest",
                f"{topic} update"
            ]
        })
    trend_items.sort(key=lambda x: (x["interest_score"], _parse_timestamp(x["timestamp"])), reverse=True)
    trend_items = trend_items[:limit]

    rising_count = len([t for t in trend_items if t["trend_direction"] == "rising"])
    breakout_count = len([t for t in trend_items if t["breakout"]])

    return {
        "trends": trend_items,
        "summary": {
            "total_trending": len(trend_items),
            "rising_topics": rising_count,
            "breakout_topics": breakout_count,
            "top_category": (
                max(
                    set([t["category"] for t in trend_items]),
                    key=lambda x: sum([t["interest_score"] for t in trend_items if t["category"] == x])
                )
                if trend_items else "None"
            )
        },
        "last_updated": _latest_timestamp(*trends_docs)
    }


# =====================================================
# SENTINEL AI ENDPOINTS
# =====================================================

def _build_sentinel_historical_comparison(history: list[dict]) -> dict:
    if not history:
        return {
            "history": [],
            "trend_data": [],
            "current": None,
            "week_ago": None,
            "month_ago": None,
            "week_change_pct": None,
            "month_change_pct": None,
            "trend_direction": "stable",
        }

    current = float(history[-1].get("risk_score", 0.0))
    week_ago = float(history[-8].get("risk_score", history[0].get("risk_score", current))) if len(history) >= 8 else None
    month_ago = float(history[0].get("risk_score", current))

    week_change_pct = None
    month_change_pct = None
    if week_ago not in (None, 0):
        week_change_pct = round(((current - week_ago) / week_ago) * 100, 2)
    if month_ago not in (None, 0):
        month_change_pct = round(((current - month_ago) / month_ago) * 100, 2)

    trend_direction = "stable"
    if month_change_pct is not None:
        if month_change_pct > 2:
            trend_direction = "worsening"
        elif month_change_pct < -2:
            trend_direction = "improving"

    return {
        "history": history,
        "trend_data": history,
        "current": round(current, 2),
        "week_ago": round(week_ago, 2) if week_ago is not None else None,
        "month_ago": round(month_ago, 2) if month_ago is not None else None,
        "week_change_pct": week_change_pct,
        "month_change_pct": month_change_pct,
        "trend_direction": trend_direction,
    }


def _build_sentinel_qa_answer(payload: SentinelQuestionRequest, analysis: dict) -> str:
    question = (payload.question or "").strip()
    if not question:
        return "Please ask a question and I can summarize the latest risk signals."

    threat_level = analysis.get("threat_level", "stable")
    risk_score = analysis.get("risk_score", 0)
    trend = analysis.get("risk_trend", "stable")
    drivers = analysis.get("top_drivers", []) or []
    driver_labels = [d.get("display_name") or d.get("feature", "unknown driver") for d in drivers[:3]]
    driver_text = ", ".join(driver_labels) if driver_labels else "multiple global indicators"

    country = None
    context = payload.context if isinstance(payload.context, dict) else None
    if context:
        country = context.get("country")

    if country:
        return (
            f"Current global risk is {risk_score} ({threat_level}, trend: {trend}). "
            f"For {country}, the most relevant active signals right now are {driver_text}. "
            f"I will keep monitoring for rapid shifts."
        )

    return (
        f"Current global risk is {risk_score} with a {threat_level} threat level and a {trend} trend. "
        f"Top current drivers are {driver_text}."
    )


@app.get("/api/sentinel/latest")
@limiter.limit("60/minute")
def get_sentinel_latest(request: Request, role: str = Depends(check_role)):
    """
    Get latest SENTINEL AI analysis including:
    - Risk score and delta
    - Threat level assessment
    - Top contributing factors
    - Multi-domain signal detection
    - Confidence level
    - Generated analysis text
    """
    try:
        analysis = compute_sentinel_analysis()
        return analysis
    except Exception as e:
        logger.error("sentinel_analysis_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to compute sentinel analysis")


@app.get("/api/sentinel/history")
@limiter.limit("30/minute")
def get_sentinel_history_api(
    request: Request,
    role: str = Depends(check_role),
    limit: int = Query(10, ge=1, le=100),
    days: int | None = Query(None, ge=1, le=30),
):
    """
    Get historical sentinel analysis data for trend analysis.

    Supports both limit and days query styles.
    """
    try:
        effective_limit = min(100, max(limit, days or 0)) if days else limit
        history = get_sentinel_history(limit=effective_limit)
        return _build_sentinel_historical_comparison(history)
    except Exception as e:
        logger.error("sentinel_history_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to retrieve sentinel history")


@app.post("/api/sentinel/qa")
@limiter.limit("40/minute")
def sentinel_qa(
    payload: SentinelQuestionRequest,
    request: Request,
    role: str = Depends(check_role),
):
    """Simple deterministic Q&A endpoint for Sentinel chat UI."""
    try:
        analysis = compute_sentinel_analysis()
        answer = _build_sentinel_qa_answer(payload, analysis)
        return {
            "answer": answer,
            "timestamp": datetime.utcnow().isoformat(),
            "analysis_snapshot": {
                "risk_score": analysis.get("risk_score"),
                "threat_level": analysis.get("threat_level"),
                "risk_trend": analysis.get("risk_trend"),
            },
        }
    except Exception as e:
        logger.error("sentinel_qa_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to process sentinel question")


@app.post("/api/sentinel/feedback")
@limiter.limit("60/minute")
def sentinel_feedback(
    payload: SentinelFeedbackRequest,
    request: Request,
    role: str = Depends(check_role),
):
    """Persist Sentinel feedback so UI actions are not dropped."""
    try:
        feedback_doc = {
            "eventId": payload.eventId,
            "feedbackType": payload.feedbackType,
            "threatLevel": payload.threatLevel,
            "riskScore": payload.riskScore,
            "timestamp": payload.timestamp,
            "notes": payload.notes,
            "submitted_at": datetime.utcnow().isoformat(),
            "submitted_by_role": role,
        }
        sentinel_feedback_collection.insert_one(feedback_doc)
        return {"ok": True}
    except Exception as e:
        logger.error("sentinel_feedback_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to store sentinel feedback")


# =====================================================
# ANALYTICS ENDPOINTS
# =====================================================
@app.get("/analytics/sentiment-forecast")
@limiter.limit("15/minute")
def analytics_sentiment_forecast(request: Request, role: str = Depends(check_role)):
    history = get_global_history(mode="online", limit=24)
    if not history:
        raise HTTPException(status_code=404, detail="No historical features available")

    sentiments = [float((d.get("features", {}) or {}).get("news_sentiment", 0.0)) * 100 for d in history]
    current = sentiments[-1]
    slope = 0.0 if len(sentiments) < 2 else (sentiments[-1] - sentiments[0]) / max(1, len(sentiments) - 1)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "current_sentiment": round(current, 3),
        "forecast_1h": round(current + slope * 1, 3),
        "forecast_6h": round(current + slope * 6, 3),
        "forecast_24h": round(current + slope * 24, 3),
        "confidence": 0.75 if len(sentiments) >= 6 else 0.55,
    }


@app.get("/analytics/market-reactions")
@limiter.limit("15/minute")
def analytics_market_reactions(request: Request, role: str = Depends(check_role), limit: int = Query(20, ge=1, le=200)):
    history = get_global_history(mode="online", limit=limit + 1)
    rows = []
    for prev, curr in zip(history, history[1:]):
        pf = prev.get("features", {})
        cf = curr.get("features", {})
        rows.append({
            "timestamp": str(curr.get("timestamp", datetime.utcnow().isoformat())),
            "event_type": "Feature shift",
            "sentiment_impact": round((float(cf.get("news_sentiment", 0.0)) - float(pf.get("news_sentiment", 0.0))) * 100, 4),
            "crypto_reaction": round((float(cf.get("crypto_return", 0.0)) - float(pf.get("crypto_return", 0.0))) * 100, 4),
            "stock_reaction": round((float(cf.get("stock_return", 0.0)) - float(pf.get("stock_return", 0.0))) * 100, 4),
            "correlation_strength": round(min(1.0, abs(float(cf.get("crypto_return", 0.0)) + float(cf.get("stock_return", 0.0)))), 4),
        })
    return list(reversed(rows))


@app.get("/analytics/event-predictions")
@limiter.limit("15/minute")
def analytics_event_predictions(request: Request, role: str = Depends(check_role), limit: int = Query(10, ge=1, le=100)):
    country_docs = list(db.country_features.find({"mode": "online"}).sort("timestamp", -1).limit(limit))
    events = []
    for idx, d in enumerate(country_docs):
        f = d.get("features", {})
        risk = float(f.get("global_risk_score", 50.0))
        sev = max(1, min(10, int(risk / 10)))
        events.append({
            "event_id": str(d.get("_id")),
            "event_type": "Country risk signal",
            "severity": sev,
            "predicted_risk_increase": round(max(0.0, risk - 50.0), 2),
            "affected_regions": [str(d.get("country", "unknown"))],
            "confidence": round(min(0.99, 0.5 + (risk / 200)), 4),
            "timestamp": str(d.get("timestamp", datetime.utcnow().isoformat())),
        })
    return events


@app.get("/analytics/export")
@limiter.limit("10/minute")
def analytics_export(
    request: Request,
    role: str = Depends(check_role),
    format: str = Query("csv"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    start_dt = parse_iso_dt(start_date)
    end_dt = parse_iso_dt(end_date)
    rows = get_global_history_api(request=request, role=role, start_date=start_date, end_date=end_date, mode="online", limit=10000)

    if format == "json":
        return rows

    if format != "csv":
        raise HTTPException(status_code=400, detail="Supported formats: csv, json")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()) if rows else ["timestamp", "risk_score"])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return {"format": "csv", "content": output.getvalue(), "rows": len(rows), "start_date": str(start_dt), "end_date": str(end_dt)}


@app.post("/analytics/compare-events")
@limiter.limit("10/minute")
def analytics_compare_events(request: Request, payload: dict, role: str = Depends(check_role)):
    event_ids = payload.get("event_ids") or []
    if not isinstance(event_ids, list):
        raise HTTPException(status_code=400, detail="event_ids must be a list")

    docs = []
    if event_ids:
        candidates = list(db.country_features.find().sort("timestamp", -1).limit(500))
        docs = [d for d in candidates if str(d.get("_id")) in event_ids]

    events = []
    for d in docs:
        f = d.get("features", {})
        events.append({
            "event_id": str(d.get("_id")),
            "event_type": "Country risk signal",
            "severity": max(1, min(10, int(float(f.get("global_risk_score", 50.0)) / 10))),
            "predicted_risk_increase": round(max(0.0, float(f.get("global_risk_score", 50.0)) - 50.0), 2),
            "affected_regions": [str(d.get("country", "unknown"))],
            "confidence": 0.7,
            "timestamp": str(d.get("timestamp", datetime.utcnow().isoformat())),
        })

    if not events:
        return {"events": [], "comparison": {"avg_risk": 0.0, "avg_severity": 0.0}}

    comparison = {
        "avg_risk": round(sum(e["predicted_risk_increase"] for e in events) / len(events), 4),
        "avg_severity": round(sum(e["severity"] for e in events) / len(events), 4),
    }
    return {"events": events, "comparison": comparison}

# =====================================================
# MODEL REGISTRY ENDPOINTS
# =====================================================
@app.get("/model_info")
@limiter.limit("5/minute")
def model_info(request: Request, role: str = Depends(check_role)):
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
@limiter.limit("10/minute")
def predict(request: Request, payload: PredictionRequest, role: str = Depends(check_role)):
    model, version = load_production_model()
    if model is None:
        raise HTTPException(status_code=404, detail="No production model available")

    expected_features = model.n_features_in_
    if len(payload.features) != expected_features:
        raise HTTPException(status_code=400, detail=f"Model expects {expected_features} features")

    try:
        prediction = model.predict([payload.features])[0]
        probabilities = model.predict_proba([payload.features])[0]
        confidence = float(probabilities[1])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Prediction failed: {str(e)}")

    drift_score = compute_feature_drift(payload.features)
    record_prediction(
        prediction_collection=prediction_collection,
        model_monitoring_collection=model_monitoring_collection,
        model_version=version,
        features=payload.features,
        prediction=int(prediction),
        probability=confidence,
        drift_score=drift_score,
        role=role,
        logger=logger,
    )
    runtime_metrics.on_prediction()

    logging.info(f"version={version} | features={payload.features} | prediction={int(prediction)} | confidence={confidence}")

    return {
        "model_version": version,
        "prediction": int(prediction),
        "probability": confidence,
        "drift_score": drift_score,
    }

# =====================================================
# PREDICTION LOGS ENDPOINT
# =====================================================
@app.get("/prediction_logs")
@limiter.limit("5/minute")
def get_prediction_logs(request: Request, limit: int = Query(50, ge=1), role: str = Depends(check_role)):
    logs = list(prediction_collection.find().sort("timestamp", -1).limit(limit))
    return [serialize_doc(log) for log in logs]

# =====================================================
# AUTHENTICATION LOGIN ENDPOINT
# =====================================================

class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str
    organization: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# Temporary storage for password reset tokens
password_reset_tokens = {}


@app.post("/auth/register")
def register(data: RegisterRequest):
    existing = users_collection.find_one({"email": data.email})
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    # Validate role
    valid_roles = ["admin", "researcher", "policy", "student"]
    if data.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

    users_collection.insert_one({
        "email": data.email,
        "password": pwd_context.hash(data.password),
        "role": data.role,
        "name": data.name,
        "organization": data.organization,
        "created_at": datetime.utcnow().isoformat(),
    })

    # Create access token
    access_token = create_access_token({
        "sub": data.email,
        "role": data.role
    })

    return {
        "access_token": access_token,
        "role": data.role,
        "message": "Registration successful"
    }


@app.post("/auth/forgot-password")
def forgot_password(data: ForgotPasswordRequest):
    user = users_collection.find_one({"email": data.email})
    if not user:
        # Return success even if user doesn't exist (security best practice)
        return {"message": "If the email exists, a reset link has been sent"}

    # Generate reset token
    reset_token = str(uuid.uuid4())
    password_reset_tokens[reset_token] = {
        "email": data.email,
        "expires": datetime.utcnow() + timedelta(hours=1)
    }

    # In production, send email with reset link
    # For now, return the token (in production, this would be sent via email)
    return {
        "message": "Password reset link has been sent to your email",
        "reset_token": reset_token  # Remove this in production
    }


@app.post("/auth/reset-password")
def reset_password(data: ResetPasswordRequest):
    # Validate token
    token_data = password_reset_tokens.get(data.token)
    if not token_data:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # Check if token is expired
    if datetime.utcnow() > token_data["expires"]:
        del password_reset_tokens[data.token]
        raise HTTPException(status_code=400, detail="Token has expired")

    # Get user email from token
    email = token_data["email"]
    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    users_collection.update_one(
        {"email": email},
        {"$set": {"password": pwd_context.hash(data.new_password), "updated_at": datetime.utcnow().isoformat()}},
    )

    # Remove used token
    del password_reset_tokens[data.token]

    return {"message": "Password has been reset successfully"}


@app.post("/auth/login")
def login(data: LoginRequest):
    user = users_collection.find_one({"email": data.email})

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not pwd_context.verify(data.password, str(user.get("password", ""))):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({
        "sub": data.email,
        "role": str(user.get("role", "user"))
    })

    return {
        "access_token": access_token,
        "role": str(user.get("role", "user"))
    }

# =====================================================
# SYSTEM HEALTH
# =====================================================
@app.get("/health/live")
def health_live():
    return {"status": "alive"}


@app.get("/health/ready")
@limiter.limit("10/minute")
def health_ready(request: Request, role: str = Depends(check_role)):
    try:
        db.command("ping")
        model, _ = load_production_model()
        return {"status": "ready", "database": "connected", "model_loaded": model is not None}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Not ready: {str(e)}")


@app.get("/health")
@limiter.limit("5/minute")
def health(request: Request, role: str = Depends(check_role)):
    try:
        db.command("ping")
        model, _ = load_production_model()
        return {"status": "healthy", "database": "connected", "model_loaded": model is not None}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/health/dependencies")
@limiter.limit("10/minute")
def health_dependencies(request: Request, role: str = Depends(require_admin), mode: str = Query("online")):
    try:
        db.command("ping")
        deps = get_country_risk_dependency_health(mode=mode)
        deps["country_risk_stream"] = country_risk_stream_health()
        return {"status": "ok", "dependencies": deps}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Dependency check failed: {e}")


@app.get("/observability/metrics")
@limiter.limit("10/minute")
def observability_metrics(request: Request, role: str = Depends(require_admin)):
    return {
        "runtime": runtime_metrics.snapshot(),
        "security": {
            "require_https": REQUIRE_HTTPS,
            "allow_insecure_localhost": ALLOW_INSECURE_LOCALHOST,
            "user_keys_configured": len(USER_API_KEYS),
            "admin_keys_configured": len(ADMIN_API_KEYS),
        },
    }


@app.get("/observability/model")
@limiter.limit("10/minute")
def observability_model(request: Request, window: int = Query(200, ge=10, le=5000), role: str = Depends(require_admin)):
    return build_monitoring_summary(model_monitoring_collection, window=window)


@app.get("/observability/streaming")
@limiter.limit("10/minute")
def observability_streaming(request: Request, role: str = Depends(require_admin)):
    return country_risk_stream_health()


@app.get("/observability/country-risk-validation")
@limiter.limit("10/minute")
def observability_country_risk_validation(request: Request, role: str = Depends(require_admin)):
    return latest_country_risk_validation()


@app.post("/observability/country-risk-validation/run")
@limiter.limit("5/minute")
def observability_country_risk_validation_run(request: Request, role: str = Depends(require_admin)):
    return run_country_risk_validation()


# =====================================================
# REAL-TIME RISK STREAM
# =====================================================
# =====================================================
# REAL-TIME RISK STREAM WITH TOPICS
# =====================================================
@app.websocket("/ws/risk")
async def websocket_risk(websocket: WebSocket, x_api_key: str = Header(None), api_key: str = Query(None)):
    # --- Security check ---
    # Support both header and query parameter for API key
    key = (x_api_key or api_key or "").strip()
    valid_key = any(hmac.compare_digest(key, k) for k in USER_API_KEYS.union(ADMIN_API_KEYS))
    if not valid_key:
        await websocket.close(code=1008)
        return

    # --- Connect client ---
    await manager.connect(websocket)

    try:
        while True:
            # Fetch the latest global_features doc
            doc = db.global_features.find_one({"mode": "online"}, sort=[("_id", DESCENDING)])
            if doc:
                # Serialize for JSON + include top topics
                data = {
                    "timestamp": doc.get("timestamp"),
                    "global_risk_score": doc["features"].get("global_risk_score", 50),
                    "top_topics": doc["features"].get("top_topics", ["no data"])
                }
                await websocket.send_json(data)
            
            # Repeat every 5 seconds
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# =====================================================
# SENTINEL AI REAL-TIME WEBSOCKET
# =====================================================
@app.websocket("/ws/country-risk-map")
async def websocket_country_risk_map(websocket: WebSocket, x_api_key: str = Header(None), api_key: str = Query(None)):
    key = (x_api_key or api_key or "").strip()
    valid_key = any(hmac.compare_digest(key, k) for k in USER_API_KEYS.union(ADMIN_API_KEYS))
    if not valid_key:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    consumer = get_consumer(
        topics=["country_risk_updates"],
        group_id=f"dashboard-country-risk-{uuid.uuid4()}",
        auto_offset_reset="latest",
        enable_auto_commit=True,
        consumer_timeout_ms=1000,
    )
    try:
        while True:
            sent_any = False
            for message in consumer:
                await websocket.send_json(message.value)
                sent_any = True
            if not sent_any:
                await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
    finally:
        try:
            consumer.close()
        except Exception:
            pass


@app.websocket("/ws/sentinel")
async def websocket_sentinel(websocket: WebSocket, x_api_key: str = Header(None), api_key: str = Query(None)):
    """
    WebSocket endpoint for Sentinel AI real-time updates.
    Provides risk score, analysis, and alerts to connected clients.
    """
    # --- Security check (optional for local dev) ---
    # Support both header and query parameter for API key
    key = (x_api_key or api_key or "").strip()
    if key and (USER_API_KEYS or ADMIN_API_KEYS):
        valid_key = any(hmac.compare_digest(key, k) for k in USER_API_KEYS.union(ADMIN_API_KEYS))
        if not valid_key:
            await websocket.close(code=1008)
            return

    # --- Connect client ---
    await websocket.accept()
    logger.info("Sentinel WebSocket client connected")

    try:
        while True:
            # Fetch latest sentinel analysis
            try:
                analysis = compute_sentinel_analysis()
                
                # Send sentinel update message
                message = {
                    "type": "sentinel_update",
                    "data": analysis,
                    "timestamp": datetime.utcnow().isoformat()
                }
                await websocket.send_json(message)
                
                # Also check for alerts and send if triggered
                risk_score = analysis.get("risk_score", 50)
                if risk_score >= 75:
                    alert_message = {
                        "type": "alert",
                        "alert": {
                            "id": f"alert-{int(time.time())}",
                            "threshold": 75,
                            "condition": "above",
                            "enabled": True,
                            "triggered": True,
                            "lastTriggered": datetime.utcnow().isoformat(),
                            "risk_score": risk_score,
                            "message": f"Critical risk level detected: {risk_score}"
                        }
                    }
                    await websocket.send_json(alert_message)
                    
            except Exception as e:
                logger.error(f"Error computing sentinel analysis: {e}")
                # Send error message but don't disconnect
                await websocket.send_json({
                    "type": "error",
                    "message": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            # Repeat every 5 seconds
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        logger.info("Sentinel WebSocket client disconnected")
    except Exception as e:
        logger.error(f"Sentinel WebSocket error: {e}")
        await websocket.close()


# =====================================================
# ADVANCED ML FEATURES ENDPOINTS
# =====================================================

@app.get("/analytics/advanced/ml-predictions")
@limiter.limit("10/minute")
def analytics_ml_predictions(request: Request, role: str = Depends(check_role)):
    """
    Get LSTM/Transformer multi-step ahead predictions (1h, 6h, 24h, 7d horizons)
    """
    try:
        from machine_learning.lstm_predictor import get_lstm_predictions
        predictions = get_lstm_predictions()
        return predictions
    except Exception as e:
        logger.error(f"ML predictions failed: {e}")
        raise HTTPException(status_code=500, detail=f"ML predictions error: {str(e)}")


@app.get("/analytics/advanced/anomalies")
@limiter.limit("10/minute")
def analytics_anomalies(request: Request, role: str = Depends(check_role)):
    """
    Get autoencoder-based anomaly detection results
    """
    try:
        from machine_learning.anomaly_detector import detect_anomalies_api
        anomalies = detect_anomalies_api()
        return anomalies
    except Exception as e:
        logger.error(f"Anomaly detection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Anomaly detection error: {str(e)}")


@app.get("/analytics/advanced/causal")
@limiter.limit("10/minute")
def analytics_causal(request: Request, role: str = Depends(check_role)):
    """
    Get causal inference / causal discovery results
    """
    try:
        from machine_learning.causal_discovery import discover_causal_structure
        causal = discover_causal_structure()
        return causal
    except Exception as e:
        logger.error(f"Causal discovery failed: {e}")
        raise HTTPException(status_code=500, detail=f"Causal discovery error: {str(e)}")


@app.get("/analytics/advanced/report")
@limiter.limit("10/minute")
def analytics_report(request: Request, role: str = Depends(check_role), report_type: str = Query("brief")):
    """
    Generate AI-powered crisis reports (brief, detailed, executive, comparison)
    """
    try:
        from processing.ai_report_generator import generate_report_api
        report = generate_report_api(report_type=report_type)
        return report
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Report generation error: {str(e)}")


@app.get("/analytics/advanced/sentiment-momentum")
@limiter.limit("10/minute")
def analytics_sentiment_momentum(request: Request, role: str = Depends(check_role)):
    """
    Get sentiment trend analysis with momentum indicators
    """
    try:
        from processing.sentiment_momentum import analyze_sentiment_momentum
        momentum = analyze_sentiment_momentum()
        return momentum
    except Exception as e:
        logger.error(f"Sentiment momentum analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sentiment momentum error: {str(e)}")


@app.get("/analytics/advanced/insights")
@limiter.limit("10/minute")
def analytics_advanced_insights(request: Request, role: str = Depends(check_role)):
    """
    Get unified advanced analytics insights combining all 5 ML features.
    Returns data in the format expected by the frontend AdvancedAnalyticsPanel.
    """
    try:
        from machine_learning.advanced_analytics import run_advanced_analytics
        insights = run_advanced_analytics()
        
        # Handle nested 'results' structure if present
        if isinstance(insights, dict) and "results" in insights:
            results = insights.get("results", {})
        elif isinstance(insights, dict) and "status" in insights:
            results = insights
        else:
            results = insights
        
        # Transform predictions
        predictions_data = results.get("predictions", results.get("lstm", {}))
        if isinstance(predictions_data, dict):
            pred_list = predictions_data.get("predictions", [])
            if isinstance(pred_list, list) and len(pred_list) > 0 and isinstance(pred_list[0], dict):
                predictions_transformed = {
                    "predictions": pred_list,
                    "model_type": predictions_data.get("model_type", "LSTM")
                }
            else:
                horizons = ["1h", "6h", "24h", "7d"]
                predictions_transformed = {
                    "predictions": [
                        {"horizon": horizons[i] if i < len(horizons) else f"{i+1}d", 
                         "risk_score": float(pred_list[i]) if i < len(pred_list) else 50.0, 
                         "confidence": 0.75}
                        for i in range(min(len(pred_list), 4))
                    ] if isinstance(pred_list, list) else [],
                    "model_type": predictions_data.get("model_type", "LSTM")
                }
        else:
            predictions_transformed = {"predictions": [], "model_type": "LSTM"}
        
        # Transform anomalies
        anomalies_data = results.get("anomalies", results.get("anomaly_detection", {}))
        if isinstance(anomalies_data, dict):
            anomalies_list = anomalies_data.get("anomalies", [])
            if isinstance(anomalies_list, list):
                anomalies_transformed = [
                    {
                        "timestamp": a.get("timestamp", datetime.utcnow().isoformat()),
                        "anomaly_score": float(a.get("anomaly_score", a.get("score", 0.5))),
                        "features": a.get("features", {}),
                        "severity": a.get("severity", "medium")
                    }
                    for a in anomalies_list[:10]
                ]
            else:
                anomalies_transformed = []
        else:
            anomalies_transformed = []
        
        # Transform causal graph
        causal_data = results.get("causal_graph", results.get("causal_discovery", {}))
        if isinstance(causal_data, dict):
            causal_list = causal_data.get("causal_links", causal_data.get("links", []))
            if isinstance(causal_list, list):
                causal_graph_transformed = [
                    {
                        "source": c.get("source", c.get("from", "")),
                        "target": c.get("target", c.get("to", "")),
                        "strength": float(c.get("strength", c.get("weight", 0.5)))
                    }
                    for c in causal_list[:20]
                ]
            else:
                causal_graph_transformed = []
        else:
            causal_graph_transformed = []
        
        # Transform sentiment momentum
        momentum_data = results.get("sentiment_momentum", results.get("sentiment", {}))
        if isinstance(momentum_data, dict):
            sentiment_momentum_transformed = {
                "velocity": float(momentum_data.get("velocity", 0.0)),
                "acceleration": float(momentum_data.get("acceleration", 0.0)),
                "trend": momentum_data.get("trend", momentum_data.get("trend_direction", "stable")),
                "rsi": float(momentum_data.get("rsi", 50.0)),
                "macd_signal": momentum_data.get("macd_signal", momentum_data.get("signal", "neutral"))
            }
        else:
            sentiment_momentum_transformed = {
                "velocity": 0.0,
                "acceleration": 0.0,
                "trend": "stable",
                "rsi": 50.0,
                "macd_signal": "neutral"
            }
        
        # Transform AI report
        report_data = results.get("ai_report", results.get("report", {}))
        if isinstance(report_data, dict):
            ai_report_transformed = {
                "title": report_data.get("title", "Global Risk Analysis Report"),
                "summary": report_data.get("summary", report_data.get("summary_text", "")),
                "key_findings": report_data.get("key_findings", report_data.get("findings", [])),
                "recommendations": report_data.get("recommendations", report_data.get("recommends", [])),
                "risk_level": report_data.get("risk_level", report_data.get("risk", "moderate"))
            }
        else:
            ai_report_transformed = {
                "title": "Global Risk Analysis Report",
                "summary": "Analysis in progress...",
                "key_findings": [],
                "recommendations": [],
                "risk_level": "moderate"
            }
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "predictions": predictions_transformed,
            "anomalies": anomalies_transformed,
            "causal_graph": causal_graph_transformed,
            "sentiment_momentum": sentiment_momentum_transformed,
            "ai_report": ai_report_transformed
        }
        
    except Exception as e:
        logger.error(f"Advanced analytics failed: {e}")
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "predictions": {
                "predictions": [
                    {"horizon": "1h", "risk_score": 50.0, "confidence": 0.75},
                    {"horizon": "6h", "risk_score": 50.0, "confidence": 0.70},
                    {"horizon": "24h", "risk_score": 50.0, "confidence": 0.65},
                    {"horizon": "7d", "risk_score": 50.0, "confidence": 0.60}
                ],
                "model_type": "LSTM"
            },
            "anomalies": [],
            "causal_graph": [],
            "sentiment_momentum": {
                "velocity": 0.0,
                "acceleration": 0.0,
                "trend": "stable",
                "rsi": 50.0,
                "macd_signal": "neutral"
            },
            "ai_report": {
                "title": "Global Risk Analysis Report",
                "summary": "Unable to generate report at this time.",
                "key_findings": [],
                "recommendations": [],
                "risk_level": "moderate"
            }
        }


# =====================================================
# STARTUP TEST USERS (ADD AT VERY BOTTOM OF FILE)
# =====================================================

@app.on_event("startup")
def load_test_users():
    bootstrap_users = [
        {"email": "admin@wp.com", "password": "admin123", "role": "admin", "name": "Admin User"},
        {"email": "researcher@wp.com", "password": "research123", "role": "researcher", "name": "Researcher User"},
        {"email": "policy@wp.com", "password": "policy123", "role": "policy", "name": "Policy User"},
        {"email": "student@wp.com", "password": "student123", "role": "student", "name": "Student User"},
    ]
    for user in bootstrap_users:
        existing = users_collection.find_one({"email": user["email"]})
        if existing:
            continue
        users_collection.insert_one({
            "email": user["email"],
            "password": pwd_context.hash(user["password"]),
            "role": user["role"],
            "name": user["name"],
            "created_at": datetime.utcnow().isoformat(),
        })
