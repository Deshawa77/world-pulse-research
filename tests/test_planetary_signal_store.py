import tempfile
import unittest
from pathlib import Path

from processing.planetary_signal_store import (
    load_recent_platform_normalized_signals,
    load_recent_platform_source_events,
    map_disaster_records_to_normalized_signals,
    map_disaster_records_to_source_events,
    map_internet_normalized_events_to_normalized_signals,
    map_internet_raw_events_to_source_events,
    persist_platform_signal_batch,
)


class PlanetarySignalStoreTests(unittest.TestCase):
    def test_persist_and_load_internet_platform_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            captured_at = "2026-04-15T00:00:00+00:00"
            source_events = map_internet_raw_events_to_source_events(
                [
                    {
                        "source_family": "bgp_routing",
                        "source_name": "routeviews",
                        "country": "LKA",
                        "timestamp": captured_at,
                        "metric_name": "latency_ms",
                        "metric_value": 142.0,
                        "event_type": "latency_spike",
                        "freshness_sec": 35,
                        "measurement_mode": "direct",
                    }
                ],
                run_id="internet_map_test_1",
                captured_at=captured_at,
            )
            normalized_signals = map_internet_normalized_events_to_normalized_signals(
                [
                    {
                        "source_family": "bgp_routing",
                        "source_name": "routeviews",
                        "country": "LKA",
                        "timestamp": captured_at,
                        "event_kind": "routing_latency",
                        "metric_name": "latency_ms",
                        "metric_value": 142.0,
                        "confidence_ratio": 0.82,
                        "freshness_sec": 35,
                    }
                ],
                run_id="internet_map_test_1",
                captured_at=captured_at,
            )

            summary = persist_platform_signal_batch(
                source_events=source_events,
                normalized_signals=normalized_signals,
                subsystem="real_time_internet_map",
                run_id="internet_map_test_1",
                captured_at=captured_at,
                root=tmpdir,
                persist_db=False,
            )

            self.assertEqual(summary["status"], "ok")
            self.assertTrue(Path(summary["manifest_latest_path"]).exists())

            stored_source_events = load_recent_platform_source_events(
                limit=10,
                root=tmpdir,
                source_family="bgp_routing",
                subsystem="real_time_internet_map",
            )
            self.assertEqual(len(stored_source_events), 1)
            self.assertEqual(stored_source_events[0]["event_type"], "latency_spike")

            stored_normalized_signals = load_recent_platform_normalized_signals(
                limit=10,
                root=tmpdir,
                signal_type="routing_latency",
            )
            self.assertEqual(len(stored_normalized_signals), 1)
            self.assertEqual(stored_normalized_signals[0]["metric_name"], "latency_ms")
            self.assertEqual(stored_normalized_signals[0]["subsystem"], "real_time_internet_map")

    def test_history_filtering_prefers_latest_captured_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            internet_captured_at = "2026-04-15T00:00:00+00:00"
            disaster_captured_at = "2026-04-15T00:11:00+00:00"

            internet_source_events = map_internet_raw_events_to_source_events(
                [
                    {
                        "source_family": "isp_telemetry",
                        "source_name": "isp_edge",
                        "country": "IND",
                        "timestamp": internet_captured_at,
                        "metric_name": "packet_loss_pct",
                        "metric_value": 3.1,
                        "event_type": "packet_loss",
                        "freshness_sec": 28,
                    }
                ],
                run_id="internet_map_test_2",
                captured_at=internet_captured_at,
            )
            internet_normalized_signals = map_internet_normalized_events_to_normalized_signals(
                [
                    {
                        "source_family": "isp_telemetry",
                        "source_name": "isp_edge",
                        "country": "IND",
                        "timestamp": internet_captured_at,
                        "event_kind": "packet_loss",
                        "metric_name": "packet_loss_pct",
                        "metric_value": 3.1,
                        "confidence_ratio": 0.71,
                        "freshness_sec": 28,
                    }
                ],
                run_id="internet_map_test_2",
                captured_at=internet_captured_at,
            )
            persist_platform_signal_batch(
                source_events=internet_source_events,
                normalized_signals=internet_normalized_signals,
                subsystem="real_time_internet_map",
                run_id="internet_map_test_2",
                captured_at=internet_captured_at,
                root=tmpdir,
                persist_db=False,
            )

            disaster_records = [
                {
                    "record_id": "quake-ind-1",
                    "source": "usgs",
                    "event_type": "earthquake",
                    "country": "IND",
                    "timestamp": disaster_captured_at,
                    "confidence": 0.67,
                    "severity_proxy": 0.72,
                    "signal_sources": ["seismic_data"],
                    "top_contributing_signals": ["magnitude", "aftershock"],
                }
            ]
            disaster_source_events = map_disaster_records_to_source_events(
                disaster_records,
                run_id="disaster_stream_test_1",
                captured_at=disaster_captured_at,
            )
            disaster_normalized_signals = map_disaster_records_to_normalized_signals(
                disaster_records,
                run_id="disaster_stream_test_1",
                captured_at=disaster_captured_at,
            )
            persist_platform_signal_batch(
                source_events=disaster_source_events,
                normalized_signals=disaster_normalized_signals,
                subsystem="global_disaster_early_warning_ai",
                run_id="disaster_stream_test_1",
                captured_at=disaster_captured_at,
                root=tmpdir,
                persist_db=False,
            )

            all_signals = load_recent_platform_normalized_signals(limit=10, root=tmpdir)
            self.assertEqual(all_signals[0]["subsystem"], "global_disaster_early_warning_ai")

            disaster_only = load_recent_platform_normalized_signals(
                limit=10,
                root=tmpdir,
                subsystem="global_disaster_early_warning_ai",
                signal_type="earthquake",
            )
            self.assertEqual(len(disaster_only), 1)
            self.assertEqual(disaster_only[0]["source_family"], "seismic_data")

            earthquake_events = load_recent_platform_source_events(
                limit=10,
                root=tmpdir,
                event_type="earthquake",
            )
            self.assertEqual(len(earthquake_events), 1)
            self.assertEqual(earthquake_events[0]["subsystem"], "global_disaster_early_warning_ai")


if __name__ == "__main__":
    unittest.main()
