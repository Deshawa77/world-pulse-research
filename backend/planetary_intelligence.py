from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from processing.country_catalog import COUNTRY_NAMES

from backend.planetary_contracts import (
    AlertEventContract,
    CorridorSnapshotContract,
    CountrySnapshotContract,
    HazardForecastContract,
    PlanetaryGlobalSummaryContract,
    PlanetaryOverviewContract,
    ReplayFrameContract,
    RuntimeStatusContract,
    WorldEntityContract,
    WorldRelationshipContract,
    iso_now,
)


CONTRACT_VERSION = "phase-0.2"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _ratio(value: Any, default: float = 0.0) -> float:
    numeric = _safe_float(value, default)
    if numeric > 1.0:
        numeric = numeric / 100.0 if numeric <= 100.0 else default
    return _clamp(numeric, 0.0, 1.0)


def _mean(values: list[float], default: float = 0.0) -> float:
    if not values:
        return default
    return sum(float(value) for value in values) / float(len(values))


def _parse_iso(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: Any, default: str | None = None) -> str:
    parsed = _parse_iso(value)
    if parsed:
        return parsed.isoformat()
    return default or iso_now()


def _freshness_sec(value: Any, default: int = 0) -> int:
    parsed = _parse_iso(value)
    if not parsed:
        return default
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


def _country_label(country: str) -> str:
    normalized = str(country or "").upper().strip()
    return COUNTRY_NAMES.get(normalized, normalized or "Unknown")


def _slug(value: str) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    return "".join(char for char in text if char.isalnum() or char in {"-", "_", ":"})


