from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from database.mongo import db


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if numeric == numeric else default


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    return "".join(char for char in text if char.isalnum() or char in {"-", "_", ":"}) or "unknown"


def _normalize_country(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if len(text) == 3 and text.isalpha() else None


def _normalize_alias(value: Any) -> str:
    text = str(value or "").strip().lower()
    cleaned = "".join(char if char.isalnum() else " " for char in text)
    return " ".join(cleaned.split())


def _string(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        rows = value
    elif isinstance(value, tuple):
        rows = list(value)
    elif isinstance(value, str):
        rows = [item.strip() for item in value.split(",")]
    else:
        rows = []
    return [str(item or "").strip() for item in rows if str(item or "").strip()]


def _doc_timestamp(doc: dict[str, Any]) -> str:
    for key in ("published_at", "timestamp", "created_at", "collected_at", "updated_at", "date"):
        raw = _string(doc.get(key))
        if raw:
            return raw
    return datetime.now(timezone.utc).isoformat()


def _doc_country(doc: dict[str, Any]) -> str | None:
    for key in ("country", "country_code", "data_country"):
        value = _normalize_country(doc.get(key))
        if value:
            return value
    for container_key in ("geo", "data", "metadata"):
        container = doc.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in ("country", "country_code"):
            value = _normalize_country(container.get(key))
            if value:
                return value
    return None


def _doc_title(doc: dict[str, Any]) -> str:
    for key in ("title", "headline", "name", "summary_title"):
        value = _string(doc.get(key))
        if value:
            return value
    return ""


def _doc_body(doc: dict[str, Any]) -> str:
    body_parts = [
        _string(doc.get("summary")),
        _string(doc.get("description")),
        _string(doc.get("body")),
        _string(doc.get("content")),
    ]
    for container_key in ("data", "metadata"):
        container = doc.get(container_key)
        if isinstance(container, dict):
            for key in ("summary", "description", "body", "content", "text"):
                body_parts.append(_string(container.get(key)))
    return " ".join(part for part in body_parts if part)


def _doc_source(doc: dict[str, Any]) -> str:
    for key in ("source_name", "source", "publisher", "outlet"):
        value = _string(doc.get(key))
        if value:
            return value
    return "news_feed"


def _doc_url(doc: dict[str, Any]) -> str | None:
    for key in ("url", "link", "source_url"):
        value = _string(doc.get(key))
        if value:
            return value
    return None


TOPIC_PATTERNS: dict[str, tuple[str, ...]] = {
    "conflict_escalation": ("conflict", "military", "strike", "shelling", "offensive", "ceasefire"),
    "civil_unrest": ("protest", "riot", "demonstration", "unrest", "march", "curfew"),
    "migration_pressure": ("migration", "displacement", "refugee", "evacuation", "border crossing"),
    "food_pressure": ("food price", "food shortage", "grain", "harvest", "bread"),
    "fuel_pressure": ("fuel", "oil", "diesel", "gasoline", "energy"),
    "internet_disruption": ("outage", "shutdown", "routing", "ddos", "internet", "telecom"),
    "logistics_disruption": ("port", "shipping", "supply chain", "cargo", "flight", "airport"),
    "flood_risk": ("flood", "overflow", "monsoon", "heavy rain"),
    "cyclone_risk": ("cyclone", "typhoon", "hurricane", "tropical storm"),
    "wildfire_risk": ("wildfire", "fire", "smoke"),
    "earthquake_risk": ("earthquake", "aftershock", "tremor", "quake"),
    "market_panic": ("currency", "inflation", "market selloff", "bank", "bond"),
}

ORG_KEYWORDS = (
    "ministry",
    "government",
    "agency",
    "bank",
    "telecom",
    "airlines",
    "airways",
    "airport",
    "port",
    "police",
    "army",
    "military",
    "council",
    "commission",
    "network",
    "authority",
    "company",
    "group",
    "union",
    "hospital",
    "operator",
)

ORG_STOPWORDS = {
    "breaking",
    "global",
    "international",
    "regional",
    "national",
    "local",
    "world",
    "update",
    "analysis",
    "news_feed",
}


def _topic_candidates(doc: dict[str, Any], blob: str) -> list[str]:
    topics = set()
    for key in ("topics", "tags", "keywords", "narratives"):
        for item in _string_list(doc.get(key)):
            topics.add(item.lower().replace(" ", "_"))
    lowered = blob.lower()
    for topic, patterns in TOPIC_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            topics.add(topic)
    return sorted(topics)


def _organization_candidates(doc: dict[str, Any], title: str, blob: str) -> list[str]:
    orgs: set[str] = set()
    for key in ("organizations", "orgs", "entities", "institutions"):
        value = doc.get(key)
        if isinstance(value, dict):
            for nested_key in ("organizations", "orgs"):
                orgs.update(_string_list(value.get(nested_key)))
        else:
            orgs.update(_string_list(value))

    source_name = _doc_source(doc)
    if source_name and len(source_name.split()) <= 6:
        orgs.add(source_name)

    for match in re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+(?:" + "|".join(ORG_KEYWORDS) + r"))\b", title):
        orgs.add(match.strip())
    for match in re.findall(r"\b[A-Z]{2,6}\b", title):
        if len(match) >= 3:
            orgs.add(match.strip())

    lowered = blob.lower()
    for keyword in ORG_KEYWORDS:
        if keyword not in lowered:
            continue
        pattern = re.compile(rf"\b([A-Z][A-Za-z&\-]+(?:\s+[A-Z][A-Za-z&\-]+){{0,3}}\s+{re.escape(keyword)})\b")
        for match in pattern.findall(title):
            orgs.add(match.strip())
    filtered: set[str] = set()
    for item in orgs:
        normalized = _normalize_alias(item)
        if len(item) < 3:
            continue
        if normalized in ORG_STOPWORDS:
            continue
        if normalized.isdigit():
            continue
        if len(normalized.split()) == 1 and normalized in {"news", "media", "press", "alert"}:
            continue
        filtered.add(item)
    return sorted(filtered)


def _infrastructure_candidates(blob: str) -> list[str]:
    matches = []
    lowered = blob.lower()
    for token in ("telecom network", "internet backbone", "airport", "port", "power grid", "pipeline", "data center"):
        if token in lowered:
            matches.append(token)
    return matches


def _event_risk_score(blob: str, topics: list[str]) -> float:
    lowered = blob.lower()
    severity = 0.22 + min(len(topics), 5) * 0.08
    if any(token in lowered for token in ("urgent", "breaking", "severe", "massive", "shutdown", "strike", "landfall")):
        severity += 0.14
    if any(token in lowered for token in ("earthquake", "wildfire", "flood", "cyclone", "hurricane", "riot", "attack", "ddos")):
        severity += 0.18
    return round(min(1.0, severity), 4)


def _recent_news_docs(*, country_scope: set[str] | None = None, limit: int = 120, lookback_days: int = 14) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(lookback_days)))
    projection = {
        "_id": 0,
        "id": 1,
        "country": 1,
        "country_code": 1,
        "title": 1,
        "headline": 1,
        "summary": 1,
        "description": 1,
        "body": 1,
        "content": 1,
        "topics": 1,
        "tags": 1,
        "keywords": 1,
        "organizations": 1,
        "orgs": 1,
        "source": 1,
        "source_name": 1,
        "publisher": 1,
        "outlet": 1,
        "url": 1,
        "link": 1,
        "timestamp": 1,
        "published_at": 1,
        "created_at": 1,
        "collected_at": 1,
        "data": 1,
        "metadata": 1,
    }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    per_collection_limit = max(limit * 2, 140)
    for collection_name in ("country_news", "news"):
        try:
            cursor = db[collection_name].find({}, projection).sort("_id", -1).limit(per_collection_limit)
        except Exception:
            continue
        for raw in cursor:
            if not isinstance(raw, dict):
                continue
            title = _doc_title(raw)
            if not title:
                continue
            stamp = _doc_timestamp(raw)
            try:
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                else:
                    parsed = parsed.astimezone(timezone.utc)
            except ValueError:
                parsed = None
            if parsed and parsed < cutoff:
                continue
            country = _doc_country(raw)
            if country_scope and country and country not in country_scope:
                continue
            key = f"{_normalize_alias(title)}|{country or 'global'}|{_normalize_alias(_doc_source(raw))}"
            if key in seen:
                continue
            seen.add(key)
            rows.append({**raw, "_collection": collection_name, "_country": country, "_timestamp": stamp, "_title": title})
            if len(rows) >= max(60, limit):
                break
        if len(rows) >= max(60, limit):
            break
    return rows[: max(1, int(limit))]


