import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id

        event = getattr(record, "event", None)
        if isinstance(event, dict):
            payload["event"] = event

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def build_logger(name: str = "world_pulse") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JsonFormatter())
    logger.addHandler(stream_handler)

    log_file = os.getenv("STRUCTURED_LOG_FILE", "").strip()
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)

    return logger


class RuntimeMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = datetime.now(timezone.utc)
        self.total_requests = 0
        self.total_errors = 0
        self.total_predictions = 0
        self.last_prediction_at = None

    def on_request(self, status_code: int) -> None:
        with self._lock:
            self.total_requests += 1
            if status_code >= 400:
                self.total_errors += 1

    def on_prediction(self) -> None:
        with self._lock:
            self.total_predictions += 1
            self.last_prediction_at = datetime.now(timezone.utc)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "started_at": self.started_at.isoformat(),
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "total_predictions": self.total_predictions,
                "last_prediction_at": self.last_prediction_at.isoformat() if self.last_prediction_at else None,
            }


def record_prediction(
    prediction_collection,
    model_monitoring_collection,
    model_version: str,
    features: list[float],
    prediction: int,
    probability: float,
    drift_score: float | None,
    role: str,
    logger: logging.Logger,
) -> None:
    timestamp = datetime.utcnow()
    prediction_doc = {
        "timestamp": timestamp,
        "model_version": model_version,
        "features": features,
        "prediction": int(prediction),
        "probability": float(probability),
    }
    prediction_collection.insert_one(prediction_doc)

    monitoring_doc = {
        "timestamp": timestamp,
        "model_version": model_version,
        "prediction": int(prediction),
        "probability": float(probability),
        "drift_score": drift_score,
        "role": role,
    }
    model_monitoring_collection.insert_one(monitoring_doc)

    logger.info(
        "prediction_recorded",
        extra={
            "event": {
                "model_version": model_version,
                "prediction": int(prediction),
                "probability": float(probability),
                "drift_score": drift_score,
                "role": role,
            }
        },
    )


def build_monitoring_summary(model_monitoring_collection, window: int = 200) -> dict[str, Any]:
    rows = list(model_monitoring_collection.find().sort("timestamp", -1).limit(max(1, window)))
    if not rows:
        return {
            "window": window,
            "samples": 0,
            "avg_probability": None,
            "avg_drift_score": None,
            "drift_alert": False,
        }

    probs = [float(r.get("probability", 0.0)) for r in rows]
    drifts = [float(r.get("drift_score")) for r in rows if r.get("drift_score") is not None]

    avg_probability = sum(probs) / len(probs)
    avg_drift = (sum(drifts) / len(drifts)) if drifts else None

    return {
        "window": window,
        "samples": len(rows),
        "avg_probability": round(avg_probability, 6),
        "avg_drift_score": round(avg_drift, 6) if avg_drift is not None else None,
        "drift_alert": bool(avg_drift is not None and avg_drift >= 0.35),
        "latest_timestamp": rows[0].get("timestamp").isoformat() if rows and rows[0].get("timestamp") else None,
    }


def health_check(model=None, feature_columns=None, db_client=None) -> dict[str, bool]:
    """
    Backward-compatible health check used by orchestrator.py.
    """
    status = {"mongo": False, "model_loaded": False}

    try:
        if db_client is not None:
            db_client.list_collection_names()
            status["mongo"] = True
    except Exception:
        status["mongo"] = False

    if model is not None and feature_columns:
        try:
            test_input = [0.0] * len(feature_columns)
            if isinstance(model, dict):
                predictors = [m for m in model.values() if hasattr(m, "predict_proba")]
                if predictors:
                    predictors[0].predict_proba([test_input])
                    status["model_loaded"] = True
            elif hasattr(model, "predict_proba"):
                model.predict_proba([test_input])
                status["model_loaded"] = True
        except Exception:
            status["model_loaded"] = False

    return status
