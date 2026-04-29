from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "data_lake" / "planetary_intelligence" / "runtime"
BEHAVIOR_ROOT = RUNTIME_ROOT / "behavior_surface"
BEHAVIOR_HISTORY_DIR = BEHAVIOR_ROOT / "history"
BEHAVIOR_LATEST_JSON = BEHAVIOR_ROOT / "latest.json"
COMMAND_ROOT = RUNTIME_ROOT / "command_layer"
COMMAND_HISTORY_DIR = COMMAND_ROOT / "history"
COMMAND_LATEST_JSON = COMMAND_ROOT / "latest.json"
MANIFEST_ROOT = RUNTIME_ROOT / "manifests"
MANIFEST_HISTORY_DIR = MANIFEST_ROOT / "history"
MANIFEST_LATEST_JSON = MANIFEST_ROOT / "latest.json"
MAP_REPLAY_ROOT = RUNTIME_ROOT / "map_replay"
MAP_REPLAY_HISTORY_DIR = MAP_REPLAY_ROOT / "history"
MAP_REPLAY_LATEST_JSON = MAP_REPLAY_ROOT / "latest.json"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _paths(root: str | Path | None = None) -> dict[str, Path]:
    base = Path(root) if root is not None else RUNTIME_ROOT
    return {
        "behavior_latest": base / "behavior_surface" / "latest.json",
        "behavior_history": base / "behavior_surface" / "history",
        "command_latest": base / "command_layer" / "latest.json",
        "command_history": base / "command_layer" / "history",
        "manifest_latest": base / "manifests" / "latest.json",
        "manifest_history": base / "manifests" / "history",
        "map_replay_latest": base / "map_replay" / "latest.json",
        "map_replay_history": base / "map_replay" / "history",
    }


def _file_slug(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    return "".join(char for char in text if char.isalnum() or char in {"-", "_"}) or "run"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _timestamp_age_seconds(value: Any) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


def persist_planetary_runtime_batch(
    *,
    behavior_surface: dict[str, Any],
    command_layer: dict[str, Any],
    map_replay_frame: dict[str, Any],
    runtime_status: dict[str, Any],
    run_id: str,
    captured_at: str,
    mode: str = "online",
    root: str | Path | None = None,
) -> dict[str, Any]:
    paths = _paths(root)
    safe_run_id = _file_slug(run_id)

    behavior_history_path = paths["behavior_history"] / f"runtime_{safe_run_id}.json"
    command_history_path = paths["command_history"] / f"runtime_{safe_run_id}.json"
    manifest_history_path = paths["manifest_history"] / f"runtime_{safe_run_id}.json"
    map_replay_history_path = paths["map_replay_history"] / f"runtime_{safe_run_id}.json"

    _write_json(paths["behavior_latest"], behavior_surface)
    _write_json(behavior_history_path, behavior_surface)
    _write_json(paths["command_latest"], command_layer)
    _write_json(command_history_path, command_layer)
    _write_json(paths["map_replay_latest"], map_replay_frame)
    _write_json(map_replay_history_path, map_replay_frame)

    manifest = {
        "captured_at": captured_at,
        "run_id": run_id,
        "mode": mode,
        "contract_version": "phase-0.8",
        "platform_scope": "planetary_runtime",
        "behavior_country_count": len(behavior_surface.get("top_countries") or []),
        "behavior_replay_count": len(behavior_surface.get("replay_frames") or []),
        "command_theater_count": len(command_layer.get("theaters") or []),
        "command_watchlist_count": len(command_layer.get("incident_watchlist") or []),
        "graph_focus_count": len(command_layer.get("graph_command_focus") or []),
        "disaster_focus_count": len(command_layer.get("disaster_command_focus") or []),
        "map_replay_frame_count": 1 if map_replay_frame else 0,
        "behavior_latest_path": str(paths["behavior_latest"]),
        "behavior_history_path": str(behavior_history_path),
        "command_latest_path": str(paths["command_latest"]),
        "command_history_path": str(command_history_path),
        "map_replay_latest_path": str(paths["map_replay_latest"]),
        "map_replay_history_path": str(map_replay_history_path),
        "runtime_status": runtime_status,
    }
    _write_json(paths["manifest_latest"], manifest)
    _write_json(manifest_history_path, manifest)
    return {
        "status": "ok",
        **manifest,
        "manifest_latest_path": str(paths["manifest_latest"]),
        "manifest_history_path": str(manifest_history_path),
    }


def load_latest_planetary_runtime_manifest(root: str | Path | None = None) -> dict[str, Any]:
    payload = _read_json(_paths(root)["manifest_latest"]) or {
        "status": "missing",
        "contract_version": "phase-0.8",
        "platform_scope": "planetary_runtime",
        "behavior_country_count": 0,
        "behavior_replay_count": 0,
        "command_theater_count": 0,
        "command_watchlist_count": 0,
        "graph_focus_count": 0,
        "disaster_focus_count": 0,
        "map_replay_frame_count": 0,
        "runtime_status": {},
    }
    payload["freshness_sec"] = _timestamp_age_seconds(payload.get("captured_at"))
    return payload


def load_latest_planetary_behavior_surface(root: str | Path | None = None) -> dict[str, Any]:
    return _read_json(_paths(root)["behavior_latest"]) or {}


def load_latest_planetary_command_layer(root: str | Path | None = None) -> dict[str, Any]:
    return _read_json(_paths(root)["command_latest"]) or {}


def load_latest_planetary_map_replay_frame(root: str | Path | None = None) -> dict[str, Any]:
    return _read_json(_paths(root)["map_replay_latest"]) or {}


def load_recent_planetary_map_replay_frames(
    root: str | Path | None = None,
    *,
    limit: int = 24,
) -> list[dict[str, Any]]:
    paths = _paths(root)
    rows: list[dict[str, Any]] = []
    history_dir = paths["map_replay_history"]
    if history_dir.exists():
        for path in sorted(history_dir.glob("runtime_*.json")):
            payload = _read_json(path)
            if isinstance(payload, dict):
                rows.append(payload)
    if not rows:
        latest = load_latest_planetary_map_replay_frame(root)
        if latest:
            rows.append(latest)
    rows.sort(key=lambda row: str(row.get("frame_timestamp") or row.get("captured_at") or ""), reverse=True)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        frame_id = str(row.get("frame_id") or row.get("run_id") or "").strip()
        if not frame_id or frame_id in seen:
            continue
        seen.add(frame_id)
        deduped.append(row)
        if len(deduped) >= max(1, int(limit)):
            break
    return deduped
