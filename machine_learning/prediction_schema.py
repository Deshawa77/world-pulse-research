from __future__ import annotations

from typing import Iterable

LEGACY_GLOBAL_PREDICTION_FEATURES = [
    "news_sentiment",
    "gdelt_sentiment",
    "crypto_return",
    "crypto_volatility",
    "stock_return",
    "stock_volatility",
    "weather_anomaly",
]

EXPANDED_GLOBAL_PREDICTION_FEATURES = [
    "news_sentiment",
    "gdelt_sentiment",
    "crypto_return",
    "crypto_volatility",
    "stock_return",
    "stock_volatility",
    "weather_anomaly",
    "global_behavior_index",
    "global_context_index",
    "global_attention_index",
    "global_disruption_index",
    "global_economic_stress_index",
    "global_mood_score",
    "forecast_risk_score",
    "forecast_risk_delta",
    "forecast_confidence",
    "top_topic_pressure",
]

DEFAULT_PREDICTION_FEATURES = EXPANDED_GLOBAL_PREDICTION_FEATURES
PREDICTION_SCHEMA_VERSION = "expanded_global_v1"


def safe_float(value: object, fallback: float = 0.0) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
        if number != number:
            return fallback
        return number
    except Exception:
        return fallback


def extract_feature_vector(feature_doc: dict | None, feature_names: Iterable[str] | None = None) -> list[float]:
    source = feature_doc or {}
    names = list(feature_names or DEFAULT_PREDICTION_FEATURES)
    return [safe_float(source.get(name), 0.0) for name in names]
