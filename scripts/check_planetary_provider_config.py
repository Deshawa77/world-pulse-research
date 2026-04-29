from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RUNTIME_ENV_VARS = [
    "PLANETARY_RUNTIME_ENABLED",
    "PLANETARY_RUNTIME_INTERVAL_SECONDS",
    "PLANETARY_RUNTIME_SOURCE_REFRESH_INTERVAL_SECONDS",
    "PLANETARY_RUNTIME_BACKTEST_INTERVAL_SECONDS",
    "PLANETARY_FLOOD_SIGNAL_RAIN_THRESHOLD",
    "PLANETARY_FLOOD_SIGNAL_WIND_THRESHOLD",
    "PLANETARY_CYCLONE_SIGNAL_WIND_THRESHOLD",
    "PLANETARY_FLOOD_ACTIVE_THRESHOLD",
    "PLANETARY_FLOOD_CRITICAL_THRESHOLD",
    "PLANETARY_CYCLONE_ACTIVE_THRESHOLD",
    "PLANETARY_CYCLONE_CRITICAL_THRESHOLD",
]

PROVIDER_PREFIXES = {
    "behavior_public_signal": ["REDDIT_", "TELEGRAM_"],
    "weather_context": ["OPENWEATHER_", "NOAA_"],
    "internet_live_telemetry": ["CLOUDFLARE_", "FASTLY_", "AKAMAI_", "BGP"],
    "ops_and_storage": ["MONGO_", "API_KEY", "ADMIN_KEY"],
}


def _matching_keys(prefixes: list[str]) -> list[str]:
    matches: list[str] = []
    for key in os.environ:
        if any(key.startswith(prefix) for prefix in prefixes):
            matches.append(key)
    return sorted(set(matches))


def main() -> int:
    runtime = {
        key: os.environ.get(key)
        for key in RUNTIME_ENV_VARS
    }
    provider_groups = {
        name: {
            "configured": bool(_matching_keys(prefixes)),
            "keys": _matching_keys(prefixes),
        }
        for name, prefixes in PROVIDER_PREFIXES.items()
    }
    payload = {
        "root": str(ROOT),
        "provider_template_present": (ROOT / "config" / "planetary_provider_activation.env.example").exists(),
        "secrets_file_env": os.environ.get("WORLD_PULSE_SECRETS_FILE"),
        "runtime_env": runtime,
        "provider_groups": provider_groups,
        "status": "ok",
        "notes": [
            "Missing groups do not mean the repo is broken; they indicate deployment activation work still needs environment wiring.",
            "Use subsystem-specific activation docs and deployment secrets for the exact provider variables in your target environment.",
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
