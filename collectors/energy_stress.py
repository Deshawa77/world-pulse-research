from datetime import datetime, timezone
from typing import Any

from backend.kafka_client import send_to_kafka
from database.mongo import insert
from collectors.economic_behavior import _eia_oil_price, _fred_series, _health_row, _persist_source_health, _series_value, _bounded_ratio

KAFKA_TOPIC = "energy_stress_topic"
SOURCE_NAME = "energy_stress"


def collect_energy_stress_signals() -> dict[str, Any]:
    fuel_rows, eia_health = _eia_oil_price()
    energy_rows, fred_health = _fred_series("PNRGINDEXM", source_name="fred_behavior_energy")
    fuel_latest, fuel_previous, fuel_date = _series_value(fuel_rows, keys=("value", "price"))
    energy_latest, energy_previous, energy_date = _series_value(energy_rows)
    fuel_pressure = _bounded_ratio(fuel_latest, fuel_previous, scale=4.5, absolute_scale=130.0)
    energy_pressure = _bounded_ratio(energy_latest, energy_previous, scale=4.0, absolute_scale=220.0)
    record = {
        "source": SOURCE_NAME,
        "category": "energy_stress",
        "collected_at": datetime.now(timezone.utc),
        "timestamp": datetime.now(timezone.utc),
        "data": {
            "fuel_price_pressure": round(fuel_pressure, 4),
            "energy_stress_score": round(max(fuel_pressure, energy_pressure), 4),
            "fuel_price_value": round(fuel_latest, 4),
            "energy_price_value": round(energy_latest, 4),
            "fuel_price_date": fuel_date,
            "energy_price_date": energy_date,
        },
    }
    inserted = insert("energy_stress", [record], unique_keys=["data.fuel_price_date", "data.energy_price_date"])
    send_to_kafka(KAFKA_TOPIC, record, key="global")
    try:
        _persist_source_health([eia_health, fred_health])
    except Exception:
        pass
    return {"source": SOURCE_NAME, "records": 1, "inserted": inserted, "fuel_price_pressure": round(fuel_pressure, 4), "energy_stress_score": round(max(fuel_pressure, energy_pressure), 4)}


if __name__ == "__main__":
    print(collect_energy_stress_signals())
