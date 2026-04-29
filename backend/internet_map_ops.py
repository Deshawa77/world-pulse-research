from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any


INTERNET_SOURCE_COMPONENTS: dict[str, list[str]] = {
    "bgp_routing": [],
    "cdn_traffic": [],
    "isp_telemetry": [],
    "cloud_metrics": [],
}

ACTION_STATUS_PRIORITY = {
    "new": 0,
    "acknowledged": 1,
    "assigned": 2,
    "snoozed": 3,
    "escalated": 4,
    "feedback": 5,
}

TEAM_QUEUE_BY_ALERT = {
    "attack": "network-security",
    "shutdown": "continuity-watch",
}

ESCALATION_DESTINATION_BY_ALERT = {
    "attack": "security-command",
    "shutdown": "regional-response-desk",
}

SLA_HOURS_BY_SEVERITY = {
    "critical": 1,
    "high": 2,
    "elevated": 4,
    "guarded": 8,
    "stable": 12,
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


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _status_from_activity(status: str, freshness_seconds: float | None) -> str:
    if status == "down":
        return "down"
    if freshness_seconds is None:
        return "degraded"
    if freshness_seconds > 600:
        return "stale"
    if freshness_seconds > 180:
        return "degraded"
    return "healthy"


def _default_team_queue(alert_type: str, severity: str | None = None) -> str:
    return TEAM_QUEUE_BY_ALERT.get(str(alert_type or "").strip().lower(), "global-ops")


def _default_escalation_destination(alert_type: str, severity: str | None = None) -> str:
    base = ESCALATION_DESTINATION_BY_ALERT.get(str(alert_type or "").strip().lower(), "operations-command")
    if str(severity or "").strip().lower() == "critical":
        return f"{base}-priority"
    return base


def _default_sla_hours(alert_type: str, severity: str | None = None) -> int:
    return int(SLA_HOURS_BY_SEVERITY.get(str(severity or "guarded").strip().lower(), 6))


def build_internet_source_health_snapshot(source_health_collection) -> list[dict[str, Any]]:
    docs = list(source_health_collection.find({"scope": "internet_map"}, {"_id": 0}))
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in docs:
        family = str(doc.get("source_family") or "").strip()
        if family in INTERNET_SOURCE_COMPONENTS:
            by_family[family].append(doc)

    now_utc = datetime.now(timezone.utc)
    snapshots: list[dict[str, Any]] = []
    for family in INTERNET_SOURCE_COMPONENTS:
        component_docs = by_family.get(family, [])
        latest_doc = None
        latest_dt = None
        for doc in component_docs:
            stamp = _parse_dt(doc.get("last_success") or doc.get("updated_at") or doc.get("last_checked"))
            if stamp and (latest_dt is None or stamp > latest_dt):
                latest_dt = stamp
                latest_doc = doc
        freshness_seconds = round((now_utc - latest_dt).total_seconds(), 2) if latest_dt else None
        base_status = str((latest_doc or {}).get("status") or ("healthy" if component_docs else "down")).lower()
        status = _status_from_activity(base_status, freshness_seconds)
        snapshots.append(
            {
                "source_family": family,
                "source": family.replace("_", " "),
                "source_name": (latest_doc or {}).get("source"),
                "stage": str((latest_doc or {}).get("stage") or ("direct-file" if component_docs else "derived")),
                "measurement_mode": str((latest_doc or {}).get("measurement_mode") or ("direct" if component_docs else "synthetic")),
                "feed_origin": str((latest_doc or {}).get("feed_origin") or ("file" if component_docs else "none")),
                "status": status,
                "records": int(sum(int(doc.get("records") or 0) for doc in component_docs)),
                "coverage_ratio": round(max((float(doc.get("coverage_ratio") or 0.0) for doc in component_docs), default=0.0), 2),
                "confidence_ratio": round(sum(float(doc.get("confidence_ratio") or 0.0) for doc in component_docs) / max(len(component_docs), 1), 2) if component_docs else 0.0,
                "last_success": latest_dt.isoformat() if latest_dt else None,
                "freshness_sec": freshness_seconds,
                "component_sources": sorted({str(doc.get("source") or "") for doc in component_docs if str(doc.get("source") or "").strip()}),
                "advisory": str((latest_doc or {}).get("advisory") or ("Fresh live source family" if status == "healthy" else "Limited source coverage")),
                "detail": str((latest_doc or {}).get("detail") or (latest_doc or {}).get("advisory") or ""),
                "errors": [str(doc.get("error") or "").strip() for doc in component_docs if str(doc.get("error") or "").strip()][:3],
                "provenance": str((latest_doc or {}).get("provenance") or ("runtime_scaffold" if not component_docs else "direct_feed")),
            }
        )
    return snapshots


def load_internet_alert_ops_state(operator_events_collection, *, hours: int = 168) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(hours, 1))).isoformat()
    docs = list(
        operator_events_collection.find(
            {
                "alert_scope": "internet_map",
                "timestamp": {"$gte": cutoff},
            },
            {"_id": 0},
        ).sort("timestamp", 1)
    )

    state: dict[str, dict[str, Any]] = {}
    summary = {
        "acknowledged": 0,
        "assigned": 0,
        "snoozed_active": 0,
        "escalated": 0,
        "false_positive_flags": 0,
        "total_actions": len(docs),
        "suppressed_by_snooze": 0,
        "active_queue_count": 0,
        "breached_sla_count": 0,
        "queue_breakdown": [],
        "escalation_breakdown": [],
    }
    queue_counter: Counter[str] = Counter()
    escalation_counter: Counter[str] = Counter()
    now_utc = datetime.now(timezone.utc)

    for doc in docs:
        key = str(doc.get("dedupe_key") or "").strip()
        if not key:
            continue
        current = state.setdefault(
            key,
            {
                "status": "new",
                "action_counts": {"acknowledge": 0, "assign": 0, "snooze": 0, "escalate": 0, "false_positive": 0},
                "false_positive_count": 0,
                "last_action": None,
                "last_timestamp": None,
                "owner": None,
                "comment": None,
                "snoozed_until": None,
                "assignee": None,
                "assignment_reason": None,
                "false_positive_reason": None,
                "team_queue": None,
                "escalation_destination": None,
                "escalation_level": 0,
                "sla_due_at": None,
                "sla_hours": None,
            },
        )
        action = str(doc.get("action") or "").strip().lower()
        current["last_action"] = action
        current["last_timestamp"] = doc.get("timestamp")
        current["owner"] = doc.get("owner")
        current["comment"] = doc.get("comment")
        if action in current["action_counts"]:
            current["action_counts"][action] += 1
        team_queue = str(doc.get("team_queue") or current.get("team_queue") or "").strip() or None
        escalation_destination = str(doc.get("escalation_destination") or current.get("escalation_destination") or "").strip() or None
        escalation_level = int(doc.get("escalation_level") or current.get("escalation_level") or 0)
        sla_due_at = doc.get("sla_due_at") or current.get("sla_due_at")
        sla_hours = int(doc.get("sla_hours") or current.get("sla_hours") or 0) or None
        if action == "acknowledge":
            current["status"] = "acknowledged"
        elif action == "assign":
            current["status"] = "assigned"
            current["assignee"] = doc.get("assignee") or doc.get("owner")
            current["assignment_reason"] = doc.get("assignment_reason")
        elif action == "snooze":
            current["status"] = "snoozed"
            current["snoozed_until"] = doc.get("snoozed_until")
        elif action == "escalate":
            current["status"] = "escalated"
        elif action == "false_positive":
            current["status"] = "feedback"
            current["false_positive_count"] += 1
            current["false_positive_reason"] = doc.get("false_positive_reason")
        current["team_queue"] = team_queue
        current["escalation_destination"] = escalation_destination
        current["escalation_level"] = escalation_level
        current["sla_due_at"] = sla_due_at
        current["sla_hours"] = sla_hours

    for current in state.values():
        snoozed_until = _parse_dt(current.get("snoozed_until"))
        if current.get("status") == "snoozed" and snoozed_until:
            if snoozed_until <= now_utc:
                if current["action_counts"].get("assign"):
                    current["status"] = "assigned"
                else:
                    current["status"] = "acknowledged" if current["action_counts"].get("acknowledge") else "new"
            else:
                summary["suppressed_by_snooze"] += 1
        sla_due_at = _parse_dt(current.get("sla_due_at"))
        current["sla_breached"] = bool(sla_due_at and now_utc > sla_due_at and current.get("status") not in {"feedback", "snoozed"})
        current["sla_remaining_sec"] = round((sla_due_at - now_utc).total_seconds(), 1) if sla_due_at else None
        summary["acknowledged"] += 1 if current.get("status") == "acknowledged" else 0
        summary["assigned"] += 1 if current.get("status") == "assigned" else 0
        summary["snoozed_active"] += 1 if current.get("status") == "snoozed" else 0
        summary["escalated"] += 1 if current.get("status") == "escalated" else 0
        summary["false_positive_flags"] += int(current.get("false_positive_count") or 0)
        summary["breached_sla_count"] += 1 if current.get("sla_breached") else 0
        if current.get("status") not in {"feedback", "new"}:
            summary["active_queue_count"] += 1
        if current.get("team_queue"):
            queue_counter[str(current.get("team_queue"))] += 1
        if current.get("escalation_destination"):
            escalation_counter[str(current.get("escalation_destination"))] += 1
    summary["queue_breakdown"] = [{"queue": queue, "count": count} for queue, count in queue_counter.most_common(8)]
    summary["escalation_breakdown"] = [{"destination": destination, "count": count} for destination, count in escalation_counter.most_common(8)]
    return state, summary


