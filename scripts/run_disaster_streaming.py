from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.disaster_streaming import run_disaster_stream_cycle


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the disaster early warning streaming cycle")
    parser.add_argument("--country", default=None)
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--no-collect", action="store_true")
    parser.add_argument("--run-backtest", action="store_true")
    args = parser.parse_args()

    iterations = max(args.iterations, 1)
    for index in range(iterations):
        result = run_disaster_stream_cycle(
            country=args.country,
            limit=max(args.limit, 1),
            refresh_sources=not args.no_collect,
            run_backtest=args.run_backtest,
        )
        print(json.dumps(result, indent=2))
        if index < iterations - 1:
            time.sleep(max(args.interval_seconds, 2.0))


if __name__ == "__main__":
    main()
