from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.planetary_intelligence import build_world_entities, build_world_relationships
from database.mongo import db
from processing.planetary_graph_ingestion import build_text_graph_enrichment

ROOT = Path(__file__).resolve().parents[1]
GRAPH_ROOT = ROOT / "data_lake" / "planetary_intelligence" / "graph"
ENTITY_ROOT = GRAPH_ROOT / "entities"
ENTITY_HISTORY_DIR = ENTITY_ROOT / "history"
ENTITY_LATEST_JSONL = ENTITY_ROOT / "latest.jsonl"
RELATIONSHIP_ROOT = GRAPH_ROOT / "relationships"
RELATIONSHIP_HISTORY_DIR = RELATIONSHIP_ROOT / "history"
RELATIONSHIP_LATEST_JSONL = RELATIONSHIP_ROOT / "latest.jsonl"
MANIFEST_ROOT = GRAPH_ROOT / "manifests"
MANIFEST_HISTORY_DIR = MANIFEST_ROOT / "history"
MANIFEST_LATEST_JSON = MANIFEST_ROOT / "latest.json"

PLANETARY_WORLD_ENTITIES_COLLECTION = "platform_world_entities"
PLANETARY_WORLD_RELATIONSHIPS_COLLECTION = "platform_world_relationships"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    _ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=_json_default, ensure_ascii=True))
            handle.write("\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if isinstance(payload, dict):
                rows.append(payload)
    except Exception:
        return []
    return rows


def _paths(root: str | Path | None = None) -> dict[str, Path]:
    base = Path(root) if root is not None else GRAPH_ROOT
    return {
        "entity_latest": base / "entities" / "latest.jsonl",
        "entity_history": base / "entities" / "history",
        "relationship_latest": base / "relationships" / "latest.jsonl",
        "relationship_history": base / "relationships" / "history",
        "manifest_latest": base / "manifests" / "latest.json",
        "manifest_history": base / "manifests" / "history",
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return {name: counts[name] for name in sorted(counts.keys())}


def _file_slug(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    return "".join(char for char in text if char.isalnum() or char in {"-", "_"}) or "run"


def _insert_many(collection_name: str, docs: list[dict[str, Any]]) -> int:
    if not docs:
        return 0
    try:
        result = db[collection_name].insert_many(docs, ordered=False)
        return len(result.inserted_ids)
    except Exception:
        return 0


def persist_planetary_graph_batch(
    *,
    world_entities: list[dict[str, Any]],
    world_relationships: list[dict[str, Any]],
    run_id: str,
    captured_at: str,
    mode: str = "online",
    root: str | Path | None = None,
    persist_db: bool = True,
) -> dict[str, Any]:
    paths = _paths(root)
    entity_rows = [row for row in world_entities if isinstance(row, dict)]
    relationship_rows = [row for row in world_relationships if isinstance(row, dict)]
    safe_run_id = _file_slug(run_id)

    entity_history_path = paths["entity_history"] / f"graph_{safe_run_id}.jsonl"
    relationship_history_path = paths["relationship_history"] / f"graph_{safe_run_id}.jsonl"
    manifest_history_path = paths["manifest_history"] / f"graph_{safe_run_id}.json"

    _write_jsonl(paths["entity_latest"], entity_rows)
    _write_jsonl(entity_history_path, entity_rows)
    _write_jsonl(paths["relationship_latest"], relationship_rows)
    _write_jsonl(relationship_history_path, relationship_rows)

    inserted_entities = _insert_many(PLANETARY_WORLD_ENTITIES_COLLECTION, entity_rows) if persist_db else 0
    inserted_relationships = _insert_many(PLANETARY_WORLD_RELATIONSHIPS_COLLECTION, relationship_rows) if persist_db else 0

    manifest = {
        "captured_at": captured_at,
        "run_id": run_id,
        "mode": mode,
        "contract_version": "phase-0.2",
        "platform_scope": "planetary_graph",
        "world_entity_count": len(entity_rows),
        "world_relationship_count": len(relationship_rows),
        "entity_types": _counts(entity_rows, "entity_type"),
        "relationship_types": _counts(relationship_rows, "relationship_type"),
        "entity_latest_path": str(paths["entity_latest"]),
        "entity_history_path": str(entity_history_path),
        "relationship_latest_path": str(paths["relationship_latest"]),
        "relationship_history_path": str(relationship_history_path),
        "mongo_inserted": {
            "world_entities": inserted_entities,
            "world_relationships": inserted_relationships,
        },
    }
    _write_json(paths["manifest_latest"], manifest)
    _write_json(manifest_history_path, manifest)
    return {
        "status": "ok",
        **manifest,
        "manifest_latest_path": str(paths["manifest_latest"]),
        "manifest_history_path": str(manifest_history_path),
    }


def _timestamp_sort_key(row: dict[str, Any]) -> float:
    raw = str(row.get("last_updated_at") or row.get("timestamp") or "")
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _dedupe_rows(rows: list[dict[str, Any]], id_key: str) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        marker = str(row.get(id_key) or "").strip() or json.dumps(row, sort_keys=True, default=_json_default)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(row)
    return unique


def _load_rows_from_files(latest_path: Path, history_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if history_dir.exists():
        history_paths = sorted(history_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
        target_rows = max(200, int(limit) * 4)
        for path in history_paths:
            rows.extend(_read_jsonl(path))
            if len(rows) >= target_rows:
                break
    if not rows:
        rows.extend(_read_jsonl(latest_path))
    return rows


def _load_rows_from_mongo(collection_name: str, *, limit: int) -> list[dict[str, Any]]:
    try:
        cursor = db[collection_name].find({}, {"_id": 0}).sort("_id", -1).limit(max(200, int(limit) * 4))
        return [row for row in cursor if isinstance(row, dict)]
    except Exception:
        return []


def load_recent_planetary_world_entities(
    *,
    limit: int = 100,
    root: str | Path | None = None,
    entity_type: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    paths = _paths(root)
    rows = _load_rows_from_files(paths["entity_latest"], paths["entity_history"], limit=limit)
    if not rows and root is None:
        rows = _load_rows_from_mongo(PLANETARY_WORLD_ENTITIES_COLLECTION, limit=limit)
    needle = str(search or "").strip().lower()
    filtered = []
    for row in rows:
        if entity_type and str(row.get("entity_type") or "").strip().lower() != str(entity_type).strip().lower():
            continue
        if needle:
            aliases = row.get("aliases") if isinstance(row.get("aliases"), list) else []
            haystack = " ".join(
                [
                    str(row.get("entity_id") or ""),
                    str(row.get("canonical_name") or ""),
                    " ".join(str(alias or "") for alias in aliases),
                    str((row.get("geography") or {}).get("country") or ""),
                    str((row.get("geography") or {}).get("region") or ""),
                ]
            ).lower()
            if needle not in haystack:
                continue
        filtered.append(row)
    filtered.sort(key=_timestamp_sort_key, reverse=True)
    return _dedupe_rows(filtered, "entity_id")[: max(1, int(limit))]


def load_recent_planetary_world_relationships(
    *,
    limit: int = 120,
    root: str | Path | None = None,
    relationship_type: str | None = None,
    entity_id: str | None = None,
) -> list[dict[str, Any]]:
    paths = _paths(root)
    rows = _load_rows_from_files(paths["relationship_latest"], paths["relationship_history"], limit=limit)
    if not rows and root is None:
        rows = _load_rows_from_mongo(PLANETARY_WORLD_RELATIONSHIPS_COLLECTION, limit=limit)
    needle = str(entity_id or "").strip().lower()
    filtered = []
    for row in rows:
        if relationship_type and str(row.get("relationship_type") or "").strip().lower() != str(relationship_type).strip().lower():
            continue
        if needle:
            source = str(row.get("source_entity_id") or "").strip().lower()
            target = str(row.get("target_entity_id") or "").strip().lower()
            if needle not in source and needle not in target:
                continue
        filtered.append(row)
    filtered.sort(key=_timestamp_sort_key, reverse=True)
    return _dedupe_rows(filtered, "relationship_id")[: max(1, int(limit))]


def seed_planetary_graph_snapshot(
    country_snapshots: list[dict[str, Any]],
    corridor_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    *,
    run_id: str,
    captured_at: str,
    mode: str = "online",
    entity_limit: int = 24,
    relationship_limit: int = 32,
    root: str | Path | None = None,
    persist_db: bool = True,
) -> dict[str, Any]:
    world_entities = build_world_entities(country_snapshots, corridor_snapshots, hazard_forecasts, limit=max(1, entity_limit))
    world_relationships = build_world_relationships(country_snapshots, corridor_snapshots, hazard_forecasts, limit=max(1, relationship_limit))
    persistence = persist_planetary_graph_batch(
        world_entities=world_entities,
        world_relationships=world_relationships,
        run_id=run_id,
        captured_at=captured_at,
        mode=mode,
        root=root,
        persist_db=persist_db,
    )
    return {
        **persistence,
        "world_entities": world_entities,
        "world_relationships": world_relationships,
    }


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    return "".join(char for char in text if char.isalnum() or char in {"-", "_", ":"}) or "unknown"


def _topic_specs() -> list[tuple[str, str]]:
    return [
        ("narrative_velocity_score", "Narrative Acceleration"),
        ("mobility_disruption_score", "Mobility Disruption"),
        ("energy_stress_score", "Energy Stress"),
        ("household_stress_score", "Household Stress"),
        ("coordination_risk_score", "Coordination Pressure"),
    ]


def _additional_world_entities(
    country_snapshots: list[dict[str, Any]],
    alert_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    alerts = [item for item in (alert_events or []) if isinstance(item, dict)]

    for alert in alerts:
        alert_id = str(alert.get("alert_id") or "").strip()
        if not alert_id:
            continue
        entity_id = f"event:{_slug(alert_id)}"
        if entity_id in seen:
            continue
        seen.add(entity_id)
        geography = alert.get("geography") if isinstance(alert.get("geography"), dict) else {"scope": "global"}
        country = str(geography.get("country") or geography.get("origin") or geography.get("target") or "").strip().upper()
        rows.append(
            {
                "entity_id": entity_id,
                "entity_type": "named_event",
                "canonical_name": str(alert.get("summary") or alert.get("alert_type") or alert_id),
                "aliases": [alert_id, str(alert.get("alert_type") or "")],
                "geography": geography,
                "valid_from": None,
                "valid_to": None,
                "confidence_ratio": round(_safe_float(alert.get("confidence_ratio"), 0.0), 4),
                "provenance_refs": list(alert.get("provenance_refs") or []),
                "last_updated_at": str(alert.get("generated_at") or datetime.now(timezone.utc).isoformat()),
                "current_risk_score": round(_safe_float(alert.get("severity_score"), 0.0) * 100.0, 2),
            }
        )
        team = str((alert.get("assignment") or {}).get("team") or (alert.get("ops_state") or {}).get("team_queue") or "").strip()
        if team:
            org_id = f"organization:{_slug(team)}"
            if org_id not in seen:
                seen.add(org_id)
                rows.append(
                    {
                        "entity_id": org_id,
                        "entity_type": "organization",
                        "canonical_name": team.replace("-", " ").title(),
                        "aliases": [team],
                        "geography": {"scope": "global", "country": country or None},
                        "valid_from": None,
                        "valid_to": None,
                        "confidence_ratio": round(_safe_float(alert.get("confidence_ratio"), 0.0), 4),
                        "provenance_refs": [{"subsystem": "planetary_intelligence"}],
                        "last_updated_at": str(alert.get("generated_at") or datetime.now(timezone.utc).isoformat()),
                    }
                )
        topic_id = f"topic:{_slug(alert.get('alert_type') or 'alert')}"
        if topic_id not in seen:
            seen.add(topic_id)
            rows.append(
                {
                    "entity_id": topic_id,
                    "entity_type": "narrative_topic",
                    "canonical_name": str(alert.get("alert_type") or "alert").replace("_", " ").title(),
                    "aliases": [str(alert.get("alert_type") or "")],
                    "geography": geography,
                    "valid_from": None,
                    "valid_to": None,
                    "confidence_ratio": round(_safe_float(alert.get("confidence_ratio"), 0.0), 4),
                    "provenance_refs": list(alert.get("provenance_refs") or []),
                    "last_updated_at": str(alert.get("generated_at") or datetime.now(timezone.utc).isoformat()),
                }
            )

    for item in country_snapshots:
        country = str(item.get("country") or "").strip().upper()
        signal_scores = item.get("signal_scores") if isinstance(item.get("signal_scores"), dict) else {}
        for metric_name, label in _topic_specs():
            if _safe_float(signal_scores.get(metric_name), 0.0) < 55.0:
                continue
            entity_id = f"topic:{_slug(metric_name)}"
            if entity_id in seen:
                continue
            seen.add(entity_id)
            rows.append(
                {
                    "entity_id": entity_id,
                    "entity_type": "narrative_topic",
                    "canonical_name": label,
                    "aliases": [metric_name],
                    "geography": {"scope": "country", "country": country},
                    "valid_from": None,
                    "valid_to": None,
                    "confidence_ratio": round(_safe_float(item.get("confidence_ratio"), 0.0), 4),
                    "provenance_refs": [{"subsystem": "global_human_behavior_intelligence_engine"}],
                    "last_updated_at": str(item.get("generated_at") or datetime.now(timezone.utc).isoformat()),
                }
            )
    return rows


def _additional_world_relationships(
    country_snapshots: list[dict[str, Any]],
    alert_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    alerts = [item for item in (alert_events or []) if isinstance(item, dict)]

    for alert in alerts:
        alert_id = str(alert.get("alert_id") or "").strip()
        if not alert_id:
            continue
        event_entity_id = f"event:{_slug(alert_id)}"
        geography = alert.get("geography") if isinstance(alert.get("geography"), dict) else {}
        countries = [
            str(geography.get("country") or "").strip().upper(),
            str(geography.get("origin") or "").strip().upper(),
            str(geography.get("target") or "").strip().upper(),
        ]
        for country in [code for code in countries if code]:
            relationship_id = f"event_country:{_slug(alert_id)}:{country}"
            if relationship_id in seen:
                continue
            seen.add(relationship_id)
            rows.append(
                {
                    "relationship_id": relationship_id,
                    "relationship_type": "event_impacts_country",
                    "source_entity_id": event_entity_id,
                    "target_entity_id": f"country:{country}",
                    "timestamp": str(alert.get("generated_at") or datetime.now(timezone.utc).isoformat()),
                    "geography": {"scope": "country", "country": country},
                    "strength_score": round(_safe_float(alert.get("severity_score"), 0.0), 4),
                    "confidence_ratio": round(_safe_float(alert.get("confidence_ratio"), 0.0), 4),
                    "provenance_refs": list(alert.get("provenance_refs") or []),
                    "supporting_evidence_refs": [{"alert_id": alert_id}],
                }
            )
        team = str((alert.get("assignment") or {}).get("team") or (alert.get("ops_state") or {}).get("team_queue") or "").strip()
        if team:
            relationship_id = f"org_event:{_slug(team)}:{_slug(alert_id)}"
            if relationship_id not in seen:
                seen.add(relationship_id)
                rows.append(
                    {
                        "relationship_id": relationship_id,
                        "relationship_type": "organization_responds_to_event",
                        "source_entity_id": f"organization:{_slug(team)}",
                        "target_entity_id": event_entity_id,
                        "timestamp": str(alert.get("generated_at") or datetime.now(timezone.utc).isoformat()),
                        "geography": geography or {"scope": "global"},
                        "strength_score": round(_safe_float(alert.get("severity_score"), 0.0), 4),
                        "confidence_ratio": round(_safe_float(alert.get("confidence_ratio"), 0.0), 4),
                        "provenance_refs": [{"subsystem": "planetary_intelligence"}],
                        "supporting_evidence_refs": [{"team": team, "alert_id": alert_id}],
                    }
                )
        topic_id = f"topic:{_slug(alert.get('alert_type') or 'alert')}"
        relationship_id = f"event_topic:{_slug(alert_id)}:{_slug(topic_id)}"
        if relationship_id not in seen:
            seen.add(relationship_id)
            rows.append(
                {
                    "relationship_id": relationship_id,
                    "relationship_type": "event_amplifies_topic",
                    "source_entity_id": event_entity_id,
                    "target_entity_id": topic_id,
                    "timestamp": str(alert.get("generated_at") or datetime.now(timezone.utc).isoformat()),
                    "geography": geography or {"scope": "global"},
                    "strength_score": round(_safe_float(alert.get("severity_score"), 0.0), 4),
                    "confidence_ratio": round(_safe_float(alert.get("confidence_ratio"), 0.0), 4),
                    "provenance_refs": list(alert.get("provenance_refs") or []),
                    "supporting_evidence_refs": [{"alert_id": alert_id}],
                }
            )

    for item in country_snapshots:
        country = str(item.get("country") or "").strip().upper()
        signal_scores = item.get("signal_scores") if isinstance(item.get("signal_scores"), dict) else {}
        for metric_name, _label in _topic_specs():
            if _safe_float(signal_scores.get(metric_name), 0.0) < 55.0:
                continue
            relationship_id = f"country_topic:{country}:{_slug(metric_name)}"
            if relationship_id in seen:
                continue
            seen.add(relationship_id)
            rows.append(
                {
                    "relationship_id": relationship_id,
                    "relationship_type": "country_topic_pressure",
                    "source_entity_id": f"country:{country}",
                    "target_entity_id": f"topic:{_slug(metric_name)}",
                    "timestamp": str(item.get("generated_at") or datetime.now(timezone.utc).isoformat()),
                    "geography": {"scope": "country", "country": country},
                    "strength_score": round(min(1.0, _safe_float(signal_scores.get(metric_name), 0.0) / 100.0), 4),
                    "confidence_ratio": round(_safe_float(item.get("confidence_ratio"), 0.0), 4),
                    "provenance_refs": [{"subsystem": "global_human_behavior_intelligence_engine"}],
                    "supporting_evidence_refs": [{"metric": metric_name}],
                }
            )
    return rows


def seed_planetary_graph_snapshot(
    country_snapshots: list[dict[str, Any]],
    corridor_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    *,
    alert_events: list[dict[str, Any]] | None = None,
    run_id: str,
    captured_at: str,
    mode: str = "online",
    entity_limit: int = 24,
    relationship_limit: int = 32,
    root: str | Path | None = None,
    persist_db: bool = True,
) -> dict[str, Any]:
    base_entities = build_world_entities(country_snapshots, corridor_snapshots, hazard_forecasts, limit=max(1, entity_limit))
    extra_entities = _additional_world_entities(country_snapshots, alert_events)
    world_entities = _dedupe_rows([*base_entities, *extra_entities], "entity_id")[: max(1, int(entity_limit))]

    base_relationships = build_world_relationships(country_snapshots, corridor_snapshots, hazard_forecasts, limit=max(1, relationship_limit))
    extra_relationships = _additional_world_relationships(country_snapshots, alert_events)
    world_relationships = _dedupe_rows([*base_relationships, *extra_relationships], "relationship_id")[: max(1, int(relationship_limit))]

    persistence = persist_planetary_graph_batch(
        world_entities=world_entities,
        world_relationships=world_relationships,
        run_id=run_id,
        captured_at=captured_at,
        mode=mode,
        root=root,
        persist_db=persist_db,
    )
    return {
        **persistence,
        "world_entities": world_entities,
        "world_relationships": world_relationships,
    }

def _merge_ref_lists(*groups: list[Any]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group or []:
            if not isinstance(item, dict):
                continue
            marker = json.dumps(item, sort_keys=True, default=_json_default)
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(dict(item))
    return merged


def _normalize_alias(value: Any) -> str:
    text = str(value or "").strip().lower()
    cleaned = "".join(char if char.isalnum() else " " for char in text)
    return " ".join(cleaned.split())


def _alias_token_set(value: Any) -> set[str]:
    normalized = _normalize_alias(value)
    return {token for token in normalized.split() if token}


def _entity_group(entity_type: str) -> str:
    text = str(entity_type or "unknown").strip().lower()
    if text in {"named_event", "organization", "narrative_topic", "country", "corridor", "hazard"}:
        return text
    return text or "unknown"


def _entity_alias_tokens(row: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    entity_id = str(row.get("entity_id") or "").strip()
    if entity_id:
        tokens.add(_normalize_alias(entity_id))
        if ":" in entity_id:
            tokens.add(_normalize_alias(entity_id.split(":", 1)[1]))
    canonical_name = str(row.get("canonical_name") or "").strip()
    if canonical_name:
        tokens.add(_normalize_alias(canonical_name))
    for alias in row.get("aliases") or []:
        normalized = _normalize_alias(alias)
        if normalized:
            tokens.add(normalized)
    geography = row.get("geography") if isinstance(row.get("geography"), dict) else {}
    for key in ("country", "region", "label"):
        normalized = _normalize_alias(geography.get(key))
        if normalized:
            tokens.add(normalized)
    return {token for token in tokens if token}


def canonicalize_world_entities(world_entities: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    canonical_entities: list[dict[str, Any]] = []
    canonical_by_id: dict[str, dict[str, Any]] = {}
    token_index: dict[tuple[str, str], str] = {}
    alias_map: dict[str, str] = {}

    for item in world_entities:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        entity_type = str(row.get("entity_type") or "unknown").strip().lower() or "unknown"
        row_id = str(row.get("entity_id") or "").strip() or f"{entity_type}:{_slug(row.get('canonical_name') or 'unknown')}"
        row["entity_id"] = row_id
        group = _entity_group(entity_type)
        tokens = _entity_alias_tokens(row)
        canonical_id = next((token_index.get((group, token)) for token in tokens if token_index.get((group, token))), None)
        if canonical_id and canonical_id in canonical_by_id:
            current = canonical_by_id[canonical_id]
            current_aliases = {_normalize_alias(alias): str(alias) for alias in current.get("aliases") or [] if str(alias or "").strip()}
            for alias in row.get("aliases") or []:
                normalized = _normalize_alias(alias)
                if normalized and normalized not in current_aliases:
                    current_aliases[normalized] = str(alias)
            canonical_name = str(row.get("canonical_name") or "").strip()
            if canonical_name and _normalize_alias(canonical_name) not in current_aliases:
                current_aliases[_normalize_alias(canonical_name)] = canonical_name
            current["aliases"] = sorted(current_aliases.values())
            current["confidence_ratio"] = round(max(_safe_float(current.get("confidence_ratio"), 0.0), _safe_float(row.get("confidence_ratio"), 0.0)), 4)
            current["current_risk_score"] = round(max(_safe_float(current.get("current_risk_score"), 0.0), _safe_float(row.get("current_risk_score"), 0.0)), 2) or current.get("current_risk_score")
            current["provenance_refs"] = _merge_ref_lists(current.get("provenance_refs") or [], row.get("provenance_refs") or [])
            current["last_updated_at"] = max(
                [str(current.get("last_updated_at") or ""), str(row.get("last_updated_at") or "")],
                key=lambda raw: _timestamp_sort_key({"last_updated_at": raw}),
            )
            current_geography = current.get("geography") if isinstance(current.get("geography"), dict) else {}
            row_geography = row.get("geography") if isinstance(row.get("geography"), dict) else {}
            if len(row_geography) > len(current_geography):
                current["geography"] = row_geography
        else:
            canonical_id = row_id
            row["aliases"] = sorted({str(alias) for alias in (row.get("aliases") or []) if str(alias or "").strip()} | ({str(row.get("canonical_name") or "").strip()} if str(row.get("canonical_name") or "").strip() else set()))
            row["provenance_refs"] = _merge_ref_lists(row.get("provenance_refs") or [])
            canonical_by_id[canonical_id] = row
            canonical_entities.append(row)
        alias_map[row_id] = canonical_id
        for token in tokens:
            token_index[(group, token)] = canonical_id

    canonical_entities.sort(key=lambda row: (_safe_float(row.get("current_risk_score"), 0.0), _safe_float(row.get("confidence_ratio"), 0.0), _timestamp_sort_key(row)), reverse=True)
    return canonical_entities, alias_map


def canonicalize_world_relationships(world_relationships: list[dict[str, Any]], alias_map: dict[str, str] | None = None) -> list[dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    alias_lookup = alias_map or {}
    for item in world_relationships:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["source_entity_id"] = alias_lookup.get(str(row.get("source_entity_id") or "").strip(), str(row.get("source_entity_id") or "").strip())
        row["target_entity_id"] = alias_lookup.get(str(row.get("target_entity_id") or "").strip(), str(row.get("target_entity_id") or "").strip())
        key = "|".join(
            [
                str(row.get("relationship_type") or "unknown"),
                str(row.get("source_entity_id") or "unknown"),
                str(row.get("target_entity_id") or "unknown"),
            ]
        )
        if key in index:
            current = index[key]
            current["strength_score"] = round(max(_safe_float(current.get("strength_score"), 0.0), _safe_float(row.get("strength_score"), 0.0)), 4)
            current["confidence_ratio"] = round(max(_safe_float(current.get("confidence_ratio"), 0.0), _safe_float(row.get("confidence_ratio"), 0.0)), 4)
            current["timestamp"] = max(
                [str(current.get("timestamp") or ""), str(row.get("timestamp") or "")],
                key=lambda raw: _timestamp_sort_key({"timestamp": raw}),
            )
            current["provenance_refs"] = _merge_ref_lists(current.get("provenance_refs") or [], row.get("provenance_refs") or [])
            current["supporting_evidence_refs"] = _merge_ref_lists(current.get("supporting_evidence_refs") or [], row.get("supporting_evidence_refs") or [])
            continue
        row["relationship_id"] = str(row.get("relationship_id") or f"rel:{_slug(key)}")
        row["provenance_refs"] = _merge_ref_lists(row.get("provenance_refs") or [])
        row["supporting_evidence_refs"] = _merge_ref_lists(row.get("supporting_evidence_refs") or [])
        index[key] = row
    rows = list(index.values())
    rows.sort(key=lambda row: (_safe_float(row.get("strength_score"), 0.0), _safe_float(row.get("confidence_ratio"), 0.0), _timestamp_sort_key(row)), reverse=True)
    return rows


def resolve_planetary_entity(
    entity_query: str,
    *,
    world_entities: list[dict[str, Any]],
    entity_type: str | None = None,
) -> dict[str, Any] | None:
    query = str(entity_query or "").strip()
    if not query:
        return None
    canonical_entities, _alias_map = canonicalize_world_entities(world_entities)
    query_token = _normalize_alias(query)
    query_tokens = _alias_token_set(query)
    type_filter = str(entity_type or "").strip().lower()
    best_match: dict[str, Any] | None = None
    best_score = -1
    matched_alias = None
    for entity in canonical_entities:
        if type_filter and str(entity.get("entity_type") or "").strip().lower() != type_filter:
            continue
        entity_id = str(entity.get("entity_id") or "").strip()
        canonical_name = str(entity.get("canonical_name") or "").strip()
        aliases = [str(alias or "").strip() for alias in (entity.get("aliases") or []) if str(alias or "").strip()]
        score = 0
        local_alias = None
        if query == entity_id:
            score = 100
        elif query_token == _normalize_alias(canonical_name):
            score = 95
            local_alias = canonical_name
        else:
            for alias in aliases:
                normalized = _normalize_alias(alias)
                if query_token == normalized:
                    score = 92
                    local_alias = alias
                    break
                if query_token and query_token in normalized:
                    score = max(score, 78)
                    local_alias = alias
            if not score and query_token and query_token in _normalize_alias(canonical_name):
                score = 82
                local_alias = canonical_name
        if query_tokens and score < 90:
            candidate_pool = [canonical_name, entity_id, *aliases]
            for candidate in candidate_pool:
                candidate_tokens = _alias_token_set(candidate)
                if not candidate_tokens:
                    continue
                overlap = len(query_tokens & candidate_tokens)
                if overlap == len(query_tokens):
                    score = max(score, 86 + min(4, len(query_tokens)))
                    local_alias = candidate
                elif overlap:
                    ratio = overlap / max(len(query_tokens), 1)
                    score = max(score, int(70 + ratio * 10))
                    local_alias = candidate
        if score > best_score:
            best_score = score
            best_match = entity
            matched_alias = local_alias
    if not best_match:
        return None
    return {
        "entity": best_match,
        "matched_alias": matched_alias,
        "query": query,
    }


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


def build_planetary_entity_profile(
    entity_query: str,
    *,
    world_entities: list[dict[str, Any]],
    world_relationships: list[dict[str, Any]],
    country_fusion_snapshots: list[dict[str, Any]] | None = None,
    correlation_chains: list[dict[str, Any]] | None = None,
    alert_events: list[dict[str, Any]] | None = None,
    hazard_forecasts: list[dict[str, Any]] | None = None,
    corridor_snapshots: list[dict[str, Any]] | None = None,
    fusion_timeline: list[dict[str, Any]] | None = None,
    operator_history: list[dict[str, Any]] | None = None,
    entity_type: str | None = None,
    limit: int = 12,
) -> dict[str, Any] | None:
    canonical_entities, alias_map = canonicalize_world_entities(world_entities)
    canonical_relationships = canonicalize_world_relationships(world_relationships, alias_map)
    resolved = resolve_planetary_entity(entity_query, world_entities=canonical_entities, entity_type=entity_type)
    if not resolved:
        return None
    entity = resolved["entity"]
    canonical_id = str(entity.get("entity_id") or "").strip()
    neighborhood_relationships = [
        row for row in canonical_relationships
        if canonical_id in {str(row.get("source_entity_id") or "").strip(), str(row.get("target_entity_id") or "").strip()}
    ][: max(1, int(limit))]
    neighbor_ids: list[str] = []
    for row in neighborhood_relationships:
        source_id = str(row.get("source_entity_id") or "").strip()
        target_id = str(row.get("target_entity_id") or "").strip()
        other = target_id if source_id == canonical_id else source_id
        if other and other not in neighbor_ids:
            neighbor_ids.append(other)
    neighborhood_entities = [row for row in canonical_entities if str(row.get("entity_id") or "").strip() in neighbor_ids][: max(1, int(limit))]

    country_scope: set[str] = set()
    geography = entity.get("geography") if isinstance(entity.get("geography"), dict) else {}
    for key in ("country", "origin", "target"):
        value = str(geography.get(key) or "").strip().upper()
        if value:
            country_scope.add(value)
    if canonical_id.startswith("country:"):
        country_scope.add(canonical_id.split(":", 1)[1].strip().upper())

    related_alerts = [
        row for row in (alert_events or [])
        if canonical_id == f"event:{_slug(row.get('alert_id') or '')}" or bool(country_scope & _alert_countries(row))
    ][: max(1, int(limit))]
    related_hazards = [
        row for row in (hazard_forecasts or [])
        if str(row.get("country") or "").strip().upper() in country_scope
    ][: max(1, int(limit))]
    related_corridors = [
        row for row in (corridor_snapshots or [])
        if country_scope & {
            str((row.get("from_region") or {}).get("country") or "").strip().upper(),
            str((row.get("to_region") or {}).get("country") or "").strip().upper(),
        }
    ][: max(1, int(limit))]
    related_fusion = [
        row for row in (country_fusion_snapshots or [])
        if str(row.get("country") or "").strip().upper() in country_scope
    ][:4]
    related_chains = [
        row for row in (correlation_chains or [])
        if str(row.get("country") or "").strip().upper() in country_scope or canonical_id in {str(item or "").strip() for item in (row.get("entity_refs") or [])}
    ][: max(1, int(limit))]
    related_timeline = [
        row for row in (fusion_timeline or [])
        if str(row.get("country") or "").strip().upper() in country_scope
        or canonical_id in {str(item or "").strip() for item in (row.get("snapshot_refs") or [])}
        or canonical_id in {str(item or "").strip() for item in (row.get("chain_refs") or [])}
    ][: max(1, int(limit))]

    return {
        "contract_version": "phase-0.4",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query": resolved.get("query"),
        "matched_alias": resolved.get("matched_alias"),
        "entity": entity,
        "country_scope": sorted(country_scope),
        "neighborhood_entities": neighborhood_entities,
        "neighborhood_relationships": neighborhood_relationships,
        "related_alerts": related_alerts,
        "related_hazard_forecasts": related_hazards,
        "related_corridors": related_corridors,
        "related_fusion_snapshots": related_fusion,
        "related_correlation_chains": related_chains,
        "related_timeline": related_timeline,
        "operator_history": list(operator_history or []),
        "evidence_summary": {
            "confidence_ratio": round(_safe_float(entity.get("confidence_ratio"), 0.0), 4),
            "entity_count": len(neighborhood_entities),
            "relationship_count": len(neighborhood_relationships),
            "alert_count": len(related_alerts),
            "timeline_count": len(related_timeline),
        },
    }


def build_planetary_entity_neighborhood(
    entity_query: str,
    *,
    world_entities: list[dict[str, Any]],
    world_relationships: list[dict[str, Any]],
    entity_type: str | None = None,
    limit: int = 16,
) -> dict[str, Any] | None:
    profile = build_planetary_entity_profile(
        entity_query,
        world_entities=world_entities,
        world_relationships=world_relationships,
        entity_type=entity_type,
        limit=limit,
    )
    if not profile:
        return None
    return {
        "contract_version": profile.get("contract_version"),
        "generated_at": profile.get("generated_at"),
        "query": profile.get("query"),
        "matched_alias": profile.get("matched_alias"),
        "entity": profile.get("entity"),
        "neighborhood_entities": profile.get("neighborhood_entities") or [],
        "neighborhood_relationships": profile.get("neighborhood_relationships") or [],
    }


def seed_planetary_graph_snapshot(
    country_snapshots: list[dict[str, Any]],
    corridor_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    *,
    alert_events: list[dict[str, Any]] | None = None,
    run_id: str,
    captured_at: str,
    mode: str = "online",
    entity_limit: int = 24,
    relationship_limit: int = 32,
    root: str | Path | None = None,
    persist_db: bool = True,
) -> dict[str, Any]:
    base_entities = build_world_entities(country_snapshots, corridor_snapshots, hazard_forecasts, limit=max(1, entity_limit * 2))
    ingestion_bundle = build_text_graph_enrichment(
        country_snapshots=country_snapshots,
        alert_events=alert_events,
        limit=max(48, entity_limit * 3),
        lookback_days=14,
    )
    extra_entities = [
        *_additional_world_entities(country_snapshots, alert_events),
        *(ingestion_bundle.get("world_entities") or []),
    ]
    merged_entities, alias_map = canonicalize_world_entities([*base_entities, *extra_entities])
    merged_entities = merged_entities[: max(1, int(entity_limit))]
    kept_ids = {str(item.get("entity_id") or "").strip() for item in merged_entities if str(item.get("entity_id") or "").strip()}

    base_relationships = build_world_relationships(country_snapshots, corridor_snapshots, hazard_forecasts, limit=max(1, relationship_limit * 2))
    extra_relationships = [
        *_additional_world_relationships(country_snapshots, alert_events),
        *(ingestion_bundle.get("world_relationships") or []),
    ]
    merged_relationships = [
        row for row in canonicalize_world_relationships([*base_relationships, *extra_relationships], alias_map)
        if str(row.get("source_entity_id") or "").strip() in kept_ids and str(row.get("target_entity_id") or "").strip() in kept_ids
    ][: max(1, int(relationship_limit))]

    persistence = persist_planetary_graph_batch(
        world_entities=merged_entities,
        world_relationships=merged_relationships,
        run_id=run_id,
        captured_at=captured_at,
        mode=mode,
        root=root,
        persist_db=persist_db,
    )
    return {
        **persistence,
        "world_entities": merged_entities,
        "world_relationships": merged_relationships,
    }
