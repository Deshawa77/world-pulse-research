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
import math
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
import numpy as np
from passlib.context import CryptContext
import jwt
from datetime import timedelta
from collections import defaultdict
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

ADVANCED_INSIGHTS_EXECUTOR = ThreadPoolExecutor(max_workers=1)
ADVANCED_INSIGHTS_CACHE_LOCK = threading.Lock()
ADVANCED_INSIGHTS_FUTURE = None
ADVANCED_INSIGHTS_FUTURE_STARTED_AT = 0.0
ADVANCED_INSIGHTS_CACHE = None
ADVANCED_INSIGHTS_CACHE_AT = 0.0
ADVANCED_INSIGHTS_CACHE_TTL_SECONDS = 45.0
ADVANCED_INSIGHTS_WAIT_TIMEOUT_SECONDS = 8.0
ADVANCED_INSIGHTS_STALL_SECONDS = 60.0
DASHBOARD_ROUTE_CACHE_LOCK = threading.Lock()
DASHBOARD_ROUTE_CACHE: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
DASHBOARD_ROUTE_CACHE_TTLS = {
    "risk_map": 20.0,
    "coverage": 20.0,
    "feed": 4.0,
    "trust": 30.0,
    "global_quality": 20.0,
}
KAFKA_UNAVAILABLE_RETRY_SECONDS = 60.0
LIVE_CONSUMER_UNAVAILABLE_UNTIL: dict[str, float] = defaultdict(float)
COUNTRY_REFRESH_TRIGGER_AGE_SECONDS = 900.0
COUNTRY_REFRESH_MIN_INTERVAL_SECONDS = 900.0
COUNTRY_REFRESH_BATCH_SIZE = 10
COUNTRY_REFRESH_MAX_RECORDS = 4
COUNTRY_REFRESH_LOCK = threading.Lock()
COUNTRY_REFRESH_STARTED_AT = 0.0


def _dashboard_cache_get(namespace: str, cache_key: str) -> Any | None:
    now_ts = time.time()
    ttl = float(DASHBOARD_ROUTE_CACHE_TTLS.get(namespace, 0.0) or 0.0)
    if ttl <= 0.0:
        return None
    with DASHBOARD_ROUTE_CACHE_LOCK:
        entry = DASHBOARD_ROUTE_CACHE.get(namespace, {}).get(cache_key)
        if not entry:
            return None
        if now_ts - float(entry.get("timestamp", 0.0) or 0.0) > ttl:
            DASHBOARD_ROUTE_CACHE.get(namespace, {}).pop(cache_key, None)
            return None
        return entry.get("value")


def _dashboard_cache_set(namespace: str, cache_key: str, value: Any) -> Any:
    with DASHBOARD_ROUTE_CACHE_LOCK:
        DASHBOARD_ROUTE_CACHE.setdefault(namespace, {})[cache_key] = {
            "timestamp": time.time(),
            "value": value,
        }
    return value


def _mark_consumer_unavailable(stream_name: str) -> None:
    LIVE_CONSUMER_UNAVAILABLE_UNTIL[stream_name] = time.monotonic() + KAFKA_UNAVAILABLE_RETRY_SECONDS


def _consumer_retry_allowed(stream_name: str) -> bool:
    return time.monotonic() >= float(LIVE_CONSUMER_UNAVAILABLE_UNTIL.get(stream_name, 0.0) or 0.0)


def _reset_advanced_insights_executor(reason: str) -> None:
    global ADVANCED_INSIGHTS_EXECUTOR
    global ADVANCED_INSIGHTS_FUTURE
    global ADVANCED_INSIGHTS_FUTURE_STARTED_AT
    old_executor = ADVANCED_INSIGHTS_EXECUTOR
    ADVANCED_INSIGHTS_EXECUTOR = ThreadPoolExecutor(max_workers=1)
    ADVANCED_INSIGHTS_FUTURE = None
    ADVANCED_INSIGHTS_FUTURE_STARTED_AT = 0.0
    try:
        old_executor.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        try:
            old_executor.shutdown(wait=False)
        except Exception:
            pass
    except Exception:
        pass
    logging.getLogger(__name__).warning("advanced_insights_executor_reset reason=%s", reason)


def _advanced_insights_cache_fresh(now_ts: float | None = None) -> bool:
    now_ts = now_ts if now_ts is not None else time.time()
    return ADVANCED_INSIGHTS_CACHE is not None and (now_ts - ADVANCED_INSIGHTS_CACHE_AT) <= ADVANCED_INSIGHTS_CACHE_TTL_SECONDS

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


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")[:72]
    safe_password = password_bytes.decode("utf-8", errors="ignore")
    return pwd_context.hash(safe_password)


from processing.global_risk import compute_global_risk
from processing.global_mood import compute_global_operational_features
from processing.world_state_quality import compute_quality_gate
from processing.country_daily_risk import country_daily_refresh_if_due
from processing.country_incremental_risk import recompute_country_risk
from processing.spillover_graph import load_country_spillover_map
from collectors.country_news import get_country_catalog
from processing.country_catalog import COUNTRY_NAMES
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
from machine_learning.prediction_schema import (
    DEFAULT_PREDICTION_FEATURES,
    EXPANDED_GLOBAL_PREDICTION_FEATURES,
    LEGACY_GLOBAL_PREDICTION_FEATURES,
    PREDICTION_SCHEMA_VERSION,
    extract_feature_vector,
)

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
LEGACY_DEV_API_KEY = (os.environ.get("LEGACY_DEV_API_KEY") or "super_secure_api_key").strip().strip('"').strip("'")
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
if LEGACY_DEV_API_KEY:
    USER_API_KEYS.add(LEGACY_DEV_API_KEY)
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
source_health_collection = db["source_health"]
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
source_health_collection.create_index([("source", ASCENDING)], unique=True)
source_health_collection.create_index([("updated_at", DESCENDING)])
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
model_cache = {"model": None, "version": None, "feature_names": DEFAULT_PREDICTION_FEATURES, "schema_version": PREDICTION_SCHEMA_VERSION}

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


def _build_attention_observability(window_hours: int = 48, max_countries: int = 12) -> dict:
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(hours=window_hours)
    sample_docs = list(db.wiki.find({}, {"_id": 0, "country": 1, "collected_at": 1, "data": 1}).sort("_id", DESCENDING).limit(5000))

    latest_by_country: dict[str, dict] = {}
    total_recent_docs = 0
    positive_delta_docs = 0
    total_views = 0.0
    total_delta_ratio = 0.0
    measured_docs = 0

    for doc in sample_docs:
        stamp = _parse_timestamp(doc.get("collected_at") or (doc.get("data") or {}).get("date"))
        if stamp < cutoff:
            continue

        country = str(doc.get("country") or "").strip().upper()
        if not country:
            continue

        total_recent_docs += 1
        data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
        views = _safe_float(data.get("views"), 0.0)
        delta_ratio = _safe_float(data.get("view_delta_ratio"), 0.0)
        total_views += views
        total_delta_ratio += delta_ratio
        measured_docs += 1
        if delta_ratio > 0:
            positive_delta_docs += 1

        existing = latest_by_country.get(country)
        if existing is None or stamp > existing["stamp"]:
            latest_by_country[country] = {
                "stamp": stamp,
                "views": views,
                "delta_ratio": delta_ratio,
            }

    countries = sorted(
        (
            {
                "country": code,
                "country_name": COUNTRY_NAMES.get(code) or get_country_catalog().get(code, code),
                "timestamp": payload["stamp"].isoformat(),
                "views": round(payload["views"], 0),
                "delta_ratio": round(payload["delta_ratio"], 4),
            }
            for code, payload in latest_by_country.items()
        ),
        key=lambda item: (item["delta_ratio"], item["views"]),
        reverse=True,
    )

    coverage_ratio = (len(latest_by_country) / 233.0) if latest_by_country else 0.0
    return {
        "status": "healthy" if latest_by_country else "monitoring",
        "window_hours": window_hours,
        "latest_country_count": len(latest_by_country),
        "coverage_ratio": round(coverage_ratio, 4),
        "recent_doc_count": total_recent_docs,
        "positive_delta_ratio": round((positive_delta_docs / measured_docs), 4) if measured_docs else 0.0,
        "average_views": round((total_views / measured_docs), 2) if measured_docs else 0.0,
        "average_delta_ratio": round((total_delta_ratio / measured_docs), 4) if measured_docs else 0.0,
        "top_countries": countries[:max_countries],
        "last_updated": countries[0]["timestamp"] if countries else None,
        "source": "wikimedia_pageviews",
    }


def _build_mobility_observability(displacement_window_hours: int = 72, aviation_window_hours: int = 18, max_countries: int = 12) -> dict:
    now_utc = datetime.now(timezone.utc)
    displacement_cutoff = now_utc - timedelta(hours=displacement_window_hours)
    aviation_cutoff = now_utc - timedelta(hours=aviation_window_hours)
    logistics_cutoff = now_utc - timedelta(hours=max(displacement_window_hours, 96))

    displacement_docs = list(db.mobility.find({}, {"_id": 0, "country": 1, "collected_at": 1, "data": 1}).sort("_id", DESCENDING).limit(6000))
    aviation_docs = list(db.aviation.find({}, {"_id": 0, "country": 1, "collected_at": 1, "data": 1}).sort("_id", DESCENDING).limit(6000))
    logistics_docs = list(db.logistics.find({}, {"_id": 0, "country": 1, "collected_at": 1, "data": 1}).sort("_id", DESCENDING).limit(6000))

    latest_displacement: dict[str, dict] = {}
    latest_aviation: dict[str, dict] = {}
    latest_logistics: dict[str, dict] = {}
    displacement_daily: dict[str, set[str]] = {}
    aviation_hourly: dict[str, set[str]] = {}
    combined_daily: dict[str, set[str]] = {}

    for doc in displacement_docs:
        stamp = _parse_timestamp(doc.get("collected_at") or (doc.get("data") or {}).get("snapshot_date"))
        if stamp < displacement_cutoff:
            continue
        country = str(doc.get("country") or "").strip().upper()
        if not country:
            continue
        day_key = stamp.astimezone(timezone.utc).date().isoformat()
        displacement_daily.setdefault(day_key, set()).add(country)
        combined_daily.setdefault(day_key, set()).add(country)
        displaced_people = _safe_float(((doc.get("data") or {}).get("displaced_people")), 0.0)
        delta_ratio = _safe_float(((doc.get("data") or {}).get("displacement_delta_ratio")), 0.0)
        displaced_pressure = min((math.log1p(max(displaced_people, 0.0)) / 13.0) + max(delta_ratio, 0.0) * 0.2, 1.0)
        payload = {
            "stamp": stamp,
            "displaced_people": displaced_people,
            "delta_ratio": delta_ratio,
            "displaced_pressure": displaced_pressure,
        }
        existing = latest_displacement.get(country)
        if existing is None or stamp > existing["stamp"]:
            latest_displacement[country] = payload

    for doc in aviation_docs:
        stamp = _parse_timestamp(doc.get("collected_at") or (doc.get("data") or {}).get("snapshot_at"))
        if stamp < aviation_cutoff:
            continue
        country = str(doc.get("country") or "").strip().upper()
        if not country:
            continue
        hour_key = stamp.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
        day_key = stamp.astimezone(timezone.utc).date().isoformat()
        aviation_hourly.setdefault(hour_key, set()).add(country)
        combined_daily.setdefault(day_key, set()).add(country)
        payload = {
            "stamp": stamp,
            "aircraft_count": _safe_float(((doc.get("data") or {}).get("aircraft_count")), 0.0),
            "aviation_disruption_score": _safe_float(((doc.get("data") or {}).get("aviation_disruption_score")), 0.0),
        }
        existing = latest_aviation.get(country)
        if existing is None or stamp > existing["stamp"]:
            latest_aviation[country] = payload

    for doc in logistics_docs:
        stamp = _parse_timestamp(doc.get("collected_at") or doc.get("timestamp"))
        if stamp < logistics_cutoff:
            continue
        country = str(doc.get("country") or "").strip().upper()
        if not country:
            continue
        day_key = stamp.astimezone(timezone.utc).date().isoformat()
        combined_daily.setdefault(day_key, set()).add(country)
        payload = {
            "stamp": stamp,
            "logistics_stress_score": _safe_float(((doc.get("data") or {}).get("logistics_stress_score")), 0.0),
        }
        existing = latest_logistics.get(country)
        if existing is None or stamp > existing["stamp"]:
            latest_logistics[country] = payload

    union_countries = sorted(set(latest_displacement.keys()) | set(latest_aviation.keys()) | set(latest_logistics.keys()))
    catalog = get_country_catalog()
    top_rows = []
    for code in union_countries:
        displacement = latest_displacement.get(code) or {}
        aviation = latest_aviation.get(code) or {}
        logistics = latest_logistics.get(code) or {}
        feature_docs = list(db.country_features.find({"country": code, "mode": "online"}).sort("timestamp", -1).limit(8))
        preferred_doc = _prefer_feature_doc(feature_docs)
        preferred_features = preferred_doc.get("features", {}) if preferred_doc else {}
        source_count = sum(1 for item in (displacement, aviation, logistics) if item)
        freshness_values = []
        for item, window in ((displacement, displacement_window_hours), (aviation, aviation_window_hours), (logistics, max(displacement_window_hours, 96))):
            stamp = item.get("stamp") if item else None
            if stamp:
                age_hours = max((now_utc - stamp).total_seconds() / 3600.0, 0.0)
                freshness_values.append(max(0.0, 1.0 - min(age_hours / max(window, 1), 1.0)))
        freshness = round(sum(freshness_values) / len(freshness_values), 4) if freshness_values else 0.0
        confidence = round(min((source_count / 3.0) * 0.65 + freshness * 0.35, 1.0), 4) if source_count else 0.0
        displaced_pressure = _safe_float(displacement.get("displaced_pressure"), 0.0)
        aviation_disruption = _safe_float(aviation.get("aviation_disruption_score"), 0.0)
        logistics_stress = _safe_float(logistics.get("logistics_stress_score"), 0.0)
        severity = round(min(displaced_pressure * 0.4 + aviation_disruption * 0.3 + logistics_stress * 0.2 + freshness * 0.05 + confidence * 0.05, 1.0), 4)
        top_rows.append({
            "country": code,
            "country_name": COUNTRY_NAMES.get(code) or catalog.get(code, code),
            "risk_score": round(_safe_float(preferred_features.get("global_risk_score"), 0.0), 4),
            "severity_score": severity,
            "normalized_displaced_pressure": round(displaced_pressure, 4),
            "aviation_disruption_score": round(aviation_disruption, 4),
            "logistics_stress_score": round(logistics_stress, 4),
            "freshness_score": freshness,
            "confidence_score": confidence,
            "displaced_people": round(_safe_float(displacement.get("displaced_people"), 0.0), 0),
            "aircraft_count": round(_safe_float(aviation.get("aircraft_count"), 0.0), 0),
            "direct_behavior_score": round(_safe_float(preferred_features.get("direct_behavior_score"), 0.0), 4),
            "contextual_pressure_score": round(_safe_float(preferred_features.get("contextual_pressure_score"), 0.0), 4),
            "household_stress_score": round(_safe_float(preferred_features.get("household_stress_score"), 0.0), 4),
            "fuel_price_pressure": round(_safe_float(preferred_features.get("fuel_price_pressure"), 0.0), 4),
            "food_price_pressure": round(_safe_float(preferred_features.get("food_price_pressure"), 0.0), 4),
            "labor_stress_score": round(_safe_float(preferred_features.get("labor_stress_score"), 0.0), 4),
            "fx_pressure_score": round(_safe_float(preferred_features.get("fx_pressure_score"), 0.0), 4),
            "remittance_stress_score": round(_safe_float(preferred_features.get("remittance_stress_score"), 0.0), 4),
            "energy_stress_score": round(_safe_float(preferred_features.get("energy_stress_score"), 0.0), 4),
            "displacement_updated_at": displacement.get("stamp").isoformat() if displacement.get("stamp") else None,
            "aviation_updated_at": aviation.get("stamp").isoformat() if aviation.get("stamp") else None,
            "logistics_updated_at": logistics.get("stamp").isoformat() if logistics.get("stamp") else None,
            "source_count": source_count,
        })

    top_rows.sort(key=lambda item: (item["severity_score"], item["normalized_displaced_pressure"], item["aviation_disruption_score"], item["logistics_stress_score"], item["freshness_score"], item["confidence_score"]), reverse=True)
    overlap_count = len(set(latest_displacement.keys()) & set(latest_aviation.keys()))
    displacement_latest = max((payload["stamp"] for payload in latest_displacement.values()), default=None)
    aviation_latest = max((payload["stamp"] for payload in latest_aviation.values()), default=None)
    logistics_latest = max((payload["stamp"] for payload in latest_logistics.values()), default=None)

    displacement_history = [
        {"period": period, "country_count": len(countries)}
        for period, countries in sorted(displacement_daily.items())[-7:]
    ]
    aviation_history = [
        {"period": period, "country_count": len(countries)}
        for period, countries in sorted(aviation_hourly.items())[-12:]
    ]
    combined_history = [
        {"period": period, "country_count": len(countries)}
        for period, countries in sorted(combined_daily.items())[-7:]
    ]

    displacement_delta = 0
    if len(displacement_history) >= 2:
        displacement_delta = int(displacement_history[-1]["country_count"] - displacement_history[-2]["country_count"])
    aviation_delta = 0
    if len(aviation_history) >= 2:
        aviation_delta = int(aviation_history[-1]["country_count"] - aviation_history[-2]["country_count"])
    combined_delta = 0
    if len(combined_history) >= 2:
        combined_delta = int(combined_history[-1]["country_count"] - combined_history[-2]["country_count"])

    return {
        "generated_at": now_utc.isoformat(),
        "status": "healthy" if union_countries else "monitoring",
        "sources": {
            "displacement": {
                "source": "unhcr_idmc",
                "country_count": len(latest_displacement),
                "window_hours": displacement_window_hours,
                "last_updated": displacement_latest.isoformat() if displacement_latest else None,
            },
            "aviation": {
                "source": "opensky",
                "country_count": len(latest_aviation),
                "window_hours": aviation_window_hours,
                "last_updated": aviation_latest.isoformat() if aviation_latest else None,
            },
            "logistics": {
                "source": "worldbank_logistics",
                "country_count": len(latest_logistics),
                "window_hours": max(displacement_window_hours, 96),
                "last_updated": logistics_latest.isoformat() if logistics_latest else None,
            },
        },
        "combined_country_count": len(union_countries),
        "crosscheck_overlap_count": overlap_count,
        "crosscheck_overlap_ratio": round((overlap_count / max(len(union_countries), 1)), 4),
        "trend": {
            "displacement_delta": displacement_delta,
            "aviation_delta": aviation_delta,
            "combined_delta": combined_delta,
            "displacement_daily": displacement_history,
            "aviation_hourly": aviation_history,
            "combined_daily": combined_history,
        },
        "top_countries": top_rows[:max_countries],
    }


def _build_economic_observability(window_hours: int = 96, max_countries: int = 12) -> dict:
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(hours=window_hours)
    docs = list(db.economic_behavior.find({}, {"_id": 0, "country": 1, "country_name": 1, "collected_at": 1, "timestamp": 1, "data": 1}).sort("_id", DESCENDING).limit(8000))

    latest_by_country: dict[str, dict[str, Any]] = {}
    daily_country_sets: dict[str, set[str]] = {}
    total_household = 0.0
    total_fuel = 0.0
    total_food = 0.0
    total_labor = 0.0
    total_fx = 0.0
    measured = 0

    for doc in docs:
        stamp = _parse_timestamp(doc.get("timestamp") or doc.get("collected_at"))
        if stamp < cutoff:
            continue
        country = str(doc.get("country") or "").strip().upper()
        payload = doc.get("data") if isinstance(doc.get("data"), dict) else {}
        if not country or not payload:
            continue
        day_key = stamp.astimezone(timezone.utc).date().isoformat()
        daily_country_sets.setdefault(day_key, set()).add(country)
        if country not in latest_by_country:
            household = _safe_float(payload.get("household_stress_score"), 0.0)
            fuel = _safe_float(payload.get("fuel_price_pressure"), 0.0)
            food = _safe_float(payload.get("food_price_pressure"), 0.0)
            labor = _safe_float(payload.get("labor_stress_score"), 0.0)
            fx = _safe_float(payload.get("fx_pressure_score"), 0.0)
            latest_by_country[country] = {
                "country": country,
                "country_name": doc.get("country_name") or COUNTRY_NAMES.get(country, country),
                "timestamp": stamp.isoformat(),
                "household_stress_score": round(household, 4),
                "fuel_price_pressure": round(fuel, 4),
                "food_price_pressure": round(food, 4),
                "labor_stress_score": round(labor, 4),
                "fx_pressure_score": round(fx, 4),
                "component_sources": payload.get("component_sources") if isinstance(payload.get("component_sources"), list) else [],
            }
            total_household += household
            total_fuel += fuel
            total_food += food
            total_labor += labor
            total_fx += fx
            measured += 1

    trend_history = [
        {"period": period, "country_count": len(countries)}
        for period, countries in sorted(daily_country_sets.items())[-7:]
    ]
    coverage_delta = 0
    if len(trend_history) >= 2:
        coverage_delta = int(trend_history[-1]["country_count"] - trend_history[-2]["country_count"])

    top_countries = sorted(
        latest_by_country.values(),
        key=lambda item: (item["household_stress_score"], item["fuel_price_pressure"], item["food_price_pressure"], item["labor_stress_score"]),
        reverse=True,
    )[:max_countries]
    last_updated = max((_parse_timestamp(item["timestamp"]) for item in latest_by_country.values()), default=None)

    return {
        "status": "healthy" if latest_by_country else "monitoring",
        "source": "economic_behavior",
        "window_hours": window_hours,
        "country_count": len(latest_by_country),
        "last_updated": last_updated.isoformat() if last_updated else None,
        "averages": {
            "household_stress_score": round((total_household / measured), 4) if measured else 0.0,
            "fuel_price_pressure": round((total_fuel / measured), 4) if measured else 0.0,
            "food_price_pressure": round((total_food / measured), 4) if measured else 0.0,
            "labor_stress_score": round((total_labor / measured), 4) if measured else 0.0,
            "fx_pressure_score": round((total_fx / measured), 4) if measured else 0.0,
        },
        "trend": {
            "coverage_delta": coverage_delta,
            "daily_country_counts": trend_history,
        },
        "top_countries": top_countries,
    }


def _build_operational_alerts(latest_ingestion: dict, source_health: dict, mobility_snapshot: dict, economic_snapshot: dict) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    for row in (latest_ingestion or {}).get("sources", []) if isinstance((latest_ingestion or {}).get("sources"), list) else []:
        if row.get("status") == "stale":
            source_name = str(row.get("source") or "")
            alerts.append({
                "severity": "medium" if row.get("tier") == "core" else ("medium" if source_name in {"mobility", "aviation", "economic_behavior", "weather", "trends"} else "low"),
                "category": "source_stale",
                "source": source_name,
                "source_label": _source_label(source_name),
                "message": f"{_source_label(source_name)} is stale at {row.get('age_hours')}h against {row.get('sla_hours')}h SLA.",
            })

    for row in (source_health or {}).get("sources", []) if isinstance((source_health or {}).get("sources"), list) else []:
        source_name = str(row.get("source") or "")
        source_label = _source_label(source_name)
        if row.get("rate_limited"):
            alerts.append({
                "severity": "high" if source_name in {"opensky", "unhcr_idmc"} else "medium",
                "category": "rate_limited",
                "source": source_name,
                "source_label": source_label,
                "message": f"{source_label} is reporting rate limits.",
            })
        if row.get("auth_failed"):
            alerts.append({
                "severity": "high",
                "category": "auth_failed",
                "source": source_name,
                "source_label": source_label,
                "message": f"{source_label} authentication failed.",
            })
        if str(row.get("status") or "").lower() == "down" and source_name in {"unhcr_idmc", "opensky", "worldbank_behavior_SL.UEM.TOTL.ZS", "worldbank_behavior_FP.CPI.TOTL.ZG", "fred_behavior", "eia_behavior", "frankfurter_behavior"}:
            alerts.append({
                "severity": "high" if source_name in {"unhcr_idmc", "opensky"} else "medium",
                "category": "source_down",
                "source": source_name,
                "source_label": source_label,
                "message": f"{source_label} is down: {row.get('error') or 'no detail'}",
            })

    mobility_sources = (mobility_snapshot or {}).get("sources") if isinstance((mobility_snapshot or {}).get("sources"), dict) else {}
    displacement = mobility_sources.get("displacement") if isinstance(mobility_sources, dict) else {}
    aviation = mobility_sources.get("aviation") if isinstance(mobility_sources, dict) else {}
    if isinstance(displacement, dict) and int(displacement.get("country_count", 0) or 0) == 0:
        alerts.append({
            "severity": "high",
            "category": "zero_country_ingest",
            "source": "unhcr_idmc",
            "message": "Mobility displacement ingest returned zero countries in the current window.",
        })
    if isinstance(aviation, dict) and int(aviation.get("country_count", 0) or 0) == 0:
        alerts.append({
            "severity": "high",
            "category": "zero_country_ingest",
            "source": "opensky",
            "message": "Aviation ingest returned zero countries in the current window.",
        })
    mobility_trend = (mobility_snapshot or {}).get("trend") if isinstance((mobility_snapshot or {}).get("trend"), dict) else {}
    if int(mobility_trend.get("combined_delta", 0) or 0) <= -8:
        alerts.append({
            "severity": "medium",
            "category": "coverage_drop",
            "source": "mobility",
            "message": f"Mobility cross-check coverage dropped by {int(mobility_trend.get('combined_delta', 0) or 0)} countries.",
        })

    if int((economic_snapshot or {}).get("country_count", 0) or 0) == 0:
        alerts.append({
            "severity": "high",
            "category": "zero_country_ingest",
            "source": "economic_behavior",
            "message": "Economic behavior ingest returned zero countries in the current window.",
        })
    economic_trend = (economic_snapshot or {}).get("trend") if isinstance((economic_snapshot or {}).get("trend"), dict) else {}
    if int(economic_trend.get("coverage_delta", 0) or 0) <= -12:
        alerts.append({
            "severity": "medium",
            "category": "coverage_drop",
            "source": "economic_behavior",
            "message": f"Economic behavior coverage dropped by {int(economic_trend.get('coverage_delta', 0) or 0)} countries.",
        })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda item: (severity_order.get(str(item.get("severity")), 3), str(item.get("source") or ""), str(item.get("category") or "")))
    return alerts[:24]


