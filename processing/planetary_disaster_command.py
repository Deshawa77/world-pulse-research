from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if numeric == numeric else default


def _ratio(value: Any, default: float = 0.0) -> float:
    numeric = _safe_float(value, default)
    if numeric > 1.0:
        numeric = numeric / 100.0 if numeric <= 100.0 else default
    return max(0.0, min(1.0, numeric))


def build_planetary_disaster_command_surface(
    disaster_payload: dict[str, Any],
    *,
    backtest_summary: dict[str, Any] | None = None,
    stream_status: dict[str, Any] | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    forecasts = [row for row in (disaster_payload.get("forecasts") or disaster_payload.get("hazard_forecasts") or []) if isinstance(row, dict)]
    source_health = [row for row in (disaster_payload.get("source_health") or []) if isinstance(row, dict)]
    hotspot_groups = disaster_payload.get("hotspots_by_hazard") if isinstance(disaster_payload.get("hotspots_by_hazard"), dict) else {}

    forecasts.sort(
        key=lambda row: (
            max(_ratio(row.get("likelihood"), 0.0), _ratio(row.get("severity_score"), 0.0)),
            _ratio(row.get("confidence_ratio"), 0.0),
        ),
        reverse=True,
    )

    hazard_counts = Counter(str(item.get("hazard_type") or "unknown").strip().lower() or "unknown" for item in forecasts)
    forecast_lead = {
        str(item.get("hazard_type") or "unknown").strip().lower() or "unknown": round(
            sum(_safe_float(row.get("forecast_horizon"), 0.0) for row in forecasts if str(row.get("hazard_type") or "").strip().lower() == str(item.get("hazard_type") or "").strip().lower())
            / max(1, sum(1 for row in forecasts if str(row.get("hazard_type") or "").strip().lower() == str(item.get("hazard_type") or "").strip().lower())),
            2,
        )
        for item in forecasts[: max(1, min(len(forecasts), limit))]
    }

    top_regions = []
    for row in forecasts[: max(1, int(limit))]:
        top_regions.append(
            {
                "forecast_id": row.get("forecast_id"),
                "hazard_type": row.get("hazard_type"),
                "country": row.get("country"),
                "region": row.get("region"),
                "likelihood": row.get("likelihood"),
                "severity_score": row.get("severity_score"),
                "confidence_ratio": row.get("confidence_ratio"),
                "calibration_status": row.get("calibration_status"),
                "calibration_adjustments": row.get("calibration_adjustments"),
                "forecast_horizon": row.get("forecast_horizon"),
                "recommended_action": row.get("recommended_action"),
            }
        )

    source_posture = []
    for row in source_health:
        source_posture.append(
            {
                "source_family": row.get("source_family"),
                "status": row.get("status"),
                "freshness_minutes": row.get("freshness_minutes"),
                "records": row.get("records"),
                "confidence_ratio": row.get("confidence_ratio"),
            }
        )
    source_posture.sort(
        key=lambda row: (
            str(row.get("status") or ""),
            -_safe_float(row.get("records"), 0.0),
        )
    )

    hotspot_summary = {
        key: len(value) if isinstance(value, list) else 0
        for key, value in hotspot_groups.items()
    }

    overall_backtest = dict((backtest_summary or {}).get("overall") or {})
    hazard_backtests = dict((backtest_summary or {}).get("hazards") or {})

    return {
        "contract_version": "phase-0.6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "forecast_count": len(forecasts),
        "hazard_counts": dict(hazard_counts),
        "forecast_lead_hours": forecast_lead,
        "top_regions": top_regions,
        "source_posture": source_posture[: max(1, int(limit))],
        "stream_status": dict(stream_status or {}),
        "backtest_summary": {
            "overall": overall_backtest,
            "hazards": hazard_backtests,
        },
        "hotspot_summary": hotspot_summary,
    }
