import time
from datetime import datetime, timezone
from typing import Any

from backend.kafka_client import send_to_kafka
from database.mongo import db, insert
from processing.country_catalog import COUNTRY_NAMES
from collectors.economic_behavior import _health_row, _persist_source_health, _world_bank_indicator

KAFKA_TOPIC = "worldbank_behavior_topic"
SOURCE_NAME = "worldbank_behavior"
WORLD_BANK_BEHAVIOR_INDICATORS = {
    "unemployment_rate": "SL.UEM.TOTL.ZS",
    "inflation_rate": "FP.CPI.TOTL.ZG",
    "remittance_inflows_usd": "BX.TRF.PWKR.CD.DT",
    "energy_import_dependency": "EG.IMP.CONS.ZS",
}


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if parsed == parsed else fallback
    except Exception:
        return fallback


def _record(country: str, collected_at: datetime, values: dict[str, dict[str, Any]]) -> dict[str, Any]:
    unemployment = _safe_float((values.get("unemployment_rate") or {}).get("value"), 0.0)
    inflation = _safe_float((values.get("inflation_rate") or {}).get("value"), 0.0)
    remittance = _safe_float((values.get("remittance_inflows_usd") or {}).get("value"), 0.0)
    energy_import_dependency = _safe_float((values.get("energy_import_dependency") or {}).get("value"), 0.0)
    remittance_stress = min((remittance / 5_000_000_000.0), 1.0) if remittance > 0 else 0.0
    energy_dependency_score = min(max(energy_import_dependency / 100.0, 0.0), 1.0)
    return {
        "source": SOURCE_NAME,
        "category": "worldbank_behavior",
        "country": country,
        "country_name": COUNTRY_NAMES.get(country, country),
        "collected_at": collected_at,
        "timestamp": collected_at,
        "data": {
            "unemployment_rate": round(unemployment, 4),
            "inflation_rate": round(inflation, 4),
            "remittance_inflows_usd": round(remittance, 2),
            "energy_import_dependency": round(energy_import_dependency, 4),
            "remittance_stress_score": round(remittance_stress, 4),
            "energy_dependency_score": round(energy_dependency_score, 4),
            "indicator_years": {k: (v or {}).get("year") for k, v in values.items()},
        },
    }


def collect_worldbank_behavior_indicators() -> dict[str, Any]:
    collected_at = datetime.now(timezone.utc)
    indicator_rows = {}
    health_rows = []
    for label, indicator in WORLD_BANK_BEHAVIOR_INDICATORS.items():
        rows, health = _world_bank_indicator(indicator)
        indicator_rows[label] = rows
        health_rows.append(health)

    countries = sorted(set().union(*[set(rows.keys()) for rows in indicator_rows.values() if rows]))
    records = []
    for country in countries:
        values = {label: rows.get(country) for label, rows in indicator_rows.items()}
        records.append(_record(country, collected_at, values))

    inserted = insert("worldbank_behavior", records, unique_keys=["country", "data.indicator_years.unemployment_rate", "data.indicator_years.inflation_rate", "data.indicator_years.remittance_inflows_usd", "data.indicator_years.energy_import_dependency"])
    for record in records:
        send_to_kafka(KAFKA_TOPIC, record, key=record.get("country"))
    try:
        _persist_source_health(health_rows)
    except Exception:
        pass
    return {"source": SOURCE_NAME, "records": len(records), "inserted": inserted, "health": {row["source"]: row for row in health_rows}}


if __name__ == "__main__":
    print(collect_worldbank_behavior_indicators())