def _top_country_rows(country_rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ranked = sorted(
        [dict(row) for row in country_rows if isinstance(row, dict)],
        key=lambda row: (
            _safe_float(row.get("display_risk"), _safe_float(row.get("raw_risk_score"), _safe_float(row.get("risk")))),
            _safe_float(row.get("risk_delta_24h")),
            _safe_float(row.get("confidence_score")),
        ),
        reverse=True,
    )
    visible = [row for row in ranked if str(row.get("gating_action") or "allow") != "suppress"]
    return (visible or ranked)[: max(1, limit)]


def build_country_snapshots(country_rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for row in _top_country_rows(country_rows, limit):
        country = str(row.get("country") or "UNK").upper()
        generated_at = _iso(row.get("feature_timestamp") or row.get("timestamp"))
        spillovers = row.get("spillover_links") if isinstance(row.get("spillover_links"), list) else []
        top_alerts: list[dict[str, Any]] = []
        raw_risk = _safe_float(row.get("raw_risk_score"), _safe_float(row.get("risk")))
        if raw_risk >= 70.0:
            top_alerts.append({
                "type": "behavioral_stress",
                "severity": row.get("risk_band") or "high",
                "reason": str(row.get("advisory") or "Elevated behavior stress detected."),
            })
        if _safe_float(row.get("risk_delta_24h")) >= 3.0:
            top_alerts.append({
                "type": "rapid_change",
                "severity": "elevated",
                "reason": f"24h risk delta {round(_safe_float(row.get('risk_delta_24h')), 2)} indicates rapid deterioration.",
            })
        for spillover in spillovers[:2]:
            top_alerts.append({
                "type": "spillover",
                "severity": "watch",
                "reason": f"Regional spillover link to {spillover.get('country')} via {spillover.get('relationship') or 'regional coupling'}.",
            })

        snapshot = CountrySnapshotContract(
            country=country,
            generated_at=generated_at,
            time_window={"primary": "24h", "secondary": "7d"},
            freshness_sec=_freshness_sec(generated_at, default=0),
            confidence_ratio=_ratio(row.get("confidence_score")),
            signal_scores={
                "raw_risk_score": round(raw_risk, 2),
                "direct_behavior_score": round(_safe_float(row.get("direct_behavior_score")), 2),
                "contextual_pressure_score": round(_safe_float(row.get("contextual_pressure_score")), 2),
                "coordination_risk_score": round(_safe_float(row.get("coordination_risk_score")), 2),
                "mobility_disruption_score": round(_safe_float(row.get("mobility_disruption_score")), 2),
                "logistics_stress_score": round(_safe_float(row.get("logistics_stress_score")), 2),
                "household_stress_score": round(_safe_float(row.get("household_stress_score")), 2),
                "energy_stress_score": round(_safe_float(row.get("energy_stress_score")), 2),
                "narrative_velocity_score": round(_safe_float(row.get("narrative_velocity_score")), 2),
            },
            top_alerts=top_alerts,
            source_health={
                "status": str(row.get("source_status") or "unknown"),
                "validated_today": bool(row.get("validated_today")),
                "source_count": _safe_int(row.get("source_count")),
                "data_quality": str(row.get("data_quality") or "unknown"),
                "quality_status": str(row.get("country_quality_status") or "unknown"),
            },
            provenance_summary={
                "subsystem": "global_human_behavior_intelligence_engine",
                "mode": str(row.get("mode") or "online"),
                "external_sources": row.get("external_sources") if isinstance(row.get("external_sources"), list) else [],
                "score_semantics": row.get("score_semantics") or {},
                "gating_action": str(row.get("gating_action") or "allow"),
            },
            risk_band=str(row.get("risk_band") or "unknown"),
            confidence_band=str(row.get("confidence_band") or "unknown"),
            display_risk=_safe_float(row.get("display_risk"), raw_risk),
            raw_risk_score=round(raw_risk, 2),
            risk_delta_24h=round(_safe_float(row.get("risk_delta_24h")), 2),
            risk_delta_7d=round(_safe_float(row.get("risk_delta_7d")), 2),
            risk_trend_direction=str(row.get("risk_trend_direction") or "stable"),
            spillover_links=spillovers,
            advisory=str(row.get("advisory") or ""),
        )
        snapshots.append(snapshot.model_dump(mode="json"))
    return snapshots

def build_corridor_snapshots(internet_payload: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    items = internet_payload.get("top_corridors") if isinstance(internet_payload.get("top_corridors"), list) and internet_payload.get("top_corridors") else internet_payload.get("flows")
    corridors = [dict(item) for item in (items or []) if isinstance(item, dict)]
    summary = internet_payload.get("summary") if isinstance(internet_payload.get("summary"), dict) else {}
    generated_at = _iso(internet_payload.get("generated_at"))
    ranked = sorted(
        corridors,
        key=lambda item: (
            _safe_float(item.get("anomaly_score")),
            _safe_float(item.get("congestion_index")),
            _safe_float(item.get("attack_index")),
            _safe_float(item.get("throughput_gbps")),
        ),
        reverse=True,
    )[: max(1, limit)]

    snapshots: list[dict[str, Any]] = []
    for item in ranked:
        severity_score = max(_ratio(item.get("anomaly_score")), _ratio(item.get("congestion_index")), _ratio(item.get("attack_index")))
        contract = CorridorSnapshotContract(
            corridor_id=str(item.get("id") or f"{item.get('origin')}-{item.get('destination')}").lower(),
            from_region={"country": str(item.get("origin") or "UNK"), "label": str(item.get("origin_label") or item.get("origin") or "Unknown")},
            to_region={"country": str(item.get("destination") or "UNK"), "label": str(item.get("destination_label") or item.get("destination") or "Unknown")},
            generated_at=_iso(item.get("generated_at"), generated_at),
            freshness_sec=max(_safe_int(item.get("freshness_sec"), 0), _freshness_sec(item.get("generated_at"), default=0)),
            confidence_ratio=_ratio(item.get("confidence_ratio"), 0.45),
            flow_metrics={
                "throughput_gbps": round(_safe_float(item.get("throughput_gbps")), 2),
                "latency_ms": round(_safe_float(item.get("latency_ms")), 2),
                "packet_loss_pct": round(_safe_float(item.get("packet_loss_pct")), 2),
                "reroute_factor": round(_safe_float(item.get("reroute_factor"), 1.0), 2),
                "congestion_index": round(_safe_float(item.get("congestion_index")), 2),
                "attack_index": round(_safe_float(item.get("attack_index")), 2),
                "anomaly_score": round(_safe_float(item.get("anomaly_score")), 2),
                "traffic_share": round(_safe_float(item.get("traffic_share")), 3),
            },
            severity_score=round(severity_score, 4),
            related_entities=[str(item.get("origin") or "UNK"), str(item.get("destination") or "UNK"), str(item.get("id") or "")],
            provenance_summary={
                "subsystem": "real_time_internet_map",
                "source_families": item.get("source_families") if isinstance(item.get("source_families"), list) else [],
                "stage": str(item.get("stage") or summary.get("source_stage") or "unknown"),
                "source_status": str(summary.get("source_status") or "unknown"),
            },
            status=str(item.get("status") or "unknown"),
            severity=str(item.get("severity") or "unknown"),
        )
        snapshots.append(contract.model_dump(mode="json"))
    return snapshots


def build_hazard_forecasts(disaster_payload: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    forecasts = [dict(item) for item in (disaster_payload.get("forecasts") or []) if isinstance(item, dict)]
    ranked = sorted(
        forecasts,
        key=lambda item: (_ratio(item.get("severity_score")), _ratio(item.get("likelihood")), _ratio(item.get("confidence"))),
        reverse=True,
    )[: max(1, limit)]

    results: list[dict[str, Any]] = []
    for item in ranked:
        hazard = str(item.get("event_type") or "unknown")
        region = str(item.get("region_name") or item.get("region") or item.get("country") or "global")
        country = str(item.get("country") or disaster_payload.get("country") or "GLB").upper()
        generated_at = _iso(item.get("updated_at"), _iso(disaster_payload.get("generated_at")))
        forecast_id = str(item.get("forecast_id") or f"{hazard}:{country}:{_slug(region)}")
        contract = HazardForecastContract(
            forecast_id=forecast_id,
            hazard_type=hazard,
            region=region,
            country=country,
            generated_at=generated_at,
            forecast_horizon={"hours": max(1, _safe_int(item.get("lead_time_hours"), 24))},
            likelihood=round(_ratio(item.get("likelihood"), 0.0), 4),
            severity_score=round(_ratio(item.get("severity_score"), 0.0), 4),
            confidence_ratio=round(_ratio(item.get("confidence"), 0.0), 4),
            top_contributing_signals=[str(signal) for signal in (item.get("top_contributing_signals") or []) if str(signal or "").strip()],
            recommended_action=str(item.get("recommended_action") or "Review the hazard evidence and prepare response options."),
            provenance_refs=[{"subsystem": "global_disaster_early_warning_ai", "source_family": str(source)} for source in (item.get("signal_sources") or []) if str(source or "").strip()],
            hazard_band=str(item.get("hazard_band") or item.get("hotspot_band") or "watch"),
            hotspot_region_count=_safe_int(item.get("regional_hotspots_count"), 0),
        )
        results.append(contract.model_dump(mode="json"))
    return results


def build_alert_events(country_snapshots: list[dict[str, Any]], internet_payload: dict[str, Any], hazard_forecasts: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    for item in country_snapshots:
        risk_score = _ratio(item.get("raw_risk_score"), 0.0)
        if risk_score < 0.68 and _safe_float(item.get("risk_delta_24h")) < 3.0:
            continue
        country = str(item.get("country") or "UNK")
        alerts.append(AlertEventContract(
            alert_id=f"behavior-{country.lower()}",
            alert_type="behavior_stress",
            generated_at=_iso(item.get("generated_at")),
            geography={"scope": "country", "country": country},
            severity_score=round(max(risk_score, _clamp(max(0.0, _safe_float(item.get("risk_delta_24h"))) / 10.0)), 4),
            confidence_ratio=round(_ratio(item.get("confidence_ratio"), 0.0), 4),
            freshness_sec=_safe_int(item.get("freshness_sec"), 0),
            related_entities_or_regions=[country] + [str(link.get("country") or "") for link in (item.get("spillover_links") or []) if str(link.get("country") or "").strip()],
            summary=f"{country} behavior stress is {item.get('risk_band') or 'elevated'} with trend {item.get('risk_trend_direction') or 'stable'}.",
            recommended_action=str(item.get("advisory") or "Inspect supporting behavior signals before escalation."),
            status="active" if risk_score >= 0.78 else "watch",
            assignment={"team": "behavior-ops", "owner": None},
            sla_state={"target_minutes": 60 if risk_score >= 0.78 else 180, "status": "open"},
            provenance_refs=[{"subsystem": "global_human_behavior_intelligence_engine", "source_status": (item.get("source_health") or {}).get("status")}],
        ).model_dump(mode="json"))

    for item in hazard_forecasts:
        severity = _ratio(item.get("severity_score"), 0.0)
        likelihood = _ratio(item.get("likelihood"), 0.0)
        if severity < 0.52 and likelihood < 0.6:
            continue
        alerts.append(AlertEventContract(
            alert_id=f"hazard-{_slug(str(item.get('forecast_id') or item.get('hazard_type') or 'unknown'))}",
            alert_type=f"hazard_{str(item.get('hazard_type') or 'unknown')}",
            generated_at=_iso(item.get("generated_at")),
            geography={"scope": "region", "country": str(item.get("country") or "GLB"), "region": str(item.get("region") or "global")},
            severity_score=round(max(severity, likelihood), 4),
            confidence_ratio=round(_ratio(item.get("confidence_ratio"), 0.0), 4),
            freshness_sec=_freshness_sec(item.get("generated_at"), default=0),
            related_entities_or_regions=[str(item.get("country") or "GLB"), str(item.get("region") or "global")],
            summary=f"{str(item.get('hazard_type') or 'hazard').capitalize()} risk elevated in {item.get('region') or item.get('country') or 'global'}.",
            recommended_action=str(item.get("recommended_action") or "Review hazard evidence and prepare response options."),
            status="active" if severity >= 0.7 else "watch",
            assignment={"team": "hazard-ops", "owner": None},
            sla_state={"target_minutes": 45 if severity >= 0.7 else 120, "status": "open"},
            provenance_refs=item.get("provenance_refs") if isinstance(item.get("provenance_refs"), list) else [],
        ).model_dump(mode="json"))

    for item in (internet_payload.get("shutdown_alerts") or []):
        if not isinstance(item, dict):
            continue
        country = str(item.get("country") or "UNK")
        alerts.append(AlertEventContract(
            alert_id=str(item.get("id") or f"shutdown-{country.lower()}"),
            alert_type="internet_shutdown",
            generated_at=_iso(item.get("generated_at") or item.get("started_at")),
            geography={"scope": "country", "country": country},
            severity_score=round(_ratio(item.get("shutdown_risk"), 0.0), 4),
            confidence_ratio=round(_ratio(item.get("confidence_ratio"), 0.0), 4),
            freshness_sec=max(_safe_int(item.get("freshness_sec"), 0), _freshness_sec(item.get("started_at"), default=0)),
            related_entities_or_regions=[country],
            summary=f"Internet shutdown risk elevated in {country}.",
            recommended_action=str(item.get("advisory") or item.get("reason") or "Verify national gateway and mobile reachability."),
            status=str(item.get("status") or "active"),
            assignment={"team": "internet-ops", "owner": None},
            sla_state={"target_minutes": 30, "status": "open"},
            provenance_refs=[{"subsystem": "real_time_internet_map", "source_family": source} for source in (item.get("source_families") or [])],
        ).model_dump(mode="json"))

    for item in (internet_payload.get("cyber_attacks") or []):
        if not isinstance(item, dict):
            continue
        origin = str(item.get("origin") or "UNK")
        target = str(item.get("target") or "UNK")
        alerts.append(AlertEventContract(
            alert_id=str(item.get("id") or f"attack-{origin.lower()}-{target.lower()}"),
            alert_type="routing_or_attack_anomaly",
            generated_at=_iso(item.get("generated_at") or item.get("started_at")),
            geography={"scope": "corridor", "origin": origin, "target": target},
            severity_score=round(_ratio(item.get("attack_index"), 0.0), 4),
            confidence_ratio=round(_ratio(item.get("confidence_ratio"), 0.0), 4),
            freshness_sec=max(_safe_int(item.get("freshness_sec"), 0), _freshness_sec(item.get("started_at"), default=0)),
            related_entities_or_regions=[origin, target],
            summary=f"Potential internet attack pressure detected between {origin} and {target}.",
            recommended_action=f"Correlate {item.get('vector') or 'control-plane'} activity with transit and edge telemetry.",
            status=str(item.get("status") or "monitoring"),
            assignment={"team": "network-security", "owner": None},
            sla_state={"target_minutes": 30, "status": "open"},
            provenance_refs=[{"subsystem": "real_time_internet_map", "source_family": source} for source in (item.get("source_families") or [])],
        ).model_dump(mode="json"))

    alerts.sort(key=lambda item: (_ratio(item.get("severity_score")), _ratio(item.get("confidence_ratio"))), reverse=True)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for alert in alerts:
        alert_id = str(alert.get("alert_id") or "")
        if not alert_id or alert_id in seen:
            continue
        seen.add(alert_id)
        deduped.append(alert)
        if len(deduped) >= limit:
            break
    return deduped

def build_world_entities(country_snapshots: list[dict[str, Any]], corridor_snapshots: list[dict[str, Any]], hazard_forecasts: list[dict[str, Any]], *, limit: int = 14) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in country_snapshots:
        country = str(item.get("country") or "UNK").upper()
        entity_id = f"country:{country}"
        if entity_id in seen:
            continue
        seen.add(entity_id)
        entities.append(WorldEntityContract(
            entity_id=entity_id,
            entity_type="country",
            canonical_name=_country_label(country),
            aliases=[country],
            geography={"scope": "country", "country": country},
            valid_from=None,
            valid_to=None,
            confidence_ratio=round(_ratio(item.get("confidence_ratio"), 0.0), 4),
            provenance_refs=[{"subsystem": "global_human_behavior_intelligence_engine"}],
            last_updated_at=_iso(item.get("generated_at")),
            current_risk_score=_safe_float(item.get("raw_risk_score")),
        ).model_dump(mode="json"))
        if len(entities) >= limit:
            return entities

    for item in corridor_snapshots:
        corridor_id = str(item.get("corridor_id") or "")
        entity_id = f"corridor:{corridor_id}"
        if not corridor_id or entity_id in seen:
            continue
        seen.add(entity_id)
        entities.append(WorldEntityContract(
            entity_id=entity_id,
            entity_type="network_corridor",
            canonical_name=f"{(item.get('from_region') or {}).get('country')}-{(item.get('to_region') or {}).get('country')}",
            aliases=[corridor_id],
            geography={"scope": "corridor", "from_country": (item.get("from_region") or {}).get("country"), "to_country": (item.get("to_region") or {}).get("country")},
            valid_from=None,
            valid_to=None,
            confidence_ratio=round(_ratio(item.get("confidence_ratio"), 0.0), 4),
            provenance_refs=[{"subsystem": "real_time_internet_map"}],
            last_updated_at=_iso(item.get("generated_at")),
        ).model_dump(mode="json"))
        if len(entities) >= limit:
            return entities

    for item in hazard_forecasts:
        region = str(item.get("region") or "global")
        hazard = str(item.get("hazard_type") or "hazard")
        entity_id = f"hazard_region:{hazard}:{_slug(region)}"
        if entity_id in seen:
            continue
        seen.add(entity_id)
        entities.append(WorldEntityContract(
            entity_id=entity_id,
            entity_type="hazard_region",
            canonical_name=f"{hazard.capitalize()} hotspot: {region}",
            aliases=[region, str(item.get("country") or "GLB")],
            geography={"scope": "region", "country": str(item.get("country") or "GLB"), "region": region},
            valid_from=None,
            valid_to=None,
            confidence_ratio=round(_ratio(item.get("confidence_ratio"), 0.0), 4),
            provenance_refs=item.get("provenance_refs") if isinstance(item.get("provenance_refs"), list) else [],
            last_updated_at=_iso(item.get("generated_at")),
        ).model_dump(mode="json"))
        if len(entities) >= limit:
            return entities
    return entities


def build_world_relationships(country_snapshots: list[dict[str, Any]], corridor_snapshots: list[dict[str, Any]], hazard_forecasts: list[dict[str, Any]], *, limit: int = 18) -> list[dict[str, Any]]:
    relationships: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in country_snapshots:
        source_country = str(item.get("country") or "UNK").upper()
        for link in (item.get("spillover_links") or []):
            target_country = str(link.get("country") or "").upper()
            if not target_country:
                continue
            relationship_id = f"spillover:{source_country}:{target_country}"
            if relationship_id in seen:
                continue
            seen.add(relationship_id)
            relationships.append(WorldRelationshipContract(
                relationship_id=relationship_id,
                relationship_type="behavioral_spillover",
                source_entity_id=f"country:{source_country}",
                target_entity_id=f"country:{target_country}",
                timestamp=_iso(item.get("generated_at")),
                geography={"scope": "regional", "country": source_country},
                strength_score=round(_clamp(_safe_float(link.get("risk"), _safe_float(item.get("raw_risk_score"))) / 100.0), 4),
                confidence_ratio=round(_ratio(item.get("confidence_ratio"), 0.0), 4),
                provenance_refs=[{"subsystem": "global_human_behavior_intelligence_engine"}],
                supporting_evidence_refs=[{"relationship": str(link.get("relationship") or "Regional spillover")}],
            ).model_dump(mode="json"))
            if len(relationships) >= limit:
                return relationships

    for item in corridor_snapshots:
        from_country = str((item.get("from_region") or {}).get("country") or "UNK").upper()
        to_country = str((item.get("to_region") or {}).get("country") or "UNK").upper()
        corridor_id = str(item.get("corridor_id") or "")
        relationship_id = f"corridor:{from_country}:{to_country}:{corridor_id}"
        if relationship_id in seen:
            continue
        seen.add(relationship_id)
        relationships.append(WorldRelationshipContract(
            relationship_id=relationship_id,
            relationship_type="network_corridor",
            source_entity_id=f"country:{from_country}",
            target_entity_id=f"country:{to_country}",
            timestamp=_iso(item.get("generated_at")),
            geography={"scope": "corridor", "from_country": from_country, "to_country": to_country},
            strength_score=round(_ratio((item.get("flow_metrics") or {}).get("anomaly_score"), 0.0), 4),
            confidence_ratio=round(_ratio(item.get("confidence_ratio"), 0.0), 4),
            provenance_refs=[{"subsystem": "real_time_internet_map"}],
            supporting_evidence_refs=[{"corridor_id": corridor_id}],
        ).model_dump(mode="json"))
        if len(relationships) >= limit:
            return relationships

    for item in hazard_forecasts:
        country = str(item.get("country") or "GLB").upper()
        region = str(item.get("region") or "global")
        hazard = str(item.get("hazard_type") or "hazard")
        relationship_id = f"hazard:{country}:{hazard}:{_slug(region)}"
        if relationship_id in seen:
            continue
        seen.add(relationship_id)
        relationships.append(WorldRelationshipContract(
            relationship_id=relationship_id,
            relationship_type="exposed_to_hazard",
            source_entity_id=f"country:{country}",
            target_entity_id=f"hazard_region:{hazard}:{_slug(region)}",
            timestamp=_iso(item.get("generated_at")),
            geography={"scope": "region", "country": country, "region": region},
            strength_score=round(max(_ratio(item.get("severity_score"), 0.0), _ratio(item.get("likelihood"), 0.0)), 4),
            confidence_ratio=round(_ratio(item.get("confidence_ratio"), 0.0), 4),
            provenance_refs=item.get("provenance_refs") if isinstance(item.get("provenance_refs"), list) else [],
            supporting_evidence_refs=[{"forecast_id": str(item.get("forecast_id") or "")}],
        ).model_dump(mode="json"))
        if len(relationships) >= limit:
            return relationships
    return relationships


def build_replay_frames(playback_frames: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for item in [frame for frame in playback_frames if isinstance(frame, dict)][: max(1, limit)]:
        countries = item.get("countries") if isinstance(item.get("countries"), list) else []
        corridors = item.get("top_corridors") if isinstance(item.get("top_corridors"), list) and item.get("top_corridors") else item.get("flows") if isinstance(item.get("flows"), list) else []
        attacks = item.get("cyber_attacks") if isinstance(item.get("cyber_attacks"), list) else []
        shutdowns = item.get("shutdown_alerts") if isinstance(item.get("shutdown_alerts"), list) else []
        source_health = item.get("source_health") if isinstance(item.get("source_health"), list) else []
        alert_refs = [str(alert.get("id") or "") for alert in attacks + shutdowns if isinstance(alert, dict) and str(alert.get("id") or "").strip()]
        snapshot_refs = [*[f"country:{str(country.get('country') or '').upper()}" for country in countries[:3] if isinstance(country, dict)], *[f"corridor:{str(flow.get('id') or '').lower()}" for flow in corridors[:3] if isinstance(flow, dict)]]
        frames.append(ReplayFrameContract(
            frame_id=str(item.get("run_id") or item.get("captured_at") or iso_now()),
            generated_at=_iso(item.get("generated_at") or item.get("captured_at")),
            frame_timestamp=_iso(item.get("captured_at") or item.get("generated_at")),
            frame_type="internet_map",
            geography={"scope": "global"},
            snapshot_refs=snapshot_refs,
            alert_refs=alert_refs,
            confidence_summary={
                "country_avg_confidence": round(_mean([_ratio(country.get("confidence_ratio"), 0.0) for country in countries if isinstance(country, dict)]), 4),
                "corridor_avg_confidence": round(_mean([_ratio(flow.get("confidence_ratio"), 0.0) for flow in corridors if isinstance(flow, dict)]), 4),
                "source_status": ((item.get("summary") or {}).get("source_status") if isinstance(item.get("summary"), dict) else None),
            },
            source_health_summary={
                "family_count": len(source_health),
                "healthy_count": sum(1 for row in source_health if str((row or {}).get("status") or "") == "healthy"),
                "degraded_count": sum(1 for row in source_health if str((row or {}).get("status") or "") == "degraded"),
                "limited_count": sum(1 for row in source_health if str((row or {}).get("status") or "") not in {"healthy", "degraded"}),
            },
        ).model_dump(mode="json"))
    return frames


def _latest_fresh_source_timestamp(freshness: dict[str, Any]) -> str | None:
    rows = freshness.get("sources") if isinstance(freshness.get("sources"), list) else []
    candidates = [(_safe_float(row.get("age_hours"), 9999.0), str(row.get("last_updated") or "").strip()) for row in rows if isinstance(row, dict) and str(row.get("last_updated") or "").strip()]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def build_runtime_statuses(global_context: dict[str, Any], internet_payload: dict[str, Any], disaster_stream_status: dict[str, Any]) -> list[dict[str, Any]]:
    generated_at = iso_now()
    freshness = global_context.get("freshness") if isinstance(global_context.get("freshness"), dict) else {}
    source_health = global_context.get("source_health") if isinstance(global_context.get("source_health"), dict) else {}
    quality_gate = global_context.get("quality_gate") if isinstance(global_context.get("quality_gate"), dict) else {}
    runtime_status: list[dict[str, Any]] = []

    runtime_status.append(RuntimeStatusContract(
        runtime_name="country_intelligence_platform",
        generated_at=generated_at,
        status="ok" if not bool(quality_gate.get("active")) else "degraded",
        last_success_at=_latest_fresh_source_timestamp(freshness),
        last_error_at=None,
        freshness_sec=int((_safe_float(freshness.get("newest_age_hours"), 0.0)) * 3600) if freshness.get("newest_age_hours") is not None else None,
        queue_depth=0,
        cycle_latency_ms=None,
        cache_hit_ratio=None,
        error_summary={"message": str(quality_gate.get("message") or "Coverage healthy"), "reasons": quality_gate.get("reasons") if isinstance(quality_gate.get("reasons"), list) else [], "critical_sources_down": _safe_int(source_health.get("critical_down_live"), _safe_int(source_health.get("critical_down")))},
    ).model_dump(mode="json"))

    internet_runtime_raw = internet_payload.get("runtime_status") if isinstance(internet_payload.get("runtime_status"), dict) else {}
    collector_summary = internet_payload.get("collector_summary") if isinstance(internet_payload.get("collector_summary"), dict) else {}
    runtime_status.append(RuntimeStatusContract(
        runtime_name="real_time_internet_map",
        generated_at=generated_at,
        status=str(internet_runtime_raw.get("last_cycle_status") or internet_runtime_raw.get("status") or "unknown"),
        last_success_at=str(internet_runtime_raw.get("last_cycle_finished_at") or internet_runtime_raw.get("captured_at") or "") or None,
        last_error_at=None,
        freshness_sec=_freshness_sec(internet_runtime_raw.get("last_cycle_finished_at") or internet_runtime_raw.get("captured_at"), default=0),
        queue_depth=_safe_int(internet_runtime_raw.get("queue_depth"), 0),
        cycle_latency_ms=round(_safe_float(internet_runtime_raw.get("cycle_latency_ms"), 0.0), 3),
        cache_hit_ratio=1.0 if bool(collector_summary.get("served_from_cache")) else (0.0 if collector_summary else None),
        error_summary={"last_error": internet_runtime_raw.get("last_error"), "source_stage": internet_runtime_raw.get("source_stage"), "collector_total_records": _safe_int(internet_runtime_raw.get("collector_total_records"), 0)},
    ).model_dump(mode="json"))

    runtime_status.append(RuntimeStatusContract(
        runtime_name="global_disaster_early_warning_ai",
        generated_at=generated_at,
        status=str(disaster_stream_status.get("status") or "idle"),
        last_success_at=str(disaster_stream_status.get("captured_at") or "") or None,
        last_error_at=None,
        freshness_sec=_freshness_sec(disaster_stream_status.get("captured_at"), default=0),
        queue_depth=0,
        cycle_latency_ms=round(_safe_float(disaster_stream_status.get("cycle_latency_ms"), 0.0), 3),
        cache_hit_ratio=None,
        error_summary={"forecast_count": _safe_int(disaster_stream_status.get("forecast_count"), 0), "active_alerts": _safe_int(disaster_stream_status.get("active_alerts"), 0), "collector_total_records": _safe_int(disaster_stream_status.get("collector_total_records"), 0), "down_families": _safe_int(disaster_stream_status.get("down_families"), 0), "stale_families": _safe_int(disaster_stream_status.get("stale_families"), 0)},
    ).model_dump(mode="json"))
    return runtime_status

def build_global_summary(country_snapshots: list[dict[str, Any]], corridor_snapshots: list[dict[str, Any]], hazard_forecasts: list[dict[str, Any]], global_context: dict[str, Any], global_doc: dict[str, Any] | None, internet_payload: dict[str, Any]) -> dict[str, Any]:
    behavior_values = [max(_ratio(item.get("raw_risk_score"), 0.0), _ratio((item.get("signal_scores") or {}).get("direct_behavior_score"), 0.0), _ratio((item.get("signal_scores") or {}).get("contextual_pressure_score"), 0.0)) for item in country_snapshots]
    economic_values = [_mean([_ratio((item.get("signal_scores") or {}).get("household_stress_score"), 0.0), _ratio((item.get("signal_scores") or {}).get("fuel_price_pressure"), 0.0), _ratio((item.get("signal_scores") or {}).get("food_price_pressure"), 0.0), _ratio((item.get("signal_scores") or {}).get("labor_stress_score"), 0.0), _ratio((item.get("signal_scores") or {}).get("fx_pressure_score"), 0.0), _ratio((item.get("signal_scores") or {}).get("remittance_stress_score"), 0.0), _ratio((item.get("signal_scores") or {}).get("energy_stress_score"), 0.0)]) for item in country_snapshots]
    migration_values = [_mean([_ratio((item.get("signal_scores") or {}).get("mobility_disruption_score"), 0.0), _ratio((item.get("signal_scores") or {}).get("logistics_stress_score"), 0.0), _ratio((item.get("signal_scores") or {}).get("coordination_risk_score"), 0.0)]) for item in country_snapshots]
    internet_summary = internet_payload.get("summary") if isinstance(internet_payload.get("summary"), dict) else {}
    infrastructure_fragility = _clamp(0.45 * _ratio(internet_summary.get("global_congestion_index"), 0.0) + 0.35 * _ratio(internet_summary.get("cyber_attack_index"), 0.0) + 0.20 * _clamp(len(internet_payload.get("shutdown_alerts") or []) / 6.0), 0.0, 1.0)
    conflict_probability = _clamp(0.45 * _mean([_ratio((item.get("signal_scores") or {}).get("coordination_risk_score"), 0.0) for item in country_snapshots], 0.0) + 0.20 * _mean([_clamp(max(0.0, _safe_float(item.get("risk_delta_24h"))) / 10.0) for item in country_snapshots], 0.0) + 0.20 * _mean([_ratio(item.get("severity_score"), 0.0) for item in hazard_forecasts], 0.0) + 0.15 * infrastructure_fragility, 0.0, 1.0)
    confidence_candidates = [*[_ratio(item.get("confidence_ratio"), 0.0) for item in country_snapshots], *[_ratio(item.get("confidence_ratio"), 0.0) for item in corridor_snapshots], *[_ratio(item.get("confidence_ratio"), 0.0) for item in hazard_forecasts]]
    global_features = (global_doc or {}).get("features") if isinstance((global_doc or {}).get("features"), dict) else {}
    if global_features.get("global_mood_confidence") is not None:
        confidence_candidates.append(_ratio(global_features.get("global_mood_confidence"), 0.0))
    freshness_candidates = [*[_safe_int(item.get("freshness_sec"), 0) for item in country_snapshots], *[_safe_int(item.get("freshness_sec"), 0) for item in corridor_snapshots], *[_freshness_sec(item.get("generated_at"), default=0) for item in hazard_forecasts]]
    quality_gate = global_context.get("quality_gate") if isinstance(global_context.get("quality_gate"), dict) else {}
    top_dimensions = [
        {"metric": "global_stress_level", "value": round(_mean(behavior_values, 0.0), 4), "subsystem": "behavior"},
        {"metric": "infrastructure_fragility_score", "value": round(infrastructure_fragility, 4), "subsystem": "internet"},
        {"metric": "economic_panic_indicator", "value": round(_mean(economic_values, 0.0), 4), "subsystem": "behavior"},
        {"metric": "migration_pressure_index", "value": round(_mean(migration_values, 0.0), 4), "subsystem": "behavior"},
        {"metric": "conflict_escalation_probability", "value": round(conflict_probability, 4), "subsystem": "fusion"},
    ]
    top_dimensions.sort(key=lambda item: _safe_float(item.get("value")), reverse=True)
    return PlanetaryGlobalSummaryContract(
        generated_at=iso_now(),
        freshness_sec=max(freshness_candidates) if freshness_candidates else 0,
        confidence_ratio=round(_mean(confidence_candidates, 0.0), 4),
        global_stress_level=round(_mean(behavior_values, 0.0), 4),
        conflict_escalation_probability=round(conflict_probability, 4),
        economic_panic_indicator=round(_mean(economic_values, 0.0), 4),
        migration_pressure_index=round(_mean(migration_values, 0.0), 4),
        infrastructure_fragility_score=round(infrastructure_fragility, 4),
        quality_gate=quality_gate,
        top_contributing_dimensions=top_dimensions[:5],
        provenance_summary={"subsystems": ["global_human_behavior_intelligence_engine", "global_disaster_early_warning_ai", "real_time_internet_map"], "behavior_country_count": len(country_snapshots), "corridor_count": len(corridor_snapshots), "hazard_count": len(hazard_forecasts), "internet_source_status": internet_summary.get("source_status"), "global_risk_score": global_features.get("global_risk_score")},
    ).model_dump(mode="json")


def build_planetary_overview_payload(*, mode: str, country_rows: list[dict[str, Any]], internet_payload: dict[str, Any], disaster_payload: dict[str, Any], playback_frames: list[dict[str, Any]], global_context: dict[str, Any], global_doc: dict[str, Any] | None, disaster_stream_status: dict[str, Any], country_limit: int = 10, corridor_limit: int = 8, hazard_limit: int = 8, replay_limit: int = 8, entity_limit: int = 14, relationship_limit: int = 18, alert_limit: int = 12) -> dict[str, Any]:
    country_snapshots = build_country_snapshots(country_rows, limit=country_limit)
    corridor_snapshots = build_corridor_snapshots(internet_payload, limit=corridor_limit)
    hazard_forecasts = build_hazard_forecasts(disaster_payload, limit=hazard_limit)
    alert_events = build_alert_events(country_snapshots, internet_payload, hazard_forecasts, limit=alert_limit)
    world_entities = build_world_entities(country_snapshots, corridor_snapshots, hazard_forecasts, limit=entity_limit)
    world_relationships = build_world_relationships(country_snapshots, corridor_snapshots, hazard_forecasts, limit=relationship_limit)
    replay_frames_payload = build_replay_frames(playback_frames, limit=replay_limit)
    runtime_status = build_runtime_statuses(global_context, internet_payload, disaster_stream_status)
    global_summary = build_global_summary(country_snapshots, corridor_snapshots, hazard_forecasts, global_context, global_doc, internet_payload)
    return PlanetaryOverviewContract(
        generated_at=iso_now(),
        mode=mode,
        contract_version=CONTRACT_VERSION,
        global_summary=global_summary,
        country_snapshots=country_snapshots,
        corridor_snapshots=corridor_snapshots,
        hazard_forecasts=hazard_forecasts,
        alert_events=alert_events,
        world_entities=world_entities,
        world_relationships=world_relationships,
        replay_frames=replay_frames_payload,
        runtime_status=runtime_status,
    ).model_dump(mode="json")
