# backend/observability.py

import os
import logging
from datetime import datetime
from pymongo import MongoClient
from pythonjsonlogger import jsonlogger
from sklearn.metrics import accuracy_score

# ==========================================
# MongoDB Connection
# ==========================================
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["world_pulse"]

prediction_collection = db["prediction_logs"]
performance_collection = db["model_performance"]

# ==========================================
# Structured Logging Setup
# ==========================================
logger = logging.getLogger("world_pulse")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

def log_info(message, **kwargs):
    logger.info(message, extra=kwargs)

def log_error(message, **kwargs):
    logger.error(message, extra=kwargs)

# ==========================================
# Prediction Logging
# ==========================================
def log_prediction(model_version, features, prediction, probability):
    """
    Log a single prediction to Mongo and structured logs.
    """
    document = {
        "timestamp": datetime.utcnow(),
        "model_version": model_version,
        "features": features,
        "prediction": prediction,
        "probability": probability
    }

    # Mongo
    prediction_collection.insert_one(document)
    # Structured log
    log_info("Prediction logged", **document)

# ==========================================
# Model Performance Logging
# ==========================================
def log_model_performance(model_version, y_true, y_pred):
    """
    Log model performance metrics to Mongo and structured logs.
    """
    accuracy = accuracy_score(y_true, y_pred)
    document = {
        "timestamp": datetime.utcnow(),
        "model_version": model_version,
        "accuracy": accuracy,
        "n_samples": len(y_true)
    }

    performance_collection.insert_one(document)
    log_info("Model performance logged", **document)

# ==========================================
# Health Check
# ==========================================
# ==============================
# Observability / Health Check
# ==============================
# observability_local.py

def health_check(model=None, feature_columns=None, db_client=None):
    """
    Local-safe health check:
    - Works with unauthenticated Mongo
    - Works even if FEATURE_COLUMNS are only in orchestrator
    """
    status = {"mongo": False, "model_loaded": False}

    # ---- Mongo check ----
    try:
        if db_client is not None:
            # lightweight check: just list collections
            _ = db_client.list_collection_names()
            status["mongo"] = True
        else:
            status["mongo"] = False
    except Exception as e:
        print(f"Mongo health check failed: {e}")

    # ---- ML Model check ----
    if model is not None and feature_columns is not None:
        try:
            test_input = [0.0] * len(feature_columns)
            model.predict_proba([test_input])
            status["model_loaded"] = True
        except Exception as e:
            print(f"Model health check failed: {e}")

    return status
