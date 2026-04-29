from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import _materialize_planetary_runtime_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize one planetary runtime snapshot without waiting for the background scheduler")
    parser.add_argument("--refresh-sources", action="store_true")
    parser.add_argument("--run-backtests", action="store_true")
    args = parser.parse_args()

    payload = _materialize_planetary_runtime_snapshot(
        mode="online",
        refresh_sources=args.refresh_sources,
        run_backtests=args.run_backtests,
        reason="script",
    )
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
