import os
import joblib
from feature_store.model_registry import get_production_model, register_model, promote_model, list_models

# Local model files
LOCAL_MODELS = {
    "gb_model": "./models/gb_model.pkl",
    "logistic_model": "./models/logistic_model.pkl",
    "rf_model": "./models/rf_model.pkl"
}

def load_all_models():
    """
    Loads all models, auto-registering missing ones. 
    Only the main GB model is promoted to production; others stay in staging.
    Returns a dictionary: {"model_name": model_object}.
    """
    loaded_models = {}
    registry_metadata = list_models()  # Load registry info once

    for name, path in LOCAL_MODELS.items():
        # Check if this model version is already in the registry
        found_version = None
        for version, info in registry_metadata.items():
            if name in version:
                found_version = version
                break

        # Auto-register if not found
        if not found_version:
            if os.path.exists(path):
                version = f"auto_{name}"
                try:
                    stage = "production" if name == "gb_model" else "staging"
                    register_model(path, version=version, metrics={"accuracy": 0.8}, stage=stage)
                    if stage == "production":
                        promote_model(version)
                    found_version = version
                    print(f"⚡ Auto-registered {name} in {stage}")
                except Exception as e:
                    print(f"❌ Failed to register {name}: {e}")
                    continue
            else:
                print(f"❌ Local model file not found: {path}")
                continue

        # Load the model file from registry
        model_file = list_models()[found_version]["file"]
        if os.path.exists(model_file):
            loaded_models[name] = joblib.load(model_file)
            print(f"✅ Loaded {name} from {model_file}")
        else:
            print(f"❌ Model file missing in registry for {name}")

    if not loaded_models:
        raise FileNotFoundError("No models could be loaded from registry or local files")

    return loaded_models

# Example usage
# models = load_all_models()
# gb_model = models["gb_model"]
# rf_model = models["rf_model"]