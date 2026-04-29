from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


DISASTER_SOURCE_COMPONENTS: dict[str, list[str]] = {
    "satellite_imagery": ["firms", "disaster_family_satellite_imagery"],
    "seismic_data": ["usgs", "disaster_family_seismic_data"],
    "weather_sensors": ["weather", "openweathermap", "disaster_family_weather_sensors"],
    "ocean_sensors": ["noaa_cdo", "eonet", "disaster_family_ocean_sensors"],
    "social_media_signals": ["reddit", "telegram_public", "youtube_public", "youtube_trends", "disaster_family_social_media_signals"],
}

DISASTER_ALERT_THRESHOLDS: dict[str, dict[str, Any]] = {
    "earthquake": {"min_activity": 0.43, "priority_bands": {"active", "critical"}},
    "wildfire": {"min_activity": 0.46, "priority_bands": {"active", "critical"}},
    "flood": {"min_activity": 0.44, "priority_bands": {"active", "critical"}},
    "cyclone": {"min_activity": 0.45, "priority_bands": {"active", "critical"}},
}

ACTION_STATUS_PRIORITY = {
    "new": 0,
    "acknowledged": 1,
    "snoozed": 2,
    "escalated": 3,
    "feedback": 4,
}


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _band_rank(value: Any) -> int:
    band = str(value or "guarded").strip().lower()
    order = {"critical": 3, "active": 2, "monitor": 1, "guarded": 0}
    return order.get(band, 0)


def _status_from_activity(status: str, freshness_minutes: float | None) -> str:
    if status == "down":
        return "down"
    if freshness_minutes is None:
        return "degraded"
    if freshness_minutes > 720:
        return "stale"
    if freshness_minutes > 240:
        return "degraded"
    return "up"


def build_disaster_source_health_snapshot(source_health_collection) -> list[dict[str, Any]]:
    requested_sources = sorted({source for sources in DISASTER_SOURCE_COMPONENTS.values() for source in sources})
    docs = list(source_health_collection.find({"source": {"$in": requested_sources}}, {"_id": 0}))
    doc_map = {str(doc.get("source") or ""): doc for doc in docs}
    now_utc = datetime.now(timezone.utc)
    snapshots: list[dict[str, Any]] = []

    for family, components in DISASTER_SOURCE_COMPONENTS.items():
        family_doc = doc_map.get(f"disaster_family_{family}")
        component_docs = [doc_map[source] for source in components if source in doc_map and not str(source).startswith("disaster_family_")]
        latest_candidates = []
        for doc in ([family_doc] if family_doc else []) + component_docs:
            stamp = _parse_dt(doc.get("last_success") or doc.get("updated_at") or doc.get("last_checked"))
            if stamp:
                latest_candidates.append(stamp)
        latest_success = max(latest_candidates, default=None)
        freshness_minutes = round((now_utc - latest_success).total_seconds() / 60.0, 2) if latest_success else None
        base_status = str((family_doc or {}).get("status") or ("up" if component_docs else "down")).lower()
        status = _status_from_activity(base_status, freshness_minutes)
        records = int((family_doc or {}).get("records") or sum(int(doc.get("records") or 0) for doc in component_docs))
        rate_limited = any(bool(doc.get("rate_limited")) for doc in component_docs if isinstance(doc, dict))
        auth_failed = any(bool(doc.get("auth_failed")) for doc in component_docs if isinstance(doc, dict))
        errors = [str(doc.get("error") or "").strip() for doc in component_docs if str(doc.get("error") or "").strip()]
        if family_doc and str(family_doc.get("error") or "").strip():
            errors.insert(0, str(family_doc.get("error") or "").strip())

        advisory = "Fresh live source family" if status == "up" else "Limited source coverage" if status == "degraded" else "Source family stale or unavailable"
        snapshots.append(
            {
                "source_family": family,
                "status": status,
                "records": records,
                "last_success": latest_success.isoformat() if latest_success else None,
                "freshness_minutes": freshness_minutes,
                "component_sources": [source for source in components if not source.startswith("disaster_family_")],
                "rate_limited": rate_limited,
                "auth_failed": auth_failed,
                "advisory": advisory,
                "errors": errors[:3],
            }
        )
    return snapshots


