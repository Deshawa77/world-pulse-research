from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_MANIFEST_ROOT = ROOT / "data_lake" / "disasters" / "manifests"
FEATURE_STORE_ROOT = ROOT / "feature_store" / "disasters"
FEATURES_PATH = FEATURE_STORE_ROOT / "features.parquet"
FEATURES_METADATA_PATH = FEATURE_STORE_ROOT / "metadata.json"
FEATURES_SCHEMA_PATH = FEATURE_STORE_ROOT / "schema.json"
FEATURES_LATEST_JSON = FEATURE_STORE_ROOT / "latest.json"
CYCLONE_TRACKER_ROOT = FEATURE_STORE_ROOT / "cyclone_tracker"
CYCLONE_TRACKER_JSON = CYCLONE_TRACKER_ROOT / "latest.json"
CYCLONE_TRACKER_PARQUET = CYCLONE_TRACKER_ROOT / "tracks.parquet"
SEISMIC_ANOMALY_ROOT = FEATURE_STORE_ROOT / "seismic_anomaly"
SEISMIC_ANOMALY_JSON = SEISMIC_ANOMALY_ROOT / "latest.json"
SEISMIC_ANOMALY_PARQUET = SEISMIC_ANOMALY_ROOT / "anomalies.parquet"
MONITORING_ROOT = ROOT / "monitoring" / "disasters"
STREAMING_ROOT = MONITORING_ROOT / "stream"
STREAMING_LATEST_JSON = STREAMING_ROOT / "latest.json"
STREAMING_HISTORY_DIR = STREAMING_ROOT / "history"
BACKTEST_ROOT = MONITORING_ROOT / "backtests"
BACKTEST_LATEST_JSON = BACKTEST_ROOT / "latest.json"
BACKTEST_HISTORY_DIR = BACKTEST_ROOT / "history"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")


def _fallback_table_path(path: Path) -> Path:
    return path.with_suffix(".csv")


def _write_dataframe_table(df: pd.DataFrame, path: Path) -> dict[str, Any]:
    _ensure_dir(path.parent)
    try:
        df.to_parquet(path, index=False)
        return {"path": str(path), "format": "parquet"}
    except (ImportError, ValueError):
        fallback_path = _fallback_table_path(path)
        df.to_csv(fallback_path, index=False)
        return {"path": str(fallback_path), "format": "csv"}


def load_json_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _rows_time_bounds(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    timestamps = sorted(str(row.get("timestamp") or "") for row in rows if str(row.get("timestamp") or "").strip())
    return {
        "start_timestamp": timestamps[0] if timestamps else None,
        "end_timestamp": timestamps[-1] if timestamps else None,
    }


def persist_disaster_raw_manifests(
    run_ts: str,
    by_bucket: dict[str, list[dict[str, Any]]],
    written_files: dict[str, str],
    *,
    inserted_records: int,
) -> dict[str, Any]:
    _ensure_dir(RAW_MANIFEST_ROOT)
    bucket_summaries: dict[str, Any] = {}
    total_records = 0

    for bucket, rows in by_bucket.items():
        total_records += len(rows)
        countries = sorted({str(row.get("country") or "GLB") for row in rows if str(row.get("country") or "").strip()})
        event_types = sorted({str(row.get("event_type") or "unknown") for row in rows if str(row.get("event_type") or "").strip()})
        source_families = sorted({source for row in rows for source in _string_list(row.get("signal_sources"))})
        sources = sorted({str(row.get("source") or "") for row in rows if str(row.get("source") or "").strip()})
        summary = {
            "bucket": bucket,
            "records": len(rows),
            "path": written_files.get(bucket),
            **_rows_time_bounds(rows),
            "countries": countries,
            "event_types": event_types,
            "source_families": source_families,
            "sources": sources,
        }
        bucket_summaries[bucket] = summary
        if rows:
            _write_json(RAW_MANIFEST_ROOT / f"latest_{bucket}.json", summary)

    manifest = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "run_id": f"disaster_raw_{run_ts}",
        "total_records": total_records,
        "inserted_records": inserted_records,
        "buckets": bucket_summaries,
    }
    manifest_path = RAW_MANIFEST_ROOT / f"batch_{run_ts}.json"
    _write_json(manifest_path, manifest)
    _write_json(RAW_MANIFEST_ROOT / "latest.json", manifest)
    return {"manifest_path": str(manifest_path), "bucket_summaries": bucket_summaries}


