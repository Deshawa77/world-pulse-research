from __future__ import annotations

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


def _geography_country(row: dict[str, Any]) -> str:
    geography = row.get("geography") if isinstance(row.get("geography"), dict) else {}
    return str(
        geography.get("country")
        or row.get("country")
        or row.get("country_code")
        or row.get("iso2")
        or ""
    ).strip().upper()


def _subsystem_scores(row: dict[str, Any]) -> dict[str, float]:
    source = row.get("subsystem_scores") if isinstance(row.get("subsystem_scores"), dict) else {}
    return {
        str(key): round(_ratio(value), 4)
        for key, value in source.items()
        if str(key).strip()
    }


def _hotspot_markers(
    hazard_forecasts: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for row in hazard_forecasts:
        markers.append(
            {
                "marker_id": str(row.get("forecast_id") or ""),
                "kind": "hazard",
                "country": _geography_country(row),
                "region": str(row.get("region") or "").strip(),
                "label": str(row.get("hazard_type") or "Hazard"),
                "severity_score": round(_ratio(row.get("severity_score")), 4),
                "confidence_ratio": round(_ratio(row.get("confidence_ratio")), 4),
                "likelihood": round(_ratio(row.get("likelihood")), 4),
                "geography": row.get("geography") if isinstance(row.get("geography"), dict) else {},
            }
        )
    for row in alert_events:
        markers.append(
            {
                "marker_id": str(row.get("alert_id") or ""),
                "kind": "alert",
                "country": _geography_country(row),
                "region": str(row.get("summary") or "").strip(),
                "label": str(row.get("alert_type") or "Alert"),
                "severity_score": round(_ratio(row.get("severity_score")), 4),
                "confidence_ratio": round(_ratio(row.get("confidence_ratio")), 4),
                "likelihood": round(_ratio(row.get("severity_score")), 4),
                "geography": row.get("geography") if isinstance(row.get("geography"), dict) else {},
            }
        )
    return markers


def build_planetary_map_replay_frame(
    *,
    overview: dict[str, Any],
    command_layer: dict[str, Any],
    behavior_surface: dict[str, Any],
    calibration_report: dict[str, Any],
    run_id: str,
    captured_at: str,
    mode: str = "online",
) -> dict[str, Any]:
    country_fusion = [
        row for row in (overview.get("country_fusion_snapshots") or []) if isinstance(row, dict)
    ]
    corridor_snapshots = [
        row for row in (overview.get("corridor_snapshots") or []) if isinstance(row, dict)
    ]
    hazard_forecasts = [
        row for row in (overview.get("hazard_forecasts") or []) if isinstance(row, dict)
    ]
    alert_events = [
        row for row in (overview.get("alert_events") or []) if isinstance(row, dict)
    ]
    graph_focus = [
        row for row in (command_layer.get("graph_command_focus") or []) if isinstance(row, dict)
    ]
    theaters = [
        row for row in (command_layer.get("theaters") or []) if isinstance(row, dict)
    ]
    disaster_focus = [
        row for row in (command_layer.get("disaster_command_focus") or []) if isinstance(row, dict)
    ]
    countries = []
    for row in country_fusion:
        country = str(row.get("country") or "").strip().upper()
        if not country:
            continue
        countries.append(
            {
                "country": country,
                "fused_score": round(_ratio(row.get("fused_score")), 4),
                "confidence_ratio": round(_ratio(row.get("confidence_ratio")), 4),
                "freshness_sec": row.get("freshness_sec"),
                "fusion_band": str(row.get("fusion_band") or "").strip(),
                "subsystem_scores": _subsystem_scores(row),
                "recommended_action": row.get("recommended_action"),
            }
        )
    countries.sort(
        key=lambda row: (row.get("fused_score") or 0.0, row.get("confidence_ratio") or 0.0),
        reverse=True,
    )
    corridors = []
    for row in corridor_snapshots:
        corridor_id = str(row.get("corridor_id") or "").strip()
        if not corridor_id:
            continue
        corridors.append(
            {
                "corridor_id": corridor_id,
                "from_region": str(row.get("from_region") or "").strip(),
                "to_region": str(row.get("to_region") or "").strip(),
                "from_country": str((((row.get("from_region") if isinstance(row.get("from_region"), dict) else {}) or {}).get("country") or "")).strip().upper(),
                "to_country": str((((row.get("to_region") if isinstance(row.get("to_region"), dict) else {}) or {}).get("country") or "")).strip().upper(),
                "severity_score": round(_ratio(row.get("severity_score")), 4),
                "confidence_ratio": round(_ratio(row.get("confidence_ratio")), 4),
                "related_entities": list(row.get("related_entities") or []),
                "provenance_summary": row.get("provenance_summary"),
            }
        )
    corridors.sort(
        key=lambda row: (row.get("severity_score") or 0.0, row.get("confidence_ratio") or 0.0),
        reverse=True,
    )
    return {
        "contract_version": "phase-0.8",
        "platform_scope": "planetary_map_replay",
        "run_id": run_id,
        "frame_id": run_id,
        "captured_at": captured_at,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frame_timestamp": captured_at,
        "mode": mode,
        "summary": "Replay frame for country fusion, corridors, hazards, alerts, and graph-command context.",
        "global_summary": overview.get("global_summary") if isinstance(overview.get("global_summary"), dict) else {},
        "countries": countries,
        "corridors": corridors,
        "hotspots": _hotspot_markers(hazard_forecasts, alert_events),
        "graph_focus": graph_focus,
        "theaters": theaters,
        "disaster_focus": disaster_focus,
        "behavior_replay": list((behavior_surface.get("replay_frames") or []))[:12],
        "calibration_snapshot": calibration_report.get("summary") if isinstance(calibration_report.get("summary"), dict) else {},
        "replay_bundle": {
            "country_codes": [row["country"] for row in countries[:24]],
            "corridor_ids": [row["corridor_id"] for row in corridors[:18]],
            "hazard_ids": [str(row.get("forecast_id") or "") for row in hazard_forecasts[:18]],
            "alert_ids": [str(row.get("alert_id") or "") for row in alert_events[:18]],
            "entity_ids": [str(row.get("entity_id") or "") for row in graph_focus[:18]],
        },
    }
