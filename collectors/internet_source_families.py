from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from collectors.bgp_routing import collect_bgp_routing_events
from collectors.cdn_traffic import collect_cdn_traffic_events
from collectors.cloud_region_health import collect_cloud_region_health_events
from collectors.isp_telemetry import collect_isp_telemetry_events
from processing.internet_map_storage import load_internet_map_collector_bundle, persist_internet_map_collector_bundle


def _collector_summary(source_health: list[dict[str, Any]], raw_events: list[dict[str, Any]], normalized_events: list[dict[str, Any]], captured_at: str, *, served_from_cache: bool) -> dict[str, Any]:
    return {
        "captured_at": captured_at,
        "source_family_count": len(source_health),
        "total_records": len(normalized_events),
        "raw_event_count": len(raw_events),
        "normalized_event_count": len(normalized_events),
        "stale_families": sum(1 for item in source_health if str(item.get("status") or "") in {"stale", "degraded"}),
        "down_families": sum(1 for item in source_health if str(item.get("status") or "") == "down"),
        "healthy_families": sum(1 for item in source_health if str(item.get("status") or "") == "healthy"),
        "direct_families": sum(1 for item in source_health if str(item.get("measurement_mode") or "") == "direct"),
        "cache_hit_families": sum(1 for item in source_health if bool(item.get("cache_hit"))),
        "rate_limited_families": sum(1 for item in source_health if bool(item.get("rate_limited"))),
        "auth_enabled_families": sum(1 for item in source_health if str(item.get("auth_mode") or "none") != "none"),
        "served_from_cache": served_from_cache,
        "stages": sorted({str(item.get("stage") or "unknown") for item in source_health}),
        "measurement_modes": sorted({str(item.get("measurement_mode") or "unknown") for item in source_health}),
    }


def collect_internet_source_families(snapshot: dict[str, Any], *, mode: str = "online", refresh: bool = True) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    if not refresh:
        cached_bundle = load_internet_map_collector_bundle()
        if isinstance(cached_bundle, dict) and isinstance(cached_bundle.get("collector_summary"), dict):
            payload = dict(cached_bundle)
            payload.setdefault("captured_at", started_at)
            summary = dict(payload.get("collector_summary") or {})
            summary["served_from_cache"] = True
            payload["collector_summary"] = summary
            return payload

    bundles = [
        collect_bgp_routing_events(snapshot, mode=mode, refresh=refresh),
        collect_cdn_traffic_events(snapshot, mode=mode, refresh=refresh),
        collect_isp_telemetry_events(snapshot, mode=mode, refresh=refresh),
        collect_cloud_region_health_events(snapshot, mode=mode, refresh=refresh),
    ]
    raw_events = [event for bundle in bundles for event in (bundle.get("raw_events") or [])]
    normalized_events = [event for bundle in bundles for event in (bundle.get("normalized_events") or [])]
    source_health = [bundle.get("source_health") for bundle in bundles if isinstance(bundle.get("source_health"), dict)]
    served_from_cache = all(bool(item.get("cache_hit")) for item in source_health) if source_health else False
    summary = _collector_summary(source_health, raw_events, normalized_events, started_at, served_from_cache=served_from_cache)
    payload = {
        "captured_at": started_at,
        "run_id": f"internet_collectors_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}",
        "raw_events": raw_events,
        "normalized_events": normalized_events,
        "source_health": source_health,
        "collector_summary": summary,
    }
    persist_internet_map_collector_bundle(payload)
    return payload
