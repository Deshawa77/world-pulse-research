import json
from datetime import datetime, timezone
from typing import Any

import requests
from bson import ObjectId

from backend.kafka_client import send_to_kafka
from database.mongo import insert

WHO_BASE_URL = "https://ghoapi.azureedge.net/api"
DISEASE_SH_COUNTRIES_URL = "https://disease.sh/v3/covid-19/countries"
DISEASE_SH_VACCINE_COUNTRIES_URL = "https://disease.sh/v3/covid-19/vaccine/coverage/countries"

DEFAULT_WHO_INDICATORS = [
    "WHOSIS_000001",
    "WHS9_86",
]

_COUNTRY_NAME_TO_ISO3: dict[str, str] | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_iso3(value: Any) -> str:
    if value is None:
        return ""
    code = str(value).strip().upper()
    if len(code) == 3 and code.isalpha():
        return code
    return ""


def _normalize_country_name(name: Any) -> str:
    text = str(name or "").strip().lower()
    text = text.replace("&", "and")
    text = text.replace("'", "")
    return " ".join(text.split())


def _country_name_to_iso3_map() -> dict[str, str]:
    global _COUNTRY_NAME_TO_ISO3
    if _COUNTRY_NAME_TO_ISO3 is not None:
        return _COUNTRY_NAME_TO_ISO3

    mapping: dict[str, str] = {}
    try:
        from processing.country_catalog import COUNTRY_NAMES

        for iso3, country_name in COUNTRY_NAMES.items():
            code = _safe_iso3(iso3)
            if not code:
                continue
            key = _normalize_country_name(country_name)
            if key and key not in mapping:
                mapping[key] = code
    except Exception:
        pass

    aliases = {
        "united states": "USA",
        "usa": "USA",
        "united kingdom": "GBR",
        "uk": "GBR",
        "russia": "RUS",
        "south korea": "KOR",
        "north korea": "PRK",
        "ivory coast": "CIV",
        "cote d ivoire": "CIV",
        "czechia": "CZE",
        "taiwan": "TWN",
        "laos": "LAO",
        "syria": "SYR",
        "venezuela": "VEN",
        "bolivia": "BOL",
        "moldova": "MDA",
        "palestine": "PSE",
    }
    for key, value in aliases.items():
        if key not in mapping:
            mapping[key] = value

    _COUNTRY_NAME_TO_ISO3 = mapping
    return mapping


def fetch_who_indicator(indicator_code: str, max_results: int = 250, batch_size: int = 200) -> list[dict[str, Any]]:
    collected_at = _now_iso()
    url = f"{WHO_BASE_URL}/{indicator_code}"

    records: list[dict[str, Any]] = []
    skip = 0

    try:
        while len(records) < max_results:
            top = min(batch_size, max_results - len(records))
            response = requests.get(
                url,
                params={"$top": top, "$skip": skip, "$format": "json"},
                timeout=20,
            )
            if response.status_code != 200:
                print(f"WHO {indicator_code} HTTP Error: {response.status_code}")
                break

            payload = response.json() if response.content else {}
            rows = payload.get("value") or []
            if not rows:
                break

            for item in rows:
                country = _safe_iso3(item.get("SpatialDim"))
                if not country:
                    continue

                record = {
                    "source": "who_gho",
                    "category": "health",
                    "collected_at": collected_at,
                    "data": {
                        "country": country,
                        "SpatialDim": country,
                        "year": item.get("TimeDim"),
                        "value": item.get("Value"),
                        "indicator": indicator_code,
                    },
                }
                records.append(record)

                try:
                    send_to_kafka("who_indicators", record)
                except Exception as kafka_exc:
                    print(f"Error sending WHO record to Kafka: {kafka_exc}")

                if len(records) >= max_results:
                    break

            skip += len(rows)
            if len(rows) < top:
                break

    except Exception as exc:
        print(f"Error fetching WHO indicator {indicator_code}: {exc}")

    return records


