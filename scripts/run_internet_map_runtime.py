from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import INTERNET_MAP_RUNTIME, _ensure_internet_map_runtime_started


def main() -> None:
    _ensure_internet_map_runtime_started()
    INTERNET_MAP_RUNTIME.request_cycle(mode="online", refresh_sources=True, reason="script_bootstrap", block=False)
    print("[internet-map-runtime] scheduler started")
    while True:
        status = INTERNET_MAP_RUNTIME.status()
        print(
            "[internet-map-runtime] "
            f"status={status.get('status')} "
            f"queue_depth={status.get('queue_depth')} "
            f"last_cycle={status.get('last_cycle_finished_at')}"
        )
        time.sleep(60)


if __name__ == "__main__":
    main()
