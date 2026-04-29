from __future__ import annotations



import json

import sys

import time

from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:

    sys.path.insert(0, str(ROOT))



from fastapi.testclient import TestClient



from backend.main import app, operator_events_collection, users_collection



REQUIRED_KEYS = [

    "generated_at",

    "summary",

    "source_health",

    "countries",

    "flows",

    "cyber_attacks",

    "shutdown_alerts",

    "top_corridors",

    "generated_from",

    "collector_summary",

    "stream_status",

    "history",

    "governance",

    "observability",

    "persistence",

    "backtest_summary",

    "replay_analytics",

    "retention_policy",

]





def fail(errors: list[str]) -> None:

    print(json.dumps({"status": "error", "errors": errors}, indent=2))

    raise SystemExit(1)





def main() -> None:

    suffix = str(int(time.time() * 1000))

    email = f"contract.internet.map.{suffix}@example.com"

    password = "ContractPass123!"

    owner = f"contract-{suffix}"



    with TestClient(app) as client:

        register = client.post(

            "/auth/register",

            json={

                "name": "Internet Contract",

                "email": email,

                "password": password,

                "user_type": "researcher",

            },

        )

        if register.status_code != 200:

            fail([f"register failed: {register.status_code} {register.text}"])



        token = register.json().get("access_token")

        if not token:

            fail(["register response missing access_token"])

        headers = {"Authorization": f"Bearer {token}"}



        response = client.get(

            "/dashboard/internet-map",

            headers=headers,

            params={"mode": "online", "refresh": "true", "refresh_sources": "true"},

        )

        if response.status_code != 200:

            fail([f"dashboard route failed: {response.status_code} {response.text}"])

        payload = response.json()



        errors: list[str] = []

        for key in REQUIRED_KEYS:

            if key not in payload:

                errors.append(f"missing payload key: {key}")



        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

        if summary.get("source_stage") not in {"phase-4-direct-live", "phase-4-direct-hybrid", "phase-1-derived"}:

            errors.append("summary.source_stage missing expected direct or derived stage")

        if not isinstance(payload.get("source_health"), list) or len(payload.get("source_health") or []) < 4:

            errors.append("source_health missing expected source families")

        if not isinstance(payload.get("history"), list):

            errors.append("history missing or invalid")

        if not isinstance(payload.get("stream_status"), dict) or not payload["stream_status"].get("run_id"):

            errors.append("stream_status.run_id missing")

        if not isinstance(payload.get("persistence"), dict) or "internet_alerts" not in (payload["persistence"].get("collections") or []):

            errors.append("persistence.collections missing internet_alerts")

        if not isinstance(payload.get("governance"), dict) or payload["governance"].get("raw_payload_redacted") is not True:

            errors.append("governance.raw_payload_redacted should be true")

        if not isinstance(payload.get("replay_analytics"), dict) or payload["replay_analytics"].get("trend_direction") is None:

            errors.append("replay_analytics.trend_direction missing")

        if not isinstance(payload.get("retention_policy"), dict) or payload["retention_policy"].get("maintenance_script") != "scripts/run_internet_map_maintenance.py":

            errors.append("retention_policy.maintenance_script missing")
        if not isinstance(payload.get("runtime_status"), dict) or payload["runtime_status"].get("scheduler_enabled") is None:

            errors.append("runtime_status.scheduler_enabled missing")
        if not isinstance(payload.get("ops_reporting"), dict) or payload["ops_reporting"].get("audit_window_hours") is None:

            errors.append("ops_reporting.audit_window_hours missing")



        history_response = client.get("/dashboard/internet-map/history", headers=headers, params={"limit": 8})

        if history_response.status_code != 200:

            errors.append(f"history route failed: {history_response.status_code}")

        else:

            history_payload = history_response.json()

            if "items" not in history_payload:

                errors.append("history response missing items")

        playback_response = client.get("/dashboard/internet-map/playback", headers=headers, params={"limit": 8})

        if playback_response.status_code != 200:

            errors.append(f"playback route failed: {playback_response.status_code}")

        else:

            playback_payload = playback_response.json()

            if not isinstance(playback_payload.get("frames"), list):

                errors.append("playback response missing frames")

            elif not playback_payload.get("frames"):

                errors.append("playback response returned no frames")



        backtest_response = client.get("/dashboard/internet-map/backtest", headers=headers)

        if backtest_response.status_code != 200:

            errors.append(f"backtest route failed: {backtest_response.status_code}")



        status_response = client.get("/api/internet-map/stream/status", headers=headers, params={"refresh": "false"})

        if status_response.status_code != 200:

            errors.append(f"stream status route failed: {status_response.status_code}")

        else:

            status_payload = status_response.json()

            if not (status_payload.get("stream_status") or {}).get("status"):

                errors.append("stream status payload missing stream_status.status")
            if not isinstance(status_payload.get("runtime_status"), dict):

                errors.append("stream status payload missing runtime_status")



        shutdowns = payload.get("shutdown_alerts") or []

        if shutdowns:

            action_response = client.post(

                "/api/internet-map/alerts/action",

                headers=headers,

                json={

                    "alert_type": "shutdown",

                    "country": shutdowns[0].get("country"),

                    "action": "assign",

                    "owner": owner,

                    "assignee": owner,

                    "assignment_reason": "contract validation",

                    "alert_id": shutdowns[0].get("alert_id") or shutdowns[0].get("id"),

                    "dedupe_key": shutdowns[0].get("dedupe_key"),

                    "severity": shutdowns[0].get("severity"),

                },

            )

            if action_response.status_code != 200:

                errors.append(f"alert action route failed: {action_response.status_code} {action_response.text}")

            elif action_response.json().get("ok") is not True:

                errors.append("alert action response missing ok=true")



        users_collection.delete_one({"email": email})

        operator_events_collection.delete_many({"owner": owner, "alert_scope": "internet_map"})

        operator_events_collection.delete_many({"assignee": owner, "alert_scope": "internet_map"})



    if errors:

        fail(errors)



    print(json.dumps({

        "status": "ok",

        "visible_countries": int(summary.get("visible_countries") or 0),

        "flow_count": len(payload.get("flows") or []),

        "history_points": len(payload.get("history") or []),

        "source_health_count": len(payload.get("source_health") or []),

        "stream_run_id": (payload.get("stream_status") or {}).get("run_id"),

        "source_stage": summary.get("source_stage"),

    }, indent=2))





if __name__ == "__main__":

    main()


