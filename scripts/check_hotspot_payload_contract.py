from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from processing.disaster_early_warning import compute_disaster_early_warning


def main() -> None:
    payload = compute_disaster_early_warning(limit=4)
    hotspots = ((payload.get('regional_hotspots') or {}).get('earthquake') or [])
    required = ['region', 'region_name', 'region_label', 'display_label', 'history', 'hotspot_band']
    missing = []
    for index, hotspot in enumerate(hotspots):
        for key in required:
            if key not in hotspot:
                missing.append((index, key))
    if missing:
        raise SystemExit(f'Missing hotspot contract fields: {missing}')
    print({'status': 'ok', 'hotspot_count': len(hotspots), 'fields_checked': required})


if __name__ == '__main__':
    main()