def build_internet_alert_operation_doc(payload: dict[str, Any], *, actor: str | None = None) -> dict[str, Any]:
    action = str(payload.get("action") or "").strip().lower()
    owner = str(actor or payload.get("owner") or "system").strip() or "system"
    now_utc = datetime.now(timezone.utc)
    snooze_hours = max(1, min(int(payload.get("snooze_hours") or 6), 72))
    alert_type = str(payload.get("alert_type") or "unknown").strip().lower()
    severity = str(payload.get("severity") or "guarded").strip().lower() or "guarded"
    dedupe_key = str(payload.get("dedupe_key") or "").strip()
    if not dedupe_key:
        country = str(payload.get("country") or "").strip().upper()
        flow_id = str(payload.get("flow_id") or "").strip().lower()
        if alert_type == "shutdown":
            dedupe_key = f"shutdown:{country or 'unknown'}"
        else:
            dedupe_key = f"attack:{flow_id or country or 'unknown'}"
    assignee = str(payload.get("assignee") or owner).strip() or owner
    team_queue = str(payload.get("team_queue") or _default_team_queue(alert_type, severity)).strip() or _default_team_queue(alert_type, severity)
    escalation_destination = str(payload.get("escalation_destination") or _default_escalation_destination(alert_type, severity)).strip() or _default_escalation_destination(alert_type, severity)
    escalation_level = max(0, min(int(payload.get("escalation_level") or (2 if action == "escalate" else 0)), 5))
    sla_hours = max(1, min(int(payload.get("sla_hours") or _default_sla_hours(alert_type, severity)), 72))
    return {
        "alert_scope": "internet_map",
        "alert_type": alert_type,
        "action": action,
        "owner": owner,
        "assignee": assignee if action == "assign" else None,
        "assignment_reason": str(payload.get("assignment_reason") or payload.get("comment") or "").strip() or None,
        "comment": str(payload.get("comment") or "").strip() or None,
        "country": str(payload.get("country") or "").strip().upper() or None,
        "flow_id": str(payload.get("flow_id") or "").strip() or None,
        "alert_id": str(payload.get("alert_id") or "").strip() or None,
        "dedupe_key": dedupe_key,
        "severity": severity,
        "team_queue": team_queue,
        "escalation_destination": escalation_destination if action in {"assign", "escalate"} else None,
        "escalation_level": escalation_level if action in {"assign", "escalate"} else 0,
        "snooze_hours": snooze_hours if action == "snooze" else None,
        "snoozed_until": (now_utc + timedelta(hours=snooze_hours)).isoformat() if action == "snooze" else None,
        "false_positive_reason": str(payload.get("false_positive_reason") or "").strip() or None,
        "sla_hours": sla_hours if action in {"acknowledge", "assign", "escalate"} else None,
        "sla_due_at": (now_utc + timedelta(hours=sla_hours)).isoformat() if action in {"acknowledge", "assign", "escalate"} else None,
        "timestamp": now_utc.isoformat(),
    }


