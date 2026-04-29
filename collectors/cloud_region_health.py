from __future__ import annotations

from pathlib import Path
from typing import Any

from collectors.internet_feed_utils import load_feed_records, normalize_code, normalize_region, safe_float, safe_int


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data_lake" / "internet_map" / "cloud_region_health.json"
METRIC_ALIASES = {
    "region_health_score": ("region_health_score",),
    "egress_saturation_ratio": ("egress_saturation_ratio",),
    "dns_error_ratio": ("dns_error_ratio",),
    "control_plane_incident_score": ("control_plane_incident_score",),
    "api_error_ratio": ("api_error_ratio",),
}


def _seed(value: str) -> int:
    return sum((index + 7) * ord(char) for index, char in enumerate(str(value or "").upper()))


def _metric_value(record: dict[str, Any], metric_name: str, fallback: float = 0.0) -> float:
    aliases = METRIC_ALIASES.get(metric_name, (metric_name,))
    for key in aliases:
        if key in record and record.get(key) is not None:
            return safe_float(record.get(key), fallback)
    return fallback


def _record_base(record: dict[str, Any], *, feed: dict[str, Any], mode: str, captured_at: str, index: int) -> dict[str, Any]:
    origin = normalize_code(record.get("origin") or record.get("source_country"))
    destination = normalize_code(record.get("destination") or record.get("country") or record.get("target_country"))
    country = normalize_code(record.get("country") or destination or origin, "GLB")
    region = normalize_region(origin, destination, record.get("region"), country)
    return {
        "source_family": "cloud_metrics",
        "source_name": str(record.get("source_name") or feed.get("source_name") or "cloud_region_feed"),
        "stage": str(record.get("stage") or feed.get("stage") or "scaffold"),
        "measurement_mode": str(record.get("measurement_mode") or feed.get("measurement_mode") or "synthetic"),
        "feed_origin": str(feed.get("feed_origin") or "none"),
        "mode": mode,
        "timestamp": str(record.get("timestamp") or captured_at),
        "country": country,
        "origin": origin or None,
        "destination": destination or country,
        "region": region,
        "cloud_region": record.get("cloud_region") or record.get("provider_region"),
        "provider": record.get("provider") or record.get("cloud"),
        "confidence_ratio": safe_float(record.get("confidence_ratio"), 0.84 if feed.get("measurement_mode") == "direct" else 0.68),
        "freshness_sec": max(5, safe_int(record.get("freshness_sec"), 15 if feed.get("measurement_mode") == "direct" else 26)),
        "raw_payload_ref": str(record.get("raw_payload_ref") or f"cloud://{region.lower().replace('->', '/')}/{index}"),
        "raw_payload_redacted": True,
        "payload_kind": str(record.get("payload_kind") or ("feed" if feed.get("measurement_mode") == "direct" else "scaffold")),
        "provenance": str(record.get("provenance") or feed.get("provenance") or "runtime_scaffold"),
    }


