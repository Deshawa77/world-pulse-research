import os
import time
import uuid
import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from requests import Response

from database.mongo import db

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

RELIEFWEB_APPNAME = (os.getenv("RELIEFWEB_APPNAME") or "").strip()
OPENAQ_API_KEY = (os.getenv("OPENAQ_API_KEY") or "").strip()
FIRMS_MAP_KEY = (os.getenv("FIRMS_MAP_KEY") or "").strip()
NOAA_CDO_TOKEN = (os.getenv("NOAA_CDO_TOKEN") or "").strip()
EIA_API_KEY = (os.getenv("EIA_API_KEY") or "").strip()
FRED_API_KEY = (os.getenv("FRED_API_KEY") or "").strip()
ACLED_API_KEY = (os.getenv("ACLED_API_KEY") or "").strip()
ACLED_EMAIL = (os.getenv("ACLED_EMAIL") or "").strip()
ACLED_ACCESS_TOKEN = (os.getenv("ACLED_ACCESS_TOKEN") or "").strip()

CRITICAL_SOURCES = {
    "reliefweb",
    "usgs",
    "eonet",
    "openaq",
    "cisa_kev",
    "firms",
    "noaa_cdo",
    "eia",
    "fred",
    "acled",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
        if parsed != parsed:
            return fallback
        return parsed
    except Exception:
        return fallback


def _signal(source: str, signal_type: str, value: float, confidence: float, country: str = "GLB", lat: float | None = None, lon: float | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": f"world-state:{source}:{signal_type}:{country}:{uuid.uuid4().hex[:12]}",
        "source": source,
        "signal_type": signal_type,
        "value": round(_safe_float(value), 6),
        "confidence": max(0.0, min(1.0, _safe_float(confidence, 0.5))),
        "country": (country or "GLB").upper(),
        "timestamp_utc": _now_iso(),
        "lat": _safe_float(lat) if lat is not None else None,
        "lon": _safe_float(lon) if lon is not None else None,
        "meta": meta or {},
    }


def _health_row(source: str, status: str, latency_ms: float, error: str | None = None, rate_limited: bool = False, auth_failed: bool = False, records: int = 0) -> dict[str, Any]:
    now = _now_iso()
    return {
        "source": source,
        "status": status,
        "critical": source in CRITICAL_SOURCES,
        "latency_ms": round(max(latency_ms, 0.0), 3),
        "last_checked": now,
        "last_success": now if status == "up" else None,
        "rate_limited": bool(rate_limited),
        "auth_failed": bool(auth_failed),
        "error": error,
        "records": int(max(records, 0)),
    }


def _persist_source_health(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    coll = db["source_health"]
    for row in rows:
        row["updated_at"] = _now_iso()
        coll.update_one(
            {"source": row["source"]},
            {
                "$set": row,
                "$setOnInsert": {"created_at": row["updated_at"]},
            },
            upsert=True,
        )


def _fetch_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 20) -> tuple[dict[str, Any] | list[Any] | None, float, str | None, int | None]:
    started = time.perf_counter()
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        latency_ms = (time.perf_counter() - started) * 1000.0
        if response.status_code >= 400:
            return None, latency_ms, f"HTTP {response.status_code}", response.status_code
        return response.json(), latency_ms, None, response.status_code
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return None, latency_ms, str(exc), None


def _fetch_response(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 20) -> tuple[Response | None, float, str | None, int | None]:
    started = time.perf_counter()
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        latency_ms = (time.perf_counter() - started) * 1000.0
        if response.status_code >= 400:
            return None, latency_ms, f"HTTP {response.status_code}", response.status_code
        return response, latency_ms, None, response.status_code
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return None, latency_ms, str(exc), None


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _reliefweb() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not RELIEFWEB_APPNAME:
        return [], _health_row("reliefweb", "down", 0.0, error="missing RELIEFWEB_APPNAME", auth_failed=True)
    data, latency_ms, error, status_code = _fetch_json(
        "https://api.reliefweb.int/v2/reports",
        params={
            "appname": RELIEFWEB_APPNAME,
            "limit": 30,
            "profile": "full",
            "preset": "latest",
            "sort[]": "date:desc",
        },
        timeout=25,
    )
    if error or not isinstance(data, dict):
        return [], _health_row("reliefweb", "down", latency_ms, error=error, rate_limited=status_code == 429)

    rows = []
    for item in (data.get("data") or [])[:30]:
        fields = item.get("fields") or {}
        countries = fields.get("country") or []
        country = "GLB"
        if countries and isinstance(countries, list):
            first = countries[0] or {}
            country = str(first.get("iso3") or "GLB").upper()
        rows.append(_signal("reliefweb", "humanitarian_pressure", 1.0, 0.82, country=country, meta={"title": fields.get("title")}))
    return rows, _health_row("reliefweb", "up", latency_ms, records=len(rows))


def _usgs() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data, latency_ms, error, status_code = _fetch_json("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson", timeout=20)
    if error or not isinstance(data, dict):
        return [], _health_row("usgs", "down", latency_ms, error=error, rate_limited=status_code == 429)

    rows = []
    for feature in (data.get("features") or [])[:120]:
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates") or []
        mag = _safe_float(props.get("mag"), 0.0)
        intensity = min(max(mag / 8.0, 0.0), 1.0)
        lon = _safe_float(coords[0]) if len(coords) > 0 else None
        lat = _safe_float(coords[1]) if len(coords) > 1 else None
        rows.append(_signal("usgs", "disaster_intensity", intensity, 0.92, lat=lat, lon=lon, meta={"mag": mag, "place": props.get("place")}))
    return rows, _health_row("usgs", "up", latency_ms, records=len(rows))


def _eonet() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data, latency_ms, error, status_code = _fetch_json("https://eonet.gsfc.nasa.gov/api/v3/events", params={"status": "open", "limit": 100}, timeout=25)
    if error or not isinstance(data, dict):
        return [], _health_row("eonet", "down", latency_ms, error=error, rate_limited=status_code == 429)

    rows = []
    for event in (data.get("events") or [])[:100]:
        categories = event.get("categories") or []
        signal_type = "disaster_intensity"
        category_name = str(categories[0].get("title") if categories else "event").lower()
        if any(token in category_name for token in ("wildfire", "volcano", "severe", "flood", "drought", "storm")):
            signal_type = "disaster_intensity"
        geometries = event.get("geometry") or []
        for g in geometries[:1]:
            coords = g.get("coordinates") or []
            lon = _safe_float(coords[0]) if len(coords) > 0 else None
            lat = _safe_float(coords[1]) if len(coords) > 1 else None
            rows.append(_signal("eonet", signal_type, 0.8, 0.8, lat=lat, lon=lon, meta={"title": event.get("title"), "category": category_name}))
    return rows, _health_row("eonet", "up", latency_ms, records=len(rows))


def _openaq() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not OPENAQ_API_KEY:
        return [], _health_row("openaq", "down", 0.0, error="missing OPENAQ_API_KEY", auth_failed=True)
    headers = {"X-API-Key": OPENAQ_API_KEY}
    data, latency_ms, error, status_code = _fetch_json(
        "https://api.openaq.org/v3/parameters/2/latest",
        params={"limit": 1000},
        headers=headers,
        timeout=25,
    )
    if (error or not isinstance(data, dict)) and status_code == 404:
        data, latency_ms, error, status_code = _fetch_json(
            "https://api.openaq.org/v3/sensors",
            params={"parameters_id": 2, "limit": 200},
            headers=headers,
            timeout=25,
        )

    if error or not isinstance(data, dict):
        return [], _health_row("openaq", "down", latency_ms, error=error, auth_failed=status_code in (401, 403), rate_limited=status_code == 429)

    rows = []
    for item in (data.get("results") or [])[:200]:
        latest = item.get("latest") or {}
        coords = _first_non_empty(item.get("coordinates"), latest.get("coordinates")) or {}
        value = _safe_float(_first_non_empty(item.get("value"), latest.get("value")), 0.0)
        if value <= 0.0:
            continue
        country = str(
            _first_non_empty(
                ((item.get("country") or {}).get("code") if isinstance(item.get("country"), dict) else None),
                item.get("countryCode"),
                item.get("country"),
                "GLB",
            )
        ).upper()
        pollution_index = min(max(value / 75.0, 0.0), 1.0)
        rows.append(_signal("openaq", "air_quality_stress", pollution_index, 0.76, country=country, lat=coords.get("latitude"), lon=coords.get("longitude")))
    return rows, _health_row("openaq", "up", latency_ms, records=len(rows))


def _cisa_kev() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data, latency_ms, error, status_code = _fetch_json("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json", timeout=20)
    if error or not isinstance(data, dict):
        return [], _health_row("cisa_kev", "down", latency_ms, error=error, rate_limited=status_code == 429)

    vulns = data.get("vulnerabilities") or []
    pressure = min(max(len(vulns) / 1500.0, 0.0), 1.0)
    rows = [_signal("cisa_kev", "cyber_exploit_pressure", pressure, 0.85, country="GLB", meta={"count": len(vulns)})]
    return rows, _health_row("cisa_kev", "up", latency_ms, records=len(rows))


def _firms() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not FIRMS_MAP_KEY:
        return [], _health_row("firms", "down", 0.0, error="missing FIRMS_MAP_KEY", auth_failed=True)
    response, latency_ms, error, status_code = _fetch_response(
        f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/VIIRS_SNPP_NRT/world/1",
        headers={"Accept": "text/csv"},
        timeout=25,
    )
    if error or response is None:
        return [], _health_row("firms", "down", latency_ms, error=error, auth_failed=status_code in (401, 403), rate_limited=status_code == 429)

    body = response.content.decode("utf-8-sig", errors="replace") if response.content else (response.text or "")
    stripped = body.lstrip()
    if stripped.startswith("{") or stripped.startswith("[") or stripped.startswith("<"):
        preview = stripped.splitlines()[0][:180] if stripped else "unexpected FIRMS response"
        return [], _health_row("firms", "down", latency_ms, error=preview)

    reader = csv.DictReader(io.StringIO(body))
    rows = []
    for item in reader:
        if len(rows) >= 200:
            break
        lat = _safe_float(item.get("latitude"), 0.0)
        lon = _safe_float(item.get("longitude"), 0.0)
        frp = _safe_float(item.get("frp"), 0.0)
        intensity = min(max(frp / 50.0, 0.15), 1.0)
        rows.append(_signal("firms", "disaster_intensity", intensity, 0.8, country="GLB", lat=lat, lon=lon))
    if not rows and body.strip():
        return [], _health_row("firms", "down", latency_ms, error="no parseable FIRMS rows")
    return rows, _health_row("firms", "up", latency_ms, records=len(rows))


def _noaa_cdo() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not NOAA_CDO_TOKEN:
        return [], _health_row("noaa_cdo", "down", 0.0, error="missing NOAA_CDO_TOKEN", auth_failed=True)
    data, latency_ms, error, status_code = _fetch_json(
        "https://www.ncei.noaa.gov/cdo-web/api/v2/datasets",
        params={"limit": 1},
        headers={"token": NOAA_CDO_TOKEN},
        timeout=20,
    )
    if error:
        return [], _health_row("noaa_cdo", "down", latency_ms, error=error, auth_failed=status_code in (401, 403), rate_limited=status_code == 429)
    rows = [_signal("noaa_cdo", "disaster_intensity", 0.5, 0.62, country="GLB")]
    return rows, _health_row("noaa_cdo", "up", latency_ms, records=1)


def _eia() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not EIA_API_KEY:
        return [], _health_row("eia", "down", 0.0, error="missing EIA_API_KEY", auth_failed=True)
    data, latency_ms, error, status_code = _fetch_json(
        "https://api.eia.gov/v2/seriesid/PET.RWTC.D",
        params={"api_key": EIA_API_KEY},
        timeout=20,
    )
    observations = (((data.get("response") or {}).get("data")) or []) if isinstance(data, dict) else []
    if (error or not observations) and status_code == 404:
        data, latency_ms, error, status_code = _fetch_json(
            "https://api.eia.gov/series/",
            params={"api_key": EIA_API_KEY, "series_id": "PET.RWTC.D"},
            timeout=20,
        )
        if isinstance(data, dict):
            legacy_series = (data.get("series") or [])
            legacy_points = legacy_series[0].get("data") if legacy_series else []
            latest = legacy_points[0] if legacy_points else []
            period = latest[0] if isinstance(latest, list) and len(latest) > 0 else None
            value = latest[1] if isinstance(latest, list) and len(latest) > 1 else None
            observations = [{"period": period, "value": value}] if value is not None else []
    if error or not observations:
        return [], _health_row("eia", "down", latency_ms, error=error or "no EIA observations", auth_failed=status_code in (401, 403), rate_limited=status_code == 429)
    latest = observations[0] if observations else {}
    price = _safe_float(latest.get("value"), 0.0)
    stress = min(max(price / 120.0, 0.0), 1.0) if price > 0 else 0.5
    rows = [_signal("eia", "energy_stress", stress, 0.66, country="GLB", meta={"series_id": "PET.RWTC.D", "latest_value": price, "period": latest.get("period")})]
    return rows, _health_row("eia", "up", latency_ms, records=1)


def _fred() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not FRED_API_KEY:
        return [], _health_row("fred", "down", 0.0, error="missing FRED_API_KEY", auth_failed=True)
    data, latency_ms, error, status_code = _fetch_json(
        "https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": "VIXCLS", "api_key": FRED_API_KEY, "file_type": "json", "limit": 2},
        timeout=20,
    )
    if error or not isinstance(data, dict):
        return [], _health_row("fred", "down", latency_ms, error=error, auth_failed=status_code in (401, 403), rate_limited=status_code == 429)
    rows = [_signal("fred", "energy_stress", 0.45, 0.63, country="GLB", meta={"observations": len(data.get("observations") or [])})]
    return rows, _health_row("fred", "up", latency_ms, records=1)


