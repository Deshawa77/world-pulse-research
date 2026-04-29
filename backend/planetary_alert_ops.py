from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any


ALERT_SCOPE = "planetary_intelligence"
STATUS_ORDER = {
    "new": 0,
    "acknowledged": 1,
    "assigned": 2,
    "snoozed": 3,
    "feedback": 4,
}


def _parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _default_team_queue(alert_type: str) -> str:
    text = str(alert_type or "").strip().lower()
    if text.startswith("hazard_"):
        return "hazard-ops"
    if text.startswith("internet") or text == "routing_or_attack_anomaly":
        return "internet-ops"
    if "behavior" in text:
        return "behavior-ops"
    if "fusion" in text or "correlation" in text:
        return "fusion-ops"
    return "planetary-ops"


def _default_sla_hours(alert_type: str, severity: str) -> int:
    if str(severity or "").strip().lower() in {"critical", "active", "escalated"}:
        return 2
    if str(alert_type or "").startswith("hazard_"):
        return 3
    return 4


def _dedupe_key(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("dedupe_key") or "").strip()
    if explicit:
        return explicit
    alert_id = str(payload.get("alert_id") or "").strip()
    if alert_id:
        return alert_id
    alert_type = str(payload.get("alert_type") or "unknown").strip().lower()
    country = str(payload.get("country") or "").strip().upper()
    region = str(payload.get("region") or "").strip().lower()
    return ":".join(part for part in [alert_type, country or region or "global"] if part)


def build_planetary_alert_operation_doc(payload: dict[str, Any], *, actor: str | None = None) -> dict[str, Any]:
    action = str(payload.get("action") or "").strip().lower()
    owner = str(actor or payload.get("owner") or "system").strip() or "system"
    alert_type = str(payload.get("alert_type") or "unknown").strip().lower() or "unknown"
    severity = str(payload.get("severity") or "guarded").strip().lower() or "guarded"
    now_utc = datetime.now(timezone.utc)
    snooze_hours = max(1, min(int(payload.get("snooze_hours") or 6), 72))
    sla_hours = max(1, min(int(payload.get("sla_hours") or _default_sla_hours(alert_type, severity)), 72))
    team_queue = str(payload.get("team_queue") or _default_team_queue(alert_type)).strip() or _default_team_queue(alert_type)
    assignee = str(payload.get("assignee") or owner).strip() or owner
    return {
        "alert_scope": ALERT_SCOPE,
        "alert_type": alert_type,
        "action": action,
        "owner": owner,
        "assignee": assignee if action == "assign" else None,
        "assignment_reason": str(payload.get("assignment_reason") or payload.get("comment") or "").strip() or None,
        "comment": str(payload.get("comment") or "").strip() or None,
        "country": str(payload.get("country") or "").strip().upper() or None,
        "region": str(payload.get("region") or "").strip() or None,
        "alert_id": str(payload.get("alert_id") or "").strip() or None,
        "dedupe_key": _dedupe_key(payload),
        "severity": severity,
        "team_queue": team_queue,
        "snooze_hours": snooze_hours if action == "snooze" else None,
        "snoozed_until": (now_utc + timedelta(hours=snooze_hours)).isoformat() if action == "snooze" else None,
        "false_positive_reason": str(payload.get("false_positive_reason") or "").strip() or None,
        "sla_hours": sla_hours if action in {"acknowledge", "assign"} else None,
        "sla_due_at": (now_utc + timedelta(hours=sla_hours)).isoformat() if action in {"acknowledge", "assign"} else None,
        "chain_id": str(payload.get("chain_id") or "").strip() or None,
        "timestamp": now_utc.isoformat(),
    }


