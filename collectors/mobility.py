import os
import time
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

from backend.kafka_client import send_to_kafka
from database.mongo import db, insert
from processing.country_catalog import COUNTRY_NAMES
from processing.signal_taxonomy import build_signal_metadata

load_dotenv(override=True)

UNHCR_IDMC_ENDPOINT = (os.getenv("UNHCR_IDMC_ENDPOINT") or "https://api.unhcr.org/population/v1/idmc/").strip()
DEFAULT_TIMEOUT_SEC = int(os.getenv("UNHCR_IDMC_TIMEOUT_SEC") or 20)
DEFAULT_LIMIT = int(os.getenv("UNHCR_IDMC_LIMIT") or 250)
KAFKA_TOPIC = "mobility_topic"
SOURCE_NAME = "unhcr_idmc"


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



def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return fallback



def _pick(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return None



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



def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = value.get("items") or value.get("results") or value.get("data")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []



def _normalize_country(value: Any) -> str:
    code = str(value or "").strip().upper()
    return code if len(code) == 3 and code.isalpha() else ""



def _build_record(item: dict[str, Any], collected_at: datetime) -> dict[str, Any] | None:
    origin_country = _normalize_country(_pick(item, "coo_iso", "coo", "coo_code", "origin_iso", "origin", "country_of_origin", "iso3"))
    if not origin_country:
        return None

    host_country = _normalize_country(_pick(item, "coa_iso", "coa", "coa_code", "host_iso", "host_country", "country_of_asylum"))
    year_value = _safe_int(_pick(item, "year", "year_from", "yearFrom"), datetime.now(timezone.utc).year)
    displaced_people = _safe_float(_pick(item, "value", "idps", "displaced", "displaced_persons", "population", "total", "count"), 0.0)
    if displaced_people <= 0:
        return None

    previous_people = _safe_float(_pick(item, "previous_value", "previous", "previous_total"), 0.0)
    delta_ratio = 0.0 if previous_people <= 0 else max(min((displaced_people - previous_people) / previous_people, 5.0), -1.0)
    observed_at = datetime(year=max(year_value, 1970), month=1, day=1, tzinfo=timezone.utc)
    metadata = build_signal_metadata(
        source=SOURCE_NAME,
        observed_at=observed_at,
        ingested_at=collected_at,
        language="und",
        confidence=0.82,
        coverage_weight=0.88,
        geo_scope="country",
    )
    record_key = "|".join(
        [
            origin_country,
            host_country or "GLB",
            str(year_value),
            str(_pick(item, "id", "pk", "uuid", "record_id") or "row"),
        ]
    )
    return {
        "source": SOURCE_NAME,
        "category": "mobility_displacement",
        "country": origin_country,
        "country_name": COUNTRY_NAMES.get(origin_country, origin_country),
        "collected_at": collected_at,
        "timestamp": collected_at,
        **metadata,
        "data": {
            "year": year_value,
            "origin_country": origin_country,
            "host_country": host_country,
            "displaced_people": round(displaced_people, 2),
            "previous_displaced_people": round(previous_people, 2) if previous_people > 0 else None,
            "displacement_delta_ratio": round(delta_ratio, 4),
            "source_record_key": record_key,
            "snapshot_date": collected_at.date().isoformat(),
            "raw": item,
        },
    }



def fetch_displacement_records(*, year_from: int | None = None, year_to: int | None = None, limit: int = DEFAULT_LIMIT) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    now = datetime.now(timezone.utc)
    end_year = int(year_to or now.year)
    start_year = int(year_from or max(end_year - 2, 2018))
    params = {
        "page": 1,
        "limit": max(25, min(limit, 1000)),
        "yearFrom": start_year,
        "yearTo": end_year,
        "cfType": "ISO",
        "coo_all": True,
    }
    started = time.perf_counter()
    try:
        response = requests.get(UNHCR_IDMC_ENDPOINT, params=params, headers={"Accept": "application/json"}, timeout=DEFAULT_TIMEOUT_SEC)
        latency_ms = (time.perf_counter() - started) * 1000.0
        response.raise_for_status()
        payload = response.json() if response.content else {}
        rows = _extract_rows(payload)
        if not rows:
            return [], _health_row(SOURCE_NAME, "down", latency_ms, error="unexpected UNHCR payload shape", records=0)
        collected_at = datetime.now(timezone.utc)
        records: list[dict[str, Any]] = []
        for item in rows:
            record = _build_record(item, collected_at)
            if record is not None:
                records.append(record)
        status = "up" if records else "down"
        error = None if records else "no parseable UNHCR displacement rows"
        return records, _health_row(SOURCE_NAME, status, latency_ms, error=error, records=len(records))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        latency_ms = (time.perf_counter() - started) * 1000.0
        return [], _health_row(
            SOURCE_NAME,
            "down",
            latency_ms,
            error=f"http {status_code}: {exc}",
            rate_limited=status_code == 429,
            auth_failed=status_code in (401, 403),
            records=0,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return [], _health_row(SOURCE_NAME, "down", latency_ms, error=str(exc), records=0)



def collect_mobility_signals(*, year_from: int | None = None, year_to: int | None = None, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    records, health = fetch_displacement_records(year_from=year_from, year_to=year_to, limit=limit)
    inserted = insert("mobility", records, unique_keys=["country", "data.year", "data.source_record_key", "data.snapshot_date"])
    for record in records:
        send_to_kafka(KAFKA_TOPIC, record, key=record.get("country"))
    try:
        _persist_source_health([health])
    except Exception:
        pass
    covered_countries = sorted({str(record.get("country") or "") for record in records if record.get("country")})
    return {
        "records": len(records),
        "inserted": inserted,
        "countries": len(covered_countries),
        "year_from": year_from,
        "year_to": year_to,
        "source": SOURCE_NAME,
        "health": health,
    }


if __name__ == "__main__":
    print(collect_mobility_signals())
