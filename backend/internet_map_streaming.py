from __future__ import annotations

import copy
import time
from datetime import datetime, timezone
from typing import Any

from backend.internet_map import build_internet_map_snapshot
from backend.internet_map_ops import enrich_internet_payload_with_ops
from backend.internet_map_telemetry import apply_direct_internet_signals, build_internet_replay_analytics
from collectors.internet_source_families import collect_internet_source_families
from database.mongo import db
from processing.internet_map_backtests import latest_internet_map_backtest
from processing.internet_map_maintenance import build_internet_retention_policy
from processing.internet_map_storage import (
    STREAM_HISTORY_DIR,
    load_internet_map_collector_bundle,
    load_internet_map_stream_snapshot as load_json_stream_snapshot,
    load_recent_internet_map_history,
    persist_internet_map_stream_snapshot,
)
from processing.planetary_signal_store import (
    map_internet_normalized_events_to_normalized_signals,
    map_internet_raw_events_to_source_events,
    persist_platform_signal_batch,
)

source_health_collection = db["source_health"]
operator_events_collection = db["operator_events"]
model_monitoring_collection = db["model_monitoring"]
internet_raw_events_collection = db["internet_raw_events"]
internet_normalized_events_collection = db["internet_normalized_events"]
internet_country_snapshots_collection = db["internet_country_snapshots"]
internet_flow_snapshots_collection = db["internet_flow_snapshots"]
internet_alerts_collection = db["internet_alerts"]
internet_source_health_collection = db["internet_source_health"]

INTERNET_PERSISTENCE_COLLECTIONS = [
    "internet_raw_events",
    "internet_normalized_events",
    "internet_country_snapshots",
    "internet_flow_snapshots",
    "internet_alerts",
    "internet_source_health",
]


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    return numeric if numeric == numeric else fallback


def _history_entries(limit: int = 12) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for payload in load_recent_internet_map_history(limit=limit):
        summary = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        meta = summary.get("summary") if isinstance(summary.get("summary"), dict) else {}
        collector_summary = payload.get("collector_summary") if isinstance(payload.get("collector_summary"), dict) else summary.get("collector_summary") or {}
        entries.append(
            {
                "run_id": str(payload.get("run_id") or payload.get("captured_at") or summary.get("generated_at") or ""),
                "captured_at": str(payload.get("captured_at") or summary.get("generated_at") or ""),
                "global_congestion_index": _safe_float(meta.get("global_congestion_index")),
                "cyber_attack_index": _safe_float(meta.get("cyber_attack_index")),
                "active_attack_paths": int(meta.get("active_attack_paths") or 0),
                "shutdown_alerts": int(meta.get("shutdown_alerts") or 0),
                "source_status": str(meta.get("source_status") or "unknown"),
                "source_stage": str(meta.get("source_stage") or "unknown"),
                "collector_total_records": int(collector_summary.get("total_records") or 0),
            }
        )
    return entries


def load_internet_map_history_payload(limit: int = 24) -> list[dict[str, Any]]:
    return _history_entries(limit=limit)


def load_internet_map_playback_frames(limit: int = 24) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for payload in reversed(load_recent_internet_map_history(limit=limit)):
        summary = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        if not isinstance(summary, dict):
            continue
        captured_at = str(payload.get("captured_at") or summary.get("generated_at") or "")
        run_id = str(payload.get("run_id") or captured_at or summary.get("generated_at") or "")
        frames.append(
            {
                "run_id": run_id,
                "captured_at": captured_at,
                "generated_at": str(summary.get("generated_at") or captured_at),
                "summary": copy.deepcopy(summary.get("summary") or {}),
                "countries": copy.deepcopy(summary.get("countries") or []),
                "flows": copy.deepcopy(summary.get("flows") or []),
                "cyber_attacks": copy.deepcopy(summary.get("cyber_attacks") or []),
                "shutdown_alerts": copy.deepcopy(summary.get("shutdown_alerts") or []),
                "top_corridors": copy.deepcopy(summary.get("top_corridors") or summary.get("flows") or []),
                "source_health": copy.deepcopy(summary.get("source_health") or []),
                "generated_from": copy.deepcopy(summary.get("generated_from") or {}),
                "collector_summary": copy.deepcopy(payload.get("collector_summary") or summary.get("collector_summary") or {}),
                "stream_status": copy.deepcopy(payload.get("stream_status") or summary.get("stream_status") or {}),
            }
        )
    return frames

