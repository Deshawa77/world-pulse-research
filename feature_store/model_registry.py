# backend/model_registry.py
import os
import json
import shutil
from datetime import datetime

REGISTRY_PATH = "./models/registry"
os.makedirs(REGISTRY_PATH, exist_ok=True)

PRODUCTION_PATH = os.path.join(REGISTRY_PATH, "production")
STAGING_PATH = os.path.join(REGISTRY_PATH, "staging")
ARCHIVED_PATH = os.path.join(REGISTRY_PATH, "archived")
METADATA_FILE = os.path.join(REGISTRY_PATH, "metadata.json")

# Ensure directories exist
for path in [PRODUCTION_PATH, STAGING_PATH, ARCHIVED_PATH]:
    os.makedirs(path, exist_ok=True)

# -------------------------------
# Load or initialize metadata
# -------------------------------
if os.path.exists(METADATA_FILE):
    try:
        with open(METADATA_FILE, "r", encoding="utf-8-sig") as f:
            metadata = json.load(f)
    except json.JSONDecodeError:
        metadata = {}
else:
    metadata = {}

# -------------------------------
# Register Model
# -------------------------------
def register_model(model_file: str, version: str, metrics: dict, stage="staging"):
    """Register a new ML model."""
    if stage not in ["staging", "production", "archived"]:
        raise ValueError("Stage must be staging, production, or archived")

    # Destination path
    if stage == "staging":
        dest_path = os.path.join(STAGING_PATH, f"{version}.pkl")
    elif stage == "production":
        dest_path = os.path.join(PRODUCTION_PATH, f"{version}.pkl")
    else:
        dest_path = os.path.join(ARCHIVED_PATH, f"{version}.pkl")

    # Copy model file
    shutil.copy2(model_file, dest_path)

    # Update metadata
    metadata[version] = {
        "file": dest_path,
        "stage": stage,
        "metrics": metrics,
        "registered_at": datetime.utcnow().isoformat()
    }

    with open(METADATA_FILE, "w", encoding="utf-8-sig") as f:
        json.dump(metadata, f, indent=2)

    print(f"✅ Model {version} registered in {stage} stage.")

# -------------------------------
# Promote Model (FIXED)
# -------------------------------
def promote_model(version: str):
    """Move a model from staging to production."""
    if version not in metadata:
        raise ValueError(f"Version {version} not found in registry")

    src_path = metadata[version]["file"]
    dest_path = os.path.join(PRODUCTION_PATH, f"{version}.pkl")

    # Copy to production
    shutil.copy2(src_path, dest_path)

    # 🔥 FIX: update metadata file path + stage
    metadata[version]["file"] = dest_path
    metadata[version]["stage"] = "production"
    metadata[version]["promoted_at"] = datetime.utcnow().isoformat()

    with open(METADATA_FILE, "w", encoding="utf-8-sig") as f:
        json.dump(metadata, f, indent=2)

    print(f"🚀 Model {version} promoted to production!")

# -------------------------------
# Get Production Model
# -------------------------------
def get_production_model():
    """Return path to production model."""
    for version, info in metadata.items():
        if info.get("stage") == "production":
            return info.get("file")
    return None
