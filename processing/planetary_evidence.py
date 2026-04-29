from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from processing.planetary_graph import build_planetary_entity_profile


ALERT_SCOPE = "planetary_intelligence"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if numeric == numeric else default


def _ratio(value: Any, default: float = 0.0) -> float:
    numeric = _safe_float(value, default)
    if numeric > 1.0:
        numeric = numeric / 100.0 if numeric <= 100.0 else default
    return max(0.0, min(1.0, numeric))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    return "".join(char for char in text if char.isalnum() or char in {"-", "_", ":"}) or "unknown"


def _merge_refs(*groups: list[Any]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group or []:
            if not isinstance(item, dict):
                continue
            marker = str(sorted(item.items()))
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(dict(item))
    return merged


def _country_aliases(country: str) -> set[str]:
    code = str(country or "").strip().upper()
    return {code, f"country:{code}"} if code else set()


def _alert_countries(alert: dict[str, Any]) -> set[str]:
    geography = alert.get("geography") if isinstance(alert.get("geography"), dict) else {}
    countries = {
        str(geography.get(key) or "").strip().upper()
        for key in ("country", "origin", "target", "from_country", "to_country")
    }
    countries |= {
        str(item or "").strip().upper()
        for item in (alert.get("related_entities_or_regions") or [])
        if len(str(item or "").strip()) == 3
    }
    return {item for item in countries if item}


def _row_countries(row: dict[str, Any]) -> set[str]:
    geography = row.get("geography") if isinstance(row.get("geography"), dict) else {}
    countries = {
        str(geography.get(key) or "").strip().upper()
        for key in ("country", "origin", "destination", "from_country", "to_country", "target")
    }
    return {item for item in countries if item}


def _corridor_countries(corridor: dict[str, Any]) -> set[str]:
    return {
        str((corridor.get(region_key) or {}).get("country") or "").strip().upper()
        for region_key in ("from_region", "to_region")
        if isinstance(corridor.get(region_key), dict)
    } - {""}


def _signal_matches_country(row: dict[str, Any], country: str) -> bool:
    aliases = _country_aliases(country)
    entity_refs = {str(item or "").strip().upper() for item in (row.get("entity_refs") or [])}
    return bool(_row_countries(row) & aliases) or bool(entity_refs & aliases)


def _source_event_matches_country(row: dict[str, Any], country: str) -> bool:
    return bool(_row_countries(row) & _country_aliases(country))


def _timeline_matches_country(row: dict[str, Any], country: str, alert_ids: set[str], chain_ids: set[str], snapshot_refs: set[str]) -> bool:
    row_country = str(row.get("country") or "").strip().upper()
    if row_country and country in row_country:
        return True
    if alert_ids & {str(item or "").strip() for item in (row.get("alert_refs") or [])}:
        return True
    if chain_ids & {str(item or "").strip() for item in (row.get("chain_refs") or [])}:
        return True
    if snapshot_refs & {str(item or "").strip() for item in (row.get("snapshot_refs") or [])}:
        return True
    return False


def load_planetary_operator_history(
    operator_events_collection,
    *,
    country: str | None = None,
    chain_id: str | None = None,
    alert_ids: list[str] | None = None,
    dedupe_keys: list[str] | None = None,
    limit: int = 24,
    hours: int = 336,
) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))).isoformat()
    docs = list(
        operator_events_collection.find(
            {"alert_scope": ALERT_SCOPE, "timestamp": {"$gte": cutoff}},
            {"_id": 0},
        ).sort("timestamp", -1)
    )
    country_filter = str(country or "").strip().upper()
    alert_id_set = {str(item or "").strip() for item in (alert_ids or []) if str(item or "").strip()}
    dedupe_key_set = {str(item or "").strip() for item in (dedupe_keys or []) if str(item or "").strip()}
    chain_filter = str(chain_id or "").strip()
    filtered: list[dict[str, Any]] = []
    for doc in docs:
        doc_country = str(doc.get("country") or "").strip().upper()
        doc_alert_id = str(doc.get("alert_id") or "").strip()
        doc_dedupe_key = str(doc.get("dedupe_key") or "").strip()
        doc_chain_id = str(doc.get("chain_id") or "").strip()
        if country_filter and doc_country and doc_country != country_filter and doc_country not in {"GLOBAL", "GLB", "WORLD"}:
            if not (alert_id_set and doc_alert_id in alert_id_set):
                continue
        if chain_filter and doc_chain_id and doc_chain_id != chain_filter:
            continue
        if alert_id_set or dedupe_key_set:
            if doc_alert_id not in alert_id_set and doc_dedupe_key not in dedupe_key_set:
                if not (country_filter and doc_country == country_filter):
                    continue
        filtered.append(dict(doc))
        if len(filtered) >= max(1, int(limit)):
            break
    return filtered


