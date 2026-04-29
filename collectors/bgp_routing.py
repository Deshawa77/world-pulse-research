from __future__ import annotations

from pathlib import Path
from typing import Any

from collectors.internet_feed_utils import load_feed_records, normalize_code, normalize_region, safe_float, safe_int


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data_lake" / "internet_map" / "bgp_routing.json"
METRIC_ALIASES = {
    "route_update_count": ("route_update_count", "updates", "update_count"),
    "announcement_count": ("announcement_count", "announcements"),
    "withdrawn_prefix_count": ("withdrawn_prefix_count", "withdrawals", "withdrawn"),
    "as_path_churn_score": ("as_path_churn_score", "path_churn_score"),
    "reroute_factor": ("reroute_factor", "reroute_pressure"),
    "hijack_suspect_score": ("hijack_suspect_score", "hijack_score"),
    "monitored_prefix_count": ("monitored_prefix_count", "prefix_count"),
}


def _seed(value: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(str(value or "").upper()))


def _metric_value(record: dict[str, Any], metric_name: str, fallback: float = 0.0) -> float:
    aliases = METRIC_ALIASES.get(metric_name, (metric_name,))
    for key in aliases:
        if key in record and record.get(key) is not None:
            return safe_float(record.get(key), fallback)
    return fallback


