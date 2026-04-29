from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ContractBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class SourceEventContract(ContractBaseModel):
    event_id: str
    timestamp: str
    ingested_at: str
    source_family: str
    source_name: str
    source_provenance: dict[str, Any] | list[str] | str
    geography: dict[str, Any]
    raw_payload_ref: str
    freshness_sec: int
    licensing_or_usage_tier: str


class NormalizedSignalContract(ContractBaseModel):
    signal_id: str
    timestamp: str
    generated_at: str
    signal_type: str
    source_family: str
    source_name: str
    geography: dict[str, Any]
    entity_refs: list[str] = Field(default_factory=list)
    metric_name: str
    metric_value: float
    severity_score: float
    confidence_ratio: float
    freshness_sec: int
    provenance_refs: list[dict[str, Any] | str] = Field(default_factory=list)


class WorldEntityContract(ContractBaseModel):
    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    geography: dict[str, Any]
    valid_from: str | None = None
    valid_to: str | None = None
    confidence_ratio: float
    provenance_refs: list[dict[str, Any] | str] = Field(default_factory=list)
    last_updated_at: str


class WorldRelationshipContract(ContractBaseModel):
    relationship_id: str
    relationship_type: str
    source_entity_id: str
    target_entity_id: str
    timestamp: str
    geography: dict[str, Any]
    strength_score: float
    confidence_ratio: float
    provenance_refs: list[dict[str, Any] | str] = Field(default_factory=list)
    supporting_evidence_refs: list[dict[str, Any] | str] = Field(default_factory=list)


class CountrySnapshotContract(ContractBaseModel):
    country: str
    generated_at: str
    time_window: dict[str, Any] | str
    freshness_sec: int
    confidence_ratio: float
    signal_scores: dict[str, float]
    top_alerts: list[dict[str, Any]] = Field(default_factory=list)
    source_health: dict[str, Any]
    provenance_summary: dict[str, Any]


class CorridorSnapshotContract(ContractBaseModel):
    corridor_id: str
    from_region: dict[str, Any]
    to_region: dict[str, Any]
    generated_at: str
    freshness_sec: int
    confidence_ratio: float
    flow_metrics: dict[str, Any]
    severity_score: float
    related_entities: list[str] = Field(default_factory=list)
    provenance_summary: dict[str, Any]


class HazardForecastContract(ContractBaseModel):
    forecast_id: str
    hazard_type: str
    region: str
    country: str
    generated_at: str
    forecast_horizon: dict[str, Any] | str
    likelihood: float
    severity_score: float
    confidence_ratio: float
    top_contributing_signals: list[str] = Field(default_factory=list)
    recommended_action: str
    provenance_refs: list[dict[str, Any] | str] = Field(default_factory=list)


class AlertEventContract(ContractBaseModel):
    alert_id: str
    alert_type: str
    generated_at: str
    geography: dict[str, Any]
    severity_score: float
    confidence_ratio: float
    freshness_sec: int
    related_entities_or_regions: list[str] = Field(default_factory=list)
    summary: str
    recommended_action: str
    status: str
    assignment: dict[str, Any]
    sla_state: dict[str, Any]
    provenance_refs: list[dict[str, Any] | str] = Field(default_factory=list)


class ReplayFrameContract(ContractBaseModel):
    frame_id: str
    generated_at: str
    frame_timestamp: str
    frame_type: str
    geography: dict[str, Any]
    snapshot_refs: list[str] = Field(default_factory=list)
    alert_refs: list[str] = Field(default_factory=list)
    confidence_summary: dict[str, Any]
    source_health_summary: dict[str, Any]


class RuntimeStatusContract(ContractBaseModel):
    runtime_name: str
    generated_at: str
    status: str
    last_success_at: str | None = None
    last_error_at: str | None = None
    freshness_sec: int | None = None
    queue_depth: int | None = None
    cycle_latency_ms: float | None = None
    cache_hit_ratio: float | None = None
    error_summary: dict[str, Any] | str


class PlanetaryGlobalSummaryContract(ContractBaseModel):
    generated_at: str
    freshness_sec: int
    confidence_ratio: float
    global_stress_level: float
    conflict_escalation_probability: float
    economic_panic_indicator: float
    migration_pressure_index: float
    infrastructure_fragility_score: float
    quality_gate: dict[str, Any]
    top_contributing_dimensions: list[dict[str, Any]] = Field(default_factory=list)
    provenance_summary: dict[str, Any]


class PlanetaryOverviewContract(ContractBaseModel):
    generated_at: str
    mode: str
    contract_version: str
    global_summary: PlanetaryGlobalSummaryContract
    country_snapshots: list[CountrySnapshotContract] = Field(default_factory=list)
    corridor_snapshots: list[CorridorSnapshotContract] = Field(default_factory=list)
    hazard_forecasts: list[HazardForecastContract] = Field(default_factory=list)
    alert_events: list[AlertEventContract] = Field(default_factory=list)
    world_entities: list[WorldEntityContract] = Field(default_factory=list)
    world_relationships: list[WorldRelationshipContract] = Field(default_factory=list)
    replay_frames: list[ReplayFrameContract] = Field(default_factory=list)
    runtime_status: list[RuntimeStatusContract] = Field(default_factory=list)


CONTRACT_MODEL_REGISTRY = {
    "source_event": SourceEventContract,
    "normalized_signal": NormalizedSignalContract,
    "world_entity": WorldEntityContract,
    "world_relationship": WorldRelationshipContract,
    "country_snapshot": CountrySnapshotContract,
    "corridor_snapshot": CorridorSnapshotContract,
    "hazard_forecast": HazardForecastContract,
    "alert_event": AlertEventContract,
    "replay_frame": ReplayFrameContract,
    "runtime_status": RuntimeStatusContract,
}


def build_contract_catalog_payload() -> dict[str, Any]:
    contract_families: list[dict[str, Any]] = []
    for name, model in CONTRACT_MODEL_REGISTRY.items():
        schema = model.model_json_schema()
        contract_families.append(
            {
                "name": name,
                "required_fields": list(schema.get("required") or []),
                "json_schema": schema,
            }
        )
    return {
        "generated_at": iso_now(),
        "contract_version": "phase-0.2",
        "contract_families": contract_families,
    }