def _evidence_summary(
    *,
    confidence_ratio: float,
    freshness_sec: int,
    subsystem_scores: dict[str, Any] | None,
    state_vector: dict[str, Any] | None,
    provenance_refs: list[dict[str, Any]],
    supporting_signals: list[dict[str, Any]],
    supporting_source_events: list[dict[str, Any]],
    supporting_alerts: list[dict[str, Any]],
    related_entities: list[dict[str, Any]],
    related_relationships: list[dict[str, Any]],
    supporting_timeline: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "confidence_ratio": round(_ratio(confidence_ratio, 0.0), 4),
        "freshness_sec": max(0, int(freshness_sec)),
        "subsystem_scores": dict(subsystem_scores or {}),
        "state_vector": dict(state_vector or {}),
        "provenance_count": len(provenance_refs),
        "signal_count": len(supporting_signals),
        "source_event_count": len(supporting_source_events),
        "alert_count": len(supporting_alerts),
        "entity_count": len(related_entities),
        "relationship_count": len(related_relationships),
        "timeline_count": len(supporting_timeline),
    }


def build_country_fusion_detail(
    country: str,
    *,
    country_snapshots: list[dict[str, Any]],
    country_fusion_snapshots: list[dict[str, Any]],
    correlation_chains: list[dict[str, Any]],
    fusion_timeline: list[dict[str, Any]],
    corridor_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
    world_entities: list[dict[str, Any]],
    world_relationships: list[dict[str, Any]],
    normalized_signals: list[dict[str, Any]],
    source_events: list[dict[str, Any]],
    operator_events_collection=None,
) -> dict[str, Any] | None:
    country_code = str(country or "").strip().upper()
    if not country_code:
        return None
    fusion_snapshot = next((item for item in country_fusion_snapshots if str(item.get("country") or "").strip().upper() == country_code), None)
    if not fusion_snapshot:
        return None
    country_snapshot = next((item for item in country_snapshots if str(item.get("country") or "").strip().upper() == country_code), None)
    chains = [item for item in correlation_chains if str(item.get("country") or "").strip().upper() == country_code][:8]
    alerts = [item for item in alert_events if country_code in _alert_countries(item)][:12]
    hazards = [item for item in hazard_forecasts if str(item.get("country") or "").strip().upper() == country_code][:10]
    corridors = [
        item
        for item in corridor_snapshots
        if country_code in {
            str((item.get("from_region") or {}).get("country") or "").strip().upper(),
            str((item.get("to_region") or {}).get("country") or "").strip().upper(),
        }
    ][:10]
    signals = [item for item in normalized_signals if _signal_matches_country(item, country_code)][:16]
    events = [item for item in source_events if _source_event_matches_country(item, country_code)][:16]
    profile = build_planetary_entity_profile(
        f"country:{country_code}",
        world_entities=world_entities,
        world_relationships=world_relationships,
        country_fusion_snapshots=country_fusion_snapshots,
        correlation_chains=correlation_chains,
        alert_events=alert_events,
        hazard_forecasts=hazard_forecasts,
        corridor_snapshots=corridor_snapshots,
        fusion_timeline=fusion_timeline,
        operator_history=[],
        limit=12,
    ) or {}
    alert_ids = {str(item.get("alert_id") or "").strip() for item in alerts if str(item.get("alert_id") or "").strip()}
    chain_ids = {str(item.get("chain_id") or "").strip() for item in chains if str(item.get("chain_id") or "").strip()}
    snapshot_refs = {str(fusion_snapshot.get("fusion_id") or "").strip(), *chain_ids}
    timeline = [
        item
        for item in fusion_timeline
        if _timeline_matches_country(item, country_code, alert_ids, chain_ids, snapshot_refs)
    ][:12]
    operator_history = load_planetary_operator_history(
        operator_events_collection,
        country=country_code,
        alert_ids=list(alert_ids),
        dedupe_keys=[str(item.get("dedupe_key") or "").strip() for item in alerts if str(item.get("dedupe_key") or "").strip()],
        limit=18,
    ) if operator_events_collection is not None else []
    provenance_refs = _merge_refs(
        list(fusion_snapshot.get("provenance_refs") or []),
        *[list(item.get("provenance_refs") or []) for item in [*alerts, *hazards, *signals, *(profile.get("neighborhood_entities") or [])]],
    )
    return {
        "contract_version": "phase-0.4",
        "generated_at": _iso_now(),
        "country": country_code,
        "fusion_snapshot": fusion_snapshot,
        "country_snapshot": country_snapshot,
        "related_correlation_chains": chains,
        "supporting_alerts": alerts,
        "supporting_hazard_forecasts": hazards,
        "supporting_corridors": corridors,
        "supporting_signals": signals,
        "supporting_source_events": events,
        "related_entities": profile.get("neighborhood_entities") or ([profile.get("entity")] if profile.get("entity") else []),
        "related_relationships": profile.get("neighborhood_relationships") or [],
        "supporting_timeline": timeline,
        "operator_history": operator_history,
        "provenance_refs": provenance_refs,
        "evidence_summary": _evidence_summary(
            confidence_ratio=_safe_float(fusion_snapshot.get("confidence_ratio"), 0.0),
            freshness_sec=_safe_int(fusion_snapshot.get("freshness_sec"), 0),
            subsystem_scores=fusion_snapshot.get("subsystem_scores") if isinstance(fusion_snapshot.get("subsystem_scores"), dict) else {},
            state_vector=fusion_snapshot.get("state_vector") if isinstance(fusion_snapshot.get("state_vector"), dict) else {},
            provenance_refs=provenance_refs,
            supporting_signals=signals,
            supporting_source_events=events,
            supporting_alerts=alerts,
            related_entities=profile.get("neighborhood_entities") or [],
            related_relationships=profile.get("neighborhood_relationships") or [],
            supporting_timeline=timeline,
        ),
    }


