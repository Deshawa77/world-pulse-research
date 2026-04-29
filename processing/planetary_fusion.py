from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database.mongo import db

ROOT = Path(__file__).resolve().parents[1]
FUSION_ROOT = ROOT / "data_lake" / "planetary_intelligence" / "fusion"
COUNTRY_FUSION_ROOT = FUSION_ROOT / "country_snapshots"
COUNTRY_FUSION_HISTORY_DIR = COUNTRY_FUSION_ROOT / "history"
COUNTRY_FUSION_LATEST_JSONL = COUNTRY_FUSION_ROOT / "latest.jsonl"
TIMELINE_ROOT = FUSION_ROOT / "timeline"
TIMELINE_HISTORY_DIR = TIMELINE_ROOT / "history"
TIMELINE_LATEST_JSONL = TIMELINE_ROOT / "latest.jsonl"
CORRELATION_ROOT = FUSION_ROOT / "correlations"
CORRELATION_HISTORY_DIR = CORRELATION_ROOT / "history"
CORRELATION_LATEST_JSONL = CORRELATION_ROOT / "latest.jsonl"
MANIFEST_ROOT = FUSION_ROOT / "manifests"
MANIFEST_HISTORY_DIR = MANIFEST_ROOT / "history"
MANIFEST_LATEST_JSON = MANIFEST_ROOT / "latest.json"