def _acled() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not (ACLED_ACCESS_TOKEN or (ACLED_API_KEY and ACLED_EMAIL)):
        return [], _health_row("acled", "down", 0.0, error="missing ACLED_ACCESS_TOKEN or ACLED_EMAIL/API_KEY", auth_failed=True)

    headers = {"Authorization": f"Bearer {ACLED_ACCESS_TOKEN}"} if ACLED_ACCESS_TOKEN else None
    params = {"limit": 100, "event_date": _now_iso()[:10]}
    if not ACLED_ACCESS_TOKEN:
        params.update({"key": ACLED_API_KEY, "email": ACLED_EMAIL})

    data, latency_ms, error, status_code = _fetch_json(
        "https://acleddata.com/api/acled/read",
        params=params,
        headers=headers,
        timeout=25,
    )
    if (status_code in (401, 403)) and not ACLED_ACCESS_TOKEN:
        return [], _health_row("acled", "down", latency_ms, error="missing ACLED_ACCESS_TOKEN", auth_failed=True)
    if error or not isinstance(data, dict):
        return [], _health_row("acled", "down", latency_ms, error=error, auth_failed=status_code in (401, 403), rate_limited=status_code == 429)
    rows = []
    for item in (data.get("data") or [])[:100]:
        country = str(item.get("iso3") or "GLB").upper()
        rows.append(_signal("acled", "humanitarian_pressure", 0.9, 0.86, country=country, lat=item.get("latitude"), lon=item.get("longitude")))
    return rows, _health_row("acled", "up", latency_ms, records=len(rows))


def collect_world_state_signals() -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    health_rows: list[dict[str, Any]] = []
    for fn in (_reliefweb, _usgs, _eonet, _openaq, _cisa_kev, _firms, _noaa_cdo, _eia, _fred, _acled):
        try:
            source_signals, health = fn()
            signals.extend(source_signals)
            health_rows.append(health)
        except Exception as exc:
            name = getattr(fn, "__name__", "unknown").strip("_")
            health_rows.append(_health_row(name or "unknown", "down", 0.0, error=str(exc)))
    try:
        _persist_source_health(health_rows)
    except Exception:
        # Never fail collector loop because of health persistence.
        pass
    return signals

