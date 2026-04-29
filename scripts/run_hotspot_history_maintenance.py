from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from pymongo import MongoClient

from backend.hotspot_history import ensure_hotspot_indexes, prune_history, summarize_history

load_dotenv(PROJECT_ROOT / '.env', override=True)
MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://127.0.0.1:27017'


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['world_pulse']
    history = db['hotspot_history']
    summary = db['hotspot_history_summary']
    ensure_hotspot_indexes(history, summary)
    hourly = summarize_history(summary, history, hours=24)
    daily = summarize_history(summary, history, hours=168)
    deleted = prune_history(history, retention_days=30)
    print({
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'hourly': hourly,
        'daily': daily,
        'deleted': deleted,
    })


if __name__ == '__main__':
    main()
