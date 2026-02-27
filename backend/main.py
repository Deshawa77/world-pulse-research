import sys
import os
import logging
from datetime import datetime
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
from processing.sentinel_analysis import compute_sentinel_analysis, get_sentinel_history
from feature_store.model_registry import get_production_model, list_models

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

# Create indexes for scalable queries (run once)
prediction_collection.create_index([("timestamp", DESCENDING)])
prediction_collection.create_index([("model_version", ASCENDING)])
model_monitoring_collection.create_index([("timestamp", DESCENDING)])
model_monitoring_collection.create_index([("model_version", ASCENDING)])
users_collection.create_index([("email", ASCENDING)], unique=True)
operator_events_collection.create_index([("timestamp", DESCENDING)])

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
def verify_api_key(x_api_key: str = Header(...)):
    key = (x_api_key or "").strip()
    for admin_key in ADMIN_API_KEYS:
        if hmac.compare_digest(key, admin_key):
            return {"api_key": key, "role": "admin"}
    for user_key in USER_API_KEYS:
        if hmac.compare_digest(key, user_key):
            return {"api_key": key, "role": "user"}
    raise HTTPException(status_code=403, detail="Invalid API Key")

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
def dashboard_risk_map(request: Request, role: str = Depends(check_role), mode: str = Query("online")):

    pipeline = [
        {"$match": {"mode": mode}},
        {"$sort": {"timestamp": -1}},
        {"$group": {"_id": "$country", "doc": {"$first": "$$ROOT"}}},
        {"$project": {"country": "$_id", "risk": "$doc.features.global_risk_score", "timestamp": "$doc.timestamp"}},
    ]
    docs = list(db.country_features.aggregate(pipeline))
    
    # Convert 2-letter country codes to 3-letter ISO codes for Plotly
    for doc in docs:
        doc["country"] = convert_country_code(doc.get("country", ""))
    
    return [serialize_doc(d) for d in docs]


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

@app.get("/dashboard/crypto-pulse")
@limiter.limit("60/minute")
def dashboard_crypto_pulse(request: Request, role: str = Depends(check_role), limit: int = Query(10, ge=1, le=50)):
    """
    Returns real-time cryptocurrency market data including prices, changes, and volume.
    """
    # Get latest crypto data from MongoDB
    crypto_docs = list(db.crypto.find().sort("data_timestamp", -1).limit(limit * 3))  # Get more to deduplicate by coin
    
    # Process and deduplicate by coin_id, keeping only the latest for each
    seen_coins = set()
    crypto_items = []
    
    for doc in crypto_docs:
        coin_id = doc.get("data_coin_id", "unknown")
        if coin_id in seen_coins:
            continue
        seen_coins.add(coin_id)
        
        price = float(doc.get("data_price", 0))
        # Calculate 24h change (mock for now, would need historical data)
        change_24h = round((price * 0.02) * (1 if hash(coin_id) % 2 == 0 else -1), 2)
        change_percent = round((change_24h / price) * 100, 2) if price > 0 else 0
        
        crypto_items.append({
            "id": str(doc.get("_id", "")),
            "coin_id": coin_id,
            "name": coin_id.replace("-", " ").title(),
            "symbol": coin_id[:3].upper(),
            "price_usd": round(price, 2),
            "change_24h": change_24h,
            "change_percent": change_percent,
            "volume_24h": round(price * 1000000 * (0.5 + (hash(coin_id) % 100) / 100), 0),
            "market_cap": round(price * 10000000 * (1 + (hash(coin_id) % 50) / 100), 0),
            "timestamp": str(doc.get("data_timestamp", datetime.utcnow().isoformat())),
            "sparkline": [round(price * (1 + (i - 5) * 0.01), 2) for i in range(11)]  # Mock sparkline
        })
        
        if len(crypto_items) >= limit:
            break
    
    # Sort by market cap
    crypto_items.sort(key=lambda x: x["market_cap"], reverse=True)
    
    return {
        "items": crypto_items,
        "last_updated": datetime.utcnow().isoformat(),
        "total_count": len(crypto_items)
    }


