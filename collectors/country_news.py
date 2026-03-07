import os
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

from database.mongo import db, insert
from collectors.gdelt import fetch_gdelt_articles
from processing.country_catalog import COUNTRY_NAMES
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

load_dotenv()
NEWS_API_KEY = (os.getenv("NEWS_API_KEY") or "").strip()
NEWS_API_URL = "https://newsapi.org/v2/everything"
analyzer = SentimentIntensityAnalyzer()
DEFAULT_MAX_RECORDS = 4
DEFAULT_PAUSE_SEC = 1.5
DEFAULT_BATCH_SIZE = 50
REFRESH_STATE_SERVICE = "country_news_refresh"


def get_target_country_codes():
    codes = sorted(db.country_features.distinct("country", {"mode": "online"}))
    if codes:
        return codes
    return sorted(COUNTRY_NAMES.keys())


def get_country_catalog():
    return {code: COUNTRY_NAMES.get(code, code) for code in get_target_country_codes()}


def _utc_day_bounds(day: datetime | None = None):
    current = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _format_gdelt_dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")


def _country_queries(country_name: str):
    base = country_name.strip()
    queries = [f'"{base}"', base]
    if " and " in base.lower():
        queries.append(base.replace(" and ", " "))
    return queries


def _normalize_country_articles(country_code: str, country_name: str, raw_records: list[dict], collected_at: datetime, source_name: str) -> list[dict]:
    normalized = []
    for record in raw_records:
        data = dict(record.get("data") or {})
        title = (data.get("title") or "").strip()
        if not title:
            continue
        sentiment = analyzer.polarity_scores(f"{title}. {data.get('description') or ''}")["compound"]
        data["sentiment"] = {"vader": {"compound": float(sentiment)}}
        data["country"] = country_code
        data["country_name"] = country_name
        normalized.append({
            "source": source_name,
            "category": "global_news",
            "country": country_code,
            "country_name": country_name,
            "collected_at": collected_at,
            "timestamp": collected_at,
            "data": data,
        })
    return normalized


def _fetch_newsapi_articles(query: str, start: datetime, end: datetime, max_records: int):
    if not NEWS_API_KEY:
        return []
    params = {
        "q": query,
        "pageSize": max_records,
        "apiKey": NEWS_API_KEY,
        "sortBy": "publishedAt",
        "language": "en",
        "from": start.isoformat(),
        "to": end.isoformat(),
        "searchIn": "title,description",
    }
    try:
        response = requests.get(NEWS_API_URL, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return []
    if payload.get("status") != "ok":
        return []

    records = []
    for item in payload.get("articles", []):
        records.append({
            "data": {
                "query": query,
                "title": item.get("title"),
                "description": item.get("description"),
                "url": item.get("url"),
                "published_at": item.get("publishedAt"),
                "source_name": (item.get("source") or {}).get("name"),
            }
        })
    return records


def _load_cached_country_news(country_code: str, day: datetime | None = None) -> list[dict]:
    start, end = _utc_day_bounds(day)
    return list(db.country_news.find({"country": country_code, "timestamp": {"$gte": start, "$lt": end}}).sort("timestamp", -1))


def _persist_country_news(records: list[dict]):
    if not records:
        return
    insert(
        "country_news",
        records,
        unique_keys=["country", "data.url", "data.title", "data.published_at"],
    )


def fetch_country_news(country_code: str, country_name: str, day: datetime | None = None, max_records: int = DEFAULT_MAX_RECORDS) -> list[dict]:
    day = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start, end = _utc_day_bounds(day)
    collected_at = datetime.now(timezone.utc)
    seen_keys = set()
    all_records = []

    for query in _country_queries(country_name):
        gdelt_records = fetch_gdelt_articles(
            query=query,
            max_records=max_records,
            startdatetime=_format_gdelt_dt(start),
            enddatetime=_format_gdelt_dt(end),
            sort="datedesc",
        )
        for normalized in _normalize_country_articles(country_code, country_name, gdelt_records, collected_at, "gdelt"):
            url = ((normalized.get("data") or {}).get("url") or "").strip()
            dedupe_key = url or f"gdelt:{country_code}:{(normalized.get('data') or {}).get('title')}"
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            all_records.append(normalized)
        if all_records:
            break

    if not all_records:
        for query in _country_queries(country_name):
            newsapi_records = _fetch_newsapi_articles(query, start, end, max_records)
            for normalized in _normalize_country_articles(country_code, country_name, newsapi_records, collected_at, "newsapi"):
                url = ((normalized.get("data") or {}).get("url") or "").strip()
                dedupe_key = url or f"newsapi:{country_code}:{(normalized.get('data') or {}).get('title')}"
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                all_records.append(normalized)
            if all_records:
                break

    _persist_country_news(all_records)
    return all_records


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


def refresh_country_news(
    day: datetime | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    pause_sec: float = DEFAULT_PAUSE_SEC,
    use_cache: bool = True,
) -> dict:
    target_day = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    catalog = list(get_country_catalog().items())
    state = _get_refresh_state(target_day)
    start_offset = int(state.get("next_offset", 0)) % max(len(catalog), 1)
    batch = _select_batch(catalog, start_offset, batch_size)
    summary = {
        "requested": len(catalog),
        "batch_size": len(batch),
        "start_offset": start_offset,
        "countries_with_articles": 0,
        "articles": 0,
        "cached_countries": [],
        "empty_countries": [],
        "failed_countries": {},
    }

    for code, name in batch:
        try:
            cached = _load_cached_country_news(code, target_day) if use_cache else []
            if cached:
                summary["cached_countries"].append(code)
                summary["countries_with_articles"] += 1
                summary["articles"] += len(cached)
            else:
                records = fetch_country_news(code, name, target_day, max_records)
                if records:
                    summary["countries_with_articles"] += 1
                    summary["articles"] += len(records)
                else:
                    summary["empty_countries"].append(code)
        except Exception as exc:
            summary["failed_countries"][code] = str(exc)
        if pause_sec > 0:
            time.sleep(pause_sec)

    next_offset = (start_offset + len(batch)) % max(len(catalog), 1)
    state.update({"next_offset": next_offset, "last_batch_size": len(batch)})
    _save_refresh_state(state)
    summary["next_offset"] = next_offset
    summary["cycle_completed"] = bool(catalog) and next_offset == 0
    return summary
