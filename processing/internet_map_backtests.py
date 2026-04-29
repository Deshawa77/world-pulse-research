from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from database.mongo import db
from processing.internet_map_storage import load_internet_map_backtest_snapshot, persist_internet_map_backtest_snapshot


ATTACK_LEAD_HOURS = 6
SHUTDOWN_LEAD_HOURS = 12


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


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    return numeric if numeric == numeric else fallback


def _flow_key(row: dict[str, Any]) -> str:
    return str(row.get("flow_id") or row.get("id") or f"{row.get('origin', '')}-{row.get('destination', '')}").strip().lower()


def _feedback_index(cutoff_iso: str) -> dict[str, dict[str, int]]:
    docs = list(
        db["operator_events"].find(
            {"alert_scope": "internet_map", "timestamp": {"$gte": cutoff_iso}},
            {"_id": 0, "dedupe_key": 1, "action": 1},
        )
    )
    result: dict[str, dict[str, int]] = defaultdict(lambda: {"false_positive": 0, "escalate": 0, "assign": 0})
    for doc in docs:
        key = str(doc.get("dedupe_key") or "").strip()
        action = str(doc.get("action") or "").strip().lower()
        if not key:
            continue
        if action == "false_positive":
            result[key]["false_positive"] += 1
        elif action == "escalate":
            result[key]["escalate"] += 1
        elif action == "assign":
            result[key]["assign"] += 1
    return result


def _build_backtest_result(
    *,
    evaluated: int,
    matched: int,
    false_positives: int,
    feedback_false_positive_flags: int,
    true_positive_rows: dict[str, int],
    false_positive_rows: dict[str, int],
    true_label: str,
    false_label: str,
) -> dict[str, Any]:
    precision = round(matched / evaluated, 4) if evaluated else 0.0
    feedback_denominator = evaluated + feedback_false_positive_flags
    feedback_adjusted_precision = round(matched / feedback_denominator, 4) if feedback_denominator else 0.0
    return {
        "evaluated_alerts": evaluated,
        "matched_follow_on_signals": matched,
        "false_positives": false_positives,
        "precision_proxy": precision,
        "feedback_adjusted_precision_proxy": feedback_adjusted_precision,
        "feedback_false_positive_flags": feedback_false_positive_flags,
        "false_positive_rate": round(false_positives / evaluated, 4) if evaluated else 0.0,
        true_label: dict(sorted(true_positive_rows.items(), key=lambda item: item[1], reverse=True)[:8]),
        false_label: dict(sorted(false_positive_rows.items(), key=lambda item: item[1], reverse=True)[:8]),
    }


def _evaluate_attack_alerts(alert_docs: list[dict[str, Any]], flow_docs: list[dict[str, Any]], feedback_index: dict[str, dict[str, int]]) -> dict[str, Any]:
    by_flow: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in flow_docs:
        key = _flow_key(row)
        captured = _parse_dt(row.get("captured_at"))
        if not key or not captured:
            continue
        by_flow[key].append({**row, "_captured_dt": captured})
    for rows in by_flow.values():
        rows.sort(key=lambda item: item["_captured_dt"])

    evaluated = 0
    matched = 0
    false_positives = 0
    feedback_false_positive_flags = 0
    true_positive_flows: dict[str, int] = defaultdict(int)
    false_positive_flows: dict[str, int] = defaultdict(int)

    for alert in alert_docs:
        captured = _parse_dt(alert.get("captured_at"))
        key = _flow_key(alert)
        if not key or not captured:
            continue
        evaluated += 1
        baseline_attack = _safe_float(alert.get("attack_index"), 0.0)
        window_end = captured + timedelta(hours=ATTACK_LEAD_HOURS)
        candidates = [row for row in by_flow.get(key, []) if captured < row["_captured_dt"] <= window_end]
        found = any(
            _safe_float(row.get("attack_index")) >= max(62.0, baseline_attack * 0.95)
            or _safe_float(row.get("packet_loss_pct")) >= 3.0
            or _safe_float(row.get("reroute_factor"), 1.0) >= 1.14
            or _safe_float(row.get("hijack_suspect_score")) >= 0.24
            for row in candidates
        )
        feedback = feedback_index.get(f"attack:{key}") or {}
        feedback_false_positive_flags += int(feedback.get("false_positive") or 0)
        if found:
            matched += 1
            true_positive_flows[key] += 1
        else:
            false_positives += 1
            false_positive_flows[key] += 1

    return _build_backtest_result(
        evaluated=evaluated,
        matched=matched,
        false_positives=false_positives,
        feedback_false_positive_flags=feedback_false_positive_flags,
        true_positive_rows=true_positive_flows,
        false_positive_rows=false_positive_flows,
        true_label="top_true_positive_flows",
        false_label="top_false_positive_flows",
    )