def build_internet_alert_audit_report(operator_events_collection, *, hours: int = 168) -> dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(hours, 1))).isoformat()
    docs = list(
        operator_events_collection.find(
            {"alert_scope": "internet_map", "timestamp": {"$gte": cutoff}},
            {"_id": 0},
        ).sort("timestamp", -1)
    )
    by_owner: Counter[str] = Counter()
    by_action: Counter[str] = Counter()
    by_queue: Counter[str] = Counter()
    by_destination: Counter[str] = Counter()
    recent_actions: list[dict[str, Any]] = []
    for doc in docs:
        owner = str(doc.get("owner") or "system")
        action = str(doc.get("action") or "unknown")
        by_owner[owner] += 1
        by_action[action] += 1
        if doc.get("team_queue"):
            by_queue[str(doc.get("team_queue"))] += 1
        if doc.get("escalation_destination"):
            by_destination[str(doc.get("escalation_destination"))] += 1
        if len(recent_actions) < 10:
            recent_actions.append(
                {
                    "timestamp": doc.get("timestamp"),
                    "owner": owner,
                    "action": action,
                    "dedupe_key": doc.get("dedupe_key"),
                    "team_queue": doc.get("team_queue"),
                    "escalation_destination": doc.get("escalation_destination"),
                    "severity": doc.get("severity"),
                }
            )
    return {
        "audit_window_hours": int(max(hours, 1)),
        "total_actions": len(docs),
        "actions_by_type": [{"action": action, "count": count} for action, count in by_action.most_common()],
        "team_queues": [{"queue": queue, "count": count} for queue, count in by_queue.most_common(8)],
        "escalation_destinations": [{"destination": destination, "count": count} for destination, count in by_destination.most_common(8)],
        "top_operators": [{"owner": owner, "count": count} for owner, count in by_owner.most_common(8)],
        "recent_actions": recent_actions,
    }