def get_country_risk_dependency_health(mode: str = "online"):
    status = {
        "database": "connected",
        "model_loaded": False,
        "country_features_latest": None,
        "country_news_latest": None,
        "wiki_latest": None,
        "mobility_latest": None,
        "aviation_latest": None,
        "economic_behavior_latest": None,
        "trends_latest": None,
        "weather_latest": None,
        "attention": _build_attention_observability(window_hours=48, max_countries=6),
        "mobility": _build_mobility_observability(displacement_window_hours=72, aviation_window_hours=18, max_countries=6),
        "validation_status": latest_country_risk_validation().get("status"),
    }
    model, version = load_production_model()
    status["model_loaded"] = model is not None
    status["model_version"] = version

    for name, collection_name in [("country_features_latest", "country_features"), ("country_news_latest", "country_news"), ("wiki_latest", "wiki"), ("mobility_latest", "mobility"), ("aviation_latest", "aviation"), ("economic_behavior_latest", "economic_behavior"), ("trends_latest", "trends"), ("weather_latest", "weather")]:
        status[name] = _latest_collection_stamp(db[collection_name], ["timestamp", "collected_at", "published_at", "data_timestamp", "snapshot_at", "snapshot_date"])

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

def load_production_model_bundle() -> tuple[Any | None, str | None, list[str], str]:
    model_path = get_production_model()
    if not model_path or not os.path.exists(model_path):
        return None, None, DEFAULT_PREDICTION_FEATURES, PREDICTION_SCHEMA_VERSION
    models = list_models()
    for version, info in models.items():
        if info.get("stage") == "production":
            if model_cache["version"] != version:
                loaded = joblib.load(model_path)
                feature_names = list(info.get("feature_names") or [])
                schema_version = str(info.get("schema_version") or PREDICTION_SCHEMA_VERSION)
                if isinstance(loaded, dict) and "model" in loaded:
                    model_cache["model"] = loaded.get("model")
                    feature_names = list(loaded.get("feature_names") or feature_names or DEFAULT_PREDICTION_FEATURES)
                    schema_version = str(loaded.get("schema_version") or schema_version)
                else:
                    model_cache["model"] = loaded
                    if not feature_names:
                        feature_names = DEFAULT_PREDICTION_FEATURES if getattr(loaded, "n_features_in_", 0) == len(DEFAULT_PREDICTION_FEATURES) else LEGACY_GLOBAL_PREDICTION_FEATURES
                model_cache["version"] = version
                model_cache["feature_names"] = feature_names
                model_cache["schema_version"] = schema_version
            return (
                model_cache["model"],
                version,
                list(model_cache.get("feature_names") or DEFAULT_PREDICTION_FEATURES),
                str(model_cache.get("schema_version") or PREDICTION_SCHEMA_VERSION),
            )
    return None, None, DEFAULT_PREDICTION_FEATURES, PREDICTION_SCHEMA_VERSION


def load_production_model():
    model, version, _, _ = load_production_model_bundle()
    return model, version


def _current_prediction_feature_names(model: Any | None = None) -> list[str]:
    names = list(model_cache.get("feature_names") or [])
    if names:
        return names
    expected = int(getattr(model, "n_features_in_", 0) or 0)
    if expected == len(DEFAULT_PREDICTION_FEATURES):
        return list(DEFAULT_PREDICTION_FEATURES)
    if expected == len(LEGACY_GLOBAL_PREDICTION_FEATURES):
        return list(LEGACY_GLOBAL_PREDICTION_FEATURES)
    return list(DEFAULT_PREDICTION_FEATURES)


def _current_prediction_schema_version() -> str:
    return str(model_cache.get("schema_version") or PREDICTION_SCHEMA_VERSION)


def compute_feature_drift(payload_features: list[float], feature_names: list[str] | None = None) -> float | None:
    expected_order = list(feature_names or _current_prediction_feature_names())

    if len(payload_features) != len(expected_order):
        return None

    history = get_global_history(mode="online", limit=24)
    if not history:
        return None

    # Compare against a short rolling baseline (excluding the newest point when possible)
    # so drift can capture changes instead of collapsing to zero against the current row.
    baseline_rows = history[:-1] if len(history) > 1 else history
    baseline_vec: list[float] = []
    for field in expected_order:
        samples: list[float] = []
        for row in baseline_rows:
            features = (row or {}).get("features") or {}
            try:
                samples.append(float(features.get(field, 0.0) or 0.0))
            except (TypeError, ValueError):
                continue
        baseline_vec.append(sum(samples) / len(samples) if samples else 0.0)

    drift_components = []
    for observed, expected in zip(payload_features, baseline_vec):
        denom = abs(expected) + 1e-6
        drift_components.append(abs(float(observed) - expected) / denom)

    return round(sum(drift_components) / len(drift_components), 6)


