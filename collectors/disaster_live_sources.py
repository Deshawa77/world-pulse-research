from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable

from database.mongo import db, insert

from collectors.disasters import (
    _normalize_earthquake,
    _normalize_reddit,
    _normalize_telegram,
    _normalize_weather,
    _normalize_world_state,
    _normalize_youtube,
    write_disaster_raw_batch,
)
from collectors.reddit import fetch_reddit_posts, reddit_configured
from collectors.telegram_public import collect_telegram_public_signals
from collectors.usgs import fetch_earthquakes
from collectors.weather import collect_weather_for_orchestrator
from collectors.world_state import _eonet, _firms, _noaa_cdo, _persist_source_health, _usgs
from collectors.youtube_trends import collect_youtube_trend_signals
from processing.disaster_feature_builder import build_disaster_feature_bundle

FAMILY_RATE_LIMIT_SECONDS = 1.0
MAX_RETRIES = 2
REDDIT_QUERIES = ("earthquake", "wildfire", "flood", "cyclone")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist_family_health(
    family: str,
    *,
    status: str,
    records: int,
    started_at: float,
    component_sources: list[str],
    error: str | None = None,
    rate_limited: bool = False,
    auth_failed: bool = False,
) -> dict[str, Any]:
    now = _now_iso()
    doc = {
        "source": f"disaster_family_{family}",
        "status": status,
        "critical": True,
        "latency_ms": round(max((time.perf_counter() - started_at) * 1000.0, 0.0), 3),
        "last_checked": now,
        "last_success": now if status == "up" else None,
        "records": int(max(records, 0)),
        "error": error,
        "rate_limited": bool(rate_limited),
        "auth_failed": bool(auth_failed),
        "component_sources": component_sources,
        "updated_at": now,
    }
    db["source_health"].update_one(
        {"source": doc["source"]},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return doc


def _retry_collect(label: str, fn: Callable[[], tuple[list[dict[str, Any]], dict[str, Any]]], max_retries: int = MAX_RETRIES) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    last_rows: list[dict[str, Any]] = []
    last_health: dict[str, Any] = {"source": label, "status": "down", "records": 0, "error": "not started"}
    for attempt in range(max(1, max_retries)):
        try:
            rows, health = fn()
        except Exception as exc:
            rows, health = [], {"source": label, "status": "down", "records": 0, "error": str(exc)}
        last_rows, last_health = rows, health
        if str(health.get("status") or "").lower() == "up":
            return rows, health
        if attempt < max_retries - 1:
            time.sleep(FAMILY_RATE_LIMIT_SECONDS * (attempt + 1))
    return last_rows, last_health


def _load_recent_rows(collection_name: str, since: datetime) -> list[dict[str, Any]]:
    return list(
        db[collection_name].find(
            {"collected_at": {"$gte": since}},
            {"_id": 0},
        ).sort("collected_at", -1)
    )


def collect_satellite_family() -> dict[str, Any]:
    started_at = time.perf_counter()
    signals, health = _retry_collect("firms", _firms)
    _persist_source_health([health])
    insert("world_state_signals", signals, unique_keys=["id"])
    normalized = [_normalize_world_state(signal) for signal in signals]
    write_summary = write_disaster_raw_batch(normalized, persist_db=True)
    family_health = _persist_family_health(
        "satellite_imagery",
        status="up" if normalized else str(health.get("status") or "down"),
        records=len(normalized),
        started_at=started_at,
        component_sources=["firms"],
        error=None if normalized else str(health.get("error") or "no satellite records"),
        rate_limited=bool(health.get("rate_limited")),
        auth_failed=bool(health.get("auth_failed")),
    )
    return {"family": "satellite_imagery", "records": len(normalized), "health": family_health, "write": write_summary}


def collect_seismic_family() -> dict[str, Any]:
    started_at = time.perf_counter()
    ws_signals, ws_health = _retry_collect("usgs", _usgs)
    _persist_source_health([ws_health])
    insert("world_state_signals", ws_signals, unique_keys=["id"])
    quake_rows = fetch_earthquakes()
    insert("earthquakes", quake_rows, unique_keys=["data.place", "data.time"])
    normalized = [_normalize_world_state(signal) for signal in ws_signals] + [_normalize_earthquake(row) for row in quake_rows]
    write_summary = write_disaster_raw_batch(normalized, persist_db=True)
    family_health = _persist_family_health(
        "seismic_data",
        status="up" if normalized else str(ws_health.get("status") or "down"),
        records=len(normalized),
        started_at=started_at,
        component_sources=["usgs", "earthquakes"],
        error=None if normalized else str(ws_health.get("error") or "no seismic records"),
        rate_limited=bool(ws_health.get("rate_limited")),
        auth_failed=bool(ws_health.get("auth_failed")),
    )
    return {"family": "seismic_data", "records": len(normalized), "health": family_health, "write": write_summary}


def collect_weather_family() -> dict[str, Any]:
    started_at = time.perf_counter()
    rows = collect_weather_for_orchestrator()
    if rows:
        insert("weather", rows, unique_keys=["source", "data_city", "data_timestamp"])
    normalized = [_normalize_weather(row) for row in rows]
    write_summary = write_disaster_raw_batch(normalized, persist_db=True)
    family_health = _persist_family_health(
        "weather_sensors",
        status="up" if normalized else "down",
        records=len(normalized),
        started_at=started_at,
        component_sources=["openweathermap"],
        error=None if normalized else "no weather records",
    )
    return {"family": "weather_sensors", "records": len(normalized), "health": family_health, "write": write_summary}


def collect_ocean_family() -> dict[str, Any]:
    started_at = time.perf_counter()
    component_rows: list[dict[str, Any]] = []
    component_health: list[dict[str, Any]] = []
    for name, fn in (("eonet", _eonet), ("noaa_cdo", _noaa_cdo)):
        rows, health = _retry_collect(name, fn)
        component_rows.extend(rows)
        component_health.append(health)
        time.sleep(FAMILY_RATE_LIMIT_SECONDS)
    _persist_source_health(component_health)
    insert("world_state_signals", component_rows, unique_keys=["id"])
    normalized = [_normalize_world_state(signal) for signal in component_rows]
    write_summary = write_disaster_raw_batch(normalized, persist_db=True)
    family_health = _persist_family_health(
        "ocean_sensors",
        status="up" if normalized else ("degraded" if any(str(row.get("status") or "") == "up" for row in component_health) else "down"),
        records=len(normalized),
        started_at=started_at,
        component_sources=["eonet", "noaa_cdo"],
        error=None if normalized else "; ".join(str(row.get("error") or "") for row in component_health if row.get("error")) or "no ocean records",
        rate_limited=any(bool(row.get("rate_limited")) for row in component_health),
        auth_failed=any(bool(row.get("auth_failed")) for row in component_health),
    )
    return {"family": "ocean_sensors", "records": len(normalized), "health": family_health, "write": write_summary}


def _collect_reddit_records(limit_per_query: int = 12) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not reddit_configured():
        return [], {"source": "reddit", "status": "down", "records": 0, "error": "reddit credentials unavailable", "auth_failed": True}
    rows: list[dict[str, Any]] = []
    try:
        for query in REDDIT_QUERIES:
            rows.extend(fetch_reddit_posts(query=query, limit=limit_per_query))
            time.sleep(FAMILY_RATE_LIMIT_SECONDS)
        if rows:
            insert("reddit", rows, unique_keys=["data.title", "data.url"])
        return rows, {"source": "reddit", "status": "up" if rows else "down", "records": len(rows), "error": None if rows else "no reddit records"}
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        return rows, {
            "source": "reddit",
            "status": "down",
            "records": len(rows),
            "error": message,
            "auth_failed": "401" in lowered or "unauthorized" in lowered or "forbidden" in lowered,
            "rate_limited": "429" in lowered or "rate limit" in lowered,
        }


def collect_social_family() -> dict[str, Any]:
    started_at = time.perf_counter()
    collected_at = datetime.now(timezone.utc)
    reddit_rows, reddit_health = _collect_reddit_records()
    telegram_summary = collect_telegram_public_signals()
    youtube_summary = collect_youtube_trend_signals()
    telegram_rows = _load_recent_rows("telegram_public", collected_at)
    youtube_rows = _load_recent_rows("youtube_trends", collected_at)
    normalized = [
        *[_normalize_reddit(row) for row in reddit_rows],
        *[_normalize_telegram(row) for row in telegram_rows],
        *[_normalize_youtube(row) for row in youtube_rows],
    ]
    write_summary = write_disaster_raw_batch(normalized, persist_db=True)
    family_health = _persist_family_health(
        "social_media_signals",
        status="up" if normalized else ("degraded" if telegram_rows or youtube_rows or reddit_rows else "down"),
        records=len(normalized),
        started_at=started_at,
        component_sources=["reddit", "telegram_public", "youtube_public"],
        error=None if normalized else str(reddit_health.get("error") or "no social records"),
        rate_limited=bool(reddit_health.get("rate_limited")),
        auth_failed=bool(reddit_health.get("auth_failed")),
    )
    return {
        "family": "social_media_signals",
        "records": len(normalized),
        "health": family_health,
        "write": write_summary,
        "components": {
            "reddit": len(reddit_rows),
            "telegram": int(telegram_summary.get("records") or 0),
            "youtube": int(youtube_summary.get("records") or 0),
        },
    }


def collect_disaster_source_families() -> dict[str, Any]:
    summaries = []
    for collector in (
        collect_satellite_family,
        collect_seismic_family,
        collect_weather_family,
        collect_ocean_family,
        collect_social_family,
    ):
        try:
            summaries.append(collector())
        except Exception as exc:
            summaries.append({
                "family": collector.__name__.replace("collect_", "").replace("_family", ""),
                "records": 0,
                "health": {"status": "down", "error": str(exc)},
            })
        time.sleep(FAMILY_RATE_LIMIT_SECONDS)
    feature_store_rows = 0
    feature_store_error = None
    try:
        feature_store_rows = len(build_disaster_feature_bundle(persist=True))
    except Exception as exc:
        feature_store_error = str(exc)
    return {
        "captured_at": _now_iso(),
        "families": summaries,
        "total_records": sum(int(item.get("records") or 0) for item in summaries),
        "feature_store_rows": feature_store_rows,
        "feature_store_error": feature_store_error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect live disaster source families and refresh normalized disaster raw signals")
    parser.parse_args()
    print(json.dumps(collect_disaster_source_families(), indent=2))


if __name__ == "__main__":
    main()