def _record_base(record: dict[str, Any], *, feed: dict[str, Any], mode: str, captured_at: str, index: int) -> dict[str, Any]:
    origin = normalize_code(record.get("origin") or record.get("source_country") or record.get("country"))
    destination = normalize_code(record.get("destination") or record.get("target_country"))
    country = normalize_code(record.get("country") or origin or destination, "GLB")
    region = normalize_region(origin, destination, record.get("region"), country)
    asn_value = record.get("asn")
    try:
        asn_value = int(asn_value) if asn_value is not None else None
    except (TypeError, ValueError):
        asn_value = None
    return {
        "source_family": "bgp_routing",
        "source_name": str(record.get("source_name") or feed.get("source_name") or "bgp_route_feed"),
        "stage": str(record.get("stage") or feed.get("stage") or "scaffold"),
        "measurement_mode": str(record.get("measurement_mode") or feed.get("measurement_mode") or "synthetic"),
        "feed_origin": str(feed.get("feed_origin") or "none"),
        "mode": mode,
        "timestamp": str(record.get("timestamp") or captured_at),
        "country": country,
        "origin": origin or country,
        "destination": destination or None,
        "region": region,
        "asn": asn_value,
        "prefix": record.get("prefix") or record.get("prefix_cidr"),
        "confidence_ratio": safe_float(record.get("confidence_ratio"), 0.84 if feed.get("measurement_mode") == "direct" else 0.66),
        "freshness_sec": max(5, safe_int(record.get("freshness_sec"), 16 if feed.get("measurement_mode") == "direct" else 30)),
        "raw_payload_ref": str(record.get("raw_payload_ref") or f"bgp://{region.lower().replace('->', '/')}/{index}"),
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
            event = {**base, "metric_name": metric_name, "metric_value": value, "event_type": str(record.get("event_type") or "routing_update")}
            raw_events.append(event)
            normalized_events.append({**event, "event_kind": "routing_signal"})
    return raw_events, normalized_events


def _scaffold_records(snapshot: dict[str, Any], *, feed: dict[str, Any], mode: str, captured_at: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_events: list[dict[str, Any]] = []
    for flow in (snapshot.get("flows") or [])[:16]:
        flow_id = str(flow.get("id") or "flow")
        seed = _seed(flow_id)
        route_updates = 10 + (seed % 34)
        announcements = max(4, route_updates - (seed % 6))
        withdrawn_prefixes = 1 + (seed % 7)
        churn_score = round(min(1.0, 0.18 + float(flow.get("congestion_index") or 0.0) / 140.0), 3)
        reroute_factor = round(max(1.02, float(flow.get("reroute_factor") or 1.0) + (seed % 4) * 0.03), 2)
        hijack_score = round(min(1.0, 0.12 + float(flow.get("attack_index") or 0.0) / 130.0), 3)
        monitored_prefixes = 4600 + (seed % 4200)
        record = {
            "origin": flow.get("origin"),
            "destination": flow.get("destination"),
            "country": flow.get("origin"),
            "region": f"{flow.get('origin')}->{flow.get('destination')}",
            "confidence_ratio": round(min(0.9, 0.5 + float(flow.get("traffic_share") or 0.0) * 0.32), 2),
            "freshness_sec": 26 + (seed % 12),
            "asn": int(64512 + (seed % 1024)),
            "prefix": f"203.0.{seed % 255}.0/24",
            "route_update_count": float(route_updates),
            "announcement_count": float(announcements),
            "withdrawn_prefix_count": float(withdrawn_prefixes),
            "as_path_churn_score": float(churn_score),
            "reroute_factor": float(reroute_factor),
            "hijack_suspect_score": float(hijack_score),
            "monitored_prefix_count": float(monitored_prefixes),
        }
        base = _record_base(record, feed={**feed, "stage": "scaffold", "measurement_mode": "synthetic", "provenance": "phase2_scaffold", "source_name": "bgp_scaffold_runtime"}, mode=mode, captured_at=captured_at, index=seed)
        for metric_name in METRIC_ALIASES:
            raw_events.append({**base, "metric_name": metric_name, "metric_value": _metric_value(record, metric_name), "event_type": "routing_signal"})
    normalized_events = [{**event, "event_kind": "routing_signal"} for event in raw_events]
    return raw_events, normalized_events


def _build_health(normalized_events: list[dict[str, Any]], *, feed: dict[str, Any], captured_at: str, refresh: bool) -> dict[str, Any]:
    confidence = sum(float(item.get("confidence_ratio") or 0.0) for item in normalized_events) / max(len(normalized_events), 1)
    freshness = min((int(item.get("freshness_sec") or 999) for item in normalized_events), default=999)
    measurement_mode = str(feed.get("measurement_mode") or "synthetic")
    if not normalized_events:
        status = "limited"
    elif measurement_mode == "direct" and freshness <= 90 and len(normalized_events) >= 10:
        status = "healthy"
    elif len(normalized_events) >= 6:
        status = "degraded"
    else:
        status = "limited"
    return {
        "source_family": "bgp_routing",
        "source": "BGP routing",
        "source_name": str(feed.get("source_name") or "bgp_route_feed"),
        "stage": str(feed.get("stage") or "scaffold"),
        "measurement_mode": measurement_mode,
        "feed_origin": str(feed.get("feed_origin") or "none"),
        "status": status,
        "records": len(normalized_events),
        "coverage_ratio": round(min(1.0, 0.38 + (len(normalized_events) / 48.0)), 2) if normalized_events else 0.0,
        "confidence_ratio": round(min(0.98, 0.34 + confidence * 0.64), 2) if normalized_events else 0.0,
        "freshness_sec": freshness,
        "updated_at": captured_at,
        "detail": str(feed.get("detail") or ("Configured BGP route feed is active with direct AS-path and prefix metrics." if measurement_mode == "direct" else "Direct BGP route feed is unavailable; synthetic routing scaffold remains active.")),
        "advisory": "Prefer route updates, withdrawals, and hijack heuristics when direct feeds are present.",
        "errors": list(feed.get("errors") or []),
        "provenance": str(feed.get("provenance") or "runtime_scaffold"),
        "cache_hit": bool(feed.get("cache_hit") or feed.get("served_from_cache")),
        "refresh_requested": bool(refresh),
        "rate_limited": bool(feed.get("rate_limited")),
        "auth_mode": str(feed.get("auth_mode") or "none"),
        "request_attempts": int(feed.get("request_attempts") or 0),
    }


def collect_bgp_routing_events(snapshot: dict[str, Any], *, mode: str = "online", refresh: bool = True) -> dict[str, Any]:
    feed = load_feed_records(
        family="bgp_routing",
        default_path=FIXTURE_PATH,
        env_prefix="INTERNET_MAP_BGP_FEED",
        default_source_name="bgp_route_feed",
        refresh=refresh,
    )
    captured_at = str(feed.get("captured_at"))
    if feed.get("records"):
        raw_events, normalized_events = _normalize_direct_records(list(feed.get("records") or []), feed=feed, mode=mode, captured_at=captured_at)
    else:
        raw_events, normalized_events = _scaffold_records(snapshot, feed=feed, mode=mode, captured_at=captured_at)
    return {
        "source_family": "bgp_routing",
        "raw_events": raw_events,
        "normalized_events": normalized_events,
        "source_health": _build_health(normalized_events, feed=feed, captured_at=captured_at, refresh=refresh),
    }