def load_disaster_alert_ops_state(operator_events_collection, *, hours: int = 168) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(hours, 1))).isoformat()
    docs = list(
        operator_events_collection.find(
            {
                "alert_scope": "disaster_hotspot",
                "timestamp": {"$gte": cutoff},
            },
            {"_id": 0},
        ).sort("timestamp", 1)
    )

    state: dict[str, dict[str, Any]] = {}
    summary = {
        "acknowledged": 0,
        "snoozed_active": 0,
        "escalated": 0,
        "false_positive_flags": 0,
        "total_actions": len(docs),
    }
    now_utc = datetime.now(timezone.utc)

    for doc in docs:
        hazard = str(doc.get("hazard") or "").strip().lower()
        region = str(doc.get("region") or "").strip()
        if not hazard or not region:
            continue
        key = f"{hazard}:{region}"
        current = state.setdefault(
            key,
            {
                "status": "new",
                "action_counts": {"acknowledge": 0, "snooze": 0, "escalate": 0, "false_positive": 0},
                "false_positive_count": 0,
                "last_action": None,
                "last_timestamp": None,
                "owner": None,
                "comment": None,
                "snoozed_until": None,
            },
        )
        action = str(doc.get("action") or "").strip().lower()
        current["last_action"] = action
        current["last_timestamp"] = doc.get("timestamp")
        current["owner"] = doc.get("owner")
        current["comment"] = doc.get("comment")
        if action in current["action_counts"]:
            current["action_counts"][action] += 1
        if action == "acknowledge":
            current["status"] = "acknowledged"
        elif action == "snooze":
            current["status"] = "snoozed"
            current["snoozed_until"] = doc.get("snoozed_until")
        elif action == "escalate":
            current["status"] = "escalated"
        elif action == "false_positive":
            current["status"] = "feedback"
            current["false_positive_count"] += 1

    for current in state.values():
        snoozed_until = _parse_dt(current.get("snoozed_until"))
        if current.get("status") == "snoozed" and snoozed_until and snoozed_until <= now_utc:
            current["status"] = "acknowledged" if current["action_counts"].get("acknowledge") else "new"
        summary["acknowledged"] += 1 if current.get("status") == "acknowledged" else 0
        summary["snoozed_active"] += 1 if current.get("status") == "snoozed" else 0
        summary["escalated"] += 1 if current.get("status") == "escalated" else 0
        summary["false_positive_flags"] += int(current.get("false_positive_count") or 0)
    return state, summary