def _normalize_direct_records(records: list[dict[str, Any]], *, feed: dict[str, Any], mode: str, captured_at: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_events: list[dict[str, Any]] = []
    normalized_events: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        base = _record_base(record, feed=feed, mode=mode, captured_at=captured_at, index=index)
        metrics: list[tuple[str, float]] = []
        if record.get("metric_name") is not None:
            metrics.append((str(record.get("metric_name")), safe_float(record.get("metric_value"))))
        else:
            for metric_name in METRIC_ALIASES:
                value = _metric_value(record, metric_name, fallback=float("nan"))
                if value == value:
                    metrics.append((metric_name, value))
        for metric_name, value in metrics:
            event = {**base, "metric_name": metric_name, "metric_value": value, "event_type": str(record.get("event_type") or "control_plane_metric")}
            raw_events.append(event)
            normalized_events.append({**event, "event_kind": "control_plane_signal"})
    return raw_events, normalized_events


def _scaffold_records(snapshot: dict[str, Any], *, feed: dict[str, Any], mode: str, captured_at: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_events: list[dict[str, Any]] = []
    for flow in (snapshot.get("flows") or [])[:16]:
        flow_id = str(flow.get("id") or "flow")
        seed = _seed(flow_id)
        record = {
            "origin": flow.get("origin"),
            "destination": flow.get("destination"),
            "country": flow.get("destination"),
            "region": f"{flow.get('origin')}->{flow.get('destination')}",
            "confidence_ratio": round(min(0.93, 0.48 + float(flow.get("traffic_share") or 0.0) * 0.31), 2),
            "freshness_sec": 20 + (seed % 12),
            "region_health_score": round(max(0.18, 1.0 - float(flow.get("congestion_index") or 0.0) / 140.0), 3),
            "egress_saturation_ratio": round(min(1.0, 0.18 + float(flow.get("throughput_gbps") or 0.0) / 1250.0), 3),
            "dns_error_ratio": round(min(1.0, 0.05 + float(flow.get("attack_index") or 0.0) / 180.0 + (seed % 4) * 0.012), 3),
            "control_plane_incident_score": round(min(1.0, 0.08 + float(flow.get("attack_index") or 0.0) / 165.0), 3),
            "api_error_ratio": round(min(1.0, 0.04 + float(flow.get("packet_loss_pct") or 0.0) / 30.0), 3),
        }
        base = _record_base(record, feed={**feed, "stage": "scaffold", "measurement_mode": "synthetic", "provenance": "phase4_scaffold", "source_name": "cloud_scaffold_runtime"}, mode=mode, captured_at=captured_at, index=seed)
        for metric_name in METRIC_ALIASES:
            raw_events.append({**base, "metric_name": metric_name, "metric_value": _metric_value(record, metric_name), "event_type": "control_plane_metric"})
    normalized_events = [{**event, "event_kind": "control_plane_signal"} for event in raw_events]
    return raw_events, normalized_events


def _build_health(normalized_events: list[dict[str, Any]], *, feed: dict[str, Any], captured_at: str, refresh: bool) -> dict[str, Any]:
    confidence = sum(float(item.get("confidence_ratio") or 0.0) for item in normalized_events) / max(len(normalized_events), 1)
    freshness = min((int(item.get("freshness_sec") or 999) for item in normalized_events), default=999)
    measurement_mode = str(feed.get("measurement_mode") or "synthetic")
    if not normalized_events:
        status = "limited"
    elif measurement_mode == "direct" and freshness <= 90 and len(normalized_events) >= 12:
        status = "healthy"
    elif len(normalized_events) >= 6:
        status = "degraded"
    else:
        status = "limited"
    return {
        "source_family": "cloud_metrics",
        "source": "Cloud metrics",
        "source_name": str(feed.get("source_name") or "cloud_region_feed"),
        "stage": str(feed.get("stage") or "scaffold"),
        "measurement_mode": measurement_mode,
        "feed_origin": str(feed.get("feed_origin") or "none"),
        "status": status,
        "records": len(normalized_events),
        "coverage_ratio": round(min(1.0, 0.4 + (len(normalized_events) / 54.0)), 2) if normalized_events else 0.0,
        "confidence_ratio": round(min(0.98, 0.35 + confidence * 0.64), 2) if normalized_events else 0.0,
        "freshness_sec": freshness,
        "updated_at": captured_at,
        "detail": str(feed.get("detail") or ("Configured cloud-region feed is active with egress, DNS, and control-plane metrics." if measurement_mode == "direct" else "Direct cloud-region telemetry is unavailable; synthetic control-plane metrics remain active.")),
        "advisory": "Use control-plane and DNS impairment signals to corroborate backbone incidents.",
        "errors": list(feed.get("errors") or []),
        "provenance": str(feed.get("provenance") or "runtime_scaffold"),
        "cache_hit": bool(feed.get("cache_hit") or feed.get("served_from_cache")),
        "refresh_requested": bool(refresh),
        "rate_limited": bool(feed.get("rate_limited")),
        "auth_mode": str(feed.get("auth_mode") or "none"),
        "request_attempts": int(feed.get("request_attempts") or 0),
    }


def collect_cloud_region_health_events(snapshot: dict[str, Any], *, mode: str = "online", refresh: bool = True) -> dict[str, Any]:
    feed = load_feed_records(
        family="cloud_metrics",
        default_path=FIXTURE_PATH,
        env_prefix="INTERNET_MAP_CLOUD_FEED",
        default_source_name="cloud_region_feed",
        refresh=refresh,
    )
    captured_at = str(feed.get("captured_at"))
    if feed.get("records"):
        raw_events, normalized_events = _normalize_direct_records(list(feed.get("records") or []), feed=feed, mode=mode, captured_at=captured_at)
    else:
        raw_events, normalized_events = _scaffold_records(snapshot, feed=feed, mode=mode, captured_at=captured_at)
    return {
        "source_family": "cloud_metrics",
        "raw_events": raw_events,
        "normalized_events": normalized_events,
        "source_health": _build_health(normalized_events, feed=feed, captured_at=captured_at, refresh=refresh),
    }
