import json
import os
import re
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

TIMEOUT_SEC = int(os.getenv("TELEGRAM_PUBLIC_TIMEOUT_SEC") or 20)
LOOKBACK_HOURS = int(os.getenv("TELEGRAM_PUBLIC_LOOKBACK_HOURS") or 72)
KAFKA_TOPIC = "telegram_public_topic"
SOURCE_NAME = "telegram_public"
DEFAULT_CHANNELS = {
    "UKR": ["UkraineNow"],
    "RUS": ["rian_ru"],
    "ISR": ["ynetnews"],
    "IND": ["WIONews"],
    "LKA": ["newsfirstsl"],
}
UNREST_TERMS = ("protest", "strike", "riot", "clash", "march", "rally", "shutdown", "violence")


def _load_registry() -> dict[str, list[str]]:
    raw = (os.getenv("TELEGRAM_PUBLIC_CHANNELS_JSON") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k).strip().upper(): [str(vv).strip() for vv in vv_list if str(vv).strip()] for k, vv_list in parsed.items() if isinstance(vv_list, list)}
        except Exception:
            pass
    return DEFAULT_CHANNELS


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


def _extract_posts(html: str) -> list[dict[str, Any]]:
    dates = re.findall(r'time datetime="([^"]+)"', html)
    bodies = re.findall(r'tgme_widget_message_text[^>]*>(.*?)</div>', html, flags=re.S)
    links = re.findall(r'href="([^"]+)"', html)
    posts = []
    for idx, stamp in enumerate(dates[: len(bodies) or len(dates)]):
        body = re.sub(r'<[^>]+>', ' ', bodies[idx] if idx < len(bodies) else '')
        body = re.sub(r'\s+', ' ', body).strip()
        posts.append({"timestamp": stamp, "text": body, "links": links[idx * 3:(idx * 3) + 3]})
    return posts


def collect_telegram_public_signals() -> dict[str, Any]:
    registry = _load_registry()
    lookback_cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    collected_at = datetime.now(timezone.utc)
    records = []
    started = time.perf_counter()
    errors = []
    for country, channels in registry.items():
        recent_posts = []
        repeated_fragments = {}
        unrest_hits = 0
        for handle in channels:
            try:
                response = requests.get(f"https://t.me/s/{handle}", timeout=TIMEOUT_SEC, headers={"User-Agent": "Mozilla/5.0"})
                response.raise_for_status()
                posts = _extract_posts(response.text)
                for post in posts:
                    raw_ts = str(post.get("timestamp") or "").replace("Z", "+00:00")
                    try:
                        ts = datetime.fromisoformat(raw_ts)
                    except Exception:
                        continue
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    ts = ts.astimezone(timezone.utc)
                    if ts < lookback_cutoff:
                        continue
                    text = str(post.get("text") or "")
                    if any(term in text.lower() for term in UNREST_TERMS):
                        unrest_hits += 1
                    fragment = text[:160].lower()
                    if fragment:
                        repeated_fragments[fragment] = repeated_fragments.get(fragment, 0) + 1
                    recent_posts.append({"channel": handle, "timestamp": ts.isoformat(), "text": text})
            except Exception as exc:
                errors.append(f"{country}:{handle}:{exc}")
        if not recent_posts:
            continue
        unique_channels = len({post["channel"] for post in recent_posts})
        post_count = len(recent_posts)
        coordination_risk = min(max((sum(1 for v in repeated_fragments.values() if v >= 2) / max(len(repeated_fragments), 1)) * 1.4, 0.0), 1.0)
        narrative_velocity = min((post_count / max(unique_channels, 1)) / 8.0, 1.0)
        social_unrest = min((unrest_hits / max(post_count, 1)) * 2.0, 1.0)
        records.append({
            "source": SOURCE_NAME,
            "category": "social_public_channels",
            "country": country,
            "country_name": COUNTRY_NAMES.get(country, country),
            "collected_at": collected_at,
            "timestamp": collected_at,
            **build_signal_metadata(source=SOURCE_NAME, observed_at=collected_at, ingested_at=collected_at, language="und", confidence=0.62, coverage_weight=0.55, signal_domain="social", signal_type="public_channel_posts", signal_class="direct", source_tier="community", geo_scope="country"),
            "data": {
                "post_count": post_count,
                "unique_channels": unique_channels,
                "narrative_velocity_score": round(narrative_velocity, 4),
                "coordination_risk_score": round(coordination_risk, 4),
                "social_unrest_score": round(social_unrest, 4),
                "channels": channels,
            },
        })
    inserted = insert("telegram_public", records, unique_keys=["country", "collected_at"])
    for record in records:
        send_to_kafka(KAFKA_TOPIC, record, key=record.get("country"))
    health = _health_row("up" if records else "down", (time.perf_counter() - started) * 1000.0, error="; ".join(errors[:4]) if errors else (None if records else "no telegram public rows"), records=len(records))
    _persist_health(health)
    return {"source": SOURCE_NAME, "records": len(records), "inserted": inserted, "errors": errors[:10], "health": health}


if __name__ == "__main__":
    print(collect_telegram_public_signals())
