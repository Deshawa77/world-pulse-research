from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.runtime_config import bootstrap_runtime_environment, runtime_secret_sources


FAMILIES = [
    {
        "family": "bgp_routing",
        "env_prefix": "INTERNET_MAP_BGP_FEED",
        "required_auth": ["BEARER_TOKEN", "API_KEY", "BASIC_AUTH", "HEADERS_JSON"],
    },
    {
        "family": "cdn_traffic",
        "env_prefix": "INTERNET_MAP_CDN_FEED",
        "required_auth": ["BEARER_TOKEN", "API_KEY", "BASIC_AUTH", "HEADERS_JSON"],
    },
    {
        "family": "isp_telemetry",
        "env_prefix": "INTERNET_MAP_ISP_FEED",
        "required_auth": ["BEARER_TOKEN", "API_KEY", "BASIC_AUTH", "HEADERS_JSON"],
    },
    {
        "family": "cloud_metrics",
        "env_prefix": "INTERNET_MAP_CLOUD_FEED",
        "required_auth": ["BEARER_TOKEN", "API_KEY", "BASIC_AUTH", "HEADERS_JSON"],
    },
]


def _clean(value: Any) -> str:
    return str(value or "").strip().strip('"').strip("'")


def _auth_mode(prefix: str) -> str:
    if _clean(os.environ.get(f"{prefix}_BEARER_TOKEN")):
        return "bearer"
    if _clean(os.environ.get(f"{prefix}_API_KEY")):
        return f"header:{_clean(os.environ.get(f'{prefix}_API_KEY_HEADER')) or 'x-api-key'}"
    if _clean(os.environ.get(f"{prefix}_BASIC_AUTH")):
        return "basic"
    if _clean(os.environ.get(f"{prefix}_HEADERS_JSON")):
        return "headers_json"
    return "none"


def _probe_url(url: str, timeout_sec: float) -> dict[str, Any]:
    request = Request(url, method="HEAD", headers={"User-Agent": "WorldPulseProviderCheck/1.0"})
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            return {"ok": True, "status_code": getattr(response, "status", 200)}
    except HTTPError as exc:
        return {"ok": False, "status_code": getattr(exc, "code", None), "error": str(exc)}
    except URLError as exc:
        return {"ok": False, "status_code": None, "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Internet Map provider endpoint and secret configuration.")
    parser.add_argument("--require-live", action="store_true", help="Fail if any source family is missing a URL or auth configuration.")
    parser.add_argument("--probe", action="store_true", help="Attempt HEAD requests against configured provider URLs.")
    parser.add_argument("--timeout-sec", type=float, default=5.0, help="Timeout for provider probes.")
    args = parser.parse_args()

    bootstrap_runtime_environment(PROJECT_ROOT)
    secret_state = runtime_secret_sources()
    families: list[dict[str, Any]] = []
    failed = False

    for spec in FAMILIES:
        prefix = spec["env_prefix"]
        url_value = _clean(os.environ.get(f"{prefix}_URL"))
        path_value = _clean(os.environ.get(f"{prefix}_PATH"))
        auth_mode = _auth_mode(prefix)
        live_ready = bool(url_value and auth_mode != "none")
        record: dict[str, Any] = {
            "family": spec["family"],
            "env_prefix": prefix,
            "url_configured": bool(url_value),
            "path_configured": bool(path_value),
            "auth_mode": auth_mode,
            "live_ready": live_ready,
            "timeout_sec": _clean(os.environ.get(f"{prefix}_TIMEOUT_SEC")) or _clean(os.environ.get("INTERNET_MAP_FEED_TIMEOUT_SEC")) or "6",
            "retries": _clean(os.environ.get(f"{prefix}_RETRIES")) or _clean(os.environ.get("INTERNET_MAP_FEED_RETRIES")) or "2",
        }
        if args.probe and url_value:
            record["probe"] = _probe_url(url_value, timeout_sec=max(1.0, args.timeout_sec))
            if not record["probe"].get("ok"):
                failed = True
        if args.require_live and not live_ready:
            failed = True
        families.append(record)

    payload = {
        "status": "ok" if not failed else "needs_attention",
        "environment": secret_state.get("environment"),
        "secret_source": secret_state.get("secret_source"),
        "production_safe": bool(secret_state.get("production_safe", True)),
        "families": families,
    }
    print(json.dumps(payload, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
