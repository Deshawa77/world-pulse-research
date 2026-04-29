from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.planetary_intelligence import build_country_snapshots, build_global_summary
from processing.planetary_signal_store import (
    map_country_rows_to_normalized_signals,
    map_country_rows_to_source_events,
    map_global_behavior_to_normalized_signals,
    map_global_behavior_to_source_events,
    persist_platform_signal_batch,
)

CONTRACT_VERSION = "phase-0.2"
BEHAVIOR_SUBSYSTEM = "global_human_behavior_intelligence_engine"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _ratio(value: Any, default: float = 0.0) -> float:
    numeric = _safe_float(value, default)
    if numeric > 1.0:
        numeric = numeric / 100.0 if numeric <= 100.0 else default
    return _clamp(numeric, 0.0, 1.0)


def _mean(values: list[float], default: float = 0.0) -> float:
    if not values:
        return default
    return sum(float(value) for value in values) / float(len(values))


def build_global_behavior_snapshot(
    country_snapshots: list[dict[str, Any]],
    global_context: dict[str, Any],
    global_doc: dict[str, Any] | None,
    *,
    mode: str,
    generated_at: str,
) -> dict[str, Any]:
    summary = build_global_summary(country_snapshots, [], [], global_context, global_doc, {})
    features = (global_doc or {}).get("features") if isinstance((global_doc or {}).get("features"), dict) else {}
    direct_values = [
        _ratio((item.get("signal_scores") or {}).get("direct_behavior_score"), 0.0)
        for item in country_snapshots
        if isinstance(item, dict)
    ]
    context_values = [
        _ratio((item.get("signal_scores") or {}).get("contextual_pressure_score"), 0.0)
        for item in country_snapshots
        if isinstance(item, dict)
    ]
    attention_values = [
        max(
            _ratio((item.get("signal_scores") or {}).get("narrative_velocity_score"), 0.0),
            _ratio((item.get("signal_scores") or {}).get("coordination_risk_score"), 0.0),
        )
        for item in country_snapshots
        if isinstance(item, dict)
    ]
    disruption_values = [
        max(
            _ratio((item.get("signal_scores") or {}).get("mobility_disruption_score"), 0.0),
            _ratio((item.get("signal_scores") or {}).get("logistics_stress_score"), 0.0),
        )
        for item in country_snapshots
        if isinstance(item, dict)
    ]
    economic_values = [
        max(
            _ratio((item.get("signal_scores") or {}).get("household_stress_score"), 0.0),
            _ratio((item.get("signal_scores") or {}).get("energy_stress_score"), 0.0),
        )
        for item in country_snapshots
        if isinstance(item, dict)
    ]
    ranked_countries = sorted(
        [item for item in country_snapshots if isinstance(item, dict)],
        key=lambda item: float(item.get("raw_risk_score") or item.get("display_risk") or 0.0),
        reverse=True,
    )[:10]
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": generated_at,
        "mode": mode,
        "freshness_sec": int(summary.get("freshness_sec") or 0),
        "confidence_ratio": round(_ratio(summary.get("confidence_ratio"), 0.0), 4),
        "global_stress_level": round(_safe_float(summary.get("global_stress_level"), 0.0), 4),
        "global_behavior_index": round(_safe_float(features.get("global_behavior_index"), _mean(direct_values, 0.0)), 4),
        "global_context_index": round(_safe_float(features.get("global_context_index"), _mean(context_values, 0.0)), 4),
        "global_attention_index": round(_safe_float(features.get("global_attention_index"), _mean(attention_values, 0.0)), 4),
        "global_disruption_index": round(_safe_float(features.get("global_disruption_index"), _mean(disruption_values, 0.0)), 4),
        "global_economic_stress_index": round(_safe_float(features.get("global_economic_stress_index"), _mean(economic_values, 0.0)), 4),
        "economic_panic_indicator": round(_safe_float(summary.get("economic_panic_indicator"), 0.0), 4),
        "migration_pressure_index": round(_safe_float(summary.get("migration_pressure_index"), 0.0), 4),
        "global_mood_score": round(_safe_float(features.get("global_mood_score"), 50.0), 2),
        "global_mood_confidence": round(_safe_float(features.get("global_mood_confidence"), summary.get("confidence_ratio") or 0.0), 4),
        "top_contributing_metrics": list(summary.get("top_contributing_metrics") or []),
        "top_stressed_countries": [
            {
                "country": str(item.get("country") or "UNK"),
                "display_risk": round(_safe_float(item.get("display_risk"), _safe_float(item.get("raw_risk_score"), 0.0)), 2),
                "risk_band": str(item.get("risk_band") or "unknown"),
                "confidence_ratio": round(_ratio(item.get("confidence_ratio"), 0.0), 4),
                "advisory": str(item.get("advisory") or ""),
            }
            for item in ranked_countries
        ],
        "quality_gate": dict((global_context or {}).get("quality_gate") or {}),
        "source_health": dict((global_context or {}).get("source_health") or {}),
        "provenance_summary": {
            **dict(summary.get("provenance_summary") or {}),
            "subsystem": BEHAVIOR_SUBSYSTEM,
            "country_count": len(country_snapshots),
        },
    }


def materialize_behavior_payload(
    country_rows: list[dict[str, Any]],
    global_context: dict[str, Any],
    global_doc: dict[str, Any] | None,
    *,
    mode: str,
    run_id: str,
    captured_at: str,
    country_limit: int = 14,
    persist: bool = True,
    root: str | None = None,
) -> dict[str, Any]:
    country_snapshots = build_country_snapshots(country_rows, limit=max(1, int(country_limit)))
    source_events = [
        *map_country_rows_to_source_events(country_rows, run_id=run_id, captured_at=captured_at, mode=mode),
        *map_global_behavior_to_source_events(global_doc, global_context, run_id=run_id, captured_at=captured_at, mode=mode),
    ]
    normalized_signals = [
        *map_country_rows_to_normalized_signals(country_rows, run_id=run_id, captured_at=captured_at, mode=mode),
        *map_global_behavior_to_normalized_signals(global_doc, global_context, run_id=run_id, captured_at=captured_at, mode=mode),
    ]
    persistence = persist_platform_signal_batch(
        source_events=source_events,
        normalized_signals=normalized_signals,
        subsystem=BEHAVIOR_SUBSYSTEM,
        run_id=run_id,
        captured_at=captured_at,
        mode=mode,
        root=root,
        persist_db=persist,
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": captured_at,
        "mode": mode,
        "country_snapshots": country_snapshots,
        "global_behavior_snapshot": build_global_behavior_snapshot(
            country_snapshots,
            global_context,
            global_doc,
            mode=mode,
            generated_at=captured_at,
        ),
        "persistence": persistence,
        "counts": {
            "country_snapshot_count": len(country_snapshots),
            "source_event_count": len(source_events),
            "normalized_signal_count": len(normalized_signals),
        },
    }
