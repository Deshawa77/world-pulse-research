import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from dotenv import load_dotenv

from backend.kafka_client import send_to_kafka
from database.mongo import db, insert
from processing.country_catalog import COUNTRY_NAMES
from processing.signal_taxonomy import build_signal_metadata

load_dotenv(override=True)

TIMEOUT_SEC = int(os.getenv("YOUTUBE_TRENDS_TIMEOUT_SEC") or 20)
LOOKBACK_HOURS = int(os.getenv("YOUTUBE_TRENDS_LOOKBACK_HOURS") or 96)
KAFKA_TOPIC = "youtube_trends_topic"
SOURCE_NAME = "youtube_public"
DEFAULT_CHANNELS = {
    "USA": ["UCupvZG-5ko_eiXAupbDfxWw"],
    "GBR": ["UC16niRr50-MSBwiO3YDb3RA"],
    "IND": ["UC_aEa8K-EOJ3D6gOs7HcyNg"],
    "LKA": ["UC1Exm8wCHUwh5FhsiF5dL1A"],
}
NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def _load_registry() -> dict[str, list[str]]:
    raw = (os.getenv("YOUTUBE_TREND_CHANNELS_JSON") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k).strip().upper(): [str(vv).strip() for vv in vv_list if str(vv).strip()] for k, vv_list in parsed.items() if isinstance(vv_list, list)}
        except Exception:
            pass
    return DEFAULT_CHANNELS


def _health_row(status: str, latency_ms: float, error: str | None = None, records: int = 0) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {"source": SOURCE_NAME, "status": status, "critical": False, "latency_ms": round(latency_ms, 3), "last_checked": now, "last_success": now if status == "up" else None, "error": error, "records": int(records)}


def _persist_health(row: dict[str, Any]) -> None:
    db["source_health"].update_one({"source": row["source"]}, {"$set": {**row, "updated_at": datetime.now(timezone.utc).isoformat()}, "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)


def _feed_items(channel_id: str) -> list[dict[str, Any]]:
    response = requests.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}", timeout=TIMEOUT_SEC, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    root = ET.fromstring(response.text)
    items = []
    for entry in root.findall("atom:entry", NS):
        published = entry.findtext("atom:published", default="", namespaces=NS)
        title = entry.findtext("atom:title", default="", namespaces=NS)
        video_id = entry.findtext("yt:videoId", default="", namespaces=NS)
        items.append({"published": published, "title": title, "video_id": video_id})
    return items


def collect_youtube_trend_signals() -> dict[str, Any]:
    registry = _load_registry()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    collected_at = datetime.now(timezone.utc)
    records = []
    started = time.perf_counter()
    errors = []
    for country, channels in registry.items():
        recent = []
        for channel_id in channels:
            try:
                for item in _feed_items(channel_id):
                    raw_ts = str(item.get("published") or "").replace("Z", "+00:00")
                    try:
                        ts = datetime.fromisoformat(raw_ts)
                    except Exception:
                        continue
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    ts = ts.astimezone(timezone.utc)
                    if ts < cutoff:
                        continue
                    recent.append({**item, "channel_id": channel_id, "timestamp": ts.isoformat()})
            except Exception as exc:
                errors.append(f"{country}:{channel_id}:{exc}")
        if not recent:
            continue
        video_count = len(recent)
        unique_channels = len({item["channel_id"] for item in recent})
        narrative_velocity = min((video_count / max(unique_channels, 1)) / 10.0, 1.0)
        public_attention = min(video_count / 12.0, 1.0)
        records.append({
            "source": SOURCE_NAME,
            "category": "video_attention",
            "country": country,
            "country_name": COUNTRY_NAMES.get(country, country),
            "collected_at": collected_at,
            "timestamp": collected_at,
            **build_signal_metadata(source=SOURCE_NAME, observed_at=collected_at, ingested_at=collected_at, language="und", confidence=0.64, coverage_weight=0.58, signal_domain="social", signal_type="video_feed_velocity", signal_class="direct", source_tier="platform", geo_scope="country"),
            "data": {
                "video_count": video_count,
                "unique_channels": unique_channels,
                "public_attention_score": round(public_attention, 4),
                "narrative_velocity_score": round(narrative_velocity, 4),
                "channels": channels,
            },
        })
    inserted = insert("youtube_trends", records, unique_keys=["country", "collected_at"])
    for record in records:
        send_to_kafka(KAFKA_TOPIC, record, key=record.get("country"))
    health = _health_row("up" if records else "down", (time.perf_counter() - started) * 1000.0, error="; ".join(errors[:4]) if errors else (None if records else "no youtube trend rows"), records=len(records))
    _persist_health(health)
    return {"source": SOURCE_NAME, "records": len(records), "inserted": inserted, "errors": errors[:10], "health": health}


if __name__ == "__main__":
    print(collect_youtube_trend_signals())
