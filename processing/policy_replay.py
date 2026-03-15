from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from database.mongo import db

INTERVENTION_EFFECTS: Dict[str, float] = {
    "communications": 0.96,
    "market_stabilization": 0.97,
    "climate_prepositioning": 0.95,
    "public_health_response": 0.95,
    "diplomatic_deescalation": 0.96,
}


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def run_policy_replay(
    country: Optional[str] = None,
    interventions: Optional[List[str]] = None,
    horizon_days: int = 30,
    mode: str = "online",
) -> Dict[str, Any]:
    interventions = interventions or []
    collection = db.country_features if country else db.global_features
    query: Dict[str, Any] = {"mode": mode}
    if country:
        query["country"] = country

    limit = max(12, min(180, horizon_days * 2))
    docs = list(collection.find(query).sort("timestamp", -1).limit(limit))
    docs = list(reversed(docs))

    baseline_series = []
    simulated_series = []

    effect_multiplier = 1.0
    for intervention in interventions:
        effect_multiplier *= INTERVENTION_EFFECTS.get(str(intervention).strip().lower(), 0.985)

    for idx, doc in enumerate(docs):
        ts = str(doc.get("timestamp") or datetime.utcnow().isoformat())
        risk = _safe_float(doc.get("features", {}).get("global_risk_score", 50.0), 50.0)

        baseline_series.append({"timestamp": ts, "risk": round(risk, 2)})

        # Policy impact increases gradually over replay horizon.
        phase = (idx + 1) / max(1, len(docs))
        attenuation = 1.0 - ((1.0 - effect_multiplier) * phase)
        simulated_risk = max(0.0, min(100.0, risk * attenuation))
        simulated_series.append({"timestamp": ts, "risk": round(simulated_risk, 2)})

    if baseline_series:
        baseline_end = baseline_series[-1]["risk"]
        simulated_end = simulated_series[-1]["risk"]
    else:
        baseline_end = 50.0
        simulated_end = 50.0

    return {
        "country": country,
        "scope": "country" if country else "global",
        "mode": mode,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "interventions": interventions,
        "baseline_series": baseline_series,
        "simulated_series": simulated_series,
        "baseline_final_risk": round(baseline_end, 2),
        "simulated_final_risk": round(simulated_end, 2),
        "projected_delta": round(simulated_end - baseline_end, 2),
    }
