import pandas as pd
import json
import os
from datetime import datetime
from .config import *

os.makedirs(os.path.dirname(GLOBAL_PATH), exist_ok=True)
os.makedirs(os.path.dirname(COUNTRY_PATH), exist_ok=True)
os.makedirs(os.path.dirname(REALTIME_PATH), exist_ok=True)
os.makedirs(VERSION_PATH, exist_ok=True)

class FeatureStore:

    # ---------- WRITE ----------
    def write_global(self, df: pd.DataFrame):
        self._write(df, GLOBAL_PATH, "global")

    def write_country(self, df: pd.DataFrame):
        self._write(df, COUNTRY_PATH, "country")

    def write_realtime(self, df: pd.DataFrame):
        self._write(df, REALTIME_PATH, "realtime")

    def _write(self, df, path, name):
        df = df.copy()
        df["fs_timestamp"] = datetime.utcnow().isoformat()
        df.to_parquet(path, index=False)

        meta = {
            "name": name,
            "updated_at": datetime.utcnow().isoformat(),
            "rows": len(df),
            "columns": list(df.columns)
        }

        meta_path = path.replace("features.parquet", "metadata.json")
        schema_path = path.replace("features.parquet", "schema.json")

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(
                {"schema": {col: str(dtype) for col, dtype in df.dtypes.items()}},
                f,
                indent=2
            )

    # ---------- READ ----------
    def read_global(self):
        return self._read(GLOBAL_PATH)

    def read_country(self):
        return self._read(COUNTRY_PATH)

    def read_realtime(self):
        return self._read(REALTIME_PATH)

    def _read(self, path):
        if not os.path.exists(path):
            return pd.DataFrame()
        return pd.read_parquet(path)