def build_corridor_detail(
    corridor_id: str,
    *,
    country_snapshots: list[dict[str, Any]],
    country_fusion_snapshots: list[dict[str, Any]],
    correlation_chains: list[dict[str, Any]],
    fusion_timeline: list[dict[str, Any]],
    corridor_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
    world_entities: list[dict[str, Any]],
    world_relationships: list[dict[str, Any]],
    normalized_signals: list[dict[str, Any]],
    source_events: list[dict[str, Any]],
    operator_events_collection=None,
) -> dict[str, Any] | None:
    normalized_corridor_id = str(corridor_id or "").strip()
    corridor = next((item for item in corridor_snapshots if str(item.get("corridor_id") or "").strip() == normalized_corridor_id), None)
    if not corridor:
        return None
    countries = sorted(_corridor_countries(corridor))
    chains = [
        item for item in correlation_chains
        if str(item.get("country") or "").strip().upper() in countries
    ][:10]
    alerts = [
        item for item in alert_events
        if _alert_countries(item) & set(countries)
    ][:14]
    hazards = [
        item for item in hazard_forecasts
        if str(item.get("country") or "").strip().upper() in countries
    ][:10]
    signals = [
        item for item in normalized_signals
        if any(_signal_matches_country(item, country) for country in countries)
    ][:18]
    events = [
        item for item in source_events
        if any(_source_event_matches_country(item, country) for country in countries)
    ][:18]
    related_country_fusion = [
        item for item in country_fusion_snapshots
        if str(item.get("country") or "").strip().upper() in countries
    ][:8]
    country_snapshots_for_corridor = [
        item for item in country_snapshots
        if str(item.get("country") or "").strip().upper() in countries
    ][:8]
    timeline_alert_ids = {str(item.get("alert_id") or "").strip() for item in alerts if str(item.get("alert_id") or "").strip()}
    timeline_chain_ids = {str(item.get("chain_id") or "").strip() for item in chains if str(item.get("chain_id") or "").strip()}
    snapshot_refs = {
        normalized_corridor_id,
        *[str(item.get("fusion_id") or "").strip() for item in related_country_fusion if str(item.get("fusion_id") or "").strip()],
    }
    timeline = [
        item
        for item in fusion_timeline
        if (
            str(item.get("country") or "").strip().upper() in countries
            or timeline_alert_ids & {str(ref or "").strip() for ref in (item.get("alert_refs") or [])}
            or timeline_chain_ids & {str(ref or "").strip() for ref in (item.get("chain_refs") or [])}
            or snapshot_refs & {str(ref or "").strip() for ref in (item.get("snapshot_refs") or [])}
        )
    ][:12]
    related_entity_map: dict[str, dict[str, Any]] = {}
    related_relationship_map: dict[str, dict[str, Any]] = {}
    operator_history: list[dict[str, Any]] = []
    if operator_events_collection is not None:
        for country in countries:
            operator_history.extend(
                load_planetary_operator_history(
                    operator_events_collection,
                    country=country,
                    alert_ids=list(timeline_alert_ids),
                    dedupe_keys=[str(item.get("dedupe_key") or "").strip() for item in alerts if str(item.get("dedupe_key") or "").strip()],
                    limit=8,
                )
            )
    for country in countries:
        profile = build_planetary_entity_profile(
            f"country:{country}",
            world_entities=world_entities,
            world_relationships=world_relationships,
            country_fusion_snapshots=country_fusion_snapshots,
            correlation_chains=correlation_chains,
            alert_events=alert_events,
            hazard_forecasts=hazard_forecasts,
            corridor_snapshots=corridor_snapshots,
            fusion_timeline=fusion_timeline,
            operator_history=[],
            limit=10,
        ) or {}
        entity = profile.get("entity")
        if isinstance(entity, dict) and str(entity.get("entity_id") or "").strip():
            related_entity_map[str(entity.get("entity_id") or "").strip()] = dict(entity)
        for item in (profile.get("neighborhood_entities") or []):
            if isinstance(item, dict) and str(item.get("entity_id") or "").strip():
                related_entity_map[str(item.get("entity_id") or "").strip()] = dict(item)
        for item in (profile.get("neighborhood_relationships") or []):
            if isinstance(item, dict) and str(item.get("relationship_id") or "").strip():
                related_relationship_map[str(item.get("relationship_id") or "").strip()] = dict(item)
    related_entities = list(related_entity_map.values())[:18]
    related_relationships = list(related_relationship_map.values())[:18]
    operator_history = list({
        f"{str(item.get('timestamp') or '')}|{str(item.get('action') or '')}|{str(item.get('alert_id') or '')}|{str(item.get('country') or '')}": dict(item)
        for item in operator_history
        if isinstance(item, dict)
    }.values())[:18]
    corridor_provenance = corridor.get("provenance_summary")
    provenance_refs = _merge_refs(
        list(corridor_provenance) if isinstance(corridor_provenance, list) else ([dict(corridor_provenance)] if isinstance(corridor_provenance, dict) else []),
        *[list(item.get("provenance_refs") or []) for item in [*alerts, *hazards, *signals, *related_entities]],
    )
    subsystem_scores = {
        "throughput": _safe_float((corridor.get("flow_metrics") or {}).get("throughput_gbps"), 0.0),
        "latency": _safe_float((corridor.get("flow_metrics") or {}).get("latency_ms"), 0.0),
        "packet_loss": _safe_float((corridor.get("flow_metrics") or {}).get("packet_loss_pct"), 0.0),
        "anomaly": _safe_float((corridor.get("flow_metrics") or {}).get("anomaly_score"), 0.0),
        "attack": _safe_float((corridor.get("flow_metrics") or {}).get("attack_index"), 0.0),
    }
    return {
        "contract_version": "phase-0.4",
        "generated_at": _iso_now(),
        "corridor_id": normalized_corridor_id,
        "corridor_snapshot": corridor,
        "country_scope": countries,
        "related_country_snapshots": country_snapshots_for_corridor,
        "related_country_fusion_snapshots": related_country_fusion,
        "related_correlation_chains": chains,
        "supporting_alerts": alerts,
        "supporting_hazard_forecasts": hazards,
        "supporting_corridors": [corridor],
        "supporting_signals": signals,
        "supporting_source_events": events,
        "related_entities": related_entities,
        "related_relationships": related_relationships,
        "supporting_timeline": timeline,
        "operator_history": operator_history,
        "provenance_refs": provenance_refs,
        "evidence_summary": _evidence_summary(
            confidence_ratio=_safe_float(corridor.get("confidence_ratio"), 0.0),
            freshness_sec=_safe_int(corridor.get("freshness_sec"), 0),
            subsystem_scores=subsystem_scores,
            state_vector={
                "severity": _safe_float(corridor.get("severity_score"), 0.0),
                "traffic_share": _safe_float((corridor.get("flow_metrics") or {}).get("traffic_share"), 0.0),
                "reroute_factor": _safe_float((corridor.get("flow_metrics") or {}).get("reroute_factor"), 0.0),
            },
            provenance_refs=provenance_refs,
            supporting_signals=signals,
            supporting_source_events=events,
            supporting_alerts=alerts,
            related_entities=related_entities,
            related_relationships=related_relationships,
            supporting_timeline=timeline,
        ),
    }


