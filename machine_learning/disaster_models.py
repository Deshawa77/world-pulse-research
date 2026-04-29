from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

try:
    from sklearn.linear_model import LogisticRegression
    SKLEARN_AVAILABLE = True
except Exception:
    LogisticRegression = None
    SKLEARN_AVAILABLE = False


ROOT = Path(__file__).resolve().parents[1]
DISASTER_MODEL_DIR = ROOT / "models" / "disaster"

HAZARD_FEATURES: dict[str, list[str]] = {
    "flood": [
        "severe_weather_keyword_score",
        "wind_score",
        "cold_wet_score",
        "flood_signal_density",
        "source_coverage",
        "recency_score",
    ],
    "wildfire": [
        "heat_score",
        "wind_score",
        "smoke_keyword_score",
        "wildfire_signal_density",
        "dryness_proxy_score",
        "recency_score",
    ],
    "cyclone": [
        "storm_keyword_score",
        "wind_score",
        "storm_signal_density",
        "ocean_proxy_score",
        "pressure_proxy_score",
        "recency_score",
    ],
    "earthquake": [
        "recent_quake_density",
        "average_magnitude_score",
        "major_quake_ratio",
        "aftershock_cluster_score",
        "max_magnitude_score",
        "short_term_acceleration_score",
        "strong_event_density",
        "energy_proxy_score",
        "source_coverage",
        "recency_score",
    ],
}

DEFAULT_LEAD_HOURS = {
    "flood": 24,
    "wildfire": 18,
    "cyclone": 48,
    "earthquake": 12,
}

DEFAULT_ACTIONS = {
    "flood": "Increase basin watch coverage and verify urban flood response readiness.",
    "wildfire": "Prioritize wildfire patrols, dry-fuel monitoring, and response staging.",
    "cyclone": "Treat this as a conservative cyclone outlook and verify coastal preparedness.",
    "earthquake": "Treat this as anomaly monitoring rather than deterministic prediction and verify preparedness channels.",
}

