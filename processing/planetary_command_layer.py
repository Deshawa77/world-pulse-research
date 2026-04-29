from __future__ import annotations

from collections import defaultdict
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


def _country_scope(row: dict[str, Any]) -> str:
    geography = row.get("geography") if isinstance(row.get("geography"), dict) else {}
    for key in ("country", "origin", "target", "from_country", "to_country"):
        value = str(geography.get(key) or row.get(key) or "").strip().upper()
        if value:
            return value
    return str(row.get("country") or "GLOBAL").strip().upper() or "GLOBAL"


def _top_country_theaters(
    *,
    country_fusion_snapshots: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    correlation_chains: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "country": "GLOBAL",
            "fusion_risk": 0.0,
            "alert_pressure": 0.0,
            "hazard_pressure": 0.0,
            "chain_pressure": 0.0,
            "alerts": 0,
            "hazards": 0,
            "chains": 0,
            "recommended_action": "",
        }
    )
    for row in country_fusion_snapshots:
        country = str(row.get("country") or "GLOBAL").strip().upper() or "GLOBAL"
        bucket = buckets[country]
        bucket["country"] = country
        bucket["fusion_risk"] = max(bucket["fusion_risk"], _ratio(row.get("risk_score"), 0.0))
        if not bucket["recommended_action"]:
            bucket["recommended_action"] = str(row.get("recommended_action") or "").strip()
    for row in alert_events:
        country = _country_scope(row)
        bucket = buckets[country]
        bucket["country"] = country
        bucket["alerts"] += 1
        bucket["alert_pressure"] = max(bucket["alert_pressure"], _ratio(row.get("severity_score"), 0.0))
        if not bucket["recommended_action"]:
            bucket["recommended_action"] = str(row.get("recommended_action") or "").strip()
    for row in hazard_forecasts:
        country = str(row.get("country") or "GLOBAL").strip().upper() or "GLOBAL"
        bucket = buckets[country]
        bucket["country"] = country
        bucket["hazards"] += 1
        bucket["hazard_pressure"] = max(bucket["hazard_pressure"], max(_ratio(row.get("likelihood"), 0.0), _ratio(row.get("severity_score"), 0.0)))
        if not bucket["recommended_action"]:
            bucket["recommended_action"] = str(row.get("recommended_action") or "").strip()
    for row in correlation_chains:
        country = str(row.get("country") or "GLOBAL").strip().upper() or "GLOBAL"
        bucket = buckets[country]
        bucket["country"] = country
        bucket["chains"] += 1
        bucket["chain_pressure"] = max(bucket["chain_pressure"], _ratio(row.get("confidence_ratio"), 0.0))
        if not bucket["recommended_action"]:
            bucket["recommended_action"] = str(row.get("recommended_action") or row.get("summary") or "").strip()

    theaters = []
    for bucket in buckets.values():
        overall = (
            bucket["fusion_risk"] * 0.35
            + bucket["alert_pressure"] * 0.25
            + bucket["hazard_pressure"] * 0.2
            + bucket["chain_pressure"] * 0.2
        )
        theaters.append(
            {
                **bucket,
                "overall_pressure": round(overall, 4),
            }
        )
    theaters.sort(key=lambda row: row["overall_pressure"], reverse=True)
    return theaters[: max(1, int(limit))]


def build_planetary_command_layer(
    overview: dict[str, Any],
    *,
    behavior_surface: dict[str, Any],
    graph_summary: dict[str, Any],
    disaster_surface: dict[str, Any],
    calibration_report: dict[str, Any] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    global_summary = dict(overview.get("global_summary") or {})
    country_fusion_snapshots = [row for row in (overview.get("country_fusion_snapshots") or []) if isinstance(row, dict)]
    alert_events = [row for row in (overview.get("alert_events") or []) if isinstance(row, dict)]
    hazard_forecasts = [row for row in (overview.get("hazard_forecasts") or []) if isinstance(row, dict)]
    correlation_chains = [row for row in (overview.get("correlation_chains") or []) if isinstance(row, dict)]
    replay_frames = [row for row in (overview.get("replay_frames") or []) if isinstance(row, dict)]
    fusion_timeline = [row for row in (overview.get("fusion_timeline") or []) if isinstance(row, dict)]
    runtime_status = [row for row in (overview.get("runtime_status") or []) if isinstance(row, dict)]

    theaters = _top_country_theaters(
        country_fusion_snapshots=country_fusion_snapshots,
        alert_events=alert_events,
        hazard_forecasts=hazard_forecasts,
        correlation_chains=correlation_chains,
        limit=limit,
    )

    incident_watchlist = []
    for row in alert_events[: max(1, int(limit))]:
        incident_watchlist.append(
            {
                "kind": "alert",
                "id": row.get("alert_id"),
                "label": row.get("summary") or row.get("alert_type"),
                "country": _country_scope(row),
                "severity_score": row.get("severity_score"),
                "confidence_ratio": row.get("confidence_ratio"),
                "recommended_action": row.get("recommended_action"),
            }
        )
    for row in hazard_forecasts[: max(1, int(limit // 2 or 1))]:
        incident_watchlist.append(
            {
                "kind": "hazard",
                "id": row.get("forecast_id"),
                "label": f"{row.get('hazard_type')} / {row.get('region')}",
                "country": row.get("country"),
                "severity_score": max(_ratio(row.get("severity_score"), 0.0), _ratio(row.get("likelihood"), 0.0)),
                "confidence_ratio": row.get("confidence_ratio"),
                "recommended_action": row.get("recommended_action"),
            }
        )
    incident_watchlist.sort(key=lambda row: (_ratio(row.get("severity_score"), 0.0), _ratio(row.get("confidence_ratio"), 0.0)), reverse=True)

    replay_readiness = {
        "replay_frame_count": len(replay_frames),
        "fusion_timeline_count": len(fusion_timeline),
        "behavior_replay_count": len(behavior_surface.get("replay_frames") or []),
        "queue_ready": int(len(alert_events) > 0 and len(runtime_status) > 0),
    }
    queue_breakdown = list((overview.get("alert_ops_summary") or {}).get("queue_breakdown") or [])
    validation_summary = {
        "behavior_signal_count": int((behavior_surface.get("source_health") or {}).get("normalized_signal_families") and sum((behavior_surface.get("source_health") or {}).get("normalized_signal_families", {}).values()) or 0),
        "graph_entity_count": graph_summary.get("entity_count") or 0,
        "graph_relationship_count": graph_summary.get("relationship_count") or 0,
        "disaster_forecast_count": disaster_surface.get("forecast_count") or 0,
        "calibration_backtests": dict((calibration_report or {}).get("backtests") or {}),
    }

    return {
        "contract_version": "phase-0.6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "global_kpis": {
            "global_stress_level": global_summary.get("global_stress_level"),
            "conflict_escalation_probability": global_summary.get("conflict_escalation_probability"),
            "economic_panic_indicator": global_summary.get("economic_panic_indicator"),
            "migration_pressure_index": global_summary.get("migration_pressure_index"),
            "infrastructure_fragility_score": global_summary.get("infrastructure_fragility_score"),
            "quality_gate": global_summary.get("quality_gate"),
        },
        "theaters": theaters,
        "incident_watchlist": incident_watchlist[: max(1, int(limit))],
        "replay_readiness": replay_readiness,
        "queue_breakdown": queue_breakdown,
        "validation_summary": validation_summary,
        "graph_command_focus": graph_summary.get("top_entities") or [],
        "disaster_command_focus": disaster_surface.get("top_regions") or [],
        "behavior_command_focus": behavior_surface.get("top_countries") or [],
    }
