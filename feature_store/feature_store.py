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
        # ✅ Check for empty DataFrame
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            print(f"[WARN] {name} feature DataFrame empty — skipping Parquet write")
            return

        df = df.copy()
        df["fs_timestamp"] = datetime.utcnow().isoformat()

        # ✅ Force numeric columns to avoid zero / bad types
        numeric_cols = ['crypto_return', 'crypto_volatility', 'stock_return', 'stock_volatility', 'weather_anomaly']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        # ✅ Write Parquet safely
        df.to_parquet(path, engine='pyarrow', index=False)
        print(f"[INFO] Features written to Parquet: {path}")

        # ---------- Metadata and schema ----------
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
            print(f"[WARN] Parquet file not found: {path}")
            return pd.DataFrame()
        try:
            df = pd.read_parquet(path)
            return df
        except Exception as e:
            print(f"[ERROR] Could not read Parquet: {path} → {e}")
            return pd.DataFrame()