PLANETARY_COUNTRY_FUSION_COLLECTION = "planetary_country_fusion"
PLANETARY_FUSION_TIMELINE_COLLECTION = "planetary_fusion_timeline"
PLANETARY_CORRELATION_CHAIN_COLLECTION = "planetary_correlation_chains"


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
    base = Path(root) if root is not None else FUSION_ROOT
    return {
        "country_latest": base / "country_snapshots" / "latest.jsonl",
        "country_history": base / "country_snapshots" / "history",
        "timeline_latest": base / "timeline" / "latest.jsonl",
        "timeline_history": base / "timeline" / "history",
        "correlation_latest": base / "correlations" / "latest.jsonl",
        "correlation_history": base / "correlations" / "history",
        "manifest_latest": base / "manifests" / "latest.json",
        "manifest_history": base / "manifests" / "history",
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if numeric == numeric else default


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
    return default or datetime.now(timezone.utc).isoformat()


def _freshness_sec(value: Any, default: int = 0) -> int:
    parsed = _parse_iso(value)
    if not parsed:
        return default
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    return "".join(char for char in text if char.isalnum() or char in {"-", "_", ":"}) or "unknown"


def _file_slug(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    return "".join(char for char in text if char.isalnum() or char in {"-", "_"}) or "run"


def _timestamp_sort_key(row: dict[str, Any]) -> float:
    raw = str(row.get("generated_at") or row.get("frame_timestamp") or row.get("timestamp") or "")
    parsed = _parse_iso(raw)
    return parsed.timestamp() if parsed else 0.0


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


def _insert_many(collection_name: str, docs: list[dict[str, Any]]) -> int:
    if not docs:
        return 0
    try:
        result = db[collection_name].insert_many(docs, ordered=False)
        return len(result.inserted_ids)
    except Exception:
        return 0


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return {name: counts[name] for name in sorted(counts.keys())}


def _signal_countries(signal: dict[str, Any]) -> list[str]:
    geography = signal.get("geography") if isinstance(signal.get("geography"), dict) else {}
    countries: list[str] = []
    for key in ("country", "origin", "destination", "from_country", "to_country"):
        value = str(geography.get(key) or "").strip().upper()
        if value and value not in countries and value not in {"GLB", "GLOBAL", "WORLD"}:
            countries.append(value)
    return countries


def _alert_countries(alert: dict[str, Any]) -> list[str]:
    geography = alert.get("geography") if isinstance(alert.get("geography"), dict) else {}
    countries: list[str] = []
    for key in ("country", "origin", "target", "from_country", "to_country"):
        value = str(geography.get(key) or "").strip().upper()
        if value and value not in countries and value not in {"GLB", "GLOBAL", "WORLD"}:
            countries.append(value)
    for item in (alert.get("related_entities_or_regions") or []):
        value = str(item or "").strip().upper()
        if len(value) == 3 and value.isalpha() and value not in countries:
            countries.append(value)
    return countries


def _build_country_indexes(
    corridor_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
    normalized_signals: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    corridors_by_country: dict[str, list[dict[str, Any]]] = {}
    hazards_by_country: dict[str, list[dict[str, Any]]] = {}
    alerts_by_country: dict[str, list[dict[str, Any]]] = {}
    signals_by_country: dict[str, list[dict[str, Any]]] = {}

    for item in corridor_snapshots:
        countries = [
            str((item.get("from_region") or {}).get("country") or "").strip().upper(),
            str((item.get("to_region") or {}).get("country") or "").strip().upper(),
        ]
        for country in [code for code in countries if code]:
            corridors_by_country.setdefault(country, []).append(item)

    for item in hazard_forecasts:
        country = str(item.get("country") or "").strip().upper()
        if country and country not in {"GLB", "GLOBAL", "WORLD"}:
            hazards_by_country.setdefault(country, []).append(item)

    for item in alert_events:
        for country in _alert_countries(item):
            alerts_by_country.setdefault(country, []).append(item)

    for item in normalized_signals:
        for country in _signal_countries(item):
            signals_by_country.setdefault(country, []).append(item)

    return corridors_by_country, hazards_by_country, alerts_by_country, signals_by_country


def _country_set(
    country_snapshots: list[dict[str, Any]],
    corridors_by_country: dict[str, list[dict[str, Any]]],
    hazards_by_country: dict[str, list[dict[str, Any]]],
    alerts_by_country: dict[str, list[dict[str, Any]]],
    signals_by_country: dict[str, list[dict[str, Any]]],
) -> list[str]:
    countries = {
        str(item.get("country") or "").strip().upper()
        for item in country_snapshots
        if str(item.get("country") or "").strip()
    }
    countries.update(corridors_by_country.keys())
    countries.update(hazards_by_country.keys())
    countries.update(alerts_by_country.keys())
    countries.update(signals_by_country.keys())
    return [country for country in sorted(countries) if country and country not in {"GLB", "GLOBAL", "WORLD"}]


def _recommended_action(country: str, state_vector: dict[str, float]) -> str:
    dominant_metric = max(state_vector.items(), key=lambda item: item[1])[0] if state_vector else "behavior_stress"
    if dominant_metric == "hazard_exposure":
        return f"Coordinate disaster response and infrastructure resilience planning for {country}."
    if dominant_metric == "internet_disruption":
        return f"Verify corridor health, shutdown risk, and network abuse telemetry for {country}."
    if dominant_metric == "mobility_pressure":
        return f"Inspect mobility and logistics disruption signals before conditions worsen in {country}."
    if dominant_metric == "economic_pressure":
        return f"Review household, energy, and price pressure signals driving instability in {country}."
    return f"Review behavior and narrative acceleration signals for {country} and coordinate regional monitoring."


def build_country_fusion_snapshots(
    country_snapshots: list[dict[str, Any]],
    corridor_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
    normalized_signals: list[dict[str, Any]],
    *,
    generated_at: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    country_lookup = {
        str(item.get("country") or "").strip().upper(): item
        for item in country_snapshots
        if str(item.get("country") or "").strip()
    }
    corridors_by_country, hazards_by_country, alerts_by_country, signals_by_country = _build_country_indexes(
        corridor_snapshots,
        hazard_forecasts,
        alert_events,
        normalized_signals,
    )
    countries = _country_set(country_snapshots, corridors_by_country, hazards_by_country, alerts_by_country, signals_by_country)
    rows: list[dict[str, Any]] = []

    for country in countries:
        snapshot = country_lookup.get(country) or {}
        signal_scores = snapshot.get("signal_scores") if isinstance(snapshot.get("signal_scores"), dict) else {}
        corridors = corridors_by_country.get(country, [])
        hazards = hazards_by_country.get(country, [])
        alerts = alerts_by_country.get(country, [])
        signals = signals_by_country.get(country, [])

        behavior_stress = max(
            _ratio(snapshot.get("raw_risk_score"), 0.0),
            _ratio(signal_scores.get("direct_behavior_score"), 0.0),
            _ratio(signal_scores.get("contextual_pressure_score"), 0.0),
        )
        mobility_pressure = _mean(
            [
                _ratio(signal_scores.get("mobility_disruption_score"), 0.0),
                _ratio(signal_scores.get("logistics_stress_score"), 0.0),
                _ratio(signal_scores.get("coordination_risk_score"), 0.0),
            ],
            0.0,
        )
        economic_pressure = _mean(
            [
                _ratio(signal_scores.get("household_stress_score"), 0.0),
                _ratio(signal_scores.get("energy_stress_score"), 0.0),
                _ratio(signal_scores.get("fuel_price_pressure"), 0.0),
                _ratio(signal_scores.get("food_price_pressure"), 0.0),
                _ratio(signal_scores.get("labor_stress_score"), 0.0),
                _ratio(signal_scores.get("fx_pressure_score"), 0.0),
                _ratio(signal_scores.get("remittance_stress_score"), 0.0),
            ],
            0.0,
        )
        narrative_pressure = _ratio(signal_scores.get("narrative_velocity_score"), 0.0)
        internet_disruption = max(
            [_ratio(item.get("severity_score"), 0.0) for item in corridors]
            + [
                _ratio(item.get("severity_score"), 0.0)
                for item in alerts
                if str(item.get("alert_type") or "").startswith("internet") or str(item.get("alert_type") or "") == "routing_or_attack_anomaly"
            ]
            + [
                _ratio(item.get("severity_score"), 0.0)
                for item in signals
                if str(item.get("subsystem") or "") == "real_time_internet_map"
            ]
            + [0.0]
        )
        hazard_exposure = max(
            [max(_ratio(item.get("severity_score"), 0.0), _ratio(item.get("likelihood"), 0.0)) for item in hazards]
            + [
                _ratio(item.get("severity_score"), 0.0)
                for item in alerts
                if str(item.get("alert_type") or "").startswith("hazard_")
            ]
            + [
                _ratio(item.get("severity_score"), 0.0)
                for item in signals
                if str(item.get("subsystem") or "") == "global_disaster_early_warning_ai"
            ]
            + [0.0]
        )
        fused_score = _clamp(
            0.32 * behavior_stress
            + 0.20 * hazard_exposure
            + 0.18 * internet_disruption
            + 0.16 * mobility_pressure
            + 0.09 * economic_pressure
            + 0.05 * narrative_pressure,
            0.0,
            1.0,
        )
        confidence_ratio = round(
            _mean(
                [
                    _ratio(snapshot.get("confidence_ratio"), 0.0),
                    *[_ratio(item.get("confidence_ratio"), 0.0) for item in corridors],
                    *[_ratio(item.get("confidence_ratio"), 0.0) for item in hazards],
                    *[_ratio(item.get("confidence_ratio"), 0.0) for item in alerts],
                    *[_ratio(item.get("confidence_ratio"), 0.0) for item in signals],
                ],
                0.0,
            ),
            4,
        )
        freshness_sec = max(
            [
                _safe_int(snapshot.get("freshness_sec"), 0),
                *[_safe_int(item.get("freshness_sec"), _freshness_sec(item.get("generated_at"), 0)) for item in corridors],
                *[_safe_int(item.get("freshness_sec"), _freshness_sec(item.get("generated_at"), 0)) for item in hazards],
                *[_safe_int(item.get("freshness_sec"), _freshness_sec(item.get("generated_at"), 0)) for item in alerts],
                *[_safe_int(item.get("freshness_sec"), _freshness_sec(item.get("generated_at") or item.get("timestamp"), 0)) for item in signals],
            ]
            or [0]
        )
        state_vector = {
            "behavior_stress": round(behavior_stress, 4),
            "hazard_exposure": round(hazard_exposure, 4),
            "internet_disruption": round(internet_disruption, 4),
            "mobility_pressure": round(mobility_pressure, 4),
            "economic_pressure": round(economic_pressure, 4),
            "narrative_pressure": round(narrative_pressure, 4),
        }
        fusion_band = "critical" if fused_score >= 0.75 else "elevated" if fused_score >= 0.55 else "guarded" if fused_score >= 0.35 else "stable"
        rows.append(
            {
                "fusion_id": f"fusion:{country}",
                "country": country,
                "generated_at": generated_at,
                "freshness_sec": freshness_sec,
                "confidence_ratio": confidence_ratio,
                "fused_score": round(fused_score, 4),
                "fusion_band": fusion_band,
                "state_vector": state_vector,
                "subsystem_scores": {
                    "behavior": round(max(behavior_stress, mobility_pressure, economic_pressure, narrative_pressure), 4),
                    "disaster": round(hazard_exposure, 4),
                    "internet": round(internet_disruption, 4),
                },
                "related_alert_ids": [str(item.get("alert_id") or "") for item in alerts if str(item.get("alert_id") or "").strip()],
                "related_hazard_forecasts": [str(item.get("forecast_id") or "") for item in hazards if str(item.get("forecast_id") or "").strip()],
                "related_corridors": [str(item.get("corridor_id") or "") for item in corridors if str(item.get("corridor_id") or "").strip()],
                "signal_count": len(signals),
                "recommended_action": _recommended_action(country, state_vector),
                "provenance_summary": {
                    "country_snapshot_available": bool(snapshot),
                    "hazard_count": len(hazards),
                    "corridor_count": len(corridors),
                    "alert_count": len(alerts),
                    "signal_count": len(signals),
                },
            }
        )

    rows.sort(key=lambda item: (item.get("fused_score") or 0.0, item.get("confidence_ratio") or 0.0), reverse=True)
    return rows[: max(1, int(limit))]


def build_correlation_chains(
    country_fusion_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
    *,
    generated_at: str,
    limit: int = 18,
) -> list[dict[str, Any]]:
    hazards_by_country: dict[str, list[dict[str, Any]]] = {}
    alerts_by_country: dict[str, list[dict[str, Any]]] = {}
    for item in hazard_forecasts:
        country = str(item.get("country") or "").strip().upper()
        if country:
            hazards_by_country.setdefault(country, []).append(item)
    for item in alert_events:
        for country in _alert_countries(item):
            alerts_by_country.setdefault(country, []).append(item)

    chains: list[dict[str, Any]] = []
    for item in country_fusion_snapshots:
        country = str(item.get("country") or "").strip().upper()
        vector = item.get("state_vector") if isinstance(item.get("state_vector"), dict) else {}
        behavior = _ratio(vector.get("behavior_stress"), 0.0)
        mobility = _ratio(vector.get("mobility_pressure"), 0.0)
        internet = _ratio(vector.get("internet_disruption"), 0.0)
        hazard = _ratio(vector.get("hazard_exposure"), 0.0)
        economic = _ratio(vector.get("economic_pressure"), 0.0)
        narrative = _ratio(vector.get("narrative_pressure"), 0.0)
        related_alerts = alerts_by_country.get(country, [])
        related_hazards = hazards_by_country.get(country, [])

        def add_chain(chain_type: str, stages: list[dict[str, Any]], summary: str, recommended_action: str) -> None:
            likelihood = round(_mean([_ratio(stage.get("value"), 0.0) for stage in stages], 0.0), 4)
            chains.append(
                {
                    "chain_id": f"chain:{country}:{_slug(chain_type)}",
                    "chain_type": chain_type,
                    "generated_at": generated_at,
                    "timestamp": str(item.get("generated_at") or generated_at),
                    "country": country,
                    "region": str((related_hazards[0] or {}).get("region") or country) if related_hazards else country,
                    "summary": summary,
                    "recommended_action": recommended_action,
                    "likelihood": likelihood,
                    "confidence_ratio": round(_ratio(item.get("confidence_ratio"), 0.0), 4),
                    "freshness_sec": _safe_int(item.get("freshness_sec"), 0),
                    "stages": stages,
                    "alert_refs": [str(alert.get("alert_id") or "") for alert in related_alerts if str(alert.get("alert_id") or "").strip()],
                    "entity_refs": [f"country:{country}"] + [f"event:{_slug(alert.get('alert_id') or '')}" for alert in related_alerts if str(alert.get("alert_id") or "").strip()],
                }
            )

        if hazard >= 0.35 and mobility >= 0.35 and internet >= 0.30 and behavior >= 0.45:
            add_chain(
                "hazard -> mobility -> internet -> behavior",
                [
                    {"stage": "hazard", "metric": "hazard_exposure", "value": hazard, "subsystem": "global_disaster_early_warning_ai"},
                    {"stage": "mobility", "metric": "mobility_pressure", "value": mobility, "subsystem": "global_human_behavior_intelligence_engine"},
                    {"stage": "internet", "metric": "internet_disruption", "value": internet, "subsystem": "real_time_internet_map"},
                    {"stage": "behavior", "metric": "behavior_stress", "value": behavior, "subsystem": "global_human_behavior_intelligence_engine"},
                ],
                f"{country} shows a multi-system chain from hazard pressure into mobility strain, internet disruption, and elevated behavior stress.",
                f"Coordinate hazard, mobility, and network teams for {country} before the behavior layer accelerates further.",
            )
        if economic >= 0.45 and behavior >= 0.45:
            add_chain(
                "economic -> behavior",
                [
                    {"stage": "economic", "metric": "economic_pressure", "value": economic, "subsystem": "global_human_behavior_intelligence_engine"},
                    {"stage": "behavior", "metric": "behavior_stress", "value": behavior, "subsystem": "global_human_behavior_intelligence_engine"},
                ],
                f"Economic pressure is feeding behavior stress in {country}.",
                f"Review household, energy, and price pressure drivers behind the {country} behavior escalation.",
            )
        if internet >= 0.40 and behavior >= 0.45:
            add_chain(
                "internet -> behavior",
                [
                    {"stage": "internet", "metric": "internet_disruption", "value": internet, "subsystem": "real_time_internet_map"},
                    {"stage": "behavior", "metric": "behavior_stress", "value": behavior, "subsystem": "global_human_behavior_intelligence_engine"},
                    {"stage": "narrative", "metric": "narrative_pressure", "value": narrative, "subsystem": "global_human_behavior_intelligence_engine"},
                ],
                f"Internet disruption appears to be reinforcing behavior and narrative stress in {country}.",
                f"Cross-check shutdown, routing, and narrative signals for {country} and prepare comms escalation paths.",
            )

    chains.sort(key=lambda item: (item.get("likelihood") or 0.0, item.get("confidence_ratio") or 0.0), reverse=True)
    return _dedupe_rows(chains, "chain_id")[: max(1, int(limit))]


def attach_chain_refs(
    country_fusion_snapshots: list[dict[str, Any]],
    correlation_chains: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    chain_ids_by_country: dict[str, list[str]] = {}
    for item in correlation_chains:
        country = str(item.get("country") or "").strip().upper()
        chain_id = str(item.get("chain_id") or "").strip()
        if country and chain_id:
            chain_ids_by_country.setdefault(country, []).append(chain_id)

    enriched: list[dict[str, Any]] = []
    for item in country_fusion_snapshots:
        row = dict(item)
        row["correlation_chain_ids"] = chain_ids_by_country.get(str(item.get("country") or "").strip().upper(), [])
        enriched.append(row)
    return enriched


def build_fusion_timeline(
    country_fusion_snapshots: list[dict[str, Any]],
    correlation_chains: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
    replay_frames: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    global_summary: dict[str, Any],
    *,
    generated_at: str,
    limit: int = 24,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in correlation_chains:
        rows.append(
            {
                "frame_id": str(item.get("chain_id") or ""),
                "generated_at": generated_at,
                "frame_timestamp": str(item.get("timestamp") or item.get("generated_at") or generated_at),
                "frame_type": "correlation_chain",
                "summary": str(item.get("summary") or ""),
                "country": str(item.get("country") or ""),
                "confidence_ratio": round(_ratio(item.get("confidence_ratio"), 0.0), 4),
                "severity_score": round(_ratio(item.get("likelihood"), 0.0), 4),
                "subsystems": [str(stage.get("subsystem") or "") for stage in (item.get("stages") or []) if str(stage.get("subsystem") or "").strip()],
                "snapshot_refs": [f"fusion:{item.get('country')}"] if str(item.get("country") or "").strip() else [],
                "alert_refs": list(item.get("alert_refs") or []),
                "chain_refs": [str(item.get("chain_id") or "")],
            }
        )

    for item in alert_events:
        rows.append(
            {
                "frame_id": f"alert:{_slug(item.get('alert_id') or '')}",
                "generated_at": generated_at,
                "frame_timestamp": str(item.get("generated_at") or generated_at),
                "frame_type": "alert_event",
                "summary": str(item.get("summary") or ""),
                "country": "|".join(_alert_countries(item)),
                "confidence_ratio": round(_ratio(item.get("confidence_ratio"), 0.0), 4),
                "severity_score": round(_ratio(item.get("severity_score"), 0.0), 4),
                "subsystems": [str(ref.get("subsystem") or "") for ref in (item.get("provenance_refs") or []) if isinstance(ref, dict)],
                "snapshot_refs": [str(alert_ref) for alert_ref in (item.get("related_entities_or_regions") or []) if str(alert_ref or "").strip()],
                "alert_refs": [str(item.get("alert_id") or "")],
                "chain_refs": [],
            }
        )

    for item in replay_frames:
        rows.append(
            {
                "frame_id": str(item.get("frame_id") or item.get("run_id") or item.get("frame_timestamp") or generated_at),
                "generated_at": generated_at,
                "frame_timestamp": str(item.get("frame_timestamp") or item.get("generated_at") or generated_at),
                "frame_type": str(item.get("frame_type") or "internet_replay"),
                "summary": f"Internet replay frame with {len(item.get('alert_refs') or [])} alerts and {len(item.get('snapshot_refs') or [])} snapshot refs.",
                "country": "",
                "confidence_ratio": round(_ratio((item.get("confidence_summary") or {}).get("country_avg_confidence"), 0.0), 4),
                "severity_score": round(_ratio(global_summary.get("infrastructure_fragility_score"), 0.0), 4),
                "subsystems": ["real_time_internet_map"],
                "snapshot_refs": list(item.get("snapshot_refs") or []),
                "alert_refs": list(item.get("alert_refs") or []),
                "chain_refs": [],
            }
        )

    for item in hazard_forecasts:
        rows.append(
            {
                "frame_id": f"forecast:{_slug(item.get('forecast_id') or '')}",
                "generated_at": generated_at,
                "frame_timestamp": str(item.get("generated_at") or generated_at),
                "frame_type": "hazard_forecast",
                "summary": f"{str(item.get('hazard_type') or 'Hazard').capitalize()} pressure in {item.get('region') or item.get('country') or 'global' }.",
                "country": str(item.get("country") or ""),
                "confidence_ratio": round(_ratio(item.get("confidence_ratio"), 0.0), 4),
                "severity_score": round(max(_ratio(item.get("severity_score"), 0.0), _ratio(item.get("likelihood"), 0.0)), 4),
                "subsystems": ["global_disaster_early_warning_ai"],
                "snapshot_refs": [str(item.get("forecast_id") or "")],
                "alert_refs": [],
                "chain_refs": [],
            }
        )

    for item in country_fusion_snapshots[: min(10, len(country_fusion_snapshots))]:
        rows.append(
            {
                "frame_id": str(item.get("fusion_id") or ""),
                "generated_at": generated_at,
                "frame_timestamp": str(item.get("generated_at") or generated_at),
                "frame_type": "country_fusion",
                "summary": f"{item.get('country')} fused score {round((_safe_float(item.get('fused_score'), 0.0) * 100), 1)}.",
                "country": str(item.get("country") or ""),
                "confidence_ratio": round(_ratio(item.get("confidence_ratio"), 0.0), 4),
                "severity_score": round(_ratio(item.get("fused_score"), 0.0), 4),
                "subsystems": [name for name, value in (item.get("subsystem_scores") or {}).items() if _safe_float(value, 0.0) > 0.0],
                "snapshot_refs": [str(item.get("fusion_id") or "")],
                "alert_refs": list(item.get("related_alert_ids") or []),
                "chain_refs": list(item.get("correlation_chain_ids") or []),
            }
        )

    rows.sort(key=_timestamp_sort_key, reverse=True)
    return _dedupe_rows(rows, "frame_id")[: max(1, int(limit))]


def persist_planetary_fusion_batch(
    *,
    country_fusion_snapshots: list[dict[str, Any]],
    fusion_timeline: list[dict[str, Any]],
    correlation_chains: list[dict[str, Any]],
    run_id: str,
    captured_at: str,
    mode: str = "online",
    root: str | Path | None = None,
    persist_db: bool = True,
) -> dict[str, Any]:
    paths = _paths(root)
    country_rows = [row for row in country_fusion_snapshots if isinstance(row, dict)]
    timeline_rows = [row for row in fusion_timeline if isinstance(row, dict)]
    chain_rows = [row for row in correlation_chains if isinstance(row, dict)]
    safe_run_id = _file_slug(run_id)

    country_history_path = paths["country_history"] / f"fusion_{safe_run_id}.jsonl"
    timeline_history_path = paths["timeline_history"] / f"fusion_{safe_run_id}.jsonl"
    correlation_history_path = paths["correlation_history"] / f"fusion_{safe_run_id}.jsonl"
    manifest_history_path = paths["manifest_history"] / f"fusion_{safe_run_id}.json"

    _write_jsonl(paths["country_latest"], country_rows)
    _write_jsonl(country_history_path, country_rows)
    _write_jsonl(paths["timeline_latest"], timeline_rows)
    _write_jsonl(timeline_history_path, timeline_rows)
    _write_jsonl(paths["correlation_latest"], chain_rows)
    _write_jsonl(correlation_history_path, chain_rows)

    inserted_country = _insert_many(PLANETARY_COUNTRY_FUSION_COLLECTION, country_rows) if persist_db else 0
    inserted_timeline = _insert_many(PLANETARY_FUSION_TIMELINE_COLLECTION, timeline_rows) if persist_db else 0
    inserted_chains = _insert_many(PLANETARY_CORRELATION_CHAIN_COLLECTION, chain_rows) if persist_db else 0

    manifest = {
        "captured_at": captured_at,
        "run_id": run_id,
        "mode": mode,
        "contract_version": "phase-0.3",
        "platform_scope": "planetary_fusion",
        "country_fusion_count": len(country_rows),
        "timeline_frame_count": len(timeline_rows),
        "correlation_chain_count": len(chain_rows),
        "fusion_bands": _counts(country_rows, "fusion_band"),
        "chain_types": _counts(chain_rows, "chain_type"),
        "frame_types": _counts(timeline_rows, "frame_type"),
        "country_latest_path": str(paths["country_latest"]),
        "timeline_latest_path": str(paths["timeline_latest"]),
        "correlation_latest_path": str(paths["correlation_latest"]),
        "mongo_inserted": {
            "country_fusion_snapshots": inserted_country,
            "fusion_timeline": inserted_timeline,
            "correlation_chains": inserted_chains,
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


def load_recent_country_fusion_snapshots(
    *,
    limit: int = 24,
    root: str | Path | None = None,
    country: str | None = None,
) -> list[dict[str, Any]]:
    paths = _paths(root)
    rows = _load_rows_from_files(paths["country_latest"], paths["country_history"], limit=limit)
    if not rows and root is None:
        rows = _load_rows_from_mongo(PLANETARY_COUNTRY_FUSION_COLLECTION, limit=limit)
    country_filter = str(country or "").strip().upper()
    filtered = [row for row in rows if not country_filter or str(row.get("country") or "").strip().upper() == country_filter]
    filtered.sort(key=_timestamp_sort_key, reverse=True)
    return _dedupe_rows(filtered, "fusion_id")[: max(1, int(limit))]


def load_recent_fusion_timeline(
    *,
    limit: int = 32,
    root: str | Path | None = None,
    country: str | None = None,
    frame_type: str | None = None,
) -> list[dict[str, Any]]:
    paths = _paths(root)
    rows = _load_rows_from_files(paths["timeline_latest"], paths["timeline_history"], limit=limit)
    if not rows and root is None:
        rows = _load_rows_from_mongo(PLANETARY_FUSION_TIMELINE_COLLECTION, limit=limit)
    country_filter = str(country or "").strip().upper()
    type_filter = str(frame_type or "").strip().lower()
    filtered = []
    for row in rows:
        if country_filter and country_filter not in str(row.get("country") or "").upper():
            continue
        if type_filter and str(row.get("frame_type") or "").strip().lower() != type_filter:
            continue
        filtered.append(row)
    filtered.sort(key=_timestamp_sort_key, reverse=True)
    return _dedupe_rows(filtered, "frame_id")[: max(1, int(limit))]


def load_recent_correlation_chains(
    *,
    limit: int = 24,
    root: str | Path | None = None,
    country: str | None = None,
    chain_type: str | None = None,
) -> list[dict[str, Any]]:
    paths = _paths(root)
    rows = _load_rows_from_files(paths["correlation_latest"], paths["correlation_history"], limit=limit)
    if not rows and root is None:
        rows = _load_rows_from_mongo(PLANETARY_CORRELATION_CHAIN_COLLECTION, limit=limit)
    country_filter = str(country or "").strip().upper()
    chain_filter = str(chain_type or "").strip().lower()
    filtered = []
    for row in rows:
        if country_filter and str(row.get("country") or "").strip().upper() != country_filter:
            continue
        if chain_filter and str(row.get("chain_type") or "").strip().lower() != chain_filter:
            continue
        filtered.append(row)
    filtered.sort(key=_timestamp_sort_key, reverse=True)
    return _dedupe_rows(filtered, "chain_id")[: max(1, int(limit))]


def seed_planetary_fusion_snapshot(
    country_snapshots: list[dict[str, Any]],
    corridor_snapshots: list[dict[str, Any]],
    hazard_forecasts: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
    replay_frames: list[dict[str, Any]],
    global_summary: dict[str, Any],
    normalized_signals: list[dict[str, Any]],
    *,
    run_id: str,
    captured_at: str,
    mode: str = "online",
    country_limit: int = 20,
    timeline_limit: int = 24,
    chain_limit: int = 18,
    root: str | Path | None = None,
    persist_db: bool = True,
) -> dict[str, Any]:
    country_fusion_snapshots = build_country_fusion_snapshots(
        country_snapshots,
        corridor_snapshots,
        hazard_forecasts,
        alert_events,
        normalized_signals,
        generated_at=captured_at,
        limit=country_limit,
    )
    correlation_chains = build_correlation_chains(
        country_fusion_snapshots,
        hazard_forecasts,
        alert_events,
        generated_at=captured_at,
        limit=chain_limit,
    )
    country_fusion_snapshots = attach_chain_refs(country_fusion_snapshots, correlation_chains)
    fusion_timeline = build_fusion_timeline(
        country_fusion_snapshots,
        correlation_chains,
        alert_events,
        replay_frames,
        hazard_forecasts,
        global_summary,
        generated_at=captured_at,
        limit=timeline_limit,
    )
    persistence = persist_planetary_fusion_batch(
        country_fusion_snapshots=country_fusion_snapshots,
        fusion_timeline=fusion_timeline,
        correlation_chains=correlation_chains,
        run_id=run_id,
        captured_at=captured_at,
        mode=mode,
        root=root,
        persist_db=persist_db,
    )
    return {
        **persistence,
        "country_fusion_snapshots": country_fusion_snapshots,
        "fusion_timeline": fusion_timeline,
        "correlation_chains": correlation_chains,
    }