def enrich_disaster_payload_with_ops(
    payload: dict[str, Any],
    *,
    source_health_collection,
    operator_events_collection,
) -> dict[str, Any]:
    queue_groups = (payload or {}).get("alert_queue") or {}
    hotspot_groups = (payload or {}).get("regional_hotspots") or {}
    now_utc = datetime.now(timezone.utc)
    source_health = build_disaster_source_health_snapshot(source_health_collection)
    ops_state, ops_summary = load_disaster_alert_ops_state(operator_events_collection)

    hotspot_lookup: dict[str, dict[str, Any]] = {}
    for hazard, hotspots in hotspot_groups.items():
        for hotspot in hotspots or []:
            region = str(hotspot.get("region") or "").strip()
            if region:
                hotspot_lookup[f"{hazard}:{region}"] = hotspot

    suppressed_by_snooze = 0
    enriched_groups: dict[str, list[dict[str, Any]]] = {}
    for hazard, items in queue_groups.items():
        hazard_key = str(hazard or "").strip().lower()
        threshold_cfg = DISASTER_ALERT_THRESHOLDS.get(hazard_key, {"min_activity": 0.45, "priority_bands": {"active", "critical"}})
        seen: set[str] = set()
        next_items: list[dict[str, Any]] = []
        for item in items or []:
            region = str(item.get("region") or "").strip()
            if not region:
                continue
            dedupe_key = f"{hazard_key}:{region}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            hotspot = hotspot_lookup.get(dedupe_key) or {}
            priority_band = str(item.get("priority_band") or hotspot.get("hotspot_band") or "guarded").lower()
            activity = float(item.get("activity") or hotspot.get("activity_score") or hotspot.get("hotspot_score") or 0.0)
            signal_sources = sorted({str(source) for source in ((item.get("signal_sources") or []) + (hotspot.get("signal_sources") or [])) if source})
            explainers = list(dict.fromkeys([str(signal) for signal in ((item.get("signals") or []) + (item.get("top_contributing_signals") or []) + (hotspot.get("top_contributing_signals") or [])) if signal]))[:6]
            threshold_met = bool(priority_band in threshold_cfg["priority_bands"] or activity >= float(threshold_cfg["min_activity"]))
            if not threshold_met:
                continue

            current_state = ops_state.get(dedupe_key, {"status": "new", "action_counts": {}, "false_positive_count": 0})
            snoozed_until = _parse_dt(current_state.get("snoozed_until"))
            is_snoozed = bool(snoozed_until and snoozed_until > now_utc)
            false_positive_count = int(current_state.get("false_positive_count") or 0)
            feedback_adjustment = min(false_positive_count * 0.04, 0.16)
            adjusted_activity = max(0.0, activity - feedback_adjustment)
            if is_snoozed and _band_rank(priority_band) < _band_rank("critical"):
                suppressed_by_snooze += 1
                continue

            threshold_reason = f"{priority_band} band or activity >= {float(threshold_cfg['min_activity']):.2f}"
            next_items.append(
                {
                    **item,
                    "hazard": hazard_key,
                    "display_label": item.get("display_label") or hotspot.get("display_label"),
                    "signal_sources": signal_sources,
                    "top_contributing_signals": explainers,
                    "recommended_action": item.get("recommended_action") or hotspot.get("recommended_action"),
                    "alert_id": f"alert:{dedupe_key}",
                    "dedupe_key": dedupe_key,
                    "threshold_met": threshold_met,
                    "threshold_reason": threshold_reason,
                    "feedback_adjustment": round(feedback_adjustment, 3),
                    "adjusted_activity": round(adjusted_activity, 3),
                    "ops_state": {
                        **current_state,
                        "is_snoozed": is_snoozed,
                        "snoozed_until": snoozed_until.isoformat() if snoozed_until else None,
                    },
                }
            )

        next_items.sort(
            key=lambda row: (
                _band_rank(row.get("priority_band")),
                ACTION_STATUS_PRIORITY.get(str(((row.get("ops_state") or {}).get("status") or "new")).lower(), 0),
                float(row.get("adjusted_activity") or row.get("activity") or 0.0),
            ),
            reverse=True,
        )
        enriched_groups[hazard_key] = next_items

    payload["alert_queue"] = enriched_groups
    payload["source_health"] = source_health
    payload["alert_ops_summary"] = {
        **ops_summary,
        "suppressed_by_snooze": suppressed_by_snooze,
        "active_queue_count": sum(len(items) for items in enriched_groups.values()),
    }
    return payload


def build_disaster_alert_operation_doc(payload: dict[str, Any], *, actor: str, timestamp: str | None = None) -> dict[str, Any]:
    hazard = str(payload.get("hazard") or "").strip().lower()
    region = str(payload.get("region") or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    base_timestamp = timestamp or _iso_now()
    snooze_hours = max(int(payload.get("snooze_hours") or 6), 1) if action == "snooze" else None
    snoozed_until = None
    if snooze_hours:
        snoozed_until = (datetime.now(timezone.utc) + timedelta(hours=snooze_hours)).isoformat()
    return {
        "alert_scope": "disaster_hotspot",
        "hazard": hazard,
        "region": region,
        "country": str(payload.get("country") or "GLB").upper(),
        "action": action,
        "owner": payload.get("owner") or actor,
        "comment": payload.get("comment") or "",
        "alert_id": payload.get("alert_id") or f"alert:{hazard}:{region}",
        "dedupe_key": payload.get("dedupe_key") or f"{hazard}:{region}",
        "false_positive_reason": payload.get("false_positive_reason"),
        "snooze_hours": snooze_hours,
        "snoozed_until": snoozed_until,
        "timestamp": base_timestamp,
    }
