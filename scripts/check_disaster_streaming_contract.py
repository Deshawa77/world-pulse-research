from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.disaster_streaming import run_disaster_stream_cycle


REQUIRED_STREAM_KEYS = ["run_id", "status", "captured_at", "payload", "stream_status"]
REQUIRED_PAYLOAD_KEYS = ["forecasts", "regional_hotspots", "source_health", "alert_queue", "stream_status", "backtest_summary"]


def main() -> None:
    snapshot = run_disaster_stream_cycle(limit=4, refresh_sources=False, run_backtest=False)
    errors: list[str] = []
    for key in REQUIRED_STREAM_KEYS:
        if key not in snapshot:
            errors.append(f"missing snapshot key: {key}")
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else {}
    for key in REQUIRED_PAYLOAD_KEYS:
        if key not in payload:
            errors.append(f"missing payload key: {key}")
    stream_status = payload.get("stream_status") if isinstance(payload.get("stream_status"), dict) else {}
    if not stream_status.get("run_id"):
        errors.append("stream_status.run_id missing")
    if not isinstance(payload.get("source_health"), list) or len(payload.get("source_health") or []) < 1:
        errors.append("source_health missing or empty")
    if not isinstance(payload.get("backtest_summary"), dict):
        errors.append("backtest_summary missing")

    if errors:
        print(json.dumps({"status": "error", "errors": errors}, indent=2))
        raise SystemExit(1)

    print(json.dumps({
        "status": "ok",
        "forecast_count": len(payload.get("forecasts") or []),
        "source_health_count": len(payload.get("source_health") or []),
        "active_alerts": sum(len(items or []) for items in (payload.get("alert_queue") or {}).values()),
        "stream_run_id": stream_status.get("run_id"),
    }, indent=2))


if __name__ == "__main__":
    main()