def _flatten_feature_bundle(bundle: dict[str, Any], *, country: str | None = None, context: str = "runtime") -> dict[str, Any]:
    feature_values = bundle.get("feature_values") if isinstance(bundle.get("feature_values"), dict) else {}
    signal_sources = _string_list(bundle.get("signal_sources"))
    explainers = _string_list(bundle.get("top_contributing_signals"))
    row = {
        "event_type": str(bundle.get("event_type") or "unknown"),
        "country": str(country or bundle.get("country") or "GLB"),
        "lead_time_hours": int(bundle.get("lead_time_hours") or 0),
        "updated_at": str(bundle.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        "context": context,
        "signal_sources": json.dumps(signal_sources),
        "signal_source_count": len(signal_sources),
        "top_contributing_signals": json.dumps(explainers),
        "recommended_action": str(bundle.get("recommended_action") or ""),
    }
    for key, value in feature_values.items():
        row[str(key)] = value
    return row


def _write_feature_snapshot(df: pd.DataFrame, root: Path, name: str, extra_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    _ensure_dir(root)
    parquet_path = root / "features.parquet"
    metadata_path = root / "metadata.json"
    schema_path = root / "schema.json"
    latest_json = root / "latest.json"
    table_snapshot = _write_dataframe_table(df, parquet_path)
    metadata = {
        "name": name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(df)),
        "columns": list(df.columns),
        "table_path": table_snapshot["path"],
        "table_format": table_snapshot["format"],
    }
    if extra_meta:
        metadata.update(extra_meta)
    _write_json(metadata_path, metadata)
    _write_json(schema_path, {"schema": {col: str(dtype) for col, dtype in df.dtypes.items()}})
    _write_json(latest_json, df.to_dict(orient="records"))
    return table_snapshot


def persist_disaster_feature_store(
    bundles: list[dict[str, Any]],
    *,
    country: str | None = None,
    context: str = "disaster_feature_builder",
) -> dict[str, Any]:
    rows = [_flatten_feature_bundle(bundle, country=country, context=context) for bundle in bundles]
    if not rows:
        return {"status": "empty", "rows": 0}
    df = pd.DataFrame(rows)
    root_snapshot = _write_feature_snapshot(
        df,
        FEATURE_STORE_ROOT,
        "disasters",
        {"country": country or "GLB", "hazards": sorted(df["event_type"].dropna().unique().tolist())},
    )
    for hazard, hazard_df in df.groupby("event_type"):
        _write_feature_snapshot(
            hazard_df.reset_index(drop=True),
            FEATURE_STORE_ROOT / str(hazard),
            f"disasters_{hazard}",
            {"country": country or "GLB", "event_type": hazard},
        )
    return {
        "status": "ok",
        "rows": len(df),
        "path": root_snapshot["path"],
        "format": root_snapshot["format"],
    }


def persist_cyclone_tracker_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_dir(CYCLONE_TRACKER_ROOT)
    _write_json(CYCLONE_TRACKER_JSON, payload)
    tracks = payload.get("storm_tracks") if isinstance(payload.get("storm_tracks"), list) else []
    table_snapshot = {"path": str(CYCLONE_TRACKER_PARQUET), "format": "parquet"}
    if tracks:
        flattened_tracks = []
        for track in tracks:
            row = {**track}
            if isinstance(row.get("track_points"), list):
                row["track_points"] = json.dumps(row.get("track_points"), default=_json_default)
            flattened_tracks.append(row)
        table_snapshot = _write_dataframe_table(pd.DataFrame(flattened_tracks), CYCLONE_TRACKER_PARQUET)
    return {
        "status": "ok",
        "json_path": str(CYCLONE_TRACKER_JSON),
        "track_path": table_snapshot["path"],
        "track_format": table_snapshot["format"],
        "track_count": len(tracks),
    }

def persist_seismic_anomaly_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_dir(SEISMIC_ANOMALY_ROOT)
    _write_json(SEISMIC_ANOMALY_JSON, payload)
    anomalies = payload.get("anomaly_clusters") if isinstance(payload.get("anomaly_clusters"), list) else []
    table_snapshot = {"path": str(SEISMIC_ANOMALY_PARQUET), "format": "parquet"}
    if anomalies:
        flattened = []
        for row in anomalies:
            item = {**row}
            if isinstance(item.get("history"), dict):
                item["history"] = json.dumps(item.get("history"), default=_json_default)
            if isinstance(item.get("trend_points"), list):
                item["trend_points"] = json.dumps(item.get("trend_points"), default=_json_default)
            flattened.append(item)
        table_snapshot = _write_dataframe_table(pd.DataFrame(flattened), SEISMIC_ANOMALY_PARQUET)
    return {
        "status": "ok",
        "json_path": str(SEISMIC_ANOMALY_JSON),
        "anomaly_path": table_snapshot["path"],
        "anomaly_format": table_snapshot["format"],
        "cluster_count": len(anomalies),
    }


def persist_disaster_stream_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_dir(STREAMING_HISTORY_DIR)
    captured_at = str(payload.get("captured_at") or datetime.now(timezone.utc).isoformat())
    run_id = str(payload.get("run_id") or captured_at.replace(":", "").replace("-", ""))
    latest_path = STREAMING_LATEST_JSON
    history_path = STREAMING_HISTORY_DIR / f"{run_id}.json"
    _write_json(latest_path, payload)
    _write_json(history_path, payload)
    return {"status": "ok", "latest_path": str(latest_path), "history_path": str(history_path)}


def persist_disaster_backtest_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_dir(BACKTEST_HISTORY_DIR)
    captured_at = str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat())
    run_id = str(payload.get("run_id") or captured_at.replace(":", "").replace("-", ""))
    latest_path = BACKTEST_LATEST_JSON
    history_path = BACKTEST_HISTORY_DIR / f"{run_id}.json"
    _write_json(latest_path, payload)
    _write_json(history_path, payload)
    return {"status": "ok", "latest_path": str(latest_path), "history_path": str(history_path)}