def fetch_covid_country_deaths(limit: int = 260) -> list[dict[str, Any]]:
    collected_at = _now_iso()
    records: list[dict[str, Any]] = []

    try:
        response = requests.get(
            DISEASE_SH_COUNTRIES_URL,
            params={"allowNull": "true", "sort": "deaths"},
            timeout=20,
        )
        if response.status_code != 200:
            print(f"disease.sh HTTP Error: {response.status_code}")
            return records

        rows = response.json() if response.content else []
        if not isinstance(rows, list):
            return records

        for item in rows[: max(limit, 1)]:
            country_info = item.get("countryInfo") or {}
            iso3 = _safe_iso3(country_info.get("iso3"))
            if not iso3:
                continue

            cases = item.get("cases")
            deaths = item.get("deaths")
            updated_ms = item.get("updated")
            updated_iso = collected_at
            try:
                if isinstance(updated_ms, (int, float)) and updated_ms > 0:
                    updated_iso = datetime.fromtimestamp(float(updated_ms) / 1000.0, tz=timezone.utc).isoformat()
            except Exception:
                pass

            record = {
                "source": "disease_sh",
                "category": "health",
                "collected_at": collected_at,
                "data": {
                    "country": iso3,
                    "SpatialDim": iso3,
                    "year": datetime.now(timezone.utc).year,
                    "indicator": "COVID19_CASES_DEATHS",
                    "value": cases,
                    "cases": cases,
                    "deaths": deaths,
                    "timestamp": updated_iso,
                    "disease": "COVID-19",
                },
            }
            records.append(record)

            try:
                send_to_kafka("who_indicators", record)
            except Exception as kafka_exc:
                print(f"Error sending disease.sh record to Kafka: {kafka_exc}")

    except Exception as exc:
        print(f"Error fetching disease.sh country data: {exc}")

    return records


def fetch_covid_vaccination_doses(limit: int = 260) -> list[dict[str, Any]]:
    collected_at = _now_iso()
    records: list[dict[str, Any]] = []
    name_map = _country_name_to_iso3_map()

    try:
        response = requests.get(
            DISEASE_SH_VACCINE_COUNTRIES_URL,
            params={"lastdays": 1, "fullData": "false"},
            timeout=20,
        )
        if response.status_code != 200:
            print(f"disease.sh vaccine HTTP Error: {response.status_code}")
            return records

        rows = response.json() if response.content else []
        if not isinstance(rows, list):
            return records

        for item in rows[: max(limit, 1)]:
            country_info = item.get("countryInfo") or {}
            country_name = str(item.get("country") or "").strip()
            iso3 = _safe_iso3(country_info.get("iso3"))
            if not iso3 and country_name:
                iso3 = _safe_iso3(name_map.get(_normalize_country_name(country_name)))
            if not iso3:
                continue

            timeline = item.get("timeline") or {}
            doses_value = None
            if isinstance(timeline, dict) and timeline:
                try:
                    doses_value = max(float(v) for v in timeline.values() if v is not None)
                except Exception:
                    doses_value = None
            if doses_value is None:
                continue

            record = {
                "source": "disease_sh_vaccine",
                "category": "health",
                "collected_at": collected_at,
                "data": {
                    "country": iso3,
                    "SpatialDim": iso3,
                    "year": datetime.now(timezone.utc).year,
                    "indicator": "COVID19_VACCINE_DOSES",
                    "value": doses_value,
                    "doses": doses_value,
                    "timestamp": collected_at,
                    "disease": "COVID-19",
                },
            }
            records.append(record)

            try:
                send_to_kafka("who_indicators", record)
            except Exception as kafka_exc:
                print(f"Error sending disease.sh vaccine record to Kafka: {kafka_exc}")

    except Exception as exc:
        print(f"Error fetching disease.sh vaccination data: {exc}")

    return records


def fetch_who_indicators(
    indicator_codes: list[str] | None = None,
    max_results_per_indicator: int = 250,
    include_covid_deaths: bool = True,
    max_covid_records: int = 260,
    include_vaccination_doses: bool = True,
    max_vaccination_records: int = 260,
) -> list[dict[str, Any]]:
    if indicator_codes is None:
        indicator_codes = DEFAULT_WHO_INDICATORS

    merged: list[dict[str, Any]] = []
    for code in indicator_codes:
        code_str = str(code or "").strip()
        if not code_str:
            continue
        merged.extend(fetch_who_indicator(code_str, max_results=max_results_per_indicator))

    if include_covid_deaths:
        merged.extend(fetch_covid_country_deaths(limit=max_covid_records))

    if include_vaccination_doses:
        merged.extend(fetch_covid_vaccination_doses(limit=max_vaccination_records))

    return merged


def convert_for_json(obj: Any):
    if isinstance(obj, dict):
        return {k: convert_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_for_json(i) for i in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj


if __name__ == "__main__":
    print("Starting WHO + health collector...")

    data = fetch_who_indicators(
        DEFAULT_WHO_INDICATORS,
        max_results_per_indicator=300,
        include_covid_deaths=True,
        max_covid_records=260,
        include_vaccination_doses=True,
        max_vaccination_records=260,
    )
    if data:
        insert("health", data)
        safe_data = convert_for_json(data[:20])
        print(json.dumps(safe_data, indent=2, ensure_ascii=False))
        print(f"Inserted {len(data)} health records")

    print("WHO + health collection finished.")