def build_correlation_chain_detail(
    chain_id: str,
    *,
    country_snapshots: list[dict[str, Any]],
    country_fusion_snapshots: list[dict[str, Any]],
    correlation_chains: list[dict[str, Any]],
    fusion_timeline: list[dict[str, Any]],
    corridor_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
    world_entities: list[dict[str, Any]],
    world_relationships: list[dict[str, Any]],
    normalized_signals: list[dict[str, Any]],
    source_events: list[dict[str, Any]],
    operator_events_collection=None,
) -> dict[str, Any] | None:
    chain = next((item for item in correlation_chains if str(item.get("chain_id") or "").strip() == str(chain_id or "").strip()), None)
    if not chain:
        return None
    country_code = str(chain.get("country") or "").strip().upper()
    country_detail = build_country_fusion_detail(
        country_code,
        country_snapshots=country_snapshots,
        country_fusion_snapshots=country_fusion_snapshots,
        correlation_chains=correlation_chains,
        fusion_timeline=fusion_timeline,
        corridor_snapshots=corridor_snapshots,
        hazard_forecasts=hazard_forecasts,
        alert_events=alert_events,
        world_entities=world_entities,
        world_relationships=world_relationships,
        normalized_signals=normalized_signals,
        source_events=source_events,
        operator_events_collection=operator_events_collection,
    ) or {}
    alert_refs = {str(item or "").strip() for item in (chain.get("alert_refs") or []) if str(item or "").strip()}
    chain_alerts = [item for item in (country_detail.get("supporting_alerts") or []) if str(item.get("alert_id") or "").strip() in alert_refs]
    entity_refs = {str(item or "").strip() for item in (chain.get("entity_refs") or []) if str(item or "").strip()}
    chain_entities = [item for item in (country_detail.get("related_entities") or []) if str(item.get("entity_id") or "").strip() in entity_refs]
    timeline = [item for item in (country_detail.get("supporting_timeline") or []) if str(chain_id) in {str(ref or "").strip() for ref in (item.get("chain_refs") or [])}][:10]
    operator_history = load_planetary_operator_history(
        operator_events_collection,
        country=country_code,
        chain_id=str(chain_id),
        alert_ids=list(alert_refs),
        limit=16,
    ) if operator_events_collection is not None else []
    provenance_refs = _merge_refs(
        list(chain.get("provenance_refs") or []),
        *[list(item.get("provenance_refs") or []) for item in chain_alerts],
    )
    return {
        "contract_version": "phase-0.4",
        "generated_at": _iso_now(),
        "chain_id": str(chain_id),
        "correlation_chain": chain,
        "related_country_fusion": country_detail.get("fusion_snapshot"),
        "supporting_alerts": chain_alerts,
        "supporting_signals": country_detail.get("supporting_signals") or [],
        "supporting_source_events": country_detail.get("supporting_source_events") or [],
        "supporting_hazard_forecasts": country_detail.get("supporting_hazard_forecasts") or [],
        "supporting_corridors": country_detail.get("supporting_corridors") or [],
        "related_entities": chain_entities,
        "related_relationships": [
            item for item in (country_detail.get("related_relationships") or [])
            if str(item.get("source_entity_id") or "").strip() in entity_refs or str(item.get("target_entity_id") or "").strip() in entity_refs
        ],
        "supporting_timeline": timeline,
        "operator_history": operator_history,
        "provenance_refs": provenance_refs,
        "evidence_summary": _evidence_summary(
            confidence_ratio=_safe_float(chain.get("confidence_ratio"), 0.0),
            freshness_sec=_safe_int(chain.get("freshness_sec"), 0),
            subsystem_scores={stage.get("stage") or stage.get("metric") or f"stage_{index}": stage.get("value") for index, stage in enumerate(chain.get("stages") or []) if isinstance(stage, dict)},
            state_vector=None,
            provenance_refs=provenance_refs,
            supporting_signals=country_detail.get("supporting_signals") or [],
            supporting_source_events=country_detail.get("supporting_source_events") or [],
            supporting_alerts=chain_alerts,
            related_entities=chain_entities,
            related_relationships=[
                item for item in (country_detail.get("related_relationships") or [])
                if str(item.get("source_entity_id") or "").strip() in entity_refs or str(item.get("target_entity_id") or "").strip() in entity_refs
            ],
            supporting_timeline=timeline,
        ),
    }


