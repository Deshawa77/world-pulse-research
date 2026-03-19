import hashlib
import math
import os
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

from database.mongo import db, insert
from collectors.gdelt import fetch_gdelt_articles
from processing.country_catalog import COUNTRY_NAMES
from processing.signal_taxonomy import build_signal_metadata
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

load_dotenv()
NEWS_API_KEY = (os.getenv("NEWS_API_KEY") or "").strip()
NEWS_API_URL = "https://newsapi.org/v2/everything"
NEWS_API_LANGUAGE = (os.getenv("NEWS_API_LANGUAGE") or "").strip()
TRANSLATE_PROVIDER = (os.getenv("NEWS_TRANSLATE_PROVIDER") or "mymemory").strip().lower()
LIBRETRANSLATE_URL = (os.getenv("LIBRETRANSLATE_URL") or "https://libretranslate.de/translate").strip()
MYMEMORY_URL = (os.getenv("MYMEMORY_TRANSLATE_URL") or "https://api.mymemory.translated.net/get").strip()
TRANSLATION_TIMEOUT_SEC = int(os.getenv("NEWS_TRANSLATION_TIMEOUT_SEC") or 15)
DEFAULT_MAX_RECORDS = 12
DEFAULT_CANDIDATE_MULTIPLIER = 6
DEFAULT_PAUSE_SEC = 1.5
DEFAULT_BATCH_SIZE = 50
MAX_ARTICLES_PER_SOURCE = 1
GDELT_QUERY_BUDGET = int(os.getenv("COUNTRY_NEWS_GDELT_QUERY_BUDGET") or 3)
NEWSAPI_QUERY_BUDGET = int(os.getenv("COUNTRY_NEWS_NEWSAPI_QUERY_BUDGET") or 4)
QUERY_CACHE_TTL_HOURS = int(os.getenv("COUNTRY_NEWS_QUERY_CACHE_TTL_HOURS") or 12)
REFRESH_STATE_SERVICE = "country_news_refresh"
analyzer = SentimentIntensityAnalyzer()

LANGUAGE_ALIASES = {
    "english": "en", "en": "en",
    "tamil": "ta", "ta": "ta",
    "sinhala": "si", "sinhalese": "si", "si": "si",
    "hindi": "hi", "hi": "hi",
    "arabic": "ar", "ar": "ar",
    "spanish": "es", "es": "es",
    "french": "fr", "fr": "fr",
    "german": "de", "de": "de",
    "italian": "it", "it": "it",
    "portuguese": "pt", "pt": "pt",
    "russian": "ru", "ru": "ru",
    "ukrainian": "uk", "uk": "uk",
    "turkish": "tr", "tr": "tr",
    "indonesian": "id", "id": "id",
    "japanese": "ja", "ja": "ja",
    "korean": "ko", "ko": "ko",
    "chinese": "zh", "mandarin": "zh", "zh": "zh",
    "vietnamese": "vi", "vi": "vi",
    "thai": "th", "th": "th",
}


def get_target_country_codes():
    try:
        codes = sorted(db.country_features.distinct("country", {"mode": "online"}))
        if codes:
            return codes
    except Exception:
        pass
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
    normalized = base.replace(" and ", " ") if " and " in base.lower() else base
    queries = [
        f'"{base}"',
        base,
        normalized,
        f'"{base}" politics OR government OR parliament OR election',
        f'"{base}" economy OR inflation OR jobs OR wages',
        f'"{base}" protest OR strike OR unrest OR migration',
        f'"{base}" prices OR fuel OR food OR household',
        f'"{base}" local OR province OR district OR city',
    ]
    return list(dict.fromkeys(query for query in queries if query.strip()))


def _parse_timestamp(value: str | None, fallback: datetime) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except Exception:
        return fallback
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _source_quality_weight(source_name: str) -> float:
    normalized = str(source_name or "").strip().lower()
    if not normalized:
        return 0.52
    elite_tokens = ("reuters", "associated press", "ap", "bbc", "financial times", "bloomberg", "dw", "france 24")
    if any(token in normalized for token in elite_tokens):
        return 0.92
    if normalized in {"gdelt", "newsapi"}:
        return 0.62
    return 0.72