def _current_history_entry(payload: dict[str, Any], run_id: str, captured_at: str, collector_summary: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "run_id": run_id,
        "captured_at": captured_at,
        "global_congestion_index": _safe_float(summary.get("global_congestion_index")),
        "cyber_attack_index": _safe_float(summary.get("cyber_attack_index")),
        "active_attack_paths": int(summary.get("active_attack_paths") or 0),
        "shutdown_alerts": int(summary.get("shutdown_alerts") or 0),
        "source_status": str(summary.get("source_status") or "unknown"),
        "source_stage": str(summary.get("source_stage") or "unknown"),
        "collector_total_records": int(collector_summary.get("total_records") or 0),
    }


def _country_confidence(country: dict[str, Any]) -> float:
    freshness = _safe_float(country.get("freshness_ratio"), 0.45)
    evidence = _safe_float(country.get("evidence_quality_score"), 0.4)
    validated = 0.08 if bool(country.get("validated_today")) else 0.0
    return round(min(0.98, max(_safe_float(country.get("confidence_ratio"), 0.0), 0.34 + (freshness * 0.28) + (evidence * 0.24) + validated)), 2)


def _flow_confidence(flow: dict[str, Any]) -> float:
    traffic_share = _safe_float(flow.get("traffic_share"), 0.3)
    reroute_factor = max(1.0, _safe_float(flow.get("reroute_factor"), 1.0))
    base = 0.38 + (traffic_share * 0.34) + ((reroute_factor - 1.0) * 0.28)
    return round(min(0.97, max(_safe_float(flow.get("confidence_ratio"), 0.0), base)), 2)


def _alert_freshness(item: dict[str, Any], *, default: int = 60) -> int:
    started_at = str(item.get("started_at") or "").strip()
    if not started_at:
        return default
    try:
        parsed = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(8, int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()))
    except ValueError:
        return default


def _annotate_payload_entities(payload: dict[str, Any], *, captured_at: str, mode: str) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    source_stage = str(summary.get("source_stage") or "phase-1-derived")

    countries: list[dict[str, Any]] = []
    for item in (payload.get("countries") or []):
        country = dict(item)
        country.setdefault("generated_at", captured_at)
        country.setdefault("mode", mode)
        country.setdefault("stage", source_stage)
        country.setdefault("data_quality", "derived")
        country["confidence_ratio"] = _country_confidence(country)
        country.setdefault("freshness_sec", max(18, int((1.0 - _safe_float(country.get("freshness_ratio"), 0.42)) * 120.0)))
        countries.append(country)
    payload["countries"] = countries

    flows: list[dict[str, Any]] = []
    for item in (payload.get("flows") or []):
        flow = dict(item)
        flow.setdefault("generated_at", captured_at)
        flow.setdefault("mode", mode)
        flow.setdefault("stage", source_stage)
        flow["confidence_ratio"] = _flow_confidence(flow)
        flow.setdefault("freshness_sec", max(18, int(18 + _safe_float(flow.get("packet_loss_pct")) * 9.0)))
        flow.setdefault("source_families", ["bgp_routing", "cdn_traffic", "cloud_metrics"])
        flows.append(flow)
    payload["flows"] = flows

    attacks: list[dict[str, Any]] = []
    for item in (payload.get("cyber_attacks") or []):
        attack = dict(item)
        attack.setdefault("generated_at", captured_at)
        attack.setdefault("mode", mode)
        attack.setdefault("stage", source_stage)
        attack.setdefault("freshness_sec", _alert_freshness(attack, default=42))
        attack.setdefault("source_families", ["bgp_routing", "cdn_traffic", "cloud_metrics"])
        attack.setdefault("confidence_ratio", round(min(0.99, _safe_float(attack.get("confidence_ratio"), 0.5) + 0.04), 2))
        attacks.append(attack)
    payload["cyber_attacks"] = attacks

    shutdowns: list[dict[str, Any]] = []
    for item in (payload.get("shutdown_alerts") or []):
        shutdown = dict(item)
        shutdown.setdefault("generated_at", captured_at)
        shutdown.setdefault("mode", mode)
        shutdown.setdefault("stage", source_stage)
        shutdown.setdefault("freshness_sec", _alert_freshness(shutdown, default=55))
        shutdown.setdefault("source_families", ["isp_telemetry", "bgp_routing", "cloud_metrics"])
        shutdown.setdefault("confidence_ratio", round(min(0.99, _safe_float(shutdown.get("confidence_ratio"), 0.48) + 0.04), 2))
        shutdowns.append(shutdown)
    payload["shutdown_alerts"] = shutdowns

    corridors_source = payload.get("top_corridors") if isinstance(payload.get("top_corridors"), list) and payload.get("top_corridors") else flows
    payload["top_corridors"] = [dict(item) for item in corridors_source] if corridors_source else []
    for item in payload.get("top_corridors") or []:
        item.setdefault("generated_at", captured_at)
        item.setdefault("mode", mode)
        item.setdefault("stage", source_stage)
        item["confidence_ratio"] = _flow_confidence(item)
        item.setdefault("freshness_sec", max(18, int(18 + _safe_float(item.get("packet_loss_pct")) * 9.0)))
        item.setdefault("source_families", ["bgp_routing", "cdn_traffic", "cloud_metrics"])

    return payload


