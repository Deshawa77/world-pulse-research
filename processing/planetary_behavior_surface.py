from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from backend.planetary_behavior import BEHAVIOR_SUBSYSTEM


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


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _country(row: dict[str, Any]) -> str | None:
    geography = row.get("geography") if isinstance(row.get("geography"), dict) else {}
    value = str(geography.get("country") or row.get("country") or "").strip().upper()
    return value or None


def build_behavior_replay_frames(
    *,
    normalized_signals: list[dict[str, Any]],
    source_events: list[dict[str, Any]],
    limit: int = 16,
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for signal in normalized_signals:
        country = _country(signal) or "GLOBAL"
        stamp = _parse_iso(signal.get("timestamp") or signal.get("generated_at"))
        if not stamp:
            continue
        key = f"{country}:{stamp.strftime('%Y-%m-%dT%H')}"
        bucket = buckets.setdefault(
            key,
            {
                "frame_id": f"behavior_replay:{key}",
                "frame_timestamp": stamp.replace(minute=0, second=0, microsecond=0).isoformat(),
                "country": country,
                "signal_count": 0,
                "severity_total": 0.0,
                "confidence_total": 0.0,
                "source_families": Counter(),
                "signal_types": Counter(),
            },
        )
        bucket["signal_count"] += 1
        bucket["severity_total"] += _ratio(signal.get("severity_score"), 0.0)
        bucket["confidence_total"] += _ratio(signal.get("confidence_ratio"), 0.0)
        bucket["source_families"][str(signal.get("source_family") or "unknown")] += 1
        bucket["signal_types"][str(signal.get("signal_type") or "unknown")] += 1

    for event in source_events:
        country = _country(event) or "GLOBAL"
        stamp = _parse_iso(event.get("timestamp") or event.get("ingested_at"))
        if not stamp:
            continue
        key = f"{country}:{stamp.strftime('%Y-%m-%dT%H')}"
        bucket = buckets.setdefault(
            key,
            {
                "frame_id": f"behavior_replay:{key}",
                "frame_timestamp": stamp.replace(minute=0, second=0, microsecond=0).isoformat(),
                "country": country,
                "signal_count": 0,
                "severity_total": 0.0,
                "confidence_total": 0.0,
                "source_families": Counter(),
                "signal_types": Counter(),
            },
        )
        bucket["source_families"][str(event.get("source_family") or "unknown")] += 1

    frames: list[dict[str, Any]] = []
    for bucket in buckets.values():
        signal_count = int(bucket.get("signal_count") or 0)
        avg_severity = round((bucket["severity_total"] / signal_count), 4) if signal_count else 0.0
        avg_confidence = round((bucket["confidence_total"] / signal_count), 4) if signal_count else 0.0
        frames.append(
            {
                "frame_id": bucket["frame_id"],
                "frame_timestamp": bucket["frame_timestamp"],
                "country": bucket["country"],
                "signal_count": signal_count,
                "severity_score": avg_severity,
                "confidence_ratio": avg_confidence,
                "source_families": dict(bucket["source_families"].most_common(5)),
                "signal_types": dict(bucket["signal_types"].most_common(5)),
            }
        )
    frames.sort(key=lambda row: (str(row.get("frame_timestamp") or ""), _safe_float(row.get("severity_score"), 0.0)), reverse=True)
    return frames[: max(1, int(limit))]


def build_behavior_operator_surface(
    behavior_bundle: dict[str, Any],
    *,
    normalized_signals: list[dict[str, Any]],
    source_events: list[dict[str, Any]],
    limit: int = 12,
) -> dict[str, Any]:
    country_snapshots = [row for row in (behavior_bundle.get("country_snapshots") or []) if isinstance(row, dict)]
    global_snapshot = dict(behavior_bundle.get("global_behavior_snapshot") or {})

    ranked_countries = sorted(
        country_snapshots,
        key=lambda row: (
            _safe_float(row.get("display_risk"), _safe_float(row.get("raw_risk_score"), 0.0)),
            _ratio(row.get("confidence_ratio"), 0.0),
        ),
        reverse=True,
    )
    top_countries = ranked_countries[: max(1, int(limit))]

    signal_by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_family_counts: Counter[str] = Counter()
    signal_type_counts: Counter[str] = Counter()
    for row in normalized_signals:
        country = _country(row) or "GLOBAL"
        signal_by_country[country].append(row)
        source_family_counts[str(row.get("source_family") or "unknown")] += 1
        signal_type_counts[str(row.get("signal_type") or "unknown")] += 1

    source_event_family_counts: Counter[str] = Counter()
    for row in source_events:
        source_event_family_counts[str(row.get("source_family") or "unknown")] += 1

    narrative_watch = sorted(
        normalized_signals,
        key=lambda row: (
            _ratio(row.get("severity_score"), 0.0),
            _ratio(row.get("confidence_ratio"), 0.0),
        ),
        reverse=True,
    )[: max(1, int(limit))]

    geography_heat = []
    for country, rows in signal_by_country.items():
        if country == "GLOBAL":
            continue
        avg_severity = sum(_ratio(item.get("severity_score"), 0.0) for item in rows) / max(len(rows), 1)
        avg_confidence = sum(_ratio(item.get("confidence_ratio"), 0.0) for item in rows) / max(len(rows), 1)
        geography_heat.append(
            {
                "country": country,
                "signal_count": len(rows),
                "avg_severity": round(avg_severity, 4),
                "avg_confidence": round(avg_confidence, 4),
            }
        )
    geography_heat.sort(key=lambda row: (row["avg_severity"], row["signal_count"]), reverse=True)

    return {
        "contract_version": "phase-0.6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "subsystem": BEHAVIOR_SUBSYSTEM,
        "global_behavior_snapshot": global_snapshot,
        "country_count": len(country_snapshots),
        "top_countries": top_countries,
        "narrative_watch": narrative_watch,
        "replay_frames": build_behavior_replay_frames(normalized_signals=normalized_signals, source_events=source_events, limit=max(8, limit)),
        "source_health": {
            "normalized_signal_families": dict(source_family_counts.most_common(8)),
            "source_event_families": dict(source_event_family_counts.most_common(8)),
            "signal_types": dict(signal_type_counts.most_common(8)),
        },
        "regional_heat": geography_heat[: max(1, int(limit))],
    }