def build_alert_detail(
    alert_id: str,
    *,
    country_snapshots: list[dict[str, Any]],
    country_fusion_snapshots: list[dict[str, Any]],
    correlation_chains: list[dict[str, Any]],
    fusion_timeline: list[dict[str, Any]],
    corridor_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
    world_entities: list[dict[str, Any]],
    world_relationships: list[dict[str, Any]],
    normalized_signals: list[dict[str, Any]],
    source_events: list[dict[str, Any]],
    operator_events_collection=None,
) -> dict[str, Any] | None:
    alert = next((item for item in alert_events if str(item.get("alert_id") or "").strip() == str(alert_id or "").strip()), None)
    if not alert:
        return None
    countries = list(_alert_countries(alert))
    primary_country = countries[0] if countries else ""
    country_detail = build_country_fusion_detail(
        primary_country,
        country_snapshots=country_snapshots,
        country_fusion_snapshots=country_fusion_snapshots,
        correlation_chains=correlation_chains,
        fusion_timeline=fusion_timeline,
        corridor_snapshots=corridor_snapshots,
        hazard_forecasts=hazard_forecasts,
        alert_events=alert_events,
        world_entities=world_entities,
        world_relationships=world_relationships,
        normalized_signals=normalized_signals,
        source_events=source_events,
        operator_events_collection=operator_events_collection,
    ) if primary_country else {}
    event_entity_id = f"event:{_slug(alert_id)}"
    profile = build_planetary_entity_profile(
        event_entity_id,
        world_entities=world_entities,
        world_relationships=world_relationships,
        country_fusion_snapshots=country_fusion_snapshots,
        correlation_chains=correlation_chains,
        alert_events=alert_events,
        hazard_forecasts=hazard_forecasts,
        corridor_snapshots=corridor_snapshots,
        fusion_timeline=fusion_timeline,
        operator_history=[],
        limit=12,
    ) or {}
    timeline = [
        item
        for item in fusion_timeline
        if str(alert_id) in {str(ref or "").strip() for ref in (item.get("alert_refs") or [])}
    ][:10]
    operator_history = load_planetary_operator_history(
        operator_events_collection,
        country=primary_country,
        alert_ids=[alert_id],
        dedupe_keys=[str(alert.get("dedupe_key") or "").strip()] if str(alert.get("dedupe_key") or "").strip() else [],
        limit=18,
    ) if operator_events_collection is not None else []
    provenance_refs = _merge_refs(list(alert.get("provenance_refs") or []), *(list(item.get("provenance_refs") or []) for item in (country_detail.get("supporting_signals") or [])))
    return {
        "contract_version": "phase-0.4",
        "generated_at": _iso_now(),
        "alert_id": str(alert_id),
        "alert": alert,
        "related_country_fusion": country_detail.get("fusion_snapshot"),
        "related_correlation_chains": [item for item in (country_detail.get("related_correlation_chains") or []) if alert_id in set(item.get("alert_refs") or [])],
        "supporting_signals": country_detail.get("supporting_signals") or [],
        "supporting_source_events": country_detail.get("supporting_source_events") or [],
        "supporting_hazard_forecasts": country_detail.get("supporting_hazard_forecasts") or [],
        "supporting_corridors": country_detail.get("supporting_corridors") or [],
        "related_entities": profile.get("neighborhood_entities") or ([profile.get("entity")] if profile.get("entity") else []),
        "related_relationships": profile.get("neighborhood_relationships") or [],
        "supporting_timeline": timeline,
        "operator_history": operator_history,
        "provenance_refs": provenance_refs,
        "evidence_summary": _evidence_summary(
            confidence_ratio=_safe_float(alert.get("confidence_ratio"), 0.0),
            freshness_sec=_safe_int(alert.get("freshness_sec"), 0),
            subsystem_scores={str(alert.get("alert_type") or "alert"): _safe_float(alert.get("severity_score"), 0.0)},
            state_vector=None,
            provenance_refs=provenance_refs,
            supporting_signals=country_detail.get("supporting_signals") or [],
            supporting_source_events=country_detail.get("supporting_source_events") or [],
            supporting_alerts=[alert],
            related_entities=profile.get("neighborhood_entities") or [],
            related_relationships=profile.get("neighborhood_relationships") or [],
            supporting_timeline=timeline,
        ),
    }
