from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


_SECRET_LOAD_STATE: dict[str, Any] = {
    "environment": "development",
    "dotenv_path": None,
    "dotenv_loaded": False,
    "dotenv_permitted": True,
    "secret_file": None,
    "secret_file_loaded": False,
    "secret_keys": [],
    "secret_candidates": [],
    "secret_source": "environment",
    "production_safe": True,
}


_ENVIRONMENT_ALIASES = {
    "dev": "development",
    "development": "development",
    "local": "development",
    "test": "test",
    "testing": "test",
    "stage": "staging",
    "staging": "staging",
    "prod": "production",
    "production": "production",
}


def _clean(value: Any) -> str:
    return str(value or "").strip().strip('"').strip("'")


def _bool_env(name: str, default: bool = False) -> bool:
    text = _clean(os.environ.get(name))
    if not text:
        return default
    return text.lower() in {"1", "true", "yes", "on"}


def runtime_environment_name() -> str:
    raw = _clean(os.environ.get("WORLD_PULSE_ENVIRONMENT") or os.environ.get("APP_ENV") or os.environ.get("ENVIRONMENT") or "development").lower()
    return _ENVIRONMENT_ALIASES.get(raw, raw or "development")


def _dotenv_allowed_default(environment: str) -> bool:
    return environment in {"development", "test"}


def _resolve_secret_candidates(root: Path, environment: str) -> list[Path]:
    explicit = _clean(os.environ.get("WORLD_PULSE_SECRETS_FILE") or os.environ.get("WORLD_PULSE_SECRET_FILE"))
    candidates: list[Path] = []
    if explicit:
        candidate = Path(explicit)
        candidates.append(candidate if candidate.is_absolute() else root / candidate)
    else:
        if environment in {"development", "test"}:
            candidates.append(root / "config" / "runtime-secrets.local.json")
        if environment not in {"development", "test"}:
            candidates.append(root / "config" / f"runtime-secrets.{environment}.json")
        candidates.append(root / "config" / "runtime-secrets.json")
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _flatten_secret_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("env"), dict):
        env_payload = {str(key): value for key, value in payload["env"].items()}
        merged = {**payload, **env_payload}
        merged.pop("env", None)
        return merged
    return payload


def bootstrap_runtime_environment(project_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[1]
    environment = runtime_environment_name()
    preexisting_keys = set(os.environ.keys())

    _SECRET_LOAD_STATE.update(
        {
            "environment": environment,
            "dotenv_path": None,
            "dotenv_loaded": False,
            "dotenv_permitted": _dotenv_allowed_default(environment),
            "secret_file": None,
            "secret_file_loaded": False,
            "secret_keys": [],
            "secret_candidates": [],
            "secret_source": "environment",
            "production_safe": True,
        }
    )

    dotenv_path = Path(_clean(os.environ.get("WORLD_PULSE_DOTENV_PATH")) or (root / ".env"))
    enable_dotenv = _bool_env("WORLD_PULSE_ENABLE_DOTENV_FALLBACK", default=_dotenv_allowed_default(environment))
    _SECRET_LOAD_STATE["dotenv_permitted"] = enable_dotenv
    if enable_dotenv and dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)
        _SECRET_LOAD_STATE["dotenv_loaded"] = True
        _SECRET_LOAD_STATE["dotenv_path"] = str(dotenv_path)
        _SECRET_LOAD_STATE["secret_source"] = "dotenv"

    secret_candidates = _resolve_secret_candidates(root, environment)
    _SECRET_LOAD_STATE["secret_candidates"] = [str(path) for path in secret_candidates]

    for secret_path in secret_candidates:
        if not secret_path.exists():
            continue
        try:
            payload = json.loads(secret_path.read_text(encoding="utf-8"))
        except Exception:
            payload = None
        if not isinstance(payload, dict):
            continue
        payload = _flatten_secret_payload(payload)
        loaded_keys: list[str] = []
        for key, value in payload.items():
            if key in preexisting_keys or value in (None, ""):
                continue
            os.environ[str(key)] = str(value)
            loaded_keys.append(str(key))
        _SECRET_LOAD_STATE["secret_file_loaded"] = True
        _SECRET_LOAD_STATE["secret_file"] = str(secret_path)
        _SECRET_LOAD_STATE["secret_keys"] = sorted(loaded_keys)
        _SECRET_LOAD_STATE["secret_source"] = "secret_file"
        break

    if environment == "production":
        _SECRET_LOAD_STATE["production_safe"] = bool(_SECRET_LOAD_STATE.get("secret_file_loaded") or not _SECRET_LOAD_STATE.get("dotenv_loaded"))
    else:
        _SECRET_LOAD_STATE["production_safe"] = True

    return dict(_SECRET_LOAD_STATE)


def runtime_secret_sources() -> dict[str, Any]:
    return dict(_SECRET_LOAD_STATE)
