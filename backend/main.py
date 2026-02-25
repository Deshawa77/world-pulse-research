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
        v = value.replace("Z", "+00:00")
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
