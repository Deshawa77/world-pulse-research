from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SOURCE_TAXONOMY: dict[str, dict[str, str]] = {
    "gdelt": {
        "signal_domain": "news",
        "signal_type": "multilingual_news",
        "signal_class": "contextual",
        "source_tier": "aggregated",
        "geo_scope": "country",
    },
    "newsapi": {
        "signal_domain": "news",
        "signal_type": "publisher_news",
        "signal_class": "contextual",
        "source_tier": "aggregated",
        "geo_scope": "country",
    },
    "google_trends": {
        "signal_domain": "attention",
        "signal_type": "search_interest",
        "signal_class": "direct",
        "source_tier": "platform",
        "geo_scope": "country",
    },
    "wikipedia": {
        "signal_domain": "attention",
        "signal_type": "pageview_interest",
        "signal_class": "direct",
        "source_tier": "public_reference",
        "geo_scope": "country",
    },
    "reddit": {
        "signal_domain": "social",
        "signal_type": "public_discussion",
        "signal_class": "direct",
        "source_tier": "community",
        "geo_scope": "country",
    },
    "telegram_public": {
        "signal_domain": "social",
        "signal_type": "public_channel_posts",
        "signal_class": "direct",
        "source_tier": "community",
        "geo_scope": "country",
    },
    "youtube_public": {
        "signal_domain": "social",
        "signal_type": "video_feed_velocity",
        "signal_class": "direct",
        "source_tier": "platform",
        "geo_scope": "country",
    },
    "weather": {
        "signal_domain": "environment",
        "signal_type": "weather_observation",
        "signal_class": "contextual",
        "source_tier": "sensor",
        "geo_scope": "country",
    },
    "unhcr_idmc": {
        "signal_domain": "mobility",
        "signal_type": "internal_displacement",
        "signal_class": "direct",
        "source_tier": "public_institution",
        "geo_scope": "country",
    },
    "opensky": {
        "signal_domain": "mobility",
        "signal_type": "aviation_activity",
        "signal_class": "direct",
        "source_tier": "public_network",
        "geo_scope": "country",
    },
    "logistics": {
        "signal_domain": "mobility",
        "signal_type": "logistics_flow",
        "signal_class": "contextual",
        "source_tier": "public_institution",
        "geo_scope": "country",
    },
    "economic_behavior": {
        "signal_domain": "economic_behavior",
        "signal_type": "household_labor_pressure",
        "signal_class": "direct",
        "source_tier": "public_institution",
        "geo_scope": "country",
    },
    "worldbank_behavior": {
        "signal_domain": "economic_behavior",
        "signal_type": "macro_household_dependency",
        "signal_class": "contextual",
        "source_tier": "public_institution",
        "geo_scope": "country",
    },
    "energy_stress": {
        "signal_domain": "economic_behavior",
        "signal_type": "energy_price_stress",
        "signal_class": "contextual",
        "source_tier": "public_institution",
        "geo_scope": "global",
    },
    "stocks": {
        "signal_domain": "markets",
        "signal_type": "equity_market",
        "signal_class": "contextual",
        "source_tier": "market",
        "geo_scope": "country",
    },
    "crypto": {
        "signal_domain": "markets",
        "signal_type": "crypto_market",
        "signal_class": "contextual",
        "source_tier": "market",
        "geo_scope": "country",
    },
}


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except Exception:
        return datetime.now(timezone.utc).isoformat()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def signal_taxonomy_for_source(source: str, **overrides: Any) -> dict[str, Any]:
    base = dict(SOURCE_TAXONOMY.get(str(source or "").strip().lower(), {}))
    for key, value in overrides.items():
        if value is not None:
            base[key] = value
    return base


def build_signal_metadata(
    *,
    source: str,
    observed_at: Any = None,
    ingested_at: Any = None,
    language: str | None = None,
    confidence: float | None = None,
    coverage_weight: float | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    taxonomy = signal_taxonomy_for_source(source, **overrides)
    metadata = {
        "signal_domain": taxonomy.get("signal_domain", "unknown"),
        "signal_type": taxonomy.get("signal_type", "unknown"),
        "signal_class": taxonomy.get("signal_class", "contextual"),
        "source_tier": taxonomy.get("source_tier", "unknown"),
        "geo_scope": taxonomy.get("geo_scope", "country"),
        "source_name": str(source or "unknown").strip().lower() or "unknown",
        "language": str(language or taxonomy.get("language") or "und").strip().lower() or "und",
        "observed_at": _to_iso(observed_at),
        "ingested_at": _to_iso(ingested_at or datetime.now(timezone.utc)),
        "confidence": float(confidence) if confidence is not None else None,
        "coverage_weight": float(coverage_weight) if coverage_weight is not None else None,
    }
    return metadata
