from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from database.mongo import db
from processing.disaster_storage import persist_disaster_raw_manifests

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data_lake" / "disasters" / "raw"
RAW_BUCKETS = {
    "satellite": RAW_ROOT / "satellite",
    "seismic": RAW_ROOT / "seismic",
    "weather": RAW_ROOT / "weather",
    "ocean": RAW_ROOT / "ocean",
    "social": RAW_ROOT / "social",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _event_type_from_source(source: str, category: str, signal_type: str) -> str:
    src = source.lower().strip()
    cat = category.lower().strip()
    sig = signal_type.lower().strip()
    if src == "usgs":
        return "earthquake"
    if src == "firms" or "wildfire" in cat:
        return "wildfire"
    if "flood" in cat:
        return "flood"
    if any(token in cat for token in ("cyclone", "hurricane", "typhoon", "storm")):
        return "cyclone"
    if sig == "disaster_intensity":
        return "flood"
    if sig == "humanitarian_pressure":
        return "humanitarian"
    return "weather"


def _event_type_from_text(text: str) -> str:
    value = (text or "").lower()
    if any(token in value for token in ("earthquake", "quake", "tremor", "aftershock", "seismic")):
        return "earthquake"
    if any(token in value for token in ("wildfire", "fire", "smoke", "burn")):
        return "wildfire"
    if any(token in value for token in ("cyclone", "hurricane", "typhoon", "storm surge", "landfall")):
        return "cyclone"
    if any(token in value for token in ("flood", "flooding", "overflow", "monsoon", "heavy rain")):
        return "flood"
    return "weather"


def _bucket_from_record(source: str, event_type: str) -> str:
    src = source.lower().strip()
    evt = event_type.lower().strip()
    if src in {"firms", "modis", "viirs"}:
        return "satellite"
    if src in {"usgs"} or evt == "earthquake":
        return "seismic"
    if src in {"reddit", "telegram_public", "youtube_trends", "youtube_public", "twitter", "x"}:
        return "social"
    if src in {"eonet", "ocean", "noaa", "noaa_cdo"} or evt == "cyclone":
        return "ocean"
    return "weather"



def _canonical_source_family(source: str, event_type: str) -> str:
    bucket = _bucket_from_record(source, event_type)
    if bucket == "satellite":
        return "satellite_imagery"
    if bucket == "seismic":
        return "seismic_data"
    if bucket == "ocean":
        return "ocean_sensors"
    if bucket == "social":
        return "social_media_signals"
    return "weather_sensors"

def _normalize_world_state(doc: dict[str, Any]) -> dict[str, Any]:
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    source = str(doc.get("source") or "world_state")
    signal_type = str(doc.get("signal_type") or "")
    category = str(meta.get("category") or "")
    event_type = _event_type_from_source(source, category, signal_type)
    ts = _parse_dt(doc.get("timestamp_utc") or doc.get("timestamp")) or datetime.now(timezone.utc)
    lat = _safe_float(doc.get("lat"), default=float("nan"))
    lon = _safe_float(doc.get("lon"), default=float("nan"))
    source_family = _canonical_source_family(source, event_type)
    return {
        "record_id": str(uuid.uuid4()),
        "source": source,
        "event_type": event_type,
        "country": str(doc.get("country") or "GLB").upper(),
        "lat": None if lat != lat else round(lat, 5),
        "lon": None if lon != lon else round(lon, 5),
        "timestamp": ts.isoformat(),
        "confidence": round(_safe_float(doc.get("confidence"), 0.5), 3),
        "severity_proxy": round(_safe_float(doc.get("value"), 0.0), 3),
        "signal_sources": [source_family],
        "top_contributing_signals": [s for s in [category, signal_type] if s][:3],
        "raw": {
            "title": str(meta.get("title") or meta.get("place") or ""),
            "category": category,
            "signal_type": signal_type,
            "value": _safe_float(doc.get("value"), 0.0),
        },
    }


def _normalize_weather(doc: dict[str, Any]) -> dict[str, Any]:
    text = str(doc.get("data_weather") or "").lower()
    event_type = "cyclone" if any(token in text for token in ("cyclone", "hurricane", "typhoon", "storm")) else ("flood" if any(token in text for token in ("flood", "heavy rain", "monsoon")) else "weather")
    ts = _parse_dt(doc.get("data_timestamp") or doc.get("collected_at")) or datetime.now(timezone.utc)
    temp = _safe_float(doc.get("data_temperature"), 0.0)
    wind = _safe_float(doc.get("data_wind_speed"), 0.0)
    severity = max(_safe_float(doc.get("data_temperature_normalized"), 0.0), min(wind / 120.0, 1.0))
    return {
        "record_id": str(uuid.uuid4()),
        "source": str(doc.get("source") or "weather"),
        "event_type": event_type,
        "country": str(doc.get("data_country") or doc.get("country") or "GLB").upper(),
        "lat": _safe_float(doc.get("lat"), default=None),
        "lon": _safe_float(doc.get("lon"), default=None),
        "timestamp": ts.isoformat(),
        "confidence": 0.55,
        "severity_proxy": round(severity, 3),
        "signal_sources": ["weather_sensors"],
        "top_contributing_signals": [token for token in ["temperature", "wind", text[:48] if text else ""] if token][:3],
        "raw": {
            "temperature": temp,
            "wind_speed": wind,
            "description": text,
        },
    }


def _normalize_earthquake(doc: dict[str, Any]) -> dict[str, Any]:
    ts = _parse_dt(doc.get("timestamp") or doc.get("timestamp_utc") or doc.get("collected_at")) or datetime.now(timezone.utc)
    mag = _safe_float(doc.get("mag"), 0.0)
    lat = _safe_float(doc.get("lat"), default=float("nan"))
    lon = _safe_float(doc.get("lon"), default=float("nan"))
    return {
        "record_id": str(uuid.uuid4()),
        "source": str(doc.get("source") or "usgs"),
        "event_type": "earthquake",
        "country": str(doc.get("country") or "GLB").upper(),
        "lat": None if lat != lat else round(lat, 5),
        "lon": None if lon != lon else round(lon, 5),
        "timestamp": ts.isoformat(),
        "confidence": 0.6,
        "severity_proxy": round(min(max(mag / 8.0, 0.0), 1.0), 3),
        "signal_sources": ["seismic_data"],
        "top_contributing_signals": ["magnitude", "seismic sequence"],
        "raw": {
            "mag": mag,
            "place": str(doc.get("place") or ""),
            "depth": _safe_float(doc.get("depth"), 0.0),
        },
    }


def _normalize_reddit(doc: dict[str, Any]) -> dict[str, Any]:
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    text = " ".join(part for part in [str(data.get("title") or ""), str(data.get("text") or "")] if part).strip()
    event_type = _event_type_from_text(text)
    ts = _parse_dt(data.get("created_utc") or doc.get("collected_at")) or datetime.now(timezone.utc)
    score = _safe_float(data.get("score"), 0.0)
    return {
        "record_id": str(uuid.uuid4()),
        "source": "reddit",
        "event_type": event_type,
        "country": str(doc.get("country") or "GLB").upper(),
        "lat": None,
        "lon": None,
        "timestamp": ts.isoformat(),
        "confidence": 0.46,
        "severity_proxy": round(min(max(score / 500.0, 0.0), 1.0), 3),
        "signal_sources": ["social_media_signals"],
        "top_contributing_signals": ["reddit discussion", text[:64] if text else "social chatter"],
        "raw": {
            "title": str(data.get("title") or ""),
            "score": score,
            "subreddit": str(data.get("subreddit") or ""),
        },
    }


def _normalize_telegram(doc: dict[str, Any]) -> dict[str, Any]:
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    text = " ".join(str(v) for v in [data.get("summary"), data.get("topic"), data.get("label")] if v)
    event_type = _event_type_from_text(text)
    ts = _parse_dt(doc.get("timestamp") or doc.get("collected_at")) or datetime.now(timezone.utc)
    intensity = max(
        _safe_float(data.get("social_unrest_score"), 0.0),
        _safe_float(data.get("narrative_velocity_score"), 0.0),
        _safe_float(data.get("public_attention_score"), 0.0),
    )
    return {
        "record_id": str(uuid.uuid4()),
        "source": "telegram_public",
        "event_type": event_type,
        "country": str(doc.get("country") or "GLB").upper(),
        "lat": None,
        "lon": None,
        "timestamp": ts.isoformat(),
        "confidence": 0.52,
        "severity_proxy": round(min(max(intensity, 0.0), 1.0), 3),
        "signal_sources": ["social_media_signals"],
        "top_contributing_signals": ["public channel velocity", text[:64] if text else "coordination chatter"],
        "raw": {
            "post_count": _safe_float(data.get("post_count"), 0.0),
            "narrative_velocity_score": _safe_float(data.get("narrative_velocity_score"), 0.0),
            "social_unrest_score": _safe_float(data.get("social_unrest_score"), 0.0),
        },
    }


def _normalize_youtube(doc: dict[str, Any]) -> dict[str, Any]:
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    text = " ".join(str(v) for v in [data.get("headline"), data.get("topic"), data.get("label")] if v)
    event_type = _event_type_from_text(text)
    ts = _parse_dt(doc.get("timestamp") or doc.get("collected_at")) or datetime.now(timezone.utc)
    attention = max(_safe_float(data.get("public_attention_score"), 0.0), _safe_float(data.get("narrative_velocity_score"), 0.0))
    return {
        "record_id": str(uuid.uuid4()),
        "source": "youtube_trends",
        "event_type": event_type,
        "country": str(doc.get("country") or "GLB").upper(),
        "lat": None,
        "lon": None,
        "timestamp": ts.isoformat(),
        "confidence": 0.5,
        "severity_proxy": round(min(max(attention, 0.0), 1.0), 3),
        "signal_sources": ["social_media_signals"],
        "top_contributing_signals": ["video attention spike", text[:64] if text else "public attention"],
        "raw": {
            "video_count": _safe_float(data.get("video_count"), 0.0),
            "public_attention_score": _safe_float(data.get("public_attention_score"), 0.0),
            "narrative_velocity_score": _safe_float(data.get("narrative_velocity_score"), 0.0),
        },
    }


def _ensure_dirs() -> None:
    for path in RAW_BUCKETS.values():
        path.mkdir(parents=True, exist_ok=True)


def build_disaster_raw_batch(hours: int = 72, limit_per_source: int = 1200) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(hours=max(1, int(hours)))

    batch: list[dict[str, Any]] = []

    world_state_docs = list(db["world_state_signals"].find({}, {"_id": 0}).sort("timestamp_utc", -1).limit(limit_per_source))
    for doc in world_state_docs:
        stamp = _parse_dt(doc.get("timestamp_utc") or doc.get("timestamp"))
        if stamp and stamp < cutoff:
            continue
        batch.append(_normalize_world_state(doc))

    weather_docs = list(db["weather"].find({}, {"_id": 0}).sort("collected_at", -1).limit(limit_per_source))
    for doc in weather_docs:
        stamp = _parse_dt(doc.get("data_timestamp") or doc.get("collected_at"))
        if stamp and stamp < cutoff:
            continue
        batch.append(_normalize_weather(doc))

    quake_docs = list(db["earthquakes"].find({}, {"_id": 0}).sort("timestamp", -1).limit(limit_per_source))
    for doc in quake_docs:
        stamp = _parse_dt(doc.get("timestamp") or doc.get("timestamp_utc") or doc.get("collected_at"))
        if stamp and stamp < cutoff:
            continue
        batch.append(_normalize_earthquake(doc))

    social_limit = max(80, int(limit_per_source / 4))
    reddit_docs = list(db["reddit"].find({}, {"_id": 0, "country": 1, "collected_at": 1, "data": 1}).sort("collected_at", -1).limit(social_limit))
    for doc in reddit_docs:
        stamp = _parse_dt((doc.get("data") or {}).get("created_utc") if isinstance(doc.get("data"), dict) else None) or _parse_dt(doc.get("collected_at"))
        if stamp and stamp < cutoff:
            continue
        batch.append(_normalize_reddit(doc))

    telegram_docs = list(db["telegram_public"].find({}, {"_id": 0, "country": 1, "timestamp": 1, "collected_at": 1, "data": 1}).sort("collected_at", -1).limit(social_limit))
    for doc in telegram_docs:
        stamp = _parse_dt(doc.get("timestamp") or doc.get("collected_at"))
        if stamp and stamp < cutoff:
            continue
        batch.append(_normalize_telegram(doc))

    youtube_docs = list(db["youtube_trends"].find({}, {"_id": 0, "country": 1, "timestamp": 1, "collected_at": 1, "data": 1}).sort("collected_at", -1).limit(social_limit))
    for doc in youtube_docs:
        stamp = _parse_dt(doc.get("timestamp") or doc.get("collected_at"))
        if stamp and stamp < cutoff:
            continue
        batch.append(_normalize_youtube(doc))

    return batch


def write_disaster_raw_batch(batch: list[dict[str, Any]], persist_db: bool = True) -> dict[str, Any]:
    _ensure_dirs()
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bucket_counts = {key: 0 for key in RAW_BUCKETS.keys()}
    written_files: dict[str, str] = {}

    by_bucket: dict[str, list[dict[str, Any]]] = {key: [] for key in RAW_BUCKETS.keys()}
    for record in batch:
        bucket = _bucket_from_record(str(record.get("source") or ""), str(record.get("event_type") or ""))
        by_bucket[bucket].append(record)

    for bucket, rows in by_bucket.items():
        if not rows:
            continue
        output_path = RAW_BUCKETS[bucket] / f"batch_{run_ts}.jsonl"
        with output_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=True))
                handle.write("\n")
        bucket_counts[bucket] = len(rows)
        written_files[bucket] = str(output_path)

    inserted = 0
    if persist_db and batch:
        try:
            result = db["disaster_signals_raw"].insert_many(batch, ordered=False)
            inserted = len(result.inserted_ids)
        except Exception:
            inserted = 0

    manifest_summary = persist_disaster_raw_manifests(run_ts, by_bucket, written_files, inserted_records=inserted)

    return {
        "status": "ok",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "total_records": len(batch),
        "inserted_records": inserted,
        "bucket_counts": bucket_counts,
        "manifest_path": manifest_summary.get("manifest_path"),
    }


def run_disaster_batch_ingestion(hours: int = 72, limit_per_source: int = 1200, persist_db: bool = True) -> dict[str, Any]:
    batch = build_disaster_raw_batch(hours=hours, limit_per_source=limit_per_source)
    summary = write_disaster_raw_batch(batch, persist_db=persist_db)
    try:
        from processing.disaster_feature_builder import build_disaster_feature_bundle
        feature_bundles = build_disaster_feature_bundle(persist=True)
        summary["feature_store_rows"] = len(feature_bundles)
    except Exception as exc:
        summary["feature_store_error"] = str(exc)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build normalized disaster raw batch snapshots from existing sources")
    parser.add_argument("--hours", type=int, default=72)
    parser.add_argument("--limit-per-source", type=int, default=1200)
    parser.add_argument("--no-db", action="store_true", help="Skip Mongo persistence and only write jsonl files")
    args = parser.parse_args()

    summary = run_disaster_batch_ingestion(hours=args.hours, limit_per_source=args.limit_per_source, persist_db=not args.no_db)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()