def _aggregate_latest_global_from_country_features(mode: str = "online") -> dict | None:
    pipeline = [
        {"$match": {"mode": mode}},
        {"$sort": {"timestamp": -1}},
        {"$group": {"_id": "$country", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$limit": 500},
    ]
    docs = list(country_features_collection.aggregate(pipeline))
    if not docs:
        return None

    fields = [
        "news_sentiment",
        "gdelt_sentiment",
        "crypto_return",
        "crypto_volatility",
        "stock_return",
        "stock_volatility",
        "weather_anomaly",
        "global_risk_score",
    ]
    sums = {field: 0.0 for field in fields}
    counts = {field: 0 for field in fields}
    topic_counts: dict[str, int] = defaultdict(int)
    latest_ts: datetime | None = None

    for doc in docs:
        features = doc.get("features") if isinstance(doc.get("features"), dict) else {}
        ts = _coerce_utc_datetime(features.get("timestamp") or doc.get("timestamp"))
        if ts and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

        for field in fields:
            try:
                value = float(features.get(field, 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            sums[field] += value
            counts[field] += 1

        topics = features.get("top_topics")
        if isinstance(topics, list):
            for item in topics[:3]:
                if isinstance(item, str) and item.strip():
                    topic_counts[item.strip().lower()] += 1

    aggregated_features = {
        field: round((sums[field] / counts[field]) if counts[field] else 0.0, 6)
        for field in fields
    }
    aggregated_features["timestamp"] = (latest_ts or datetime.utcnow()).isoformat()
    aggregated_features["source_count"] = len(docs)
    aggregated_features["top_topics"] = [topic for topic, _ in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]] or ["country aggregate"]

    return {
        "mode": mode,
        "version": -1,
        "timestamp": aggregated_features["timestamp"],
        "features": aggregated_features,
    }


def _aggregate_global_history_from_country_features(
    mode: str = "online",
    limit: int = 1000,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict]:
    query: dict[str, Any] = {"mode": mode}
    if start_date or end_date:
        ts_filter: dict[str, datetime] = {}
        if start_date:
            ts_filter["$gte"] = start_date
        if end_date:
            ts_filter["$lte"] = end_date
        query["timestamp"] = ts_filter

    max_docs = min(max(limit * 80, 500), 30000)
    docs = list(
        country_features_collection
        .find(query, {"timestamp": 1, "features": 1, "country": 1})
        .sort("timestamp", DESCENDING)
        .limit(max_docs)
    )
    if not docs:
        return []

    signal_fields = [
        "news_sentiment",
        "gdelt_sentiment",
        "crypto_return",
        "crypto_volatility",
        "stock_return",
        "stock_volatility",
        "weather_anomaly",
        "global_risk_score",
        "public_attention_score",
        "direct_behavior_score",
        "contextual_pressure_score",
        "evidence_quality_score",
        "narrative_velocity_score",
        "coordination_risk_score",
        "mobility_disruption_score",
        "logistics_stress_score",
        "household_stress_score",
        "fuel_price_pressure",
        "food_price_pressure",
        "labor_stress_score",
        "fx_pressure_score",
        "remittance_stress_score",
        "energy_stress_score",
    ]
    buckets: dict[str, dict[str, Any]] = {}

    for doc in docs:
        features = doc.get("features") if isinstance(doc.get("features"), dict) else {}
        ts = _coerce_utc_datetime(features.get("timestamp") or doc.get("timestamp"))
        if ts is None:
            continue
        if start_date and ts < start_date:
            continue
        if end_date and ts > end_date:
            continue

        bucket_ts = ts.replace(minute=0, second=0, microsecond=0)
        bucket_key = bucket_ts.isoformat()
        if bucket_key not in buckets:
            buckets[bucket_key] = {
                "timestamp": bucket_ts,
                "sums": {field: 0.0 for field in signal_fields},
                "counts": {field: 0 for field in signal_fields},
                "countries": set(),
            }

        bucket = buckets[bucket_key]
        country_code = str(doc.get("country") or "").upper().strip()
        if country_code:
            bucket["countries"].add(country_code)

        for field in signal_fields:
            try:
                value = float(features.get(field, 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            bucket["sums"][field] += value
            bucket["counts"][field] += 1

    ordered = sorted(buckets.values(), key=lambda row: row["timestamp"])
    if len(ordered) > limit:
        ordered = ordered[-limit:]

    history_rows: list[dict] = []
    for row in ordered:
        features: dict[str, Any] = {}
        for field in signal_fields:
            count = row["counts"][field]
            features[field] = round((row["sums"][field] / count) if count else 0.0, 6)
        features["global_behavior_index"] = round(float(features["direct_behavior_score"]), 2)
        features["global_context_index"] = round(float(features["contextual_pressure_score"]), 2)
        features["global_attention_index"] = round(((float(features["public_attention_score"]) * 100.0) + (float(features["narrative_velocity_score"]) * 100.0)) / 2.0, 2)
        features["global_disruption_index"] = round(((float(features["mobility_disruption_score"]) * 100.0) + (float(features["logistics_stress_score"]) * 100.0)) / 2.0, 2)
        features["global_economic_stress_index"] = round(((float(features["household_stress_score"]) * 100.0) + (float(features["energy_stress_score"]) * 100.0) + (float(features["remittance_stress_score"]) * 100.0)) / 3.0, 2)
        features["timestamp"] = row["timestamp"].isoformat()
        features["source_count"] = len(row["countries"])
        history_rows.append({
            "mode": mode,
            "timestamp": row["timestamp"].isoformat(),
            "features": features,
        })

    return history_rows

def _derive_global_history_from_raw_mongo(
    mode: str = "online",
    limit: int = 200,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict]:
    # Build hourly snapshots from live raw collections when feature tables are sparse.
    now_dt = datetime.utcnow()
    end_dt = end_date or now_dt
    lookback_hours = max(24, min(limit * 3, 24 * 14))
    start_dt = start_date or (end_dt - timedelta(hours=lookback_hours))

    news_docs = list(
        db.country_news.find(
            {"timestamp": {"$gte": start_dt, "$lte": end_dt}},
            {"timestamp": 1, "data.sentiment.vader.compound": 1, "data.sentiment.compound": 1, "country": 1},
        ).sort("timestamp", DESCENDING).limit(60000)
    )
    gdelt_docs = list(
        db.gdelt.find(
            {"collected_at": {"$gte": start_dt, "$lte": end_dt}},
            {"collected_at": 1, "data.sentiment.vader.compound": 1, "data.sentiment.compound": 1},
        ).sort("collected_at", DESCENDING).limit(60000)
    )
    crypto_docs = list(
        db.crypto.find(
            {"collected_at": {"$gte": start_dt, "$lte": end_dt}},
            {"collected_at": 1, "data_price": 1, "data.price": 1, "price": 1},
        ).sort("collected_at", DESCENDING).limit(30000)
    )
    stock_docs = list(
        db.stocks.find(
            {"collected_at": {"$gte": start_dt, "$lte": end_dt}},
            {"collected_at": 1, "close": 1, "data.close": 1, "price": 1, "data.price": 1},
        ).sort("collected_at", DESCENDING).limit(30000)
    )
    weather_docs = list(
        db.weather.find(
            {"collected_at": {"$gte": start_dt, "$lte": end_dt}},
            {"collected_at": 1, "data_temperature": 1, "data.temperature": 1, "temperature": 1},
        ).sort("collected_at", DESCENDING).limit(30000)
    )

    buckets: dict[str, dict[str, Any]] = {}

    def _bucket_key(ts: datetime) -> str:
        return ts.replace(minute=0, second=0, microsecond=0).isoformat()

    def _ensure_bucket(ts: datetime) -> dict[str, Any]:
        key = _bucket_key(ts)
        if key not in buckets:
            buckets[key] = {
                "timestamp": ts.replace(minute=0, second=0, microsecond=0),
                "news_vals": [],
                "gdelt_vals": [],
                "crypto_prices": [],
                "stock_prices": [],
                "temps": [],
                "countries": set(),
            }
        return buckets[key]

    for doc in news_docs:
        ts = _coerce_utc_datetime(doc.get("timestamp")) or _coerce_utc_datetime(doc.get("collected_at"))
        if ts is None:
            continue
        b = _ensure_bucket(ts)
        sent = _parse_float_maybe(_extract_nested_value(doc, "data.sentiment.vader.compound", "data.sentiment.compound"))
        if sent is not None and np.isfinite(sent):
            b["news_vals"].append(float(sent))
        country = str(doc.get("country") or "").strip().upper()
        if country:
            b["countries"].add(country)

    for doc in gdelt_docs:
        ts = _coerce_utc_datetime(doc.get("collected_at")) or _coerce_utc_datetime(doc.get("timestamp"))
        if ts is None:
            continue
        b = _ensure_bucket(ts)
        sent = _parse_float_maybe(_extract_nested_value(doc, "data.sentiment.vader.compound", "data.sentiment.compound"))
        if sent is not None and np.isfinite(sent):
            b["gdelt_vals"].append(float(sent))

    for doc in crypto_docs:
        ts = _coerce_utc_datetime(doc.get("collected_at")) or _coerce_utc_datetime(doc.get("data_timestamp"))
        if ts is None:
            continue
        b = _ensure_bucket(ts)
        p = _parse_float_maybe(_extract_nested_value(doc, "data_price", "data.price", "price"))
        if p is not None and np.isfinite(p):
            b["crypto_prices"].append(float(p))

    for doc in stock_docs:
        ts = _coerce_utc_datetime(doc.get("collected_at")) or _coerce_utc_datetime(doc.get("timestamp"))
        if ts is None:
            continue
        b = _ensure_bucket(ts)
        p = _parse_float_maybe(_extract_nested_value(doc, "close", "data.close", "price", "data.price"))
        if p is not None and np.isfinite(p):
            b["stock_prices"].append(float(p))

    for doc in weather_docs:
        ts = _coerce_utc_datetime(doc.get("collected_at")) or _coerce_utc_datetime(doc.get("data_timestamp"))
        if ts is None:
            continue
        b = _ensure_bucket(ts)
        t = _parse_float_maybe(_extract_nested_value(doc, "data_temperature", "data.temperature", "temperature", "temp"))
        if t is not None and np.isfinite(t):
            b["temps"].append(float(t))

    ordered_keys = sorted(buckets.keys())
    if not ordered_keys:
        return []

    rows: list[dict] = []
    prev_crypto_mean: float | None = None
    prev_stock_mean: float | None = None
    prev_temp_mean: float | None = None
    prev_volume: float | None = None

    for key in ordered_keys:
        b = buckets[key]
        ts = b["timestamp"]
        news_mean = float(np.mean(b["news_vals"])) if b["news_vals"] else 0.0
        gdelt_mean = float(np.mean(b["gdelt_vals"])) if b["gdelt_vals"] else 0.0
        crypto_mean = float(np.mean(b["crypto_prices"])) if b["crypto_prices"] else (prev_crypto_mean or 0.0)
        stock_mean = float(np.mean(b["stock_prices"])) if b["stock_prices"] else (prev_stock_mean or 0.0)
        temp_mean = float(np.mean(b["temps"])) if b["temps"] else (prev_temp_mean or 0.0)

        crypto_return = ((crypto_mean - prev_crypto_mean) / prev_crypto_mean) if (prev_crypto_mean and abs(prev_crypto_mean) > 1e-12) else 0.0
        stock_return = ((stock_mean - prev_stock_mean) / prev_stock_mean) if (prev_stock_mean and abs(prev_stock_mean) > 1e-12) else 0.0
        weather_anomaly = (temp_mean - prev_temp_mean) if prev_temp_mean is not None else 0.0

        volume = float(len(b["news_vals"]) + len(b["gdelt_vals"]))
        volume_delta = (volume - prev_volume) if prev_volume is not None else 0.0
        crypto_volatility = abs(float(crypto_return))
        stock_volatility = abs(float(stock_return))
        volume_pressure = min(16.0, max(0.0, volume / 15.0) + max(0.0, volume_delta / 20.0))
        risk = 50.0 - (20.0 * ((0.6 * news_mean) + (0.4 * gdelt_mean))) + (110.0 * min(crypto_volatility, 0.25)) + (90.0 * min(stock_volatility, 0.25)) + (10.0 * min(abs(weather_anomaly), 2.0)) + volume_pressure
        risk = max(0.0, min(100.0, float(risk)))

        features = {
            "timestamp": ts.isoformat(),
            "news_sentiment": round(news_mean, 6),
            "gdelt_sentiment": round(gdelt_mean, 6),
            "crypto_return": round(float(crypto_return), 6),
            "crypto_volatility": round(float(crypto_volatility), 6),
            "stock_return": round(float(stock_return), 6),
            "stock_volatility": round(float(stock_volatility), 6),
            "weather_anomaly": round(float(weather_anomaly), 6),
            "global_risk_score": round(risk, 2),
            "source_count": int(len(b["countries"])),
            "top_topics": ["live-signals"],
        }
        rows.append({"mode": mode, "timestamp": ts.isoformat(), "features": features})

        prev_crypto_mean = crypto_mean
        prev_stock_mean = stock_mean
        prev_temp_mean = temp_mean
        prev_volume = volume

    if len(rows) > limit:
        rows = rows[-limit:]
    return rows


def _derive_country_risk_map_from_country_news(mode: str = "online") -> list[dict]:
    now_dt = datetime.utcnow()
    since = now_dt - timedelta(hours=72)
    docs = list(
        db.country_news.find(
            {"timestamp": {"$gte": since}},
            {"country": 1, "timestamp": 1, "data.sentiment.vader.compound": 1, "data.sentiment.compound": 1, "data.title": 1},
        ).sort("timestamp", DESCENDING).limit(80000)
    )
    if not docs:
        return []

    grouped: dict[str, dict[str, Any]] = {}
    for doc in docs:
        country = convert_country_code(str(doc.get("country") or "").upper().strip())
        if not country:
            continue
        g = grouped.setdefault(country, {"sentiments": [], "count": 0, "latest_ts": None, "tokens": defaultdict(int)})
        g["count"] += 1
        ts = _coerce_utc_datetime(doc.get("timestamp")) or _coerce_utc_datetime(doc.get("collected_at"))
        if ts and (g["latest_ts"] is None or ts > g["latest_ts"]):
            g["latest_ts"] = ts
        sent = _parse_float_maybe(_extract_nested_value(doc, "data.sentiment.vader.compound", "data.sentiment.compound"))
        if sent is not None and np.isfinite(sent):
            g["sentiments"].append(float(sent))
        title = str(_extract_nested_value(doc, "data.title", "title") or "").lower()
        for token in re.findall(r"[a-zA-Z]{4,}", title):
            if token in {"with", "from", "after", "amid", "global", "country", "update", "latest"}:
                continue
            g["tokens"][token] += 1

    response_docs = []
    for country, g in grouped.items():
        sent_mean = float(np.mean(g["sentiments"])) if g["sentiments"] else 0.0
        volume = float(g["count"])
        volume_boost = min(18.0, volume / 12.0)
        risk = max(0.0, min(100.0, 50.0 - (28.0 * sent_mean) + volume_boost))
        top_topics = [t for t, _ in sorted(g["tokens"].items(), key=lambda kv: kv[1], reverse=True)[:3]]
        ts = g["latest_ts"] or now_dt
        quality = assess_country_risk_quality(top_topics, ts.isoformat())
        response_docs.append(
            {
                "country": country,
                "risk": round(float(risk), 2),
                "timestamp": ts.isoformat(),
                "feature_timestamp": ts.isoformat(),
                "source_count": int(volume),
                "social_unrest_score": 0.0,
                "google_trends_pressure": 0.0,
                "weather_stress": 0.0,
                "external_signal_freshness": 0.0,
                "war_state_rules": [],
                **quality,
                "data_quality": "derived_live",
            }
        )

    return sorted(response_docs, key=lambda d: (_coerce_utc_datetime(d.get("timestamp")) or now_dt), reverse=True)


def _extract_nested_value(doc: dict, *paths: str):
    for path in paths:
        current = doc
        ok = True
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current.get(part)
            else:
                ok = False
                break
        if ok and current not in (None, ""):
            return current
    return None


def _parse_float_maybe(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        if not match:
            return None
        try:
            return float(match.group(0))
        except (TypeError, ValueError):
            return None


def _compute_series_return_and_vol(series: list[float]) -> tuple[float, float]:
    clean = [float(v) for v in series if v is not None]
    if len(clean) < 2:
        return 0.0, 0.0
    first = clean[-1]
    last = clean[0]
    if abs(first) < 1e-12:
        ret = 0.0
    else:
        ret = (last - first) / first
    steps = []
    for i in range(len(clean) - 1):
        base = clean[i + 1]
        if abs(base) < 1e-12:
            continue
        steps.append((clean[i] - base) / base)
    vol = float(np.std(steps)) if steps else 0.0
    return float(ret), float(vol)


def _derive_live_global_from_raw_mongo(mode: str = "online") -> dict | None:
    now_dt = datetime.utcnow()
    now_iso = now_dt.isoformat()

    # Sentiment signals from raw collections (live Mongo data only).
    news_docs = list(db.news.find({}, {"data": 1, "sentiment": 1, "timestamp": 1, "collected_at": 1}).sort("_id", -1).limit(600))
    gdelt_docs = list(db.gdelt.find({}, {"data": 1, "sentiment": 1, "timestamp": 1, "collected_at": 1}).sort("_id", -1).limit(900))
    country_news_docs = list(db.country_news.find({}, {"data": 1, "timestamp": 1, "collected_at": 1, "source": 1}).sort("_id", -1).limit(1200))

    def _collect_sentiments(docs: list[dict]) -> list[float]:
        out = []
        for doc in docs:
            value = _extract_nested_value(
                doc,
                "data.sentiment.vader.compound",
                "data.sentiment.compound",
                "sentiment.vader.compound",
                "sentiment.compound",
                "data.vader.compound",
                "data.sentiment",
                "sentiment",
            )
            parsed = _parse_float_maybe(value)
            if parsed is None:
                continue
            if np.isfinite(parsed):
                out.append(float(parsed))
        return out

    news_sentiments = _collect_sentiments(news_docs) + _collect_sentiments(country_news_docs)
    gdelt_sentiments = _collect_sentiments(gdelt_docs)
    news_sentiment = float(np.mean(news_sentiments)) if news_sentiments else 0.0
    gdelt_sentiment = float(np.mean(gdelt_sentiments)) if gdelt_sentiments else 0.0

    # Market signals.
    crypto_docs = list(db.crypto.find({}, {"data": 1, "data_price": 1, "price": 1, "data_timestamp": 1, "collected_at": 1}).sort("_id", -1).limit(220))
    crypto_prices = []
    for doc in crypto_docs:
        parsed = _parse_float_maybe(_extract_nested_value(doc, "data_price", "data.price", "price"))
        if parsed is not None and np.isfinite(parsed):
            crypto_prices.append(float(parsed))
    crypto_return, crypto_volatility = _compute_series_return_and_vol(crypto_prices)

    stocks_docs = list(db.stocks.find({}, {"data": 1, "close": 1, "price": 1, "timestamp": 1, "collected_at": 1}).sort("_id", -1).limit(260))
    stock_prices = []
    for doc in stocks_docs:
        parsed = _parse_float_maybe(_extract_nested_value(doc, "close", "data.close", "price", "data.price"))
        if parsed is not None and np.isfinite(parsed):
            stock_prices.append(float(parsed))
    stock_return, stock_volatility = _compute_series_return_and_vol(stock_prices)

    # Weather stress from temperature changes.
    weather_docs = list(db.weather.find({}, {"data": 1, "data_temperature": 1, "temperature": 1, "data_timestamp": 1, "collected_at": 1}).sort("_id", -1).limit(180))
    temps = []
    for doc in weather_docs:
        parsed = _parse_float_maybe(_extract_nested_value(doc, "data_temperature", "data.temperature", "temperature", "temp"))
        if parsed is not None and np.isfinite(parsed):
            temps.append(float(parsed))
    weather_anomaly = float(np.mean(np.diff(list(reversed(temps))))) if len(temps) >= 3 else 0.0

    # Pressure from current ingestion volumes (last 6h).
    six_hours_ago = now_dt - timedelta(hours=6)
    pressure_count = (
        db.gdelt.count_documents({"collected_at": {"$gte": six_hours_ago}})
        + db.country_news.count_documents({"timestamp": {"$gte": six_hours_ago}})
        + db.world_state_signals.count_documents({"timestamp_utc": {"$gte": six_hours_ago}})
    )
    volume_pressure = min(18.0, pressure_count / 90.0)

    # Dynamic risk from live signals (centered at 50 but moves with real ingestion data).
    sentiment_blend = (0.6 * news_sentiment) + (0.4 * gdelt_sentiment)
    risk_score = (
        50.0
        - (22.0 * sentiment_blend)
        + (120.0 * min(abs(crypto_volatility), 0.25))
        + (100.0 * min(abs(stock_volatility), 0.25))
        + (12.0 * min(abs(weather_anomaly), 2.0))
        + (12.0 * min(abs(crypto_return), 0.25))
        + (8.0 * min(abs(stock_return), 0.25))
        + volume_pressure
    )
    risk_score = max(0.0, min(100.0, float(risk_score)))

    # Lightweight live topics from recent country/news titles.
    token_counts: dict[str, int] = defaultdict(int)
    stop = {"the", "and", "from", "with", "that", "this", "into", "over", "after", "amid", "about", "global", "country", "update", "latest"}
    for doc in (country_news_docs[:350] + gdelt_docs[:350]):
        title = str(_extract_nested_value(doc, "data.title", "title", "data.headline") or "").strip().lower()
        if not title:
            continue
        for token in re.findall(r"[a-zA-Z]{4,}", title):
            if token in stop:
                continue
            token_counts[token] += 1
    top_topics = [word for word, _ in sorted(token_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]] or ["live-signals"]

    features = {
        "timestamp": now_iso,
        "news_sentiment": round(news_sentiment, 6),
        "gdelt_sentiment": round(gdelt_sentiment, 6),
        "crypto_return": round(float(crypto_return), 6),
        "crypto_volatility": round(float(crypto_volatility), 6),
        "stock_return": round(float(stock_return), 6),
        "stock_volatility": round(float(stock_volatility), 6),
        "weather_anomaly": round(float(weather_anomaly), 6),
        "global_risk_score": round(risk_score, 2),
        "top_topics": top_topics,
        "source_mode": "mongo_live_derived",
    }
    features.update(
        compute_global_operational_features(
            current_risk_score=float(features.get("legacy_model_global_risk_score", features["global_risk_score"]) or features["global_risk_score"]),
            mode=mode,
            current_timestamp=now_iso,
            use_cache=False,
        )
    )

    return {
        "timestamp": now_dt,
        "mode": mode,
        "version": int(time.time()),
        "features": features,
        "source": "mongo_live_derived",
    }


def _is_flat_neutral_global_series(mode: str = "online", sample: int = 6) -> bool:
    rows = list(
        db.global_features.find({"mode": mode}, {"features.global_risk_score": 1})
        .sort("timestamp", DESCENDING)
        .limit(max(sample, 3))
    )
    values = []
    for row in rows:
        features = row.get("features") if isinstance(row.get("features"), dict) else {}
        score = _parse_float_maybe(features.get("global_risk_score"))
        if score is None:
            continue
        values.append(float(score))
    if len(values) < 3:
        return False
    return max(values) - min(values) <= 0.1 and all(abs(v - 50.0) <= 0.1 for v in values)


def get_latest_global_doc(mode: str = "online") -> dict:
    def _candidate_timestamp(candidate: dict | None) -> datetime | None:
        if not candidate:
            return None
        candidate_features = candidate.get("features") if isinstance(candidate.get("features"), dict) else {}
        return _coerce_utc_datetime(candidate_features.get("timestamp") or candidate.get("timestamp"))

    global_doc = db.global_features.find_one({"mode": mode}, sort=[("timestamp", DESCENDING), ("_id", DESCENDING)])
    dashboard_doc = db.dashboard_features.find_one({"mode": mode}, sort=[("timestamp", DESCENDING), ("_id", DESCENDING)])
    global_ts = _candidate_timestamp(global_doc)
    dashboard_ts = _candidate_timestamp(dashboard_doc)

    if global_doc and dashboard_doc:
        if dashboard_ts and (global_ts is None or dashboard_ts > global_ts):
            doc = dashboard_doc
            doc_ts = dashboard_ts
        else:
            doc = global_doc
            doc_ts = global_ts
    else:
        doc = global_doc or dashboard_doc
        doc_ts = global_ts or dashboard_ts

    baseline_features = doc.get("features") if isinstance((doc or {}).get("features"), dict) else {}
    baseline_system_risk = _parse_float_maybe(baseline_features.get("system_global_risk_score"))
    if baseline_system_risk is None:
        baseline_system_risk = _parse_float_maybe(baseline_features.get("global_risk_score"))
    baseline_legacy_risk = _parse_float_maybe(baseline_features.get("legacy_model_global_risk_score"))

    country_latest_ts = _coerce_utc_datetime(
        _latest_collection_stamp(country_features_collection, ["timestamp", "collected_at", "created_at"], max_scan=5)
    )
    lag_seconds = (country_latest_ts - doc_ts).total_seconds() if country_latest_ts and doc_ts else None
    should_promote_country_aggregate = doc is None or doc_ts is None or (lag_seconds is not None and lag_seconds > 600)

    if should_promote_country_aggregate:
        country_derived_doc = _aggregate_latest_global_from_country_features(mode=mode)
        country_derived_ts = _candidate_timestamp(country_derived_doc)
        if country_derived_doc and (doc_ts is None or (country_derived_ts is not None and country_derived_ts > doc_ts)):
            doc = country_derived_doc
            doc_ts = country_derived_ts
            try:
                recent = db.global_features.find_one(
                    {"mode": mode, "source": "country_live_derived"},
                    sort=[("timestamp", DESCENDING), ("_id", DESCENDING)],
                )
                recent_ts = _candidate_timestamp(recent)
                if country_derived_ts is not None and (recent_ts is None or (country_derived_ts - recent_ts).total_seconds() > 60):
                    persisted_doc = dict(country_derived_doc)
                    persisted_doc["source"] = "country_live_derived"
                    db.global_features.insert_one(persisted_doc)
            except Exception:
                pass

    # If global risk is missing/flat-neutral, derive from live source collections.
    needs_live_repair = False
    if not doc:
        needs_live_repair = True
    else:
        features = doc.get("features") if isinstance(doc.get("features"), dict) else {}
        score = _parse_float_maybe(features.get("global_risk_score"))
        if score is None:
            needs_live_repair = True
        elif abs(float(score) - 50.0) <= 0.1 and _is_flat_neutral_global_series(mode=mode):
            needs_live_repair = True

    if needs_live_repair:
        derived_doc = _derive_live_global_from_raw_mongo(mode=mode)
        if derived_doc:
            doc = derived_doc
            try:
                recent = db.global_features.find_one(
                    {"mode": mode, "source": "mongo_live_derived"},
                    sort=[("timestamp", DESCENDING), ("_id", DESCENDING)],
                )
                recent_ts = _coerce_utc_datetime((recent or {}).get("timestamp"))
                if recent_ts is None or (datetime.utcnow().replace(tzinfo=timezone.utc) - recent_ts).total_seconds() > 60:
                    db.global_features.insert_one(derived_doc)
            except Exception:
                pass

    # No synthetic payloads: require live data from Mongo-backed sources.
    if not doc:
        raise HTTPException(status_code=404, detail=f"No live global features found for mode={mode}")

    doc = serialize_doc(doc)
    features = dict(doc.get("features") or {})
    current_timestamp = features.get("timestamp") or doc.get("timestamp")
    explicit_legacy_risk = _parse_float_maybe(features.get("legacy_model_global_risk_score"))
    explicit_system_risk = _parse_float_maybe(features.get("system_global_risk_score"))
    using_baseline_risk = explicit_legacy_risk is None and explicit_system_risk is None and baseline_system_risk is not None
    current_risk = explicit_legacy_risk
    if current_risk is None:
        current_risk = explicit_system_risk
    if current_risk is None and baseline_system_risk is not None:
        current_risk = baseline_system_risk
    if current_risk is None:
        current_risk = _parse_float_maybe(features.get("global_risk_score"))
    if current_risk is None:
        current_risk = 50.0
    current_risk = float(current_risk)
    features.update(
        compute_global_operational_features(
            current_risk_score=current_risk,
            mode=mode,
            current_timestamp=current_timestamp,
            use_cache=True,
        )
    )
    if using_baseline_risk and baseline_legacy_risk is not None:
        features["legacy_model_global_risk_score"] = float(baseline_legacy_risk)
        system_risk_score = _parse_float_maybe(features.get("system_global_risk_score"))
        if system_risk_score is not None:
            features["global_risk_alignment_gap"] = round(float(system_risk_score) - float(baseline_legacy_risk), 2)
    features["legacy_model_global_risk_score"] = float(features.get("legacy_model_global_risk_score", current_risk) or current_risk)
    features["global_risk_score"] = float(features.get("system_global_risk_score", current_risk) or current_risk)
    forecast_contract = _build_global_forecast_contract(mode=mode, features=features)
    features["forecast_contract"] = forecast_contract
    features["forecast_source_status"] = forecast_contract.get("source_status")
    features["forecast_calibration_status"] = forecast_contract.get("calibration_status")
    features["forecast_gating_action"] = forecast_contract.get("gating_action")
    features["forecast_prediction_available"] = forecast_contract.get("prediction_available")
    features["forecast_withheld"] = forecast_contract.get("withheld")
    features["forecast_confidence_score"] = forecast_contract.get("confidence_score")
    features["forecast_confidence"] = forecast_contract.get("confidence_ratio")
    features["forecast_prediction_interval"] = forecast_contract.get("prediction_interval")
    features["forecast_advisory"] = forecast_contract.get("advisory")
    features["forecast_reasons"] = forecast_contract.get("reasons")
    features["forecast_model_version"] = forecast_contract.get("model_version")
    features["forecast_generated_at"] = forecast_contract.get("generated_at")
    features["forecast_risk_score"] = forecast_contract.get("risk_score")
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



def _history_cross_domain_density(rows: list[dict]) -> int:
    signal_keys = (
        "direct_behavior_score",
        "contextual_pressure_score",
        "evidence_quality_score",
        "narrative_velocity_score",
        "coordination_risk_score",
        "mobility_disruption_score",
        "logistics_stress_score",
        "household_stress_score",
        "energy_stress_score",
        "global_behavior_index",
        "global_context_index",
        "global_attention_index",
        "global_disruption_index",
        "global_economic_stress_index",
    )
    density = 0
    for row in rows:
        features = (row or {}).get("features") or {}
        if not isinstance(features, dict):
            continue
        for key in signal_keys:
            value = _parse_float_maybe(features.get(key))
            if value is not None and abs(float(value)) > 1e-9:
                density += 1
    return density


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

    country_derived_rows = _aggregate_global_history_from_country_features(
        mode=mode,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )

    if not cursor:
        if country_derived_rows:
            return country_derived_rows
        return _derive_global_history_from_raw_mongo(
            mode=mode,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )

    rows = [serialize_doc(d) for d in reversed(cursor)]
    if country_derived_rows and _history_cross_domain_density(country_derived_rows) > _history_cross_domain_density(rows):
        rows = country_derived_rows

    if len(rows) >= 2:
        return rows

    # Augment sparse stored history with live-derived raw Mongo snapshots.
    derived_rows = _derive_global_history_from_raw_mongo(
        mode=mode,
        limit=max(limit, 72),
        start_date=start_date,
        end_date=end_date,
    )
    if not derived_rows:
        return rows

    merged: dict[str, dict] = {}
    for row in rows:
        ts = str((row.get("features") or {}).get("timestamp") or row.get("timestamp") or "")
        if ts:
            merged[ts] = row
    for row in derived_rows:
        ts = str((row.get("features") or {}).get("timestamp") or row.get("timestamp") or "")
        if ts and ts not in merged:
            merged[ts] = row

    merged_rows = sorted(
        merged.values(),
        key=lambda item: str((item.get("features") or {}).get("timestamp") or item.get("timestamp") or ""),
    )
    if len(merged_rows) > limit:
        merged_rows = merged_rows[-limit:]
    return merged_rows


# =====================================================
# Request Schema
# =====================================================
class PredictionRequest(BaseModel):
    features: list[float] | None = None
    feature_names: list[str] | None = None
    feature_map: dict[str, float] | None = None


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
    batch_size: int = 120
    max_records: int = 12


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
            "risk_score": float(f.get("system_global_risk_score", f.get("global_risk_score", 50.0))),
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
            "global_behavior_index": float(f.get("global_behavior_index", 0.0)),
            "global_context_index": float(f.get("global_context_index", 0.0)),
            "global_attention_index": float(f.get("global_attention_index", 0.0)),
            "global_disruption_index": float(f.get("global_disruption_index", 0.0)),
            "global_economic_stress_index": float(f.get("global_economic_stress_index", 0.0)),
            "direct_behavior_score": float(f.get("direct_behavior_score", 0.0)),
            "contextual_pressure_score": float(f.get("contextual_pressure_score", 0.0)),
            "evidence_quality_score": float(f.get("evidence_quality_score", 0.0)),
            "narrative_velocity_score": float(f.get("narrative_velocity_score", 0.0)),
            "coordination_risk_score": float(f.get("coordination_risk_score", 0.0)),
            "mobility_disruption_score": float(f.get("mobility_disruption_score", 0.0)),
            "logistics_stress_score": float(f.get("logistics_stress_score", 0.0)),
            "household_stress_score": float(f.get("household_stress_score", 0.0)),
            "fuel_price_pressure": float(f.get("fuel_price_pressure", 0.0)),
            "food_price_pressure": float(f.get("food_price_pressure", 0.0)),
            "labor_stress_score": float(f.get("labor_stress_score", 0.0)),
            "fx_pressure_score": float(f.get("fx_pressure_score", 0.0)),
            "remittance_stress_score": float(f.get("remittance_stress_score", 0.0)),
            "energy_stress_score": float(f.get("energy_stress_score", 0.0)),
            "forecast_risk_score": float(f.get("forecast_risk_score", f.get("system_global_risk_score", f.get("global_risk_score", 50.0)))),
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
    latest_features = latest.get("features") if isinstance(latest.get("features"), dict) else {}
    latest_ingestion = _build_latest_ingestion()
    core_candidates = [
        _coerce_utc_datetime(latest_ingestion.get("country_features")),
        _coerce_utc_datetime(latest_ingestion.get("global_features")),
        _coerce_utc_datetime(latest_ingestion.get("dashboard_features")),
        _coerce_utc_datetime(latest_features.get("timestamp")),
        _coerce_utc_datetime(latest.get("timestamp")),
    ]
    freshest_core_ts = max((stamp for stamp in core_candidates if stamp is not None), default=None)
    heartbeat = (datetime.now(timezone.utc) - freshest_core_ts).total_seconds() if freshest_core_ts else 0.0
    _trigger_country_refresh_async(heartbeat)

    features = latest_features
    topics = features.get("top_topics", ["no data"])
    incidents = [f"Topic pressure: {t}" for t in topics[:4]] or ["No active incidents"]

    drift_doc = model_monitoring_collection.find_one(sort=[("timestamp", DESCENDING)])
    model_drift = float((drift_doc or {}).get("drift_score", 0.0) or 0.0)
    last_updated = freshest_core_ts.isoformat() if freshest_core_ts else str(features.get("timestamp") or latest.get("timestamp") or datetime.utcnow().isoformat())

    return {
        "incidents": incidents,
        "ingestionHeartbeatSec": round(max(0.0, heartbeat), 2),
        "modelDrift": round(model_drift, 4),
        "lastUpdated": last_updated,
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
COUNTRY_VALIDATION_FRESHNESS_WINDOW_HOURS = 30.0


def _is_recent_country_feature_timestamp(parsed_timestamp: datetime | None, *, window_hours: float = COUNTRY_VALIDATION_FRESHNESS_WINDOW_HOURS) -> bool:
    if not parsed_timestamp:
        return False
    age_hours = (datetime.now(timezone.utc) - parsed_timestamp).total_seconds() / 3600.0
    return 0.0 <= age_hours <= float(window_hours)


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


def assess_country_risk_quality(
    topics,
    feature_timestamp,
    *,
    source_count=None,
    external_signal_freshness=None,
    external_sources=None,
    evidence_quality_score=None,
    war_state_rules=None,
    public_attention_score=None,
    narrative_velocity_score=None,
    coordination_risk_score=None,
    mobility_disruption_score=None,
    logistics_stress_score=None,
    household_stress_score=None,
    fuel_price_pressure=None,
    food_price_pressure=None,
    labor_stress_score=None,
    fx_pressure_score=None,
    remittance_stress_score=None,
    energy_stress_score=None,
    weather_stress=None,
):
    normalized_topics = [str(topic).strip().lower() for topic in (topics or []) if str(topic).strip()]
    is_placeholder = not normalized_topics or any(topic in PLACEHOLDER_TOPICS for topic in normalized_topics)
    parsed_timestamp = parse_feature_timestamp(feature_timestamp)
    updated_today = _is_recent_country_feature_timestamp(parsed_timestamp)

    signal_values = [
        public_attention_score,
        narrative_velocity_score,
        coordination_risk_score,
        mobility_disruption_score,
        logistics_stress_score,
        household_stress_score,
        fuel_price_pressure,
        food_price_pressure,
        labor_stress_score,
        fx_pressure_score,
        remittance_stress_score,
        energy_stress_score,
        weather_stress,
    ]
    strongest_non_news_signal = max((float(value or 0.0) for value in signal_values), default=0.0)
    source_count_value = max(int(source_count or 0), 0)
    external_source_count = len(external_sources) if isinstance(external_sources, list) else 0
    freshness_value = max(0.0, min(float(external_signal_freshness or 0.0), 1.0))
    evidence_value = max(0.0, min(float(evidence_quality_score or 0.0), 100.0))
    has_war_rules = bool(war_state_rules)

    multi_signal_verified = (
        has_war_rules
        or source_count_value >= 1
        or (external_source_count >= 3 and freshness_value >= 0.33 and strongest_non_news_signal >= 0.45)
        or (evidence_value >= 32.0 and strongest_non_news_signal >= 0.55)
    )
    validated_today = updated_today and ((not is_placeholder) or multi_signal_verified)

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
        "verification_mode": "multi_signal" if validated_today and is_placeholder else ("topic" if validated_today else "none"),
    }


COUNTRY_INTELLIGENCE_COMPONENT_FIELDS = (
    "social_unrest_score",
    "google_trends_pressure",
    "public_attention_score",
    "narrative_velocity_score",
    "coordination_risk_score",
    "mobility_disruption_score",
    "aviation_disruption_score",
    "logistics_stress_score",
    "household_stress_score",
    "fuel_price_pressure",
    "food_price_pressure",
    "labor_stress_score",
    "fx_pressure_score",
    "remittance_stress_score",
    "energy_stress_score",
    "weather_stress",
)

COUNTRY_INTELLIGENCE_SCORE_SEMANTICS = {
    "risk_score": "0-100 composite country risk score",
    "confidence_score": "0-100 calibrated intelligence confidence",
    "component_signals": "0-1 normalized signal intensity unless otherwise labeled",
    "direct_behavior_score": "0-100 absolute behavioral pressure score",
    "contextual_pressure_score": "0-100 absolute contextual pressure score",
    "evidence_quality_score": "0-100 evidence sufficiency and integrity score",
}


def _bounded_float(value: Any, default: float = 0.0, *, low: float | None = None, high: float | None = None) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    if not np.isfinite(parsed):
        parsed = float(default)
    if low is not None:
        parsed = max(low, parsed)
    if high is not None:
        parsed = min(high, parsed)
    return float(parsed)


def _country_risk_band(score: float) -> str:
    if score >= 85.0:
        return "critical"
    if score >= 70.0:
        return "escalating"
    if score >= 55.0:
        return "elevated"
    if score >= 35.0:
        return "guarded"
    return "stable"


def _country_confidence_band(score: float) -> str:
    if score >= 80.0:
        return "high"
    if score >= 60.0:
        return "moderate"
    if score >= 40.0:
        return "limited"
    return "weak"


def _country_source_status(data_quality: str, validated_today: bool) -> str:
    if validated_today:
        return "verified_live"
    if data_quality == "stale":
        return "stale_observation"
    if data_quality == "synthetic":
        return "derived_estimate"
    return "model_unavailable"


def _country_signal_evidence_count(doc: dict) -> int:
    count = 0
    for field in COUNTRY_INTELLIGENCE_COMPONENT_FIELDS:
        if _bounded_float(doc.get(field), 0.0, low=0.0, high=1.0) >= 0.35:
            count += 1
    if _bounded_float(doc.get("direct_behavior_score"), 0.0, low=0.0, high=100.0) >= 45.0:
        count += 1
    if _bounded_float(doc.get("contextual_pressure_score"), 0.0, low=0.0, high=100.0) >= 40.0:
        count += 1
    if (doc.get("war_state_rules") or []):
        count += 1
    return count


def _country_component_coverage_ratio(doc: dict) -> float:
    observed = 0
    for field in COUNTRY_INTELLIGENCE_COMPONENT_FIELDS:
        value = doc.get(field)
        if value is None:
            continue
        try:
            parsed = float(value)
        except Exception:
            continue
        if np.isfinite(parsed) and parsed > 0.0:
            observed += 1
    return round(observed / float(len(COUNTRY_INTELLIGENCE_COMPONENT_FIELDS)), 4)


def _country_confidence_score(doc: dict, *, data_quality: str, validated_today: bool) -> float:
    evidence_pct = _bounded_float(doc.get("evidence_quality_score"), 25.0 if validated_today else 18.0, low=0.0, high=100.0)
    freshness_pct = _bounded_float(doc.get("external_signal_freshness"), 0.0, low=0.0, high=1.0) * 100.0
    source_pct = min(max(int(doc.get("source_count") or 0), 0), 8) / 8.0 * 100.0
    behavior_pct = min(_bounded_float(doc.get("direct_behavior_score"), 0.0, low=0.0, high=100.0), 80.0)
    component_pct = _country_component_coverage_ratio(doc) * 100.0
    base = (evidence_pct * 0.40) + (freshness_pct * 0.20) + (source_pct * 0.15) + (behavior_pct * 0.10) + (component_pct * 0.15)
    if validated_today:
        base += 8.0
    if doc.get("war_state_rules"):
        base += 4.0

    cap = 96.0
    if data_quality == "stale":
        cap = 74.0
    elif data_quality == "synthetic":
        cap = 58.0 if int(doc.get("source_count") or 0) > 0 or doc.get("war_state_rules") else 48.0
    elif data_quality == "unknown":
        cap = 22.0

    return round(max(0.0, min(base, cap)), 2)


def _build_country_intelligence_gate(doc: dict, quality: dict, global_quality: dict | None = None) -> dict:
    data_quality = str(quality.get("data_quality") or "unknown")
    validated_today = bool(quality.get("validated_today"))
    source_count = max(int(doc.get("source_count") or 0), 0)
    evidence = _bounded_float(doc.get("evidence_quality_score"), 0.0, low=0.0, high=100.0)
    freshness = _bounded_float(doc.get("external_signal_freshness"), 0.0, low=0.0, high=1.0)
    component_ratio = _country_component_coverage_ratio(doc)
    has_war_rules = bool(doc.get("war_state_rules"))
    reasons: list[str] = []

    if data_quality == "unknown":
        reasons.append("country data unavailable")
    if data_quality == "synthetic":
        reasons.append("country risk derived from fallback or placeholder evidence")
    if data_quality == "stale":
        reasons.append("country evidence is not same-day verified")
    if source_count < 2:
        reasons.append(f"source_count {source_count} below target 2")
    if evidence < 35.0:
        reasons.append(f"evidence quality {evidence:.1f} below target 35")
    if freshness < 0.45:
        reasons.append(f"freshness {freshness:.0%} below target 45%")
    if component_ratio < 0.18:
        reasons.append(f"component coverage {component_ratio:.0%} below target 18%")

    global_gate = (global_quality or {}).get("quality_gate") if isinstance(global_quality, dict) else {}
    global_gate_active = bool((global_gate or {}).get("active"))
    verified_global = int((((global_gate or {}).get("metrics") or {}).get("verified_countries", 0)) or 0)
    if global_gate_active and not validated_today:
        reasons.append(f"global coverage gate active with only {verified_global} verified countries")

    action = "allow"
    status = "country_ready"
    if data_quality == "unknown" or ((data_quality == "synthetic") and source_count == 0 and evidence < 30.0 and freshness < 0.35 and not has_war_rules):
        action = "suppress"
        status = "country_unreliable"
    elif (not validated_today) or (global_gate_active and not validated_today) or freshness < 0.55 or evidence < 55.0 or source_count < 2 or component_ratio < 0.25:
        action = "downgrade"
        status = "country_degraded"

    if has_war_rules and action == "suppress":
        action = "downgrade"
        status = "country_degraded"

    if action == "allow":
        message = "Country intelligence meets live reliability thresholds."
    elif action == "downgrade":
        message = "Country intelligence is visible but downgraded because evidence or freshness is below production targets."
    else:
        message = "Country intelligence is withheld because evidence quality is too weak for reliable display."

    return {
        "action": action,
        "status": status,
        "reasons": reasons,
        "message": message,
    }


def _country_intelligence_global_context(mode: str = "online") -> dict:
    cache_key = f"mode={mode}"
    cached = _dashboard_cache_get("global_quality", cache_key)
    if isinstance(cached, dict):
        return cached

    latest_ingestion = _build_latest_ingestion()
    freshness = _build_freshness_snapshot(latest_ingestion)
    source_health = _build_source_health_snapshot()
    coverage = _compute_country_coverage_snapshot(mode=mode)
    quality_gate = _build_quality_gate_snapshot(coverage, freshness, source_health)
    payload = {
        "freshness": freshness,
        "source_health": source_health,
        "coverage": coverage,
        "quality_gate": quality_gate,
    }
    return _dashboard_cache_set("global_quality", cache_key, payload)


def _canonicalize_country_intelligence_row(doc: dict, *, mode: str = "online", global_quality: dict | None = None) -> dict:
    row = dict(doc or {})
    quality = assess_country_risk_quality(
        row.get("topics"),
        row.get("feature_timestamp"),
        source_count=row.get("source_count"),
        external_signal_freshness=row.get("external_signal_freshness"),
        external_sources=row.get("external_sources"),
        evidence_quality_score=row.get("evidence_quality_score"),
        war_state_rules=row.get("war_state_rules"),
        public_attention_score=row.get("public_attention_score"),
        narrative_velocity_score=row.get("narrative_velocity_score"),
        coordination_risk_score=row.get("coordination_risk_score"),
        mobility_disruption_score=row.get("mobility_disruption_score"),
        logistics_stress_score=row.get("logistics_stress_score"),
        household_stress_score=row.get("household_stress_score"),
        fuel_price_pressure=row.get("fuel_price_pressure"),
        food_price_pressure=row.get("food_price_pressure"),
        labor_stress_score=row.get("labor_stress_score"),
        fx_pressure_score=row.get("fx_pressure_score"),
        remittance_stress_score=row.get("remittance_stress_score"),
        energy_stress_score=row.get("energy_stress_score"),
        weather_stress=row.get("weather_stress"),
    )
    if row.get("feature_timestamp"):
        quality["feature_timestamp"] = row.get("feature_timestamp")
    if isinstance(row.get("validated_today"), bool):
        quality["validated_today"] = bool(row.get("validated_today"))
    if str(row.get("data_quality") or "").strip():
        quality["data_quality"] = str(row.get("data_quality")).strip().lower()

    raw_risk = _bounded_float(row.get("risk"), 0.0, low=0.0, high=100.0)
    confidence_score = _country_confidence_score(
        row,
        data_quality=str(quality.get("data_quality") or "unknown"),
        validated_today=bool(quality.get("validated_today")),
    )
    gate = _build_country_intelligence_gate(row, quality, global_quality=global_quality)
    if gate["action"] == "downgrade":
        confidence_score = min(confidence_score, 60.0 if bool(quality.get("validated_today")) else 48.0)
    elif gate["action"] == "suppress":
        confidence_score = min(confidence_score, 24.0)

    display_risk = None if gate["action"] == "suppress" else round(raw_risk, 2)
    row.update(quality)
    row["risk"] = round(raw_risk, 2)
    row["display_risk"] = display_risk
    row["raw_risk_score"] = round(raw_risk, 2)
    row["confidence_score"] = round(confidence_score, 2)
    row["risk_band"] = _country_risk_band(raw_risk)
    row["confidence_band"] = _country_confidence_band(confidence_score)
    row["source_status"] = _country_source_status(str(quality.get("data_quality") or "unknown"), bool(quality.get("validated_today")))
    row["gating_action"] = gate["action"]
    row["country_quality_status"] = gate["status"]
    row["country_quality_reasons"] = gate["reasons"]
    row["advisory"] = gate["message"]
    row["evidence_count"] = _country_signal_evidence_count(row)
    row["component_coverage_ratio"] = _country_component_coverage_ratio(row)
    row["score_semantics"] = COUNTRY_INTELLIGENCE_SCORE_SEMANTICS
    return row


def _country_risk_interval(doc: dict) -> dict[str, float]:
    risk = _bounded_float(doc.get("display_risk", doc.get("risk")), 0.0, low=0.0, high=100.0)
    confidence = _bounded_float(doc.get("confidence_score"), 0.0, low=0.0, high=100.0)
    band_width = max(4.0, 18.0 - (confidence * 0.12))
    return {
        "lower": round(max(0.0, risk - band_width), 2),
        "upper": round(min(100.0, risk + band_width), 2),
    }

COUNTRY_EXTERNAL_FIELDS = (
    "mobility_disruption_score",
    "aviation_disruption_score",
    "logistics_stress_score",
    "household_stress_score",
    "fuel_price_pressure",
    "food_price_pressure",
    "labor_stress_score",
    "fx_pressure_score",
    "remittance_stress_score",
    "energy_stress_score",
    "public_attention_score",
    "narrative_velocity_score",
    "coordination_risk_score",
    "google_trends_pressure",
    "social_unrest_score",
    "weather_stress",
)

ROLLUP_SIGNAL_FIELDS = (
    "social_unrest_score",
    "google_trends_pressure",
    "public_attention_score",
    "narrative_velocity_score",
    "coordination_risk_score",
    "mobility_disruption_score",
    "aviation_disruption_score",
    "logistics_stress_score",
    "household_stress_score",
    "fuel_price_pressure",
    "food_price_pressure",
    "labor_stress_score",
    "fx_pressure_score",
    "remittance_stress_score",
    "energy_stress_score",
    "weather_stress",
    "external_signal_freshness",
)

COUNTRY_SPILLOVER_MAP = load_country_spillover_map()

COUNTRY_RISK_DELTA_FIELDS = (
    "direct_behavior_score",
    "contextual_pressure_score",
    "evidence_quality_score",
    "social_unrest_score",
    "google_trends_pressure",
    "public_attention_score",
    "narrative_velocity_score",
    "coordination_risk_score",
    "mobility_disruption_score",
    "aviation_disruption_score",
    "logistics_stress_score",
    "household_stress_score",
    "fuel_price_pressure",
    "food_price_pressure",
    "labor_stress_score",
    "fx_pressure_score",
    "remittance_stress_score",
    "energy_stress_score",
    "weather_stress",
)


def _safe_iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _load_today_rollup(country: str) -> dict | None:
    today = datetime.now(timezone.utc).date().isoformat()
    return db.country_signal_rollups.find_one({"country": country, "event_date": today}, sort=[("updated_at", DESCENDING), ("_id", DESCENDING)])


def _safe_numeric_float(value: Any) -> float:
    try:
        number = float(value or 0.0)
        return number if np.isfinite(number) else 0.0
    except Exception:
        return 0.0


def _risk_trend_direction(delta_24h: float, delta_7d: float) -> str:
    reference = delta_24h if abs(delta_24h) >= 0.75 else delta_7d
    if reference >= 0.75:
        return "worsening"
    if reference <= -0.75:
        return "improving"
    return "stable"


def _compute_country_deltas_from_docs(feature_docs: list[dict]) -> tuple[float, float, str]:
    if not feature_docs:
        return 0.0, 0.0, "stable"
    ordered = sorted(feature_docs, key=lambda d: _safe_iso_datetime(d.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))
    latest_doc = ordered[-1]
    latest_features = latest_doc.get("features", {}) if isinstance(latest_doc.get("features"), dict) else {}
    latest_risk = _safe_numeric_float(latest_features.get("global_risk_score"))

    previous_doc = ordered[-2] if len(ordered) >= 2 else latest_doc
    previous_features = previous_doc.get("features", {}) if isinstance(previous_doc.get("features"), dict) else {}
    previous_risk = _safe_numeric_float(previous_features.get("global_risk_score"))

    earliest_doc = ordered[0]
    earliest_features = earliest_doc.get("features", {}) if isinstance(earliest_doc.get("features"), dict) else {}
    earliest_risk = _safe_numeric_float(earliest_features.get("global_risk_score"))

    delta_24h = round(latest_risk - previous_risk, 2)
    delta_7d = round(latest_risk - earliest_risk, 2)
    return delta_24h, delta_7d, _risk_trend_direction(delta_24h, delta_7d)


def _derive_country_change_contributors(current_features: dict | None, previous_features: dict | None) -> list[dict[str, Any]]:
    current = current_features if isinstance(current_features, dict) else {}
    previous = previous_features if isinstance(previous_features, dict) else {}
    contributors: list[dict[str, Any]] = []
    for field in COUNTRY_RISK_DELTA_FIELDS:
        current_value = _safe_numeric_float(current.get(field))
        previous_value = _safe_numeric_float(previous.get(field))
        delta = current_value - previous_value
        if abs(delta) < 0.25:
            continue
        contributors.append({
            "feature": field,
            "value": round(current_value, 4),
            "delta": round(delta, 4),
            "contribution": round(delta / 100.0, 4),
        })
    contributors.sort(key=lambda item: abs(_safe_numeric_float(item.get("delta"))), reverse=True)
    return contributors[:4]


def _attach_spillover_links(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = {str(row.get("country") or "").upper(): row for row in rows}
    for row in rows:
        country = str(row.get("country") or "").upper()
        spillovers = []
        for entry in COUNTRY_SPILLOVER_MAP.get(country, []):
            neighbor = index.get(str(entry.get("country") or "").upper())
            if not neighbor:
                continue
            spillovers.append({
                "country": str(neighbor.get("country") or "").upper(),
                "risk": round(_safe_numeric_float(neighbor.get("risk")), 2),
                "relationship": str(entry.get("relationship") or "Regional spillover"),
            })
        spillovers.sort(key=lambda item: _safe_numeric_float(item.get("risk")), reverse=True)
        row["spillover_links"] = spillovers[:4]
    return rows


def _enrich_country_risk_rows(rows: list[dict[str, Any]], mode: str = "online") -> list[dict[str, Any]]:
    if not rows:
        return rows

    countries = [str(row.get("country") or "").upper() for row in rows if str(row.get("country") or "").strip()]
    history_by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if countries:
        pipeline = [
            {"$match": {"country": {"$in": countries}, "mode": mode}},
            {"$sort": {"country": 1, "timestamp": -1}},
            {"$group": {"_id": "$country", "docs": {"$push": {"timestamp": "$timestamp", "features": "$features"}}}},
            {"$project": {"docs": {"$slice": ["$docs", 8]}}},
        ]
        for entry in db.country_features.aggregate(pipeline):
            history_by_country[str(entry.get("_id") or "").upper()] = list(entry.get("docs") or [])

    for row in rows:
        country = str(row.get("country") or "").upper()
        history_docs = history_by_country.get(country, [])
        delta_24h, delta_7d, trend_direction = _compute_country_deltas_from_docs(history_docs)
        row["risk_delta_24h"] = delta_24h
        row["risk_delta_7d"] = delta_7d
        row["risk_trend_direction"] = trend_direction
        latest_doc = history_docs[0] if history_docs else None
        previous_doc = history_docs[1] if len(history_docs) >= 2 else latest_doc
        latest_features = latest_doc.get("features", {}) if isinstance((latest_doc or {}).get("features"), dict) else {}
        previous_features = previous_doc.get("features", {}) if isinstance((previous_doc or {}).get("features"), dict) else {}
        row["score_change_contributors"] = _derive_country_change_contributors(latest_features, previous_features)
    return _attach_spillover_links(rows)


def _needs_rollup_backfill(latest_features: dict, rollup: dict | None) -> bool:
    if not isinstance(rollup, dict):
        return False
    tracked_sources = {"mobility", "aviation", "opensky", "unhcr_idmc", "logistics", "economic_behavior", "telegram_public", "youtube_public", "wikipedia", "google_trends"}
    rollup_sources = {str(source) for source in (rollup.get("sources") or [])}
    if not (rollup_sources & tracked_sources):
        return False
    for field in ROLLUP_SIGNAL_FIELDS:
        feature_value = float((latest_features or {}).get(field, 0.0) or 0.0)
        rollup_value = float((rollup or {}).get(field, 0.0) or 0.0)
        if rollup_value > feature_value + 1e-9:
            return True
    feature_ts = _safe_iso_datetime((latest_features or {}).get("timestamp"))
    rollup_ts = _safe_iso_datetime((rollup or {}).get("updated_at") or (rollup or {}).get("last_event_timestamp"))
    return bool(feature_ts and rollup_ts and rollup_ts > feature_ts)


def _merge_rollup_signals(latest_features: dict, rollup: dict | None) -> dict:
    merged = dict(latest_features or {})
    if not isinstance(rollup, dict):
        return merged
    for field in ROLLUP_SIGNAL_FIELDS:
        merged[field] = max(float(merged.get(field, 0.0) or 0.0), float(rollup.get(field, 0.0) or 0.0))
    merged["external_sources"] = list(rollup.get("sources") or merged.get("external_sources") or [])
    merged["source_count"] = max(int(merged.get("source_count") or 0), len(merged["external_sources"]))
    merged["timestamp"] = merged.get("timestamp") or datetime.utcnow().isoformat()
    return merged


def _feature_signal_strength(features: dict) -> tuple[float, int]:
    if not isinstance(features, dict):
        return (0.0, 0)
    values = [float(features.get(field, 0.0) or 0.0) for field in COUNTRY_EXTERNAL_FIELDS]
    freshness = float(features.get("external_signal_freshness", 0.0) or 0.0)
    nonzero = sum(1 for value in values if value > 0.0)
    return (freshness + sum(values), nonzero)


def _prefer_feature_doc(docs: list[dict]) -> dict | None:
    if not docs:
        return None
    ranked = sorted(
        docs,
        key=lambda doc: (
            1 if str((doc or {}).get("features", {}).get("risk_definition") or "").strip() else 0,
            1 if str((doc or {}).get("features", {}).get("source") or "").strip() in {"country_risk_stream_incremental", "country_news_multi_source_daily"} else 0,
            _safe_iso_datetime((doc or {}).get("features", {}).get("timestamp")) or _safe_iso_datetime((doc or {}).get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
            _feature_signal_strength((doc or {}).get("features", {}))[1],
            _feature_signal_strength((doc or {}).get("features", {}))[0],
            str((doc or {}).get("features", {}).get("timestamp") or ""),
            str((doc or {}).get("timestamp") or ""),
        ),
        reverse=True,
    )
    return ranked[0]


def _refresh_country_features_if_stale(country: str, latest_features: dict, mode: str = "online") -> dict:
    rollup = _load_today_rollup(country)
    if not _needs_rollup_backfill(latest_features, rollup):
        return dict(latest_features or {})
    try:
        recomputed = recompute_country_risk(country, mode=mode)
        return dict(recomputed or latest_features or {})
    except Exception:
        return _merge_rollup_signals(latest_features, rollup)


def convert_country_code(code: str) -> str:
    """Convert 2-letter country code to 3-letter ISO code"""
    if not code:
        return code
    code = code.upper().strip()
    if len(code) == 3:
        return code  # Already 3-letter
    return ISO2_TO_ISO3.get(code, code)  # Convert or return as-is


@app.get("/country-intelligence/latest")
@app.get("/dashboard/risk-map")
@limiter.limit("30/minute")
def dashboard_risk_map(
    request: Request,
    role: str = Depends(check_role),
    mode: str = Query("online"),
    verified_only: bool = Query(False),
):
    cache_key = f"mode={mode}|verified_only={int(bool(verified_only))}"
    cached = _dashboard_cache_get("risk_map", cache_key)
    if isinstance(cached, list):
        return cached

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
                "public_attention_score": {"$ifNull": ["$doc.features.public_attention_score", 0.0]},
                "narrative_velocity_score": {"$ifNull": ["$doc.features.narrative_velocity_score", 0.0]},
                "coordination_risk_score": {"$ifNull": ["$doc.features.coordination_risk_score", 0.0]},
                "mobility_disruption_score": {"$ifNull": ["$doc.features.mobility_disruption_score", 0.0]},
                "logistics_stress_score": {"$ifNull": ["$doc.features.logistics_stress_score", 0.0]},
                "aviation_disruption_score": {"$ifNull": ["$doc.features.aviation_disruption_score", 0.0]},
                "household_stress_score": {"$ifNull": ["$doc.features.household_stress_score", 0.0]},
                "fuel_price_pressure": {"$ifNull": ["$doc.features.fuel_price_pressure", 0.0]},
                "food_price_pressure": {"$ifNull": ["$doc.features.food_price_pressure", 0.0]},
                "labor_stress_score": {"$ifNull": ["$doc.features.labor_stress_score", 0.0]},
                "fx_pressure_score": {"$ifNull": ["$doc.features.fx_pressure_score", 0.0]},
                "remittance_stress_score": {"$ifNull": ["$doc.features.remittance_stress_score", 0.0]},
                "energy_stress_score": {"$ifNull": ["$doc.features.energy_stress_score", 0.0]},
                "weather_stress": {"$ifNull": ["$doc.features.weather_stress", 0.0]},
                "external_signal_freshness": {"$ifNull": ["$doc.features.external_signal_freshness", 0.0]},
                "external_sources": {"$ifNull": ["$doc.features.external_sources", []]},
                "direct_behavior_score": {"$ifNull": ["$doc.features.direct_behavior_score", 0.0]},
                "contextual_pressure_score": {"$ifNull": ["$doc.features.contextual_pressure_score", 0.0]},
                "evidence_quality_score": {"$ifNull": ["$doc.features.evidence_quality_score", 0.0]},
                "war_state_rules": {"$ifNull": ["$doc.features.war_state_rules", []]},
            }
        },
    ]
    docs = list(db.country_features.aggregate(pipeline))

    if not docs:
        docs = _derive_country_risk_map_from_country_news(mode=mode)
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
                "public_attention_score": 0.0,
                "narrative_velocity_score": 0.0,
                "coordination_risk_score": 0.0,
                "mobility_disruption_score": 0.0,
                "logistics_stress_score": 0.0,
                "aviation_disruption_score": 0.0,
                "household_stress_score": 0.0,
                "fuel_price_pressure": 0.0,
                "food_price_pressure": 0.0,
                "labor_stress_score": 0.0,
                "fx_pressure_score": 0.0,
                "remittance_stress_score": 0.0,
                "energy_stress_score": 0.0,
                "weather_stress": 0.0,
                "external_signal_freshness": 0.0,
                "direct_behavior_score": 0.0,
                "contextual_pressure_score": 0.0,
                "evidence_quality_score": 0.0,
                "war_state_rules": [],
            }
            for code in placeholder_codes
        ]

    response_docs = []
    for doc in docs:
        quality = assess_country_risk_quality(
            doc.get("topics"),
            doc.get("feature_timestamp"),
            source_count=doc.get("source_count"),
            external_signal_freshness=doc.get("external_signal_freshness"),
            external_sources=doc.get("external_sources"),
            evidence_quality_score=doc.get("evidence_quality_score"),
            war_state_rules=doc.get("war_state_rules"),
            public_attention_score=doc.get("public_attention_score"),
            narrative_velocity_score=doc.get("narrative_velocity_score"),
            coordination_risk_score=doc.get("coordination_risk_score"),
            mobility_disruption_score=doc.get("mobility_disruption_score"),
            logistics_stress_score=doc.get("logistics_stress_score"),
            household_stress_score=doc.get("household_stress_score"),
            fuel_price_pressure=doc.get("fuel_price_pressure"),
            food_price_pressure=doc.get("food_price_pressure"),
            labor_stress_score=doc.get("labor_stress_score"),
            fx_pressure_score=doc.get("fx_pressure_score"),
            remittance_stress_score=doc.get("remittance_stress_score"),
            energy_stress_score=doc.get("energy_stress_score"),
            weather_stress=doc.get("weather_stress"),
        )
        if verified_only and not quality["validated_today"]:
            continue

        doc["country"] = convert_country_code(doc.get("country", ""))
        preferred = None
        needs_preferred_doc = (
            not str(doc.get("feature_timestamp") or "").strip()
            or int(doc.get("source_count") or 0) <= 0
            or not any(float(doc.get(field) or 0.0) > 0.0 for field in COUNTRY_EXTERNAL_FIELDS)
        )
        if needs_preferred_doc:
            fallback_docs = list(db.country_features.find({"country": doc["country"], "mode": mode}).sort("timestamp", -1).limit(8))
            preferred = _prefer_feature_doc(fallback_docs)
        if preferred and preferred.get("features"):
            preferred_features = preferred.get("features", {})
            doc["risk"] = preferred_features.get("global_risk_score", doc.get("risk"))
            doc["timestamp"] = preferred.get("timestamp", doc.get("timestamp"))
            doc["feature_timestamp"] = preferred_features.get("timestamp", doc.get("feature_timestamp"))
            for field in COUNTRY_EXTERNAL_FIELDS + ("external_signal_freshness", "direct_behavior_score", "contextual_pressure_score", "evidence_quality_score", "war_state_rules"):
                if field == "war_state_rules":
                    doc[field] = preferred_features.get(field, doc.get(field, []))
                else:
                    doc[field] = preferred_features.get(field, doc.get(field, 0.0))
        doc = _merge_rollup_signals(doc, _load_today_rollup(doc["country"]))
        risk_value = doc.get("risk")
        doc["risk"] = float(risk_value) if risk_value is not None else 0.0
        doc["source_count"] = int(doc.get("source_count") or 0)
        doc["social_unrest_score"] = float(doc.get("social_unrest_score") or 0.0)
        doc["google_trends_pressure"] = float(doc.get("google_trends_pressure") or 0.0)
        doc["public_attention_score"] = float(doc.get("public_attention_score") or 0.0)
        doc["narrative_velocity_score"] = float(doc.get("narrative_velocity_score") or 0.0)
        doc["coordination_risk_score"] = float(doc.get("coordination_risk_score") or 0.0)
        doc["mobility_disruption_score"] = float(doc.get("mobility_disruption_score") or 0.0)
        doc["logistics_stress_score"] = float(doc.get("logistics_stress_score") or 0.0)
        doc["aviation_disruption_score"] = float(doc.get("aviation_disruption_score") or 0.0)
        doc["household_stress_score"] = float(doc.get("household_stress_score") or 0.0)
        doc["fuel_price_pressure"] = float(doc.get("fuel_price_pressure") or 0.0)
        doc["food_price_pressure"] = float(doc.get("food_price_pressure") or 0.0)
        doc["labor_stress_score"] = float(doc.get("labor_stress_score") or 0.0)
        doc["fx_pressure_score"] = float(doc.get("fx_pressure_score") or 0.0)
        doc["remittance_stress_score"] = float(doc.get("remittance_stress_score") or 0.0)
        doc["energy_stress_score"] = float(doc.get("energy_stress_score") or 0.0)
        doc["weather_stress"] = float(doc.get("weather_stress") or 0.0)
        doc["external_signal_freshness"] = float(doc.get("external_signal_freshness") or 0.0)
        doc["direct_behavior_score"] = float(doc.get("direct_behavior_score") or 0.0)
        doc["contextual_pressure_score"] = float(doc.get("contextual_pressure_score") or 0.0)
        doc["evidence_quality_score"] = float(doc.get("evidence_quality_score") or 0.0)
        doc.update(quality)
        doc.pop("topics", None)
        response_docs.append(doc)

    response_docs = _enrich_country_risk_rows(response_docs, mode=mode)
    global_quality = _country_intelligence_global_context(mode=mode)
    canonical_docs = [_canonicalize_country_intelligence_row(d, mode=mode, global_quality=global_quality) for d in response_docs]
    serialized = [serialize_doc(d) for d in canonical_docs]
    return _dashboard_cache_set("risk_map", cache_key, serialized)


@app.get("/dashboard/risk-map/coverage")
@limiter.limit("30/minute")
def dashboard_risk_map_coverage(request: Request, role: str = Depends(check_role), mode: str = Query("online")):
    cache_key = f"mode={mode}"
    cached = _dashboard_cache_get("coverage", cache_key)
    if isinstance(cached, dict):
        return cached

    docs = dashboard_risk_map(request=request, role=role, mode=mode, verified_only=False)
    total = len(docs)
    verified = sum(1 for doc in docs if doc.get("validated_today"))
    no_data = sum(1 for doc in docs if doc.get("data_quality") == "synthetic")
    stale = sum(1 for doc in docs if doc.get("data_quality") == "stale")
    suppressed = sum(1 for doc in docs if str(doc.get("gating_action") or "") == "suppress")
    latest_validation = latest_country_risk_validation()
    payload = {
        "total": total,
        "verified": verified,
        "no_data": no_data,
        "stale": stale,
        "suppressed": suppressed,
        "remaining": max(total - verified, 0),
        "coverage_pct": round((verified / total) * 100, 2) if total else 0.0,
        "latest_validation": {
            "status": latest_validation.get("status"),
            "sample_count": int(latest_validation.get("sample_count", 0) or 0),
            "brier_score": float((((latest_validation.get("metrics") or {}).get("brier_score", 0.0)) or 0.0)),
        },
    }
    return _dashboard_cache_set("coverage", cache_key, payload)


@app.post("/dashboard/risk-map/refresh")
@limiter.limit("10/minute")
def dashboard_risk_map_refresh(request: Request, payload: CountryRefreshRequest, role: str = Depends(check_role)):
    batch_size = max(1, min(int(payload.batch_size), len(get_country_catalog())))
    max_records = max(1, min(int(payload.max_records), 25))
    summary = country_daily_refresh_if_due(max_records=max_records, batch_size=batch_size)
    return serialize_doc(summary)


def _normalized_country_aliases() -> dict[str, list[str]]:
    aliases: dict[str, set[str]] = {}
    for code, name in COUNTRY_NAMES.items():
        normalized_name = str(name or '').strip().lower()
        if not normalized_name:
            continue
        bucket = aliases.setdefault(code, set())
        bucket.add(normalized_name)
        parts = normalized_name.replace('-', ' ').split()
        if len(parts) > 1:
            bucket.add(' '.join(parts))
        if normalized_name.endswith('ia'):
            bucket.add(normalized_name[:-2] + 'ian')
        if normalized_name.endswith('y'):
            bucket.add(normalized_name[:-1] + 'ian')
    manual = {
        'USA': {'us', 'u.s.', 'u.s', 'usa', 'united states', 'american'},
        'GBR': {'uk', 'u.k.', 'britain', 'united kingdom', 'british'},
        'IRN': {'iran', 'iranian'},
        'ISR': {'israel', 'israeli'},
        'QAT': {'qatar', 'qatari'},
        'AFG': {'afghanistan', 'afghan', 'kabul'},
        'UKR': {'ukraine', 'ukrainian', 'kyiv', 'kiev'},
        'RUS': {'russia', 'russian', 'moscow'},
        'IND': {'india', 'indian', 'new delhi'},
        'SYR': {'syria', 'syrian', 'damascus'},
        'PSE': {'gaza', 'palestine', 'palestinian'},
    }
    for code, values in manual.items():
        aliases.setdefault(code, set()).update(values)
    return {code: sorted(values, key=len, reverse=True) for code, values in aliases.items()}


COUNTRY_ALIASES = _normalized_country_aliases()


def _infer_affected_country_code(*parts: str, fallback: str = 'UNK') -> str:
    blob = ' '.join(str(part or '') for part in parts).lower()
    if not blob.strip():
        return convert_country_code(fallback)
    blocked_alias_contexts: dict[str, tuple[str, ...]] = {
        'JEY': (r'\bnew jersey\b',),
    }
    best_code = convert_country_code(fallback)
    best_length = 0
    for code, aliases in COUNTRY_ALIASES.items():
        blocked_patterns = blocked_alias_contexts.get(code, ())
        if blocked_patterns and any(re.search(pattern, blob) for pattern in blocked_patterns):
            continue
        for alias in aliases:
            if len(alias) < 3:
                continue
            if re.search(rf'(?<![a-z]){re.escape(alias)}(?![a-z])', blob):
                if len(alias) > best_length:
                    best_code = code
                    best_length = len(alias)
                break
    return convert_country_code(best_code)


@app.get("/dashboard/global-intelligence-feed")
@limiter.limit("60/minute")
def dashboard_global_intelligence_feed(
    request: Request,
    role: str = Depends(check_role),
    mode: str = Query("online"),
    country: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Returns a live MongoDB-backed intelligence feed.
    No mock/template content is generated.
    """
    requested_country = convert_country_code(str(country or "").upper().strip()) if country else None
    cache_key = f"mode={mode}|country={requested_country or 'all'}|limit={min(limit, 50)}"
    cached = _dashboard_cache_get("feed", cache_key)
    if isinstance(cached, list):
        return cached[:limit]

    risk_by_country: dict[str, dict[str, Any]] = {}
    cached_risk_rows = _dashboard_cache_get("risk_map", f"mode={mode}|verified_only=0")
    if isinstance(cached_risk_rows, list) and cached_risk_rows:
        for row in cached_risk_rows:
            code = convert_country_code(str(row.get("country") or "").upper().strip())
            if not code:
                continue
            risk_by_country[code] = {
                "risk_score": float(row.get("risk", 50.0) or 50.0),
                "topics": row.get("top_topics") if isinstance(row.get("top_topics"), list) else [],
            }
    else:
        country_risk_pipeline = [
            {"$match": {"mode": mode}},
            {"$sort": {"timestamp": -1}},
            {"$group": {"_id": "$country", "doc": {"$first": "$$ROOT"}}},
            {"$replaceRoot": {"newRoot": "$doc"}},
            {"$project": {"country": 1, "risk": "$features.global_risk_score", "topics": "$features.top_topics"}},
        ]
        risk_docs = list(db.country_features.aggregate(country_risk_pipeline))
        for row in risk_docs:
            code = convert_country_code(str(row.get("country") or "").upper().strip())
            if not code:
                continue
            risk_by_country[code] = {
                "risk_score": float(row.get("risk", 50.0) or 50.0),
                "topics": row.get("topics") if isinstance(row.get("topics"), list) else [],
            }

    def _infer_category(title: str, summary: str, risk_score: float, topics: list[str]) -> str:
        blob = f"{title} {summary} {' '.join([str(t) for t in topics])}".lower()
        if risk_score >= 75 or any(tok in blob for tok in ["war", "conflict", "attack", "military", "security"]):
            return "security"
        if any(tok in blob for tok in ["econom", "market", "inflation", "interest rate", "trade", "currency"]):
            return "economic"
        if any(tok in blob for tok in ["climate", "weather", "flood", "storm", "wildfire", "drought"]):
            return "environment"
        if any(tok in blob for tok in ["tech", "ai", "cyber", "digital", "internet", "software"]):
            return "technology"
        if any(tok in blob for tok in ["election", "parliament", "government", "policy", "diplomat"]):
            return "political"
        return "social"

    news_match: dict[str, Any] = {}
    if requested_country:
        news_match["country"] = requested_country

    news_docs = list(
        db.country_news.find(
            news_match,
            {
                "_id": 1,
                "country": 1,
                "country_name": 1,
                "timestamp": 1,
                "collected_at": 1,
                "data.title": 1,
                "data.description": 1,
                "data.content": 1,
                "data.url": 1,
                "data.source_name": 1,
                "data.published_at": 1,
                "source": 1,
            },
        )
        .sort("timestamp", DESCENDING)
        .limit(max(120, min(limit * 4, 320)))
    )

    feed_items = []
    seen = set()

    def _freshness_score(timestamp_value: str) -> float:
        parsed = _parse_timestamp(timestamp_value)
        if parsed == datetime.min.replace(tzinfo=timezone.utc):
            return 0.25
        age_hours = max((datetime.utcnow().replace(tzinfo=timezone.utc) - parsed).total_seconds() / 3600.0, 0.0)
        if age_hours <= 1:
            return 1.0
        if age_hours <= 6:
            return 0.88
        if age_hours <= 24:
            return 0.72
        if age_hours <= 72:
            return 0.55
        return 0.35

    def _keyword_intensity(*parts: str) -> float:
        blob = " ".join(str(part or "") for part in parts).lower()
        critical_terms = ("war", "conflict", "missile", "attack", "strike", "evacuation", "sanction", "emergency", "protest", "riot", "crisis")
        elevated_terms = ("disruption", "inflation", "shortage", "outage", "shutdown", "border", "military", "cyber", "drought", "flood")
        score = 0.0
        if any(term in blob for term in critical_terms):
            score += 0.65
        if any(term in blob for term in elevated_terms):
            score += 0.35
        return min(score, 1.0)

    def _topic_overlap(*parts: str, topics: list[str]) -> float:
        if not topics:
            return 0.0
        blob = " ".join(str(part or "") for part in parts).lower()
        matches = 0
        for topic_value in topics:
            topic = str(topic_value or "").strip().lower()
            if topic and topic in blob:
                matches += 1
        return min(matches / max(len(topics), 1), 1.0)

    for doc in news_docs:
        data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
        headline = str(data.get("title") or "").strip()
        if not headline:
            continue

        source_country_code = convert_country_code(str(doc.get("country") or data.get("country") or "UNK").upper().strip())
        summary = str(data.get("description") or data.get("content") or "").strip()
        full_article = str(data.get("content") or summary or headline).strip()
        inferred_country_code = _infer_affected_country_code(headline, fallback="UNK")
        if inferred_country_code == "UNK" and summary:
            inferred_country_code = _infer_affected_country_code(summary[:220], fallback="UNK")
        if requested_country:
            country_code = inferred_country_code if inferred_country_code != "UNK" else source_country_code
        else:
            country_code = inferred_country_code if inferred_country_code != "UNK" else source_country_code
        if not country_code or country_code == "UNK":
            continue
        country_name = str(COUNTRY_NAMES.get(country_code, doc.get("country_name") or country_code))
        source = str(data.get("source_name") or doc.get("source") or "unknown")
        source_url = str(data.get("url") or "").strip()
        raw_timestamp = data.get("published_at") or doc.get("timestamp") or doc.get("collected_at") or datetime.utcnow().isoformat()
        parsed_timestamp = _parse_timestamp(raw_timestamp)
        timestamp = parsed_timestamp.isoformat() if parsed_timestamp != datetime.min.replace(tzinfo=timezone.utc) else str(raw_timestamp)

        normalized_headline = re.sub(r"\s+", " ", headline.lower()).strip()
        dedupe_key = f"{country_code}|{normalized_headline}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        risk_meta = risk_by_country.get(country_code, {"risk_score": 50.0, "topics": []})
        risk_score = float(risk_meta.get("risk_score", 50.0) or 50.0)
        topics = risk_meta.get("topics") if isinstance(risk_meta.get("topics"), list) else []
        category = _infer_category(headline, summary, risk_score, topics)
        freshness_score = _freshness_score(timestamp)
        keyword_intensity = _keyword_intensity(headline, summary)
        topic_overlap = _topic_overlap(headline, summary, full_article, topics=topics)
        relevance_score = round(
            (min(max(risk_score, 0.0), 100.0) / 100.0) * 0.46
            + freshness_score * 0.28
            + keyword_intensity * 0.18
            + topic_overlap * 0.08,
            4,
        )

        feed_items.append(
            {
                "id": str(doc.get("_id")),
                "country": country_code or "UNK",
                "country_name": country_name or (country_code or "Unknown"),
                "headline": headline,
                "summary": summary if summary else headline,
                "full_article": full_article if full_article else headline,
                "source": source,
                "source_url": source_url,
                "risk_score": risk_score,
                "timestamp": timestamp,
                "category": category,
                "relevance_score": relevance_score,
            }
        )
        if len(feed_items) >= max(limit * 4, 80):
            break

    feed_items.sort(
        key=lambda item: (
            float(item.get("relevance_score") or 0.0),
            _parse_timestamp(str(item.get("timestamp") or "")),
        ),
        reverse=True,
    )

    diversified: list[dict[str, Any]] = []
    country_counts: dict[str, int] = {}
    per_country_cap = 2 if not requested_country else limit
    for item in feed_items:
        code = str(item.get("country") or "UNK")
        if country_counts.get(code, 0) >= per_country_cap:
            continue
        diversified.append(item)
        country_counts[code] = country_counts.get(code, 0) + 1
        if len(diversified) >= limit:
            break
    if len(diversified) < limit:
        seen_ids = {str(item.get("id")) for item in diversified}
        for item in feed_items:
            if str(item.get("id")) in seen_ids:
                continue
            diversified.append(item)
            if len(diversified) >= limit:
                break
    final_items = diversified[:limit]
    _dashboard_cache_set("feed", cache_key, final_items)
    return final_items





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

@app.get("/country-intelligence/{country}")
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


    preferred_doc = _prefer_feature_doc(docs) or docs[0]
    ordered = list(reversed(docs))
    latest = preferred_doc
    latest_features = _refresh_country_features_if_stale(code, latest.get("features", {}), mode=mode)
    trend = [
        {
            "timestamp": str(d.get("timestamp", datetime.utcnow().isoformat())),
            "value": float(d.get("features", {}).get("global_risk_score", 50.0)),
        }
        for d in ordered
    ]

    drivers = []
    for k in (
        "direct_behavior_score",
        "contextual_pressure_score",
        "evidence_quality_score",
        "social_unrest_score",
        "google_trends_pressure",
        "public_attention_score",
        "narrative_velocity_score",
        "coordination_risk_score",
        "mobility_disruption_score",
        "logistics_stress_score",
        "aviation_disruption_score",
        "household_stress_score",
        "fuel_price_pressure",
        "food_price_pressure",
        "labor_stress_score",
        "fx_pressure_score",
        "remittance_stress_score",
        "energy_stress_score",
        "weather_stress",
        "news_sentiment",
        "gdelt_sentiment",
    ):
        value = float(latest_features.get(k, 0.0))
        if k == "evidence_quality_score":
            contribution = round((value - 50.0) / 100.0, 4)
        else:
            contribution = round(value / 100.0, 4) if "score" in k or k.endswith("stress") or k.endswith("pressure") else round(value * 0.12, 4)
        drivers.append({
            "feature": k,
            "value": value,
            "contribution": contribution,
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
    canonical_doc = _canonicalize_country_intelligence_row(
        {
            "country": code,
            "risk": risk,
            "feature_timestamp": latest_features.get("timestamp"),
            "topics": latest_features.get("top_topics", []),
            "source_count": latest_features.get("source_count", 0),
            "social_unrest_score": latest_features.get("social_unrest_score", 0.0),
            "google_trends_pressure": latest_features.get("google_trends_pressure", 0.0),
            "public_attention_score": latest_features.get("public_attention_score", 0.0),
            "narrative_velocity_score": latest_features.get("narrative_velocity_score", 0.0),
            "coordination_risk_score": latest_features.get("coordination_risk_score", 0.0),
            "mobility_disruption_score": latest_features.get("mobility_disruption_score", 0.0),
            "logistics_stress_score": latest_features.get("logistics_stress_score", 0.0),
            "aviation_disruption_score": latest_features.get("aviation_disruption_score", 0.0),
            "household_stress_score": latest_features.get("household_stress_score", 0.0),
            "fuel_price_pressure": latest_features.get("fuel_price_pressure", 0.0),
            "food_price_pressure": latest_features.get("food_price_pressure", 0.0),
            "labor_stress_score": latest_features.get("labor_stress_score", 0.0),
            "fx_pressure_score": latest_features.get("fx_pressure_score", 0.0),
            "remittance_stress_score": latest_features.get("remittance_stress_score", 0.0),
            "energy_stress_score": latest_features.get("energy_stress_score", 0.0),
            "weather_stress": latest_features.get("weather_stress", 0.0),
            "external_signal_freshness": latest_features.get("external_signal_freshness", 0.0),
            "direct_behavior_score": latest_features.get("direct_behavior_score", 0.0),
            "contextual_pressure_score": latest_features.get("contextual_pressure_score", 0.0),
            "evidence_quality_score": latest_features.get("evidence_quality_score", 0.0),
            "war_state_rules": latest_features.get("war_state_rules", []),
        },
        mode=mode,
        global_quality=_country_intelligence_global_context(mode=mode),
    )
    confidence_interval = _country_risk_interval(canonical_doc)
    return {
        "country": country,
        "risk": float(canonical_doc.get("display_risk") if canonical_doc.get("display_risk") is not None else canonical_doc.get("risk", risk)),
        "display_risk": canonical_doc.get("display_risk"),
        "raw_risk_score": canonical_doc.get("raw_risk_score", risk),
        "confidence_score": canonical_doc.get("confidence_score", 0.0),
        "risk_band": canonical_doc.get("risk_band"),
        "confidence_band": canonical_doc.get("confidence_band"),
        "source_status": canonical_doc.get("source_status"),
        "gating_action": canonical_doc.get("gating_action"),
        "country_quality_status": canonical_doc.get("country_quality_status"),
        "country_quality_reasons": canonical_doc.get("country_quality_reasons", []),
        "advisory": canonical_doc.get("advisory"),
        "evidence_count": canonical_doc.get("evidence_count", 0),
        "score_semantics": canonical_doc.get("score_semantics", COUNTRY_INTELLIGENCE_SCORE_SEMANTICS),
        "direct_behavior_score": float(latest_features.get("direct_behavior_score", 0.0) or 0.0),
        "contextual_pressure_score": float(latest_features.get("contextual_pressure_score", 0.0) or 0.0),
        "evidence_quality_score": float(latest_features.get("evidence_quality_score", 0.0) or 0.0),
        "mobility_disruption_score": float(latest_features.get("mobility_disruption_score", 0.0) or 0.0),
        "logistics_stress_score": float(latest_features.get("logistics_stress_score", 0.0) or 0.0),
        "household_stress_score": float(latest_features.get("household_stress_score", 0.0) or 0.0),
        "fuel_price_pressure": float(latest_features.get("fuel_price_pressure", 0.0) or 0.0),
        "food_price_pressure": float(latest_features.get("food_price_pressure", 0.0) or 0.0),
        "labor_stress_score": float(latest_features.get("labor_stress_score", 0.0) or 0.0),
        "fx_pressure_score": float(latest_features.get("fx_pressure_score", 0.0) or 0.0),
        "remittance_stress_score": float(latest_features.get("remittance_stress_score", 0.0) or 0.0),
        "energy_stress_score": float(latest_features.get("energy_stress_score", 0.0) or 0.0),
        "narrative_velocity_score": float(latest_features.get("narrative_velocity_score", 0.0) or 0.0),
        "coordination_risk_score": float(latest_features.get("coordination_risk_score", 0.0) or 0.0),
        "trend": trend,
        "drivers": drivers,
        "events": events,
        "confidenceInterval": confidence_interval,
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


def _build_governance_payload(mode: str = "online") -> dict[str, Any]:
    latest_doc = get_latest_global_doc(mode)
    base_risk = float(latest_doc.get("features", {}).get("global_risk_score", 50.0))

    model_info_docs = list(model_monitoring_collection.find().sort("timestamp", -1).limit(300))
    by_model: dict[str, list[dict]] = defaultdict(list)
    for d in model_info_docs:
        by_model[str(d.get("model_version", "unknown"))].append(d)

    registry_models = list_models()

    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _extract_registry_calibration(metrics: Any) -> float:
        if not isinstance(metrics, dict):
            return 0.0
        for key in ("calibration", "probability", "confidence", "f1", "accuracy", "auc"):
            if key in metrics:
                return max(0.0, min(1.0, _safe_float(metrics.get(key), 0.0)))
        return 0.0

    all_model_names = set(by_model.keys()) | set(registry_models.keys())
    ordered_names = sorted(
        all_model_names,
        key=lambda name: (
            0 if str((registry_models.get(name) or {}).get("stage", "")).lower() == "production" else 1,
            name,
        ),
    )

    models = []
    total_models = max(len(ordered_names), 1)
    center = (total_models - 1) / 2.0
    for idx, model_name in enumerate(ordered_names):
        rows = by_model.get(model_name) or []
        reg = registry_models.get(model_name) if isinstance(registry_models, dict) else None
        latest = rows[0] if rows else {}
        drift = _safe_float(
            latest.get("drift_score", (reg or {}).get("metrics", {}).get("drift_score", 0.0)),
            0.0,
        )
        if rows:
            conf_values = [_safe_float(x.get("probability"), 0.5) for x in rows[:30]]
            calibration = sum(conf_values) / max(1, len(conf_values))
        else:
            calibration = _extract_registry_calibration((reg or {}).get("metrics", {}))
        latency = int(_safe_float(latest.get("latency_ms", ((reg or {}).get("metrics", {}) or {}).get("latency_ms", 0.0)), 0.0))
        vote = max(0.0, min(100.0, base_risk + ((idx - center) * 1.8)))
        models.append({
            "name": model_name,
            "stage": str((reg or {}).get("stage", "unknown")),
            "latencyMs": latency,
            "calibration": round(calibration, 4),
            "driftHint": "watch" if drift >= 0.35 else "stable",
            "vote": round(vote, 2),
            "confidence": round(calibration, 4),
        })

    if not models:
        models = [{
            "name": "production",
            "stage": "unknown",
            "latencyMs": 0,
            "calibration": 0.0,
            "driftHint": "stable",
            "vote": round(base_risk, 2),
            "confidence": 0.0,
        }]

    disagreement = []
    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            raw_gap = abs(models[i]["vote"] - models[j]["vote"])
            disagreement.append({
                "left": models[i]["name"],
                "right": models[j]["name"],
                "value": round(max(0.0, min(1.0, raw_gap / 100.0)), 4),
            })

    cal_trend_source = list(prediction_collection.find().sort("timestamp", -1).limit(50))
    calibration_trend = [
        {"timestamp": str(d.get("timestamp")), "value": float(d.get("probability", 0.0))}
        for d in reversed(cal_trend_source)
    ]

    calibration_trend_by_model: dict[str, list[dict[str, Any]]] = {}
    model_calibration_lookup = {
        str(m.get("name")): max(0.0, min(1.0, _safe_float(m.get("calibration"), 0.5)))
        for m in models
    }

    for model_name in ordered_names:
        rows = by_model.get(model_name) or []
        points: list[dict[str, Any]] = []
        for row in reversed(rows[:50]):
            prob = _safe_float(row.get("probability"), -1.0)
            if prob < 0.0:
                continue
            points.append({
                "timestamp": str(row.get("timestamp", datetime.utcnow().isoformat())),
                "value": max(0.0, min(1.0, prob)),
            })

        if not points:
            target_calibration = model_calibration_lookup.get(model_name, 0.5)
            seed = (sum(ord(ch) for ch in model_name) % 7) - 3
            source_series = calibration_trend[-30:] if calibration_trend else []

            if source_series:
                synthetic_points: list[dict[str, Any]] = []
                for idx, base_point in enumerate(source_series):
                    base_value = max(0.0, min(1.0, _safe_float(base_point.get("value"), target_calibration)))
                    local_wave = ((idx % 5) - 2) * 0.0025
                    model_offset = seed * 0.0035
                    blended = (base_value * 0.35) + (target_calibration * 0.65) + local_wave + model_offset
                    synthetic_points.append({
                        "timestamp": str(base_point.get("timestamp", datetime.utcnow().isoformat())),
                        "value": round(max(0.0, min(1.0, blended)), 4),
                    })
                points = synthetic_points
            else:
                base_ts = datetime.utcnow().timestamp()
                points = [
                    {
                        "timestamp": datetime.fromtimestamp(base_ts + idx).isoformat(),
                        "value": round(max(0.0, min(1.0, target_calibration + (seed * 0.0035) + (((idx % 5) - 2) * 0.0025))), 4),
                    }
                    for idx in range(20)
                ]

        calibration_trend_by_model[model_name] = points

    active_model = next((m.get("name") for m in models if str(m.get("stage", "")).lower() == "production"), None)
    selected_model_name = str(active_model or (models[0].get("name") if models else ""))
    selected_trend = calibration_trend_by_model.get(selected_model_name, calibration_trend)

    return {
        "models": models,
        "disagreement": disagreement,
        "calibrationTrend": selected_trend,
        "calibrationTrendByModel": calibration_trend_by_model,
        "selectedCalibrationModel": selected_model_name,
    }


@app.get("/dashboard/governance")
@limiter.limit("30/minute")
def dashboard_governance(request: Request, role: str = Depends(check_role), mode: str = Query("online")):
    return _build_governance_payload(mode)


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
        normalized = value.strip()
        if normalized:
            try:
                if len(normalized) == 16 and normalized.endswith('Z') and normalized[8] == 'T':
                    parsed = datetime.strptime(normalized, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
                    return parsed
            except ValueError:
                pass
            normalized = normalized.replace("Z", "+00:00")
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
def dashboard_disaster_monitor(
    request: Request,
    role: str = Depends(check_role),
    limit: int = Query(20, ge=1, le=100),
    broaden_context: bool = Query(True),
):
    """
    Returns multi-source real-time disaster alerts including earthquakes, weather, wildfires,
    flood/storm/volcano events, humanitarian reports, and conflict incidents.

    When live signals are sparse, broadened context mode adds clearly tagged older incidents
    (last 7 days) for non-wildfire categories.
    """
    now_utc = datetime.now(timezone.utc)
    eq_cutoff = now_utc - timedelta(hours=48)
    weather_cutoff = now_utc - timedelta(hours=24)
    world_state_cutoff = now_utc - timedelta(hours=72)
    context_cutoff = now_utc - timedelta(days=7)

    def _severity_from_value(value: float) -> str:
        score = _safe_float(value, 0.0)
        if score >= 0.85:
            return "critical"
        if score >= 0.65:
            return "elevated"
        return "guarded"

    def _severity_rank(severity: str) -> int:
        return {"critical": 3, "elevated": 2, "guarded": 1}.get(str(severity).lower(), 0)

    def _context_rank(item: dict[str, Any]) -> int:
        return 0 if str(item.get("context_tag") or "live") == "older_7d" else 1

    def _is_severe_weather(doc: dict) -> bool:
        weather_text = str(_pick_nested(doc, "event", "data_weather", "data.weather", "data.description", default="")).lower()
        wind_speed = _safe_float(_pick_nested(doc, "wind_speed", "data_wind_speed", "data.wind_speed", default=0.0))
        severe_tokens = (
            "storm", "thunder", "flood", "hurricane", "cyclone", "tornado", "blizzard",
            "wildfire", "heatwave", "extreme", "warning", "alert"
        )
        return wind_speed >= 60 or any(token in weather_text for token in severe_tokens)

    def _map_world_state_item(doc: dict, *, context_tag: str = "live", is_broadened_context: bool = False) -> dict | None:
        source = str(doc.get("source") or "").lower().strip()
        signal_type = str(doc.get("signal_type") or "").lower().strip()
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
        category = str(meta.get("category") or "").lower()
        title = str(meta.get("title") or meta.get("place") or "").strip()
        country = str(doc.get("country") or "GLB").upper()
        lat = doc.get("lat")
        lon = doc.get("lon")
        value = _safe_float(doc.get("value"), 0.0)
        confidence = _safe_float(doc.get("confidence"), 0.5)
        timestamp = str(doc.get("timestamp_utc") or doc.get("timestamp") or now_utc.isoformat())

        event_type = ""
        if source == "firms":
            event_type = "wildfire"
        elif source == "acled":
            event_type = "conflict"
        elif source == "reliefweb":
            event_type = "humanitarian"
        elif source == "eonet":
            if "wildfire" in category:
                event_type = "wildfire"
            elif "volcano" in category:
                event_type = "volcano"
            elif "flood" in category:
                event_type = "flood"
            elif any(token in category for token in ("storm", "cyclone", "hurricane", "severe", "drought", "blizzard")):
                event_type = "storm"
            else:
                event_type = "weather"
        elif source == "usgs":
            event_type = "earthquake"
        elif signal_type == "humanitarian_pressure":
            event_type = "humanitarian"
        elif signal_type == "disaster_intensity":
            event_type = "weather"
        else:
            return None

        if not title:
            title = {
                "wildfire": "Active Wildfire Signals",
                "conflict": "Conflict Incident Signals",
                "humanitarian": "Humanitarian Situation Reports",
                "volcano": "Volcanic Activity",
                "flood": "Flood Event",
                "storm": "Storm Event",
                "weather": "Environmental Hazard",
            }.get(event_type, "Global Incident")

        location = country if country and country != "" else "GLB"
        if location == "GLB":
            title_parts = [part.strip() for part in title.split(",") if part and part.strip()]
            if len(title_parts) >= 2:
                location = ", ".join(title_parts[-2:])
            elif title_parts:
                location = title_parts[-1]

        severity = _severity_from_value(value)
        if event_type in {"conflict", "humanitarian"} and severity == "guarded":
            severity = "elevated"

        extra_fields: dict[str, Any] = {}
        if event_type == "earthquake":
            mag = _safe_float(meta.get("mag"), _safe_float(value * 8.0, 0.0))
            extra_fields["magnitude"] = round(mag, 2)
            if not title:
                title = f"Magnitude {round(mag, 1)} Earthquake"
            place = str(meta.get("place") or "").strip()
            if place:
                location = place

        return {
            "id": str(doc.get("id") or f"world-state-{source}-{event_type}-{title[:24]}-{timestamp}"),
            "type": event_type,
            "title": title,
            "location": location,
            "coordinates": {
                "lat": _safe_float(lat, 0.0),
                "lon": _safe_float(lon, 0.0),
            } if lat is not None and lon is not None else None,
            "severity": severity,
            "description": f"{source.upper()} signal: {signal_type or event_type}" + (f" | category: {category}" if category else ""),
            "timestamp": timestamp,
            "source": source.upper(),
            "confidence": round(max(0.0, min(1.0, confidence)), 3),
            "signal_value": round(value, 3),
            "category": category or None,
            **extra_fields,
            "context_tag": context_tag,
            "is_broadened_context": bool(is_broadened_context),
        }

    earthquake_pool = list(db.earthquakes.find().sort("collected_at", -1).limit(max(limit * 30, 400)))
    weather_pool = list(db.weather.find().sort("collected_at", -1).limit(max(limit * 25, 300)))
    world_state_pool = list(db.world_state_signals.find().sort("timestamp_utc", -1).limit(max(limit * 50, 1200)))

    recent_earthquakes = [
        doc for doc in earthquake_pool
        if _parse_timestamp(_safe_timestamp(doc, "timestamp", "data.time", "collected_at")) >= eq_cutoff
    ]
    weather_recent_all = [
        doc for doc in weather_pool
        if _parse_timestamp(_safe_timestamp(doc, "timestamp", "data_timestamp", "data.date", "collected_at")) >= weather_cutoff
    ]
    severe_weather = [doc for doc in weather_recent_all if _is_severe_weather(doc)]
    recent_world_state = [
        doc for doc in world_state_pool
        if _parse_timestamp(str(doc.get("timestamp_utc") or doc.get("timestamp") or "")) >= world_state_cutoff
    ]

    disaster_items: list[dict[str, Any]] = []

    for doc in recent_earthquakes:
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
            "source": "USGS",
            "context_tag": "live",
            "is_broadened_context": False,
        })

    for doc in severe_weather:
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
            "source": str(doc.get("source", "Weather API")),
            "is_fallback_observation": False,
            "context_tag": "live",
            "is_broadened_context": False,
        })

    for doc in recent_world_state:
        mapped = _map_world_state_item(doc, context_tag="live", is_broadened_context=False)
        if mapped is not None:
            disaster_items.append(mapped)

    # If no severe incidents exist at all, show a small live weather fallback slice.
    severe_exists = any(item.get("severity") in {"critical", "elevated"} for item in disaster_items)
    if not severe_exists and weather_recent_all:
        for doc in weather_recent_all[: min(max(2, limit // 3), 8)]:
            weather_text = str(_pick_nested(doc, "event", "data_weather", "data.weather", "data.description", default=""))
            city = str(_pick_nested(doc, "location", "data_city", "data.city", default="Unknown Location"))
            country = str(_pick_nested(doc, "country", "data_country", "data.country", default="")).strip()
            location = f"{city}, {country}" if country and country.lower() not in city.lower() else city
            disaster_items.append({
                "id": str(doc.get("_id", "")) + "-fallback",
                "type": "weather",
                "title": f"Weather Observation: {weather_text.title()}" if weather_text else "Weather Observation",
                "location": location,
                "severity": "guarded",
                "description": str(_pick_nested(doc, "description", "data_weather", "data.description", default=weather_text)),
                "temperature": _safe_float(_pick_nested(doc, "temperature", "data_temperature", "data.temperature", "data.temp", default=0.0)),
                "wind_speed": _safe_float(_pick_nested(doc, "wind_speed", "data_wind_speed", "data.wind_speed", default=0.0)),
                "timestamp": _safe_timestamp(doc, "timestamp", "data_timestamp", "data.date", "collected_at"),
                "source": str(doc.get("source", "Weather API")),
                "is_fallback_observation": True,
                "context_tag": "live",
                "is_broadened_context": False,
            })

    broadened_added = 0
    if broaden_context:
        live_non_fallback = [item for item in disaster_items if not bool(item.get("is_fallback_observation"))]
        live_types = {str(item.get("type") or "") for item in live_non_fallback}
        live_non_wildfire_count = sum(1 for item in live_non_fallback if str(item.get("type") or "") != "wildfire")
        sparse_live_mix = len(live_types) <= 2 or live_non_wildfire_count < 2

        if sparse_live_mix:
            older_quota = max(4, limit // 2)

            older_earthquakes = [
                doc for doc in earthquake_pool
                if context_cutoff <= _parse_timestamp(_safe_timestamp(doc, "timestamp", "data.time", "collected_at")) < eq_cutoff
            ]
            for doc in older_earthquakes:
                if broadened_added >= older_quota:
                    break
                magnitude = _safe_float(_pick_nested(doc, "magnitude", "data.magnitude", "data.mag", default=0.0))
                severity = "critical" if magnitude >= 7.0 else "elevated" if magnitude >= 5.0 else "guarded"
                disaster_items.append({
                    "id": str(doc.get("_id", "")) + "-older7d",
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
                    "source": "USGS",
                    "context_tag": "older_7d",
                    "is_broadened_context": True,
                })
                broadened_added += 1

            older_world_state = [
                doc for doc in world_state_pool
                if context_cutoff <= _parse_timestamp(str(doc.get("timestamp_utc") or doc.get("timestamp") or "")) < world_state_cutoff
            ]
            for doc in older_world_state:
                if broadened_added >= older_quota * 2:
                    break
                mapped = _map_world_state_item(doc, context_tag="older_7d", is_broadened_context=True)
                if mapped is None:
                    continue
                if str(mapped.get("type") or "") == "wildfire":
                    continue
                disaster_items.append(mapped)
                broadened_added += 1

    # De-duplicate near-identical entries.
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in disaster_items:
        ts = _parse_timestamp(str(item.get("timestamp") or "")).replace(second=0, microsecond=0).isoformat()
        key = f"{item.get('type')}|{item.get('location')}|{str(item.get('title') or '')[:64]}|{ts}|{item.get('context_tag') or 'live'}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    deduped.sort(
        key=lambda x: (
            _context_rank(x),
            _severity_rank(str(x.get("severity") or "")),
            _parse_timestamp(str(x.get("timestamp") or "")),
        ),
        reverse=True,
    )

    # Keep output diverse: include at least one item per available type before filling remaining slots.
    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in deduped:
        by_type[str(item.get("type") or "unknown")].append(item)

    for event_type in sorted(by_type.keys()):
        if len(selected) >= limit:
            break
        first = by_type[event_type][0]
        item_id = str(first.get("id") or "")
        selected.append(first)
        if item_id:
            used_ids.add(item_id)

    for item in deduped:
        if len(selected) >= limit:
            break
        item_id = str(item.get("id") or "")
        if item_id and item_id in used_ids:
            continue
        selected.append(item)
        if item_id:
            used_ids.add(item_id)

    if selected:
        last_updated = max(_parse_timestamp(str(item.get("timestamp") or "")) for item in selected).isoformat()
    else:
        last_updated = now_utc.isoformat()

    broadened_in_selected = sum(1 for item in selected if bool(item.get("is_broadened_context")))

    return {
        "items": selected,
        "last_updated": last_updated,
        "total_count": len(deduped),
        "context_mode": "broadened" if broadened_in_selected > 0 else "live_only",
        "broadened_context_added": broadened_in_selected,
        "broaden_context_enabled": bool(broaden_context),
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
def dashboard_health_alerts(
    request: Request,
    role: str = Depends(check_role),
    limit: int = Query(10, ge=1, le=50),
    broaden_context: bool = Query(True),
):
    """
    Returns WHO/health alerts with broadened context support.

    If live alerts are sparse, include clearly tagged older (last 30 days) indicator incidents.
    """
    now_utc = datetime.now(timezone.utc)
    live_cutoff = now_utc - timedelta(hours=72)
    context_cutoff = now_utc - timedelta(days=30)

    health_pool = list(db.health.find().sort("collected_at", -1).limit(max(limit * 40, 400)))
    legacy_pool = list(db.who.find().sort("collected_at", -1).limit(max(limit * 40, 400)))
    source_pool = health_pool if health_pool else legacy_pool
    if len(source_pool) < max(limit * 8, 80):
        source_pool = source_pool + [doc for doc in legacy_pool if doc not in source_pool]

    def _doc_ts(doc: dict) -> datetime:
        return _parse_timestamp(_safe_timestamp(doc, "timestamp", "data.timestamp", "collected_at"))

    def _build_health_item(doc: dict, idx: int, *, context_tag: str = "live", is_broadened_context: bool = False) -> dict[str, Any]:
        indicator = str(_pick_nested(doc, "data.indicator", "indicator", default="WHO Indicator"))
        disease_name = str(_pick_nested(doc, "data.disease", "disease", default="")).strip()
        cases_raw = _pick_nested(doc, "cases", "data.cases", "data.data.cases", default=None)
        deaths_raw = _pick_nested(doc, "deaths", "data.data.deaths", "data.deaths", default=None)
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
            # Indicator-only fallback severity so panel is not always "guarded" when values are high.
            if parsed_indicator_value is None:
                severity = "guarded"
            elif parsed_indicator_value >= 80:
                severity = "critical"
            elif parsed_indicator_value >= 40:
                severity = "elevated"
            else:
                severity = "guarded"
            status = "active" if severity in {"critical", "elevated"} else "monitoring"

        safe_deaths = None if deaths < 0 else max(deaths, 0)
        location = str(_pick_nested(doc, "country", "data.country", "data.SpatialDim", default="Global"))

        return {
            "id": str(doc.get("_id", f"health-{idx}")) + ("-ctx30d" if context_tag == "older_30d" else ""),
            "disease": (disease_name if disease_name else indicator.replace("_", " ")),
            "type": "outbreak" if has_outbreak_counts else "indicator",
            "severity": severity,
            "location": location,
            "cases": safe_cases,
            "deaths": safe_deaths,
            "indicator_value": parsed_indicator_value,
            "indicator_value_raw": str(indicator_value_raw) if indicator_value_raw not in (None, "") else None,
            "status": status,
            "timestamp": _safe_timestamp(doc, "timestamp", "data.timestamp", "collected_at"),
            "source": str(doc.get("source", "WHO")).upper(),
            "description": f"Latest WHO indicator update for {indicator.replace('_', ' ')} in {location}.",
            "context_tag": context_tag,
            "is_broadened_context": bool(is_broadened_context),
        }

    def _is_vaccine_doc(doc: dict) -> bool:
        indicator = str(_pick_nested(doc, "data.indicator", "indicator", default="")).lower()
        source_name = str(doc.get("source") or "").lower()
        return ("vacc" in indicator) or ("dose" in indicator) or ("immun" in indicator) or (source_name == "disease_sh_vaccine")

    live_docs = [doc for doc in source_pool if _doc_ts(doc) >= live_cutoff and (not _is_vaccine_doc(doc))]
    context_docs = [doc for doc in source_pool if context_cutoff <= _doc_ts(doc) < live_cutoff and (not _is_vaccine_doc(doc))]

    health_items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for idx, doc in enumerate(live_docs):
        item = _build_health_item(doc, idx, context_tag="live", is_broadened_context=False)
        key = f"{item['disease']}|{item['location']}|{item['type']}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        health_items.append(item)
        if len(health_items) >= limit * 3:
            break

    broadened_added = 0
    live_active_count = sum(1 for item in health_items if item.get("status") == "active")
    if broaden_context and (live_active_count < 2 or len(health_items) < limit):
        for idx, doc in enumerate(context_docs):
            item = _build_health_item(doc, idx, context_tag="older_30d", is_broadened_context=True)
            if item.get("severity") == "guarded":
                continue
            key = f"{item['disease']}|{item['location']}|{item['type']}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            health_items.append(item)
            broadened_added += 1
            if broadened_added >= max(4, limit // 2):
                break

    health_items.sort(
        key=lambda h: (
            0 if str(h.get("context_tag") or "live") == "older_30d" else 1,
            {"critical": 3, "elevated": 2, "guarded": 1}.get(str(h.get("severity") or "guarded"), 1),
            _parse_timestamp(str(h.get("timestamp") or "")),
        ),
        reverse=True,
    )
    non_covid_items = [h for h in health_items if "covid" not in str(h.get("disease") or "").lower()]
    covid_items = [h for h in health_items if "covid" in str(h.get("disease") or "").lower()]
    if len(non_covid_items) >= limit:
        health_items = non_covid_items[:limit]
    else:
        covid_cap = max(1, limit // 4)
        health_items = (non_covid_items + covid_items[:covid_cap])[:limit]

    vaccination_docs = [
        doc for doc in source_pool
        if any(token in str(_pick_nested(doc, "data.indicator", "indicator", default="")).lower() for token in ["vacc", "dose", "immun"])
    ]
    vaccination_values = [
        _extract_first_number(_pick_nested(doc, "data.value", "value", default=None), default=0.0) or 0.0
        for doc in vaccination_docs
    ]

    coverage_country_set = set()
    for doc in source_pool:
        c = str(_pick_nested(doc, "data.country", "country", "data.SpatialDim", default="")).strip().upper()
        if c and len(c) == 3 and c.isalpha():
            coverage_country_set.add(c)

    coverage_countries = min(len(coverage_country_set), 233)

    vaccination_data = {
        "global_coverage": round((coverage_countries / 233.0) * 100.0, 1),
        "target_coverage": 70.0,
        "doses_administered": int(sum(vaccination_values)) if vaccination_values else 0,
        "campaigns_active": len(vaccination_docs),
    }

    last_updated = _latest_timestamp(*source_pool[: max(1, min(len(source_pool), 25))]) if source_pool else now_utc.isoformat()

    return {
        "outbreaks": health_items,
        "vaccination": vaccination_data,
        "last_updated": last_updated,
        "total_active": len([h for h in health_items if h["status"] == "active"]),
        "context_mode": "broadened" if broadened_added > 0 else "live_only",
        "broadened_context_added": broadened_added,
        "broaden_context_enabled": bool(broaden_context),
        "coverage_countries": coverage_countries,
        "coverage_total_countries": 233,
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
        topic = str(_pick_nested(doc, "data.query", "topic", "data.topic", "data.keyword", default="")).strip()
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
        source_mode = str(_pick_nested(docs[0], "data.source_mode", default="interest_over_time"))
        region = str(_pick_nested(docs[0], "data.geo", "geo", default=""))
        stored_related = _pick_nested(docs[0], "data.related_queries", default=None)
        related_queries = stored_related if isinstance(stored_related, list) and stored_related else [
            f"{topic} news",
            f"{topic} latest",
            f"{topic} update"
        ]
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
            "source_mode": source_mode,
            "region": region,
            "related_queries": related_queries[:5]
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

            topic = str(_pick_nested(doc, "data.query", "topic", "data.topic", "data.keyword", default="")).strip()
            if not topic:
                continue
            topic_key = topic.lower()
            if topic_key in seen_topics:
                continue

            interest_score = _safe_int(
                _pick_nested(doc, "value", "data.value", "search_volume", "data.interest", "data.interest_score", default=0),
                default=0,
            )
            source_mode = str(_pick_nested(doc, "data.source_mode", default="interest_over_time"))
            region = str(_pick_nested(doc, "data.geo", "geo", default=""))
            stored_related = _pick_nested(doc, "data.related_queries", default=None)
            related_queries = stored_related if isinstance(stored_related, list) and stored_related else [
                f"{topic} news",
                f"{topic} latest",
                f"{topic} update"
            ]
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
                "source_mode": source_mode,
                "region": region,
                "related_queries": related_queries[:5]
            })
            seen_ids.add(fallback_id)
            seen_topics.add(topic_key)
    trend_items.sort(key=lambda x: (1 if str(x.get("source_mode") or "") == "trending_searches" else 0, x["interest_score"], _parse_timestamp(x["timestamp"])), reverse=True)
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
    history = _aggregate_global_history_from_country_features(mode="online", limit=48)
    history_source = "country_aggregated_history"
    if len(history) < 2:
        history = get_global_history(mode="online", limit=48)
        history_source = "global_history"
    if not history:
        raise HTTPException(status_code=404, detail="No historical features available")

    risk_scores: list[float] = []
    for row in history:
        features = (row.get("features") or {}) if isinstance(row, dict) else {}
        score = _parse_float_maybe(features.get("system_global_risk_score"))
        if score is None:
            score = _parse_float_maybe(features.get("global_risk_score"))
        if score is None:
            continue
        risk_scores.append(max(0.0, min(float(score), 100.0)))
    if not risk_scores:
        raise HTTPException(status_code=404, detail="No historical risk data available")

    current = risk_scores[-1]
    confidence = 0.8 if len(risk_scores) >= 12 else 0.65 if len(risk_scores) >= 6 else 0.55
    slope = 0.0 if len(risk_scores) < 2 else (risk_scores[-1] - risk_scores[0]) / max(1, len(risk_scores) - 1)
    proposed_24h = current + (slope * 24)
    horizon_bundle = _build_structural_forecast_horizons(
        current_risk=current,
        proposed_risk=proposed_24h,
        confidence_ratio=confidence,
        mode="online",
        horizon_hours=24,
    )
    horizon_map = {int(item.get("hours", 0)): item for item in horizon_bundle.get("horizons", []) if isinstance(item, dict)}
    quality = _prediction_quality_summary(mode="online")

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "current_sentiment": round(current, 4),
        "current_risk": round(current, 4),
        "forecast_1h": round(float((horizon_map.get(1) or {}).get("risk_score", current)), 4),
        "forecast_6h": round(float((horizon_map.get(6) or {}).get("risk_score", current)), 4),
        "forecast_24h": round(float((horizon_map.get(24) or {}).get("risk_score", current)), 4),
        "forecast_7d": round(float((horizon_map.get(168) or {}).get("risk_score", current)), 4),
        "confidence": confidence,
        "source": "bounded_risk_projection",
        "source_status": "derived_estimate",
        "model_version": "bounded_structural_projection_v2",
        "calibration_status": "structural_guarded",
        "prediction_interval": None,
        "fallback_reason": f"Structurally bounded projection over {len(risk_scores)} global risk points from {history_source}.",
        **quality,
    }


@app.get("/analytics/market-reactions")
@limiter.limit("15/minute")
def analytics_market_reactions(request: Request, role: str = Depends(check_role), limit: int = Query(20, ge=1, le=200)):
    def _build_rows(history_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows_local: list[dict[str, Any]] = []
        for prev, curr in zip(history_rows, history_rows[1:]):
            pf = prev.get("features", {})
            cf = curr.get("features", {})

            sentiment_impact = (float(cf.get("news_sentiment", 0.0)) - float(pf.get("news_sentiment", 0.0))) * 100

            crypto_return_delta = (float(cf.get("crypto_return", 0.0)) - float(pf.get("crypto_return", 0.0))) * 100
            crypto_vol_delta = (float(cf.get("crypto_volatility", 0.0)) - float(pf.get("crypto_volatility", 0.0))) * 100
            stock_return_delta = (float(cf.get("stock_return", 0.0)) - float(pf.get("stock_return", 0.0))) * 100
            stock_vol_delta = (float(cf.get("stock_volatility", 0.0)) - float(pf.get("stock_volatility", 0.0))) * 100

            # Blend return and volatility changes so market traces remain informative even during low-return windows.
            crypto_reaction = crypto_return_delta + (0.35 * crypto_vol_delta)
            stock_reaction = stock_return_delta + (0.35 * stock_vol_delta)

            market_combo = crypto_reaction + stock_reaction
            market_mag = abs(crypto_reaction) + abs(stock_reaction)
            sent_mag = abs(sentiment_impact)
            if sent_mag < 1e-9 and market_mag < 1e-9:
                corr = 0.0
            else:
                ratio = min(sent_mag, market_mag) / max(sent_mag, market_mag, 1e-9)
                direction_factor = 1.0 if (sentiment_impact * market_combo) >= 0 else 0.45
                corr = min(1.0, max(0.0, ratio * direction_factor))
                if sent_mag > 0.01 or market_mag > 0.01:
                    corr = max(0.05, corr)

            rows_local.append({
                "timestamp": str(curr.get("timestamp", datetime.utcnow().isoformat())),
                "event_type": "Feature shift",
                "sentiment_impact": round(sentiment_impact, 4),
                "crypto_reaction": round(crypto_reaction, 4),
                "stock_reaction": round(stock_reaction, 4),
                "correlation_strength": round(corr, 4),
            })

        return sorted(
            rows_local,
            key=lambda r: abs(float(r.get("sentiment_impact", 0.0))) + abs(float(r.get("crypto_reaction", 0.0))) + abs(float(r.get("stock_reaction", 0.0))),
            reverse=True,
        )

    # Primary source: country-aggregated history.
    history = _aggregate_global_history_from_country_features(mode="online", limit=min(500, max(limit + 36, 80)))
    if len(history) < 2:
        history = get_global_history(mode="online", limit=max(limit + 8, 40))

    rows = _build_rows(history)
    primary_move = max((abs(float(r.get("crypto_reaction", 0.0))) + abs(float(r.get("stock_reaction", 0.0))) for r in rows), default=0.0)

    # Fallback: if market channels are flat in country aggregates, use global history rows.
    if primary_move < 0.01:
        alt_history = get_global_history(mode="online", limit=max(limit + 36, 80))
        alt_rows = _build_rows(alt_history)
        alt_move = max((abs(float(r.get("crypto_reaction", 0.0))) + abs(float(r.get("stock_reaction", 0.0))) for r in alt_rows), default=0.0)
        if alt_move > primary_move:
            rows = alt_rows

    return rows[:limit]


@app.get("/analytics/incidents-outlook")
@app.get("/analytics/event-predictions")
@limiter.limit("60/minute")
def analytics_event_predictions(request: Request, role: str = Depends(check_role), limit: int = Query(233, ge=1, le=300)):
    def _normalize_risk_score(raw: Any, fallback: float = 50.0) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = fallback
        if value <= 1.0:
            value *= 100.0
        elif value <= 10.0:
            value *= 10.0
        return max(0.0, min(100.0, value))

    pipeline = [
        {"$match": {"mode": "online"}},
        {"$sort": {"timestamp": -1}},
        {"$group": {"_id": "$country", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$sort": {"timestamp": -1}},
        {"$limit": 1000},
    ]
    country_docs = list(country_features_collection.aggregate(pipeline))
    latest_by_country = {
        str(d.get("country", "")).upper(): d
        for d in country_docs
        if str(d.get("country", "")).strip()
    }

    events = []
    for country_code, d in latest_by_country.items():
        features = d.get("features")
        f = features if isinstance(features, dict) else {}
        risk = _normalize_risk_score(f.get("global_risk_score", 50.0), 50.0)

        baseline_docs = list(
            country_features_collection.find(
                {
                    "mode": "online",
                    "country": country_code,
                    "timestamp": {"$lt": d.get("timestamp")},
                },
                {"features.global_risk_score": 1},
            ).sort("timestamp", -1).limit(12)
        )
        baseline_vals = []
        for row in baseline_docs:
            rf = row.get("features") if isinstance(row.get("features"), dict) else {}
            baseline_vals.append(_normalize_risk_score(rf.get("global_risk_score", 50.0), 50.0))
        baseline = (sum(baseline_vals) / len(baseline_vals)) if baseline_vals else 50.0

        risk_delta = round(risk - baseline, 2)
        confidence = min(0.99, max(0.45, 0.58 + (abs(risk_delta) / 45.0)))
        ts_value = str(d.get("timestamp", datetime.utcnow().isoformat()))
        event_id = str(d.get("_id"))

        severity_score_raw = float(risk + (abs(risk_delta) * 1.75))
        events.append({
            "event_id": event_id,
            "event_type": "Country risk signal",
            "severity": 1,
            "predicted_risk_increase": round(risk_delta, 2),
            "affected_regions": [country_code],
            "confidence": round(confidence, 4),
            "timestamp": ts_value,
            "source": "country_risk_delta",
            "source_status": "derived_estimate",
            "model_version": "country_baseline_delta_v1",
            "fallback_reason": "Derived from current country risk versus recent baseline, then severity-ranked across countries.",
            "_severity_score_raw": severity_score_raw,
            "_risk_score": round(risk, 2),
        })

    # Assign severity as deciles across all countries so the distribution is informative.
    scores = sorted(float(e.get("_severity_score_raw", 0.0)) for e in events)
    total = max(len(scores), 1)
    for e in events:
        score = float(e.get("_severity_score_raw", 0.0))
        rank = bisect_right(scores, score)
        severity = max(1, min(10, int(((rank / float(total)) * 10.0) + 0.9999)))
        e["severity"] = severity
        e.pop("_severity_score_raw", None)

    # Surface meaningful changes first.
    events = sorted(
        events,
        key=lambda e: (
            abs(float(e.get("predicted_risk_increase", 0.0))),
            float(e.get("severity", 0.0)),
            float(e.get("_risk_score", 0.0)),
        ),
        reverse=True,
    )
    for e in events:
        e.pop("_risk_score", None)
    return events[:limit]


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
    available = [
        {
            "version": version,
            "stage": info.get("stage"),
            "registered_at": info.get("registered_at"),
            "promoted_at": info.get("promoted_at"),
        }
        for version, info in sorted(models.items())
    ]
    for version, info in models.items():
        if info.get("stage") == "production":
            return {
                "version": version,
                "metrics": info.get("metrics"),
                "registered_at": info.get("registered_at"),
                "promoted_at": info.get("promoted_at"),
                "available_models": available,
            }
    raise HTTPException(status_code=404, detail="No production model found")

# =====================================================
# PREDICT ENDPOINT
# =====================================================
@app.post("/predict")
@limiter.limit("10/minute")
def predict(request: Request, payload: PredictionRequest, role: str = Depends(check_role)):
    model, version, model_feature_names, schema_version = load_production_model_bundle()
    if model is None:
        raise HTTPException(status_code=404, detail="No production model available")

    expected_features = int(getattr(model, "n_features_in_", len(model_feature_names)) or len(model_feature_names))
    if len(model_feature_names) != expected_features:
        model_feature_names = model_feature_names[:expected_features] if len(model_feature_names) > expected_features else model_feature_names + [f"feature_{idx+1}" for idx in range(len(model_feature_names), expected_features)]

    aligned_features: list[float]
    provided_names: list[str] = []

    if payload.feature_map:
        provided_names = list(payload.feature_map.keys())
        aligned_features = [float(payload.feature_map.get(name, 0.0) or 0.0) for name in model_feature_names]
    elif payload.features is not None:
        raw_features = [float(value or 0.0) for value in payload.features]
        if payload.feature_names and len(payload.feature_names) == len(raw_features):
            feature_lookup = {str(name): raw_features[idx] for idx, name in enumerate(payload.feature_names)}
            provided_names = [str(name) for name in payload.feature_names]
            aligned_features = [float(feature_lookup.get(name, 0.0) or 0.0) for name in model_feature_names]
        elif len(raw_features) == expected_features:
            provided_names = list(model_feature_names)
            aligned_features = raw_features
        elif len(raw_features) == len(LEGACY_GLOBAL_PREDICTION_FEATURES) and expected_features >= len(raw_features):
            feature_lookup = {name: raw_features[idx] for idx, name in enumerate(LEGACY_GLOBAL_PREDICTION_FEATURES)}
            provided_names = list(LEGACY_GLOBAL_PREDICTION_FEATURES)
            aligned_features = [float(feature_lookup.get(name, 0.0) or 0.0) for name in model_feature_names]
        else:
            raise HTTPException(status_code=400, detail=f"Model expects {expected_features} features; received {len(raw_features)}")
    else:
        raise HTTPException(status_code=400, detail="Provide features, feature_names, or feature_map")

    try:
        raw_prediction = float(model.predict([aligned_features])[0])
        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba([aligned_features])[0]
            confidence = float(probabilities[1])
            prediction_output = int(raw_prediction)
            predicted_risk_score = round(confidence * 100.0, 4)
        else:
            predicted_risk_score = round(max(0.0, min(100.0, raw_prediction)), 4)
            confidence = round(predicted_risk_score / 100.0, 6)
            prediction_output = predicted_risk_score
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Prediction failed: {str(e)}")

    drift_score = compute_feature_drift(aligned_features, model_feature_names)
    record_prediction(
        prediction_collection=prediction_collection,
        model_monitoring_collection=model_monitoring_collection,
        model_version=version,
        features=aligned_features,
        feature_names=model_feature_names,
        schema_version=schema_version,
        prediction=float(prediction_output),
        probability=confidence,
        drift_score=drift_score,
        role=role,
        logger=logger,
    )
    runtime_metrics.on_prediction()

    logging.info(f"version={version} | feature_names={model_feature_names} | prediction={prediction_output} | confidence={confidence}")
    quality = _prediction_gate_action(mode="online")
    gate_action = str(quality.get("gate_action") or "allow")
    if gate_action == "suppress":
        confidence = 0.0
        prediction_output = 0.0
        predicted_risk_score = 0.0
        source_status = "withheld"
        fallback_reason = "Prediction suppressed because reliability thresholds failed."
    elif gate_action == "downgrade":
        confidence = min(float(confidence), 0.35)
        predicted_risk_score = round(confidence * 100.0, 4)
        source_status = "degraded_live_model"
        fallback_reason = "Prediction confidence downgraded because reliability thresholds were not fully met."
    else:
        source_status = "live_model"
        fallback_reason = None

    return {
        "model_version": version,
        "schema_version": schema_version,
        "feature_names": model_feature_names,
        "provided_feature_names": provided_names,
        "prediction": prediction_output,
        "predicted_risk_score": predicted_risk_score,
        "probability": confidence,
        "drift_score": drift_score,
        "source": "production_predict_endpoint",
        "source_status": source_status,
        "calibration_status": "probability_output" if hasattr(model, "predict_proba") else "score_output",
        "prediction_interval": None,
        "fallback_reason": fallback_reason,
        **quality,
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


@app.get("/observability/attention")
@limiter.limit("10/minute")
def observability_attention(
    request: Request,
    window_hours: int = Query(48, ge=6, le=168),
    role: str = Depends(require_admin),
):
    return _build_attention_observability(window_hours=window_hours)


@app.get("/observability/mobility")
@limiter.limit("10/minute")
def observability_mobility(
    request: Request,
    displacement_window_hours: int = Query(72, ge=12, le=336),
    aviation_window_hours: int = Query(18, ge=3, le=72),
    role: str = Depends(require_admin),
):
    return _build_mobility_observability(displacement_window_hours=displacement_window_hours, aviation_window_hours=aviation_window_hours)


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
    "mobility": 36.0,
    "aviation": 6.0,
    "economic_behavior": 72.0,
}

CORE_INGESTION_SOURCES = {
    "country_features",
    "global_features",
    "dashboard_features",
}


def _ingestion_source_tier(source: str) -> str:
    return "core" if source in CORE_INGESTION_SOURCES else "supporting"


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
        "mobility": _latest_collection_stamp(db["mobility"], ["collected_at", "timestamp", "created_at"]),
        "aviation": _latest_collection_stamp(db["aviation"], ["collected_at", "timestamp", "created_at"]),
        "economic_behavior": _latest_collection_stamp(db["economic_behavior"], ["collected_at", "timestamp", "created_at"]),
    }


def _build_freshness_snapshot(latest_ingestion: dict) -> dict:
    rows = []
    for source, stamp in latest_ingestion.items():
        age_hours = _hours_since(stamp)
        sla_hours = float(INGESTION_SLA_HOURS.get(source, 24.0))
        status = "unknown"
        if age_hours is not None:
            status = "fresh" if age_hours <= sla_hours else "stale"
        tier = _ingestion_source_tier(source)
        rows.append({
            "source": source,
            "tier": tier,
            "last_updated": stamp,
            "age_hours": round(age_hours, 3) if age_hours is not None else None,
            "sla_hours": sla_hours,
            "status": status,
        })

    known_rows = [r for r in rows if r.get("status") in {"fresh", "stale"}]
    core_rows = [r for r in known_rows if r.get("tier") == "core"]
    supporting_rows = [r for r in known_rows if r.get("tier") != "core"]
    known_ages = [float(r["age_hours"]) for r in rows if isinstance(r.get("age_hours"), (int, float))]
    fresh_count = len([r for r in rows if r.get("status") == "fresh"])
    stale_count = len([r for r in rows if r.get("status") == "stale"])
    fresh_core_count = len([r for r in core_rows if r.get("status") == "fresh"])
    stale_core_count = len([r for r in core_rows if r.get("status") == "stale"])
    fresh_supporting_count = len([r for r in supporting_rows if r.get("status") == "fresh"])
    stale_supporting_count = len([r for r in supporting_rows if r.get("status") == "stale"])
    known_total = max(fresh_count + stale_count, 1)
    core_total = max(fresh_core_count + stale_core_count, 1)

    overall_status = "healthy"
    if stale_core_count > 0:
        overall_status = "stale"
    elif stale_count > 0:
        overall_status = "degraded"

    return {
        "sources": rows,
        "fresh_count": fresh_count,
        "stale_count": stale_count,
        "unknown_count": len([r for r in rows if r.get("status") == "unknown"]),
        "fresh_core_count": fresh_core_count,
        "stale_core_count": stale_core_count,
        "fresh_supporting_count": fresh_supporting_count,
        "stale_supporting_count": stale_supporting_count,
        "freshness_ratio": round(float(fresh_count) / float(known_total), 4),
        "core_freshness_ratio": round(float(fresh_core_count) / float(core_total), 4),
        "oldest_age_hours": round(max(known_ages), 3) if known_ages else None,
        "newest_age_hours": round(min(known_ages), 3) if known_ages else None,
        "overall_status": overall_status,
    }


def _latest_global_features_doc(mode: str = "online") -> dict | None:
    doc = global_features_collection.find_one({"mode": mode}, sort=[("_id", DESCENDING)])
    if doc:
        return doc
    return dashboard_features_collection.find_one({"mode": mode}, sort=[("_id", DESCENDING)])


def _build_confidence_snapshot(mode: str = "online") -> dict:
    doc = get_latest_global_doc(mode=mode)
    features = doc.get("features") or {}
    forecast_contract = features.get("forecast_contract") if isinstance(features.get("forecast_contract"), dict) else _build_global_forecast_contract(mode=mode, features=features)
    mood_conf = features.get("global_mood_confidence")
    mood_unc = features.get("global_mood_uncertainty")
    forecast_delta = forecast_contract.get("risk_delta", features.get("forecast_risk_delta"))
    forecast_risk = forecast_contract.get("risk_score")
    risk_now = features.get("global_risk_score")
    return {
        "global_risk_score": float(risk_now) if risk_now is not None else None,
        "global_mood_confidence": float(mood_conf) if mood_conf is not None else None,
        "global_mood_uncertainty": float(mood_unc) if mood_unc is not None else None,
        "forecast_confidence": float(forecast_contract.get("confidence_ratio")) if forecast_contract.get("confidence_ratio") is not None else None,
        "forecast_confidence_score": float(forecast_contract.get("confidence_score")) if forecast_contract.get("confidence_score") is not None else None,
        "forecast_risk_delta": float(forecast_delta) if forecast_delta is not None else None,
        "forecast_risk_score": float(forecast_risk) if forecast_risk is not None else None,
        "forecast_source_status": forecast_contract.get("source_status"),
        "forecast_calibration_status": forecast_contract.get("calibration_status"),
        "forecast_gating_action": forecast_contract.get("gating_action"),
        "forecast_withheld": bool(forecast_contract.get("withheld")),
        "timestamp": str(features.get("timestamp") or doc.get("timestamp") or datetime.now(timezone.utc).isoformat()),
    }



def _prediction_quality_summary(mode: str = "online") -> dict[str, Any]:
    latest_ingestion = _build_latest_ingestion()
    freshness = _build_freshness_snapshot(latest_ingestion)
    source_health = _build_source_health_snapshot()
    coverage_snapshot = _compute_country_coverage_snapshot(mode=mode)
    quality_gate = _build_quality_gate_snapshot(coverage_snapshot, freshness, source_health)
    reasons = quality_gate.get("reasons") if isinstance(quality_gate.get("reasons"), list) else []
    return {
        "data_quality_status": "degraded" if bool(quality_gate.get("active")) else "healthy",
        "quality_gate": quality_gate,
        "freshness": {
            "overall_status": freshness.get("overall_status"),
            "freshness_ratio": freshness.get("freshness_ratio"),
            "core_freshness_ratio": freshness.get("core_freshness_ratio"),
        },
        "source_health": {
            "critical_down": int(source_health.get("critical_down_live", source_health.get("critical_down", 0)) or 0),
            "warning_count": int(source_health.get("warning_count", 0) or 0),
        },
        "coverage": {
            "verified": int(coverage_snapshot.get("verified", 0) or 0),
            "total": int(coverage_snapshot.get("total", 0) or 0),
        },
        "advisory": str(quality_gate.get("message") or "Coverage healthy"),
        "reasons": [str(reason) for reason in reasons if str(reason).strip()],
    }



def _build_prediction_feature_snapshot(mode: str = "online") -> list[dict[str, Any]]:
    feature_specs = {
        "news_sentiment": {"label": "News Sentiment", "scale": "sentiment", "importance_scale": 1.0},
        "gdelt_sentiment": {"label": "GDELT Sentiment", "scale": "sentiment", "importance_scale": 1.0},
        "crypto_return": {"label": "Crypto Return", "scale": "return", "importance_scale": 0.08},
        "crypto_volatility": {"label": "Crypto Volatility", "scale": "volatility", "importance_scale": 40.0},
        "stock_return": {"label": "Stock Return", "scale": "return", "importance_scale": 0.05},
        "stock_volatility": {"label": "Stock Volatility", "scale": "volatility", "importance_scale": 4.0},
        "weather_anomaly": {"label": "Weather Anomaly", "scale": "sentiment", "importance_scale": 1.0},
        "direct_behavior_score": {"label": "Direct Behavior", "scale": "absolute_100", "importance_scale": 100.0},
        "contextual_pressure_score": {"label": "Context Pressure", "scale": "absolute_100", "importance_scale": 100.0},
        "evidence_quality_score": {"label": "Evidence Quality", "scale": "absolute_100", "importance_scale": 100.0},
        "narrative_velocity_score": {"label": "Narrative Velocity", "scale": "normalized", "importance_scale": 1.0},
        "coordination_risk_score": {"label": "Coordination Risk", "scale": "normalized", "importance_scale": 1.0},
        "mobility_disruption_score": {"label": "Mobility Disruption", "scale": "normalized", "importance_scale": 1.0},
        "logistics_stress_score": {"label": "Logistics Stress", "scale": "normalized", "importance_scale": 1.0},
        "household_stress_score": {"label": "Household Stress", "scale": "normalized", "importance_scale": 1.0},
        "fuel_price_pressure": {"label": "Fuel Pressure", "scale": "normalized", "importance_scale": 1.0},
        "food_price_pressure": {"label": "Food Pressure", "scale": "normalized", "importance_scale": 1.0},
        "labor_stress_score": {"label": "Labor Stress", "scale": "normalized", "importance_scale": 1.0},
        "fx_pressure_score": {"label": "FX Pressure", "scale": "normalized", "importance_scale": 1.0},
        "remittance_stress_score": {"label": "Remittance Stress", "scale": "normalized", "importance_scale": 1.0},
        "energy_stress_score": {"label": "Energy Stress", "scale": "normalized", "importance_scale": 1.0},
        "global_behavior_index": {"label": "Behavior Index", "scale": "absolute_100", "importance_scale": 100.0},
        "global_context_index": {"label": "Context Index", "scale": "absolute_100", "importance_scale": 100.0},
        "global_attention_index": {"label": "Attention Index", "scale": "absolute_100", "importance_scale": 100.0},
        "global_disruption_index": {"label": "Disruption Index", "scale": "absolute_100", "importance_scale": 100.0},
        "global_economic_stress_index": {"label": "Economic Stress Index", "scale": "absolute_100", "importance_scale": 100.0},
        "global_risk_score": {"label": "Global Risk Score", "scale": "absolute_100", "importance_scale": 100.0},
    }

    try:
        latest_doc = get_latest_global_doc(mode)
        features = (latest_doc or {}).get("features", {}) if isinstance(latest_doc, dict) else {}
    except Exception:
        features = {}

    def _raw_float(key: str) -> float:
        try:
            return float(features.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    snapshot: list[dict[str, Any]] = []
    for key, spec in feature_specs.items():
        raw_value = _raw_float(key)
        scale = str(spec.get("scale") or "normalized")
        importance_scale = float(spec.get("importance_scale") or 1.0)

        if scale == "absolute_100":
            display_value = round(max(0.0, min(raw_value, 100.0)), 2)
            normalized_value = round(display_value / 100.0, 4)
        elif scale == "normalized":
            display_value = round(max(0.0, min(raw_value, 1.0)) * 100.0, 2)
            normalized_value = round(max(0.0, min(raw_value, 1.0)), 4)
        elif scale == "return":
            display_value = round(raw_value * 100.0, 3)
            normalized_value = round(max(-1.0, min(1.0, raw_value / importance_scale if importance_scale else raw_value)), 4)
        elif scale == "volatility":
            scaled = abs(raw_value) / importance_scale if importance_scale else abs(raw_value)
            normalized_value = round(max(0.0, min(math.tanh(scaled), 1.0)), 4)
            display_value = round(raw_value, 3)
        else:  # sentiment / signed bounded signal
            display_value = round(raw_value, 3)
            normalized_value = round(max(-1.0, min(1.0, raw_value / importance_scale if importance_scale else raw_value)), 4)

        importance = round(abs(normalized_value) * 100.0, 2)
        direction = "positive" if normalized_value >= 0 else "negative"
        snapshot.append({
            "key": key,
            "label": str(spec.get("label") or key),
            "value": display_value,
            "raw_value": round(raw_value, 6),
            "normalized_value": normalized_value,
            "importance": importance,
            "direction": direction,
            "scale": scale,
        })

    snapshot.sort(key=lambda entry: (float(entry.get("importance", 0.0)), float(entry.get("value", 0.0))), reverse=True)
    return snapshot


def _prediction_gate_action(mode: str = "online") -> dict[str, Any]:
    quality = _prediction_quality_summary(mode=mode)
    gate = quality.get("quality_gate") if isinstance(quality.get("quality_gate"), dict) else {}
    status = str(gate.get("status") or "sufficient")
    severe_statuses = {
        "global_reliability_degraded",
        "freshness_and_sources_degraded",
        "critical_source_outage",
    }
    degraded_statuses = {
        "coverage_and_freshness_degraded",
        "coverage_and_sources_degraded",
        "stale_global_data",
        "insufficient_global_coverage",
    }
    if status in severe_statuses:
        action = "suppress"
    elif bool(gate.get("active")) or status in degraded_statuses:
        action = "downgrade"
    else:
        action = "allow"
    return {
        **quality,
        "gate_action": action,
        "prediction_available": action != "suppress",
    }


def _infer_forecast_calibration_status(model_type: str | None, basis: str | None, source_status: str | None) -> str:
    source_text = f"{model_type or ''} {basis or ''} {source_status or ''}".lower()
    if str(source_status or '').lower() == 'withheld':
        return 'withheld'
    if any(token in source_text for token in ('fallback', 'heuristic', 'trend_extrapolation', 'statistical', 'derived')):
        return 'fallback'
    if any(token in source_text for token in ('calibrated', 'lstm', 'ensemble', 'advanced', 'production')):
        return 'calibrated'
    return 'unknown'


def _normalize_prediction_interval(interval: Any) -> dict[str, float] | None:
    if not isinstance(interval, dict):
        return None
    values = {}
    for key in ('p10', 'p50', 'p90'):
        value = _parse_float_maybe(interval.get(key))
        if value is not None:
            values[key] = round(max(0.0, min(float(value), 100.0)), 2)
    return values or None


def _prediction_row_hours(row: Any) -> int | None:
    if not isinstance(row, dict):
        return None
    direct = _parse_float_maybe(row.get('horizon_hours'))
    if direct is None:
        direct = _parse_float_maybe(row.get('hours'))
    if direct is not None:
        return max(1, int(round(float(direct))))
    horizon = str(row.get('horizon') or '').strip().lower()
    mapping = {
        '1h': 1,
        '6h': 6,
        '24h': 24,
        '1d': 24,
        '7d': 168,
        '7day': 168,
        '7days': 168,
    }
    return mapping.get(horizon)


def _select_prediction_row(prediction_rows: list[dict[str, Any]], preferred_hours: int = 24) -> dict[str, Any]:
    exact_match = None
    closest_match = None
    closest_distance = None
    fallback = {}
    for row in prediction_rows:
        if not isinstance(row, dict):
            continue
        if not fallback:
            fallback = row
        hours = _prediction_row_hours(row)
        if hours is None:
            continue
        if hours == preferred_hours:
            exact_match = row
            break
        distance = abs(hours - preferred_hours)
        if closest_distance is None or distance < closest_distance:
            closest_match = row
            closest_distance = distance
    return exact_match or closest_match or fallback


def _recent_global_risk_scores(mode: str = 'online', limit: int = 24) -> list[float]:
    history = _aggregate_global_history_from_country_features(mode=mode, limit=limit)
    if len(history) < 2:
        history = get_global_history(mode=mode, limit=limit)
    scores: list[float] = []
    for row in history:
        features = (row.get('features') or {}) if isinstance(row, dict) else {}
        score = _parse_float_maybe(features.get('system_global_risk_score'))
        if score is None:
            score = _parse_float_maybe(features.get('global_risk_score'))
        if score is None:
            continue
        scores.append(max(0.0, min(float(score), 100.0)))
    return scores


def _latest_country_risk_scores(mode: str = 'online', limit: int = 800) -> list[float]:
    scores: list[float] = []
    seen: set[str] = set()
    try:
        docs = db.country_features.find({'mode': mode}).sort('timestamp', -1).limit(limit)
        for doc in docs:
            country = str(doc.get('country') or '').strip().upper()
            if not country or country in seen:
                continue
            seen.add(country)
            features = doc.get('features') or {}
            score = _parse_float_maybe(features.get('global_risk_score'))
            if score is None:
                continue
            scores.append(max(0.0, min(float(score), 100.0)))
    except Exception:
        return []
    return scores


def _build_structural_forecast_horizons(
    current_risk: float,
    proposed_risk: float | None,
    confidence_ratio: float,
    *,
    mode: str = 'online',
    horizon_hours: int = 24,
) -> dict[str, Any]:
    current = max(0.0, min(float(current_risk or 50.0), 100.0))
    proposed = current if proposed_risk is None else max(0.0, min(float(proposed_risk), 100.0))
    confidence = max(0.0, min(float(confidence_ratio or 0.0), 1.0))

    recent_scores = _recent_global_risk_scores(mode=mode, limit=max(24, horizon_hours))
    recent_window = recent_scores[-12:] if recent_scores else [current]
    recent_peak = max(recent_window) if recent_window else current

    country_scores = _latest_country_risk_scores(mode=mode)
    top_scores = sorted(country_scores, reverse=True)[:12]
    top_mean = (sum(top_scores) / len(top_scores)) if top_scores else current
    critical_count = sum(1 for score in country_scores if score >= 85.0)
    high_count = sum(1 for score in country_scores if score >= 65.0)

    structural_support = max(35.0, min(82.0, top_mean * 0.72))
    if critical_count >= 4:
        structural_support = max(structural_support, 62.0 + min((critical_count - 4) * 1.4, 10.0))
    if high_count >= 12:
        structural_support = max(structural_support, 58.0 + min((high_count - 12) * 0.5, 8.0))

    history_support = max(35.0, recent_peak - (8.0 if current >= 65.0 else 12.0 if current >= 50.0 else 16.0))
    movement_scale = 0.7 + (confidence * 0.6)
    max_drop_24h = (4.5 if current >= 75.0 else 6.0 if current >= 65.0 else 8.0 if current >= 50.0 else 10.0) * movement_scale
    support_floor = max(current - max_drop_24h, history_support, structural_support)

    upper_cap = min(100.0, max(current + max(6.0, 10.0 * movement_scale), recent_peak + 4.0))
    target_24h = max(support_floor, min(upper_cap, proposed))

    easing_denominator = max(float(horizon_hours), 24.0) / 2.6
    easing_denominator = max(easing_denominator, 1.0)

    def _interpolate(hours: int) -> float:
        if hours >= 24:
            return target_24h
        progress = 1.0 - math.exp(-float(hours) / easing_denominator)
        return current + ((target_24h - current) * progress)

    score_1h = max(0.0, min(100.0, _interpolate(1)))
    score_6h = max(0.0, min(100.0, _interpolate(6)))
    score_24h = max(0.0, min(100.0, target_24h))

    seven_day_support = max(support_floor, score_24h - max(2.5, abs(score_24h - current) * 0.25))
    seven_day_continuation = score_24h + max(0.0, score_24h - current) * 0.35
    score_7d = max(seven_day_support, min(100.0, seven_day_continuation))

    horizons = [
        {'label': '1h', 'hours': 1, 'risk_score': round(score_1h, 2), 'risk_delta': round(score_1h - current, 2)},
        {'label': '6h', 'hours': 6, 'risk_score': round(score_6h, 2), 'risk_delta': round(score_6h - current, 2)},
        {'label': '24h', 'hours': 24, 'risk_score': round(score_24h, 2), 'risk_delta': round(score_24h - current, 2)},
        {'label': '7d', 'hours': 168, 'risk_score': round(score_7d, 2), 'risk_delta': round(score_7d - current, 2)},
    ]
    return {
        'support_floor': round(support_floor, 2),
        'structural_support': round(structural_support, 2),
        'history_support': round(history_support, 2),
        'critical_country_count': critical_count,
        'high_country_count': high_count,
        'horizons': horizons,
    }


def _build_global_forecast_contract(
    mode: str = 'online',
    *,
    features: dict[str, Any] | None = None,
    predictions_payload: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if features is None:
        latest_doc = get_latest_global_doc(mode)
        features = (latest_doc or {}).get('features', {}) if isinstance(latest_doc, dict) else {}
    if not isinstance(features, dict):
        features = {}
    quality = quality if isinstance(quality, dict) else _prediction_gate_action(mode=mode)
    gate_action = str(quality.get('gate_action') or 'allow')
    payload = predictions_payload if isinstance(predictions_payload, dict) else {}
    prediction_rows = payload.get('predictions') if isinstance(payload.get('predictions'), list) else []
    selected_prediction = _select_prediction_row([row for row in prediction_rows if isinstance(row, dict)], preferred_hours=24)

    current_risk = _parse_float_maybe(features.get('system_global_risk_score'))
    if current_risk is None:
        current_risk = _parse_float_maybe(features.get('global_risk_score'))
    if current_risk is None:
        current_risk = _parse_float_maybe(features.get('legacy_model_global_risk_score'))
    current_risk = max(0.0, min(float(current_risk if current_risk is not None else 50.0), 100.0))

    risk_candidate = _parse_float_maybe(selected_prediction.get('risk_score'))
    if risk_candidate is None:
        risk_candidate = _parse_float_maybe(features.get('forecast_risk_score'))
    if risk_candidate is None:
        risk_candidate = current_risk

    confidence_candidate = _parse_float_maybe(selected_prediction.get('confidence'))
    if confidence_candidate is None:
        confidence_candidate = _parse_float_maybe(features.get('forecast_confidence'))
    confidence_ratio = max(0.0, min(float(confidence_candidate or 0.0), 1.0))

    selected_horizon_hours = _prediction_row_hours(selected_prediction)
    horizon_hours = max(1, int(selected_horizon_hours or _parse_float_maybe(features.get('forecast_horizon_hours')) or 24))

    source_status = str(payload.get('source_status') or '').strip().lower()
    basis = str(features.get('forecast_basis') or payload.get('source') or 'global_forecast_contract')
    model_version = str(payload.get('model_type') or features.get('forecast_model_version') or features.get('model_version') or 'unknown')
    calibration_status = str(payload.get('calibration_status') or _infer_forecast_calibration_status(model_version, basis, source_status))

    horizon_bundle = _build_structural_forecast_horizons(
        current_risk=current_risk,
        proposed_risk=risk_candidate,
        confidence_ratio=confidence_ratio,
        mode=mode,
        horizon_hours=horizon_hours,
    )
    horizon_map = {int(item.get('hours', 0)): item for item in horizon_bundle.get('horizons', []) if isinstance(item, dict)}
    selected_horizon = horizon_map.get(24) or next(iter(horizon_map.values()), {'risk_score': current_risk, 'risk_delta': 0.0})

    if gate_action == 'suppress':
        source_status = 'withheld'
        calibration_status = 'withheld'
        risk_score = None
        risk_delta = None
        prediction_interval = None
        horizons = []
    else:
        if not source_status:
            if calibration_status == 'calibrated':
                source_status = 'calibrated_model'
            elif calibration_status == 'fallback':
                source_status = 'fallback'
            else:
                source_status = 'derived_estimate' if risk_candidate is not None else 'model_unavailable'
        risk_score = round(max(0.0, min(float(selected_horizon.get('risk_score', current_risk) or current_risk), 100.0)), 2)
        risk_delta = round(float(selected_horizon.get('risk_delta', risk_score - current_risk) or 0.0), 2)
        prediction_interval = _normalize_prediction_interval(selected_prediction.get('interval'))
        horizons = horizon_bundle.get('horizons', [])

    reasons = [str(reason) for reason in (quality.get('reasons') or []) if str(reason).strip()]
    fallback_reason = str(payload.get('fallback_reason') or '').strip()
    if fallback_reason and fallback_reason not in reasons:
        reasons.append(fallback_reason)
    if gate_action != 'suppress' and risk_candidate is not None and abs(float(risk_candidate) - float(risk_score or current_risk)) >= 3.0:
        reasons.append('Forecast bounded by structural global-risk support to prevent unrealistic unwind.')

    contract = {
        'source': str(payload.get('source') or 'global_forecast_contract'),
        'source_status': source_status,
        'calibration_status': calibration_status,
        'gating_action': gate_action,
        'prediction_available': gate_action != 'suppress',
        'withheld': gate_action == 'suppress',
        'risk_score': risk_score,
        'confidence_ratio': round(confidence_ratio, 4),
        'confidence_score': round(confidence_ratio * 100.0, 2),
        'risk_delta': risk_delta,
        'horizon_hours': 24,
        'prediction_interval': prediction_interval,
        'advisory': str(payload.get('fallback_reason') or quality.get('advisory') or 'Forecast available'),
        'reasons': reasons,
        'quality_status': str(quality.get('data_quality_status') or 'healthy'),
        'basis': basis,
        'model_version': model_version,
        'generated_at': generated_at or str(features.get('timestamp') or datetime.now(timezone.utc).isoformat()),
        'support_floor': horizon_bundle.get('support_floor'),
        'horizons': horizons,
        'score_semantics': {
            'risk_score': '0-100 forecast risk score; null when quality gating withholds the forecast.',
            'confidence_score': '0-100 forecast confidence after gating and calibration semantics are applied.',
            'gating_action': 'allow, downgrade, or suppress depending on freshness, coverage, and source-health reliability.',
            'source_status': 'calibrated_model, degraded_calibrated_model, fallback, degraded_fallback, derived_estimate, model_unavailable, or withheld.',
        },
    }
    return contract


def _extract_advanced_insights_results(insights: Any) -> dict[str, Any]:
    if isinstance(insights, dict) and 'results' in insights:
        return insights.get('results', {}) or {}
    if isinstance(insights, dict) and 'status' in insights:
        return insights
    return insights if isinstance(insights, dict) else {}


def _store_advanced_insights_cache(result: dict[str, Any]) -> dict[str, Any]:
    global ADVANCED_INSIGHTS_CACHE
    global ADVANCED_INSIGHTS_CACHE_AT
    ADVANCED_INSIGHTS_CACHE = result
    ADVANCED_INSIGHTS_CACHE_AT = time.time()
    return result


def _load_advanced_insights_results() -> dict[str, Any]:
    global ADVANCED_INSIGHTS_FUTURE
    global ADVANCED_INSIGHTS_FUTURE_STARTED_AT

    from machine_learning.advanced_analytics import run_advanced_analytics

    now_ts = time.time()
    future = None
    with ADVANCED_INSIGHTS_CACHE_LOCK:
        if _advanced_insights_cache_fresh(now_ts):
            return ADVANCED_INSIGHTS_CACHE

        if ADVANCED_INSIGHTS_FUTURE is not None and ADVANCED_INSIGHTS_FUTURE.done():
            try:
                completed = _extract_advanced_insights_results(ADVANCED_INSIGHTS_FUTURE.result())
            except Exception as exc:
                logger.warning('advanced_insights_cached_future_failed error=%s', exc)
            else:
                _store_advanced_insights_cache(completed)
            ADVANCED_INSIGHTS_FUTURE = None
            ADVANCED_INSIGHTS_FUTURE_STARTED_AT = 0.0
            if _advanced_insights_cache_fresh(now_ts):
                return ADVANCED_INSIGHTS_CACHE

        if ADVANCED_INSIGHTS_FUTURE is not None and (now_ts - ADVANCED_INSIGHTS_FUTURE_STARTED_AT) > ADVANCED_INSIGHTS_STALL_SECONDS:
            _reset_advanced_insights_executor('stalled_future')

        if ADVANCED_INSIGHTS_FUTURE is None:
            ADVANCED_INSIGHTS_FUTURE = ADVANCED_INSIGHTS_EXECUTOR.submit(run_advanced_analytics)
            ADVANCED_INSIGHTS_FUTURE_STARTED_AT = now_ts

        future = ADVANCED_INSIGHTS_FUTURE

    try:
        resolved = _extract_advanced_insights_results(future.result(timeout=ADVANCED_INSIGHTS_WAIT_TIMEOUT_SECONDS))
    except FuturesTimeoutError as exc:
        with ADVANCED_INSIGHTS_CACHE_LOCK:
            if _advanced_insights_cache_fresh():
                return ADVANCED_INSIGHTS_CACHE
        raise RuntimeError('Advanced analytics computation still in progress') from exc
    except Exception as exc:
        with ADVANCED_INSIGHTS_CACHE_LOCK:
            if ADVANCED_INSIGHTS_FUTURE is future:
                ADVANCED_INSIGHTS_FUTURE = None
                ADVANCED_INSIGHTS_FUTURE_STARTED_AT = 0.0
            if _advanced_insights_cache_fresh():
                return ADVANCED_INSIGHTS_CACHE
        raise RuntimeError(f'Advanced analytics computation failed: {exc}') from exc

    with ADVANCED_INSIGHTS_CACHE_LOCK:
        if ADVANCED_INSIGHTS_FUTURE is future:
            ADVANCED_INSIGHTS_FUTURE = None
            ADVANCED_INSIGHTS_FUTURE_STARTED_AT = 0.0
        return _store_advanced_insights_cache(resolved)


@app.get("/trust/reliability")
@limiter.limit("20/minute")
def trust_reliability(request: Request, role: str = Depends(check_role), mode: str = Query("online")):
    cache_key = f"mode={mode}"
    cached = _dashboard_cache_get("trust", cache_key)
    if isinstance(cached, dict):
        return cached

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
    source_health = _build_source_health_snapshot()
    coverage_snapshot = _compute_country_coverage_snapshot(mode=mode)
    quality_gate = _build_quality_gate_snapshot(coverage_snapshot, freshness, source_health)
    mobility_snapshot = _build_mobility_observability()
    economic_snapshot = _build_economic_observability()
    alerts = _build_operational_alerts(freshness, source_health, mobility_snapshot, economic_snapshot)
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
        "source_health": source_health,
        "coverage": coverage_snapshot,
        "quality_gate": quality_gate,
        "confidence": _build_confidence_snapshot(mode=mode),
        "mobility": mobility_snapshot,
        "economic": economic_snapshot,
        "alerts": alerts,
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

    return _dashboard_cache_set("trust", cache_key, payload)


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


def _latest_collection_stamp(collection, keys: list[str], max_scan: int = 25) -> str | None:
    docs = list(collection.find().sort("_id", DESCENDING).limit(max_scan))
    if not docs:
        return None

    for doc in docs:
        for key in keys:
            value = doc.get(key)
            if value is None:
                continue
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, str) and value.strip():
                return value
            if value:
                return str(value)
            nested = doc.get("data") if isinstance(doc.get("data"), dict) else {}
            nested_value = nested.get(key) if isinstance(nested, dict) else None
            if isinstance(nested_value, datetime):
                return nested_value.isoformat()
            if isinstance(nested_value, str) and nested_value.strip():
                return nested_value
            if nested_value:
                return str(nested_value)

    return None


def _trigger_country_refresh_async(age_seconds: float) -> bool:
    global COUNTRY_REFRESH_STARTED_AT

    if age_seconds < COUNTRY_REFRESH_TRIGGER_AGE_SECONDS:
        return False

    now_ts = time.time()
    if now_ts - COUNTRY_REFRESH_STARTED_AT < COUNTRY_REFRESH_MIN_INTERVAL_SECONDS:
        return False

    if not COUNTRY_REFRESH_LOCK.acquire(blocking=False):
        return False

    COUNTRY_REFRESH_STARTED_AT = now_ts

    def _runner() -> None:
        try:
            country_daily_refresh_if_due(
                max_records=COUNTRY_REFRESH_MAX_RECORDS,
                batch_size=COUNTRY_REFRESH_BATCH_SIZE,
            )
        except Exception as exc:
            logger.warning("country_refresh_on_demand_failed", extra={"event": {"error": str(exc)}})
        finally:
            COUNTRY_REFRESH_LOCK.release()

    threading.Thread(target=_runner, name="country-refresh-on-demand", daemon=True).start()
    return True


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
        "mobility": _latest_collection_stamp(db["mobility"], ["collected_at", "timestamp", "created_at"]),
        "aviation": _latest_collection_stamp(db["aviation"], ["collected_at", "timestamp", "created_at"]),
        "economic_behavior": _latest_collection_stamp(db["economic_behavior"], ["collected_at", "timestamp", "created_at"]),
    }

    mobility_snapshot = _build_mobility_observability(displacement_window_hours=72, aviation_window_hours=18, max_countries=8)
    economic_snapshot = _build_economic_observability(window_hours=96, max_countries=8)
    freshness_snapshot = _build_freshness_snapshot(latest_ingestion)
    source_health_snapshot = _build_source_health_snapshot()
    operational_alerts = _build_operational_alerts(freshness_snapshot, source_health_snapshot, mobility_snapshot, economic_snapshot)

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
            "freshness": freshness_snapshot,
            "source_health": source_health_snapshot,
            "mobility": mobility_snapshot,
            "economic": economic_snapshot,
            "alerts": operational_alerts,
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
            # If token is invalid/expired, continue to Authorization/API key fallback.
            pass

    bearer = (authorization or "").strip()
    if bearer.lower().startswith("bearer "):
        try:
            return decode_access_token(bearer.split(" ", 1)[1].strip(), source="websocket_authorization_header")
        except HTTPException:
            # Fall through to API key fallback.
            pass

    return _identity_from_api_key(x_api_key or api_key)


# =====================================================
# REAL-TIME RISK STREAM
# =====================================================
LIVE_UPDATE_TOPIC = "country_risk_updates"
WS_CONSUMER_TIMEOUT_MS = 250
WS_IDLE_KEEPALIVE_SECONDS = 20.0


def _live_consumer_config(topic: str, group_prefix: str) -> dict:
    return {
        "topics": [topic],
        # Live dashboard sockets are fan-out readers, not work-sharing consumers.
        # Avoid creating ephemeral consumer groups for each websocket connection.
        "group_id": None,
        "auto_offset_reset": "latest",
        "enable_auto_commit": False,
        "consumer_timeout_ms": WS_CONSUMER_TIMEOUT_MS,
    }



def _drain_consumer_messages(active_consumer, timeout_ms: int = WS_CONSUMER_TIMEOUT_MS, max_records: int = 64) -> list[dict]:
    records = active_consumer.poll(timeout_ms=timeout_ms, max_records=max_records)
    messages = []
    for batch in records.values():
        for message in batch:
            if isinstance(message.value, dict):
                messages.append(message.value)
    return messages



def _connect_live_consumer(topic: str, group_prefix: str):
    return get_consumer(**_live_consumer_config(topic, group_prefix))



def _latest_online_global_doc() -> dict:
    try:
        return get_latest_global_doc(mode="online") or {}
    except Exception:
        return db.global_features.find_one({"mode": "online"}, sort=[("_id", DESCENDING)]) or {}



def _build_live_risk_snapshot(trigger: dict | None = None) -> dict:
    doc = _latest_online_global_doc()
    features = doc.get("features") or {}
    top_topics = features.get("top_topics") or ["no data"]
    if not isinstance(top_topics, list):
        top_topics = [str(top_topics)]

    payload = {
        "type": "risk_update",
        "timestamp": str(doc.get("timestamp") or features.get("timestamp") or datetime.utcnow().isoformat()),
        "global_risk_score": float(features.get("global_risk_score", 50) or 50),
        "global_mood_score": float(features.get("global_mood_score", features.get("global_risk_score", 50)) or 50),
        "global_mood_confidence": float(features.get("global_mood_confidence", 0.0) or 0.0),
        "global_mood_uncertainty": float(features.get("global_mood_uncertainty", 18.0) or 18.0),
        "global_mood_verified_countries": int(features.get("global_mood_verified_countries", 0) or 0),
        "global_mood_eligible_countries": int(features.get("global_mood_eligible_countries", 0) or 0),
        "global_mood_used_countries": int(features.get("global_mood_used_countries", features.get("global_mood_contributing_countries", 0)) or 0),
        "global_mood_excluded_countries": int(features.get("global_mood_excluded_countries", 0) or 0),
        "forecast_risk_score": float(features.get("forecast_risk_score", features.get("global_risk_score", 50)) or 50),
        "forecast_risk_delta": float(features.get("forecast_risk_delta", 0.0) or 0.0),
        "forecast_confidence": float(features.get("forecast_confidence", 0.35) or 0.35),
        "forecast_horizon_hours": int(features.get("forecast_horizon_hours", 24) or 24),
        "top_topics": top_topics,
    }
    if trigger:
        payload["trigger_country"] = trigger.get("country")
        payload["trigger_risk"] = trigger.get("risk")
        payload["trigger_timestamp"] = trigger.get("timestamp")
        payload["trigger_quality"] = trigger.get("data_quality")
    return payload



def _build_sentinel_stream_messages(trigger: dict | None = None) -> list[dict]:
    analysis = compute_sentinel_analysis()
    timestamp = datetime.utcnow().isoformat()
    message = {
        "type": "sentinel_update",
        "data": analysis,
        "timestamp": timestamp,
    }
    if trigger:
        message["trigger"] = {
            "country": trigger.get("country"),
            "risk": trigger.get("risk"),
            "timestamp": trigger.get("timestamp"),
            "data_quality": trigger.get("data_quality"),
        }

    messages = [message]
    risk_score = float(analysis.get("risk_score", 50) or 50)
    if risk_score >= 75:
        messages.append({
            "type": "alert",
            "alert": {
                "id": f"alert-{int(time.time())}",
                "threshold": 75,
                "condition": "above",
                "enabled": True,
                "triggered": True,
                "lastTriggered": timestamp,
                "risk_score": risk_score,
                "message": f"Critical risk level detected: {risk_score}",
            },
        })
    return messages



def _heartbeat_message(message_type: str) -> dict:
    return {
        "type": f"{message_type}_keepalive",
        "timestamp": datetime.utcnow().isoformat(),
    }


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

    await websocket.accept()
    consumer = None
    last_keepalive = time.monotonic()
    last_snapshot_emit = 0.0
    snapshot_interval_seconds = 3.0

    try:
        await websocket.send_json(_build_live_risk_snapshot())
        last_snapshot_emit = time.monotonic()
        while True:
            if consumer is None and _consumer_retry_allowed("risk"):
                try:
                    consumer = await asyncio.to_thread(_connect_live_consumer, LIVE_UPDATE_TOPIC, "dashboard-live-risk")
                except Exception as exc:
                    _mark_consumer_unavailable("risk")
                    logger.warning("live_risk_ws_consumer_unavailable", extra={"event": {"error": str(exc)}})

            if consumer is None:
                if time.monotonic() - last_snapshot_emit >= snapshot_interval_seconds:
                    await websocket.send_json(_build_live_risk_snapshot())
                    last_snapshot_emit = time.monotonic()
                    last_keepalive = time.monotonic()
                elif time.monotonic() - last_keepalive >= WS_IDLE_KEEPALIVE_SECONDS:
                    await websocket.send_json(_heartbeat_message("risk"))
                    last_keepalive = time.monotonic()
                await asyncio.sleep(0.5)
                continue

            try:
                messages = await asyncio.to_thread(_drain_consumer_messages, consumer)
            except Exception as exc:
                logger.warning("live_risk_ws_consumer_failed", extra={"event": {"error": str(exc)}})
                try:
                    await asyncio.to_thread(consumer.close)
                except Exception:
                    pass
                consumer = None
                await asyncio.sleep(1)
                continue

            if messages:
                await websocket.send_json(_build_live_risk_snapshot(messages[-1]))
                last_keepalive = time.monotonic()
                last_snapshot_emit = time.monotonic()
                continue

            # Even when there are no Kafka events, stream fresh DB snapshots so dashboard
            # top-line cards (mood/risk/forecast) continue updating in near real time.
            if time.monotonic() - last_snapshot_emit >= snapshot_interval_seconds:
                await websocket.send_json(_build_live_risk_snapshot())
                last_snapshot_emit = time.monotonic()
                last_keepalive = time.monotonic()

            if time.monotonic() - last_keepalive >= WS_IDLE_KEEPALIVE_SECONDS:
                await websocket.send_json(_heartbeat_message("risk"))
                last_keepalive = time.monotonic()

            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return
    finally:
        if consumer is not None:
            try:
                await asyncio.to_thread(consumer.close)
            except Exception:
                pass


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
    consumer = None
    try:
        try:
            consumer = await asyncio.to_thread(_connect_live_consumer, LIVE_UPDATE_TOPIC, "dashboard-country-risk")
        except Exception as exc:
            logger.warning(
                "country_risk_ws_consumer_unavailable",
                extra={"event": {"error": str(exc)}},
            )

        while True:
            if consumer is None:
                await asyncio.sleep(0.5)
                if not _consumer_retry_allowed("country_risk_map"):
                    continue
                try:
                    consumer = await asyncio.to_thread(_connect_live_consumer, LIVE_UPDATE_TOPIC, "dashboard-country-risk")
                except Exception as exc:
                    _mark_consumer_unavailable("country_risk_map")
                    logger.warning("country_risk_ws_consumer_unavailable", extra={"event": {"error": str(exc)}})
                    continue
                continue

            try:
                messages = await asyncio.to_thread(_drain_consumer_messages, consumer)
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

            quality_context = _country_intelligence_global_context(mode="online")
            for payload in messages:
                await websocket.send_json(_canonicalize_country_intelligence_row(payload, mode="online", global_quality=quality_context))
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
    WebSocket endpoint for Sentinel AI event-driven updates.
    Pushes analysis as soon as country risk events land instead of on a fixed timer.
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

    await websocket.accept()
    logger.info("Sentinel WebSocket client connected")
    consumer = None
    last_keepalive = time.monotonic()

    try:
        for outbound in _build_sentinel_stream_messages():
            await websocket.send_json(outbound)

        while True:
            if consumer is None:
                try:
                    consumer = await asyncio.to_thread(_connect_live_consumer, LIVE_UPDATE_TOPIC, "dashboard-sentinel")
                except Exception as exc:
                    logger.warning("sentinel_ws_consumer_unavailable", extra={"event": {"error": str(exc)}})
                    await asyncio.sleep(3)
                    continue

            try:
                messages = await asyncio.to_thread(_drain_consumer_messages, consumer)
            except Exception as exc:
                logger.warning("sentinel_ws_consumer_failed", extra={"event": {"error": str(exc)}})
                try:
                    await asyncio.to_thread(consumer.close)
                except Exception:
                    pass
                consumer = None
                await asyncio.sleep(1)
                continue

            if messages:
                trigger = messages[-1]
                try:
                    for outbound in _build_sentinel_stream_messages(trigger=trigger):
                        await websocket.send_json(outbound)
                    last_keepalive = time.monotonic()
                except Exception as exc:
                    logger.error(f"Error computing sentinel analysis: {exc}")
                    await websocket.send_json({
                        "type": "error",
                        "message": str(exc),
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                continue

            if time.monotonic() - last_keepalive >= WS_IDLE_KEEPALIVE_SECONDS:
                await websocket.send_json(_heartbeat_message("sentinel"))
                last_keepalive = time.monotonic()

            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        logger.info("Sentinel WebSocket client disconnected")
    except Exception as e:
        logger.error(f"Sentinel WebSocket error: {e}")
        await websocket.close()
    finally:
        if consumer is not None:
            try:
                await asyncio.to_thread(consumer.close)
            except Exception:
                pass



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
        results = _load_advanced_insights_results()
        generated_at = datetime.utcnow().isoformat()
        
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
        
        latest_doc = get_latest_global_doc("online")
        latest_features = (latest_doc or {}).get("features", {}) if isinstance(latest_doc, dict) else {}
        quality = _prediction_gate_action(mode="online")
        gate_action = str(quality.get("gate_action") or "allow")
        prediction_source_status = "fallback" if "fallback" in str(predictions_transformed.get("model_type", "")).lower() else ("calibrated_model" if predictions_transformed.get("predictions") else "model_unavailable")
        predictions_payload = {
            **predictions_transformed,
            "source": "advanced_analytics",
            "source_status": prediction_source_status,
            "calibration_status": "calibrated" if prediction_source_status == "calibrated_model" else "fallback",
            "fallback_reason": None if prediction_source_status == "calibrated_model" else "Advanced analytics returned fallback or partial prediction output.",
        }
        if gate_action == "suppress":
            predictions_payload.update({
                "predictions": [],
                "model_type": "withheld_by_quality_gate",
                "source_status": "withheld",
                "calibration_status": "withheld",
                "fallback_reason": "Predictions suppressed because reliability thresholds failed.",
            })
        elif gate_action == "downgrade":
            predictions_payload["predictions"] = [
                {
                    **row,
                    "confidence": round(min(float(row.get("confidence", 0.0) or 0.0), 0.35), 2),
                }
                for row in (predictions_payload.get("predictions") or [])
                if isinstance(row, dict)
            ]
            predictions_payload["source_status"] = "degraded_calibrated_model"
            predictions_payload["fallback_reason"] = "Predictions downgraded because reliability thresholds were not fully met."

        forecast_contract = _build_global_forecast_contract(
            mode="online",
            features=latest_features,
            predictions_payload=predictions_payload,
            quality=quality,
            generated_at=generated_at,
        )
        canonical_predictions = {
            **predictions_payload,
            "predictions": [
                {
                    "horizon": str(item.get("label") or f"{int(item.get('hours', 24))}h"),
                    "risk_score": float(item.get("risk_score", forecast_contract.get("risk_score", 50.0)) or 50.0),
                    "confidence": float(forecast_contract.get("confidence_ratio", 0.0) or 0.0),
                    "interval": forecast_contract.get("prediction_interval"),
                }
                for item in (forecast_contract.get("horizons") or [])
                if isinstance(item, dict)
            ],
            "source_status": forecast_contract.get("source_status"),
            "calibration_status": forecast_contract.get("calibration_status"),
            "model_type": forecast_contract.get("model_version") or predictions_payload.get("model_type"),
            "fallback_reason": forecast_contract.get("advisory") or predictions_payload.get("fallback_reason"),
        }
        return {
            "timestamp": generated_at,
            "generated_at": generated_at,
            "predictions": canonical_predictions,
            "forecast_contract": forecast_contract,
            "anomalies": anomalies_transformed,
            "causal_graph": causal_graph_transformed,
            "sentiment_momentum": sentiment_momentum_transformed,
            "ai_report": ai_report_transformed,
            "feature_snapshot": _build_prediction_feature_snapshot("online"),
            "governance": _build_governance_payload("online"),
            "ml_observability": results.get("ml_observability", {}),
            **quality,
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

        quality = _prediction_gate_action(mode="online")
        gate_action = str(quality.get("gate_action") or "allow")
        generated_at = datetime.utcnow().isoformat()
        predictions_payload = {
            "predictions": dynamic_preds,
            "model_type": "statistical_fallback",
            "source": "advanced_analytics",
            "source_status": "fallback",
            "calibration_status": "fallback",
            "fallback_reason": "Advanced analytics failed, so dynamic statistical fallback projections were used.",
        }
        if gate_action == "suppress":
            predictions_payload.update({
                "predictions": [],
                "model_type": "withheld_by_quality_gate",
                "source_status": "withheld",
                "calibration_status": "withheld",
                "fallback_reason": "Predictions suppressed because reliability thresholds failed.",
            })
        elif gate_action == "downgrade":
            predictions_payload["predictions"] = [
                {**row, "confidence": round(min(float(row.get("confidence", 0.0) or 0.0), 0.35), 2)}
                for row in predictions_payload.get("predictions", [])
                if isinstance(row, dict)
            ]
            predictions_payload["source_status"] = "degraded_fallback"
            predictions_payload["fallback_reason"] = "Fallback projections downgraded because reliability thresholds were not fully met."
        forecast_contract = _build_global_forecast_contract(
            mode="online",
            features=latest_features,
            predictions_payload=predictions_payload,
            quality=quality,
            generated_at=generated_at,
        )
        canonical_predictions = {
            **predictions_payload,
            "predictions": [
                {
                    "horizon": str(item.get("label") or f"{int(item.get('hours', 24))}h"),
                    "risk_score": float(item.get("risk_score", forecast_contract.get("risk_score", 50.0)) or 50.0),
                    "confidence": float(forecast_contract.get("confidence_ratio", 0.0) or 0.0),
                    "interval": forecast_contract.get("prediction_interval"),
                }
                for item in (forecast_contract.get("horizons") or [])
                if isinstance(item, dict)
            ],
            "source_status": forecast_contract.get("source_status"),
            "calibration_status": forecast_contract.get("calibration_status"),
            "model_type": forecast_contract.get("model_version") or predictions_payload.get("model_type"),
            "fallback_reason": forecast_contract.get("advisory") or predictions_payload.get("fallback_reason"),
        }
        return {
            "timestamp": generated_at,
            "generated_at": generated_at,
            "predictions": canonical_predictions,
            "forecast_contract": forecast_contract,
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
            },
            "feature_snapshot": _build_prediction_feature_snapshot("online"),
            "governance": _build_governance_payload("online"),
            "ml_observability": {},
            **quality,
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














SOURCE_LABELS = {
    "unhcr_idmc": "UNHCR displacement",
    "opensky": "OpenSky aviation",
    "opensky_auth": "OpenSky auth",
    "fred_behavior": "FRED food pressure",
    "fred_behavior_labor": "FRED labor proxy",
    "eia_behavior": "EIA fuel pressure",
    "frankfurter_behavior": "Frankfurter FX pressure",
    "worldbank_behavior_BX.TRF.PWKR.CD.DT": "World Bank remittance inflows",
    "worldbank_behavior_EG.IMP.CONS.ZS": "World Bank energy dependency",
    "fred_behavior_energy": "FRED energy proxy",
    "telegram_public": "Telegram public channels",
    "youtube_public": "YouTube public trends",
    "logistics": "Logistics stress",
    "worldbank_behavior_SL.UEM.TOTL.ZS": "World Bank unemployment",
    "worldbank_behavior_FP.CPI.TOTL.ZG": "World Bank inflation",
    "acled": "ACLED events",
    "reliefweb": "ReliefWeb",
    "weather": "Weather feed",
    "trends": "Trends feed",
    "economic_behavior": "Economic behavior",
}


def _source_label(source: str) -> str:
    key = str(source or "").strip()
    if key in SOURCE_LABELS:
        return SOURCE_LABELS[key]
    return key.replace("_", " ").replace(".", " ").title()


def _build_source_health_snapshot() -> dict:
    docs = [
        {**row, "source_label": _source_label(str(row.get("source") or ""))}
        for row in source_health_collection.find({}, {"_id": 0}).sort("updated_at", DESCENDING)
        if str(row.get("source") or "") != "worldbank_behavior"
    ]
    critical_down = 0
    critical_down_live = 0
    up_count = 0
    down_count = 0
    config_missing_count = 0
    for row in docs:
        status = str(row.get("status") or "unknown").lower()
        error_text = str(row.get("error") or "").lower()
        config_missing = error_text.startswith("missing ")
        if config_missing:
            config_missing_count += 1
        if status == "up":
            up_count += 1
        elif status == "down":
            down_count += 1
            if bool(row.get("critical")):
                critical_down += 1
                if not config_missing:
                    critical_down_live += 1
    return {
        "sources": docs,
        "up_count": up_count,
        "down_count": down_count,
        "critical_down": critical_down,
        "critical_down_live": critical_down_live,
        "config_missing_count": config_missing_count,
        "total": len(docs),
    }

def _build_quality_gate_snapshot(coverage: dict, freshness: dict, source_health: dict) -> dict:
    verified = int(coverage.get("verified", 0) or 0)
    total = int(coverage.get("total", 0) or 0)
    fresh = int(freshness.get("fresh_core_count", freshness.get("fresh_count", 0)) or 0)
    stale = int(freshness.get("stale_core_count", freshness.get("stale_count", 0)) or 0)
    known = max(fresh + stale, 1)
    freshness_ratio = float(fresh) / float(known)
    critical_down = int(source_health.get("critical_down_live", source_health.get("critical_down", 0)) or 0)
    return compute_quality_gate(
        verified_countries=verified,
        total_countries=total,
        freshness_ratio=freshness_ratio,
        critical_sources_down=critical_down,
    )


def _compute_country_coverage_snapshot(mode: str = "online") -> dict:
    pipeline = [
        {"$match": {"mode": mode}},
        {"$sort": {"timestamp": -1}},
        {"$group": {"_id": "$country", "doc": {"$first": "$$ROOT"}}},
    ]
    docs = list(country_features_collection.aggregate(pipeline))
    total = len(docs)
    verified = 0
    stale = 0
    no_data = 0
    for row in docs:
        features = (row.get("doc") or {}).get("features") or {}
        quality = assess_country_risk_quality(
            features.get("top_topics"),
            features.get("timestamp"),
            source_count=features.get("source_count"),
            external_signal_freshness=features.get("external_signal_freshness"),
            external_sources=features.get("external_sources"),
            evidence_quality_score=features.get("evidence_quality_score"),
            war_state_rules=features.get("war_state_rules"),
            public_attention_score=features.get("public_attention_score"),
            narrative_velocity_score=features.get("narrative_velocity_score"),
            coordination_risk_score=features.get("coordination_risk_score"),
            mobility_disruption_score=features.get("mobility_disruption_score"),
            logistics_stress_score=features.get("logistics_stress_score"),
            household_stress_score=features.get("household_stress_score"),
            fuel_price_pressure=features.get("fuel_price_pressure"),
            food_price_pressure=features.get("food_price_pressure"),
            labor_stress_score=features.get("labor_stress_score"),
            fx_pressure_score=features.get("fx_pressure_score"),
            remittance_stress_score=features.get("remittance_stress_score"),
            energy_stress_score=features.get("energy_stress_score"),
            weather_stress=features.get("weather_stress"),
        )
        if quality.get("validated_today"):
            verified += 1
        elif quality.get("data_quality") == "stale":
            stale += 1
        elif quality.get("data_quality") == "synthetic":
            no_data += 1
    return {
        "total": total,
        "verified": verified,
        "stale": stale,
        "no_data": no_data,
        "coverage_pct": round((verified / total) * 100, 2) if total else 0.0,
    }

@app.get("/observability/source-health")
@limiter.limit("30/minute")
def observability_source_health(request: Request, role: str = Depends(require_admin)):
    return _build_source_health_snapshot()

@app.get("/observability/world-state")
@limiter.limit("20/minute")
def observability_world_state(request: Request, role: str = Depends(require_admin), mode: str = Query("online")):
    source_health = _build_source_health_snapshot()
    coverage = _compute_country_coverage_snapshot(mode=mode)

    recent = list(global_features_collection.find({"mode": mode}, {"features": 1, "timestamp": 1}).sort("_id", DESCENDING).limit(8))
    drift = {
        "global_risk_delta": 0.0,
        "global_mood_delta": 0.0,
        "window": len(recent),
    }
    if len(recent) >= 2:
        latest = (recent[0].get("features") or {})
        older = (recent[-1].get("features") or {})
        drift["global_risk_delta"] = round(float(latest.get("global_risk_score", 0.0) or 0.0) - float(older.get("global_risk_score", 0.0) or 0.0), 4)
        drift["global_mood_delta"] = round(float(latest.get("global_mood_score", 0.0) or 0.0) - float(older.get("global_mood_score", 0.0) or 0.0), 4)

    region_coverage = {
        "north_america": 0,
        "south_america": 0,
        "europe": 0,
        "middle_east_north_africa": 0,
        "sub_saharan_africa": 0,
        "south_asia": 0,
        "east_asia": 0,
        "southeast_asia": 0,
        "central_asia": 0,
        "oceania": 0,
        "other": 0,
    }
    for row in country_features_collection.aggregate([
        {"$match": {"mode": mode}},
        {"$sort": {"timestamp": -1}},
        {"$group": {"_id": "$country", "doc": {"$first": "$$ROOT"}}},
    ]):
        country_code = str(row.get("_id") or "").upper().strip()
        region = "other"
        region_coverage[region if region in region_coverage else "other"] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_health": source_health,
        "coverage": coverage,
        "feature_drift": drift,
        "region_coverage": region_coverage,
    }