DEFAULT_SOURCE_FAMILIES = {
    "flood": ["weather_sensors", "ocean_sensors"],
    "wildfire": ["weather_sensors", "satellite_imagery"],
    "cyclone": ["weather_sensors", "ocean_sensors", "satellite_imagery"],
    "earthquake": ["seismic_data"],
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _model_path(hazard: str) -> Path:
    return DISASTER_MODEL_DIR / f"{hazard}_model.joblib"


@lru_cache(maxsize=1)
def _loaded_models() -> dict[str, Any]:
    models: dict[str, Any] = {}
    for hazard, feature_names in HAZARD_FEATURES.items():
        path = _model_path(hazard)
        if path.exists():
            try:
                models[hazard] = joblib.load(path)
                continue
            except Exception:
                pass
        models[hazard] = _runtime_bundle(hazard, len(feature_names))
    return models


def _runtime_bundle(hazard: str, width: int) -> dict[str, Any]:
    rng = np.random.default_rng(abs(hash(hazard)) % (2**32))
    sample_count = 320
    x = rng.uniform(0.0, 1.0, size=(sample_count, width))

    if hazard == "flood":
        risk = 0.30 * x[:, 0] + 0.15 * x[:, 1] + 0.12 * x[:, 2] + 0.26 * x[:, 3] + 0.07 * x[:, 4] + 0.10 * x[:, 5]
    elif hazard == "wildfire":
        risk = 0.28 * x[:, 0] + 0.15 * x[:, 1] + 0.14 * x[:, 2] + 0.24 * x[:, 3] + 0.10 * x[:, 4] + 0.09 * x[:, 5]
    elif hazard == "cyclone":
        risk = 0.25 * x[:, 0] + 0.22 * x[:, 1] + 0.18 * x[:, 2] + 0.15 * x[:, 3] + 0.10 * x[:, 4] + 0.10 * x[:, 5]
    else:
        risk = 0.24 * x[:, 0] + 0.22 * x[:, 1] + 0.18 * x[:, 2] + 0.16 * x[:, 3] + 0.10 * x[:, 4] + 0.10 * x[:, 5]

    risk = np.clip(risk + rng.normal(0.0, 0.045, size=sample_count), 0.0, 1.0)
    y = (risk >= 0.52).astype(int)

    bundle: dict[str, Any] = {
        "hazard": hazard,
        "feature_names": HAZARD_FEATURES[hazard],
        "trained_at": None,
        "metrics": {"source": "runtime_bootstrap"},
        "model_type": "weighted_feature_fallback",
        "model": None,
        "persisted": False,
        "threshold": 0.54 if hazard in {"cyclone", "earthquake"} else 0.5,
        "post_scale": 0.84 if hazard == "earthquake" else 0.9 if hazard == "cyclone" else 1.0,
        "severity_cap": 0.72 if hazard == "earthquake" else 0.8 if hazard == "cyclone" else 0.96,
        "confidence_cap": 0.68 if hazard == "earthquake" else 0.74 if hazard == "cyclone" else 0.92,
        "calibration_method": None,
    }
    if SKLEARN_AVAILABLE and LogisticRegression is not None and len(np.unique(y)) > 1:
        model = LogisticRegression(max_iter=300)
        model.fit(x, y)
        bundle["model"] = model
        bundle["model_type"] = "logistic_regression"
    return bundle


def _fallback_score(feature_vector: list[float]) -> float:
    weights = np.linspace(1.0, 0.7, num=len(feature_vector))
    numerator = float(sum(value * weight for value, weight in zip(feature_vector, weights)))
    denominator = float(sum(weights)) if len(weights) else 1.0
    return _clamp(numerator / denominator)


def _normalize_sources(hazard: str, feature_bundle: dict[str, Any]) -> list[str]:
    values = [str(source).strip() for source in (feature_bundle.get("signal_sources") or []) if str(source).strip()]
    return sorted(set(values or DEFAULT_SOURCE_FAMILIES.get(hazard, ["weather_sensors"])))


def _normalize_explainers(feature_bundle: dict[str, Any]) -> list[str]:
    values = [str(item).strip() for item in (feature_bundle.get("top_contributing_signals") or []) if str(item).strip()]
    return values[:6] if values else ["model feature fusion"]


def _normalize_lead_time(hazard: str, feature_bundle: dict[str, Any]) -> int:
    raw = feature_bundle.get("lead_time_hours")
    try:
        lead_time = int(raw)
        return max(lead_time, 1)
    except Exception:
        return DEFAULT_LEAD_HOURS.get(hazard, 24)


def predict_hazard_forecast(feature_bundle: dict[str, Any]) -> dict[str, Any]:
    hazard = str(feature_bundle.get("event_type") or "").lower()
    feature_names = HAZARD_FEATURES.get(hazard, [])
    feature_values = feature_bundle.get("feature_values") or {}
    vector = [float(feature_values.get(name) or 0.0) for name in feature_names]

    bundle = _loaded_models().get(hazard) or _runtime_bundle(hazard, len(feature_names))
    model = bundle.get("model")
    used_fallback = model is None
    if model is not None:
        feature_frame = pd.DataFrame([{name: float(feature_values.get(name) or 0.0) for name in feature_names}], columns=feature_names)
        likelihood = float(model.predict_proba(feature_frame)[0][1])
    else:
        likelihood = _fallback_score(vector)

    post_scale = float(bundle.get("post_scale") or 1.0)
    threshold = float(bundle.get("threshold") or 0.5)
    likelihood = _clamp(likelihood * post_scale)

    source_coverage = float(feature_values.get("source_coverage") or 0.0)
    recency_score = float(feature_values.get("recency_score") or 0.0)
    threshold_support = _clamp((likelihood - threshold + 0.22) / 0.72)
    severity_score = _clamp((likelihood * 0.64) + (threshold_support * 0.1) + (source_coverage * 0.1) + (recency_score * 0.16))
    confidence = _clamp(0.38 + (source_coverage * 0.34) + (recency_score * 0.18) + (0.08 if not used_fallback else 0.0))

    severity_score = min(severity_score, float(bundle.get("severity_cap") or 1.0))
    confidence = min(confidence, float(bundle.get("confidence_cap") or 1.0))

    trained_at = bundle.get("trained_at")
    model_version = f"disaster-{hazard}-persisted-v1" if trained_at else f"disaster-{hazard}-runtime-v1"
    model_status = "persisted_trained_model" if trained_at else ("trained_runtime_model" if model is not None else "fallback_only")

    signal_sources = _normalize_sources(hazard, feature_bundle)
    explainers = _normalize_explainers(feature_bundle)
    lead_time_hours = _normalize_lead_time(hazard, feature_bundle)
    recommended_action = str(feature_bundle.get("recommended_action") or DEFAULT_ACTIONS.get(hazard) or "Review this alert.")
    updated_at = str(feature_bundle.get("updated_at") or datetime.now(timezone.utc).isoformat())

    return {
        **feature_bundle,
        "signal_sources": signal_sources,
        "top_contributing_signals": explainers,
        "lead_time_hours": lead_time_hours,
        "recommended_action": recommended_action,
        "updated_at": updated_at,
        "likelihood": round(_clamp(likelihood), 3),
        "severity_score": round(_clamp(severity_score), 3),
        "confidence": round(_clamp(confidence), 3),
        "alert_threshold": round(threshold, 3),
        "threshold_support": round(threshold_support, 3),
        "calibration_method": bundle.get("calibration_method"),
        "model_type": str(bundle.get("model_type") or ("logistic_regression" if not used_fallback else "weighted_feature_fallback")),
        "model_status": model_status,
        "model_version": model_version,
        "model_trained_at": trained_at,
        "model_metrics": bundle.get("metrics") or {},
    }
