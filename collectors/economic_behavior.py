import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from dotenv import load_dotenv

from backend.kafka_client import send_to_kafka
from database.mongo import db, insert
from processing.country_catalog import COUNTRY_NAMES
from processing.signal_taxonomy import build_signal_metadata

load_dotenv(override=True)

WORLD_BANK_BASE = (os.getenv("WORLD_BANK_API_BASE") or "https://api.worldbank.org/v2").strip().rstrip("/")
FRED_API_URL = (os.getenv("FRED_API_URL") or "https://api.stlouisfed.org/fred/series/observations").strip()
EIA_API_URL = (os.getenv("EIA_API_URL") or "https://api.eia.gov/v2/seriesid/PET.RWTC.D").strip()
FRANKFURTER_BASE = (os.getenv("FRANKFURTER_API_BASE") or "https://api.frankfurter.app").strip().rstrip("/")
FRED_API_KEY = (os.getenv("FRED_API_KEY") or "").strip()
EIA_API_KEY = (os.getenv("EIA_API_KEY") or "").strip()
TIMEOUT_SEC = int(os.getenv("ECONOMIC_BEHAVIOR_TIMEOUT_SEC") or 25)
KAFKA_TOPIC = "economic_behavior_topic"
SOURCE_NAME = "economic_behavior"