def _enrich_alert(alert: dict[str, Any], alert_type: str, ops_state: dict[str, Any] | None) -> dict[str, Any]:
    item = dict(alert)
    severity = str(item.get("severity") or item.get("status") or "guarded").strip().lower() or "guarded"
    if not ops_state:
        sla_hours = _default_sla_hours(alert_type, severity)
        due_at = datetime.now(timezone.utc) + timedelta(hours=sla_hours)
        ops_state = {
            "status": "new",
            "false_positive_count": 0,
            "team_queue": _default_team_queue(alert_type, severity),
            "escalation_destination": _default_escalation_destination(alert_type, severity),
            "escalation_level": 0,
            "sla_hours": sla_hours,
            "sla_due_at": due_at.isoformat(),
            "sla_remaining_sec": round(sla_hours * 3600.0, 1),
            "sla_breached": False,
        }
    else:
        ops_state = dict(ops_state)
        ops_state.setdefault("team_queue", _default_team_queue(alert_type, severity))
        ops_state.setdefault("escalation_destination", _default_escalation_destination(alert_type, severity))
        ops_state.setdefault("sla_hours", _default_sla_hours(alert_type, severity))
    false_positive_count = int(ops_state.get("false_positive_count") or 0)
    confidence_penalty = min(0.36, false_positive_count * 0.12)
    confidence_bonus = 0.08 if ops_state.get("status") == "escalated" else 0.04 if ops_state.get("status") == "assigned" else 0.0
    item["confidence_ratio"] = round(_clamp(float(item.get("confidence_ratio") or 0.5) - confidence_penalty + confidence_bonus, 0.05, 0.99), 2)
    if false_positive_count >= 2 and ops_state.get("status") not in {"escalated", "assigned"}:
        item["status"] = "needs-review"
    item["ops_state"] = ops_state
    return item


def enrich_internet_payload_with_ops(payload: dict[str, Any], *, source_health_collection, operator_events_collection) -> dict[str, Any]:
    payload = dict(payload or {})
    if not isinstance(payload.get("source_health"), list) or not payload.get("source_health"):
        payload["source_health"] = build_internet_source_health_snapshot(source_health_collection)

    state_by_key, ops_summary = load_internet_alert_ops_state(operator_events_collection)
    attack_rows: list[dict[str, Any]] = []
    for item in payload.get("cyber_attacks") or []:
        flow_id = str(item.get("flow_id") or item.get("id") or "unknown").strip().lower()
        dedupe_key = str(item.get("dedupe_key") or f"attack:{flow_id}")
        row = dict(item)
        row["dedupe_key"] = dedupe_key
        attack_rows.append(_enrich_alert(row, "attack", state_by_key.get(dedupe_key)))
    shutdown_rows: list[dict[str, Any]] = []
    for item in payload.get("shutdown_alerts") or []:
        country = str(item.get("country") or "unknown").strip().upper()
        dedupe_key = str(item.get("dedupe_key") or f"shutdown:{country}")
        row = dict(item)
        row["dedupe_key"] = dedupe_key
        shutdown_rows.append(_enrich_alert(row, "shutdown", state_by_key.get(dedupe_key)))

    payload["cyber_attacks"] = sorted(attack_rows, key=lambda item: (ACTION_STATUS_PRIORITY.get(str((item.get("ops_state") or {}).get("status") or "new"), 0), float(item.get("attack_index") or 0.0)), reverse=True)
    payload["shutdown_alerts"] = sorted(shutdown_rows, key=lambda item: (ACTION_STATUS_PRIORITY.get(str((item.get("ops_state") or {}).get("status") or "new"), 0), float(item.get("shutdown_risk") or 0.0)), reverse=True)
    payload["alert_ops_summary"] = ops_summary
    payload["ops_reporting"] = build_internet_alert_audit_report(operator_events_collection)
    payload["governance"] = {
        "provenance_mode": "operator_safe",
        "raw_payload_redacted": True,
        "operator_feedback_enabled": True,
        "assignment_enabled": True,
        "team_queue_enabled": True,
        "sla_tracking_enabled": True,
        "audit_reporting_enabled": True,
        "confidence_method": "telemetry_plus_operator_feedback",
        "source_stages": sorted({str(item.get("stage") or "unknown") for item in payload.get("source_health") or []}),
        "browser_safe_payload": True,
        "supported_actions": ["acknowledge", "assign", "snooze", "escalate", "false_positive"],
        "generated_at": _iso_now(),
    }
    return payload
