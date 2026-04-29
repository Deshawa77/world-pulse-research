from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen

from processing.internet_map_storage import collector_feed_cache_path


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data_lake" / "internet_map"
DEFAULT_FEED_TIMEOUT_SEC = 6.0
DEFAULT_FEED_RETRIES = 2
DEFAULT_FEED_CACHE_TTL_SEC = 90.0
DEFAULT_FEED_BACKOFF_SEC = 1.25
DEFAULT_RATE_LIMIT_FALLBACK_SEC = 45.0


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    return numeric if numeric == numeric else fallback


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def normalize_code(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().upper()
    return text or fallback


def normalize_region(origin: Any, destination: Any, region: Any, country: Any) -> str:
    region_text = str(region or "").strip().upper()
    if region_text:
        return region_text
    left = normalize_code(origin)
    right = normalize_code(destination)
    if left and right:
        return f"{left}->{right}"
    if left:
        return left
    return normalize_code(country, "GLB") or "GLB"


def _clean(value: Any) -> str:
    return str(value or "").strip().strip('"').strip("'")


def _resolve_path(value: str | None, default_path: Path) -> Path:
    text = _clean(value)
    if not text:
        return default_path
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    return ROOT / candidate


def _parse_payload(text: str, source: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    records: list[dict[str, Any]] = []
    for index, line in enumerate(stripped.splitlines()):
        row = line.strip()
        if not row:
            continue
        try:
            parsed = json.loads(row)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Unable to parse JSONL record {index} from {source}: {exc}") from exc
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("records", "items", "events", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _base_meta(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {
        "source_name": payload.get("source_name"),
        "stage": payload.get("stage"),
        "provenance": payload.get("provenance"),
        "measurement_mode": payload.get("measurement_mode"),
        "detail": payload.get("detail") or payload.get("advisory"),
        "captured_at": payload.get("captured_at") or payload.get("generated_at"),
    }


def _load_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _persist_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _cache_age_sec(cache_payload: dict[str, Any] | None) -> float | None:
    if not isinstance(cache_payload, dict):
        return None
    stamp = _clean(cache_payload.get("stored_at") or cache_payload.get("captured_at"))
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())


def _build_headers(env_prefix: str, *, conditional_cache: dict[str, Any] | None = None) -> tuple[dict[str, str], str]:
    headers = {"User-Agent": "WorldPulseInternetMap/2.0"}
    auth_mode = "none"

    bearer = _clean(os.environ.get(f"{env_prefix}_BEARER_TOKEN"))
    basic_auth = _clean(os.environ.get(f"{env_prefix}_BASIC_AUTH"))
    api_key = _clean(os.environ.get(f"{env_prefix}_API_KEY"))
    api_key_header = _clean(os.environ.get(f"{env_prefix}_API_KEY_HEADER")) or "x-api-key"
    headers_json = _clean(os.environ.get(f"{env_prefix}_HEADERS_JSON"))

    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
        auth_mode = "bearer"
    elif basic_auth:
        headers["Authorization"] = f"Basic {basic_auth}"
        auth_mode = "basic"
    elif api_key:
        headers[api_key_header] = api_key
        auth_mode = f"header:{api_key_header}"

    if headers_json:
        try:
            extra_headers = json.loads(headers_json)
        except Exception:
            extra_headers = None
        if isinstance(extra_headers, dict):
            for key, value in extra_headers.items():
                if key and value is not None:
                    headers[str(key)] = str(value)

    response_headers = conditional_cache.get("response_headers") if isinstance(conditional_cache, dict) else None
    if isinstance(response_headers, dict):
        etag = _clean(response_headers.get("etag"))
        last_modified = _clean(response_headers.get("last_modified"))
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

    return headers, auth_mode


def _append_query_params(url_value: str, env_prefix: str) -> str:
    query_json = _clean(os.environ.get(f"{env_prefix}_QUERY_PARAMS_JSON"))
    if not query_json:
        return url_value
    try:
        extra = json.loads(query_json)
    except Exception:
        return url_value
    if not isinstance(extra, dict):
        return url_value

    parts = urlsplit(url_value)
    merged = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in extra.items():
        if key and value is not None:
            merged[str(key)] = str(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(merged), parts.fragment))


def _rate_limit_block(cache_payload: dict[str, Any] | None) -> float:
    if not isinstance(cache_payload, dict):
        return 0.0
    return safe_float((cache_payload.get("rate_limit") or {}).get("blocked_until_ts"), 0.0)


def _payload_from_cache(
    cache_payload: dict[str, Any] | None,
    *,
    family: str,
    default_source_name: str,
    default_stage: str = "cached",
    errors: list[str] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(cache_payload, dict):
        return None
    selected_payload = cache_payload.get("payload")
    records = _extract_records(selected_payload)
    if not records:
        return None
    selected_meta = _base_meta(selected_payload)
    age_sec = _cache_age_sec(cache_payload)
    return {
        "records": records,
        "source_name": str(selected_meta.get("source_name") or cache_payload.get("source_name") or default_source_name),
        "stage": str(selected_meta.get("stage") or cache_payload.get("stage") or default_stage),
        "provenance": str(selected_meta.get("provenance") or cache_payload.get("provenance") or "collector_cache"),
        "measurement_mode": str(selected_meta.get("measurement_mode") or cache_payload.get("measurement_mode") or "direct"),
        "detail": selected_meta.get("detail") or cache_payload.get("detail"),
        "feed_origin": str(cache_payload.get("feed_origin") or "cache"),
        "captured_at": str(selected_meta.get("captured_at") or cache_payload.get("captured_at") or iso_now()),
        "errors": list(errors or []),
        "served_from_cache": True,
        "cache_hit": True,
        "cache_age_sec": round(age_sec or 0.0, 3),
        "request_attempts": 0,
        "rate_limited": bool((cache_payload.get("rate_limit") or {}).get("active")),
        "auth_mode": str(cache_payload.get("auth_mode") or "cache"),
        "response_headers": cache_payload.get("response_headers") or {},
        "family": family,
    }


def _store_cache(
    cache_path: Path,
    *,
    payload: Any,
    meta: dict[str, Any],
    feed_origin: str,
    auth_mode: str,
    response_headers: dict[str, Any] | None,
    status_code: int | None,
    rate_limit: dict[str, Any] | None = None,
) -> None:
    stored = {
        "stored_at": iso_now(),
        "captured_at": str(meta.get("captured_at") or iso_now()),
        "source_name": meta.get("source_name"),
        "stage": meta.get("stage"),
        "provenance": meta.get("provenance"),
        "measurement_mode": meta.get("measurement_mode"),
        "detail": meta.get("detail"),
        "payload": payload,
        "feed_origin": feed_origin,
        "auth_mode": auth_mode,
        "response_headers": response_headers or {},
        "last_status_code": status_code,
        "rate_limit": rate_limit or {"active": False, "blocked_until_ts": 0.0},
    }
    _persist_cache(cache_path, stored)


def _http_response_headers(response) -> dict[str, str]:
    return {
        "etag": _clean(response.headers.get("ETag")),
        "last_modified": _clean(response.headers.get("Last-Modified")),
        "retry_after": _clean(response.headers.get("Retry-After")),
        "content_type": _clean(response.headers.get("Content-Type")),
    }


def _retry_after_seconds(value: str | None) -> float:
    text = _clean(value)
    if not text:
        return DEFAULT_RATE_LIMIT_FALLBACK_SEC
    try:
        return max(1.0, float(text))
    except ValueError:
        return DEFAULT_RATE_LIMIT_FALLBACK_SEC


def load_feed_records(
    *,
    family: str,
    default_path: Path,
    env_prefix: str,
    default_source_name: str,
    refresh: bool = True,
) -> dict[str, Any]:
    url_value = _clean(os.environ.get(f"{env_prefix}_URL"))
    path_value = _clean(os.environ.get(f"{env_prefix}_PATH"))
    timeout_sec = max(1.0, safe_float(os.environ.get(f"{env_prefix}_TIMEOUT_SEC") or os.environ.get("INTERNET_MAP_FEED_TIMEOUT_SEC"), DEFAULT_FEED_TIMEOUT_SEC))
    retries = max(0, safe_int(os.environ.get(f"{env_prefix}_RETRIES") or os.environ.get("INTERNET_MAP_FEED_RETRIES"), DEFAULT_FEED_RETRIES))
    backoff_sec = max(0.2, safe_float(os.environ.get(f"{env_prefix}_BACKOFF_SEC") or os.environ.get("INTERNET_MAP_FEED_BACKOFF_SEC"), DEFAULT_FEED_BACKOFF_SEC))
    cache_ttl_sec = max(5.0, safe_float(os.environ.get(f"{env_prefix}_CACHE_TTL_SEC") or os.environ.get("INTERNET_MAP_COLLECTOR_CACHE_TTL_SEC"), DEFAULT_FEED_CACHE_TTL_SEC))
    errors: list[str] = []
    cache_path = collector_feed_cache_path(family)
    cache_payload = _load_cache(cache_path)
    cached = _payload_from_cache(cache_payload, family=family, default_source_name=default_source_name)
    cached_age = _cache_age_sec(cache_payload)

    if not refresh and cached is not None:
        cached["detail"] = cached.get("detail") or f"Cached {family} collector bundle served without live refresh."
        return cached

    blocked_until_ts = _rate_limit_block(cache_payload)
    if blocked_until_ts > time.time() and cached is not None:
        wait_sec = round(max(0.0, blocked_until_ts - time.time()), 3)
        errors.append(f"{family} rate-limited; serving cached payload for {wait_sec}s")
        cached["errors"] = errors
        cached["rate_limited"] = True
        cached["next_refresh_after_sec"] = wait_sec
        return cached

    if cached is not None and cached_age is not None and cached_age <= cache_ttl_sec and not url_value:
        cached["detail"] = cached.get("detail") or f"Recent {family} cache reused from persisted collector snapshot."
        return cached

    selected_payload: Any = None
    selected_meta: dict[str, Any] = {}
    source_label = default_source_name
    stage = "scaffold"
    provenance = "runtime_scaffold"
    measurement_mode = "synthetic"
    feed_origin = "none"
    served_from_cache = False
    request_attempts = 0
    auth_mode = "none"
    response_headers: dict[str, Any] = {}

    if url_value:
        request_url = _append_query_params(url_value, env_prefix)
        headers, auth_mode = _build_headers(env_prefix, conditional_cache=cache_payload)
        for attempt in range(retries + 1):
            request_attempts = attempt + 1
            request = Request(request_url, headers=headers)
            try:
                with urlopen(request, timeout=timeout_sec) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    response_headers = _http_response_headers(response)
                    selected_payload = _parse_payload(response.read().decode(charset), request_url)
                selected_meta = _base_meta(selected_payload)
                source_label = str(selected_meta.get("source_name") or default_source_name)
                stage = str(selected_meta.get("stage") or "live")
                provenance = str(selected_meta.get("provenance") or "configured_url")
                measurement_mode = str(selected_meta.get("measurement_mode") or "direct")
                feed_origin = "url"
                _store_cache(
                    cache_path,
                    payload=selected_payload,
                    meta={**selected_meta, "source_name": source_label, "stage": stage, "provenance": provenance, "measurement_mode": measurement_mode},
                    feed_origin=feed_origin,
                    auth_mode=auth_mode,
                    response_headers=response_headers,
                    status_code=200,
                )
                break
            except HTTPError as exc:
                status_code = getattr(exc, "code", None)
                response_headers = {
                    "retry_after": _clean(exc.headers.get("Retry-After")) if exc.headers else "",
                    "etag": "",
                    "last_modified": "",
                    "content_type": _clean(exc.headers.get("Content-Type")) if exc.headers else "",
                }
                if status_code == 304 and cached is not None:
                    cached["detail"] = cached.get("detail") or f"{family} feed returned not-modified; cached payload reused."
                    return cached
                if status_code == 429 and cached is not None:
                    retry_after_sec = _retry_after_seconds(response_headers.get("retry_after"))
                    rate_limit = {"active": True, "blocked_until_ts": time.time() + retry_after_sec}
                    _store_cache(
                        cache_path,
                        payload=cache_payload.get("payload") if isinstance(cache_payload, dict) else selected_payload,
                        meta={**(selected_meta or _base_meta((cache_payload or {}).get("payload"))), "source_name": source_label or default_source_name},
                        feed_origin=(cache_payload or {}).get("feed_origin") or "cache",
                        auth_mode=auth_mode,
                        response_headers=(cache_payload or {}).get("response_headers") or {},
                        status_code=429,
                        rate_limit=rate_limit,
                    )
                    errors.append(f"{family} provider rate-limited request; retry after {retry_after_sec:.1f}s")
                    cached = _payload_from_cache(_load_cache(cache_path), family=family, default_source_name=default_source_name, errors=errors)
                    if cached is not None:
                        cached["next_refresh_after_sec"] = retry_after_sec
                        cached["rate_limited"] = True
                        return cached
                if status_code and status_code >= 500 and attempt < retries:
                    time.sleep(backoff_sec * (attempt + 1))
                    continue
                errors.append(f"{family} url feed unavailable: HTTP {status_code or 'error'}")
                break
            except (OSError, ValueError, URLError) as exc:
                if attempt < retries:
                    time.sleep(backoff_sec * (attempt + 1))
                    continue
                errors.append(f"{family} url feed unavailable: {exc}")

    if selected_payload is None:
        path = _resolve_path(path_value, default_path)
        if path.exists():
            try:
                selected_payload = _parse_payload(path.read_text(encoding="utf-8"), str(path))
                selected_meta = _base_meta(selected_payload)
                source_label = str(selected_meta.get("source_name") or default_source_name)
                stage = str(selected_meta.get("stage") or "direct-file")
                provenance = str(selected_meta.get("provenance") or ("configured_file" if path_value else "repo_export"))
                measurement_mode = str(selected_meta.get("measurement_mode") or "direct")
                feed_origin = "file"
                _store_cache(
                    cache_path,
                    payload=selected_payload,
                    meta={**selected_meta, "source_name": source_label, "stage": stage, "provenance": provenance, "measurement_mode": measurement_mode},
                    feed_origin=feed_origin,
                    auth_mode="file",
                    response_headers={},
                    status_code=200,
                )
            except (OSError, ValueError) as exc:
                errors.append(f"{family} file feed unavailable: {exc}")
        elif cached is not None:
            errors.append(f"{family} live source unavailable; serving persisted cache")
            cached["errors"] = errors
            return cached

    records = _extract_records(selected_payload)
    if not records and cached is not None:
        errors.append(f"{family} feed returned no records; serving cached payload")
        cached["errors"] = errors
        return cached

    if not records:
        stage = "scaffold"
        provenance = "runtime_scaffold"
        measurement_mode = "synthetic"
        feed_origin = "none"

    return {
        "records": records,
        "source_name": source_label,
        "stage": stage,
        "provenance": provenance,
        "measurement_mode": measurement_mode,
        "detail": selected_meta.get("detail"),
        "feed_origin": feed_origin,
        "captured_at": str(selected_meta.get("captured_at") or iso_now()),
        "errors": errors,
        "served_from_cache": served_from_cache,
        "cache_hit": False,
        "cache_age_sec": round(cached_age or 0.0, 3) if cached_age is not None else None,
        "request_attempts": request_attempts,
        "rate_limited": False,
        "auth_mode": auth_mode,
        "response_headers": response_headers,
    }
