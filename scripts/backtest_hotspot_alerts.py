from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(PROJECT_ROOT / '.env', override=True)
MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://127.0.0.1:27017'


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['world_pulse']
    history_docs = list(db['hotspot_history'].find({}, {'_id': 0}).sort('captured_at', 1).limit(10000))
    seismic_docs = list(db['world_state_signals'].find({'source': 'usgs'}, {'_id': 0, 'timestamp_utc': 1, 'timestamp': 1, 'lat': 1, 'lon': 1, 'meta.mag': 1}).sort('timestamp_utc', 1).limit(50000))
    false_positive_by_region: dict[str, int] = defaultdict(int)
    true_positive_by_region: dict[str, int] = defaultdict(int)
    evaluated = 0
    matched = 0
    for row in history_docs:
        band = str(row.get('hotspot_band') or 'guarded')
        if band not in {'critical', 'active'}:
            continue
        captured = parse_dt(row.get('captured_at'))
        if not captured:
            continue
        evaluated += 1
        region = str(row.get('region') or '')
        region_name = str(row.get('region_name') or region)
        future_cutoff = captured + timedelta(hours=24)
        has_follow_on = False
        for signal in seismic_docs:
            signal_dt = parse_dt(signal.get('timestamp_utc') or signal.get('timestamp'))
            if not signal_dt or signal_dt <= captured or signal_dt > future_cutoff:
                continue
            lat = signal.get('lat')
            lon = signal.get('lon')
            if lat is None or lon is None:
                continue
            if region and region.endswith(f"_{int((float(lon) + 180.0) // 40):02d}"):
                mag = float((((signal.get('meta') or {}).get('mag')) or 0.0))
                if mag >= 3.5:
                    has_follow_on = True
                    break
        if has_follow_on:
            matched += 1
            true_positive_by_region[region_name] += 1
        else:
            false_positive_by_region[region_name] += 1
    print({
        'evaluated_alerts': evaluated,
        'matched_follow_on_events': matched,
        'precision_proxy': round(matched / evaluated, 4) if evaluated else 0.0,
        'false_positives_by_region': dict(sorted(false_positive_by_region.items(), key=lambda item: item[1], reverse=True)[:10]),
        'true_positives_by_region': dict(sorted(true_positive_by_region.items(), key=lambda item: item[1], reverse=True)[:10]),
    })


if __name__ == '__main__':
    main()
