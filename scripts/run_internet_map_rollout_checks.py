from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.runtime_config import bootstrap_runtime_environment

bootstrap_runtime_environment(PROJECT_ROOT)


class HttpClient:
    def __init__(self, base_url: str, timeout_sec: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    def request_json(self, method: str, path: str, *, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode({key: value for key, value in params.items() if value is not None})}"
        payload = None
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
        request = Request(url, data=payload, headers=request_headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw.strip() else {}
                return int(getattr(response, "status", 200)), parsed if isinstance(parsed, dict) else {"data": parsed}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8") if exc.fp else ""
            try:
                parsed = json.loads(raw) if raw.strip() else {}
            except Exception:
                parsed = {"detail": raw}
            return int(getattr(exc, "code", 500)), parsed if isinstance(parsed, dict) else {"data": parsed}
        except URLError as exc:
            return 599, {"detail": str(exc)}

    def first_sse_event(self, path: str, *, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode({key: value for key, value in params.items() if value is not None})}"
        request = Request(url, headers=headers or {}, method="GET")
        with urlopen(request, timeout=self.timeout_sec) as response:
            event_name = None
            data_lines: list[str] = []
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    if data_lines:
                        payload = json.loads("\n".join(data_lines))
                        return {"event": event_name or "message", "data": payload}
                    continue
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
        raise RuntimeError("No SSE event received")


def _auth_headers(token: str | None = None, api_key: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _register_or_login(client: HttpClient, email: str, password: str) -> dict[str, Any]:
    register_body = {
        "name": "Internet Map Rollout",
        "email": email,
        "password": password,
        "user_type": "researcher",
    }
    status, payload = client.request_json("POST", "/auth/register", body=register_body)
    if status == 200 and payload.get("access_token"):
        return payload
    status, payload = client.request_json("POST", "/auth/login", body={"email": email, "password": password})
    if status == 200 and payload.get("access_token"):
        return payload
    raise RuntimeError(f"Unable to register/login rollout user: {status} {payload}")


def _first_alert_action(snapshot: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    attacks = snapshot.get("cyber_attacks") or []
    if attacks:
        return attacks[0], "attack"
    shutdowns = snapshot.get("shutdown_alerts") or []
    if shutdowns:
        return shutdowns[0], "shutdown"
    return None, None


def _cache_ratio(snapshot: dict[str, Any]) -> float:
    collector_summary = snapshot.get("collector_summary") or {}
    source_count = int(collector_summary.get("source_family_count") or 0)
    cache_hits = int(collector_summary.get("cache_hit_families") or 0)
    if source_count <= 0:
        return 0.0
    return round(cache_hits / source_count, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Internet Map staging-to-production rollout checks.")
    parser.add_argument("--base-url", default=os.environ.get("INTERNET_MAP_ROLLOUT_BASE_URL") or "http://127.0.0.1:8000", help="Base URL for the deployed API.")
    parser.add_argument("--email", default=os.environ.get("INTERNET_MAP_ROLLOUT_EMAIL") or f"rollout.internet.map.{int(time.time())}@example.com")
    parser.add_argument("--password", default=os.environ.get("INTERNET_MAP_ROLLOUT_PASSWORD") or "RolloutPass123!")
    parser.add_argument("--token", default=os.environ.get("INTERNET_MAP_ROLLOUT_TOKEN") or "")
    parser.add_argument("--api-key", default=os.environ.get("INTERNET_MAP_ROLLOUT_API_KEY") or "")
    parser.add_argument("--admin-api-key", default=os.environ.get("INTERNET_MAP_ROLLOUT_ADMIN_API_KEY") or os.environ.get("ADMIN_KEY") or "")
    parser.add_argument("--warm-requests", type=int, default=4)
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    args = parser.parse_args()

    client = HttpClient(args.base_url, timeout_sec=max(5.0, args.timeout_sec))
    token = args.token
    if not token and not args.api_key:
        auth = _register_or_login(client, args.email, args.password)
        token = str(auth.get("access_token") or "")

    user_headers = _auth_headers(token=token or None, api_key=args.api_key or None)
    admin_headers = _auth_headers(api_key=args.admin_api_key or None)

    cold_started = time.perf_counter()
    cold_status, cold_snapshot = client.request_json("GET", "/dashboard/internet-map", headers=user_headers, params={"refresh": "true", "refresh_sources": "true"})
    cold_latency_ms = round((time.perf_counter() - cold_started) * 1000.0, 3)
    if cold_status != 200:
        raise RuntimeError(f"cold snapshot failed: {cold_status} {cold_snapshot}")

    warm_latencies: list[float] = []
    warm_snapshots: list[dict[str, Any]] = []
    for _ in range(max(1, args.warm_requests)):
        started = time.perf_counter()
        status, snapshot = client.request_json("GET", "/dashboard/internet-map", headers=user_headers)
        warm_latencies.append((time.perf_counter() - started) * 1000.0)
        if status != 200:
            raise RuntimeError(f"warm snapshot failed: {status} {snapshot}")
        warm_snapshots.append(snapshot)
    warm_p95_ms = round(max(warm_latencies), 3)

    sse_event = client.first_sse_event(
        "/api/internet-map/alerts/stream",
        headers=user_headers,
        params={"poll_seconds": 2, "mode": "live", "data_mode": "online"},
    )

    selected_alert, alert_type = _first_alert_action(cold_snapshot)
    action_response: dict[str, Any] = {"skipped": True}
    if selected_alert and alert_type:
        action_body = {
            "alert_type": alert_type,
            "action": "assign",
            "owner": "rollout-check",
            "assignee": "rollout-check",
            "assignment_reason": "rollout validation",
            "alert_id": selected_alert.get("alert_id") or selected_alert.get("id"),
            "flow_id": selected_alert.get("flow_id"),
            "country": selected_alert.get("country"),
            "dedupe_key": selected_alert.get("dedupe_key"),
            "severity": selected_alert.get("severity"),
        }
        status, action_response = client.request_json("POST", "/api/internet-map/alerts/action", headers=user_headers, body=action_body)
        if status != 200:
            raise RuntimeError(f"alert action failed: {status} {action_response}")

    admin_results: dict[str, Any] = {"skipped": True}
    if args.admin_api_key:
        queue_status, queue_payload = client.request_json("POST", "/api/internet-map/runtime/queue-refresh", headers=admin_headers, params={"refresh_sources": "true", "wait": "false"})
        backtest_status, backtest_payload = client.request_json("POST", "/api/internet-map/backtests/run", headers=admin_headers, params={"days": 30})
        prune_status, prune_payload = client.request_json("POST", "/api/internet-map/maintenance/prune", headers=admin_headers, params={"retention_days": 30, "stream_retention_days": 30, "backtest_retention_days": 90, "collector_retention_days": 30})
        admin_results = {
            "skipped": False,
            "queue_refresh": {"status_code": queue_status, "ok": queue_status == 200, "runtime_status": queue_payload.get("runtime_status")},
            "backtest": {"status_code": backtest_status, "ok": backtest_status == 200, "summary": backtest_payload.get("overall") or backtest_payload},
            "maintenance": {"status_code": prune_status, "ok": prune_status == 200, "summary": prune_payload},
        }

    payload = {
        "status": "ok",
        "base_url": args.base_url,
        "cold_cycle_latency_ms": cold_latency_ms,
        "warm_p95_ms": warm_p95_ms,
        "warm_cache_hit_ratio": _cache_ratio(warm_snapshots[-1]) if warm_snapshots else 0.0,
        "source_stage": (cold_snapshot.get("summary") or {}).get("source_stage"),
        "sse_event": sse_event.get("event"),
        "sse_run_id": ((sse_event.get("data") or {}).get("stream_status") or {}).get("run_id"),
        "alert_workflow": action_response,
        "admin_jobs": admin_results,
        "slo_targets": (cold_snapshot.get("observability") or {}).get("slo_targets") or {},
        "runtime_status": cold_snapshot.get("runtime_status") or {},
    }
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
