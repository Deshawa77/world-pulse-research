import os
import time
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

from backend.kafka_client import send_to_kafka
from database.mongo import db, insert
from processing.signal_taxonomy import build_signal_metadata

load_dotenv(override=True)

OPENSKY_API_URL = (os.getenv("OPENSKY_API_URL") or "https://opensky-network.org/api/states/all").strip()
OPENSKY_AUTH_URL = (os.getenv("OPENSKY_AUTH_URL") or "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token").strip()
OPENSKY_CLIENT_ID = (os.getenv("OPENSKY_CLIENT_ID") or "").strip()
OPENSKY_CLIENT_SECRET = (os.getenv("OPENSKY_CLIENT_SECRET") or "").strip()
OPENSKY_TIMEOUT_SEC = int(os.getenv("OPENSKY_TIMEOUT_SEC") or 20)
KAFKA_TOPIC = "aviation_topic"
SOURCE_NAME = "opensky"

_TOKEN_CACHE: dict[str, Any] = {"token": None, "expires_at": 0.0}

AVIATION_HUBS: dict[str, tuple[float, float]] = {
    "USA": (39.8, -98.6), "CAN": (56.1, -106.3), "MEX": (23.6, -102.6), "BRA": (-14.2, -51.9),
    "ARG": (-38.4, -63.6), "GBR": (55.4, -3.4), "FRA": (46.2, 2.2), "DEU": (51.2, 10.4),
    "ESP": (40.4, -3.7), "ITA": (42.8, 12.5), "RUS": (61.5, 105.3), "CHN": (35.9, 104.2),
    "IND": (20.6, 78.9), "JPN": (36.2, 138.3), "KOR": (36.5, 127.9), "AUS": (-25.3, 133.8),
    "ZAF": (-30.6, 22.9), "EGY": (26.8, 30.8), "NGA": (9.1, 8.7), "TUR": (38.9, 35.2),
    "SAU": (23.9, 45.1), "IDN": (-0.8, 113.9), "PAK": (30.4, 69.3), "UKR": (48.4, 31.2),
    "LKA": (7.9, 80.7), "DZA": (28.0, 1.7), "IRN": (32.4, 53.7), "AFG": (33.9, 67.7),
    "BGD": (23.7, 90.4), "NPL": (28.4, 84.1), "MMR": (21.2, 96.0), "THA": (15.9, 100.9),
    "VNM": (14.1, 108.3), "MYS": (4.2, 102.0), "PHL": (12.9, 121.8), "NZL": (-41.5, 172.8),
    "NOR": (60.5, 8.5), "SWE": (60.1, 18.6), "FIN": (64.5, 26.0), "POL": (52.1, 19.4),
    "NLD": (52.1, 5.3), "BEL": (50.8, 4.5), "CHE": (46.8, 8.2), "AUT": (47.6, 14.1),
    "ISR": (31.0, 34.8), "IRQ": (33.2, 43.7), "QAT": (25.3, 51.2), "ARE": (24.3, 54.4),
    "KWT": (29.3, 47.5), "KEN": (0.0, 37.9), "ETH": (9.1, 40.5), "GHA": (7.9, -1.0),
    "MAR": (31.8, -7.1), "TUN": (34.0, 9.6), "SGP": (1.35, 103.82),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _health_row(source: str, status: str, latency_ms: float, error: str | None = None, rate_limited: bool = False, auth_failed: bool = False, records: int = 0) -> dict[str, Any]:
    now = _now_iso()
    return {
        "source": source,
        "status": status,
        "critical": True,
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
            {"$set": row, "$setOnInsert": {"created_at": row["updated_at"]}},
            upsert=True,
        )



def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
        if parsed != parsed:
            return fallback
        return parsed
    except Exception:
        return fallback



def _get_access_token() -> tuple[str | None, dict[str, Any] | None]:
    now = time.time()
    cached = str(_TOKEN_CACHE.get("token") or "").strip()
    expires_at = float(_TOKEN_CACHE.get("expires_at") or 0.0)
    if cached and expires_at - now > 30:
        return cached, None
    if not (OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET):
        return None, None
    started = time.perf_counter()
    try:
        response = requests.post(
            OPENSKY_AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": OPENSKY_CLIENT_ID,
                "client_secret": OPENSKY_CLIENT_SECRET,
            },
            timeout=OPENSKY_TIMEOUT_SEC,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        response.raise_for_status()
        payload = response.json() if response.content else {}
        token = str(payload.get("access_token") or "").strip()
        expires_in = max(int(payload.get("expires_in") or 0), 0)
        if token:
            _TOKEN_CACHE["token"] = token
            _TOKEN_CACHE["expires_at"] = now + expires_in
            return token, _health_row("opensky_auth", "up", latency_ms, records=1)
        return None, _health_row("opensky_auth", "down", latency_ms, error="missing access_token", auth_failed=True)
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        latency_ms = (time.perf_counter() - started) * 1000.0
        return None, _health_row("opensky_auth", "down", latency_ms, error=f"http {status_code}: {exc}", rate_limited=status_code == 429, auth_failed=status_code in (401, 403))
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return None, _health_row("opensky_auth", "down", latency_ms, error=str(exc))



def _headers() -> tuple[dict[str, str], dict[str, Any] | None]:
    token, auth_health = _get_access_token()
    if token:
        return {"Authorization": f"Bearer {token}"}, auth_health
    return {}, auth_health



def _bbox(lat: float, lon: float, span: float = 2.0) -> dict[str, float]:
    return {
        "lamin": max(-90.0, lat - span),
        "lamax": min(90.0, lat + span),
        "lomin": max(-180.0, lon - span),
        "lomax": min(180.0, lon + span),
    }



def _baseline_for_country(country: str, limit: int = 12) -> tuple[float, float]:
    docs = list(db.aviation.find({"country": country}).sort("collected_at", -1).limit(limit))
    if not docs:
        return 0.0, 0.0
    counts = [_safe_float((doc.get("data") or {}).get("aircraft_count"), 0.0) for doc in docs]
    speeds = [_safe_float((doc.get("data") or {}).get("avg_velocity_mps"), 0.0) for doc in docs if _safe_float((doc.get("data") or {}).get("avg_velocity_mps"), 0.0) > 0]
    baseline_count = sum(counts) / len(counts) if counts else 0.0
    baseline_speed = sum(speeds) / len(speeds) if speeds else 0.0
    return baseline_count, baseline_speed



def _build_record(country: str, lat: float, lon: float, states: list[list[Any]], collected_at: datetime) -> dict[str, Any]:
    aircraft_count = len(states)
    on_ground_count = sum(1 for state in states if len(state) > 8 and bool(state[8]))
    velocities = [_safe_float(state[9], 0.0) for state in states if len(state) > 9 and _safe_float(state[9], 0.0) > 0]
    avg_velocity = sum(velocities) / len(velocities) if velocities else 0.0
    baseline_count, baseline_speed = _baseline_for_country(country)
    activity_drop = max(0.0, (baseline_count - aircraft_count) / baseline_count) if baseline_count > 0 else 0.0
    speed_drop = max(0.0, (baseline_speed - avg_velocity) / baseline_speed) if baseline_speed > 0 else 0.0
    ground_ratio = (on_ground_count / aircraft_count) if aircraft_count > 0 else (1.0 if baseline_count >= 3 else 0.0)
    disruption_score = min(activity_drop * 0.65 + speed_drop * 0.15 + ground_ratio * 0.2, 1.0)
    metadata = build_signal_metadata(
        source=SOURCE_NAME,
        observed_at=collected_at,
        ingested_at=collected_at,
        language="und",
        confidence=0.71 if baseline_count > 0 else 0.6,
        coverage_weight=0.72,
        geo_scope="country",
    )
    return {
        "source": SOURCE_NAME,
        "category": "aviation_activity",
        "country": country,
        "collected_at": collected_at,
        "timestamp": collected_at,
        **metadata,
        "data": {
            "hub_lat": lat,
            "hub_lon": lon,
            "aircraft_count": aircraft_count,
            "on_ground_count": on_ground_count,
            "avg_velocity_mps": round(avg_velocity, 3),
            "baseline_aircraft_count": round(baseline_count, 3),
            "baseline_avg_velocity_mps": round(baseline_speed, 3),
            "aviation_disruption_score": round(disruption_score, 4),
            "snapshot_at": collected_at.strftime("%Y-%m-%dT%H:%M"),
        },
    }



def collect_aviation_signals(countries: list[str] | None = None, pause_sec: float = 0.2) -> dict[str, Any]:
    target_countries = [code for code in (countries or list(AVIATION_HUBS.keys())) if code in AVIATION_HUBS]
    collected_at = datetime.now(timezone.utc)
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    total_latency_ms = 0.0
    rate_limited = False
    auth_failed = False
    headers, auth_health = _headers()

    for index, country in enumerate(target_countries):
        lat, lon = AVIATION_HUBS[country]
        started = time.perf_counter()
        try:
            response = requests.get(OPENSKY_API_URL, params=_bbox(lat, lon), headers=headers, timeout=OPENSKY_TIMEOUT_SEC)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            total_latency_ms += elapsed_ms
            response.raise_for_status()
            payload = response.json() if response.content else {}
            states = payload.get("states") if isinstance(payload, dict) else []
            states = states if isinstance(states, list) else []
            records.append(_build_record(country, lat, lon, states, collected_at))
        except requests.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            total_latency_ms += elapsed_ms
            status_code = exc.response.status_code if exc.response is not None else None
            rate_limited = rate_limited or status_code == 429
            auth_failed = auth_failed or status_code in (401, 403)
            errors.append(f"{country}:http {status_code}")
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            total_latency_ms += elapsed_ms
            errors.append(f"{country}:{exc}")
        if pause_sec > 0 and index < len(target_countries) - 1:
            time.sleep(pause_sec)

    insert("aviation", records, unique_keys=["country", "data.snapshot_at"])
    for record in records:
        send_to_kafka(KAFKA_TOPIC, record, key=record.get("country"))

    average_latency_ms = total_latency_ms / max(len(target_countries), 1)
    if records:
        health = _health_row(SOURCE_NAME, "up", average_latency_ms, error=("; ".join(errors[:4]) if errors else None), rate_limited=rate_limited, auth_failed=auth_failed, records=len(records))
    else:
        health = _health_row(SOURCE_NAME, "down", average_latency_ms, error=("; ".join(errors[:4]) if errors else "no parseable OpenSky responses"), rate_limited=rate_limited, auth_failed=auth_failed, records=0)
    try:
        rows = [health]
        if auth_health is not None:
            rows.append(auth_health)
        _persist_source_health(rows)
    except Exception:
        pass

    return {
        "records": len(records),
        "countries": len([record for record in records if _safe_float((record.get("data") or {}).get("aircraft_count"), 0.0) >= 0]),
        "errors": errors[:10],
        "source": SOURCE_NAME,
        "health": health,
    }


if __name__ == "__main__":
    print(collect_aviation_signals())