def _evaluate_shutdown_alerts(alert_docs: list[dict[str, Any]], country_docs: list[dict[str, Any]], feedback_index: dict[str, dict[str, int]]) -> dict[str, Any]:
    by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in country_docs:
        country = str(row.get("country") or "").strip().upper()
        captured = _parse_dt(row.get("captured_at"))
        if not country or not captured:
            continue
        by_country[country].append({**row, "_captured_dt": captured})
    for rows in by_country.values():
        rows.sort(key=lambda item: item["_captured_dt"])

    evaluated = 0
    matched = 0
    false_positives = 0
    feedback_false_positive_flags = 0
    true_positive_countries: dict[str, int] = defaultdict(int)
    false_positive_countries: dict[str, int] = defaultdict(int)

    for alert in alert_docs:
        country = str(alert.get("country") or "").strip().upper()
        captured = _parse_dt(alert.get("captured_at"))
        if not country or not captured:
            continue
        evaluated += 1
        baseline_shutdown = _safe_float(alert.get("shutdown_risk"), 0.0)
        window_end = captured + timedelta(hours=SHUTDOWN_LEAD_HOURS)
        candidates = [row for row in by_country.get(country, []) if captured < row["_captured_dt"] <= window_end]
        found = any(
            _safe_float(row.get("shutdown_risk")) >= max(66.0, baseline_shutdown * 0.95)
            or _safe_float(row.get("subscriber_availability_ratio"), 1.0) <= 0.8
            or _safe_float(row.get("fixed_reachability_ratio"), 1.0) <= 0.82
            or _safe_float(row.get("mobile_reachability_ratio"), 1.0) <= 0.8
            or _safe_float(row.get("throughput_drop_pct")) >= 22.0
            or _safe_float(row.get("control_plane_incident_score")) >= 0.18
            for row in candidates
        )
        feedback = feedback_index.get(f"shutdown:{country}") or {}
        feedback_false_positive_flags += int(feedback.get("false_positive") or 0)
        if found:
            matched += 1
            true_positive_countries[country] += 1
        else:
            false_positives += 1
            false_positive_countries[country] += 1

    return _build_backtest_result(
        evaluated=evaluated,
        matched=matched,
        false_positives=false_positives,
        feedback_false_positive_flags=feedback_false_positive_flags,
        true_positive_rows=true_positive_countries,
        false_positive_rows=false_positive_countries,
        true_label="top_true_positive_countries",
        false_label="top_false_positive_countries",
    )


def run_internet_map_backtest(days: int = 30, persist: bool = True) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=max(days, 1))
    cutoff_iso = cutoff.isoformat()
    attack_alerts = list(db["internet_alerts"].find({"captured_at": {"$gte": cutoff_iso}, "alert_type": "attack"}, {"_id": 0}).sort("captured_at", 1).limit(120000))
    shutdown_alerts = list(db["internet_alerts"].find({"captured_at": {"$gte": cutoff_iso}, "alert_type": "shutdown"}, {"_id": 0}).sort("captured_at", 1).limit(120000))
    flow_docs = list(db["internet_flow_snapshots"].find({"captured_at": {"$gte": cutoff_iso}}, {"_id": 0}).sort("captured_at", 1).limit(180000))
    country_docs = list(db["internet_country_snapshots"].find({"captured_at": {"$gte": cutoff_iso}}, {"_id": 0}).sort("captured_at", 1).limit(180000))
    feedback_index = _feedback_index(cutoff_iso)

    attacks = _evaluate_attack_alerts(attack_alerts, flow_docs, feedback_index)
    shutdowns = _evaluate_shutdown_alerts(shutdown_alerts, country_docs, feedback_index)
    total_evaluated = int(attacks["evaluated_alerts"]) + int(shutdowns["evaluated_alerts"])
    total_matched = int(attacks["matched_follow_on_signals"]) + int(shutdowns["matched_follow_on_signals"])
    total_false_positives = int(attacks["false_positives"]) + int(shutdowns["false_positives"])
    total_feedback_false_positive_flags = int(attacks.get("feedback_false_positive_flags") or 0) + int(shutdowns.get("feedback_false_positive_flags") or 0)
    payload = {
        "generated_at": now_utc.isoformat(),
        "run_id": f"internet_map_backtest_{now_utc.strftime('%Y%m%dT%H%M%SZ')}",
        "window_days": int(max(days, 1)),
        "status": "ok",
        "overall": {
            "evaluated_alerts": total_evaluated,
            "matched_follow_on_signals": total_matched,
            "false_positives": total_false_positives,
            "precision_proxy": round(total_matched / total_evaluated, 4) if total_evaluated else 0.0,
            "feedback_adjusted_precision_proxy": round(total_matched / (total_evaluated + total_feedback_false_positive_flags), 4) if (total_evaluated + total_feedback_false_positive_flags) else 0.0,
            "feedback_false_positive_flags": total_feedback_false_positive_flags,
            "false_positive_rate": round(total_false_positives / total_evaluated, 4) if total_evaluated else 0.0,
        },
        "attack_alerts": attacks,
        "shutdown_alerts": shutdowns,
    }
    if persist:
        persist_internet_map_backtest_snapshot(payload)
    return payload


def latest_internet_map_backtest() -> dict[str, Any]:
    return load_internet_map_backtest_snapshot() or {
        "generated_at": None,
        "status": "idle",
        "window_days": 30,
        "overall": {
            "evaluated_alerts": 0,
            "matched_follow_on_signals": 0,
            "false_positives": 0,
            "precision_proxy": 0.0,
            "feedback_adjusted_precision_proxy": 0.0,
            "feedback_false_positive_flags": 0,
            "false_positive_rate": 0.0,
        },
        "attack_alerts": {},
        "shutdown_alerts": {},
    }