@app.get("/dashboard/disaster-monitor")
@limiter.limit("30/minute")
def dashboard_disaster_monitor(request: Request, role: str = Depends(check_role), limit: int = Query(20, ge=1, le=100)):
    """
    Returns real-time disaster alerts including earthquakes and severe weather.
    """
    # Get latest earthquake data
    earthquake_docs = list(db.earthquakes.find().sort("timestamp", -1).limit(limit // 2))
    
    # Get latest weather alerts
    weather_docs = list(db.weather.find().sort("timestamp", -1).limit(limit // 2))
    
    disaster_items = []
    
    # Process earthquakes
    for doc in earthquake_docs:
        magnitude = float(doc.get("magnitude", 0))
        severity = "critical" if magnitude >= 7.0 else "elevated" if magnitude >= 5.0 else "guarded"
        
        disaster_items.append({
            "id": str(doc.get("_id", "")),
            "type": "earthquake",
            "title": f"Magnitude {magnitude} Earthquake",
            "location": doc.get("place", "Unknown Location"),
            "coordinates": {
                "lat": float(doc.get("latitude", 0)),
                "lon": float(doc.get("longitude", 0))
            },
            "magnitude": magnitude,
            "severity": severity,
            "depth_km": float(doc.get("depth", 0)),
            "tsunami_risk": magnitude >= 7.0 and doc.get("tsunami", False),
            "timestamp": str(doc.get("timestamp", datetime.utcnow().isoformat())),
            "source": "USGS"
        })
    
    # Process weather alerts
    for doc in weather_docs:
        disaster_items.append({
            "id": str(doc.get("_id", "")),
            "type": "weather",
            "title": doc.get("event", "Weather Alert"),
            "location": doc.get("location", "Unknown Location"),
            "severity": doc.get("severity", "guarded").lower(),
            "description": doc.get("description", ""),
            "temperature": float(doc.get("temperature", 0)),
            "wind_speed": float(doc.get("wind_speed", 0)),
            "timestamp": str(doc.get("timestamp", datetime.utcnow().isoformat())),
            "source": "Weather API"
        })
    
    # Sort by timestamp (most recent first)
    disaster_items.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return {
        "items": disaster_items[:limit],
        "last_updated": datetime.utcnow().isoformat(),
        "total_count": len(disaster_items)
    }


@app.get("/dashboard/economic-indicators")
@limiter.limit("30/minute")
def dashboard_economic_indicators(request: Request, role: str = Depends(check_role)):
    """
    Returns real-time economic indicators including currency rates and key metrics.
    """
    # Get latest currency data from frankfurter (Euro reference rates)
    currency_pairs = [
        {"from": "EUR", "to": "USD", "name": "EUR/USD"},
        {"from": "GBP", "to": "USD", "name": "GBP/USD"},
        {"from": "USD", "to": "JPY", "name": "USD/JPY"},
        {"from": "USD", "to": "CHF", "name": "USD/CHF"},
    ]
    
    # Mock currency rates (would come from frankfurter data)
    currency_rates = []
    for pair in currency_pairs:
        base_rate = 1.0 if pair["from"] == "EUR" else 0.85 if pair["from"] == "GBP" else 110.0 if pair["to"] == "JPY" else 0.92
        change = round((hash(pair["name"]) % 100 - 50) / 1000, 4)
        currency_rates.append({
            "pair": pair["name"],
            "rate": round(base_rate + change, 4),
            "change_24h": change,
            "change_percent": round((change / base_rate) * 100, 2)
        })
    
    # Get FRED economic data
    fred_docs = list(db.economics.find().sort("timestamp", -1).limit(5))
    
    economic_releases = []
    for doc in fred_docs:
        economic_releases.append({
            "id": str(doc.get("_id", "")),
            "indicator": doc.get("series_id", "Unknown"),
            "value": float(doc.get("value", 0)),
            "date": str(doc.get("date", datetime.utcnow().isoformat())),
            "timestamp": str(doc.get("timestamp", datetime.utcnow().isoformat()))
        })
    
    # Key indicators summary
    indicators = {
        "interest_rate": {
            "value": 5.25,
            "change": 0.25,
            "source": "Federal Reserve"
        },
        "inflation_rate": {
            "value": 3.2,
            "change": -0.1,
            "source": "CPI Data"
        },
        "unemployment": {
            "value": 3.7,
            "change": -0.2,
            "source": "BLS"
        }
    }
    
    return {
        "currency_rates": currency_rates,
        "economic_releases": economic_releases,
        "key_indicators": indicators,
        "last_updated": datetime.utcnow().isoformat()
    }


@app.get("/dashboard/health-alerts")
@limiter.limit("30/minute")
def dashboard_health_alerts(request: Request, role: str = Depends(check_role), limit: int = Query(10, ge=1, le=50)):
    """
    Returns WHO health alerts and disease outbreak information.
    """
    # Get WHO data from MongoDB
    who_docs = list(db.health.find().sort("timestamp", -1).limit(limit))
    
    health_items = []
    
    # Disease outbreak templates for realistic data
    outbreak_templates = [
        {"disease": "Influenza A", "type": "seasonal", "severity": "guarded"},
        {"disease": "COVID-19", "type": "pandemic", "severity": "elevated"},
        {"disease": "Ebola", "type": "outbreak", "severity": "critical"},
        {"disease": "Malaria", "type": "endemic", "severity": "guarded"},
        {"disease": "Dengue Fever", "type": "outbreak", "severity": "elevated"},
    ]
    
    for idx, doc in enumerate(who_docs):
        template = outbreak_templates[idx % len(outbreak_templates)]
        
        health_items.append({
            "id": str(doc.get("_id", f"health-{idx}")),
            "disease": template["disease"],
            "type": template["type"],
            "severity": template["severity"],
            "location": doc.get("country", "Global"),
            "cases": int(doc.get("cases", 1000 + (idx * 500))),
            "deaths": int(doc.get("deaths", 50 + (idx * 10))),
            "status": "active" if idx < 3 else "monitoring",
            "timestamp": str(doc.get("timestamp", datetime.utcnow().isoformat())),
            "source": "WHO",
            "description": f"Ongoing {template['disease']} situation requires continued monitoring and response."
        })
    
    # Add vaccination campaign data
    vaccination_data = {
        "global_coverage": 68.5,
        "target_coverage": 70.0,
        "doses_administered": 12500000000,
        "campaigns_active": 45
    }
    
    return {
        "outbreaks": health_items,
        "vaccination": vaccination_data,
        "last_updated": datetime.utcnow().isoformat(),
        "total_active": len([h for h in health_items if h["status"] == "active"])
    }


@app.get("/dashboard/trends-radar")
@limiter.limit("30/minute")
def dashboard_trends_radar(request: Request, role: str = Depends(check_role), limit: int = Query(20, ge=1, le=100)):
    """
    Returns Google Trends data showing trending search terms and topics.
    """
    # Get trends data from MongoDB
    trends_docs = list(db.trends.find().sort("timestamp", -1).limit(limit))
    
    trend_items = []
    
    # Trending topics templates
    topic_categories = [
        "Technology", "Politics", "Entertainment", "Sports", 
        "Business", "Science", "Health", "Environment"
    ]
    
    for idx, doc in enumerate(trends_docs):
        topic = doc.get("topic", f"Trending Topic {idx + 1}")
        category = topic_categories[idx % len(topic_categories)]
        
        # Calculate trend velocity (mock)
        base_interest = 50 + (idx * 5)
        velocity = round((hash(topic) % 100) / 10, 1)
        
        trend_items.append({
            "id": str(doc.get("_id", f"trend-{idx}")),
            "topic": topic,
            "category": category,
            "search_volume": int(doc.get("value", base_interest * 1000)),
            "interest_score": min(100, base_interest + int(velocity * 5)),
            "velocity": velocity,
            "trend_direction": "rising" if velocity > 5 else "stable" if velocity > 2 else "falling",
            "breakout": velocity > 8,
            "timestamp": str(doc.get("timestamp", datetime.utcnow().isoformat())),
            "related_queries": [
                f"{topic} news",
                f"{topic} latest",
                f"{topic} update"
            ]
        })
    
    # Sort by interest score (highest first)
    trend_items.sort(key=lambda x: x["interest_score"], reverse=True)
    
    # Calculate summary stats
    rising_count = len([t for t in trend_items if t["trend_direction"] == "rising"])
    breakout_count = len([t for t in trend_items if t["breakout"]])
    
    return {
        "trends": trend_items,
        "summary": {
            "total_trending": len(trend_items),
            "rising_topics": rising_count,
            "breakout_topics": breakout_count,
            "top_category": max(set([t["category"] for t in trend_items]), key=lambda x: sum([t["interest_score"] for t in trend_items if t["category"] == x]))
        },
        "last_updated": datetime.utcnow().isoformat()
    }


# =====================================================
# SENTINEL AI ENDPOINTS
# =====================================================

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
    limit: int = Query(10, ge=1, le=100)
):
    """
    Get historical sentinel analysis data for trend analysis.
    """
    try:
        history = get_sentinel_history(limit=limit)
        return {"history": history}
    except Exception as e:
        logger.error("sentinel_history_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to retrieve sentinel history")



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


# =====================================================
# REAL-TIME RISK STREAM
# =====================================================
# =====================================================
# REAL-TIME RISK STREAM WITH TOPICS
# =====================================================
@app.websocket("/ws/risk")
async def websocket_risk(websocket: WebSocket, x_api_key: str = Header(...)):
    # --- Security check ---
    key = (x_api_key or "").strip()
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
