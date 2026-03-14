from __future__ import annotations

import argparse
import time
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from machine_learning.lstm_predictor import train_lstm_models
from processing.country_risk_validation import run_country_risk_backtest, run_country_risk_validation
from processing.global_mood_validation import run_global_mood_backtest, run_global_mood_validation


def _run_hourly_refresh() -> None:
    started = datetime.now(timezone.utc).isoformat()
    print(f"[scheduler] hourly refresh started at {started}")
    result = train_lstm_models(force=False)
    status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
    model_meta = result.get("model_metadata", {}) if isinstance(result, dict) else {}
    print(f"[scheduler] hourly refresh done status={status} version={model_meta.get('version')}")


def _run_validation_suite(backtest_days: int = 60) -> None:
    started = datetime.now(timezone.utc).isoformat()
    print(f"[scheduler] validation suite started at {started}")
    country_validation = run_country_risk_validation()
    global_validation = run_global_mood_validation()
    country_backtest = run_country_risk_backtest(days=max(1, int(backtest_days)))
    global_backtest = run_global_mood_backtest(days=max(1, int(backtest_days)))
    print(
        "[scheduler] validation suite done "
        f"country_status={country_validation.get('status')} "
        f"global_status={global_validation.get('status')} "
        f"country_backtest={country_backtest.get('status')} "
        f"global_backtest={global_backtest.get('status')}"
    )


def _run_daily_retrain(backtest_days: int = 60) -> None:
    started = datetime.now(timezone.utc).isoformat()
    print(f"[scheduler] daily retrain started at {started}")
    result = train_lstm_models(force=True)
    status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
    model_meta = result.get("model_metadata", {}) if isinstance(result, dict) else {}
    print(f"[scheduler] daily retrain done status={status} version={model_meta.get('version')}")
    _run_validation_suite(backtest_days=backtest_days)


def _parse_hhmm(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("--daily-at must be HH:MM")
    hh = int(parts[0])
    mm = int(parts[1])
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        raise ValueError("--daily-at must be valid 24h time")
    return hh, mm


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline LSTM trainer scheduler")
    parser.add_argument("--hourly-minutes", type=int, default=60, help="Interval for lightweight model refresh")
    parser.add_argument("--daily-at", type=str, default="02:10", help="UTC HH:MM for forced daily retrain")
    parser.add_argument("--run-once", action="store_true", help="Run one forced retrain and validation suite, then exit")
    parser.add_argument("--backtest-days", type=int, default=60, help="Historical window used for daily validation backtests")
    args = parser.parse_args()

    if args.run_once:
        _run_daily_retrain(backtest_days=max(1, args.backtest_days))
        return

    hourly_seconds = max(300, int(args.hourly_minutes) * 60)
    daily_h, daily_m = _parse_hhmm(args.daily_at)

    print(
        f"[scheduler] started hourly every {hourly_seconds // 60}m, "
        f"daily retrain at {args.daily_at} UTC with {max(1, args.backtest_days)}d backtests"
    )

    _run_hourly_refresh()
    last_hourly = time.time()
    last_daily_date = None

    while True:
        now = datetime.now(timezone.utc)

        if (time.time() - last_hourly) >= hourly_seconds:
            _run_hourly_refresh()
            last_hourly = time.time()

        if now.hour == daily_h and now.minute == daily_m and now.date() != last_daily_date:
            _run_daily_retrain(backtest_days=max(1, args.backtest_days))
            last_daily_date = now.date()

        time.sleep(1)


if __name__ == "__main__":
    main()
