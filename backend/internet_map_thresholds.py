from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THRESHOLD_PATH = ROOT / "config" / "internet-map-thresholds.local.json"

DEFAULT_INTERNET_MAP_THRESHOLDS: dict[str, Any] = {
    "flow_signals": {
        "attack_index": 60.0,
        "hijack_suspect_score": 0.22,
        "control_plane_incident_score": 0.2,
        "dns_error_ratio": 0.14,
        "edge_error_rate": 0.16,
        "reroute_factor": 1.12,
    },
    "shutdown_signals": {
        "shutdown_risk": 62.0,
        "subscriber_availability_ratio": 0.8,
        "fixed_reachability_ratio": 0.82,
        "mobile_reachability_ratio": 0.8,
        "throughput_drop_pct": 22.0,
        "control_plane_incident_score": 0.18,
    },
    "alert_filters": {
        "min_attack_signals": 2,
        "attack_index_gate": 66.0,
        "attack_hijack_gate": 0.26,
        "attack_active_index": 74.0,
        "attack_active_signals": 4,
        "attack_investigate_signals": 3,
        "min_shutdown_signals": 2,
        "shutdown_risk_gate": 64.0,
        "shutdown_availability_gate": 0.78,
        "shutdown_active_risk": 74.0,
        "shutdown_active_availability": 0.68,
        "shutdown_reason_availability": 0.65,
        "shutdown_active_signals": 4,
        "shutdown_reason_control_plane": 0.18,
    },
}

_THRESHOLD_CACHE: dict[str, Any] | None = None


def _clean(value: Any) -> str:
    return str(value or "").strip().strip('"').strip("'")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_threshold_path() -> Path | None:
    configured = _clean(os.environ.get("INTERNET_MAP_THRESHOLD_CONFIG_FILE") or os.environ.get("INTERNET_MAP_THRESHOLDS_FILE"))
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else ROOT / path
    if DEFAULT_THRESHOLD_PATH.exists():
        return DEFAULT_THRESHOLD_PATH
    return None


def load_internet_map_thresholds(*, refresh: bool = False) -> dict[str, Any]:
    global _THRESHOLD_CACHE
    if _THRESHOLD_CACHE is not None and not refresh:
        return deepcopy(_THRESHOLD_CACHE)

    thresholds = deepcopy(DEFAULT_INTERNET_MAP_THRESHOLDS)
    path = _resolve_threshold_path()
    if path and path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            thresholds = _deep_merge(thresholds, payload)

    overrides_json = _clean(os.environ.get("INTERNET_MAP_THRESHOLD_OVERRIDES_JSON"))
    if overrides_json:
        try:
            override_payload = json.loads(overrides_json)
        except Exception:
            override_payload = None
        if isinstance(override_payload, dict):
            thresholds = _deep_merge(thresholds, override_payload)

    _THRESHOLD_CACHE = thresholds
    return deepcopy(_THRESHOLD_CACHE)


def threshold_value(section: str, key: str, default: float | int) -> float | int:
    thresholds = load_internet_map_thresholds()
    section_payload = thresholds.get(section) if isinstance(thresholds.get(section), dict) else {}
    value = section_payload.get(key, default)
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return int(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