def _normalize_language(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "und"
    return LANGUAGE_ALIASES.get(raw, raw[:2] if len(raw) >= 2 else raw)


def _cache_key(*parts: str) -> str:
    return hashlib.sha1("||".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()


def _load_query_cache(source: str, country_code: str, query: str, day: datetime):
    start, _ = _utc_day_bounds(day)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=QUERY_CACHE_TTL_HOURS)
    doc = db.country_news_query_cache.find_one({
        "source": source,
        "country": country_code,
        "query_hash": _cache_key(country_code, query, start.date().isoformat(), source),
        "cached_at": {"$gte": cutoff},
    })
    if doc and isinstance(doc.get("records"), list):
        return doc["records"]
    return None


def _store_query_cache(source: str, country_code: str, query: str, day: datetime, records: list[dict]):
    start, _ = _utc_day_bounds(day)
    db.country_news_query_cache.update_one(
        {
            "source": source,
            "country": country_code,
            "query_hash": _cache_key(country_code, query, start.date().isoformat(), source),
        },
        {
            "$set": {
                "source": source,
                "country": country_code,
                "day": start.date().isoformat(),
                "query": query,
                "records": records,
                "cached_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


def _load_translation_cache(text: str, source_lang: str):
    doc = db.translation_cache.find_one({"cache_key": _cache_key(text, source_lang, "en", TRANSLATE_PROVIDER)})
    if not doc:
        return None
    return {
        "translation": doc.get("translation"),
        "provider": doc.get("provider"),
        "confidence": float(doc.get("confidence") or 0.0),
    }


def _store_translation_cache(text: str, source_lang: str, translation: str | None, provider: str, confidence: float):
    db.translation_cache.update_one(
        {"cache_key": _cache_key(text, source_lang, "en", provider)},
        {"$set": {
            "cache_key": _cache_key(text, source_lang, "en", provider),
            "source_lang": source_lang,
            "target_lang": "en",
            "provider": provider,
            "translation": translation,
            "confidence": round(confidence, 4),
            "updated_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )


def _translate_via_mymemory(text: str, source_lang: str):
    response = requests.get(
        MYMEMORY_URL,
        params={"q": text, "langpair": f"{source_lang}|en"},
        timeout=TRANSLATION_TIMEOUT_SEC,
    )
    response.raise_for_status()
    payload = response.json() if response.content else {}
    translated = (((payload.get("responseData") or {}).get("translatedText")) or "").strip()
    quality = float(payload.get("responseStatus") == 200)
    return translated or None, quality


def _translate_via_libretranslate(text: str, source_lang: str):
    response = requests.post(
        LIBRETRANSLATE_URL,
        data={"q": text, "source": source_lang, "target": "en", "format": "text"},
        timeout=TRANSLATION_TIMEOUT_SEC,
    )
    response.raise_for_status()
    payload = response.json() if response.content else {}
    translated = str(payload.get("translatedText") or "").strip()
    return translated or None, 0.72


def _translate_text(text: str, source_lang: str):
    clean = str(text or "").strip()
    lang = _normalize_language(source_lang)
    if not clean:
        return None, None, 0.0
    if lang in {"en", "und"}:
        return clean, "identity", 1.0
    cached = _load_translation_cache(clean, lang)
    if cached:
        return cached.get("translation"), cached.get("provider"), float(cached.get("confidence") or 0.0)
    try:
        if TRANSLATE_PROVIDER == "libretranslate":
            translated, confidence = _translate_via_libretranslate(clean, lang)
            provider = "libretranslate"
        else:
            translated, confidence = _translate_via_mymemory(clean, lang)
            provider = "mymemory"
        _store_translation_cache(clean, lang, translated, provider, confidence)
        return translated, provider, confidence
    except Exception:
        _store_translation_cache(clean, lang, None, TRANSLATE_PROVIDER, 0.0)
        return None, TRANSLATE_PROVIDER, 0.0


def _article_score(country_name: str, article: dict, observed_at: datetime, now: datetime) -> float:
    data = article.get("data") or {}
    title = str(data.get("title_translated_en") or data.get("title") or "").strip()
    description = str(data.get("description_translated_en") or data.get("description") or "").strip()
    query = str(data.get("query") or "").strip().lower()
    source_name = str(data.get("source_name") or article.get("source") or "").strip()
    country_token = country_name.strip().lower()
    title_text = title.lower()
    desc_text = description.lower()

    country_bonus = 0.25 if country_token and country_token in title_text else 0.0
    country_bonus += 0.08 if country_token and country_token in desc_text else 0.0
    query_bonus = 0.08 if query and query.replace('"', '') in title_text else 0.0
    source_bonus = _source_quality_weight(source_name)
    translation_bonus = 0.06 if data.get("text_translated_en") else 0.0

    age_hours = max((now - observed_at).total_seconds() / 3600.0, 0.0)
    recency_bonus = math.exp(-age_hours / 18.0)
    richness_bonus = min(len(title) / 180.0, 0.08) + min(len(description) / 320.0, 0.05)

    return round((country_bonus + query_bonus + translation_bonus) + (source_bonus * 0.45) + (recency_bonus * 0.35) + richness_bonus, 6)


def _normalize_country_articles(country_code: str, country_name: str, raw_records: list[dict], collected_at: datetime, source_name: str) -> list[dict]:
    normalized = []
    for record in raw_records:
        data = dict(record.get("data") or {})
        title = (data.get("title") or "").strip()
        if not title:
            continue
        description = str(data.get("description") or "").strip()
        observed_at = _parse_timestamp(data.get("published_at"), collected_at)
        sentiment = analyzer.polarity_scores(f"{title}. {description}")["compound"]
        language = _normalize_language(data.get("language") or "und")
        text_original = ". ".join(part for part in [title, description] if part)
        title_translated_en, translation_provider, title_conf = _translate_text(title, language)
        description_translated_en, _, desc_conf = _translate_text(description, language)
        text_translated_en, _, text_conf = _translate_text(text_original, language)
        translation_conf = max(title_conf, desc_conf, text_conf)
        data["sentiment"] = {"vader": {"compound": float(sentiment)}}
        data["country"] = country_code
        data["country_name"] = country_name
        data["language"] = language
        data["source_name"] = str(data.get("source_name") or source_name).strip() or source_name
        data["title_original"] = title
        data["description_original"] = description
        data["text_original"] = text_original
        data["title_translated_en"] = title_translated_en
        data["description_translated_en"] = description_translated_en
        data["text_translated_en"] = text_translated_en
        data["translation_provider"] = translation_provider
        data["translation_confidence"] = round(translation_conf, 4)
        metadata = build_signal_metadata(
            source=source_name,
            observed_at=observed_at,
            ingested_at=collected_at,
            language=language,
            confidence=max(_source_quality_weight(data.get("source_name") or source_name), translation_conf or 0.0),
            coverage_weight=1.0,
            geo_scope="country",
        )
        normalized.append({
            "source": source_name,
            "category": "global_news",
            "country": country_code,
            "country_name": country_name,
            "collected_at": collected_at,
            "timestamp": collected_at,
            **metadata,
            "data": data,
            "observed_at": metadata["observed_at"],
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
        "from": start.isoformat(),
        "to": end.isoformat(),
        "searchIn": "title,description",
    }
    if NEWS_API_LANGUAGE:
        params["language"] = NEWS_API_LANGUAGE
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
                "language": item.get("language") or NEWS_API_LANGUAGE or "und",
            }
        })
    return records


def _fetch_gdelt_articles_cached(country_code: str, query: str, start: datetime, end: datetime, max_records: int, day: datetime):
    cached = _load_query_cache("gdelt", country_code, query, day)
    if cached is not None:
        return cached
    try:
        records = fetch_gdelt_articles(
            query=query,
            max_records=max_records,
            startdatetime=_format_gdelt_dt(start),
            enddatetime=_format_gdelt_dt(end),
            sort="datedesc",
        )
    except Exception:
        records = []
    _store_query_cache("gdelt", country_code, query, day, records)
    return records


def _fetch_newsapi_articles_cached(country_code: str, query: str, start: datetime, end: datetime, max_records: int, day: datetime):
    cached = _load_query_cache("newsapi", country_code, query, day)
    if cached is not None:
        return cached
    records = _fetch_newsapi_articles(query, start, end, max_records)
    _store_query_cache("newsapi", country_code, query, day, records)
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


def _rank_country_articles(country_name: str, records: list[dict], max_records: int, collected_at: datetime) -> list[dict]:
    scored = []
    for record in records:
        data = record.get("data") or {}
        dedupe_key = ((data.get("url") or "").strip() or f"{record.get('source')}::{(data.get('title') or '').strip().lower()}")
        observed_at = _parse_timestamp(data.get("published_at"), collected_at)
        score = _article_score(country_name, record, observed_at, collected_at)
        scored.append((dedupe_key, score, observed_at, record))

    deduped = {}
    for dedupe_key, score, observed_at, record in scored:
        prev = deduped.get(dedupe_key)
        if prev is None or score > prev[0]:
            deduped[dedupe_key] = (score, observed_at, record)

    ranked = sorted(deduped.values(), key=lambda item: (item[0], item[1]), reverse=True)
    per_source_counts: dict[str, int] = {}
    selected: list[dict] = []
    overflow: list[dict] = []

    for score, observed_at, record in ranked:
        source_name = str((record.get("data") or {}).get("source_name") or record.get("source") or "unknown").strip().lower()
        current = per_source_counts.get(source_name, 0)
        if current < MAX_ARTICLES_PER_SOURCE:
            per_source_counts[source_name] = current + 1
            selected.append(record)
        else:
            overflow.append(record)
        if len(selected) >= max_records:
            break

    if len(selected) < max_records:
        for record in overflow:
            selected.append(record)
            if len(selected) >= max_records:
                break

    return selected[:max_records]


def fetch_country_news(country_code: str, country_name: str, day: datetime | None = None, max_records: int = DEFAULT_MAX_RECORDS) -> list[dict]:
    day = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start, end = _utc_day_bounds(day)
    collected_at = datetime.now(timezone.utc)
    candidate_limit = max(max_records * DEFAULT_CANDIDATE_MULTIPLIER, max_records, 24)
    all_records: list[dict] = []
    gdelt_budget = GDELT_QUERY_BUDGET
    newsapi_budget = NEWSAPI_QUERY_BUDGET
    consecutive_gdelt_empty = 0

    for query in _country_queries(country_name):
        if gdelt_budget > 0 and consecutive_gdelt_empty < 2 and len(all_records) < candidate_limit:
            gdelt_budget -= 1
            gdelt_records = _fetch_gdelt_articles_cached(country_code, query, start, end, candidate_limit, day)
            all_records.extend(_normalize_country_articles(country_code, country_name, gdelt_records, collected_at, "gdelt"))
            consecutive_gdelt_empty = consecutive_gdelt_empty + 1 if not gdelt_records else 0
        if newsapi_budget > 0 and len(all_records) < candidate_limit:
            newsapi_budget -= 1
            newsapi_records = _fetch_newsapi_articles_cached(country_code, query, start, end, candidate_limit, day)
            all_records.extend(_normalize_country_articles(country_code, country_name, newsapi_records, collected_at, "newsapi"))
        if len(all_records) >= candidate_limit:
            break

    final_records = _rank_country_articles(country_name, all_records, max_records, collected_at)
    _persist_country_news(final_records)
    return final_records


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
