import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

from backend.kafka_client import send_to_kafka
from collectors.country_news import get_country_catalog
from database.mongo import db, insert
from processing.signal_taxonomy import build_signal_metadata

BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
DEFAULT_DAYS = 2
DEFAULT_BATCH_SIZE = 50
DEFAULT_PAUSE_SEC = 0.15
REFRESH_STATE_SERVICE = "country_attention_refresh"
HEADERS = {
    "User-Agent": "world_pulse_app (research project)",
}


def _utc_day_bounds(day: datetime | None = None):
    current = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _get_refresh_state(day: datetime):
    state = db.service_status.find_one({"service": REFRESH_STATE_SERVICE}) or {}
    day_key = day.astimezone(timezone.utc).date().isoformat()
    if state.get("day") != day_key:
        return {"service": REFRESH_STATE_SERVICE, "day": day_key, "next_offset": 0}
    return state


def _save_refresh_state(state: dict):
    db.service_status.update_one(
        {"service": REFRESH_STATE_SERVICE},
        {"$set": {**state, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


def _select_batch(items: list[tuple[str, str]], start_offset: int, batch_size: int):
    if not items:
        return []
    size = min(batch_size, len(items))
    return [items[(start_offset + idx) % len(items)] for idx in range(size)]


def _fetch_pageviews(article: str, days: int = DEFAULT_DAYS):
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=max(days, 2))
    start = start_date.strftime("%Y%m%d")
    end = end_date.strftime("%Y%m%d")
    url = f"{BASE_URL}/en.wikipedia/all-access/all-agents/{quote(article.replace(' ', '_'), safe='')}/daily/{start}/{end}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.json().get("items", [])
    except requests.RequestException:
        return []


def fetch_country_attention(country_code: str, country_name: str, days: int = DEFAULT_DAYS) -> list[dict]:
    items = _fetch_pageviews(country_name, days=days)
    if not items:
        return []
    collected_at = datetime.now(timezone.utc)
    rows: list[dict] = []
    previous_views = None
    for item in items[-2:]:
        views = int(item.get("views") or 0)
        if views <= 0:
            continue
        timestamp_raw = str(item.get("timestamp") or "")
        observed_at = datetime.strptime(timestamp_raw[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
        delta_ratio = 0.0 if previous_views in (None, 0) else max(min((views - previous_views) / float(previous_views), 3.0), -1.0)
        metadata = build_signal_metadata(
            source="wikipedia",
            observed_at=observed_at,
            ingested_at=collected_at,
            language="en",
            confidence=0.66,
            coverage_weight=0.75,
            geo_scope="country",
        )
        row = {
            "source": "wikipedia",
            "category": "public_attention",
            "country": country_code,
            "country_name": country_name,
            "collected_at": collected_at,
            "timestamp": collected_at,
            **metadata,
            "data": {
                "article": country_name,
                "date": observed_at.date().isoformat(),
                "views": views,
                "previous_views": previous_views,
                "view_delta_ratio": round(delta_ratio, 4),
            },
        }
        rows.append(row)
        previous_views = views
    return rows[-1:] if rows else []


def collect_country_attention(day: datetime | None = None, batch_size: int = DEFAULT_BATCH_SIZE, pause_sec: float = DEFAULT_PAUSE_SEC) -> dict:
    target_day = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    catalog = list(get_country_catalog().items())
    state = _get_refresh_state(target_day)
    start_offset = int(state.get("next_offset", 0)) % max(len(catalog), 1)
    batch = _select_batch(catalog, start_offset, batch_size)
    summary = {
        "requested": len(catalog),
        "batch_size": len(batch),
        "countries_with_attention": 0,
        "records": 0,
        "empty_countries": [],
    }
    for code, name in batch:
        records = fetch_country_attention(code, name)
        if records:
            insert("wiki", records, unique_keys=["country", "data.article", "data.date"])
            for record in records:
                send_to_kafka("wiki_pageviews", record, key=code)
            summary["countries_with_attention"] += 1
            summary["records"] += len(records)
        else:
            summary["empty_countries"].append(code)
        if pause_sec > 0:
            time.sleep(pause_sec)
    next_offset = (start_offset + len(batch)) % max(len(catalog), 1)
    state.update({"next_offset": next_offset, "last_batch_size": len(batch)})
    _save_refresh_state(state)
    summary["next_offset"] = next_offset
    summary["cycle_completed"] = bool(catalog) and next_offset == 0
    return summary


if __name__ == "__main__":
    print(collect_country_attention())