def load_planetary_alert_ops_state(operator_events_collection, *, hours: int = 168) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(hours, 1))).isoformat()
    docs = list(
        operator_events_collection.find(
            {"alert_scope": ALERT_SCOPE, "timestamp": {"$gte": cutoff}},
            {"_id": 0},
        ).sort("timestamp", 1)
    )
    state: dict[str, dict[str, Any]] = {}
    for doc in docs:
        dedupe_key = str(doc.get("dedupe_key") or "").strip()
        if not dedupe_key:
            continue
        current = state.setdefault(
            dedupe_key,
            {
                "status": "new",
                "action_counts": {"acknowledge": 0, "assign": 0, "snooze": 0, "false_positive": 0},
                "false_positive_count": 0,
                "last_action": None,
                "last_timestamp": None,
                "owner": None,
                "assignee": None,
                "assignment_reason": None,
                "comment": None,
                "false_positive_reason": None,
                "snoozed_until": None,
                "team_queue": None,
                "sla_due_at": None,
                "sla_breached": False,
                "alert_type": None,
                "country": None,
                "region": None,
                "chain_id": None,
            },
        )
        action = str(doc.get("action") or "").strip().lower()
        if action in current["action_counts"]:
            current["action_counts"][action] += 1
        current["last_action"] = action
        current["last_timestamp"] = doc.get("timestamp")
        current["owner"] = doc.get("owner") or current.get("owner")
        current["comment"] = doc.get("comment") or current.get("comment")
        current["team_queue"] = doc.get("team_queue") or current.get("team_queue")
        current["alert_type"] = doc.get("alert_type") or current.get("alert_type")
        current["country"] = doc.get("country") or current.get("country")
        current["region"] = doc.get("region") or current.get("region")
        current["chain_id"] = doc.get("chain_id") or current.get("chain_id")
        if action == "acknowledge":
            current["status"] = "acknowledged"
            current["sla_due_at"] = doc.get("sla_due_at") or current.get("sla_due_at")
        elif action == "assign":
            current["status"] = "assigned"
            current["assignee"] = doc.get("assignee") or current.get("assignee")
            current["assignment_reason"] = doc.get("assignment_reason") or current.get("assignment_reason")
            current["sla_due_at"] = doc.get("sla_due_at") or current.get("sla_due_at")
        elif action == "snooze":
            current["status"] = "snoozed"
            current["snoozed_until"] = doc.get("snoozed_until")
        elif action == "false_positive":
            current["status"] = "feedback"
            current["false_positive_count"] += 1
            current["false_positive_reason"] = doc.get("false_positive_reason") or current.get("false_positive_reason")

    now_utc = datetime.now(timezone.utc)
    summary = {
        "acknowledged": 0,
        "assigned": 0,
        "snoozed_active": 0,
        "false_positive_flags": 0,
        "breached_sla_count": 0,
        "active_queue_count": 0,
        "suppressed_by_snooze": 0,
        "queue_breakdown": [],
    }
    queue_counter: Counter[str] = Counter()
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
        summary["acknowledged"] += 1 if current.get("status") == "acknowledged" else 0
        summary["assigned"] += 1 if current.get("status") == "assigned" else 0
        summary["snoozed_active"] += 1 if current.get("status") == "snoozed" else 0
        summary["false_positive_flags"] += int(current.get("false_positive_count") or 0)
        summary["breached_sla_count"] += 1 if current.get("sla_breached") else 0
        if current.get("status") not in {"new", "feedback"}:
            summary["active_queue_count"] += 1
        if current.get("team_queue"):
            queue_counter[str(current.get("team_queue"))] += 1
    summary["queue_breakdown"] = [{"queue": queue, "count": count} for queue, count in queue_counter.most_common(8)]
    return state, summary


def enrich_planetary_alerts_with_ops(
    alert_events: list[dict[str, Any]],
    operator_events_collection,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    state_by_key, summary = load_planetary_alert_ops_state(operator_events_collection)
    enriched: list[dict[str, Any]] = []
    for alert in alert_events:
        row = dict(alert)
        dedupe_key = _dedupe_key(row)
        ops_state = state_by_key.get(dedupe_key)
        row["dedupe_key"] = dedupe_key
        if ops_state:
            row["status"] = str(ops_state.get("status") or row.get("status") or "active")
            assignment = dict(row.get("assignment") or {})
            if ops_state.get("team_queue"):
                assignment["team"] = ops_state.get("team_queue")
            if ops_state.get("assignee"):
                assignment["owner"] = ops_state.get("assignee")
            if ops_state.get("assignment_reason"):
                assignment["reason"] = ops_state.get("assignment_reason")
            row["assignment"] = assignment
            sla_state = dict(row.get("sla_state") or {})
            sla_state["due_at"] = ops_state.get("sla_due_at")
            sla_state["breached"] = bool(ops_state.get("sla_breached"))
            sla_state["status"] = "breached" if ops_state.get("sla_breached") else sla_state.get("status") or "open"
            row["sla_state"] = sla_state
            row["ops_state"] = dict(ops_state)
        else:
            row["ops_state"] = {
                "status": row.get("status") or "active",
                "action_counts": {"acknowledge": 0, "assign": 0, "snooze": 0, "false_positive": 0},
                "false_positive_count": 0,
                "last_action": None,
                "last_timestamp": None,
                "assignee": None,
                "assignment_reason": None,
                "snoozed_until": None,
                "team_queue": (row.get("assignment") or {}).get("team"),
                "sla_due_at": None,
                "sla_breached": False,
            }
        enriched.append(row)
    return enriched, summary
