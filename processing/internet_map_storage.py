from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

MONITORING_ROOT = ROOT / "monitoring" / "internet_map"
STREAM_ROOT = MONITORING_ROOT / "stream"
STREAM_LATEST_JSON = STREAM_ROOT / "latest.json"
STREAM_HISTORY_DIR = STREAM_ROOT / "history"

BACKTEST_ROOT = MONITORING_ROOT / "backtests"
BACKTEST_LATEST_JSON = BACKTEST_ROOT / "latest.json"
BACKTEST_HISTORY_DIR = BACKTEST_ROOT / "history"

COLLECTOR_ROOT = MONITORING_ROOT / "collectors"
COLLECTOR_LATEST_JSON = COLLECTOR_ROOT / "latest.json"
COLLECTOR_HISTORY_DIR = COLLECTOR_ROOT / "history"
COLLECTOR_FEED_CACHE_DIR = COLLECTOR_ROOT / "feeds"

RUNTIME_ROOT = MONITORING_ROOT / "runtime"
RUNTIME_STATUS_JSON = RUNTIME_ROOT / "status.json"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _recent_history(directory: Path, *, limit: int = 24) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    items: list[tuple[float, dict[str, Any]]] = []
    for path in directory.glob("*.json"):
        payload = _load_json(path)
        if not payload:
            continue
        stamp = str(payload.get("captured_at") or payload.get("generated_at") or "")
        try:
            ts = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() if stamp else path.stat().st_mtime
        except Exception:
            ts = path.stat().st_mtime
        items.append((ts, payload))
    items.sort(key=lambda row: row[0], reverse=True)
    return [payload for _, payload in items[: max(1, int(limit))]]


def load_internet_map_stream_snapshot() -> dict[str, Any] | None:
    return _load_json(STREAM_LATEST_JSON)


def persist_internet_map_stream_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_dir(STREAM_HISTORY_DIR)
    captured_at = str(payload.get("captured_at") or datetime.now(timezone.utc).isoformat())
    run_id = str(payload.get("run_id") or captured_at.replace(":", "").replace("-", ""))
    latest_path = STREAM_LATEST_JSON
    history_path = STREAM_HISTORY_DIR / f"{run_id}.json"
    _write_json(latest_path, payload)
    _write_json(history_path, payload)
    return {"status": "ok", "latest_path": str(latest_path), "history_path": str(history_path), "run_id": run_id}


def load_recent_internet_map_history(limit: int = 24) -> list[dict[str, Any]]:
    return _recent_history(STREAM_HISTORY_DIR, limit=limit)


def load_internet_map_backtest_snapshot() -> dict[str, Any] | None:
    return _load_json(BACKTEST_LATEST_JSON)


def persist_internet_map_backtest_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_dir(BACKTEST_HISTORY_DIR)
    generated_at = str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat())
    run_id = str(payload.get("run_id") or generated_at.replace(":", "").replace("-", ""))
    latest_path = BACKTEST_LATEST_JSON
    history_path = BACKTEST_HISTORY_DIR / f"{run_id}.json"
    _write_json(latest_path, payload)
    _write_json(history_path, payload)
    return {"status": "ok", "latest_path": str(latest_path), "history_path": str(history_path), "run_id": run_id}


def load_recent_internet_map_backtests(limit: int = 12) -> list[dict[str, Any]]:
    return _recent_history(BACKTEST_HISTORY_DIR, limit=limit)


def load_internet_map_collector_bundle() -> dict[str, Any] | None:
    return _load_json(COLLECTOR_LATEST_JSON)


def persist_internet_map_collector_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_dir(COLLECTOR_HISTORY_DIR)
    captured_at = str(payload.get("captured_at") or datetime.now(timezone.utc).isoformat())
    run_id = str(payload.get("run_id") or captured_at.replace(":", "").replace("-", ""))
    latest_path = COLLECTOR_LATEST_JSON
    history_path = COLLECTOR_HISTORY_DIR / f"{run_id}.json"
    _write_json(latest_path, payload)
    _write_json(history_path, payload)
    return {"status": "ok", "latest_path": str(latest_path), "history_path": str(history_path), "run_id": run_id}


def load_recent_internet_map_collector_history(limit: int = 24) -> list[dict[str, Any]]:
    return _recent_history(COLLECTOR_HISTORY_DIR, limit=limit)


def collector_feed_cache_path(family: str) -> Path:
    safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(family or "unknown").strip().lower())
    return COLLECTOR_FEED_CACHE_DIR / f"{safe_name}.json"


def load_internet_map_runtime_status() -> dict[str, Any] | None:
    return _load_json(RUNTIME_STATUS_JSON)


def persist_internet_map_runtime_status(payload: dict[str, Any]) -> dict[str, Any]:
    _write_json(RUNTIME_STATUS_JSON, payload)
    return {"status": "ok", "path": str(RUNTIME_STATUS_JSON)}


def prune_json_history_dir(directory: Path, *, retention_days: int = 30) -> int:
    if retention_days <= 0 or not directory.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = 0
    for path in directory.glob("*.json"):
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except Exception:
            continue
        if modified < cutoff:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                continue
    return deleted
