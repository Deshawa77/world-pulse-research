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

WORLD_BANK_API_BASE = (os.getenv("WORLD_BANK_API_BASE") or "https://api.worldbank.org/v2").strip().rstrip("/")
TIMEOUT_SEC = int(os.getenv("LOGISTICS_TIMEOUT_SEC") or 25)
KAFKA_TOPIC = "logistics_topic"
SOURCE_NAME = "logistics"
LOGISTICS_INDICATORS = {
    "logistics_performance": "LP.LPI.OVRL.XQ",
    "container_port_traffic": "IS.SHP.GOOD.TU",
    "air_freight": "IS.AIR.GOOD.MT.K1",
}


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if parsed == parsed else fallback
    except Exception:
        return fallback


def _health_row(status: str, latency_ms: float, error: str | None = None, records: int = 0) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {"source": SOURCE_NAME, "status": status, "critical": False, "latency_ms": round(latency_ms, 3), "last_checked": now, "last_success": now if status == "up" else None, "error": error, "records": int(records)}


def _persist_health(row: dict[str, Any]) -> None:
    db["source_health"].update_one({"source": row["source"]}, {"$set": {**row, "updated_at": datetime.now(timezone.utc).isoformat()}, "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)


def _indicator_rows(indicator: str) -> dict[str, dict[str, Any]]:
    response = requests.get(f"{WORLD_BANK_API_BASE}/country/all/indicator/{indicator}", params={"format": "json", "per_page": 20000, "mrv": 1}, timeout=TIMEOUT_SEC)
    response.raise_for_status()
    payload = response.json() if response.content else []
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list) else []
    data = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        country = str(item.get("countryiso3code") or "").strip().upper()
        value = item.get("value")
        if len(country) != 3 or country not in COUNTRY_NAMES or value in (None, ""):
            continue
        data[country] = {"value": _safe_float(value, 0.0), "year": str(item.get("date") or "")}
    return data


def collect_logistics_signals() -> dict[str, Any]:
    started = time.perf_counter()
    try:
        indicator_maps = {name: _indicator_rows(code) for name, code in LOGISTICS_INDICATORS.items()}
        countries = sorted(set().union(*[set(m.keys()) for m in indicator_maps.values() if m]))
        collected_at = datetime.now(timezone.utc)
        records = []
        for country in countries:
            lpi = _safe_float((indicator_maps["logistics_performance"].get(country) or {}).get("value"), 0.0)
            port = _safe_float((indicator_maps["container_port_traffic"].get(country) or {}).get("value"), 0.0)
            air = _safe_float((indicator_maps["air_freight"].get(country) or {}).get("value"), 0.0)
            logistics_stress = min(max((5.0 - lpi) / 5.0, 0.0) * 0.6 + min(port / 20_000_000.0, 1.0) * 0.15 + min(air / 2_000_000.0, 1.0) * 0.25, 1.0)
            records.append({
                "source": SOURCE_NAME,
                "category": "logistics_stress",
                "country": country,
                "country_name": COUNTRY_NAMES.get(country, country),
                "collected_at": collected_at,
                "timestamp": collected_at,
                **build_signal_metadata(source=SOURCE_NAME, observed_at=collected_at, ingested_at=collected_at, language="und", confidence=0.68, coverage_weight=0.62, signal_domain="mobility", signal_type="logistics_flow", signal_class="contextual", source_tier="public_institution", geo_scope="country"),
                "data": {
                    "logistics_stress_score": round(logistics_stress, 4),
                    "logistics_performance": round(lpi, 4),
                    "container_port_traffic": round(port, 2),
                    "air_freight": round(air, 2),
                },
            })
        inserted = insert("logistics", records, unique_keys=["country", "data.logistics_performance", "data.container_port_traffic", "data.air_freight"])
        for record in records:
            send_to_kafka(KAFKA_TOPIC, record, key=record.get("country"))
        health = _health_row("up" if records else "down", (time.perf_counter() - started) * 1000.0, error=None if records else "no logistics rows", records=len(records))
        _persist_health(health)
        return {"source": SOURCE_NAME, "records": len(records), "inserted": inserted, "health": health}
    except Exception as exc:
        health = _health_row("down", (time.perf_counter() - started) * 1000.0, error=str(exc), records=0)
        _persist_health(health)
        return {"source": SOURCE_NAME, "records": 0, "inserted": 0, "health": health}


if __name__ == "__main__":
    print(collect_logistics_signals())