def _build_observability(payload: dict[str, Any], collector_summary: dict[str, Any], *, cycle_latency_ms: float, backtest_summary: dict[str, Any]) -> dict[str, Any]:
    source_health = payload.get("source_health") if isinstance(payload.get("source_health"), list) else []
    ops_summary = payload.get("alert_ops_summary") if isinstance(payload.get("alert_ops_summary"), dict) else {}
    freshness_rows = [
        {
            "source": str(item.get("source") or item.get("source_family") or "unknown"),
            "status": str(item.get("status") or "unknown"),
            "freshness_sec": _safe_float(item.get("freshness_sec"), 999.0),
        }
        for item in source_health
    ]
    overall = backtest_summary.get("overall") if isinstance(backtest_summary.get("overall"), dict) else {}
    return {
        "source_freshness": freshness_rows,
        "collector_health": {
            "source_family_count": int(collector_summary.get("source_family_count") or len(source_health)),
            "total_records": int(collector_summary.get("total_records") or 0),
            "raw_event_count": int(collector_summary.get("raw_event_count") or 0),
            "normalized_event_count": int(collector_summary.get("normalized_event_count") or 0),
            "stale_families": int(collector_summary.get("stale_families") or 0),
            "down_families": int(collector_summary.get("down_families") or 0),
            "direct_families": int(collector_summary.get("direct_families") or 0),
            "cache_hit_families": int(collector_summary.get("cache_hit_families") or 0),
            "rate_limited_families": int(collector_summary.get("rate_limited_families") or 0),
            "auth_enabled_families": int(collector_summary.get("auth_enabled_families") or 0),
            "served_from_cache": bool(collector_summary.get("served_from_cache")),
        },
        "snapshot_build": {
            "latency_ms": round(cycle_latency_ms, 3),
            "p95_target_ms": 800,
            "within_target": cycle_latency_ms <= 800.0,
            "cache_namespace": "internet_map",
            "cache_ttl_sec": 12,
        },
        "stream_delivery": {
            "mode": "sse",
            "poll_seconds": 12,
            "replay_history_points": len(payload.get("history") or []),
        },
        "alert_quality": {
            "active_queue_count": int(ops_summary.get("active_queue_count") or 0),
            "suppressed_by_snooze": int(ops_summary.get("suppressed_by_snooze") or 0),
            "false_positive_flags": int(ops_summary.get("false_positive_flags") or 0),
            "backtest_precision_proxy": _safe_float(overall.get("feedback_adjusted_precision_proxy") or overall.get("precision_proxy")),
            "feedback_adjusted_precision_proxy": _safe_float(overall.get("feedback_adjusted_precision_proxy")),
        },
        "slo_targets": {
            "snapshot_api_p95_ms": 800,
            "freshness_sec": 60,
            "alert_delivery_cycles": 1,
        },
    }


def _build_persistence_state(run_id: str, captured_at: str, history_count: int, retention_policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "collections": list(INTERNET_PERSISTENCE_COLLECTIONS),
        "history_points": int(history_count),
        "replay_available": history_count > 0,
        "local_history_dir": str(STREAM_HISTORY_DIR),
        "last_run_id": run_id,
        "latest_captured_at": captured_at,
        "retention_days": retention_policy.get("mongo_retention_days"),
        "maintenance_script": retention_policy.get("maintenance_script"),
    }


