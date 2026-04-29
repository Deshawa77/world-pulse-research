from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from database.mongo import db
from processing.internet_map_storage import BACKTEST_HISTORY_DIR, COLLECTOR_HISTORY_DIR, STREAM_HISTORY_DIR, prune_json_history_dir

INTERNET_COLLECTIONS = [
    "internet_raw_events",
    "internet_normalized_events",
    "internet_country_snapshots",
    "internet_flow_snapshots",
    "internet_alerts",
    "internet_source_health",
]
DEFAULT_RETENTION_DAYS = int(os.environ.get("INTERNET_MAP_RETENTION_DAYS") or 30)
DEFAULT_STREAM_HISTORY_RETENTION_DAYS = int(os.environ.get("INTERNET_MAP_STREAM_HISTORY_RETENTION_DAYS") or 30)
DEFAULT_BACKTEST_RETENTION_DAYS = int(os.environ.get("INTERNET_MAP_BACKTEST_RETENTION_DAYS") or 90)
DEFAULT_COLLECTOR_RETENTION_DAYS = int(os.environ.get("INTERNET_MAP_COLLECTOR_HISTORY_RETENTION_DAYS") or 30)


def build_internet_retention_policy() -> dict[str, Any]:
    return {
        "mongo_retention_days": DEFAULT_RETENTION_DAYS,
        "stream_history_retention_days": DEFAULT_STREAM_HISTORY_RETENTION_DAYS,
        "backtest_retention_days": DEFAULT_BACKTEST_RETENTION_DAYS,
        "collector_history_retention_days": DEFAULT_COLLECTOR_RETENTION_DAYS,
        "collections": list(INTERNET_COLLECTIONS),
        "maintenance_script": "scripts/run_internet_map_maintenance.py",
    }


def prune_internet_map_collections(*, retention_days: int = DEFAULT_RETENTION_DAYS) -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(retention_days, 1))).isoformat()
    deleted: dict[str, int] = {}
    for name in INTERNET_COLLECTIONS:
        field = "updated_at" if name == "internet_source_health" else "captured_at"
        try:
            result = db[name].delete_many({field: {"$lt": cutoff}})
            deleted[name] = int(result.deleted_count)
        except Exception:
            deleted[name] = 0
    return deleted


def summarize_internet_map_collections(*, hours: int = 24) -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(hours, 1))).isoformat()
    counts: dict[str, int] = {}
    for name in INTERNET_COLLECTIONS:
        field = "updated_at" if name == "internet_source_health" else "captured_at"
        try:
            counts[name] = int(db[name].count_documents({field: {"$gte": cutoff}}))
        except Exception:
            counts[name] = 0
    return counts


def run_internet_map_maintenance(
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    stream_retention_days: int = DEFAULT_STREAM_HISTORY_RETENTION_DAYS,
    backtest_retention_days: int = DEFAULT_BACKTEST_RETENTION_DAYS,
    collector_retention_days: int = DEFAULT_COLLECTOR_RETENTION_DAYS,
) -> dict[str, Any]:
    deleted = prune_internet_map_collections(retention_days=retention_days)
    stream_deleted = prune_json_history_dir(STREAM_HISTORY_DIR, retention_days=max(stream_retention_days, 1))
    backtest_deleted = prune_json_history_dir(BACKTEST_HISTORY_DIR, retention_days=max(backtest_retention_days, 1))
    collector_deleted = prune_json_history_dir(COLLECTOR_HISTORY_DIR, retention_days=max(collector_retention_days, 1))
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "retention": {
            **build_internet_retention_policy(),
            "mongo_retention_days": retention_days,
            "stream_history_retention_days": stream_retention_days,
            "backtest_retention_days": backtest_retention_days,
            "collector_history_retention_days": collector_retention_days,
        },
        "deleted": deleted,
        "local_deleted": {
            "stream_history": stream_deleted,
            "backtest_history": backtest_deleted,
            "collector_history": collector_deleted,
        },
        "recent_counts": summarize_internet_map_collections(hours=24),
    }
