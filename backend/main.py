import sys
import os
import logging
from datetime import datetime, timezone
import re
import asyncio
import time
import threading
import platform
import uuid
import hmac
import csv
import io
import json
from urllib import request as urllib_request, error as urllib_error, parse as urllib_parse
from dotenv import load_dotenv
from typing import Literal, Any, Optional

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
from processing.global_mood import compute_global_operational_features
from processing.country_daily_risk import country_daily_refresh_if_due
from collectors.country_news import get_country_catalog
from processing.sentinel_analysis import compute_sentinel_analysis, get_sentinel_history
from processing.causal_risk_navigator import build_causal_explanation
from processing.counterfactual_engine import run_counterfactual
from processing.action_recommender import build_action_plan
from processing.policy_replay import run_policy_replay
from processing.country_risk_validation import (
    latest_country_risk_validation,
    run_country_risk_validation,
    list_country_risk_validation_history,
    run_country_risk_backtest,
    latest_country_risk_backtest,
    list_country_risk_backtests,
)
from processing.global_mood_validation import (
    latest_global_mood_validation,
    run_global_mood_validation,
    list_global_mood_validation_history,
    run_global_mood_backtest,
    latest_global_mood_backtest,
    list_global_mood_backtests,
)
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
ADMIN_INVITE_CODE = (os.environ.get("ADMIN_INVITE_CODE") or "").strip().strip('\"').strip("'")

ROLE_ADMIN = "admin"
ROLE_USER = "user"
DEFAULT_USER_TYPE = "researcher"
VALID_ROLES = {ROLE_ADMIN, ROLE_USER}
VALID_USER_TYPES = {"researcher", "policy", "student", "developer"}
LEGACY_USER_TYPE_MAP = {
    "researcher": "researcher",
    "analyst": "researcher",
    "policy": "policy",
    "ngo": "policy",
    "student": "student",
    "educator": "student",
    "developer": "developer",
    "admin": "developer",
}

# =====================================================
# FastAPI app and rate limiter
# =====================================================
app = FastAPI(title="World Pulse Secure API")
logger = build_logger("world_pulse.api")
runtime_metrics = RuntimeMetrics()
security_metrics_lock = threading.Lock()
security_metrics_started_at = datetime.now(timezone.utc)
security_metrics_counters = defaultdict(int)

SECURITY_WINDOW_MINUTES = 15
FAILED_LOGIN_SUSPICIOUS_THRESHOLD = 5
JWT_FAILURE_SUSPICIOUS_THRESHOLD = 8

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
country_features_collection = db["country_features"]
global_features_collection = db["global_features"]
dashboard_features_collection = db["dashboard_features"]
earthquakes_collection = db["earthquakes"]
weather_collection = db["weather"]
economics_collection = db["economics"]
health_collection = db["health"]
trends_collection = db["trends"]
security_events_collection = db["security_events"]
causal_explanations_collection = db["causal_explanations"]
counterfactual_runs_collection = db["counterfactual_runs"]
policy_replays_collection = db["policy_replays"]
action_recommendations_collection = db["action_recommendations"]
# Create indexes for scalable queries (run once)
prediction_collection.create_index([("timestamp", DESCENDING)])
prediction_collection.create_index([("model_version", ASCENDING)])
model_monitoring_collection.create_index([("timestamp", DESCENDING)])
model_monitoring_collection.create_index([("model_version", ASCENDING)])
users_collection.create_index([("email", ASCENDING)], unique=True)
users_collection.create_index([("role", ASCENDING)])
users_collection.create_index([("user_type", ASCENDING)])
users_collection.create_index([("active", ASCENDING)])
operator_events_collection.create_index([("timestamp", DESCENDING)])
sentinel_feedback_collection.create_index([("timestamp", DESCENDING)])
operator_events_collection.create_index([("country", ASCENDING), ("timestamp", DESCENDING)])
country_features_collection.create_index([("mode", ASCENDING), ("timestamp", DESCENDING)])
country_features_collection.create_index([("country", ASCENDING), ("mode", ASCENDING), ("timestamp", DESCENDING)])
global_features_collection.create_index([("mode", ASCENDING), ("timestamp", DESCENDING)])
dashboard_features_collection.create_index([("mode", ASCENDING), ("timestamp", DESCENDING)])
earthquakes_collection.create_index([("collected_at", DESCENDING)])
weather_collection.create_index([("data_timestamp", DESCENDING)])
economics_collection.create_index([("collected_at", DESCENDING)])
health_collection.create_index([("collected_at", DESCENDING)])
trends_collection.create_index([("collected_at", DESCENDING)])
security_events_collection.create_index([("timestamp", DESCENDING)])
security_events_collection.create_index([("event_type", ASCENDING), ("status", ASCENDING), ("timestamp", DESCENDING)])
security_events_collection.create_index([("email", ASCENDING), ("timestamp", DESCENDING)])
causal_explanations_collection.create_index([("country", ASCENDING), ("timestamp", DESCENDING)])
counterfactual_runs_collection.create_index([("country", ASCENDING), ("timestamp", DESCENDING)])
policy_replays_collection.create_index([("country", ASCENDING), ("timestamp", DESCENDING)])
action_recommendations_collection.create_index([("country", ASCENDING), ("timestamp", DESCENDING)])
security_events_collection.create_index([("client_ip", ASCENDING), ("timestamp", DESCENDING)])
# =====================================================
# Model Cache
# =====================================================
model_cache = {"model": None, "version": None}

# =====================================================
# USER STORE (MongoDB)
# =====================================================

fake_users_db = {}  # legacy fallback; auth now uses Mongo users collection


def normalize_role(raw_role: str | None) -> str:
    candidate = str(raw_role or "").strip().lower()
    return ROLE_ADMIN if candidate == ROLE_ADMIN else ROLE_USER


def normalize_user_type(raw_user_type: str | None, fallback_role: str | None = None) -> str:
    candidate = str(raw_user_type or "").strip().lower()
    if candidate in VALID_USER_TYPES:
        return candidate
    if candidate in LEGACY_USER_TYPE_MAP:
        return LEGACY_USER_TYPE_MAP[candidate]

    fallback = str(fallback_role or "").strip().lower()
    if fallback in VALID_USER_TYPES:
        return fallback
    if fallback in LEGACY_USER_TYPE_MAP:
        return LEGACY_USER_TYPE_MAP[fallback]

    return DEFAULT_USER_TYPE


def _sanitize_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def _default_user_type_for_role(role: str) -> str:
    return "developer" if role == ROLE_ADMIN else DEFAULT_USER_TYPE


def ensure_user_role_shape(user_doc: dict) -> tuple[str, str, bool]:
    if not user_doc:
        return ROLE_USER, DEFAULT_USER_TYPE, False

    source_role = str(user_doc.get("role") or "").strip().lower()
    normalized_role = normalize_role(source_role)
    normalized_user_type = normalize_user_type(user_doc.get("user_type"), source_role)

    updates = {}
    if str(user_doc.get("role") or "").strip().lower() != normalized_role:
        updates["role"] = normalized_role
    if str(user_doc.get("user_type") or "").strip().lower() != normalized_user_type:
        updates["user_type"] = normalized_user_type

    if updates and user_doc.get("_id") is not None:
        updates["updated_at"] = datetime.utcnow().isoformat()
        users_collection.update_one({"_id": user_doc["_id"]}, {"$set": updates})

    return normalized_role, normalized_user_type, bool(updates)


def ensure_user_active_shape(user_doc: dict) -> tuple[bool, bool]:
    if not user_doc:
        return True, False

    has_active = "active" in user_doc
    active = bool(user_doc.get("active", True))

    if not has_active and user_doc.get("_id") is not None:
        users_collection.update_one(
            {"_id": user_doc["_id"]},
            {"$set": {"active": True, "updated_at": datetime.utcnow().isoformat()}},
        )
        return True, True

    return active, False


def sanitize_user_document(user_doc: dict) -> dict:
    role, user_type, _ = ensure_user_role_shape(user_doc)
    active, _ = ensure_user_active_shape(user_doc)
    return {
        "id": str(user_doc.get("_id", "")),
        "email": str(user_doc.get("email") or ""),
        "name": str(user_doc.get("name") or ""),
        "organization": user_doc.get("organization"),
        "role": role,
        "user_type": user_type,
        "active": active,
        "deactivated_at": user_doc.get("deactivated_at"),
        "deactivated_by": user_doc.get("deactivated_by"),
        "created_at": user_doc.get("created_at"),
        "updated_at": user_doc.get("updated_at"),
    }


def _increment_security_metric(metric_name: str, amount: int = 1) -> None:
    with security_metrics_lock:
        security_metrics_counters[metric_name] += amount


def _security_metrics_snapshot() -> dict:
    with security_metrics_lock:
        return {
            "started_at": security_metrics_started_at.isoformat(),
            "login_success": int(security_metrics_counters.get("login_success", 0)),
            "login_failed": int(security_metrics_counters.get("login_failed", 0)),
            "login_blocked": int(security_metrics_counters.get("login_blocked", 0)),
            "suspicious_activity_events": int(security_metrics_counters.get("suspicious_activity_events", 0)),
            "jwt_issued": int(security_metrics_counters.get("jwt_issued", 0)),
            "jwt_validated_success": int(security_metrics_counters.get("jwt_validated_success", 0)),
            "jwt_validated_failed": int(security_metrics_counters.get("jwt_validated_failed", 0)),
        }


