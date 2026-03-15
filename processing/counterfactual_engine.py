from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Optional

from processing.causal_risk_navigator import build_causal_explanation, FEATURE_WEIGHTS


def _apply_shock(base_value: float, shock: float) -> float:
    # For compact payloads, treat -1..1 as relative shock and anything else as absolute delta.
    if -1.0 <= shock <= 1.0:
        return base_value * (1.0 + shock)
    return base_value + shock


def run_counterfactual(
    scenario: Dict[str, float],
    country: Optional[str] = None,
    mode: str = "online",
) -> Dict[str, Any]:
    explanation = build_causal_explanation(country=country, mode=mode)
    base_risk = float(explanation.get("risk_score", 50.0))
    base_driver_map = {d["feature"]: d for d in explanation.get("drivers", [])}

    feature_impacts = []
    cumulative_delta = 0.0

    for feature, shock in scenario.items():
        try:
            shock_value = float(shock)
        except (TypeError, ValueError):
            continue

        current_value = float(base_driver_map.get(feature, {}).get("value", 0.0))
        adjusted_value = _apply_shock(current_value, shock_value)
        delta_value = adjusted_value - current_value
        weight = float(FEATURE_WEIGHTS.get(feature, 0.18))

        # Risk sensitivity scaling: deterministic and bounded.
        risk_delta = delta_value * weight * 18.0
        cumulative_delta += risk_delta

        feature_impacts.append(
            {
                "feature": feature,
                "before": round(current_value, 4),
                "after": round(adjusted_value, 4),
                "shock": round(shock_value, 4),
                "estimated_risk_delta": round(risk_delta, 3),
            }
        )

    projected_risk = max(0.0, min(100.0, base_risk + cumulative_delta))

    if cumulative_delta > 1.5:
        trajectory = "worsening"
    elif cumulative_delta < -1.5:
        trajectory = "improving"
    else:
        trajectory = "stable"

    confidence = max(0.45, min(0.9, 0.72 - (0.03 * max(0, len(feature_impacts) - 3))))

    return {
        "country": country,
        "scope": "country" if country else "global",
        "mode": mode,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "base_risk_score": round(base_risk, 2),
        "projected_risk_score": round(projected_risk, 2),
        "projected_risk_delta": round(projected_risk - base_risk, 2),
        "trajectory": trajectory,
        "confidence": round(confidence, 2),
        "feature_impacts": feature_impacts,
    }