WORLD_BANK_INDICATORS = {
    "unemployment_rate": "SL.UEM.TOTL.ZS",
    "inflation_rate": "FP.CPI.TOTL.ZG",
    "remittance_inflows_usd": "BX.TRF.PWKR.CD.DT",
    "energy_import_dependency": "EG.IMP.CONS.ZS",
}
FRED_SERIES = {
    "food_price_index": "PFOODINDEXM",
    "labor_stress_proxy": "UNRATE",
}
COUNTRY_CURRENCY = {
    "USA": "USD", "CAN": "CAD", "MEX": "MXN", "BRA": "BRL", "ARG": "ARS", "GBR": "GBP", "FRA": "EUR", "DEU": "EUR",
    "ESP": "EUR", "ITA": "EUR", "RUS": "RUB", "CHN": "CNY", "IND": "INR", "JPN": "JPY", "KOR": "KRW", "AUS": "AUD",
    "ZAF": "ZAR", "EGY": "EGP", "NGA": "NGN", "TUR": "TRY", "SAU": "SAR", "IDN": "IDR", "PAK": "PKR", "UKR": "UAH",
    "LKA": "LKR", "DZA": "DZD", "IRN": "IRR", "AFG": "AFN", "BGD": "BDT", "NPL": "NPR", "MMR": "MMK", "THA": "THB",
    "VNM": "VND", "MYS": "MYR", "PHL": "PHP", "NZL": "NZD", "NOR": "NOK", "SWE": "SEK", "FIN": "EUR", "POL": "PLN",
    "NLD": "EUR", "BEL": "EUR", "CHE": "CHF", "AUT": "EUR", "ISR": "ILS", "IRQ": "IQD", "QAT": "QAR", "ARE": "AED",
    "KWT": "KWD", "KEN": "KES", "ETH": "ETB", "GHA": "GHS", "MAR": "MAD", "TUN": "TND", "SGP": "SGD", "URY": "UYU",
    "BOL": "BOB", "CMR": "XAF", "CIV": "XOF", "SEN": "XOF", "MLI": "XOF", "BEN": "XOF", "BFA": "XOF", "NER": "XOF",
    "TGO": "XOF", "GNB": "XOF", "GIN": "GNF", "UGA": "UGX", "TZA": "TZS", "RWA": "RWF", "ZMB": "ZMW", "ZWE": "USD",
    "CHL": "CLP", "COL": "COP", "PER": "PEN", "VEN": "VES", "ECU": "USD", "PAN": "USD", "CRI": "CRC", "DOM": "DOP",
    "GTM": "GTQ", "HND": "HNL", "NIC": "NIO", "SLV": "USD", "JAM": "JMD", "CUB": "CUP", "PRY": "PYG", "ROU": "RON",
    "CZE": "CZK", "HUN": "HUF", "DNK": "DKK", "ISL": "ISK", "HRV": "EUR", "SRB": "RSD", "BGR": "BGN", "JOR": "JOD",
    "LBN": "LBP", "OMN": "OMR", "BHR": "BHD", "YEM": "YER", "KAZ": "KZT", "UZB": "UZS", "AZE": "AZN", "ARM": "AMD",
    "GEO": "GEL", "MNG": "MNT", "KHM": "KHR", "LAO": "LAK", "TWN": "TWD", "HKG": "HKD",
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


def _health_row(source: str, status: str, latency_ms: float, error: str | None = None, rate_limited: bool = False, auth_failed: bool = False, records: int = 0) -> dict[str, Any]:
    now = _now_iso()
    return {
        "source": source,
        "status": status,
        "critical": False,
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


def _normalize_country(code: Any) -> str:
    candidate = str(code or "").strip().upper()
    return candidate if len(candidate) == 3 and candidate.isalpha() else ""


def _latest_cached_by_country(limit: int = 4000) -> dict[str, dict[str, Any]]:
    docs = list(
        db["economic_behavior"]
        .find({}, {"_id": 0, "country": 1, "data": 1})
        .sort("_id", -1)
        .limit(limit)
    )
    latest: dict[str, dict[str, Any]] = {}
    for doc in docs:
        country = _normalize_country(doc.get("country"))
        if not country or country not in COUNTRY_NAMES or country in latest:
            continue
        payload = doc.get("data") if isinstance(doc.get("data"), dict) else {}
        latest[country] = payload or {}
    return latest


def _world_bank_indicator(indicator: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    source_name = f"worldbank_behavior_{indicator}"
    try:
        response = requests.get(
            f"{WORLD_BANK_BASE}/country/all/indicator/{indicator}",
            params={"format": "json", "per_page": 20000, "mrv": 1},
            timeout=TIMEOUT_SEC,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        response.raise_for_status()
        payload = response.json() if response.content else []
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list) else []
        results: dict[str, dict[str, Any]] = {}
        for item in rows:
            if not isinstance(item, dict):
                continue
            country_code = _normalize_country(item.get("countryiso3code") or ((item.get("country") or {}).get("id")))
            value = item.get("value")
            if not country_code or country_code not in COUNTRY_NAMES or value in (None, ""):
                continue
            results[country_code] = {
                "value": _safe_float(value, 0.0),
                "year": str(item.get("date") or ""),
            }
        status = "up" if results else "down"
        error = None if results else f"no parseable World Bank rows for {indicator}"
        return results, _health_row(source_name, status, latency_ms, error=error, records=len(results))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        latency_ms = (time.perf_counter() - started) * 1000.0
        return {}, _health_row(source_name, "down", latency_ms, error=f"http {status_code}: {exc}", rate_limited=status_code == 429, auth_failed=status_code in (401, 403))
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return {}, _health_row(source_name, "down", latency_ms, error=str(exc))


def _fred_series(series_id: str, source_name: str = "fred_behavior") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not FRED_API_KEY:
        return [], _health_row(source_name, "down", 0.0, error="missing FRED_API_KEY", auth_failed=True)
    started = time.perf_counter()
    try:
        response = requests.get(
            FRED_API_URL,
            params={"series_id": series_id, "api_key": FRED_API_KEY, "file_type": "json", "sort_order": "desc", "limit": 2},
            timeout=TIMEOUT_SEC,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        response.raise_for_status()
        payload = response.json() if response.content else {}
        observations = payload.get("observations") if isinstance(payload, dict) else []
        observations = [item for item in observations if isinstance(item, dict)]
        return observations[:2], _health_row(source_name, "up" if observations else "down", latency_ms, error=None if observations else f"no FRED observations for {series_id}", records=len(observations))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        latency_ms = (time.perf_counter() - started) * 1000.0
        return [], _health_row(source_name, "down", latency_ms, error=f"http {status_code}: {exc}", rate_limited=status_code == 429, auth_failed=status_code in (401, 403))
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return [], _health_row(source_name, "down", latency_ms, error=str(exc))


def _eia_oil_price() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not EIA_API_KEY:
        return [], _health_row("eia_behavior", "down", 0.0, error="missing EIA_API_KEY", auth_failed=True)
    started = time.perf_counter()
    try:
        response = requests.get(EIA_API_URL, params={"api_key": EIA_API_KEY}, timeout=TIMEOUT_SEC)
        latency_ms = (time.perf_counter() - started) * 1000.0
        response.raise_for_status()
        payload = response.json() if response.content else {}
        observations = (((payload.get("response") or {}).get("data")) or []) if isinstance(payload, dict) else []
        observations = [item for item in observations if isinstance(item, dict)][:2]
        if not observations and isinstance(payload, dict):
            series = (((payload.get("response") or {}).get("series")) or [])
            if isinstance(series, list) and series and isinstance(series[0], dict):
                observations = [item for item in (series[0].get("data") or [])[:2] if isinstance(item, dict)]
        return observations, _health_row("eia_behavior", "up" if observations else "down", latency_ms, error=None if observations else "no EIA observations", records=len(observations))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        latency_ms = (time.perf_counter() - started) * 1000.0
        return [], _health_row("eia_behavior", "down", latency_ms, error=f"http {status_code}: {exc}", rate_limited=status_code == 429, auth_failed=status_code in (401, 403))
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return [], _health_row("eia_behavior", "down", latency_ms, error=str(exc))


def _fetch_frankfurter_rates(date_value: datetime | None = None) -> tuple[dict[str, float], dict[str, Any]]:
    started = time.perf_counter()
    endpoint = f"{FRANKFURTER_BASE}/latest" if date_value is None else f"{FRANKFURTER_BASE}/{date_value.date().isoformat()}"
    try:
        response = requests.get(endpoint, params={"from": "USD"}, timeout=TIMEOUT_SEC)
        latency_ms = (time.perf_counter() - started) * 1000.0
        response.raise_for_status()
        payload = response.json() if response.content else {}
        rates = payload.get("rates") if isinstance(payload, dict) else {}
        if not isinstance(rates, dict):
            rates = {}
        parsed = {str(currency).upper(): _safe_float(rate, 0.0) for currency, rate in rates.items() if _safe_float(rate, 0.0) > 0}
        return parsed, _health_row("frankfurter_behavior", "up" if parsed else "down", latency_ms, error=None if parsed else "no Frankfurter rates", records=len(parsed))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        latency_ms = (time.perf_counter() - started) * 1000.0
        return {}, _health_row("frankfurter_behavior", "down", latency_ms, error=f"http {status_code}: {exc}", rate_limited=status_code == 429, auth_failed=status_code in (401, 403))
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return {}, _health_row("frankfurter_behavior", "down", latency_ms, error=str(exc))


def _series_value(observations: list[dict[str, Any]], keys: tuple[str, ...] = ("value",)) -> tuple[float, float, str | None]:
    latest = observations[0] if observations else {}
    previous = observations[1] if len(observations) > 1 else {}
    latest_value = 0.0
    previous_value = 0.0
    for key in keys:
        if latest_value == 0.0:
            latest_value = _safe_float(latest.get(key), 0.0)
        if previous_value == 0.0:
            previous_value = _safe_float(previous.get(key), 0.0)
    date_value = str(latest.get("date") or latest.get("period") or latest.get("periodName") or "") or None
    return latest_value, previous_value, date_value


def _bounded_ratio(latest: float, previous: float, scale: float, absolute_scale: float) -> float:
    ratio = max((latest - previous) / previous, 0.0) if previous > 0 else 0.0
    return min(max(ratio * scale, 0.0) + min(max(latest / absolute_scale, 0.0), 1.0) * 0.35, 1.0)


def _fx_pressure(latest: float, previous: float) -> float:
    if latest <= 0 or previous <= 0:
        return 0.0
    depreciation = max((latest - previous) / previous, 0.0)
    return min(depreciation * 4.2, 1.0)


def _round4(value: float) -> float:
    return round(_safe_float(value, 0.0), 4)


def _build_country_record(
    country: str,
    collected_at: datetime,
    household_stress_score: float,
    fuel_price_pressure: float,
    food_price_pressure: float,
    labor_stress_score: float,
    fx_pressure_score: float,
    remittance_stress_score: float,
    energy_stress_score: float,
    inflation: float,
    unemployment: float,
    worldbank_year: str | None,
    food_latest: float,
    food_date: str | None,
    fuel_latest: float,
    fuel_date: str | None,
    currency_code: str | None,
    component_sources: list[str],
    confidence: float,
) -> dict[str, Any]:
    metadata = build_signal_metadata(
        source=SOURCE_NAME,
        observed_at=collected_at,
        ingested_at=collected_at,
        language="und",
        confidence=confidence,
        coverage_weight=0.8,
        signal_domain="economic_behavior",
        signal_type="household_labor_pressure",
        signal_class="direct",
        source_tier="public_institution",
        geo_scope="country",
    )
    return {
        "source": SOURCE_NAME,
        "category": "economic_behavior",
        "country": country,
        "country_name": COUNTRY_NAMES.get(country, country),
        "collected_at": collected_at,
        "timestamp": collected_at,
        **metadata,
        "data": {
            "household_stress_score": _round4(household_stress_score),
            "fuel_price_pressure": _round4(fuel_price_pressure),
            "food_price_pressure": _round4(food_price_pressure),
            "labor_stress_score": _round4(labor_stress_score),
            "fx_pressure_score": _round4(fx_pressure_score),
            "remittance_stress_score": _round4(remittance_stress_score),
            "energy_stress_score": _round4(energy_stress_score),
            "currency_code": currency_code,
            "inflation_rate": _round4(inflation),
            "unemployment_rate": _round4(unemployment),
            "worldbank_year": worldbank_year,
            "food_price_value": _round4(food_latest),
            "food_price_date": food_date,
            "fuel_price_value": _round4(fuel_latest),
            "fuel_price_date": fuel_date,
            "component_sources": component_sources,
        },
    }


def collect_economic_behavior_signals() -> dict[str, Any]:
    unemployment_rows, worldbank_unemp_health = _world_bank_indicator(WORLD_BANK_INDICATORS["unemployment_rate"])
    inflation_rows, worldbank_infl_health = _world_bank_indicator(WORLD_BANK_INDICATORS["inflation_rate"])
    remittance_rows, worldbank_remit_health = _world_bank_indicator(WORLD_BANK_INDICATORS["remittance_inflows_usd"])
    energy_import_rows, worldbank_energy_health = _world_bank_indicator(WORLD_BANK_INDICATORS["energy_import_dependency"])
    food_rows, fred_health = _fred_series(FRED_SERIES["food_price_index"])
    labor_rows, fred_labor_health = _fred_series(FRED_SERIES["labor_stress_proxy"], source_name="fred_behavior_labor")
    fuel_rows, eia_health = _eia_oil_price()
    fx_now_rows, frankfurter_health = _fetch_frankfurter_rates()
    fx_prev_rows, _ = _fetch_frankfurter_rates(datetime.now(timezone.utc) - timedelta(days=30))
    cached_rows = _latest_cached_by_country()

    food_latest, food_previous, food_date = _series_value(food_rows)
    labor_latest, labor_previous, labor_date = _series_value(labor_rows)
    fuel_latest, fuel_previous, fuel_date = _series_value(fuel_rows, keys=("value", "price"))
    food_price_pressure = _bounded_ratio(food_latest, food_previous, scale=5.0, absolute_scale=220.0)
    fuel_price_pressure = _bounded_ratio(fuel_latest, fuel_previous, scale=4.5, absolute_scale=130.0)
    labor_proxy_score = _bounded_ratio(labor_latest, labor_previous, scale=4.0, absolute_scale=8.0)

    collected_at = datetime.now(timezone.utc)
    records: list[dict[str, Any]] = []
    countries = sorted((set(unemployment_rows.keys()) | set(inflation_rows.keys()) | set(remittance_rows.keys()) | set(energy_import_rows.keys()) | set(cached_rows.keys()) | set(COUNTRY_CURRENCY.keys())) & set(COUNTRY_NAMES.keys()))
    if not countries:
        countries = sorted(COUNTRY_NAMES.keys())

    for country in countries:
        cached_payload = cached_rows.get(country) or {}
        currency_code = COUNTRY_CURRENCY.get(country)
        fx_pressure_score = _safe_float(cached_payload.get("fx_pressure_score"), 0.0)
        if currency_code and currency_code != "USD":
            fx_pressure_score = _fx_pressure(_safe_float(fx_now_rows.get(currency_code), 0.0), _safe_float(fx_prev_rows.get(currency_code), 0.0))
        unemployment = _safe_float((unemployment_rows.get(country) or {}).get("value"), _safe_float(cached_payload.get("unemployment_rate"), labor_latest))
        inflation = _safe_float((inflation_rows.get(country) or {}).get("value"), _safe_float(cached_payload.get("inflation_rate"), 4.5))
        remittance_inflows = _safe_float((remittance_rows.get(country) or {}).get("value"), _safe_float(cached_payload.get("remittance_inflows_usd"), 0.0))
        energy_import_dependency = _safe_float((energy_import_rows.get(country) or {}).get("value"), _safe_float(cached_payload.get("energy_import_dependency"), 0.0))
        labor_stress_score = min(
            max(
                max(unemployment / 18.0, 0.0) if unemployment > 0 else 0.0,
                labor_proxy_score,
                _safe_float(cached_payload.get("labor_stress_score"), 0.0),
            ),
            1.0,
        )
        inflation_stress = min(
            max(
                (inflation / 15.0) if inflation > 0 else 0.0,
                _safe_float(cached_payload.get("household_stress_score"), 0.0) * 0.55,
            ),
            1.0,
        )
        remittance_stress_score = min((remittance_inflows / 5_000_000_000.0), 1.0) if remittance_inflows > 0 else _safe_float(cached_payload.get("remittance_stress_score"), 0.0)
        energy_stress_score = min(max(energy_import_dependency / 100.0, 0.0), 1.0) if energy_import_dependency > 0 else _safe_float(cached_payload.get("energy_stress_score"), fuel_price_pressure)
        household_stress_score = min(
            labor_stress_score * 0.28 + inflation_stress * 0.22 + fuel_price_pressure * 0.1 + food_price_pressure * 0.1 + fx_pressure_score * 0.14 + energy_stress_score * 0.1 + remittance_stress_score * 0.06,
            1.0,
        )
        component_sources: list[str] = []
        confidence = 0.52
        if country in unemployment_rows or country in inflation_rows or country in remittance_rows or country in energy_import_rows:
            component_sources.append("worldbank_behavior")
            confidence = 0.76
        else:
            component_sources.append("economic_behavior_cache")
        if food_rows:
            component_sources.append("fred_behavior")
            confidence = min(confidence + 0.04, 0.84)
        if fuel_rows:
            component_sources.append("eia_behavior")
            confidence = min(confidence + 0.04, 0.86)
        if labor_rows:
            component_sources.append("fred_behavior_labor_proxy")
            confidence = min(confidence + 0.03, 0.87)
        if currency_code and fx_now_rows:
            component_sources.append("frankfurter_behavior")
            confidence = min(confidence + 0.03, 0.9)

        records.append(
            _build_country_record(
                country=country,
                collected_at=collected_at,
                household_stress_score=household_stress_score,
                fuel_price_pressure=fuel_price_pressure,
                food_price_pressure=food_price_pressure,
                labor_stress_score=labor_stress_score,
                fx_pressure_score=fx_pressure_score,
                remittance_stress_score=remittance_stress_score,
                energy_stress_score=energy_stress_score,
                inflation=inflation,
                unemployment=unemployment,
                worldbank_year=(inflation_rows.get(country) or unemployment_rows.get(country) or remittance_rows.get(country) or energy_import_rows.get(country) or {}).get("year") or str(labor_date or food_date or fuel_date or ""),
                food_latest=food_latest,
                food_date=food_date,
                fuel_latest=fuel_latest,
                fuel_date=fuel_date,
                currency_code=currency_code,
                component_sources=component_sources,
                confidence=confidence,
            )
        )

    inserted = insert("economic_behavior", records, unique_keys=["country", "data.worldbank_year", "data.food_price_date", "data.fuel_price_date"])
    for record in records:
        send_to_kafka(KAFKA_TOPIC, record, key=record.get("country"))
    try:
        _persist_source_health([worldbank_unemp_health, worldbank_infl_health, worldbank_remit_health, worldbank_energy_health, fred_health, fred_labor_health, eia_health, frankfurter_health])
    except Exception:
        pass
    return {
        "records": len(records),
        "inserted": inserted,
        "countries": len({record.get("country") for record in records if record.get("country")}),
        "fuel_price_pressure": round(fuel_price_pressure, 4),
        "food_price_pressure": round(food_price_pressure, 4),
        "labor_proxy_score": round(labor_proxy_score, 4),
        "source": SOURCE_NAME,
        "health": {
            "worldbank_unemployment": worldbank_unemp_health,
            "worldbank_inflation": worldbank_infl_health,
            "worldbank_remittance": worldbank_remit_health,
            "worldbank_energy_dependency": worldbank_energy_health,
            "fred_behavior": fred_health,
            "fred_behavior_labor": fred_labor_health,
            "eia_behavior": eia_health,
            "frankfurter_behavior": frankfurter_health,
        },
    }


if __name__ == "__main__":
    print(collect_economic_behavior_signals())