def build_text_graph_enrichment(
    *,
    country_snapshots: list[dict[str, Any]],
    alert_events: list[dict[str, Any]] | None = None,
    limit: int = 120,
    lookback_days: int = 14,
) -> dict[str, list[dict[str, Any]]]:
    country_scope = {
        _normalize_country(item.get("country"))
        for item in country_snapshots
        if isinstance(item, dict)
    }
    if alert_events:
        for alert in alert_events:
            if not isinstance(alert, dict):
                continue
            geography = alert.get("geography") if isinstance(alert.get("geography"), dict) else {}
            for key in ("country", "origin", "target"):
                country = _normalize_country(geography.get(key))
                if country:
                    country_scope.add(country)

    docs = _recent_news_docs(country_scope={item for item in country_scope if item}, limit=limit, lookback_days=lookback_days)
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []

    for doc in docs:
        title = _doc_title(doc)
        body = _doc_body(doc)
        blob = " ".join(part for part in (title, body) if part)
        if not blob:
            continue
        country = doc.get("_country")
        timestamp = doc.get("_timestamp") or datetime.now(timezone.utc).isoformat()
        source_name = _doc_source(doc)
        provenance = [
            {
                "source_family": "news",
                "source_name": source_name,
                "collection": doc.get("_collection"),
                "url": _doc_url(doc),
                "timestamp": timestamp,
                "document_id": _string(doc.get("id")) or _slug(title),
            }
        ]
        topics = _topic_candidates(doc, blob)
        organizations = _organization_candidates(doc, title, blob)
        infrastructures = _infrastructure_candidates(blob)
        event_risk = _event_risk_score(blob, topics)
        event_id = f"event:{_slug(country or 'global')}:{_slug(title)[:96]}"

        entities.append(
            {
                "entity_id": event_id,
                "entity_type": "named_event",
                "canonical_name": title[:140],
                "aliases": [title, _string(doc.get("headline"))],
                "geography": {"scope": "country" if country else "global", "country": country},
                "valid_from": timestamp,
                "valid_to": None,
                "confidence_ratio": round(min(0.94, 0.46 + (event_risk * 0.42)), 4),
                "provenance_refs": provenance,
                "last_updated_at": timestamp,
                "current_risk_score": round(event_risk * 100.0, 2),
            }
        )
        if country:
            relationships.append(
                {
                    "relationship_id": f"news_event_country:{_slug(event_id)}:{country}",
                    "relationship_type": "event_impacts_country",
                    "source_entity_id": event_id,
                    "target_entity_id": f"country:{country}",
                    "timestamp": timestamp,
                    "geography": {"scope": "country", "country": country},
                    "strength_score": event_risk,
                    "confidence_ratio": round(min(0.92, 0.44 + (event_risk * 0.4)), 4),
                    "provenance_refs": provenance,
                    "supporting_evidence_refs": [{"title": title, "url": _doc_url(doc)}],
                }
            )

        for organization in organizations[:6]:
            org_id = f"organization:{_slug(organization)}"
            entities.append(
                {
                    "entity_id": org_id,
                    "entity_type": "organization",
                    "canonical_name": organization,
                    "aliases": [organization, source_name if organization != source_name else ""],
                    "geography": {"scope": "country" if country else "global", "country": country},
                    "valid_from": None,
                    "valid_to": None,
                    "confidence_ratio": round(min(0.9, 0.4 + (event_risk * 0.36)), 4),
                    "provenance_refs": provenance,
                    "last_updated_at": timestamp,
                    "current_risk_score": round(min(100.0, 42.0 + (event_risk * 42.0)), 2),
                }
            )
            relationships.append(
                {
                    "relationship_id": f"news_org_event:{_slug(organization)}:{_slug(event_id)}",
                    "relationship_type": "organization_involved_in_event",
                    "source_entity_id": org_id,
                    "target_entity_id": event_id,
                    "timestamp": timestamp,
                    "geography": {"scope": "country" if country else "global", "country": country},
                    "strength_score": round(min(1.0, 0.45 + event_risk * 0.35), 4),
                    "confidence_ratio": round(min(0.9, 0.42 + (event_risk * 0.34)), 4),
                    "provenance_refs": provenance,
                    "supporting_evidence_refs": [{"organization": organization, "title": title}],
                }
            )
            if country:
                relationships.append(
                    {
                        "relationship_id": f"news_org_country:{_slug(organization)}:{country}",
                        "relationship_type": "organization_operates_in_country",
                        "source_entity_id": org_id,
                        "target_entity_id": f"country:{country}",
                        "timestamp": timestamp,
                        "geography": {"scope": "country", "country": country},
                        "strength_score": round(min(1.0, 0.38 + event_risk * 0.28), 4),
                        "confidence_ratio": round(min(0.88, 0.4 + (event_risk * 0.28)), 4),
                        "provenance_refs": provenance,
                        "supporting_evidence_refs": [{"organization": organization, "title": title}],
                    }
                )

        for topic in topics[:6]:
            topic_id = f"topic:{_slug(topic)}"
            entities.append(
                {
                    "entity_id": topic_id,
                    "entity_type": "narrative_topic",
                    "canonical_name": topic.replace("_", " ").title(),
                    "aliases": [topic, topic.replace("_", " ")],
                    "geography": {"scope": "country" if country else "global", "country": country},
                    "valid_from": None,
                    "valid_to": None,
                    "confidence_ratio": round(min(0.9, 0.44 + (event_risk * 0.34)), 4),
                    "provenance_refs": provenance,
                    "last_updated_at": timestamp,
                    "current_risk_score": round(min(100.0, 30.0 + (event_risk * 38.0)), 2),
                }
            )
            relationships.append(
                {
                    "relationship_id": f"news_event_topic:{_slug(event_id)}:{_slug(topic)}",
                    "relationship_type": "event_amplifies_topic",
                    "source_entity_id": event_id,
                    "target_entity_id": topic_id,
                    "timestamp": timestamp,
                    "geography": {"scope": "country" if country else "global", "country": country},
                    "strength_score": round(min(1.0, 0.4 + event_risk * 0.4), 4),
                    "confidence_ratio": round(min(0.9, 0.42 + (event_risk * 0.34)), 4),
                    "provenance_refs": provenance,
                    "supporting_evidence_refs": [{"topic": topic, "title": title}],
                }
            )
            if country:
                relationships.append(
                    {
                        "relationship_id": f"news_topic_country:{_slug(topic)}:{country}",
                        "relationship_type": "topic_pressures_country",
                        "source_entity_id": topic_id,
                        "target_entity_id": f"country:{country}",
                        "timestamp": timestamp,
                        "geography": {"scope": "country", "country": country},
                        "strength_score": round(min(1.0, 0.34 + event_risk * 0.36), 4),
                        "confidence_ratio": round(min(0.88, 0.4 + (event_risk * 0.26)), 4),
                        "provenance_refs": provenance,
                        "supporting_evidence_refs": [{"topic": topic, "title": title}],
                    }
                )

        for infrastructure in infrastructures[:4]:
            infra_id = f"infrastructure:{_slug(infrastructure)}"
            entities.append(
                {
                    "entity_id": infra_id,
                    "entity_type": "infrastructure",
                    "canonical_name": infrastructure.title(),
                    "aliases": [infrastructure],
                    "geography": {"scope": "country" if country else "global", "country": country},
                    "valid_from": None,
                    "valid_to": None,
                    "confidence_ratio": round(min(0.86, 0.38 + (event_risk * 0.26)), 4),
                    "provenance_refs": provenance,
                    "last_updated_at": timestamp,
                    "current_risk_score": round(min(100.0, 28.0 + (event_risk * 32.0)), 2),
                }
            )
            relationships.append(
                {
                    "relationship_id": f"news_event_infrastructure:{_slug(event_id)}:{_slug(infrastructure)}",
                    "relationship_type": "event_impacts_infrastructure",
                    "source_entity_id": event_id,
                    "target_entity_id": infra_id,
                    "timestamp": timestamp,
                    "geography": {"scope": "country" if country else "global", "country": country},
                    "strength_score": round(min(1.0, 0.32 + event_risk * 0.36), 4),
                    "confidence_ratio": round(min(0.84, 0.36 + (event_risk * 0.24)), 4),
                    "provenance_refs": provenance,
                    "supporting_evidence_refs": [{"infrastructure": infrastructure, "title": title}],
                }
            )

    return {
        "world_entities": entities[: max(1, int(limit * 3))],
        "world_relationships": relationships[: max(1, int(limit * 5))],
    }
