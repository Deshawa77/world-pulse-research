from __future__ import annotations

from pathlib import Path
from typing import Any

from collectors.internet_feed_utils import load_feed_records, normalize_code, normalize_region, safe_float, safe_int


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data_lake" / "internet_map" / "isp_telemetry.json"
METRIC_ALIASES = {
    "subscriber_availability_ratio": ("subscriber_availability_ratio", "availability_ratio"),
    "fixed_reachability_ratio": ("fixed_reachability_ratio", "fixed_ratio"),
    "mobile_reachability_ratio": ("mobile_reachability_ratio", "mobile_ratio"),
    "throughput_drop_pct": ("throughput_drop_pct",),
    "outage_report_count": ("outage_report_count", "outage_reports"),
    "subscribers_impacted_m": ("subscribers_impacted_m", "impacted_users_m"),
}


def _seed(value: str) -> int:
    return sum((index + 5) * ord(char) for index, char in enumerate(str(value or "").upper()))


def _metric_value(record: dict[str, Any], metric_name: str, fallback: float = 0.0) -> float:
    aliases = METRIC_ALIASES.get(metric_name, (metric_name,))
    for key in aliases:
        if key in record and record.get(key) is not None:
            return safe_float(record.get(key), fallback)
    return fallback


def _record_base(record: dict[str, Any], *, feed: dict[str, Any], mode: str, captured_at: str, index: int) -> dict[str, Any]:
    country = normalize_code(record.get("country"), "GLB")
    region = normalize_region(record.get("origin"), record.get("destination"), record.get("region"), country)
    return {
        "source_family": "isp_telemetry",
        "source_name": str(record.get("source_name") or feed.get("source_name") or "isp_reachability_feed"),
        "stage": str(record.get("stage") or feed.get("stage") or "scaffold"),
        "measurement_mode": str(record.get("measurement_mode") or feed.get("measurement_mode") or "synthetic"),
        "feed_origin": str(feed.get("feed_origin") or "none"),
        "mode": mode,
        "timestamp": str(record.get("timestamp") or captured_at),
        "country": country,
        "region": region,
        "provider": record.get("provider") or record.get("isp"),
        "confidence_ratio": safe_float(record.get("confidence_ratio"), 0.83 if feed.get("measurement_mode") == "direct" else 0.67),
        "freshness_sec": max(5, safe_int(record.get("freshness_sec"), 18 if feed.get("measurement_mode") == "direct" else 30)),
        "raw_payload_ref": str(record.get("raw_payload_ref") or f"isp://{country.lower()}/{index}"),
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
            event = {**base, "metric_name": metric_name, "metric_value": value, "event_type": str(record.get("event_type") or "reachability_metric")}
            raw_events.append(event)
            normalized_events.append({**event, "event_kind": "subscriber_signal"})
    return raw_events, normalized_events


def _scaffold_records(snapshot: dict[str, Any], *, feed: dict[str, Any], mode: str, captured_at: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_events: list[dict[str, Any]] = []
    for country in (snapshot.get("countries") or [])[:20]:
        code = str(country.get("country") or "GLB")
        seed = _seed(code)
        availability_ratio = round(max(0.22, 1.0 - float(country.get("shutdown_risk") or 0.0) / 145.0), 3)
        fixed_ratio = round(max(0.2, availability_ratio - 0.03 - (seed % 4) * 0.01), 3)
        mobile_ratio = round(max(0.18, availability_ratio - 0.05 - (seed % 5) * 0.012), 3)
        throughput_drop = round(min(100.0, float(country.get("congestion_index") or 0.0) * 0.92 + (seed % 9)), 2)
        outage_reports = float(8 + (seed % 26))
        impacted_users = round(max(0.4, float(country.get("packet_flow_gbps") or 0.0) * 0.03), 2)
        record = {
            "country": code,
            "region": code,
            "confidence_ratio": round(min(0.9, 0.44 + (float(country.get("freshness_ratio") or 0.0) * 0.26) + (float(country.get("evidence_quality_score") or 0.0) * 0.18)), 2),
            "freshness_sec": 26 + (seed % 14),
            "subscriber_availability_ratio": availability_ratio,
            "fixed_reachability_ratio": fixed_ratio,
            "mobile_reachability_ratio": mobile_ratio,
            "throughput_drop_pct": throughput_drop,
            "outage_report_count": outage_reports,
            "subscribers_impacted_m": impacted_users,
        }
        base = _record_base(record, feed={**feed, "stage": "scaffold", "measurement_mode": "synthetic", "provenance": "phase4_scaffold", "source_name": "isp_scaffold_runtime"}, mode=mode, captured_at=captured_at, index=seed)
        for metric_name in METRIC_ALIASES:
            raw_events.append({**base, "metric_name": metric_name, "metric_value": _metric_value(record, metric_name), "event_type": "reachability_metric"})
    normalized_events = [{**event, "event_kind": "subscriber_signal"} for event in raw_events]
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
        "source_family": "isp_telemetry",
        "source": "ISP telemetry",
        "source_name": str(feed.get("source_name") or "isp_reachability_feed"),
        "stage": str(feed.get("stage") or "scaffold"),
        "measurement_mode": measurement_mode,
        "feed_origin": str(feed.get("feed_origin") or "none"),
        "status": status,
        "records": len(normalized_events),
        "coverage_ratio": round(min(1.0, 0.34 + (len(normalized_events) / 60.0)), 2) if normalized_events else 0.0,
        "confidence_ratio": round(min(0.97, 0.34 + confidence * 0.64), 2) if normalized_events else 0.0,
        "freshness_sec": freshness,
        "updated_at": captured_at,
        "detail": str(feed.get("detail") or ("Configured ISP feed is active with fixed/mobile reachability and subscriber impact metrics." if measurement_mode == "direct" else "Direct ISP telemetry is unavailable; synthetic reachability estimates remain active.")),
        "advisory": "Prefer fixed/mobile corroboration before escalating shutdown alerts.",
        "errors": list(feed.get("errors") or []),
        "provenance": str(feed.get("provenance") or "runtime_scaffold"),
        "cache_hit": bool(feed.get("cache_hit") or feed.get("served_from_cache")),
        "refresh_requested": bool(refresh),
        "rate_limited": bool(feed.get("rate_limited")),
        "auth_mode": str(feed.get("auth_mode") or "none"),
        "request_attempts": int(feed.get("request_attempts") or 0),
    }


def collect_isp_telemetry_events(snapshot: dict[str, Any], *, mode: str = "online", refresh: bool = True) -> dict[str, Any]:
    feed = load_feed_records(
        family="isp_telemetry",
        default_path=FIXTURE_PATH,
        env_prefix="INTERNET_MAP_ISP_FEED",
        default_source_name="isp_reachability_feed",
        refresh=refresh,
    )
    captured_at = str(feed.get("captured_at"))
    if feed.get("records"):
        raw_events, normalized_events = _normalize_direct_records(list(feed.get("records") or []), feed=feed, mode=mode, captured_at=captured_at)
    else:
        raw_events, normalized_events = _scaffold_records(snapshot, feed=feed, mode=mode, captured_at=captured_at)
    return {
        "source_family": "isp_telemetry",
        "raw_events": raw_events,
        "normalized_events": normalized_events,
        "source_health": _build_health(normalized_events, feed=feed, captured_at=captured_at, refresh=refresh),
    }