def _safe_insert_many(collection, docs: list[dict[str, Any]]) -> None:
    if not docs:
        return
    try:
        collection.insert_many(docs, ordered=False)
    except Exception:
        pass


def _persist_source_health_docs(source_health: list[dict[str, Any]], *, captured_at: str) -> None:
    for item in source_health:
        source_name = str(item.get("source_name") or item.get("source_family") or item.get("source") or "").strip()
        if not source_name:
            continue
        doc = {
            "scope": "internet_map",
            "source": source_name,
            "source_family": item.get("source_family") or source_name,
            "status": item.get("status"),
            "records": int(item.get("records") or 0),
            "coverage_ratio": _safe_float(item.get("coverage_ratio")),
            "confidence_ratio": _safe_float(item.get("confidence_ratio")),
            "freshness_sec": _safe_float(item.get("freshness_sec"), 999.0),
            "advisory": item.get("advisory"),
            "detail": item.get("detail"),
            "stage": item.get("stage"),
            "measurement_mode": item.get("measurement_mode"),
            "feed_origin": item.get("feed_origin"),
            "provenance": item.get("provenance"),
            "updated_at": captured_at,
            "last_success": captured_at,
            "error": "; ".join(str(error) for error in (item.get("errors") or []) if str(error).strip()) or None,
        }
        try:
            source_health_collection.update_one({"source": source_name}, {"$set": doc}, upsert=True)
        except Exception:
            pass
        try:
            internet_source_health_collection.update_one({"scope": "internet_map", "source": source_name}, {"$set": doc}, upsert=True)
        except Exception:
            pass


def _persist_raw_and_normalized_events(raw_events: list[dict[str, Any]], normalized_events: list[dict[str, Any]], *, run_id: str, captured_at: str) -> None:
    _safe_insert_many(internet_raw_events_collection, [{**item, "run_id": run_id, "captured_at": captured_at, "scope": "internet_map"} for item in raw_events])
    _safe_insert_many(internet_normalized_events_collection, [{**item, "run_id": run_id, "captured_at": captured_at, "scope": "internet_map"} for item in normalized_events])


def _persist_snapshot_entities(payload: dict[str, Any], *, run_id: str, captured_at: str, mode: str) -> None:
    countries = payload.get("countries") if isinstance(payload.get("countries"), list) else []
    flows = payload.get("flows") if isinstance(payload.get("flows"), list) else []
    source_health = payload.get("source_health") if isinstance(payload.get("source_health"), list) else []
    alerts = []
    for item in (payload.get("cyber_attacks") or []):
        alerts.append({**item, "alert_type": "attack"})
    for item in (payload.get("shutdown_alerts") or []):
        alerts.append({**item, "alert_type": "shutdown"})
    _safe_insert_many(internet_country_snapshots_collection, [{**item, "run_id": run_id, "captured_at": captured_at, "mode": mode, "scope": "internet_map"} for item in countries])
    _safe_insert_many(internet_flow_snapshots_collection, [{**item, "run_id": run_id, "captured_at": captured_at, "mode": mode, "scope": "internet_map"} for item in flows])
    _safe_insert_many(internet_alerts_collection, [{**item, "run_id": run_id, "captured_at": captured_at, "mode": mode, "scope": "internet_map"} for item in alerts])
    _safe_insert_many(internet_source_health_collection, [{**item, "run_id": run_id, "captured_at": captured_at, "mode": mode, "scope": "internet_map"} for item in source_health])


def _record_monitoring(payload: dict[str, Any], collector_summary: dict[str, Any], *, run_id: str, cycle_latency_ms: float) -> None:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    try:
        model_monitoring_collection.insert_one(
            {
                "timestamp": datetime.now(timezone.utc),
                "model_version": "internet-map-runtime-v4",
                "schema_version": "internet-map-stream-v4",
                "scope": "internet_map",
                "prediction": _safe_float(summary.get("global_congestion_index")),
                "probability": min(1.0, _safe_float(summary.get("cyber_attack_index")) / 100.0),
                "drift_score": None,
                "role": "system_stream",
                "collector_total_records": int(collector_summary.get("total_records") or 0),
                "raw_event_count": int(collector_summary.get("raw_event_count") or 0),
                "normalized_event_count": int(collector_summary.get("normalized_event_count") or 0),
                "cycle_latency_ms": round(float(cycle_latency_ms), 3),
                "run_id": run_id,
            }
        )
    except Exception:
        pass