def _client_ip_from_request(request: Request | None) -> str | None:
    if request is None:
        return None

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None

    return request.client.host if request.client else None


def _record_security_event(
    event_type: str,
    status: str,
    detail: str,
    email: str | None = None,
    client_ip: str | None = None,
    meta: dict | None = None,
) -> None:
    event_doc = {
        "timestamp": datetime.utcnow(),
        "event_type": event_type,
        "status": status,
        "detail": detail,
        "email": email or None,
        "client_ip": client_ip or None,
        "meta": meta or {},
    }
    try:
        security_events_collection.insert_one(event_doc)
    except Exception as exc:
        logger.warning(
            "security_event_record_failed",
            extra={"event": {"event_type": event_type, "status": status, "error": str(exc)}},
        )

    if event_type == "suspicious_activity":
        _increment_security_metric("suspicious_activity_events")


def _has_recent_suspicious_event(detail: str, email: str | None, client_ip: str | None, minutes: int = 5) -> bool:
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    query = {
        "event_type": "suspicious_activity",
        "detail": detail,
        "timestamp": {"$gte": cutoff},
    }
    if email:
        query["email"] = email
    if client_ip:
        query["client_ip"] = client_ip
    return security_events_collection.count_documents(query) > 0


def _maybe_record_suspicious_failed_logins(email: str, client_ip: str | None) -> None:
    cutoff = datetime.utcnow() - timedelta(minutes=SECURITY_WINDOW_MINUTES)
    base_query = {
        "event_type": "login_attempt",
        "status": "failed",
        "timestamp": {"$gte": cutoff},
    }

    email_failed_count = 0
    if email:
        email_failed_count = security_events_collection.count_documents({**base_query, "email": email})

    ip_failed_count = 0
    if client_ip:
        ip_failed_count = security_events_collection.count_documents({**base_query, "client_ip": client_ip})

    if email and email_failed_count >= FAILED_LOGIN_SUSPICIOUS_THRESHOLD:
        detail = "Repeated failed login attempts for email"
        if not _has_recent_suspicious_event(detail, email=email, client_ip=client_ip):
            _record_security_event(
                "suspicious_activity",
                "warning",
                detail,
                email=email,
                client_ip=client_ip,
                meta={
                    "window_minutes": SECURITY_WINDOW_MINUTES,
                    "failed_attempts_for_email": email_failed_count,
                },
            )

    if client_ip and ip_failed_count >= FAILED_LOGIN_SUSPICIOUS_THRESHOLD:
        detail = "Repeated failed login attempts from IP"
        if not _has_recent_suspicious_event(detail, email=email, client_ip=client_ip):
            _record_security_event(
                "suspicious_activity",
                "warning",
                detail,
                email=email,
                client_ip=client_ip,
                meta={
                    "window_minutes": SECURITY_WINDOW_MINUTES,
                    "failed_attempts_for_ip": ip_failed_count,
                },
            )


def _maybe_record_suspicious_jwt_failures(client_ip: str | None) -> None:
    if not client_ip:
        return

    cutoff = datetime.utcnow() - timedelta(minutes=SECURITY_WINDOW_MINUTES)
    failed_count = security_events_collection.count_documents(
        {
            "event_type": "jwt_validation",
            "status": "failed",
            "client_ip": client_ip,
            "timestamp": {"$gte": cutoff},
        }
    )

    if failed_count >= JWT_FAILURE_SUSPICIOUS_THRESHOLD:
        detail = "Repeated JWT validation failures from IP"
        if not _has_recent_suspicious_event(detail, email=None, client_ip=client_ip):
            _record_security_event(
                "suspicious_activity",
                "warning",
                detail,
                client_ip=client_ip,
                meta={
                    "window_minutes": SECURITY_WINDOW_MINUTES,
                    "jwt_failed_attempts_for_ip": failed_count,
                },
            )


