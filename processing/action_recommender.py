from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from processing.causal_risk_navigator import build_causal_explanation

ACTION_LIBRARY: Dict[str, Dict[str, Any]] = {
    "news_sentiment": {
        "title": "Strategic Communications Surge",
        "action": "Launch verified public briefings and rumor-control updates every 6 hours.",
        "eta_hours": 12,
        "expected_risk_reduction": 2.4,
    },
    "gdelt_sentiment": {
        "title": "Diplomatic Signaling",
        "action": "Coordinate proactive diplomatic messaging and multilateral updates.",
        "eta_hours": 24,
        "expected_risk_reduction": 1.9,
    },
    "crypto_volatility": {
        "title": "Liquidity Monitoring",
        "action": "Activate market-liquidity watchlist and trigger volatility circuit response.",
        "eta_hours": 8,
        "expected_risk_reduction": 1.5,
    },
    "stock_volatility": {
        "title": "Equity Stress Protocol",
        "action": "Enable stress protocol with liquidity support and institutional advisories.",
        "eta_hours": 8,
        "expected_risk_reduction": 1.7,
    },
    "weather_anomaly": {
        "title": "Climate Risk Readiness",
        "action": "Preposition emergency resources near anomaly zones and trigger early ops briefing.",
        "eta_hours": 6,
        "expected_risk_reduction": 2.1,
    },
}


def build_action_plan(country: Optional[str] = None, mode: str = "online", max_actions: int = 4) -> Dict[str, Any]:
    explanation = build_causal_explanation(country=country, mode=mode)
    drivers = explanation.get("drivers", [])

    recommendations: List[Dict[str, Any]] = []
    for driver in drivers:
        feature = str(driver.get("feature", ""))
        template = ACTION_LIBRARY.get(feature)
        if not template:
            continue

        impact = float(driver.get("impact", 0.0))
        confidence = max(0.48, min(0.9, 0.55 + (impact * 0.15)))

        recommendations.append(
            {
                "feature": feature,
                "title": template["title"],
                "action": template["action"],
                "priority": "high" if impact >= 0.18 else "medium",
                "eta_hours": template["eta_hours"],
                "expected_risk_reduction": round(template["expected_risk_reduction"] * (1 + min(0.45, impact)), 2),
                "confidence": round(confidence, 2),
            }
        )

    if not recommendations:
        recommendations = [
            {
                "feature": "system",
                "title": "Data Integrity Sweep",
                "action": "Run quality audit on incoming feeds and validate signal freshness.",
                "priority": "medium",
                "eta_hours": 4,
                "expected_risk_reduction": 0.8,
                "confidence": 0.52,
            }
        ]

    recommendations = recommendations[:max_actions]
    projected_total_reduction = round(sum(r["expected_risk_reduction"] for r in recommendations), 2)

    return {
        "country": country,
        "scope": "country" if country else "global",
        "mode": mode,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "risk_score": explanation.get("risk_score", 50.0),
        "threat_level": explanation.get("threat_level", "guarded"),
        "recommendations": recommendations,
        "projected_total_risk_reduction": projected_total_reduction,
    }
