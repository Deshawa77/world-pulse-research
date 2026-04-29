from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from backend.disaster_alert_ops import build_disaster_source_health_snapshot, enrich_disaster_payload_with_ops
from backend.hotspot_history import build_alert_queue, build_alert_transitions, build_top_movers, load_recent_history_lookup, persist_hotspot_snapshots
from collectors.disaster_live_sources import collect_disaster_source_families
from collectors.disasters import build_disaster_raw_batch
from database.mongo import db
from processing.disaster_backtests import latest_disaster_backtest, run_disaster_backtests
from processing.disaster_early_warning import compute_disaster_early_warning
from processing.disaster_hotspot_regions import HOTSPOT_TREND_WINDOWS, iso_now
from processing.disaster_storage import STREAMING_LATEST_JSON, load_json_snapshot, persist_disaster_stream_snapshot
from processing.planetary_signal_store import (
    map_disaster_records_to_normalized_signals,
    map_disaster_records_to_source_events,
    persist_platform_signal_batch,
)

source_health_collection = db["source_health"]
operator_events_collection = db["operator_events"]
hotspot_history_collection = db["hotspot_history"]
model_monitoring_collection = db["model_monitoring"]


HAZARD_KEYS = ["earthquake", "wildfire", "flood", "cyclone"]


def _build_hotspot_history_health() -> dict[str, Any]:
    latest = hotspot_history_collection.find_one({}, {"captured_at": 1}, sort=[("captured_at", -1)])
    latest_raw = latest.get("captured_at") if latest else None
    latest_ts = None
    if latest_raw:
        try:
            latest_ts = datetime.fromisoformat(str(latest_raw).replace("Z", "+00:00"))
            if latest_ts.tzinfo is None:
                latest_ts = latest_ts.replace(tzinfo=timezone.utc)
            else:
                latest_ts = latest_ts.astimezone(timezone.utc)
        except Exception:
            latest_ts = None
    now_dt = datetime.now(timezone.utc)
    age_minutes = round((now_dt - latest_ts).total_seconds() / 60.0, 2) if latest_ts else None
    status = "healthy"
    if latest_ts is None:
        status = "degraded"
    elif age_minutes is not None and age_minutes > 45:
        status = "stale"
    elif age_minutes is not None and age_minutes > 20:
        status = "degraded"
    return {
        "status": status,
        "latest_captured_at": latest_ts.isoformat() if latest_ts else None,
        "age_minutes": age_minutes,
        "advisory": "Hotspot history is live" if status == "healthy" else "Hotspot history is limited or stale",
    }


def _hydrate_hotspot_history_views(payload: dict[str, Any]) -> dict[str, Any]:
    hotspot_groups = ((payload or {}).get("regional_hotspots") or {})
    captured_at = str(payload.get("generated_at") or iso_now())
    for hazard, hotspots in hotspot_groups.items():
        if hotspots:
            persist_hotspot_snapshots(hotspot_history_collection, hotspots, captured_at=captured_at, hazard=hazard)
    payload["hotspot_history_health"] = _build_hotspot_history_health()
    payload["trend_comparison"] = {hazard: build_top_movers(hotspot_history_collection, hours=24, limit=5, hazard=hazard) for hazard in HAZARD_KEYS}
    payload["alert_queue"] = {hazard: build_alert_queue(hotspot_history_collection, hours=24, limit=8, hazard=hazard) for hazard in HAZARD_KEYS}
    payload["recent_alert_transitions"] = {hazard: build_alert_transitions(hotspot_history_collection, hours=72, limit=12, hazard=hazard) for hazard in HAZARD_KEYS}
    payload["legend"] = {
        "bands": [
            {"key": "critical", "label": "Critical", "color": "#f87171"},
            {"key": "active", "label": "Active", "color": "#fbbf24"},
            {"key": "monitor", "label": "Monitor", "color": "#38bdf8"},
            {"key": "guarded", "label": "Guarded", "color": "#94a3b8"},
        ],
        "trend_windows": [{"key": key, "hours": hours} for key, hours in HOTSPOT_TREND_WINDOWS.items()],
        "hazards": [{"key": hazard, "label": hazard.capitalize()} for hazard in HAZARD_KEYS],
    }
    payload["named_region_metadata_version"] = "multi-hazard-v2"
    return payload


def _record_disaster_monitoring(payload: dict[str, Any], run_id: str, cycle_latency_ms: float) -> int:
    forecasts = payload.get("forecasts") if isinstance(payload.get("forecasts"), list) else []
    docs = []
    now_dt = datetime.now(timezone.utc)
    for forecast in forecasts:
        event_type = str(forecast.get("event_type") or "unknown")
        docs.append(
            {
                "timestamp": now_dt,
                "model_version": str(forecast.get("model_version") or f"disaster-{event_type}-runtime"),
                "schema_version": "disaster-warning-v2",
                "feature_names": list((forecast.get("feature_values") or {}).keys()),
                "prediction": float(forecast.get("severity_score") or 0.0),
                "probability": float(forecast.get("likelihood") or 0.0),
                "drift_score": None,
                "role": "system_stream",
                "scope": "disaster_early_warning",
                "hazard": event_type,
                "region": forecast.get("region"),
                "country": forecast.get("country"),
                "confidence": float(forecast.get("confidence") or 0.0),
                "lead_time_hours": int(forecast.get("lead_time_hours") or 0),
                "source_families": forecast.get("signal_sources") or [],
                "run_id": run_id,
                "cycle_latency_ms": round(cycle_latency_ms, 3),
            }
        )
    if not docs:
        return 0
    model_monitoring_collection.insert_many(docs)
    return len(docs)