def _format_uptime(total_seconds: float) -> str:
    seconds = max(0, int(total_seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

# =====================================================
# Security: API Key / Bearer Verification
# =====================================================
def _identity_from_api_key(key: str | None):
    candidate = (key or "").strip()
    if not candidate:
        return None
    for admin_key in ADMIN_API_KEYS:
        if hmac.compare_digest(candidate, admin_key):
            return {
                "auth_type": "api_key",
                "api_key": candidate,
                "sub": "api-key-admin",
                "role": ROLE_ADMIN,
                "user_type": _default_user_type_for_role(ROLE_ADMIN),
            }
    for user_key in USER_API_KEYS:
        if hmac.compare_digest(candidate, user_key):
            return {
                "auth_type": "api_key",
                "api_key": candidate,
                "sub": "api-key-user",
                "role": ROLE_USER,
                "user_type": _default_user_type_for_role(ROLE_USER),
            }
    return None


def decode_access_token(token: str, request: Request | None = None, source: str = "bearer"):
    client_ip = _client_ip_from_request(request)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        subject = _sanitize_email(payload.get("sub"))
        if not subject:
            raise HTTPException(status_code=401, detail="Invalid token subject")

        user_doc = users_collection.find_one(
            {"email": subject},
            {"role": 1, "user_type": 1, "name": 1, "active": 1},
        )
        if not user_doc:
            raise HTTPException(status_code=401, detail="User not found")

        role, user_type, _ = ensure_user_role_shape(user_doc)
        active, _ = ensure_user_active_shape(user_doc)
        if not active:
            raise HTTPException(status_code=403, detail="User account is deactivated")

        name = str(user_doc.get("name") or payload.get("name") or "")
        _increment_security_metric("jwt_validated_success")

        return {
            "auth_type": "jwt",
            "sub": subject,
            "role": role,
            "user_type": user_type,
            "name": name,
        }
    except HTTPException as exc:
        _increment_security_metric("jwt_validated_failed")
        _record_security_event(
            "jwt_validation",
            "failed",
            str(exc.detail),
            client_ip=client_ip,
            meta={"source": source},
        )
        _maybe_record_suspicious_jwt_failures(client_ip)
        raise
    except Exception as exc:
        _increment_security_metric("jwt_validated_failed")
        _record_security_event(
            "jwt_validation",
            "failed",
            f"Invalid token: {exc}",
            client_ip=client_ip,
            meta={"source": source},
        )
        _maybe_record_suspicious_jwt_failures(client_ip)
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

def verify_api_key(request: Request, x_api_key: str | None = Header(None), authorization: str | None = Header(None)):
    bearer = (authorization or "").strip()
    if bearer.lower().startswith("bearer "):
        return decode_access_token(
            bearer.split(" ", 1)[1].strip(),
            request=request,
            source="authorization_header",
        )

    identity = _identity_from_api_key(x_api_key)
    if identity:
        return identity

    if x_api_key:
        _record_security_event(
            "api_key_auth",
            "failed",
            "Invalid API key",
            client_ip=_client_ip_from_request(request),
        )

    raise HTTPException(status_code=401, detail="Missing or invalid API key / bearer token")

# Role-Based Access Control
def check_role(identity: dict = Depends(verify_api_key)):
    return identity["role"]


def require_admin(role: str = Depends(check_role)):
    if role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access only")
    return role


def require_admin_identity(identity: dict = Depends(verify_api_key)):
    if normalize_role(identity.get("role")) != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access only")
    return identity

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

    token = jwt.encode(
        to_encode,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    _increment_security_metric("jwt_issued")
    return token


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

    # Fallback source used by orchestrator dashboard sync.
    if not doc:
        doc = db.dashboard_features.find_one({"mode": mode}, sort=[("_id", DESCENDING)])

    # Final safety fallback keeps frontend booting even before data arrives.
    if not doc:
        now = datetime.utcnow().isoformat()
        doc = {
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

    doc = serialize_doc(doc)
    features = dict(doc.get("features") or {})
    current_timestamp = features.get("timestamp") or doc.get("timestamp")
    current_risk = float(features.get("global_risk_score", 50.0) or 50.0)
    features.update(
        compute_global_operational_features(
            current_risk_score=current_risk,
            mode=mode,
            current_timestamp=current_timestamp,
            use_cache=True,
        )
    )
    doc["features"] = features
    return doc


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

class CounterfactualRequest(BaseModel):
    country: str | None = None
    scenario: dict[str, float]
    mode: str = "online"

class ActionPlanRequest(BaseModel):
    country: str | None = None
    mode: str = "online"
    max_actions: int = 4

class PolicyReplayRequest(BaseModel):
    country: str | None = None
    interventions: list[str] | None = None
    horizon_days: int = 30
    mode: str = "online"
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
            "global_mood_score": float(f.get("global_mood_score", 50.0)),
            "global_mood_confidence": float(f.get("global_mood_confidence", 0.0)),
            "global_mood_uncertainty": float(f.get("global_mood_uncertainty", 18.0)),
            "global_mood_verified_countries": int(f.get("global_mood_verified_countries", 0) or 0),
            "global_mood_eligible_countries": int(f.get("global_mood_eligible_countries", f.get("global_mood_verified_countries", 0)) or 0),
            "global_mood_used_countries": int(f.get("global_mood_used_countries", f.get("global_mood_contributing_countries", 0)) or 0),
            "global_mood_excluded_countries": int(f.get("global_mood_excluded_countries", 0) or 0),
            "forecast_risk_score": float(f.get("forecast_risk_score", f.get("global_risk_score", 50.0))),
            "forecast_risk_delta": float(f.get("forecast_risk_delta", 0.0)),
            "forecast_confidence": float(f.get("forecast_confidence", 0.0)),
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





WEATHER_CACHE_TTL_SECONDS = 600
_weather_cache: dict[str, dict[str, Any]] = {}


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed == parsed else fallback


def _weather_condition_label(code: int) -> str:
    labels = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        80: "Rain showers",
        81: "Moderate showers",
        82: "Violent showers",
        95: "Thunderstorm",
    }
    return labels.get(int(code), "Unknown conditions")


def _fetch_json(url: str, timeout: int = 12, headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
    req = urllib_request.Request(url, headers=headers or {})
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8", errors="replace")
    return json.loads(payload)


def _fetch_open_meteo_weather(lat: float, lon: float) -> dict[str, Any]:
    endpoint = "https://api.open-meteo.com/v1/forecast?" + urllib_parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,rain,wind_speed_10m,wind_gusts_10m,wind_direction_10m,weather_code",
        "timezone": "auto",
        "forecast_days": 1,
    })
    payload = _fetch_json(endpoint)
    current = payload.get("current") or {}
    code = int(round(_safe_float(current.get("weather_code"), 0.0)))
    return {
        "latitude": lat,
        "longitude": lon,
        "observedAt": str(current.get("time") or datetime.utcnow().isoformat()),
        "conditionCode": code,
        "conditionLabel": _weather_condition_label(code),
        "temperatureC": _safe_float(current.get("temperature_2m")),
        "feelsLikeC": _safe_float(current.get("apparent_temperature"), _safe_float(current.get("temperature_2m"))),
        "humidityPct": _safe_float(current.get("relative_humidity_2m")),
        "precipitationMm": _safe_float(current.get("precipitation")),
        "rainMm": _safe_float(current.get("rain")),
        "windSpeedKmh": _safe_float(current.get("wind_speed_10m")),
        "windGustKmh": _safe_float(current.get("wind_gusts_10m"), _safe_float(current.get("wind_speed_10m"))),
        "windDirectionDeg": _safe_float(current.get("wind_direction_10m")),
        "provider": "open-meteo",
    }


def _fetch_met_no_weather(lat: float, lon: float) -> dict[str, Any]:
    endpoint = "https://api.met.no/weatherapi/locationforecast/2.0/compact?" + urllib_parse.urlencode({"lat": lat, "lon": lon})
    payload = _fetch_json(endpoint, headers={"User-Agent": "world-pulse-research/1.0"})
    ts = ((payload.get("properties") or {}).get("timeseries") or [{}])[0]
    details = (((ts.get("data") or {}).get("instant") or {}).get("details") or {})
    next_hour = ((ts.get("data") or {}).get("next_1_hours") or {})
    symbol = (((next_hour.get("summary") or {}).get("symbol_code") or "") + "").replace("_", " ").strip().title() or "Unknown conditions"
    precipitation = _safe_float(((next_hour.get("details") or {}).get("precipitation_amount")), 0.0)
    wind_speed_kmh = _safe_float(details.get("wind_speed"), 0.0) * 3.6
    temp = _safe_float(details.get("air_temperature"))
    return {
        "latitude": lat,
        "longitude": lon,
        "observedAt": str(ts.get("time") or datetime.utcnow().isoformat()),
        "conditionCode": -1,
        "conditionLabel": symbol,
        "temperatureC": temp,
        "feelsLikeC": temp,
        "humidityPct": _safe_float(details.get("relative_humidity")),
        "precipitationMm": precipitation,
        "rainMm": precipitation,
        "windSpeedKmh": wind_speed_kmh,
        "windGustKmh": wind_speed_kmh,
        "windDirectionDeg": _safe_float(details.get("wind_from_direction")),
        "provider": "met-no",
    }


def _weather_cache_key(country: Optional[str], lat: float, lon: float) -> str:
    country_key = (country or "").upper().strip()
    return f"{country_key}:{round(lat, 3)}:{round(lon, 3)}"
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


@app.get("/dashboard/weather/current")
@limiter.limit("60/minute")
def dashboard_weather_current(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    country: Optional[str] = Query(default=None),
    force_refresh: bool = Query(default=False),
    role: str = Depends(check_role),
):
    cache_key = _weather_cache_key(country, lat, lon)
    now_ts = time.time()
    cached_entry = _weather_cache.get(cache_key)

    if cached_entry and not force_refresh and now_ts - float(cached_entry.get("timestamp", 0.0)) <= WEATHER_CACHE_TTL_SECONDS:
        payload = dict(cached_entry.get("payload") or {})
        payload["cached"] = True
        payload["cacheAgeSec"] = int(now_ts - float(cached_entry.get("timestamp", now_ts)))
        return payload

    last_error: str | None = None
    for attempt in range(3):
        try:
            payload = _fetch_open_meteo_weather(lat, lon)
            payload["cached"] = False
            payload["cacheAgeSec"] = 0
            _weather_cache[cache_key] = {"payload": payload, "timestamp": now_ts}
            return payload
        except Exception as exc:
            last_error = f"open-meteo: {exc}"
            try:
                payload = _fetch_met_no_weather(lat, lon)
                payload["cached"] = False
                payload["cacheAgeSec"] = 0
                _weather_cache[cache_key] = {"payload": payload, "timestamp": now_ts}
                return payload
            except Exception as fallback_exc:
                last_error = f"met-no: {fallback_exc}"
                if attempt < 2:
                    time.sleep(0.25 * (attempt + 1))

    if cached_entry:
        payload = dict(cached_entry.get("payload") or {})
        payload["cached"] = True
        payload["stale"] = True
        payload["cacheAgeSec"] = int(now_ts - float(cached_entry.get("timestamp", now_ts)))
        payload["warning"] = "Live weather temporarily unavailable. Returning last cached snapshot."
        return payload

    raise HTTPException(status_code=503, detail={"message": "Live weather temporarily unavailable", "provider_error": last_error})

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


@app.get("/dashboard/causal-explanations")
@limiter.limit("40/minute")
def dashboard_causal_explanations(
    request: Request,
    role: str = Depends(check_role),
    country: str | None = Query(default=None),
    mode: str = Query("online"),
):
    normalized_country = country.upper().strip() if country else None
    explanation = build_causal_explanation(country=normalized_country, mode=mode)

    causal_explanations_collection.insert_one({
        "timestamp": datetime.utcnow(),
        "country": normalized_country,
        "mode": mode,
        "payload": explanation,
    })
    return explanation


@app.post("/dashboard/counterfactual")
@limiter.limit("30/minute")
def dashboard_counterfactual(
    request: Request,
    payload: CounterfactualRequest,
    role: str = Depends(check_role),
):
    normalized_country = payload.country.upper().strip() if payload.country else None
    result = run_counterfactual(scenario=payload.scenario, country=normalized_country, mode=payload.mode)

    counterfactual_runs_collection.insert_one({
        "timestamp": datetime.utcnow(),
        "country": normalized_country,
        "mode": payload.mode,
        "scenario": payload.scenario,
        "payload": result,
    })
    return result


@app.post("/dashboard/action-plan")
@limiter.limit("30/minute")
def dashboard_action_plan(
    request: Request,
    payload: ActionPlanRequest,
    role: str = Depends(check_role),
):
    normalized_country = payload.country.upper().strip() if payload.country else None
    result = build_action_plan(country=normalized_country, mode=payload.mode, max_actions=max(1, min(payload.max_actions, 8)))

    action_recommendations_collection.insert_one({
        "timestamp": datetime.utcnow(),
        "country": normalized_country,
        "mode": payload.mode,
        "max_actions": payload.max_actions,
        "payload": result,
    })
    return result


@app.post("/dashboard/policy-replay")
@limiter.limit("30/minute")
def dashboard_policy_replay(
    request: Request,
    payload: PolicyReplayRequest,
    role: str = Depends(check_role),
):
    normalized_country = payload.country.upper().strip() if payload.country else None
    interventions = payload.interventions or []
    result = run_policy_replay(
        country=normalized_country,
        interventions=interventions,
        horizon_days=max(7, min(payload.horizon_days, 180)),
        mode=payload.mode,
    )

    policy_replays_collection.insert_one({
        "timestamp": datetime.utcnow(),
        "country": normalized_country,
        "mode": payload.mode,
        "horizon_days": payload.horizon_days,
        "interventions": interventions,
        "payload": result,
    })
    return result


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


def _extract_first_number(value: Any, default: float | None = None) -> float | None:
    """
    Parse first numeric token from strings like '47.2 [45.3-49.1]'.
    """
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return default
    try:
        return float(match.group(0))
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
    query_limit = max(limit * 96, 240)
    crypto_docs = list(db.crypto.find().sort("data_timestamp", -1).limit(query_limit))
    price_history_by_coin: dict[str, list[dict]] = defaultdict(list)
    for doc in crypto_docs:
        coin_id = str(_pick_nested(doc, "data_coin_id", "data.coin_id", "data.coin", "coin_id", default="unknown"))
        if coin_id:
            price_history_by_coin[coin_id].append(doc)

    crypto_items = []

    for coin_id, docs in price_history_by_coin.items():
        unique_docs = []
        seen_timestamps = set()
        for doc in docs:
            timestamp_key = _safe_timestamp(doc, "data_timestamp", "data.timestamp", "timestamp", "collected_at")
            if timestamp_key in seen_timestamps:
                continue
            seen_timestamps.add(timestamp_key)
            unique_docs.append(doc)

        if not unique_docs:
            continue

        latest_doc = unique_docs[0]
        price_points = [
            _safe_float(_pick_nested(doc, "data_price", "data.price", "price", default=0.0))
            for doc in unique_docs
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
        coin_name = str(_pick_nested(latest_doc, "data_name", "data.name", "name", default=coin_id.replace("-", " ").title()))
        coin_symbol = str(_pick_nested(latest_doc, "data_symbol", "data.symbol", "symbol", default=coin_id[:4].upper())).upper()

        crypto_items.append({
            "id": str(latest_doc.get("_id", "")),
            "coin_id": coin_id,
            "name": coin_name,
            "symbol": coin_symbol,
            "price_usd": price,
            "change_24h": change_24h,
            "change_percent": change_percent,
            "volume_24h": round(observed_volume, 0),
            "market_cap": round(observed_market_cap, 0),
            "timestamp": _safe_timestamp(latest_doc, "data_timestamp", "data.timestamp", "timestamp", "collected_at"),
            "sparkline": [round(point, 2) for point in sparkline_points],
        })

    total_available = len(crypto_items)
    crypto_items.sort(
        key=lambda item: (_parse_timestamp(item["timestamp"]), item["market_cap"], item["price_usd"]),
        reverse=True,
    )
    crypto_items = crypto_items[:limit]

    return {
        "items": crypto_items,
        "last_updated": _latest_timestamp(*crypto_docs),
        "total_count": total_available,
    }


@app.get("/dashboard/disaster-monitor")
@limiter.limit("30/minute")
def dashboard_disaster_monitor(request: Request, role: str = Depends(check_role), limit: int = Query(20, ge=1, le=100)):
    """
    Returns real-time disaster alerts including earthquakes and severe weather.
    """
    half_limit = max(1, limit // 2)
    weather_quota = max(1, limit - half_limit)

    # Read enough rows from both collections.
    earthquake_pool = list(db.earthquakes.find().sort("collected_at", -1).limit(limit * 3))
    weather_pool = list(db.weather.find().sort("collected_at", -1).limit(limit * 3))

    # Prevent stale feeds from polluting live monitor cards.
    now_utc = datetime.now(timezone.utc)
    eq_cutoff = now_utc - timedelta(hours=48)
    weather_cutoff = now_utc - timedelta(hours=24)
    recent_earthquakes = [
        doc for doc in earthquake_pool
        if _parse_timestamp(_safe_timestamp(doc, "timestamp", "data.time", "collected_at")) >= eq_cutoff
    ]
    recent_weather = [
        doc for doc in weather_pool
        if _parse_timestamp(_safe_timestamp(doc, "timestamp", "data_timestamp", "data.date", "collected_at")) >= weather_cutoff
    ]

    selected_earthquakes = recent_earthquakes[:half_limit]
    selected_weather = recent_weather[:weather_quota]

    remaining = limit - (len(selected_earthquakes) + len(selected_weather))
    if remaining > 0:
        selected_earthquakes.extend(recent_earthquakes[len(selected_earthquakes): len(selected_earthquakes) + remaining])
        remaining = limit - (len(selected_earthquakes) + len(selected_weather))
    if remaining > 0:
        selected_weather.extend(recent_weather[len(selected_weather): len(selected_weather) + remaining])

    disaster_items = []

    # Process earthquakes
    for doc in selected_earthquakes:
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
    for doc in selected_weather:
        weather_text = str(_pick_nested(doc, "event", "data_weather", "data.weather", "data.description", default=""))
        temperature = _safe_float(_pick_nested(doc, "temperature", "data_temperature", "data.temperature", "data.temp", default=0.0))
        wind_speed = _safe_float(_pick_nested(doc, "wind_speed", "data_wind_speed", "data.wind_speed", default=0.0))
        city = str(_pick_nested(doc, "location", "data_city", "data.city", default="Unknown Location"))
        country = str(_pick_nested(doc, "country", "data_country", "data.country", default="")).strip()
        location = f"{city}, {country}" if country and country.lower() not in city.lower() else city

        severity = str(_pick_nested(doc, "severity", "data_severity", default="")).strip().lower()
        if severity not in {"critical", "elevated", "guarded"}:
            weather_lower = weather_text.lower()
            if wind_speed >= 100 or "hurricane" in weather_lower or "tornado" in weather_lower:
                severity = "critical"
            elif wind_speed >= 60 or any(token in weather_lower for token in ["storm", "flood", "blizzard"]):
                severity = "elevated"
            else:
                severity = "guarded"

        disaster_items.append({
            "id": str(doc.get("_id", "")),
            "type": "weather",
            "title": weather_text.title() if weather_text else "Weather Alert",
            "location": location,
            "severity": severity,
            "description": str(_pick_nested(doc, "description", "data_weather", "data.description", default=weather_text)),
            "temperature": temperature,
            "wind_speed": wind_speed,
            "timestamp": _safe_timestamp(doc, "timestamp", "data_timestamp", "data.date", "collected_at"),
            "source": str(doc.get("source", "Weather API"))
        })

    # Sort by timestamp (most recent first)
    disaster_items.sort(key=lambda x: _parse_timestamp(x["timestamp"]), reverse=True)

    return {
        "items": disaster_items[:limit],
        "last_updated": _latest_timestamp(*recent_earthquakes, *recent_weather),
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
    health_docs = list(db.health.find().sort("collected_at", -1).limit(limit))
    legacy_docs = list(db.who.find().sort("collected_at", -1).limit(limit * 3))

    primary_latest = (
        _parse_timestamp(_safe_timestamp(health_docs[0], "timestamp", "data.timestamp", "collected_at"))
        if health_docs
        else datetime.min.replace(tzinfo=timezone.utc)
    )
    legacy_latest = (
        _parse_timestamp(_safe_timestamp(legacy_docs[0], "timestamp", "data.timestamp", "collected_at"))
        if legacy_docs
        else datetime.min.replace(tzinfo=timezone.utc)
    )

    # Prefer fresher WHO stream data if it is newer than the health collection.
    if legacy_latest > primary_latest:
        health_docs = legacy_docs[:limit]
    elif len(health_docs) < limit and legacy_docs:
        seen_ids = {str(doc.get("_id", "")) for doc in health_docs}
        for doc in legacy_docs:
            doc_id = str(doc.get("_id", ""))
            if doc_id in seen_ids:
                continue
            health_docs.append(doc)
            seen_ids.add(doc_id)
            if len(health_docs) >= limit:
                break

    health_items = []
    for idx, doc in enumerate(health_docs):
        indicator = str(_pick_nested(doc, "data.indicator", "indicator", default="WHO Indicator"))
        cases_raw = _pick_nested(doc, "cases", "data.cases", default=None)
        deaths_raw = _pick_nested(doc, "deaths", "data.deaths", default=None)
        indicator_value_raw = _pick_nested(doc, "data.value", "value", default=None)

        cases = _safe_int(cases_raw, default=-1) if cases_raw not in (None, "") else -1
        deaths = _safe_int(deaths_raw, default=-1) if deaths_raw not in (None, "") else -1
        parsed_indicator_value = _extract_first_number(indicator_value_raw, default=None)
        has_outbreak_counts = cases >= 0 or deaths >= 0

        if has_outbreak_counts:
            safe_cases = max(cases, 0)
            severity = "critical" if safe_cases >= 100000 else "elevated" if safe_cases >= 10000 else "guarded"
            status = "active" if severity in {"critical", "elevated"} else "monitoring"
        else:
            safe_cases = None
            severity = "guarded"
            status = "monitoring"

        safe_deaths = None if deaths < 0 else max(deaths, 0)
        location = str(_pick_nested(doc, "country", "data.country", "data.SpatialDim", default="Global"))

        health_items.append({
            "id": str(doc.get("_id", f"health-{idx}")),
            "disease": indicator.replace("_", " "),
            "type": "indicator",
            "severity": severity,
            "location": location,
            "cases": safe_cases,
            "deaths": safe_deaths,
            "indicator_value": parsed_indicator_value,
            "indicator_value_raw": str(indicator_value_raw) if indicator_value_raw not in (None, "") else None,
            "status": status,
            "timestamp": _safe_timestamp(doc, "timestamp", "data.timestamp", "collected_at"),
            "source": str(doc.get("source", "WHO")).upper(),
            "description": f"Latest WHO indicator update for {indicator.replace('_', ' ')} in {location}."
        })

    vaccination_docs = [
        doc for doc in health_docs
        if "vacc" in str(_pick_nested(doc, "data.indicator", "indicator", default="")).lower()
    ]
    vaccination_values = [
        _extract_first_number(_pick_nested(doc, "data.value", "value", default=None), default=0.0) or 0.0
        for doc in vaccination_docs
    ]
    vaccination_data = {
        "global_coverage": round(max(vaccination_values), 1) if vaccination_values else 0.0,
        "target_coverage": 70.0,
        "doses_administered": int(sum(max(value, 0.0) for value in vaccination_values)),
        "campaigns_active": len(vaccination_docs)
    }

    return {
        "outbreaks": health_items,
        "vaccination": vaccination_data,
        "last_updated": _latest_timestamp(*health_docs),
        "total_active": len([h for h in health_items if h["status"] == "active"])
    }

@app.get("/dashboard/trends-radar")
@limiter.limit("30/minute")
def dashboard_trends_radar(request: Request, role: str = Depends(check_role), limit: int = Query(20, ge=1, le=100)):
    """
    Returns Google Trends data showing trending search terms and topics.
    """
    trends_docs = list(db.trends.find().sort("collected_at", -1).limit(min(5000, limit * 320)))
    trend_items = []
    grouped_topics: dict[str, list[dict]] = defaultdict(list)
    for doc in trends_docs:
        topic = str(_pick_nested(doc, "topic", "data.topic", "data.query", "data.keyword", default="")).strip()
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
            "category": str(_pick_nested(docs[0], "trend_category", "data.category", "category", default="Public Interest")) or "Public Interest",
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
    if len(trend_items) < limit:
        seen_ids = {str(item.get("id", "")) for item in trend_items}
        seen_topics = {str(item.get("topic", "")).strip().lower() for item in trend_items}
        for idx, doc in enumerate(trends_docs):
            if len(trend_items) >= limit:
                break
            fallback_id = str(doc.get("_id", f"trend-fallback-{idx}"))
            if fallback_id in seen_ids:
                continue

            topic = str(_pick_nested(doc, "topic", "data.topic", "data.query", "data.keyword", default="")).strip()
            if not topic:
                continue
            topic_key = topic.lower()
            if topic_key in seen_topics:
                continue

            interest_score = _safe_int(
                _pick_nested(doc, "value", "data.value", "search_volume", "data.interest", "data.interest_score", default=0),
                default=0,
            )
            trend_items.append({
                "id": fallback_id,
                "topic": topic,
                "category": str(_pick_nested(doc, "trend_category", "data.category", "category", default="Public Interest")) or "Public Interest",
                "search_volume": interest_score,
                "interest_score": min(100, interest_score),
                "velocity": 0.0,
                "trend_direction": "stable",
                "breakout": interest_score >= 80,
                "timestamp": _safe_timestamp(doc, "timestamp", "data_timestamp", "collected_at"),
                "related_queries": [
                    f"{topic} news",
                    f"{topic} latest",
                    f"{topic} update"
                ]
            })
            seen_ids.add(fallback_id)
            seen_topics.add(topic_key)
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


@app.get("/analytics/incidents-outlook")
@app.get("/analytics/event-predictions")
@limiter.limit("60/minute")
def analytics_event_predictions(request: Request, role: str = Depends(check_role), limit: int = Query(10, ge=1, le=100)):
    country_docs = list(db.country_features.find({"mode": "online"}).sort("timestamp", -1).limit(limit))
    events = []
    for d in country_docs:
        features = d.get("features")
        f = features if isinstance(features, dict) else {}

        raw_risk = f.get("global_risk_score", 50.0)
        try:
            risk = float(raw_risk)
        except (TypeError, ValueError):
            risk = 50.0
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
    user_type: str | None = None
    role: str | None = None  # Optional legacy input; normalized to admin|user
    admin_invite_code: str | None = None
    organization: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    organization: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateUserStatusRequest(BaseModel):
    active: bool

class UpdateUserAccessRequest(BaseModel):
    role: str | None = None
    user_type: str | None = None


# Temporary storage for password reset tokens
password_reset_tokens = {}


def _build_auth_response(email: str, role: str, user_type: str, name: str = "", message: str | None = None):
    access_token = create_access_token({
        "sub": email,
        "role": role,
        "user_type": user_type,
        "name": name,
    })
    response = {
        "access_token": access_token,
        "email": email,
        "name": name,
        "role": role,
        "user_type": user_type,
    }
    if message:
        response["message"] = message
    return response


def _get_jwt_user_or_401(identity: dict) -> tuple[str, dict]:
    if identity.get("auth_type") != "jwt":
        raise HTTPException(status_code=401, detail="JWT authentication is required")

    email = _sanitize_email(identity.get("sub"))
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token subject")

    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    _, _, _ = ensure_user_role_shape(user)
    active, _ = ensure_user_active_shape(user)
    if not active:
        raise HTTPException(status_code=403, detail="User account is deactivated")

    return email, user


@app.post("/auth/register")
def register(data: RegisterRequest):
    email = _sanitize_email(data.email)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid email")

    existing = users_collection.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    requested_role = normalize_role(data.role)
    assigned_role = ROLE_USER

    if requested_role == ROLE_ADMIN:
        supplied_code = str(data.admin_invite_code or "").strip()
        if not ADMIN_INVITE_CODE:
            raise HTTPException(status_code=403, detail="Admin self-registration is disabled")
        if not supplied_code or not hmac.compare_digest(supplied_code, ADMIN_INVITE_CODE):
            raise HTTPException(status_code=403, detail="Invalid admin invite code")
        assigned_role = ROLE_ADMIN

    normalized_user_type = (
        "developer"
        if assigned_role == ROLE_ADMIN
        else normalize_user_type(data.user_type, data.role)
    )
    normalized_name = str(data.name or "").strip()

    users_collection.insert_one({
        "email": email,
        "password": hash_password(data.password),
        "role": assigned_role,
        "user_type": normalized_user_type,
        "name": normalized_name,
        "organization": data.organization,
        "active": True,
        "deactivated_at": None,
        "deactivated_by": None,
        "created_at": datetime.utcnow().isoformat(),
    })

    return _build_auth_response(
        email=email,
        role=assigned_role,
        user_type=normalized_user_type,
        name=normalized_name,
        message="Registration successful",
    )


@app.post("/auth/forgot-password")
def forgot_password(data: ForgotPasswordRequest):
    email = _sanitize_email(data.email)
    user = users_collection.find_one({"email": email})
    if not user:
        # Return success even if user doesn't exist (security best practice)
        return {"message": "If the email exists, a reset link has been sent"}

    # Generate reset token
    reset_token = str(uuid.uuid4())
    password_reset_tokens[reset_token] = {
        "email": email,
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
    email = _sanitize_email(token_data["email"])
    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    users_collection.update_one(
        {"email": email},
        {"$set": {"password": hash_password(data.new_password), "updated_at": datetime.utcnow().isoformat()}},
    )

    # Remove used token
    del password_reset_tokens[data.token]

    return {"message": "Password has been reset successfully"}


@app.post("/auth/login")
def login(data: LoginRequest, request: Request):
    email = _sanitize_email(data.email)
    client_ip = _client_ip_from_request(request)
    user = users_collection.find_one({"email": email})

    if not user:
        _increment_security_metric("login_failed")
        _record_security_event(
            "login_attempt",
            "failed",
            "Invalid credentials",
            email=email,
            client_ip=client_ip,
            meta={"reason": "user_not_found"},
        )
        _maybe_record_suspicious_failed_logins(email, client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(data.password, str(user.get("password", ""))):
        _increment_security_metric("login_failed")
        _record_security_event(
            "login_attempt",
            "failed",
            "Invalid credentials",
            email=email,
            client_ip=client_ip,
            meta={"reason": "invalid_password"},
        )
        _maybe_record_suspicious_failed_logins(email, client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    role, user_type, _ = ensure_user_role_shape(user)
    active, _ = ensure_user_active_shape(user)
    if not active:
        _increment_security_metric("login_blocked")
        _record_security_event(
            "login_attempt",
            "blocked",
            "User account is deactivated",
            email=email,
            client_ip=client_ip,
            meta={"reason": "deactivated_account"},
        )
        _record_security_event(
            "suspicious_activity",
            "warning",
            "Login attempt on deactivated account",
            email=email,
            client_ip=client_ip,
        )
        raise HTTPException(status_code=403, detail="User account is deactivated")

    name = str(user.get("name") or "")
    _increment_security_metric("login_success")
    _record_security_event(
        "login_attempt",
        "success",
        "Authenticated",
        email=email,
        client_ip=client_ip,
        meta={"role": role, "user_type": user_type},
    )

    return _build_auth_response(
        email=email,
        role=role,
        user_type=user_type,
        name=name,
    )

@app.get("/auth/me")
def auth_me(identity: dict = Depends(verify_api_key)):
    if identity.get("auth_type") != "jwt":
        role = normalize_role(identity.get("role"))
        user_type = normalize_user_type(identity.get("user_type"), role)
        return {
            "email": str(identity.get("sub") or "api-key-client"),
            "name": "API Key Client",
            "organization": None,
            "role": role,
            "user_type": user_type,
            "active": True,
            "deactivated_at": None,
            "deactivated_by": None,
            "auth_type": "api_key",
        }

    _, user = _get_jwt_user_or_401(identity)
    sanitized = sanitize_user_document(user)
    sanitized["auth_type"] = "jwt"
    return sanitized


@app.patch("/auth/me")
def auth_update_me(payload: UpdateProfileRequest, identity: dict = Depends(verify_api_key)):
    email, user = _get_jwt_user_or_401(identity)

    updates = {}
    if payload.name is not None:
        updates["name"] = str(payload.name).strip()
    if payload.organization is not None:
        updates["organization"] = str(payload.organization).strip() or None

    if not updates:
        raise HTTPException(status_code=400, detail="No updates were provided")

    updates["updated_at"] = datetime.utcnow().isoformat()
    users_collection.update_one({"email": email}, {"$set": updates})

    refreshed = users_collection.find_one({"email": email})
    if not refreshed:
        raise HTTPException(status_code=404, detail="User not found")

    sanitized = sanitize_user_document(refreshed)
    sanitized["auth_type"] = "jwt"
    return sanitized


@app.post("/auth/change-password")
def auth_change_password(payload: ChangePasswordRequest, identity: dict = Depends(verify_api_key)):
    email, user = _get_jwt_user_or_401(identity)

    if not verify_password(payload.current_password, str(user.get("password", ""))):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")

    users_collection.update_one(
        {"email": email},
        {
            "$set": {
                "password": hash_password(payload.new_password),
                "updated_at": datetime.utcnow().isoformat(),
            }
        },
    )

    return {"message": "Password updated successfully"}


@app.get("/admin/users")
def admin_list_users(role: str = Depends(require_admin)):
    docs = list(users_collection.find({}, {"password": 0}).sort("created_at", DESCENDING).limit(1000))
    users = [sanitize_user_document(doc) for doc in docs]
    return {"count": len(users), "users": users}


@app.patch("/admin/users/{email}/access")
def admin_update_user_access(email: str, payload: UpdateUserAccessRequest, role: str = Depends(require_admin)):
    target_email = _sanitize_email(email)
    if not target_email:
        raise HTTPException(status_code=400, detail="Invalid email")

    user = users_collection.find_one({"email": target_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    current_role, _, _ = ensure_user_role_shape(user)
    current_active, _ = ensure_user_active_shape(user)

    updates = {}
    if payload.role is not None:
        updates["role"] = normalize_role(payload.role)
    if payload.user_type is not None:
        updates["user_type"] = normalize_user_type(payload.user_type)

    if not updates:
        raise HTTPException(status_code=400, detail="No updates were provided")

    if updates.get("role") == ROLE_ADMIN and payload.user_type is None:
        updates["user_type"] = "developer"

    if current_role == ROLE_ADMIN and updates.get("role") == ROLE_USER and current_active:
        active_admin_count = users_collection.count_documents({"role": ROLE_ADMIN, "active": True})
        if active_admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last active admin account")

    updates["updated_at"] = datetime.utcnow().isoformat()
    users_collection.update_one({"email": target_email}, {"$set": updates})

    updated_doc = users_collection.find_one({"email": target_email}, {"password": 0})
    if not updated_doc:
        raise HTTPException(status_code=404, detail="Updated user not found")

    return sanitize_user_document(updated_doc)


@app.patch("/admin/users/{email}/status")
def admin_update_user_status(
    email: str,
    payload: UpdateUserStatusRequest,
    identity: dict = Depends(require_admin_identity),
):
    target_email = _sanitize_email(email)
    if not target_email:
        raise HTTPException(status_code=400, detail="Invalid email")

    actor_email = _sanitize_email(identity.get("sub"))
    if actor_email and actor_email == target_email and not payload.active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    user = users_collection.find_one({"email": target_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role, _, _ = ensure_user_role_shape(user)
    current_active, _ = ensure_user_active_shape(user)

    next_active = bool(payload.active)
    if role == ROLE_ADMIN and current_active and not next_active:
        active_admin_count = users_collection.count_documents({"role": ROLE_ADMIN, "active": True})
        if active_admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot deactivate the last active admin account")

    updates = {
        "active": next_active,
        "updated_at": datetime.utcnow().isoformat(),
        "deactivated_at": None if next_active else datetime.utcnow().isoformat(),
        "deactivated_by": None if next_active else (actor_email or "admin"),
    }

    users_collection.update_one({"email": target_email}, {"$set": updates})

    updated_doc = users_collection.find_one({"email": target_email}, {"password": 0})
    if not updated_doc:
        raise HTTPException(status_code=404, detail="Updated user not found")

    return sanitize_user_document(updated_doc)

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
    base = build_monitoring_summary(model_monitoring_collection, window=window)
    advanced_ml = {}

    try:
        from machine_learning.advanced_analytics import get_advanced_analytics_kpis
        advanced_ml = get_advanced_analytics_kpis() or {}
    except Exception:
        advanced_ml = {}

    try:
        from machine_learning.lstm_predictor import load_model_metadata
        model_meta = load_model_metadata() or {}
    except Exception:
        model_meta = {}

    return {
        **base,
        "advanced_ml": advanced_ml,
        "model_metadata": model_meta,
    }


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


@app.get("/observability/global-mood-validation")
@limiter.limit("10/minute")
def observability_global_mood_validation(request: Request, role: str = Depends(require_admin)):
    return latest_global_mood_validation()


@app.post("/observability/global-mood-validation/run")
@limiter.limit("5/minute")
def observability_global_mood_validation_run(request: Request, role: str = Depends(require_admin)):
    return run_global_mood_validation()


@app.get("/observability/country-risk-validation/history")
@limiter.limit("10/minute")
def observability_country_risk_validation_history(
    request: Request,
    role: str = Depends(require_admin),
    limit: int = Query(30, ge=1, le=365),
):
    return {"rows": list_country_risk_validation_history(limit=limit), "limit": limit}


@app.get("/observability/global-mood-validation/history")
@limiter.limit("10/minute")
def observability_global_mood_validation_history(
    request: Request,
    role: str = Depends(require_admin),
    limit: int = Query(30, ge=1, le=365),
):
    return {"rows": list_global_mood_validation_history(limit=limit), "limit": limit}


@app.get("/observability/country-risk-backtest")
@limiter.limit("10/minute")
def observability_country_risk_backtest(request: Request, role: str = Depends(require_admin)):
    return latest_country_risk_backtest()


@app.get("/observability/global-mood-backtest")
@limiter.limit("10/minute")
def observability_global_mood_backtest(request: Request, role: str = Depends(require_admin)):
    return latest_global_mood_backtest()


@app.post("/observability/backtests/run")
@limiter.limit("5/minute")
def observability_backtests_run(
    request: Request,
    role: str = Depends(require_admin),
    days: int = Query(60, ge=1, le=365),
):
    return {
        "country": run_country_risk_backtest(days=days),
        "global_mood": run_global_mood_backtest(days=days),
    }


def _coerce_utc_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _hours_since(value) -> float | None:
    dt = _coerce_utc_datetime(value)
    if not dt:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)


INGESTION_SLA_HOURS = {
    "country_features": 6.0,
    "global_features": 6.0,
    "dashboard_features": 6.0,
    "earthquakes": 6.0,
    "weather": 12.0,
    "economics": 24.0,
    "health": 24.0,
    "trends": 24.0,
}


def _build_latest_ingestion() -> dict:
    return {
        "country_features": _latest_collection_stamp(country_features_collection, ["timestamp", "collected_at", "created_at"]),
        "global_features": _latest_collection_stamp(global_features_collection, ["timestamp", "collected_at", "created_at"]),
        "dashboard_features": _latest_collection_stamp(dashboard_features_collection, ["timestamp", "collected_at", "created_at"]),
        "earthquakes": _latest_collection_stamp(earthquakes_collection, ["collected_at", "timestamp", "created_at"]),
        "weather": _latest_collection_stamp(weather_collection, ["data_timestamp", "collected_at", "timestamp", "created_at"]),
        "economics": _latest_collection_stamp(economics_collection, ["collected_at", "timestamp", "created_at"]),
        "health": _latest_collection_stamp(health_collection, ["collected_at", "timestamp", "created_at"]),
        "trends": _latest_collection_stamp(trends_collection, ["collected_at", "timestamp", "created_at"]),
    }


def _build_freshness_snapshot(latest_ingestion: dict) -> dict:
    rows = []
    for source, stamp in latest_ingestion.items():
        age_hours = _hours_since(stamp)
        sla_hours = float(INGESTION_SLA_HOURS.get(source, 24.0))
        status = "unknown"
        if age_hours is not None:
            status = "fresh" if age_hours <= sla_hours else "stale"
        rows.append({
            "source": source,
            "last_updated": stamp,
            "age_hours": round(age_hours, 3) if age_hours is not None else None,
            "sla_hours": sla_hours,
            "status": status,
        })

    known_ages = [float(r["age_hours"]) for r in rows if isinstance(r.get("age_hours"), (int, float))]
    stale_count = len([r for r in rows if r.get("status") == "stale"])
    return {
        "sources": rows,
        "fresh_count": len([r for r in rows if r.get("status") == "fresh"]),
        "stale_count": stale_count,
        "unknown_count": len([r for r in rows if r.get("status") == "unknown"]),
        "oldest_age_hours": round(max(known_ages), 3) if known_ages else None,
        "newest_age_hours": round(min(known_ages), 3) if known_ages else None,
        "overall_status": "stale" if stale_count > 0 else "healthy",
    }


def _latest_global_features_doc(mode: str = "online") -> dict | None:
    doc = global_features_collection.find_one({"mode": mode}, sort=[("_id", DESCENDING)])
    if doc:
        return doc
    return dashboard_features_collection.find_one({"mode": mode}, sort=[("_id", DESCENDING)])


def _build_confidence_snapshot(mode: str = "online") -> dict:
    doc = _latest_global_features_doc(mode=mode) or {}
    features = doc.get("features") or {}
    mood_conf = features.get("global_mood_confidence")
    mood_unc = features.get("global_mood_uncertainty")
    forecast_conf = features.get("forecast_confidence")
    forecast_delta = features.get("forecast_risk_delta")
    forecast_risk = features.get("forecast_risk_score")
    risk_now = features.get("global_risk_score")
    return {
        "global_risk_score": float(risk_now) if risk_now is not None else None,
        "global_mood_confidence": float(mood_conf) if mood_conf is not None else None,
        "global_mood_uncertainty": float(mood_unc) if mood_unc is not None else None,
        "forecast_confidence": float(forecast_conf) if forecast_conf is not None else None,
        "forecast_risk_delta": float(forecast_delta) if forecast_delta is not None else None,
        "forecast_risk_score": float(forecast_risk) if forecast_risk is not None else None,
        "timestamp": str(features.get("timestamp") or doc.get("timestamp") or datetime.now(timezone.utc).isoformat()),
    }


@app.get("/trust/reliability")
@limiter.limit("20/minute")
def trust_reliability(request: Request, role: str = Depends(check_role), mode: str = Query("online")):
    runtime_snapshot = runtime_metrics.snapshot()
    started_at = _coerce_utc_datetime(runtime_snapshot.get("started_at")) or datetime.now(timezone.utc)
    uptime_seconds = max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())
    total_requests = int(runtime_snapshot.get("total_requests", 0) or 0)
    total_errors = int(runtime_snapshot.get("total_errors", 0) or 0)

    db_ok = True
    model_loaded = False
    model_version = None
    ready_error = None
    try:
        db.command("ping")
        model, model_version = load_production_model()
        model_loaded = model is not None
    except Exception as exc:
        db_ok = False
        ready_error = str(exc)

    latest_ingestion = _build_latest_ingestion()
    freshness = _build_freshness_snapshot(latest_ingestion)
    country_validation = latest_country_risk_validation()
    global_validation = latest_global_mood_validation()
    country_backtest = latest_country_risk_backtest()
    global_backtest = latest_global_mood_backtest()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_health": {
            "status": "healthy" if db_ok and model_loaded else "degraded",
            "database": "connected" if db_ok else "disconnected",
            "model_loaded": bool(model_loaded),
            "model_version": model_version,
        },
        "uptime": {
            "uptime_seconds": round(uptime_seconds, 3),
            "uptime_human": _format_uptime(uptime_seconds),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": round((float(total_errors) / float(total_requests)), 6) if total_requests else 0.0,
            "requests_per_minute": round((float(total_requests) / (uptime_seconds / 60.0)), 3) if uptime_seconds > 0 else 0.0,
            "total_predictions": int(runtime_snapshot.get("total_predictions", 0) or 0),
            "last_prediction_at": runtime_snapshot.get("last_prediction_at"),
        },
        "data_freshness": freshness,
        "latest_ingestion": latest_ingestion,
        "confidence": _build_confidence_snapshot(mode=mode),
        "validation": {
            "country_latest": {
                "status": country_validation.get("status"),
                "timestamp": country_validation.get("timestamp"),
                "sample_count": int(country_validation.get("sample_count", 0) or 0),
                "brier_score": float((((country_validation.get("metrics") or {}).get("brier_score", 0.0)) or 0.0)),
            },
            "global_latest": {
                "status": global_validation.get("status"),
                "timestamp": global_validation.get("timestamp"),
                "sample_count": int(global_validation.get("sample_count", 0) or 0),
                "confidence_avg": float((((global_validation.get("metrics") or {}).get("confidence_avg", 0.0)) or 0.0)),
                "uncertainty_avg": float((((global_validation.get("metrics") or {}).get("uncertainty_avg", 0.0)) or 0.0)),
            },
            "country_backtest": {
                "status": country_backtest.get("status"),
                "timestamp": country_backtest.get("timestamp"),
                "window_days": int(country_backtest.get("window_days", 0) or 0),
                "matched_days": int(country_backtest.get("matched_days", 0) or 0),
                "weighted_brier_score": float((((country_backtest.get("metrics") or {}).get("weighted_brier_score", 0.0)) or 0.0)),
            },
            "global_backtest": {
                "status": global_backtest.get("status"),
                "timestamp": global_backtest.get("timestamp"),
                "window_days": int(global_backtest.get("window_days", 0) or 0),
                "matched_days": int(global_backtest.get("matched_days", 0) or 0),
                "weighted_brier_score": float((((global_backtest.get("metrics") or {}).get("weighted_brier_score", 0.0)) or 0.0)),
                "weighted_mae": float((((global_backtest.get("metrics") or {}).get("weighted_mae", 0.0)) or 0.0)),
            },
        },
    }

    if ready_error:
        payload["api_health"]["error"] = ready_error

    return payload


@app.get("/trust/backtests/country")
@limiter.limit("20/minute")
def trust_country_backtests(
    request: Request,
    role: str = Depends(check_role),
    limit: int = Query(30, ge=1, le=365),
):
    return {"rows": list_country_risk_backtests(limit=limit), "limit": limit}


@app.get("/trust/backtests/global-mood")
@limiter.limit("20/minute")
def trust_global_mood_backtests(
    request: Request,
    role: str = Depends(check_role),
    limit: int = Query(30, ge=1, le=365),
):
    return {"rows": list_global_mood_backtests(limit=limit), "limit": limit}


def _latest_collection_stamp(collection, keys: list[str]) -> str | None:
    doc = collection.find_one(sort=[("_id", DESCENDING)])
    if not doc:
        return None

    for key in keys:
        value = doc.get(key)
        if value is None:
            continue
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    return None


@app.get("/admin/system-monitoring")
@limiter.limit("10/minute")
def admin_system_monitoring(request: Request, role: str = Depends(require_admin), mode: str = Query("online")):
    runtime_snapshot = runtime_metrics.snapshot()

    started_at_raw = runtime_snapshot.get("started_at")
    try:
        started_at = datetime.fromisoformat(str(started_at_raw)) if started_at_raw else datetime.now(timezone.utc)
    except Exception:
        started_at = datetime.now(timezone.utc)

    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    uptime_seconds = max(0.0, (datetime.now(timezone.utc) - started_at.astimezone(timezone.utc)).total_seconds())
    total_requests = int(runtime_snapshot.get("total_requests", 0) or 0)
    total_errors = int(runtime_snapshot.get("total_errors", 0) or 0)

    error_rate = (float(total_errors) / float(total_requests)) if total_requests else 0.0
    requests_per_minute = (float(total_requests) / (uptime_seconds / 60.0)) if uptime_seconds > 0 else 0.0

    try:
        db.command("ping")
        database_status = "connected"
        model, model_version = load_production_model()
        model_loaded = model is not None
        ready_status = "ready" if model_loaded else "degraded"
        ready_error = None
    except Exception as exc:
        database_status = "disconnected"
        model_loaded = False
        model_version = None
        ready_status = "degraded"
        ready_error = str(exc)

    try:
        dependencies = get_country_risk_dependency_health(mode=mode)
        dependencies["country_risk_stream"] = country_risk_stream_health()
        pipeline_status = "ok"
        pipeline_error = None
    except Exception as exc:
        dependencies = {"error": str(exc)}
        pipeline_status = "degraded"
        pipeline_error = str(exc)

    latest_ingestion = {
        "country_features": _latest_collection_stamp(country_features_collection, ["timestamp", "collected_at", "created_at"]),
        "global_features": _latest_collection_stamp(global_features_collection, ["timestamp", "collected_at", "created_at"]),
        "dashboard_features": _latest_collection_stamp(dashboard_features_collection, ["timestamp", "collected_at", "created_at"]),
        "earthquakes": _latest_collection_stamp(earthquakes_collection, ["collected_at", "timestamp", "created_at"]),
        "weather": _latest_collection_stamp(weather_collection, ["data_timestamp", "collected_at", "timestamp", "created_at"]),
        "economics": _latest_collection_stamp(economics_collection, ["collected_at", "timestamp", "created_at"]),
        "health": _latest_collection_stamp(health_collection, ["collected_at", "timestamp", "created_at"]),
        "trends": _latest_collection_stamp(trends_collection, ["collected_at", "timestamp", "created_at"]),
    }

    response = {
        "server_status": {
            "status": "running",
            "app": "World Pulse Secure API",
            "process_id": os.getpid(),
            "hostname": platform.node(),
            "python_version": platform.python_version(),
            "started_at": started_at.isoformat(),
        },
        "api_health": {
            "live": {"status": "alive"},
            "ready": {
                "status": ready_status,
                "database": database_status,
                "model_loaded": model_loaded,
                "model_version": model_version,
            },
        },
        "data_pipeline_status": {
            "status": pipeline_status,
            "dependencies": dependencies,
            "latest_ingestion": latest_ingestion,
        },
        "uptime_statistics": {
            "uptime_seconds": round(uptime_seconds, 3),
            "uptime_human": _format_uptime(uptime_seconds),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": round(error_rate, 6),
            "requests_per_minute": round(requests_per_minute, 3),
            "total_predictions": int(runtime_snapshot.get("total_predictions", 0) or 0),
            "last_prediction_at": runtime_snapshot.get("last_prediction_at"),
        },
    }

    if ready_error:
        response["api_health"]["ready"]["error"] = ready_error
    if pipeline_error:
        response["data_pipeline_status"]["error"] = pipeline_error

    return response


@app.get("/admin/security-logs")
@limiter.limit("10/minute")
def admin_security_logs(
    request: Request,
    role: str = Depends(require_admin),
    limit: int = Query(100, ge=10, le=1000),
    minutes: int = Query(1440, ge=15, le=10080),
):
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    base_query = {"timestamp": {"$gte": cutoff}}

    login_base = {**base_query, "event_type": "login_attempt"}
    login_total = security_events_collection.count_documents(login_base)
    login_success = security_events_collection.count_documents({**login_base, "status": "success"})
    login_failed = security_events_collection.count_documents({**login_base, "status": "failed"})
    login_blocked = security_events_collection.count_documents({**login_base, "status": "blocked"})

    suspicious_total = security_events_collection.count_documents({**base_query, "event_type": "suspicious_activity"})

    jwt_failed_recent = security_events_collection.count_documents(
        {**base_query, "event_type": "jwt_validation", "status": "failed"}
    )

    events = [
        serialize_doc(doc)
        for doc in security_events_collection.find(base_query).sort("timestamp", DESCENDING).limit(limit)
    ]

    return {
        "window_minutes": minutes,
        "generated_at": datetime.utcnow().isoformat(),
        "login_attempts": {
            "total": int(login_total),
            "success": int(login_success),
            "failed": int(login_failed),
            "blocked": int(login_blocked),
        },
        "suspicious_activity": {
            "total": int(suspicious_total),
        },
        "jwt_token_monitoring": {
            **_security_metrics_snapshot(),
            "recent_failed_validations": int(jwt_failed_recent),
        },
        "events": events,
    }

def _identity_from_ws_credentials(
    x_api_key: str | None = None,
    api_key: str | None = None,
    authorization: str | None = None,
    token: str | None = None,
):
    # Prefer JWT from explicit query token, then Authorization header, then API key fallback.
    candidate_token = (token or "").strip()
    if candidate_token:
        try:
            return decode_access_token(candidate_token, source="websocket_query_token")
        except HTTPException:
            return None

    bearer = (authorization or "").strip()
    if bearer.lower().startswith("bearer "):
        try:
            return decode_access_token(bearer.split(" ", 1)[1].strip(), source="websocket_authorization_header")
        except HTTPException:
            return None

    return _identity_from_api_key(x_api_key or api_key)


# =====================================================
# REAL-TIME RISK STREAM
# =====================================================
# =====================================================
# REAL-TIME RISK STREAM WITH TOPICS
# =====================================================
@app.websocket("/ws/risk")
async def websocket_risk(
    websocket: WebSocket,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
    api_key: str = Query(None),
    token: str = Query(None),
):
    identity = _identity_from_ws_credentials(
        x_api_key=x_api_key,
        api_key=api_key,
        authorization=authorization,
        token=token,
    )
    if not identity:
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
async def websocket_country_risk_map(
    websocket: WebSocket,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
    api_key: str = Query(None),
    token: str = Query(None),
):
    identity = _identity_from_ws_credentials(
        x_api_key=x_api_key,
        api_key=api_key,
        authorization=authorization,
        token=token,
    )
    if not identity:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    consumer_config = {
        "topics": ["country_risk_updates"],
        "group_id": f"dashboard-country-risk-{uuid.uuid4()}",
        "auto_offset_reset": "latest",
        "enable_auto_commit": True,
        "consumer_timeout_ms": 250,
    }

    def drain_consumer(active_consumer):
        records = active_consumer.poll(timeout_ms=250, max_records=64)
        messages = []
        for batch in records.values():
            for message in batch:
                messages.append(message.value)
        return messages

    consumer = None
    try:
        try:
            consumer = await asyncio.to_thread(get_consumer, **consumer_config)
        except Exception as exc:
            logger.warning(
                "country_risk_ws_consumer_unavailable",
                extra={"event": {"error": str(exc)}},
            )

        while True:
            if consumer is None:
                await asyncio.sleep(3)
                try:
                    consumer = await asyncio.to_thread(get_consumer, **consumer_config)
                except Exception:
                    continue
                continue

            try:
                messages = await asyncio.to_thread(drain_consumer, consumer)
            except Exception as exc:
                logger.warning(
                    "country_risk_ws_consumer_failed",
                    extra={"event": {"error": str(exc)}},
                )
                try:
                    await asyncio.to_thread(consumer.close)
                except Exception:
                    pass
                consumer = None
                await asyncio.sleep(1)
                continue

            if not messages:
                await asyncio.sleep(0.1)
                continue

            for payload in messages:
                await websocket.send_json(payload)
    except WebSocketDisconnect:
        return
    finally:
        if consumer is not None:
            try:
                await asyncio.to_thread(consumer.close)
            except Exception:
                pass

@app.websocket("/ws/sentinel")
async def websocket_sentinel(
    websocket: WebSocket,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
    api_key: str = Query(None),
    token: str = Query(None),
):
    """
    WebSocket endpoint for Sentinel AI real-time updates.
    Provides risk score, analysis, and alerts to connected clients.
    """
    identity = _identity_from_ws_credentials(
        x_api_key=x_api_key,
        api_key=api_key,
        authorization=authorization,
        token=token,
    )
    if not identity:
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
        if isinstance(anomalies_data, list):
            anomalies_list = anomalies_data
        elif isinstance(anomalies_data, dict):
            anomalies_list = anomalies_data.get("anomalies", [])
        else:
            anomalies_list = []

        anomalies_transformed = [
            {
                "timestamp": a.get("timestamp", datetime.utcnow().isoformat()),
                "anomaly_score": float(a.get("anomaly_score", a.get("score", 0.5))),
                "features": a.get("features", {}),
                "severity": a.get("severity", "medium")
            }
            for a in anomalies_list[:10]
            if isinstance(a, dict)
        ]
        
        # Transform causal graph
        causal_data = results.get("causal_graph", results.get("causal_discovery", {}))
        if isinstance(causal_data, list):
            causal_list = causal_data
        elif isinstance(causal_data, dict):
            causal_list = causal_data.get("causal_links", causal_data.get("links", []))
        else:
            causal_list = []

        causal_graph_transformed = [
            {
                "source": c.get("source", c.get("from", "")),
                "target": c.get("target", c.get("to", "")),
                "strength": float(c.get("strength", c.get("weight", 0.5)))
            }
            for c in causal_list[:20]
            if isinstance(c, dict)
        ]
        
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
            "ai_report": ai_report_transformed,
            "ml_observability": results.get("ml_observability", {}),
        }
        
    except Exception as e:
        logger.error(f"Advanced analytics failed: {e}")

        # Dynamic fallback anchored to the latest observed global risk.
        baseline_risk = 50.0
        try:
            latest_doc = get_latest_global_doc("online")
            latest_features = (latest_doc or {}).get("features", {}) if isinstance(latest_doc, dict) else {}
            baseline_risk = float(latest_features.get("global_risk_score", 50.0))
        except Exception:
            baseline_risk = 50.0

        baseline_risk = max(0.0, min(100.0, baseline_risk))
        drifts = [0.0, -0.08, -0.15, -0.22]
        horizons = ["1h", "6h", "24h", "7d"]
        dynamic_preds = []
        for idx, horizon in enumerate(horizons):
            projected = baseline_risk + (baseline_risk - 50.0) * drifts[idx]
            dynamic_preds.append(
                {
                    "horizon": horizon,
                    "risk_score": round(max(0.0, min(100.0, projected)), 2),
                    "confidence": round(max(0.2, 0.75 - (idx * 0.07)), 2),
                }
            )

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "predictions": {
                "predictions": dynamic_preds,
                "model_type": "statistical_fallback"
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
                "summary": "Unable to generate full advanced report right now; showing dynamic fallback projections.",
                "key_findings": [],
                "recommendations": [],
                "risk_level": "moderate"
            }
        }


# =====================================================
# STARTUP USER MIGRATION / SEED
# =====================================================

def migrate_user_profiles() -> int:
    migrated = 0
    for doc in users_collection.find({}, {"role": 1, "user_type": 1, "active": 1}):
        _, _, changed_role = ensure_user_role_shape(doc)
        _, changed_active = ensure_user_active_shape(doc)
        if changed_role or changed_active:
            migrated += 1
    return migrated


@app.on_event("startup")
def bootstrap_and_migrate_users():
    bootstrap_users = [
        {
            "email": "admin@wp.com",
            "password": "admin123",
            "role": ROLE_ADMIN,
            "user_type": "developer",
            "name": "Admin User",
        },
        {
            "email": "researcher@wp.com",
            "password": "research123",
            "role": ROLE_USER,
            "user_type": "researcher",
            "name": "Researcher User",
        },
        {
            "email": "policy@wp.com",
            "password": "policy123",
            "role": ROLE_USER,
            "user_type": "policy",
            "name": "Policy User",
        },
        {
            "email": "student@wp.com",
            "password": "student123",
            "role": ROLE_USER,
            "user_type": "student",
            "name": "Student User",
        },
        {
            "email": "developer@wp.com",
            "password": "developer123",
            "role": ROLE_USER,
            "user_type": "developer",
            "name": "Developer User",
        },
    ]

    for user in bootstrap_users:
        email = _sanitize_email(user["email"])
        existing = users_collection.find_one({"email": email})

        if not existing:
            users_collection.insert_one({
                "email": email,
                "password": hash_password(user["password"]),
                "role": normalize_role(user["role"]),
                "user_type": normalize_user_type(user["user_type"], user["role"]),
                "name": user["name"],
                "active": True,
                "deactivated_at": None,
                "deactivated_by": None,
                "created_at": datetime.utcnow().isoformat(),
            })
            continue

        desired_role = normalize_role(user["role"])
        desired_user_type = normalize_user_type(user["user_type"], user["role"])
        updates = {}

        if str(existing.get("role") or "").strip().lower() != desired_role:
            updates["role"] = desired_role
        if str(existing.get("user_type") or "").strip().lower() != desired_user_type:
            updates["user_type"] = desired_user_type
        if "active" not in existing:
            updates["active"] = True
        if "deactivated_at" not in existing:
            updates["deactivated_at"] = None
        if "deactivated_by" not in existing:
            updates["deactivated_by"] = None

        if updates:
            updates["updated_at"] = datetime.utcnow().isoformat()
            users_collection.update_one({"_id": existing["_id"]}, {"$set": updates})

    migrated = migrate_user_profiles()
    if migrated:
        logger.info(
            "user_profiles_migrated",
            extra={"event": {"count": migrated}},
        )












