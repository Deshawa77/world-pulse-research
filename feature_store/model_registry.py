# backend/model_registry.py
import os
import json
import shutil
from datetime import datetime

# ==========================================================
# Paths
# ==========================================================

REGISTRY_PATH = "./models/registry"
PRODUCTION_PATH = os.path.join(REGISTRY_PATH, "production")
STAGING_PATH = os.path.join(REGISTRY_PATH, "staging")
ARCHIVED_PATH = os.path.join(REGISTRY_PATH, "archived")

METADATA_FILE = os.path.join(REGISTRY_PATH, "metadata.json")
AUDIT_FILE = os.path.join(REGISTRY_PATH, "audit_log.json")

# Ensure directories exist
for path in [REGISTRY_PATH, PRODUCTION_PATH, STAGING_PATH, ARCHIVED_PATH]:
    os.makedirs(path, exist_ok=True)

# ==========================================================
# Metadata Handling
# ==========================================================

def load_metadata():
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_metadata(metadata):
    with open(METADATA_FILE, "w", encoding="utf-8-sig") as f:
        json.dump(metadata, f, indent=2)

metadata = load_metadata()

# ==========================================================
# Audit Logging
# ==========================================================

def log_event(event_type: str, version: str):
    entry = {
        "event": event_type,
        "version": version,
        "timestamp": datetime.utcnow().isoformat()
    }

    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE, "r") as f:
                logs = json.load(f)
        except json.JSONDecodeError:
            logs = []
    else:
        logs = []

    logs.append(entry)

    with open(AUDIT_FILE, "w") as f:
        json.dump(logs, f, indent=2)

# ==========================================================
# Register Model
# ==========================================================

def register_model(model_file: str, version: str, metrics: dict, stage="staging"):
    """Register a new ML model."""
    
    if version in metadata:
        raise ValueError(f"Version {version} already exists in registry")

    if stage not in ["staging", "production", "archived"]:
        raise ValueError("Stage must be staging, production, or archived")

    # Destination path
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
        "registered_at": datetime.utcnow().isoformat()
    }

    save_metadata(metadata)
    log_event("registered", version)

    print(f"✅ Model {version} registered in {stage} stage.")

# ==========================================================
# Promote Model (Single Production + Auto Archive)
# ==========================================================

def promote_model(version: str):
    """Promote a model to production. Automatically archives existing production model."""
    
    if version not in metadata:
        raise ValueError(f"Version {version} not found in registry")

    # Archive current production model (if exists)
    for v, info in metadata.items():
        if info.get("stage") == "production":
            old_path = info["file"]
            archived_path = os.path.join(ARCHIVED_PATH, f"{v}.pkl")

            if os.path.exists(old_path):
                shutil.move(old_path, archived_path)

            metadata[v]["file"] = archived_path
            metadata[v]["stage"] = "archived"
            metadata[v]["archived_at"] = datetime.utcnow().isoformat()

            log_event("archived", v)

    # Promote selected version
    src_path = metadata[version]["file"]
    dest_path = os.path.join(PRODUCTION_PATH, f"{version}.pkl")

    shutil.copy2(src_path, dest_path)

    metadata[version]["file"] = dest_path
    metadata[version]["stage"] = "production"
    metadata[version]["promoted_at"] = datetime.utcnow().isoformat()

    save_metadata(metadata)
    log_event("promoted", version)

    print(f"🚀 Model {version} promoted to production!")

# ==========================================================
# Rollback
# ==========================================================

def rollback_to_version(version: str):
    """Rollback production to a previously archived model."""
    
    if version not in metadata:
        raise ValueError(f"Version {version} not found")

    if metadata[version]["stage"] != "archived":
        raise ValueError("Rollback allowed only for archived models")

    promote_model(version)
    log_event("rollback", version)

    print(f"⏪ Rolled back to version {version}")

# ==========================================================
# Get Production Model
# ==========================================================

def get_production_model():
    """Return path to current production model."""
    
    for version, info in metadata.items():
        if info.get("stage") == "production":
            return info.get("file")
    return None

# ==========================================================
# Optional Helper: List All Models
# ==========================================================

def list_models():
    """Return metadata for all registered models."""
    return metadata