def build_internet_map_stream_status(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {
            "status": "idle",
            "captured_at": None,
            "active_attack_paths": 0,
            "shutdown_alerts": 0,
            "collector_total_records": 0,
            "raw_event_count": 0,
            "normalized_event_count": 0,
            "stale_families": 0,
            "down_families": 0,
            "cycle_latency_ms": 0.0,
            "replay_history_points": len(_history_entries(limit=24)),
        }
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    collector_summary = snapshot.get("collector_summary") if isinstance(snapshot.get("collector_summary"), dict) else {}
    stream_status = snapshot.get("stream_status") if isinstance(snapshot.get("stream_status"), dict) else {}
    return {
        "status": str(stream_status.get("status") or "ok"),
        "run_id": snapshot.get("run_id"),
        "captured_at": snapshot.get("captured_at"),
        "active_attack_paths": int(summary.get("active_attack_paths") or 0),
        "shutdown_alerts": int(summary.get("shutdown_alerts") or 0),
        "collector_total_records": int(collector_summary.get("total_records") or 0),
        "raw_event_count": int(collector_summary.get("raw_event_count") or 0),
        "normalized_event_count": int(collector_summary.get("normalized_event_count") or 0),
        "stale_families": int(collector_summary.get("stale_families") or 0),
        "down_families": int(collector_summary.get("down_families") or 0),
        "cycle_latency_ms": round(_safe_float(stream_status.get("cycle_latency_ms")), 3),
        "replay_history_points": len(_history_entries(limit=24)),
        "refresh_sources": bool(stream_status.get("refresh_sources")),
    }


def load_internet_map_stream_snapshot() -> dict[str, Any] | None:
    snapshot = load_json_stream_snapshot()
    if snapshot and isinstance(snapshot.get("payload"), dict):
        return snapshot
    return None


def _resolve_collector_bundle(payload: dict[str, Any], *, mode: str, refresh_sources: bool) -> dict[str, Any]:
    if refresh_sources:
        return collect_internet_source_families(payload, mode=mode, refresh=True)
    cached_bundle = load_internet_map_collector_bundle()
    if isinstance(cached_bundle, dict) and isinstance(cached_bundle.get("collector_summary"), dict):
        summary = dict(cached_bundle.get("collector_summary") or {})
        summary["served_from_cache"] = True
        return {
            "captured_at": cached_bundle.get("captured_at") or datetime.now(timezone.utc).isoformat(),
            "raw_events": list(cached_bundle.get("raw_events") or []),
            "normalized_events": list(cached_bundle.get("normalized_events") or []),
            "source_health": list(cached_bundle.get("source_health") or []),
            "collector_summary": summary,
        }
    return collect_internet_source_families(payload, mode=mode, refresh=True)


def run_internet_map_stream_cycle(
    country_snapshot: list[dict[str, Any]],
    global_snapshot: dict[str, Any],
    *,
    mode: str = "online",
    refresh_sources: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    now_utc = datetime.now(timezone.utc)
    payload = build_internet_map_snapshot(country_snapshot, global_doc=global_snapshot, mode=mode)
    collector_bundle = _resolve_collector_bundle(payload, mode=mode, refresh_sources=refresh_sources)
    if collector_bundle.get("source_health"):
        payload["source_health"] = collector_bundle.get("source_health")
    payload = apply_direct_internet_signals(payload, list(collector_bundle.get("normalized_events") or []), list(payload.get("source_health") or []))

    captured_at = now_utc.isoformat()
    run_id = f"internet_map_{now_utc.strftime('%Y%m%dT%H%M%S%fZ')}"
    payload = _annotate_payload_entities(payload, captured_at=captured_at, mode=mode)
    payload = enrich_internet_payload_with_ops(payload, source_health_collection=source_health_collection, operator_events_collection=operator_events_collection)

    payload.setdefault("generated_from", {})
    payload["generated_from"]["collector_stages"] = (collector_bundle.get("collector_summary") or {}).get("stages") or []
    payload["generated_from"]["raw_event_count"] = int((collector_bundle.get("collector_summary") or {}).get("raw_event_count") or 0)
    payload["generated_from"]["normalized_event_count"] = int((collector_bundle.get("collector_summary") or {}).get("normalized_event_count") or 0)
    payload["generated_from"]["local_history_dir"] = str(STREAM_HISTORY_DIR)
    payload["generated_from"]["persistence_enabled"] = True
    payload["generated_from"]["measurement_modes"] = (collector_bundle.get("collector_summary") or {}).get("measurement_modes") or []
    payload["generated_from"]["served_from_cache"] = bool((collector_bundle.get("collector_summary") or {}).get("served_from_cache"))

    history_rows = _history_entries(limit=11)
    payload["history"] = [_current_history_entry(payload, run_id, captured_at, collector_bundle.get("collector_summary") or {})] + history_rows
    payload["replay_available"] = bool(payload.get("history"))

    cycle_latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
    stream_status = {
        "status": "ok",
        "run_id": run_id,
        "captured_at": captured_at,
        "refresh_sources": refresh_sources,
        "cycle_latency_ms": cycle_latency_ms,
        "collector_total_records": int(((collector_bundle.get("collector_summary") or {}).get("total_records") or 0)),
        "raw_event_count": int(((collector_bundle.get("collector_summary") or {}).get("raw_event_count") or 0)),
        "normalized_event_count": int(((collector_bundle.get("collector_summary") or {}).get("normalized_event_count") or 0)),
        "stale_families": int(((collector_bundle.get("collector_summary") or {}).get("stale_families") or 0)),
        "down_families": int(((collector_bundle.get("collector_summary") or {}).get("down_families") or 0)),
        "replay_history_points": len(payload.get("history") or []),
    }
    payload["stream_status"] = stream_status
    payload["collector_summary"] = collector_bundle.get("collector_summary") or {}

    _persist_source_health_docs(payload.get("source_health") or [], captured_at=captured_at)
    _persist_raw_and_normalized_events(collector_bundle.get("raw_events") or [], collector_bundle.get("normalized_events") or [], run_id=run_id, captured_at=captured_at)
    platform_source_events = map_internet_raw_events_to_source_events(
        list(collector_bundle.get("raw_events") or []),
        run_id=run_id,
        captured_at=captured_at,
        mode=mode,
    )
    platform_normalized_signals = map_internet_normalized_events_to_normalized_signals(
        list(collector_bundle.get("normalized_events") or []),
        run_id=run_id,
        captured_at=captured_at,
        mode=mode,
    )
    platform_signal_store = persist_platform_signal_batch(
        source_events=platform_source_events,
        normalized_signals=platform_normalized_signals,
        subsystem="real_time_internet_map",
        run_id=run_id,
        captured_at=captured_at,
        mode=mode,
    )
    payload["generated_from"]["planetary_signal_store"] = platform_signal_store
    stream_status["platform_source_event_count"] = int(platform_signal_store.get("source_event_count") or 0)
    stream_status["platform_normalized_signal_count"] = int(platform_signal_store.get("normalized_signal_count") or 0)
    _persist_snapshot_entities(payload, run_id=run_id, captured_at=captured_at, mode=mode)

    backtest_summary = latest_internet_map_backtest()
    replay_analytics = build_internet_replay_analytics(list(payload.get("history") or []), internet_country_snapshots_collection, internet_flow_snapshots_collection, internet_alerts_collection)
    retention_policy = build_internet_retention_policy()
    payload["backtest_summary"] = backtest_summary
    payload["replay_analytics"] = replay_analytics
    payload["retention_policy"] = retention_policy
    payload["observability"] = _build_observability(payload, collector_bundle.get("collector_summary") or {}, cycle_latency_ms=cycle_latency_ms, backtest_summary=backtest_summary)
    payload["persistence"] = _build_persistence_state(run_id, captured_at, len(payload.get("history") or []), retention_policy)
    payload["persistence"]["planetary_signal_store"] = platform_signal_store

    _record_monitoring(payload, collector_bundle.get("collector_summary") or {}, run_id=run_id, cycle_latency_ms=cycle_latency_ms)

    snapshot = {
        "run_id": run_id,
        "status": "ok",
        "captured_at": captured_at,
        "collector_summary": collector_bundle.get("collector_summary") or {},
        "stream_status": stream_status,
        "payload": copy.deepcopy(payload),
    }
    storage_result = persist_internet_map_stream_snapshot(snapshot)
    payload["storage"] = storage_result
    snapshot["payload"] = payload
    return snapshot

