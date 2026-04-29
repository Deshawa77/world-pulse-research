from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "config" / "runtime-secrets.local.json"
PROVIDER_PREFIXES = (
    "INTERNET_MAP_BGP_FEED_",
    "INTERNET_MAP_CDN_FEED_",
    "INTERNET_MAP_ISP_FEED_",
    "INTERNET_MAP_CLOUD_FEED_",
    "INTERNET_MAP_THRESHOLD_CONFIG_FILE",
    "WORLD_PULSE_ENVIRONMENT",
    "WORLD_PULSE_ENABLE_DOTENV_FALLBACK",
    "INTERNET_MAP_RUNTIME_",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _secret(length: int = 48) -> str:
    return secrets.token_urlsafe(length)


def _preserve_runtime_settings(existing: dict[str, Any]) -> dict[str, Any]:
    preserved: dict[str, Any] = {}
    for key, value in existing.items():
        if any(str(key).startswith(prefix) for prefix in PROVIDER_PREFIXES):
            preserved[str(key)] = value
    return preserved


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a rotated runtime secret file for World Pulse deployments.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to write the rotated secret JSON file.")
    parser.add_argument("--source", default="", help="Optional existing secret file to preserve non-rotated provider settings from.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file.")
    args = parser.parse_args()

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    if output_path.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite existing secret file without --force: {output_path}")

    source_path = Path(args.source) if args.source else output_path
    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path
    existing = _load_json(source_path)
    payload = {
        "WORLD_PULSE_ENVIRONMENT": existing.get("WORLD_PULSE_ENVIRONMENT") or "production",
        "WORLD_PULSE_ENABLE_DOTENV_FALLBACK": "false",
        "JWT_SECRET": _secret(48),
        "API_KEY": _secret(24),
        "ADMIN_KEY": _secret(24),
        "ADMIN_INVITE_CODE": _secret(16),
        **_preserve_runtime_settings(existing),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "output": str(output_path),
        "generated_keys": ["JWT_SECRET", "API_KEY", "ADMIN_KEY", "ADMIN_INVITE_CODE"],
        "preserved_provider_settings": sorted(key for key in payload if key.startswith("INTERNET_MAP_") or key.startswith("WORLD_PULSE_")),
    }, indent=2))


if __name__ == "__main__":
    main()