def build_disaster_stream_status(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {
            "status": "idle",
            "captured_at": None,
            "forecast_count": 0,
            "active_alerts": 0,
            "collector_total_records": 0,
            "stale_families": 0,
            "down_families": 0,
        }
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else {}
    source_health = payload.get("source_health") if isinstance(payload.get("source_health"), list) else []
    alert_queue = payload.get("alert_queue") if isinstance(payload.get("alert_queue"), dict) else {}
    return {
        "status": str((snapshot.get("stream_status") or {}).get("status") or "ok"),
        "run_id": snapshot.get("run_id"),
        "captured_at": snapshot.get("captured_at"),
        "forecast_count": len(payload.get("forecasts") or []),
        "active_alerts": sum(len(items or []) for items in alert_queue.values()) if isinstance(alert_queue, dict) else 0,
        "collector_total_records": int(((snapshot.get("collector_summary") or {}).get("total_records") or 0)),
        "stale_families": sum(1 for item in source_health if str(item.get("status") or "") in {"stale", "degraded"}),
        "down_families": sum(1 for item in source_health if str(item.get("status") or "") == "down"),
        "cycle_latency_ms": float(((snapshot.get("stream_status") or {}).get("cycle_latency_ms") or 0.0)),
    }


def load_disaster_stream_snapshot() -> dict[str, Any] | None:
    snapshot = load_json_snapshot(STREAMING_LATEST_JSON)
    if snapshot and isinstance(snapshot.get("payload"), dict):
        return snapshot
    return None


def run_disaster_stream_cycle(
    *,
    country: str | None = None,
    limit: int = 6,
    refresh_sources: bool = True,
    run_backtest: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    now_utc = datetime.now(timezone.utc)
    collector_summary = collect_disaster_source_families() if refresh_sources else None
    history_lookup = load_recent_history_lookup(hotspot_history_collection, hours=72, points_per_region=12)
    payload = compute_disaster_early_warning(country=country, limit=limit, history_lookup=history_lookup)
    payload = _hydrate_hotspot_history_views(payload)
    payload = enrich_disaster_payload_with_ops(payload, source_health_collection=source_health_collection, operator_events_collection=operator_events_collection)

    backtest = run_disaster_backtests(days=30, persist=True) if run_backtest else latest_disaster_backtest()
    run_id = f"disaster_stream_{now_utc.strftime('%Y%m%dT%H%M%SZ')}"
    cycle_latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
    monitoring_rows = _record_disaster_monitoring(payload, run_id, cycle_latency_ms)

    platform_signal_store = {
        "status": "unavailable",
        "subsystem": "global_disaster_early_warning_ai",
        "run_id": run_id,
        "captured_at": now_utc.isoformat(),
        "source_event_count": 0,
        "normalized_signal_count": 0,
    }
    try:
        disaster_raw_records = build_disaster_raw_batch(hours=72, limit_per_source=max(120, int(limit) * 30))
        platform_source_events = map_disaster_records_to_source_events(
            disaster_raw_records,
            run_id=run_id,
            captured_at=now_utc.isoformat(),
        )
        platform_normalized_signals = map_disaster_records_to_normalized_signals(
            disaster_raw_records,
            run_id=run_id,
            captured_at=now_utc.isoformat(),
        )
        platform_signal_store = persist_platform_signal_batch(
            source_events=platform_source_events,
            normalized_signals=platform_normalized_signals,
            subsystem="global_disaster_early_warning_ai",
            run_id=run_id,
            captured_at=now_utc.isoformat(),
        )
    except Exception as exc:
        platform_signal_store = {
            "status": "error",
            "subsystem": "global_disaster_early_warning_ai",
            "run_id": run_id,
            "captured_at": now_utc.isoformat(),
            "source_event_count": 0,
            "normalized_signal_count": 0,
            "error": str(exc),
        }

    source_health = payload.get("source_health") if isinstance(payload.get("source_health"), list) else build_disaster_source_health_snapshot(source_health_collection)
    stream_status = {
        "status": "ok",
        "run_id": run_id,
        "captured_at": now_utc.isoformat(),
        "refresh_sources": refresh_sources,
        "cycle_latency_ms": cycle_latency_ms,
        "model_monitor_rows": monitoring_rows,
        "collector_total_records": int((collector_summary or {}).get("total_records") or 0),
        "stale_families": sum(1 for item in source_health if str(item.get("status") or "") in {"stale", "degraded"}),
        "down_families": sum(1 for item in source_health if str(item.get("status") or "") == "down"),
        "backtest_precision_proxy": float(((backtest.get("overall") or {}).get("precision_proxy") or 0.0)),
    }
    payload["stream_status"] = stream_status
    payload["backtest_summary"] = backtest
    payload.setdefault("generated_from", {})
    payload["generated_from"]["planetary_signal_store"] = platform_signal_store
    payload["stream_status"]["platform_source_event_count"] = int(platform_signal_store.get("source_event_count") or 0)
    payload["stream_status"]["platform_normalized_signal_count"] = int(platform_signal_store.get("normalized_signal_count") or 0)

    snapshot = {
        "run_id": run_id,
        "status": "ok",
        "captured_at": now_utc.isoformat(),
        "collector_summary": collector_summary,
        "stream_status": stream_status,
        "backtest": backtest,
        "payload": payload,
    }
    persist_disaster_stream_snapshot(snapshot)
    return snapshot
