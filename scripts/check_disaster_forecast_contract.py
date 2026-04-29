from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import _build_disaster_warning_payload

CANONICAL_SOURCE_FAMILIES = {
    "satellite_imagery",
    "seismic_data",
    "weather_sensors",
    "ocean_sensors",
    "social_media_signals",
}
REQUIRED_FORECAST_FIELDS = [
    "event_type",
    "signal_sources",
    "confidence",
    "lead_time_hours",
    "top_contributing_signals",
    "recommended_action",
]


def _validate_forecast(forecast: dict, index: int) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FORECAST_FIELDS:
        if field not in forecast:
            errors.append(f"forecast[{index}] missing {field}")
    signal_sources = forecast.get("signal_sources") or []
    if not isinstance(signal_sources, list) or not signal_sources:
        errors.append(f"forecast[{index}] missing signal_sources values")
    elif any(str(source) not in CANONICAL_SOURCE_FAMILIES for source in signal_sources):
        errors.append(f"forecast[{index}] contains non-canonical source family")
    confidence = forecast.get("confidence")
    try:
        confidence_value = float(confidence)
        if confidence_value < 0.0 or confidence_value > 1.0:
            errors.append(f"forecast[{index}] confidence out of range")
    except Exception:
        errors.append(f"forecast[{index}] confidence is not numeric")
    try:
        if int(forecast.get("lead_time_hours") or 0) <= 0:
            errors.append(f"forecast[{index}] lead_time_hours must be positive")
    except Exception:
        errors.append(f"forecast[{index}] lead_time_hours is invalid")
    explainers = forecast.get("top_contributing_signals") or []
    if not isinstance(explainers, list) or not explainers:
        errors.append(f"forecast[{index}] explainability signals missing")
    action = str(forecast.get("recommended_action") or "").strip()
    if not action:
        errors.append(f"forecast[{index}] recommended_action missing")
    return errors


def main() -> None:
    payload = _build_disaster_warning_payload(limit=6)
    forecasts = payload.get("forecasts") or []
    source_health = payload.get("source_health") or []
    queue_groups = payload.get("alert_queue") or {}
    errors: list[str] = []

    if not forecasts:
        errors.append("payload returned no forecasts")
    for index, forecast in enumerate(forecasts):
        errors.extend(_validate_forecast(forecast, index))

    seen_families = {str(row.get("source_family") or "") for row in source_health}
    if not CANONICAL_SOURCE_FAMILIES.issubset(seen_families):
        errors.append("source_health missing one or more source families")

    for hazard, items in queue_groups.items():
        for index, item in enumerate(items or []):
            if not str(item.get("dedupe_key") or "").strip():
                errors.append(f"alert_queue[{hazard}][{index}] missing dedupe_key")
            if not str(item.get("threshold_reason") or "").strip():
                errors.append(f"alert_queue[{hazard}][{index}] missing threshold_reason")
            if not isinstance(item.get("ops_state"), dict):
                errors.append(f"alert_queue[{hazard}][{index}] missing ops_state")

    if errors:
        raise SystemExit("Disaster forecast contract failed: " + "; ".join(errors))

    print({
        "status": "ok",
        "forecast_count": len(forecasts),
        "source_health_count": len(source_health),
        "active_queue_count": sum(len(items or []) for items in queue_groups.values()),
        "validated_fields": REQUIRED_FORECAST_FIELDS,
    })


if __name__ == "__main__":
    main()
