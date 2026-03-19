# backend/model_registry.py

import os
import json
import shutil
from datetime import datetime
from typing import Optional, Dict

# ==========================================================
# Paths
# ==========================================================

REGISTRY_PATH = "./models/registry"
PRODUCTION_PATH = os.path.join(REGISTRY_PATH, "production")
STAGING_PATH = os.path.join(REGISTRY_PATH, "staging")
ARCHIVED_PATH = os.path.join(REGISTRY_PATH, "archived")

METADATA_FILE = os.path.join(REGISTRY_PATH, "metadata.json")
AUDIT_FILE = os.path.join(REGISTRY_PATH, "audit_log.json")

for path in [REGISTRY_PATH, PRODUCTION_PATH, STAGING_PATH, ARCHIVED_PATH]:
    os.makedirs(path, exist_ok=True)

# ==========================================================
# Metadata Handling (Always Reload Fresh)
# ==========================================================

def load_metadata() -> Dict:
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_metadata(metadata: Dict):
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

# ==========================================================
# Audit Logging
# ==========================================================

def log_event(event_type: str, version: str, extra: Optional[Dict] = None):
    entry = {
        "event": event_type,
        "version": version,
        "timestamp": datetime.utcnow().isoformat()
    }

    if extra:
        entry.update(extra)

    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except json.JSONDecodeError:
            logs = []
    else:
        logs = []

    logs.append(entry)

    with open(AUDIT_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)

# ==========================================================
# Register Model
# ==========================================================

def register_model(model_file: str, version: str, metrics: dict, stage="staging", extra_metadata: Optional[Dict] = None):
    metadata = load_metadata()

    if version in metadata:
        raise ValueError(f"Version '{version}' already exists")

    if stage not in ["staging", "production", "archived"]:
        raise ValueError("Stage must be staging, production, or archived")

    # Determine destination
    if stage == "staging":
        dest_path = os.path.join(STAGING_PATH, f"{version}.pkl")
    elif stage == "production":
        dest_path = os.path.join(PRODUCTION_PATH, f"{version}.pkl")
    else:
        dest_path = os.path.join(ARCHIVED_PATH, f"{version}.pkl")

    shutil.copy2(model_file, dest_path)

    metadata[version] = {
        "file": dest_path,
        "stage": stage,
        "metrics": metrics,
        "registered_at": datetime.utcnow().isoformat(),
        "promoted_at": None,
        "archived_at": None,
        "rolled_back_from": None
    }
    if extra_metadata:
        metadata[version].update(extra_metadata)

    save_metadata(metadata)
    log_event("registered", version)

    print(f"Model {version} registered in {stage}")

# ==========================================================
# Promote Model
# ==========================================================

def promote_model(version: str):
    metadata = load_metadata()

    if version not in metadata:
        raise ValueError(f"Version '{version}' not found")

    current_production = None

    # Archive existing production
    for v, info in metadata.items():
        if info.get("stage") == "production":
            current_production = v
            old_path = info["file"]
            archived_path = os.path.join(ARCHIVED_PATH, f"{v}.pkl")

            if os.path.exists(old_path):
                shutil.move(old_path, archived_path)

            metadata[v]["file"] = archived_path
            metadata[v]["stage"] = "archived"
            metadata[v]["archived_at"] = datetime.utcnow().isoformat()

            log_event("archived", v)

    # Promote selected model (move instead of copy)
    src_path = metadata[version]["file"]
    dest_path = os.path.join(PRODUCTION_PATH, f"{version}.pkl")

    if os.path.abspath(src_path) != os.path.abspath(dest_path):
        shutil.move(src_path, dest_path)

    metadata[version]["file"] = dest_path
    metadata[version]["stage"] = "production"
    metadata[version]["promoted_at"] = datetime.utcnow().isoformat()
    metadata[version]["rolled_back_from"] = None

    save_metadata(metadata)
    log_event("promoted", version, {"previous_production": current_production})

    print(f"Model {version} is now PRODUCTION")

# ==========================================================
# Rollback
# ==========================================================

def rollback_to_version(version: str):
    metadata = load_metadata()

    if version not in metadata:
        raise ValueError(f"Version '{version}' not found")

    if metadata[version]["stage"] != "archived":
        raise ValueError("Rollback allowed only for archived models")

    # Get current production
    current_prod = None
    for v, info in metadata.items():
        if info.get("stage") == "production":
            current_prod = v
            break

    promote_model(version)

    metadata = load_metadata()
    metadata[version]["rolled_back_from"] = current_prod

    save_metadata(metadata)
    log_event("rollback", version, {"from": current_prod})

    print(f"Rolled back to {version}")

# ==========================================================
# Get Production Model
# ==========================================================

def get_production_model() -> Optional[str]:
    metadata = load_metadata()
    for version, info in metadata.items():
        if info.get("stage") == "production":
            return info.get("file")
    return None

def get_production_metadata() -> Optional[Dict]:
    metadata = load_metadata()
    for version, info in metadata.items():
        if info.get("stage") == "production":
            return {version: info}
    return None

# ==========================================================
# List All Models
# ==========================================================

def list_models() -> Dict:
    return load_metadata()
