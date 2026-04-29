from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from processing.planetary_graph import canonicalize_world_entities, canonicalize_world_relationships, resolve_planetary_entity


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if numeric == numeric else default


def _entity_country_scope(entity: dict[str, Any]) -> list[str]:
    geography = entity.get("geography") if isinstance(entity.get("geography"), dict) else {}
    countries: list[str] = []
    for key in ("country", "origin", "target", "from_country", "to_country"):
        value = str(geography.get(key) or "").strip().upper()
        if value and value not in countries:
            countries.append(value)
    entity_id = str(entity.get("entity_id") or "").strip()
    if entity_id.startswith("country:"):
        country = entity_id.split(":", 1)[1].strip().upper()
        if country and country not in countries:
            countries.append(country)
    return countries


def build_planetary_graph_summary(
    *,
    world_entities: list[dict[str, Any]],
    world_relationships: list[dict[str, Any]],
    limit: int = 12,
) -> dict[str, Any]:
    canonical_entities, alias_map = canonicalize_world_entities(world_entities)
    canonical_relationships = canonicalize_world_relationships(world_relationships, alias_map)
    entity_index = {
        str(item.get("entity_id") or "").strip(): item
        for item in canonical_entities
        if str(item.get("entity_id") or "").strip()
    }

    entity_type_counts = Counter(str(item.get("entity_type") or "unknown").strip() or "unknown" for item in canonical_entities)
    relationship_type_counts = Counter(str(item.get("relationship_type") or "unknown").strip() or "unknown" for item in canonical_relationships)

    degree_counter: Counter[str] = Counter()
    related_type_counts: dict[str, Counter[str]] = defaultdict(Counter)
    country_hotspots: Counter[str] = Counter()
    for relation in canonical_relationships:
        source_id = str(relation.get("source_entity_id") or "").strip()
        target_id = str(relation.get("target_entity_id") or "").strip()
        relation_type = str(relation.get("relationship_type") or "unknown").strip() or "unknown"
        if source_id:
            degree_counter[source_id] += 1
            related_type_counts[source_id][relation_type] += 1
        if target_id:
            degree_counter[target_id] += 1
            related_type_counts[target_id][relation_type] += 1

    for entity in canonical_entities:
        for country in _entity_country_scope(entity):
            country_hotspots[country] += 1

    top_entities: list[dict[str, Any]] = []
    for entity_id, degree in degree_counter.most_common(max(1, int(limit))):
        entity = entity_index.get(entity_id)
        if not entity:
            continue
        top_entities.append(
            {
                "entity_id": entity_id,
                "canonical_name": entity.get("canonical_name"),
                "entity_type": entity.get("entity_type"),
                "confidence_ratio": entity.get("confidence_ratio"),
                "current_risk_score": entity.get("current_risk_score"),
                "relationship_degree": degree,
                "top_relationship_types": dict(related_type_counts[entity_id].most_common(4)),
                "country_scope": _entity_country_scope(entity),
            }
        )

    query_spots = [
        item
        for item in canonical_entities
        if str(item.get("entity_type") or "").strip().lower() in {"named_event", "organization", "narrative_topic", "infrastructure"}
    ]
    query_spots.sort(
        key=lambda item: (
            degree_counter.get(str(item.get("entity_id") or "").strip(), 0),
            _safe_float(item.get("current_risk_score"), 0.0),
            _safe_float(item.get("confidence_ratio"), 0.0),
        ),
        reverse=True,
    )

    return {
        "contract_version": "phase-0.6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entity_count": len(canonical_entities),
        "relationship_count": len(canonical_relationships),
        "entity_type_counts": dict(entity_type_counts),
        "relationship_type_counts": dict(relationship_type_counts),
        "top_entities": top_entities,
        "country_hotspots": dict(country_hotspots.most_common(10)),
        "query_spots": query_spots[: max(1, int(limit))],
    }


def search_planetary_graph_entities(
    query: str,
    *,
    world_entities: list[dict[str, Any]],
    world_relationships: list[dict[str, Any]],
    entity_type: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    canonical_entities, alias_map = canonicalize_world_entities(world_entities)
    canonical_relationships = canonicalize_world_relationships(world_relationships, alias_map)

    resolved = resolve_planetary_entity(query, world_entities=canonical_entities, entity_type=entity_type)
    query_text = str(query or "").strip().lower()
    matches: list[dict[str, Any]] = []
    for entity in canonical_entities:
        if entity_type and str(entity.get("entity_type") or "").strip().lower() != str(entity_type).strip().lower():
            continue
        haystack = " ".join(
            [
                str(entity.get("entity_id") or ""),
                str(entity.get("canonical_name") or ""),
                " ".join(str(alias or "") for alias in (entity.get("aliases") or [])),
                " ".join(_entity_country_scope(entity)),
            ]
        ).lower()
        if query_text and query_text not in haystack:
            continue
        entity_id = str(entity.get("entity_id") or "").strip()
        relationship_degree = sum(
            1
            for row in canonical_relationships
            if entity_id in {str(row.get("source_entity_id") or "").strip(), str(row.get("target_entity_id") or "").strip()}
        )
        matches.append(
            {
                "entity_id": entity_id,
                "canonical_name": entity.get("canonical_name"),
                "entity_type": entity.get("entity_type"),
                "aliases": entity.get("aliases") or [],
                "country_scope": _entity_country_scope(entity),
                "confidence_ratio": entity.get("confidence_ratio"),
                "current_risk_score": entity.get("current_risk_score"),
                "relationship_degree": relationship_degree,
            }
        )

    matches.sort(
        key=lambda item: (
            1 if resolved and str(resolved["entity"].get("entity_id") or "") == str(item.get("entity_id") or "") else 0,
            int(item.get("relationship_degree") or 0),
            _safe_float(item.get("current_risk_score"), 0.0),
            _safe_float(item.get("confidence_ratio"), 0.0),
        ),
        reverse=True,
    )

    return {
        "contract_version": "phase-0.6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "matched_alias": resolved.get("matched_alias") if resolved else None,
        "resolved_entity": resolved.get("entity") if resolved else None,
        "count": len(matches[: max(1, int(limit))]),
        "results": matches[: max(1, int(limit))],
    }
