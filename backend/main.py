import sys
import os
import logging
from datetime import datetime
import asyncio
import time
import uuid
import hmac
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

# Create indexes for scalable queries (run once)
prediction_collection.create_index([("timestamp", DESCENDING)])
prediction_collection.create_index([("model_version", ASCENDING)])
model_monitoring_collection.create_index([("timestamp", DESCENDING)])
model_monitoring_collection.create_index([("model_version", ASCENDING)])

# =====================================================
# Model Cache
# =====================================================
model_cache = {"model": None, "version": None}

# =====================================================
# TEMP USER DATABASE (Testing Only)
# Replace later with MongoDB users collection
# =====================================================

fake_users_db = {}

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


# =====================================================
# Request Schema
# =====================================================
class PredictionRequest(BaseModel):
    features: list[float]

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
@limiter.limit("10/minute")
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
def get_prediction_logs(request: Request, limit: int = Query(50, ge=1), role: str = Depends(require_admin)):
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
    # Check if user already exists
    if data.email in fake_users_db:
        raise HTTPException(status_code=400, detail="User already exists")

    # Validate role
    valid_roles = ["admin", "researcher", "policy", "student"]
    if data.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

    # Create new user
    fake_users_db[data.email] = {
        "password": pwd_context.hash(data.password),
        "role": data.role,
        "name": data.name,
        "organization": data.organization
    }

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
    # Check if user exists
    user = fake_users_db.get(data.email)
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
    user = fake_users_db.get(email)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    # Update password
    user["password"] = pwd_context.hash(data.new_password)

    # Remove used token
    del password_reset_tokens[data.token]

    return {"message": "Password has been reset successfully"}


@app.post("/auth/login")
def login(data: LoginRequest):

    user = fake_users_db.get(data.email)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not pwd_context.verify(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({
        "sub": data.email,
        "role": user["role"]
    })

    return {
        "access_token": access_token,
        "role": user["role"]
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
    global fake_users_db

    fake_users_db = {
        "admin@wp.com": {
            "password": pwd_context.hash("admin123"),
            "role": "admin"
        },
        "researcher@wp.com": {
            "password": pwd_context.hash("research123"),
            "role": "researcher"
        },
        "policy@wp.com": {
            "password": pwd_context.hash("policy123"),
            "role": "policy"
        },
        "student@wp.com": {
            "password": pwd_context.hash("student123"),
            "role": "student"
        }
    }
