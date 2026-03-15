from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database.mongo import db

FEATURE_WEIGHTS: Dict[str, float] = {
    "news_sentiment": 0.40,
    "gdelt_sentiment": 0.38,
    "crypto_return": 0.22,
    "crypto_volatility": 0.30,
    "stock_return": 0.22,
    "stock_volatility": 0.30,
    "weather_anomaly": 0.26,
}

FEATURE_LABELS: Dict[str, str] = {
    "news_sentiment": "News Sentiment",
    "gdelt_sentiment": "Global Media Sentiment",
    "crypto_return": "Crypto Return",
    "crypto_volatility": "Crypto Volatility",
    "stock_return": "Stock Return",
    "stock_volatility": "Stock Volatility",
    "weather_anomaly": "Weather Anomaly",
}


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _threat_level(score: float) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "elevated"
    if score >= 25:
        return "guarded"
    return "stable"


def _collect_series(country: Optional[str], mode: str, limit: int = 24) -> List[dict]:
    query: Dict[str, Any] = {"mode": mode}
    collection = db.global_features
    if country:
        query["country"] = country
        collection = db.country_features
    docs = list(collection.find(query).sort("timestamp", -1).limit(limit))
    return list(reversed(docs))


def _latest_doc(country: Optional[str], mode: str) -> Optional[dict]:
    query: Dict[str, Any] = {"mode": mode}
    collection = db.global_features
    if country:
        query["country"] = country
        collection = db.country_features
    return collection.find_one(query, sort=[("timestamp", -1)])


def build_causal_explanation(country: Optional[str] = None, mode: str = "online") -> Dict[str, Any]:
    latest_doc = _latest_doc(country=country, mode=mode)
    if not latest_doc:
        return {
            "scope": "country" if country else "global",
            "country": country,
            "mode": mode,
            "risk_score": 50.0,
            "threat_level": "guarded",
            "drivers": [],
            "root_cause_graph": {"nodes": [], "edges": []},
            "evidence": [],
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data_freshness_minutes": None,
            "summary": "No feature data available yet for causal explanation.",
        }

    features = latest_doc.get("features", {}) or {}
    risk_score = _safe_float(features.get("global_risk_score", 50.0), 50.0)

    series = _collect_series(country=country, mode=mode, limit=24)
    prior_risk = risk_score
    if len(series) >= 2:
        prior_risk = _safe_float(series[-2].get("features", {}).get("global_risk_score", risk_score), risk_score)
    risk_delta = round(risk_score - prior_risk, 2)

    drivers: List[Dict[str, Any]] = []
    for feature, weight in FEATURE_WEIGHTS.items():
        value = _safe_float(features.get(feature, 0.0), 0.0)
        impact = round(abs(value) * weight, 4)
        direction = "upward" if value >= 0 else "downward"
        drivers.append(
            {
                "feature": feature,
                "label": FEATURE_LABELS.get(feature, feature.replace("_", " ").title()),
                "value": round(value, 4),
                "weight": weight,
                "impact": impact,
                "direction": direction,
            }
        )

    drivers.sort(key=lambda item: item["impact"], reverse=True)
    top_drivers = drivers[:5]

    nodes = [{"id": "risk", "label": "Global Risk", "value": round(risk_score, 2), "type": "target"}]
    edges = []
    for driver in top_drivers:
        node_id = driver["feature"]
        nodes.append({"id": node_id, "label": driver["label"], "value": driver["impact"], "type": "driver"})
        edges.append(
            {
                "source": node_id,
                "target": "risk",
                "weight": round(driver["impact"], 4),
                "polarity": "positive" if driver["direction"] == "upward" else "negative",
            }
        )

    latest_ts = _parse_timestamp(latest_doc.get("timestamp") or latest_doc.get("collected_at"))
    freshness_minutes = None
    if latest_ts.year > 1970:
        freshness_minutes = int((datetime.now(timezone.utc) - latest_ts).total_seconds() / 60)

    evidence = [
        {
            "title": "Risk delta",
            "detail": f"Risk changed by {risk_delta:+.2f} points since previous interval.",
            "confidence": 0.72,
        },
        {
            "title": "Dominant drivers",
            "detail": ", ".join([d["label"] for d in top_drivers[:3]]) or "No dominant drivers",
            "confidence": 0.68,
        },
    ]

    return {
        "scope": "country" if country else "global",
        "country": country,
        "mode": mode,
        "risk_score": round(risk_score, 2),
        "risk_delta": risk_delta,
        "threat_level": _threat_level(risk_score),
        "drivers": top_drivers,
        "root_cause_graph": {"nodes": nodes, "edges": edges},
        "evidence": evidence,
        "timestamp": latest_doc.get("timestamp") or latest_doc.get("collected_at") or datetime.utcnow().isoformat(),
        "data_freshness_minutes": freshness_minutes,
        "summary": (
            f"{('Country ' + country) if country else 'Global'} risk is {_threat_level(risk_score)} at {risk_score:.1f}. "
            f"Primary pressure comes from {', '.join([d['label'] for d in top_drivers[:3]]) or 'limited signals'}."
        ),
    }
