import json, os
from datetime import datetime
from .config import REGISTRY_PATH, VERSION_PATH

class FeatureRegistry:

    def __init__(self):
        if not os.path.exists(REGISTRY_PATH):
            with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump({"versions": []}, f)

    def register_version(self, version_name, description):
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            reg = json.load(f)

        version_info = {
            "version": version_name,
            "created_at": datetime.utcnow().isoformat(),
            "description": description
        }

        reg["versions"].append(version_info)

        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)

        os.makedirs(os.path.join(VERSION_PATH, version_name), exist_ok=True)

    def list_versions(self):
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
