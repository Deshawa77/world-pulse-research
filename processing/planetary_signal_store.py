from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database.mongo import db

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_ROOT = ROOT / "data_lake" / "planetary_intelligence"
SOURCE_EVENT_ROOT = PLATFORM_ROOT / "source_events"
SOURCE_EVENT_HISTORY_DIR = SOURCE_EVENT_ROOT / "history"
SOURCE_EVENT_LATEST_JSONL = SOURCE_EVENT_ROOT / "latest.jsonl"
NORMALIZED_SIGNAL_ROOT = PLATFORM_ROOT / "normalized_signals"
NORMALIZED_SIGNAL_HISTORY_DIR = NORMALIZED_SIGNAL_ROOT / "history"
NORMALIZED_SIGNAL_LATEST_JSONL = NORMALIZED_SIGNAL_ROOT / "latest.jsonl"
MANIFEST_ROOT = PLATFORM_ROOT / "manifests"
MANIFEST_HISTORY_DIR = MANIFEST_ROOT / "history"
MANIFEST_LATEST_JSON = MANIFEST_ROOT / "latest.json"

PLATFORM_SOURCE_EVENTS_COLLECTION = "platform_source_events"
PLATFORM_NORMALIZED_SIGNALS_COLLECTION = "platform_normalized_signals"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    _ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=_json_default, ensure_ascii=True))
            handle.write("\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if isinstance(payload, dict):
                rows.append(payload)
    except Exception:
        return []
    return rows


def _resolve_root(root: str | Path | None = None) -> Path:
    return Path(root) if root is not None else PLATFORM_ROOT


def _paths(root: str | Path | None = None) -> dict[str, Path]:
    base = _resolve_root(root)
    return {
        "source_latest": base / "source_events" / "latest.jsonl",
        "source_history": base / "source_events" / "history",
        "signal_latest": base / "normalized_signals" / "latest.jsonl",
        "signal_history": base / "normalized_signals" / "history",
        "manifest_latest": base / "manifests" / "latest.json",
        "manifest_history": base / "manifests" / "history",
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if numeric == numeric else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _ratio(value: Any, default: float = 0.0) -> float:
    numeric = _safe_float(value, default)
    if numeric > 1.0:
        numeric = numeric / 100.0 if numeric <= 100.0 else default
    return _clamp(numeric, 0.0, 1.0)


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    return "".join(char for char in text if char.isalnum() or char in {"-", "_", ":"}) or "unknown"


def _file_slug(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    return "".join(char for char in text if char.isalnum() or char in {"-", "_"}) or "run"


def _event_id(prefix: str, source_family: str, source_name: str, metric_name: str, timestamp: str, geography_key: str, index: int) -> str:
    return ":".join(
        [
            prefix,
            _slug(source_family),
            _slug(source_name),
            _slug(metric_name),
            _slug(geography_key),
            _slug(timestamp),
            str(index),
        ]
    )


def _normalize_country(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text or text in {"GLB", "GLOBAL", "WORLD", "ALL"}:
        return None
    return text


def _geography(
    *,
    country: Any = None,
    origin: Any = None,
    destination: Any = None,
    region: Any = None,
    lat: Any = None,
    lon: Any = None,
    scope: str | None = None,
) -> dict[str, Any]:
    country_code = _normalize_country(country)
    origin_code = _normalize_country(origin)
    destination_code = _normalize_country(destination)
    resolved_scope = scope or ("corridor" if origin_code and destination_code else "country" if country_code else "global")
    return {
        "scope": resolved_scope,
        "country": country_code,
        "origin": origin_code,
        "destination": destination_code,
        "region": str(region or "").strip() or None,
        "lat": _optional_float(lat),
        "lon": _optional_float(lon),
    }


def _geography_key(geography: dict[str, Any]) -> str:
    if geography.get("country"):
        return str(geography.get("country"))
    if geography.get("region"):
        return str(geography.get("region"))
    if geography.get("origin") or geography.get("destination"):
        return f"{geography.get('origin') or 'na'}-{geography.get('destination') or 'na'}"
    return str(geography.get("scope") or "global")


def _entity_refs(*values: Any) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        refs.append(text)
    return refs


def _severity_from_metric(metric_name: str, metric_value: Any, fallback: float = 0.0) -> float:
    name = str(metric_name or "").lower()
    value = _safe_float(metric_value, fallback)
    if any(token in name for token in ("risk", "score", "ratio", "confidence")):
        return round(_ratio(value, fallback), 4)
    if "latency" in name:
        return round(_clamp(value / 400.0), 4)
    if "packet_loss" in name:
        return round(_clamp(value / 10.0), 4)
    if "throughput" in name:
        return round(_clamp(value / 1000.0), 4)
    if "count" in name or "updates" in name or "announcements" in name:
        return round(_clamp(value / 100.0), 4)
    if abs(value) <= 1.0:
        return round(_clamp(abs(value)), 4)
    if abs(value) <= 100.0:
        return round(_clamp(abs(value) / 100.0), 4)
    return round(_clamp(abs(value) / 1000.0), 4)


def map_internet_raw_events_to_source_events(
    raw_events: list[dict[str, Any]],
    *,
    run_id: str,
    captured_at: str,
    mode: str = "online",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw_events):
        if not isinstance(item, dict):
            continue
        geography = _geography(
            country=item.get("country"),
            origin=item.get("origin"),
            destination=item.get("destination"),
            region=item.get("region"),
            scope="corridor" if item.get("origin") and item.get("destination") else None,
        )
        source_family = str(item.get("source_family") or "internet_telemetry")
        source_name = str(item.get("source_name") or source_family)
        metric_name = str(item.get("metric_name") or item.get("event_type") or "metric")
        timestamp = str(item.get("timestamp") or captured_at)
        event_id = str(
            item.get("event_id")
            or _event_id(
                "source-event",
                source_family,
                source_name,
                metric_name,
                timestamp,
                _geography_key(geography),
                index,
            )
        )
        rows.append(
            {
                "event_id": event_id,
                "timestamp": timestamp,
                "ingested_at": captured_at,
                "source_family": source_family,
                "source_name": source_name,
                "source_provenance": {
                    "subsystem": "real_time_internet_map",
                    "run_id": run_id,
                    "mode": mode,
                    "stage": item.get("stage"),
                    "measurement_mode": item.get("measurement_mode"),
                    "feed_origin": item.get("feed_origin"),
                    "provenance": item.get("provenance"),
                },
                "geography": geography,
                "raw_payload_ref": str(item.get("raw_payload_ref") or f"internet://{_slug(source_family)}/{_slug(_geography_key(geography))}/{index}"),
                "freshness_sec": max(0, _safe_int(item.get("freshness_sec"), 0)),
                "licensing_or_usage_tier": "provider_or_authenticated" if str(item.get("measurement_mode") or "").lower() == "direct" else "scaffold_or_cached",
                "metric_name": metric_name,
                "metric_value": _safe_float(item.get("metric_value"), 0.0),
                "event_type": str(item.get("event_type") or "metric"),
                "scope": "internet_map",
                "subsystem": "real_time_internet_map",
                "run_id": run_id,
                "mode": mode,
                "raw_payload_redacted": bool(item.get("raw_payload_redacted", True)),
            }
        )
    return rows


def map_internet_normalized_events_to_normalized_signals(
    normalized_events: list[dict[str, Any]],
    *,
    run_id: str,
    captured_at: str,
    mode: str = "online",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(normalized_events):
        if not isinstance(item, dict):
            continue
        geography = _geography(
            country=item.get("country"),
            origin=item.get("origin"),
            destination=item.get("destination"),
            region=item.get("region"),
            scope="corridor" if item.get("origin") and item.get("destination") else None,
        )
        source_family = str(item.get("source_family") or "internet_telemetry")
        source_name = str(item.get("source_name") or source_family)
        metric_name = str(item.get("metric_name") or item.get("event_kind") or item.get("event_type") or "metric")
        timestamp = str(item.get("timestamp") or captured_at)
        signal_id = str(
            item.get("signal_id")
            or _event_id(
                "normalized-signal",
                source_family,
                source_name,
                metric_name,
                timestamp,
                _geography_key(geography),
                index,
            )
        )
        rows.append(
            {
                "signal_id": signal_id,
                "timestamp": timestamp,
                "generated_at": captured_at,
                "signal_type": str(item.get("event_kind") or item.get("event_type") or "internet_signal"),
                "source_family": source_family,
                "source_name": source_name,
                "geography": geography,
                "entity_refs": _entity_refs(item.get("country"), item.get("origin"), item.get("destination"), item.get("region")),
                "metric_name": metric_name,
                "metric_value": _safe_float(item.get("metric_value"), 0.0),
                "severity_score": _severity_from_metric(metric_name, item.get("metric_value"), fallback=_ratio(item.get("confidence_ratio"), 0.0)),
                "confidence_ratio": round(_ratio(item.get("confidence_ratio"), 0.0), 4),
                "freshness_sec": max(0, _safe_int(item.get("freshness_sec"), 0)),
                "provenance_refs": [
                    {
                        "subsystem": "real_time_internet_map",
                        "run_id": run_id,
                        "mode": mode,
                        "stage": item.get("stage"),
                        "measurement_mode": item.get("measurement_mode"),
                        "provenance": item.get("provenance"),
                    }
                ],
                "event_type": str(item.get("event_type") or "metric"),
                "scope": "internet_map",
                "subsystem": "real_time_internet_map",
                "run_id": run_id,
                "mode": mode,
            }
        )
    return rows


def map_disaster_records_to_source_events(
    records: list[dict[str, Any]],
    *,
    run_id: str,
    captured_at: str,
    mode: str = "online",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            continue
        source_family = str(((item.get("signal_sources") or [None])[0]) or "disaster_signal")
        source_name = str(item.get("source") or source_family)
        timestamp = str(item.get("timestamp") or captured_at)
        geography = _geography(
            country=item.get("country"),
            lat=item.get("lat"),
            lon=item.get("lon"),
            scope=None,
        )
        event_id = str(
            item.get("event_id")
            or item.get("record_id")
            or _event_id(
                "source-event",
                source_family,
                source_name,
                str(item.get("event_type") or "hazard"),
                timestamp,
                _geography_key(geography),
                index,
            )
        )
        rows.append(
            {
                "event_id": event_id,
                "timestamp": timestamp,
                "ingested_at": captured_at,
                "source_family": source_family,
                "source_name": source_name,
                "source_provenance": {
                    "subsystem": "global_disaster_early_warning_ai",
                    "run_id": run_id,
                    "mode": mode,
                    "signal_sources": list(item.get("signal_sources") or []),
                    "top_contributing_signals": list(item.get("top_contributing_signals") or []),
                },
                "geography": geography,
                "raw_payload_ref": f"disaster://raw/{_slug(source_name)}/{_slug(event_id)}",
                "freshness_sec": max(0, _safe_int(item.get("freshness_sec"), 0)),
                "licensing_or_usage_tier": "public_or_open_source",
                "event_type": str(item.get("event_type") or "hazard_observation"),
                "severity_proxy": round(_safe_float(item.get("severity_proxy"), 0.0), 4),
                "scope": "disaster_early_warning",
                "subsystem": "global_disaster_early_warning_ai",
                "run_id": run_id,
                "mode": mode,
            }
        )
    return rows


def map_disaster_records_to_normalized_signals(
    records: list[dict[str, Any]],
    *,
    run_id: str,
    captured_at: str,
    mode: str = "online",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            continue
        source_family = str(((item.get("signal_sources") or [None])[0]) or "disaster_signal")
        source_name = str(item.get("source") or source_family)
        timestamp = str(item.get("timestamp") or captured_at)
        geography = _geography(
            country=item.get("country"),
            lat=item.get("lat"),
            lon=item.get("lon"),
            scope=None,
        )
        metric_value = _safe_float(item.get("severity_proxy"), 0.0)
        signal_id = str(
            item.get("signal_id")
            or item.get("record_id")
            or _event_id(
                "normalized-signal",
                source_family,
                source_name,
                str(item.get("event_type") or "hazard_signal"),
                timestamp,
                _geography_key(geography),
                index,
            )
        )
        rows.append(
            {
                "signal_id": signal_id,
                "timestamp": timestamp,
                "generated_at": captured_at,
                "signal_type": str(item.get("event_type") or "hazard_signal"),
                "source_family": source_family,
                "source_name": source_name,
                "geography": geography,
                "entity_refs": _entity_refs(item.get("country"), item.get("event_type"), item.get("source")),
                "metric_name": "severity_proxy",
                "metric_value": round(metric_value, 4),
                "severity_score": round(_clamp(metric_value), 4),
                "confidence_ratio": round(_ratio(item.get("confidence"), 0.0), 4),
                "freshness_sec": max(0, _safe_int(item.get("freshness_sec"), 0)),
                "provenance_refs": [
                    {
                        "subsystem": "global_disaster_early_warning_ai",
                        "run_id": run_id,
                        "mode": mode,
                        "signal_sources": list(item.get("signal_sources") or []),
                        "top_contributing_signals": list(item.get("top_contributing_signals") or []),
                    }
                ],
                "scope": "disaster_early_warning",
                "subsystem": "global_disaster_early_warning_ai",
                "run_id": run_id,
                "mode": mode,
            }
        )
    return rows


BEHAVIOR_SOURCE_SUBSYSTEM = "global_human_behavior_intelligence_engine"

BEHAVIOR_METRIC_SPECS: list[dict[str, str]] = [
    {"field": "raw_risk_score", "source_family": "country_behavior_snapshot", "signal_type": "behavior_risk"},
    {"field": "direct_behavior_score", "source_family": "country_behavior_model", "signal_type": "behavior_direct"},
    {"field": "contextual_pressure_score", "source_family": "country_behavior_model", "signal_type": "behavior_contextual_pressure"},
    {"field": "coordination_risk_score", "source_family": "country_behavior_model", "signal_type": "coordination_pressure"},
    {"field": "social_unrest_score", "source_family": "attention_signals", "signal_type": "social_unrest"},
    {"field": "google_trends_pressure", "source_family": "attention_signals", "signal_type": "search_attention"},
    {"field": "public_attention_score", "source_family": "attention_signals", "signal_type": "public_attention"},
    {"field": "narrative_velocity_score", "source_family": "attention_signals", "signal_type": "narrative_velocity"},
    {"field": "mobility_disruption_score", "source_family": "mobility_and_logistics", "signal_type": "mobility_disruption"},
    {"field": "aviation_disruption_score", "source_family": "mobility_and_logistics", "signal_type": "aviation_disruption"},
    {"field": "logistics_stress_score", "source_family": "mobility_and_logistics", "signal_type": "logistics_stress"},
    {"field": "household_stress_score", "source_family": "economic_behavior", "signal_type": "household_stress"},
    {"field": "fuel_price_pressure", "source_family": "economic_behavior", "signal_type": "fuel_price_pressure"},
    {"field": "food_price_pressure", "source_family": "economic_behavior", "signal_type": "food_price_pressure"},
    {"field": "labor_stress_score", "source_family": "economic_behavior", "signal_type": "labor_stress"},
    {"field": "fx_pressure_score", "source_family": "economic_behavior", "signal_type": "fx_pressure"},
    {"field": "remittance_stress_score", "source_family": "economic_behavior", "signal_type": "remittance_stress"},
    {"field": "energy_stress_score", "source_family": "economic_behavior", "signal_type": "energy_stress"},
    {"field": "weather_stress", "source_family": "weather_context", "signal_type": "weather_stress"},
]

GLOBAL_BEHAVIOR_METRIC_SPECS: list[dict[str, str]] = [
    {"field": "global_risk_score", "signal_type": "global_behavior_risk"},
    {"field": "global_mood_score", "signal_type": "global_mood"},
    {"field": "global_mood_confidence", "signal_type": "global_mood_confidence"},
    {"field": "global_behavior_index", "signal_type": "global_behavior_index"},
    {"field": "global_context_index", "signal_type": "global_context_index"},
    {"field": "global_attention_index", "signal_type": "global_attention_index"},
    {"field": "global_disruption_index", "signal_type": "global_disruption_index"},
    {"field": "global_economic_stress_index", "signal_type": "global_economic_stress_index"},
]


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _freshness_from_timestamp(timestamp: Any, captured_at: str) -> int:
    reference = _parse_timestamp(timestamp)
    captured = _parse_timestamp(captured_at) or datetime.now(timezone.utc)
    if not reference:
        return 0
    return max(0, int((captured - reference).total_seconds()))


def _behavior_confidence_ratio(row: dict[str, Any]) -> float:
    source_count = _safe_int(row.get("source_count"), 0)
    source_support = _clamp(source_count / 10.0)
    return round(
        max(
            _ratio(row.get("confidence_score"), 0.0),
            _ratio(row.get("evidence_quality_score"), 0.0),
            round(source_support * 0.42, 4),
        ),
        4,
    )


def _behavior_entity_refs(row: dict[str, Any]) -> list[str]:
    spillovers = row.get("spillover_links") if isinstance(row.get("spillover_links"), list) else []
    return _entity_refs(
        row.get("country"),
        *[str(item.get("country") or "") for item in spillovers if isinstance(item, dict)],
    )


def map_country_rows_to_source_events(
    country_rows: list[dict[str, Any]],
    *,
    run_id: str,
    captured_at: str,
    mode: str = "online",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(country_rows):
        if not isinstance(row, dict):
            continue
        country = str(row.get("country") or "").strip().upper()
        if not country:
            continue
        geography = _geography(country=country, scope="country")
        timestamp = str(row.get("feature_timestamp") or row.get("timestamp") or captured_at)
        freshness_sec = _freshness_from_timestamp(timestamp, captured_at)
        confidence_ratio = _behavior_confidence_ratio(row)
        for metric_index, spec in enumerate(BEHAVIOR_METRIC_SPECS):
            field = spec["field"]
            value = row.get(field)
            if field == "raw_risk_score" and value is None:
                value = row.get("risk") if row.get("risk") is not None else row.get("display_risk")
            if value is None:
                continue
            numeric = _safe_float(value, 0.0)
            event_id = _event_id(
                "source-event",
                spec["source_family"],
                field,
                field,
                timestamp,
                f"{country}:{field}",
                row_index * 100 + metric_index,
            )
            rows.append(
                {
                    "event_id": event_id,
                    "timestamp": timestamp,
                    "ingested_at": captured_at,
                    "source_family": spec["source_family"],
                    "source_name": field,
                    "source_provenance": {
                        "subsystem": BEHAVIOR_SOURCE_SUBSYSTEM,
                        "run_id": run_id,
                        "mode": mode,
                        "source_status": row.get("source_status"),
                        "validated_today": bool(row.get("validated_today")),
                        "data_quality": row.get("data_quality"),
                        "source_count": _safe_int(row.get("source_count"), 0),
                        "risk_band": row.get("risk_band"),
                        "confidence_band": row.get("confidence_band"),
                        "gating_action": row.get("gating_action"),
                        "external_sources": list(row.get("external_sources") or []),
                        "spillover_links": list(row.get("spillover_links") or []),
                    },
                    "geography": geography,
                    "raw_payload_ref": f"behavior://country/{_slug(country)}/{_slug(field)}/{_slug(timestamp)}",
                    "freshness_sec": freshness_sec,
                    "licensing_or_usage_tier": "derived_internal_platform",
                    "metric_name": field,
                    "metric_value": round(numeric, 4),
                    "event_type": "behavior_metric",
                    "scope": "human_behavior",
                    "subsystem": BEHAVIOR_SOURCE_SUBSYSTEM,
                    "run_id": run_id,
                    "mode": mode,
                    "confidence_ratio": confidence_ratio,
                }
            )
    return rows


def map_country_rows_to_normalized_signals(
    country_rows: list[dict[str, Any]],
    *,
    run_id: str,
    captured_at: str,
    mode: str = "online",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(country_rows):
        if not isinstance(row, dict):
            continue
        country = str(row.get("country") or "").strip().upper()
        if not country:
            continue
        geography = _geography(country=country, scope="country")
        timestamp = str(row.get("feature_timestamp") or row.get("timestamp") or captured_at)
        freshness_sec = _freshness_from_timestamp(timestamp, captured_at)
        confidence_ratio = _behavior_confidence_ratio(row)
        entity_refs = _behavior_entity_refs(row)
        for metric_index, spec in enumerate(BEHAVIOR_METRIC_SPECS):
            field = spec["field"]
            value = row.get(field)
            if field == "raw_risk_score" and value is None:
                value = row.get("risk") if row.get("risk") is not None else row.get("display_risk")
            if value is None:
                continue
            numeric = _safe_float(value, 0.0)
            signal_id = _event_id(
                "normalized-signal",
                spec["source_family"],
                field,
                field,
                timestamp,
                f"{country}:{field}",
                row_index * 100 + metric_index,
            )
            rows.append(
                {
                    "signal_id": signal_id,
                    "timestamp": timestamp,
                    "generated_at": captured_at,
                    "signal_type": spec["signal_type"],
                    "source_family": spec["source_family"],
                    "source_name": field,
                    "geography": geography,
                    "entity_refs": entity_refs,
                    "metric_name": field,
                    "metric_value": round(numeric, 4),
                    "severity_score": _severity_from_metric(field, numeric, fallback=confidence_ratio),
                    "confidence_ratio": confidence_ratio,
                    "freshness_sec": freshness_sec,
                    "provenance_refs": [
                        {
                            "subsystem": BEHAVIOR_SOURCE_SUBSYSTEM,
                            "run_id": run_id,
                            "mode": mode,
                            "source_status": row.get("source_status"),
                            "validated_today": bool(row.get("validated_today")),
                            "data_quality": row.get("data_quality"),
                            "risk_band": row.get("risk_band"),
                            "confidence_band": row.get("confidence_band"),
                            "gating_action": row.get("gating_action"),
                        }
                    ],
                    "scope": "human_behavior",
                    "subsystem": BEHAVIOR_SOURCE_SUBSYSTEM,
                    "run_id": run_id,
                    "mode": mode,
                }
            )
    return rows


def _global_behavior_confidence(global_doc: dict[str, Any] | None, global_context: dict[str, Any] | None) -> float:
    features = (global_doc or {}).get("features") if isinstance((global_doc or {}).get("features"), dict) else {}
    freshness = (global_context or {}).get("freshness") if isinstance((global_context or {}).get("freshness"), dict) else {}
    newest_age_hours = _safe_float(freshness.get("newest_age_hours"), 24.0)
    freshness_ratio = _clamp(1.0 - min(newest_age_hours / 24.0, 1.0))
    return round(max(_ratio(features.get("global_mood_confidence"), 0.0), round(freshness_ratio * 0.6, 4)), 4)


def map_global_behavior_to_source_events(
    global_doc: dict[str, Any] | None,
    global_context: dict[str, Any] | None,
    *,
    run_id: str,
    captured_at: str,
    mode: str = "online",
) -> list[dict[str, Any]]:
    features = (global_doc or {}).get("features") if isinstance((global_doc or {}).get("features"), dict) else {}
    if not features:
        return []
    confidence_ratio = _global_behavior_confidence(global_doc, global_context)
    timestamp = str((global_doc or {}).get("timestamp") or features.get("timestamp") or captured_at)
    freshness_sec = _freshness_from_timestamp(timestamp, captured_at)
    rows: list[dict[str, Any]] = []
    for index, spec in enumerate(GLOBAL_BEHAVIOR_METRIC_SPECS):
        field = spec["field"]
        if features.get(field) is None:
            continue
        numeric = _safe_float(features.get(field), 0.0)
        rows.append(
            {
                "event_id": _event_id("source-event", "global_behavior_aggregate", field, field, timestamp, "global", index),
                "timestamp": timestamp,
                "ingested_at": captured_at,
                "source_family": "global_behavior_aggregate",
                "source_name": field,
                "source_provenance": {
                    "subsystem": BEHAVIOR_SOURCE_SUBSYSTEM,
                    "run_id": run_id,
                    "mode": mode,
                    "quality_gate": (global_context or {}).get("quality_gate"),
                    "freshness": (global_context or {}).get("freshness"),
                    "source_health": (global_context or {}).get("source_health"),
                },
                "geography": {"scope": "global"},
                "raw_payload_ref": f"behavior://global/{_slug(field)}/{_slug(timestamp)}",
                "freshness_sec": freshness_sec,
                "licensing_or_usage_tier": "derived_internal_platform",
                "metric_name": field,
                "metric_value": round(numeric, 4),
                "event_type": "global_behavior_metric",
                "scope": "human_behavior",
                "subsystem": BEHAVIOR_SOURCE_SUBSYSTEM,
                "run_id": run_id,
                "mode": mode,
                "confidence_ratio": confidence_ratio,
            }
        )
    return rows


def map_global_behavior_to_normalized_signals(
    global_doc: dict[str, Any] | None,
    global_context: dict[str, Any] | None,
    *,
    run_id: str,
    captured_at: str,
    mode: str = "online",
) -> list[dict[str, Any]]:
    features = (global_doc or {}).get("features") if isinstance((global_doc or {}).get("features"), dict) else {}
    if not features:
        return []
    confidence_ratio = _global_behavior_confidence(global_doc, global_context)
    timestamp = str((global_doc or {}).get("timestamp") or features.get("timestamp") or captured_at)
    freshness_sec = _freshness_from_timestamp(timestamp, captured_at)
    rows: list[dict[str, Any]] = []
    for index, spec in enumerate(GLOBAL_BEHAVIOR_METRIC_SPECS):
        field = spec["field"]
        if features.get(field) is None:
            continue
        numeric = _safe_float(features.get(field), 0.0)
        rows.append(
            {
                "signal_id": _event_id("normalized-signal", "global_behavior_aggregate", field, field, timestamp, "global", index),
                "timestamp": timestamp,
                "generated_at": captured_at,
                "signal_type": spec["signal_type"],
                "source_family": "global_behavior_aggregate",
                "source_name": field,
                "geography": {"scope": "global"},
                "entity_refs": ["global"],
                "metric_name": field,
                "metric_value": round(numeric, 4),
                "severity_score": _severity_from_metric(field, numeric, fallback=confidence_ratio),
                "confidence_ratio": confidence_ratio,
                "freshness_sec": freshness_sec,
                "provenance_refs": [
                    {
                        "subsystem": BEHAVIOR_SOURCE_SUBSYSTEM,
                        "run_id": run_id,
                        "mode": mode,
                        "quality_gate": (global_context or {}).get("quality_gate"),
                        "source_health": (global_context or {}).get("source_health"),
                    }
                ],
                "scope": "human_behavior",
                "subsystem": BEHAVIOR_SOURCE_SUBSYSTEM,
                "run_id": run_id,
                "mode": mode,
            }
        )
    return rows


def _insert_many(collection_name: str, docs: list[dict[str, Any]]) -> int:
    if not docs:
        return 0
    try:
        result = db[collection_name].insert_many(docs, ordered=False)
        return len(result.inserted_ids)
    except Exception:
        return 0


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return {name: counts[name] for name in sorted(counts.keys())}


def persist_platform_signal_batch(
    *,
    source_events: list[dict[str, Any]],
    normalized_signals: list[dict[str, Any]],
    subsystem: str,
    run_id: str,
    captured_at: str,
    mode: str = "online",
    root: str | Path | None = None,
    persist_db: bool = True,
) -> dict[str, Any]:
    paths = _paths(root)
    source_rows = [row for row in source_events if isinstance(row, dict)]
    signal_rows = [row for row in normalized_signals if isinstance(row, dict)]
    safe_run_id = _file_slug(run_id)
    safe_subsystem = _file_slug(subsystem)

    source_history_path = paths["source_history"] / f"{safe_subsystem}_{safe_run_id}.jsonl"
    signal_history_path = paths["signal_history"] / f"{safe_subsystem}_{safe_run_id}.jsonl"
    manifest_history_path = paths["manifest_history"] / f"{safe_subsystem}_{safe_run_id}.json"

    _write_jsonl(paths["source_latest"], source_rows)
    _write_jsonl(source_history_path, source_rows)
    _write_jsonl(paths["signal_latest"], signal_rows)
    _write_jsonl(signal_history_path, signal_rows)

    inserted_source_events = _insert_many(PLATFORM_SOURCE_EVENTS_COLLECTION, source_rows) if persist_db else 0
    inserted_normalized_signals = _insert_many(PLATFORM_NORMALIZED_SIGNALS_COLLECTION, signal_rows) if persist_db else 0

    manifest = {
        "captured_at": captured_at or _iso_now(),
        "run_id": run_id,
        "subsystem": subsystem,
        "mode": mode,
        "platform_scope": "planetary_intelligence",
        "contract_version": "phase-0.2",
        "contract_families": ["source_event", "normalized_signal"],
        "source_event_count": len(source_rows),
        "normalized_signal_count": len(signal_rows),
        "source_families": _counts(source_rows + signal_rows, "source_family"),
        "signal_types": _counts(signal_rows, "signal_type"),
        "source_event_latest_path": str(paths["source_latest"]),
        "source_event_history_path": str(source_history_path),
        "normalized_signal_latest_path": str(paths["signal_latest"]),
        "normalized_signal_history_path": str(signal_history_path),
        "mongo_inserted": {
            "source_events": inserted_source_events,
            "normalized_signals": inserted_normalized_signals,
        },
    }
    _write_json(paths["manifest_latest"], manifest)
    _write_json(manifest_history_path, manifest)

    return {
        "status": "ok",
        **manifest,
        "manifest_latest_path": str(paths["manifest_latest"]),
        "manifest_history_path": str(manifest_history_path),
    }


def _timestamp_sort_key(row: dict[str, Any]) -> float:
    raw = str(row.get("ingested_at") or row.get("generated_at") or row.get("timestamp") or "")
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _dedupe_rows(rows: list[dict[str, Any]], id_key: str) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        marker = str(row.get(id_key) or "").strip() or json.dumps(row, sort_keys=True, default=_json_default)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(row)
    return unique


def _source_event_subsystem(row: dict[str, Any]) -> str:
    if str(row.get("subsystem") or "").strip():
        return str(row.get("subsystem") or "")
    provenance = row.get("source_provenance") if isinstance(row.get("source_provenance"), dict) else {}
    return str(provenance.get("subsystem") or "")


def _normalized_signal_subsystem(row: dict[str, Any]) -> str:
    if str(row.get("subsystem") or "").strip():
        return str(row.get("subsystem") or "")
    provenance_refs = row.get("provenance_refs") if isinstance(row.get("provenance_refs"), list) else []
    first = provenance_refs[0] if provenance_refs and isinstance(provenance_refs[0], dict) else {}
    return str(first.get("subsystem") or "")


def _matches_source_event(row: dict[str, Any], *, source_family: str | None, subsystem: str | None, event_type: str | None) -> bool:
    if source_family and str(row.get("source_family") or "").strip().lower() != str(source_family).strip().lower():
        return False
    if subsystem and _source_event_subsystem(row).strip().lower() != str(subsystem).strip().lower():
        return False
    if event_type and str(row.get("event_type") or "").strip().lower() != str(event_type).strip().lower():
        return False
    return True


def _matches_normalized_signal(row: dict[str, Any], *, source_family: str | None, subsystem: str | None, signal_type: str | None) -> bool:
    if source_family and str(row.get("source_family") or "").strip().lower() != str(source_family).strip().lower():
        return False
    if subsystem and _normalized_signal_subsystem(row).strip().lower() != str(subsystem).strip().lower():
        return False
    if signal_type and str(row.get("signal_type") or "").strip().lower() != str(signal_type).strip().lower():
        return False
    return True


def _load_rows_from_files(latest_path: Path, history_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if history_dir.exists():
        history_paths = sorted(history_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
        target_rows = max(200, int(limit) * 4)
        for path in history_paths:
            rows.extend(_read_jsonl(path))
            if len(rows) >= target_rows:
                break
    if not rows:
        rows.extend(_read_jsonl(latest_path))
    return rows


def _load_rows_from_mongo(collection_name: str, *, limit: int) -> list[dict[str, Any]]:
    try:
        cursor = db[collection_name].find({}, {"_id": 0}).sort("_id", -1).limit(max(200, int(limit) * 4))
        return [row for row in cursor if isinstance(row, dict)]
    except Exception:
        return []


def load_recent_platform_source_events(
    *,
    limit: int = 120,
    root: str | Path | None = None,
    source_family: str | None = None,
    subsystem: str | None = None,
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    paths = _paths(root)
    rows = _load_rows_from_files(paths["source_latest"], paths["source_history"], limit=limit)
    if not rows and root is None:
        rows = _load_rows_from_mongo(PLATFORM_SOURCE_EVENTS_COLLECTION, limit=limit)
    filtered = [
        row
        for row in rows
        if _matches_source_event(row, source_family=source_family, subsystem=subsystem, event_type=event_type)
    ]
    filtered.sort(key=_timestamp_sort_key, reverse=True)
    return _dedupe_rows(filtered, "event_id")[: max(1, int(limit))]


def load_recent_platform_normalized_signals(
    *,
    limit: int = 120,
    root: str | Path | None = None,
    source_family: str | None = None,
    subsystem: str | None = None,
    signal_type: str | None = None,
) -> list[dict[str, Any]]:
    paths = _paths(root)
    rows = _load_rows_from_files(paths["signal_latest"], paths["signal_history"], limit=limit)
    if not rows and root is None:
        rows = _load_rows_from_mongo(PLATFORM_NORMALIZED_SIGNALS_COLLECTION, limit=limit)
    filtered = [
        row
        for row in rows
        if _matches_normalized_signal(row, source_family=source_family, subsystem=subsystem, signal_type=signal_type)
    ]
    filtered.sort(key=_timestamp_sort_key, reverse=True)
    return _dedupe_rows(filtered, "signal_id")[: max(1, int(limit))]

