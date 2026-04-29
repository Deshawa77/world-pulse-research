from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from processing.disaster_backtests import run_disaster_backtests


def main() -> None:
    parser = argparse.ArgumentParser(description="Run disaster early warning backtests and persist the latest summary")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()

    result = run_disaster_backtests(days=max(args.days, 1), persist=not args.no_persist)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
