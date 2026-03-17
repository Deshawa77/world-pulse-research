from pytrends.request import TrendReq
from datetime import datetime, timezone
import time
import random
import json
import requests
from database.mongo import insert
from backend.kafka_client import send_to_kafka  # Make sure this exists
from pytrends.exceptions import TooManyRequestsError

DEFAULT_TREND_KEYWORDS = [
    "election",
    "ai",
    "stock market",
    "bitcoin",
    "inflation",
    "job market",
    "climate change",
    "travel",
    "football",
    "olympics",
    "movie releases",
    "celebrity",
    "earthquake",
    "outbreak",
    "cyberattack",
    "geopolitics",
]

DEFAULT_TREND_REGIONS = [
    "US", "GB", "IN", "JP", "AU",
    "CA", "DE", "FR", "IT", "ES",
    "NL", "SE", "NO", "DK", "FI",
    "PL", "BR", "MX", "AR", "CL",
    "ZA", "NG", "EG", "TR", "KR",
]

def _extract_iso3_to_iso2_map():
    """Read ISO2->ISO3 map literal from backend/main.py and invert it without importing backend.main."""
    try:
        import ast
        from pathlib import Path

        backend_path = Path(__file__).resolve().parents[1] / "backend" / "main.py"
        text = backend_path.read_text(encoding="utf-8", errors="ignore")
        marker = "ISO2_TO_ISO3 = {"
        start = text.find(marker)
        if start < 0:
            return {}
        brace_start = text.find("{", start)
        if brace_start < 0:
            return {}

        depth = 0
        end = -1
        for idx in range(brace_start, len(text)):
            ch = text[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = idx
                    break
        if end < 0:
            return {}

        iso2_to_iso3 = ast.literal_eval(text[brace_start:end + 1])
        return {
            str(iso3).upper(): str(iso2).upper()
            for iso2, iso3 in (iso2_to_iso3 or {}).items()
            if isinstance(iso2, str) and isinstance(iso3, str)
        }
    except Exception:
        return {}


def _catalog_trend_regions(default_regions=None):
    """Build Trends region list from country catalog (up to full map), fallback to defaults."""
    fallback = list(default_regions or [])
    try:
        from processing.country_catalog import COUNTRY_NAMES

        iso3_to_iso2 = _extract_iso3_to_iso2_map()
        regions = []
        seen = set()
        for iso3 in COUNTRY_NAMES.keys():
            code3 = str(iso3 or "").strip().upper()
            if not code3 or code3 == "UNK":
                continue
            iso2 = iso3_to_iso2.get(code3)
            if not iso2 or len(iso2) != 2:
                continue
            if iso2 in seen:
                continue
            seen.add(iso2)
            regions.append(iso2)

        # Keep deterministic order and always include fallback regions.
        for code in fallback:
            code2 = str(code or "").strip().upper()
            if len(code2) == 2 and code2 not in seen:
                seen.add(code2)
                regions.append(code2)

        return regions or fallback
    except Exception:
        return fallback

def infer_keyword_category(keyword):
    """
    Assign a lightweight category so dashboard filters have variety.
    """
    token = str(keyword or "").strip().lower()
    if token in {"earthquake", "flood", "wildfire", "hurricane"}:
        return "Disaster"
    if token in {"outbreak", "pandemic", "public health"}:
        return "Health"
    if token in {"inflation", "recession", "stock market", "job market", "bitcoin"}:
        return "Economy"
    if token in {"cyberattack", "cyber threat", "ai"}:
        return "Technology"
    if token in {"election", "geopolitics", "war", "diplomacy"}:
        return "Politics"
    if token in {"football", "olympics", "cricket", "nba", "nfl"}:
        return "Sports"
    if token in {"movie releases", "celebrity", "music", "streaming"}:
        return "Entertainment"
    if token in {"travel", "tourism"}:
        return "Travel"
    if token in {"climate change", "climate", "heatwave"}:
        return "Climate"
    return "Public Interest"





def fetch_trending_search_queries(regions=None, max_terms_per_region=25, max_retries=4):
    """
    Fetch live trending search queries from Google Trends daily RSS feeds by region.
    """
    if regions is None:
        regions = _catalog_trend_regions(DEFAULT_TREND_REGIONS)

    import xml.etree.ElementTree as ET

    collected_at = datetime.now(timezone.utc).isoformat()
    records = []
    seen_queries = set()


    region_aliases = {
        "UK": "GB",
    }
    normalized = []
    seen_regions = set()
    for raw_region in regions:
        region_code = str(raw_region or "").strip().upper()
        region_code = region_aliases.get(region_code, region_code)
        if len(region_code) != 2 or (not region_code.isalpha()) or region_code in seen_regions:
            continue
        seen_regions.add(region_code)
        normalized.append(region_code)
    regions = normalized

    effective_max_retries = 1 if len(regions) >= 120 else max_retries
    request_timeout = 8 if len(regions) >= 120 else 20

    for raw_region in regions:
        region_code = str(raw_region or "").strip().upper()
        if not region_code:
            continue

        url = f"https://trends.google.com/trending/rss?geo={region_code}"
        xml_text = None

        for attempt in range(effective_max_retries):
            try:
                response = requests.get(url, timeout=request_timeout)
                if response.status_code != 200:
                    if attempt == effective_max_retries - 1:
                        print(f"[trending_rss {region_code}] HTTP {response.status_code}")
                    time.sleep(random.uniform(1.5, 3.5))
                    continue
                xml_text = response.text
                break
            except Exception as exc:
                if attempt == effective_max_retries - 1:
                    print(f"[trending_rss {region_code}] failed: {exc}")
                time.sleep(random.uniform(1.5, 3.5))

        if not xml_text:
            continue

        try:
            root = ET.fromstring(xml_text)
        except Exception as exc:
            print(f"[trending_rss {region_code}] parse error: {exc}")
            continue

        channel = root.find("channel")
        if channel is None:
            continue

        rank = 0
        for item in channel.findall("item"):
            if rank >= max_terms_per_region:
                break
            title_node = item.find("title")
            if title_node is None:
                continue
            query = str(title_node.text or "").strip()
            if not query:
                continue

            query_key = query.lower()
            if query_key in seen_queries:
                continue
            seen_queries.add(query_key)

            rank += 1
            category = infer_keyword_category(query)
            interest_score = max(100 - ((rank - 1) * 2), 25)

            # Google RSS namespace tag often includes approximate traffic.
            approx_traffic = None
            for child in item:
                if child.tag.endswith("approx_traffic") and child.text:
                    approx_traffic = str(child.text).strip()
                    break

            record = {
                "source": "google_trends_live",
                "category": "public_interest",
                "topic": query,
                "trend_category": category,
                "collected_at": collected_at,
                "data": {
                    "keyword": query,
                    "topic": query,
                    "query": query,
                    "category": category,
                    "geo": region_code,
                    "rank": rank,
                    "date": collected_at,
                    "interest": int(interest_score),
                    "approx_traffic": approx_traffic,
                    "source_mode": "trending_searches",
                    "related_queries": [f"{query} news", f"{query} latest", f"{query} live"],
                },
            }
            records.append(record)
            try:
                send_to_kafka("trends", record)
            except Exception as kafka_exc:
                print(f"Error sending live trend record to Kafka: {kafka_exc}")

    return records


def fetch_trends(keyword="football", max_retries=5):
    """
    Fetch Google Trends data for the past 7 days and return standardized records.
    Handles rate limiting (429) with retries and random delays.
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))

    for attempt in range(effective_max_retries):
        try:
            pytrends.build_payload(kw_list=[keyword], timeframe="now 7-d", geo="", gprop="")
            time.sleep(random.uniform(5, 10))  # Random delay to avoid rate limits
            df = pytrends.interest_over_time()
            break
        except TooManyRequestsError:
            wait_time = 30 + random.randint(0, 10)  # wait 30-40 sec before retry
            print(f"[Attempt {attempt+1}] Rate limited by Google. Waiting {wait_time} seconds...")
            time.sleep(wait_time)
    else:
        print("Failed to fetch trends data after multiple attempts.")
        return []

    if df.empty:
        print(f"No Google Trends data returned for '{keyword}'")
        return []

    records = []
    category = infer_keyword_category(keyword)
    for idx, row in df.iterrows():
        records.append(
            {
                "source": "google_trends",
                "category": "public_interest",
                "topic": keyword,
                "trend_category": category,
                "collected_at": collected_at,
                "data": {
                    "keyword": keyword,
                    "topic": keyword,
                    "category": category,
                    "date": idx.strftime("%Y-%m-%d %H:%M:%S"),
                    "interest": int(row[keyword]),
                },
            }
        )

    return records


def fetch_trends_multi(keywords=None, max_retries=3):
    """
    Fetch Google Trends records for multiple keywords and flatten the results.
    """
    if keywords is None:
        keywords = DEFAULT_TREND_KEYWORDS

    records = []
    records.extend(fetch_trending_search_queries())
    seen = set()
    for raw_keyword in keywords:
        keyword = str(raw_keyword or "").strip()
        if not keyword:
            continue
        keyword_key = keyword.lower()
        if keyword_key in seen:
            continue
        seen.add(keyword_key)
        records.extend(fetch_trends(keyword=keyword, max_retries=max_retries))
    return records


def convert_for_json(obj):
    """Recursively convert datetimes and MongoDB ObjectIds to strings"""
    from bson import ObjectId

    if isinstance(obj, dict):
        return {k: convert_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_for_json(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj


def collect_trends(keyword=None):
    """
    Fetch Google Trends data, send each record to Kafka, insert into MongoDB.
    """
    if keyword is None:
        data = fetch_trends_multi(DEFAULT_TREND_KEYWORDS)
    elif isinstance(keyword, (list, tuple, set)):
        data = fetch_trends_multi(list(keyword))
    else:
        data = fetch_trends(str(keyword))
    if not data:
        print("No data fetched from Google Trends.")
        return

    # Insert into MongoDB (warehouse)
    insert("trends", data)

    # Send each record to Kafka (make JSON-safe)
    for record in data:
        record_json_safe = convert_for_json(record)
        send_to_kafka("trends", record_json_safe)
        print(f"Sent to Kafka: {record['data']['keyword']} - {record['data']['date']}")

    print(f"Google Trends collector finished. {len(data)} records processed.")


if __name__ == "__main__":
    collect_trends(DEFAULT_TREND_KEYWORDS)







