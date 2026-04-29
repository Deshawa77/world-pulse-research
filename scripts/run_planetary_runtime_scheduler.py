from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import _materialize_planetary_runtime_snapshot


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the planetary runtime materialization loop as a standalone worker.")
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--source-refresh-interval-seconds", type=int, default=900)
    parser.add_argument("--backtest-interval-seconds", type=int, default=21600)
    parser.add_argument("--once", action="store_true", help="Run one materialization cycle and exit.")
    args = parser.parse_args()

    stop = False

    def handle_stop(_signum, _frame) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    last_source_refresh_at = 0.0
    last_backtest_at = 0.0

    while not stop:
        now = time.monotonic()
        refresh_sources = (now - last_source_refresh_at) >= max(300, int(args.source_refresh_interval_seconds))
        run_backtests = (now - last_backtest_at) >= max(900, int(args.backtest_interval_seconds))
        payload = _materialize_planetary_runtime_snapshot(
            mode="online",
            refresh_sources=refresh_sources,
            run_backtests=run_backtests,
            reason="scripted_scheduler",
        )
        if refresh_sources:
            last_source_refresh_at = time.monotonic()
        if run_backtests:
            last_backtest_at = time.monotonic()
        print(json.dumps({
            "generated_at": _now_iso(),
            "status": "ok",
            "run_id": payload.get("run_id"),
            "captured_at": payload.get("captured_at"),
            "refresh_sources": refresh_sources,
            "run_backtests": run_backtests,
        }, indent=2))
        if args.once:
            break
        sleep_for = max(60, int(args.interval_seconds))
        deadline = time.monotonic() + sleep_for
        while not stop and time.monotonic() < deadline:
            time.sleep(1.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
