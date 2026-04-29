from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.runtime_config import bootstrap_runtime_environment
from processing.internet_map_maintenance import run_internet_map_maintenance

bootstrap_runtime_environment(PROJECT_ROOT)


def main() -> None:
    result = run_internet_map_maintenance()
    print(result)


if __name__ == '__main__':
    main()
