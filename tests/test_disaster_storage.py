import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import processing.disaster_storage as disaster_storage


class DisasterStorageFallbackTests(unittest.TestCase):
    def test_feature_snapshot_falls_back_to_csv_when_parquet_engine_missing(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "event_type": "flood",
                    "country": "USA",
                    "lead_time_hours": 24,
                    "updated_at": "2026-04-29T00:00:00+00:00",
                }
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "feature_store"
            with patch.object(pd.DataFrame, "to_parquet", side_effect=ImportError("missing parquet engine")):
                snapshot = disaster_storage._write_feature_snapshot(frame, root, "disasters")

            metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["format"], "csv")
            self.assertTrue(snapshot["path"].endswith("features.csv"))
            self.assertEqual(metadata["table_format"], "csv")
            self.assertTrue((root / "features.csv").exists())
            self.assertTrue((root / "latest.json").exists())

    def test_cyclone_tracker_snapshot_falls_back_to_csv(self) -> None:
        payload = {
            "storm_tracks": [
                {
                    "storm_id": "alpha",
                    "track_points": [{"lat": 10.0, "lon": 80.0}],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            with patch.object(disaster_storage, "CYCLONE_TRACKER_ROOT", tmp / "cyclone"), patch.object(
                disaster_storage, "CYCLONE_TRACKER_JSON", tmp / "cyclone" / "latest.json"
            ), patch.object(
                disaster_storage, "CYCLONE_TRACKER_PARQUET", tmp / "cyclone" / "tracks.parquet"
            ), patch.object(pd.DataFrame, "to_parquet", side_effect=ImportError("missing parquet engine")):
                result = disaster_storage.persist_cyclone_tracker_snapshot(payload)

            self.assertEqual(result["track_format"], "csv")
            self.assertTrue(result["track_path"].endswith("tracks.csv"))
            self.assertTrue((tmp / "cyclone" / "tracks.csv").exists())

    def test_seismic_snapshot_falls_back_to_csv(self) -> None:
        payload = {
            "anomaly_clusters": [
                {
                    "cluster_id": "cluster-1",
                    "history": {"score": 0.7},
                    "trend_points": [0.2, 0.4, 0.7],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            with patch.object(disaster_storage, "SEISMIC_ANOMALY_ROOT", tmp / "seismic"), patch.object(
                disaster_storage, "SEISMIC_ANOMALY_JSON", tmp / "seismic" / "latest.json"
            ), patch.object(
                disaster_storage, "SEISMIC_ANOMALY_PARQUET", tmp / "seismic" / "anomalies.parquet"
            ), patch.object(pd.DataFrame, "to_parquet", side_effect=ImportError("missing parquet engine")):
                result = disaster_storage.persist_seismic_anomaly_snapshot(payload)

            self.assertEqual(result["anomaly_format"], "csv")
            self.assertTrue(result["anomaly_path"].endswith("anomalies.csv"))
            self.assertTrue((tmp / "seismic" / "anomalies.csv").exists())


if __name__ == "__main__":
    unittest.main()
