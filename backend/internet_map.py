from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any

from processing.country_catalog import COUNTRY_NAMES

COUNTRY_COORDS: dict[str, tuple[float, float]] = {
    "USA": (39.8, -98.6),
    "CAN": (56.1, -106.3),
    "MEX": (23.6, -102.6),
    "BRA": (-14.2, -51.9),
    "ARG": (-38.4, -63.6),
    "GBR": (55.4, -3.4),
    "FRA": (46.2, 2.2),
    "DEU": (51.2, 10.4),
    "ESP": (40.4, -3.7),
    "ITA": (42.8, 12.5),
    "NLD": (52.1, 5.3),
    "BEL": (50.8, 4.5),
    "CHE": (46.8, 8.2),
    "NOR": (60.5, 8.5),
    "SWE": (60.1, 18.6),
    "FIN": (64.5, 26.0),
    "POL": (52.1, 19.4),
    "UKR": (48.4, 31.2),
    "RUS": (61.5, 105.3),
    "TUR": (38.9, 35.2),
    "ISR": (31.0, 34.8),
    "QAT": (25.3, 51.2),
    "ARE": (24.3, 54.4),
    "SAU": (23.9, 45.1),
    "EGY": (26.8, 30.8),
    "NGA": (9.1, 8.7),
    "ZAF": (-30.6, 22.9),
    "KEN": (0.0, 37.9),
    "ETH": (9.1, 40.5),
    "MAR": (31.8, -7.1),
    "DZA": (28.0, 1.7),
    "IND": (20.6, 78.9),
    "PAK": (30.4, 69.3),
    "BGD": (23.7, 90.4),
    "LKA": (7.9, 80.7),
    "NPL": (28.4, 84.1),
    "CHN": (35.9, 104.2),
    "JPN": (36.2, 138.3),
    "KOR": (36.5, 127.9),
    "TWN": (23.7, 121.0),
    "IDN": (-0.8, 113.9),
    "THA": (15.9, 100.9),
    "VNM": (14.1, 108.3),
    "MYS": (4.2, 102.0),
    "PHL": (12.9, 121.8),
    "AUS": (-25.3, 133.8),
    "NZL": (-41.5, 172.8),
    "IRN": (32.4, 53.7),
}

COUNTRY_CAPACITY_WEIGHT: dict[str, float] = {
    "USA": 1.55,
    "CHN": 1.48,
    "IND": 1.34,
    "GBR": 1.1,
    "DEU": 1.08,
    "JPN": 1.07,
    "FRA": 1.01,
    "NLD": 1.02,
    "BRA": 0.98,
    "CAN": 0.97,
    "AUS": 0.95,
    "KOR": 0.94,
    "SGP": 0.93,
    "ARE": 0.88,
    "IND": 1.34,
    "ITA": 0.87,
    "ESP": 0.86,
    "MEX": 0.83,
    "IDN": 0.82,
    "ZAF": 0.8,
    "TUR": 0.8,
    "ISR": 0.78,
    "POL": 0.76,
    "LKA": 0.61,
}

CORE_CORRIDORS: list[tuple[str, str]] = [
    ("USA", "GBR"),
    ("USA", "DEU"),
    ("USA", "BRA"),
    ("USA", "JPN"),
    ("USA", "IND"),
    ("GBR", "DEU"),
    ("GBR", "IND"),
    ("GBR", "ARE"),
    ("DEU", "IND"),
    ("DEU", "TUR"),
    ("DEU", "ZAF"),
    ("IND", "ARE"),
    ("IND", "SGP"),
    ("IND", "LKA"),
    ("IND", "CHN"),
    ("CHN", "JPN"),
    ("CHN", "KOR"),
    ("CHN", "AUS"),
    ("JPN", "AUS"),
    ("BRA", "ESP"),
    ("ZAF", "GBR"),
    ("ARE", "AUS"),
]

ATTACK_VECTORS = [
    "Volumetric DDoS",
    "BGP Hijack Pressure",
    "DNS Amplification",
    "Credential Flooding",
    "Control Plane Abuse",
]


def _round(value: float, digits: int = 1) -> float:
    return round(float(value), digits)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _normalize_ratio(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric):
        return default
    if numeric > 1.0:
        numeric = numeric / 100.0 if numeric <= 100.0 else default
    return _clamp(numeric, 0.0, 1.0)


def _seed(value: str) -> int:
    text = str(value or "").strip().upper()
    return sum((index + 1) * ord(char) for index, char in enumerate(text))


def _fallback_coords(country: str) -> tuple[float, float]:
    seed = _seed(country)
    lat = ((_clamp(seed % 120, 0, 120) / 120.0) * 120.0) - 60.0
    lon = (((seed * 7) % 3600) / 10.0) - 180.0
    return (_round(lat, 2), _round(lon, 2))


def _resolve_coords(country: str) -> tuple[float, float]:
    return COUNTRY_COORDS.get(country, _fallback_coords(country))


def _country_label(country: str) -> str:
    return COUNTRY_NAMES.get(country, country)


def _severity(value: float) -> str:
    if value >= 85.0:
        return "critical"
    if value >= 70.0:
        return "high"
    if value >= 50.0:
        return "elevated"
    if value >= 30.0:
        return "guarded"
    return "stable"


def _country_status(congestion: float, attack: float, shutdown: float, risk_ratio: float) -> str:
    if shutdown >= 74.0:
        return "shutdown-alert"
    if attack >= 72.0:
        return "under-attack"
    if congestion >= 68.0:
        return "congested"
    if risk_ratio >= 0.58:
        return "volatile"
    return "stable"


def _flow_status(congestion: float, attack: float, packet_loss_pct: float) -> str:
    if attack >= 72.0:
        return "contested"
    if congestion >= 68.0 or packet_loss_pct >= 4.0:
        return "degraded"
    return "stable"


def _source_status(coverage_ratio: float, confidence_ratio: float, freshness_sec: int) -> str:
    if coverage_ratio >= 0.7 and confidence_ratio >= 0.65 and freshness_sec <= 45:
        return "healthy"
    if coverage_ratio >= 0.5 and confidence_ratio >= 0.45 and freshness_sec <= 90:
        return "degraded"
    return "limited"


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    return radius * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def _country_advisory(country: dict[str, Any]) -> str:
    if country["status"] == "shutdown-alert":
        return "Prioritize national gateway, mobile ASN, and DNS reachability verification before escalation."
    if country["status"] == "under-attack":
        return "Correlate route volatility with edge saturation and upstream scrubbing posture."
    if country["status"] == "congested":
        return "Inspect international transit contention and confirm whether reroute pressure is sustained."
    return "Monitor for sustained divergence before alerting downstream operators."


def _shutdown_reason(country: dict[str, Any]) -> str:
    if country["shutdown_risk"] >= 78.0:
        return "Compounded energy, logistics, and freshness stress indicates elevated national shutdown risk."
    if country["shutdown_risk"] >= 64.0:
        return "Multiple disruption signals suggest growing impairment at national internet access points."
    return "Route and service continuity should be watched for early shutdown signatures."


def _attack_vector(flow_id: str, attack_index: float) -> str:
    offset = 1 if attack_index >= 72.0 else 0
    return ATTACK_VECTORS[(_seed(flow_id) + offset) % len(ATTACK_VECTORS)]


def build_internet_map_snapshot(
    country_docs: list[dict[str, Any]] | None,
    global_doc: dict[str, Any] | None = None,
    mode: str = "online",
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    generated_at_iso = generated_at.isoformat()
    features = global_doc.get("features") if isinstance(global_doc, dict) and isinstance(global_doc.get("features"), dict) else {}
    latest_global_timestamp = str(features.get("timestamp") or (global_doc or {}).get("timestamp") or generated_at_iso)
    docs = list(country_docs or [])

    normalized: list[dict[str, Any]] = []
    validated_count = 0
    monitored_total = 0

    for raw in docs:
        country = str((raw or {}).get("country") or "").strip().upper()
        if not country:
            continue
        monitored_total += 1
        risk = _normalize_ratio((raw or {}).get("risk"))
        attention = _normalize_ratio((raw or {}).get("public_attention_score"))
        mobility = _normalize_ratio((raw or {}).get("mobility_disruption_score"))
        logistics = _normalize_ratio((raw or {}).get("logistics_stress_score"))
        energy = _normalize_ratio((raw or {}).get("energy_stress_score"))
        coordination = _normalize_ratio((raw or {}).get("coordination_risk_score"))
        freshness = _normalize_ratio((raw or {}).get("external_signal_freshness"), 0.42)
        evidence = _normalize_ratio((raw or {}).get("evidence_quality_score"), 0.38)
        source_count = max(0, int((raw or {}).get("source_count") or 0))
        validated_today = bool((raw or {}).get("validated_today"))
        if validated_today:
            validated_count += 1
        lat, lon = _resolve_coords(country)
        base_capacity = COUNTRY_CAPACITY_WEIGHT.get(country, 0.62 + ((_seed(country) % 44) / 100.0))
        packet_flow_gbps = _round(
            85.0
            + base_capacity * 410.0
            + source_count * 24.0
            + (1.0 - risk) * 135.0
            + attention * 58.0
            + freshness * 36.0,
            1,
        )
        congestion_index = _round(
            _clamp(
                100.0 * (0.31 * risk + 0.27 * mobility + 0.19 * logistics + 0.13 * energy + 0.10 * (1.0 - freshness)),
                0.0,
                100.0,
            ),
            1,
        )
        attack_index = _round(
            _clamp(
                100.0 * (0.36 * risk + 0.28 * coordination + 0.18 * attention + 0.10 * logistics + 0.08 * (1.0 - freshness)),
                0.0,
                100.0,
            ),
            1,
        )
        shutdown_risk = _round(
            _clamp(
                100.0 * (0.26 * risk + 0.24 * energy + 0.21 * mobility + 0.17 * logistics + 0.12 * (1.0 - freshness)),
                0.0,
                100.0,
            ),
            1,
        )
        stability_score = _round(
            _clamp(
                100.0 - (0.36 * congestion_index + 0.33 * attack_index + 0.31 * shutdown_risk),
                0.0,
                100.0,
            ),
            1,
        )
        signal_strength = _round(
            _clamp(
                0.30 * risk
                + 0.16 * attention
                + 0.14 * mobility
                + 0.12 * logistics
                + 0.10 * energy
                + 0.08 * freshness
                + 0.10 * evidence
                + min(source_count, 8) / 10.0,
                0.0,
                1.6,
            ),
            3,
        )
        normalized.append(
            {
                "country": country,
                "label": _country_label(country),
                "lat": lat,
                "lon": lon,
                "risk": _round(risk, 3),
                "data_quality": str((raw or {}).get("data_quality") or "unknown"),
                "validated_today": validated_today,
                "source_count": source_count,
                "freshness_ratio": _round(freshness, 3),
                "evidence_quality_score": _round(evidence, 3),
                "packet_flow_gbps": packet_flow_gbps,
                "congestion_index": congestion_index,
                "attack_index": attack_index,
                "shutdown_risk": shutdown_risk,
                "stability_score": stability_score,
                "signal_strength": signal_strength,
                "status": _country_status(congestion_index, attack_index, shutdown_risk, risk),
                "severity": _severity(max(congestion_index, attack_index, shutdown_risk)),
                "advisory": _country_advisory({
                    "status": _country_status(congestion_index, attack_index, shutdown_risk, risk),
                    "shutdown_risk": shutdown_risk,
                }),
            }
        )

    if not normalized:
        return {
            "generated_at": generated_at_iso,
            "refresh_interval_sec": 20,
            "summary": {
                "mode": mode,
                "source_stage": "phase-1-derived",
                "source_status": "limited",
                "monitored_countries": 0,
                "visible_countries": 0,
                "healthy_countries": 0,
                "degraded_countries": 0,
                "shutdown_alerts": 0,
                "active_attack_paths": 0,
                "global_packet_volume_gbps": 0.0,
                "global_congestion_index": 0.0,
                "cyber_attack_index": 0.0,
                "rerouted_prefixes": 0,
                "monitored_prefixes": 0,
            },
            "source_health": [],
            "countries": [],
            "flows": [],
            "cyber_attacks": [],
            "shutdown_alerts": [],
            "top_corridors": [],
            "generated_from": {
                "mode": mode,
                "source_stage": "phase-1-derived",
                "latest_global_timestamp": latest_global_timestamp,
                "note": "No country intelligence was available for the internet map snapshot.",
            },
        }

    eligible = [
        row for row in normalized
        if row["source_count"] > 0
        or row["validated_today"]
        or row["risk"] >= 0.05
        or row["signal_strength"] >= 0.26
    ]
    if not eligible:
        eligible = list(normalized)

    core_keep = {origin for origin, _ in CORE_CORRIDORS} | {destination for _, destination in CORE_CORRIDORS}
    eligible.sort(key=lambda row: (row["signal_strength"], row["packet_flow_gbps"]), reverse=True)
    visible: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in eligible:
        if row["country"] in seen:
            continue
        seen.add(row["country"])
        visible.append(row)
        if len(visible) >= 42:
            break
    for row in normalized:
        if len(visible) >= 42:
            break
        if row["country"] not in core_keep or row["country"] in seen:
            continue
        seen.add(row["country"])
        visible.append(row)

    visible.sort(key=lambda row: (max(row["shutdown_risk"], row["attack_index"], row["congestion_index"]), row["packet_flow_gbps"]), reverse=True)
    countries_by_code = {row["country"]: row for row in visible}

    flow_pairs = list(CORE_CORRIDORS)
    top_flow_codes = [row["country"] for row in sorted(visible, key=lambda row: row["packet_flow_gbps"], reverse=True)[:8]]
    for index, origin in enumerate(top_flow_codes):
        for destination in top_flow_codes[index + 1:index + 4]:
            flow_pairs.append((origin, destination))

    flows: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for origin, destination in flow_pairs:
        if origin not in countries_by_code or destination not in countries_by_code or origin == destination:
            continue
        key = tuple(sorted((origin, destination)))
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        left = countries_by_code[origin]
        right = countries_by_code[destination]
        distance_km = _distance_km(left["lat"], left["lon"], right["lat"], right["lon"])
        throughput_gbps = _round(
            ((left["packet_flow_gbps"] + right["packet_flow_gbps"]) / 2.0)
            * (0.54 + min(distance_km, 16000.0) / 28000.0),
            1,
        )
        congestion_index = _round((left["congestion_index"] * 0.52) + (right["congestion_index"] * 0.48), 1)
        attack_index = _round(max(left["attack_index"], right["attack_index"]) * 0.62 + min(left["attack_index"], right["attack_index"]) * 0.22, 1)
        latency_ms = _round(26.0 + (distance_km / 215.0) + (congestion_index * 0.26) + (attack_index * 0.08), 1)
        packet_loss_pct = _round(min(12.0, 0.18 + (congestion_index * 0.035) + (attack_index * 0.018)), 2)
        reroute_factor = _round(1.0 + max(0.0, congestion_index - 35.0) / 130.0 + max(0.0, attack_index - 40.0) / 160.0, 2)
        anomaly_score = _round(min(100.0, (congestion_index * 0.55) + (attack_index * 0.45) + (packet_loss_pct * 2.5)), 1)
        flows.append(
            {
                "id": f"{origin.lower()}-{destination.lower()}",
                "origin": origin,
                "origin_label": left["label"],
                "origin_lat": left["lat"],
                "origin_lon": left["lon"],
                "destination": destination,
                "destination_label": right["label"],
                "destination_lat": right["lat"],
                "destination_lon": right["lon"],
                "throughput_gbps": throughput_gbps,
                "congestion_index": congestion_index,
                "attack_index": attack_index,
                "latency_ms": latency_ms,
                "packet_loss_pct": packet_loss_pct,
                "reroute_factor": reroute_factor,
                "anomaly_score": anomaly_score,
                "status": _flow_status(congestion_index, attack_index, packet_loss_pct),
                "severity": _severity(max(congestion_index, attack_index, packet_loss_pct * 8.0)),
            }
        )

    flows.sort(key=lambda row: (row["anomaly_score"], row["throughput_gbps"]), reverse=True)
    flows = flows[:18]
    peak_throughput = max((row["throughput_gbps"] for row in flows), default=1.0)
    for flow in flows:
        flow["traffic_share"] = _round(flow["throughput_gbps"] / peak_throughput, 3)

    shutdown_alerts: list[dict[str, Any]] = []
    for country in visible:
        if country["shutdown_risk"] < 56.0 and country["status"] != "shutdown-alert":
            continue
        started_at = generated_at - timedelta(minutes=12 + (_seed(country["country"]) % 180))
        shutdown_alerts.append(
            {
                "id": f"shutdown-{country['country'].lower()}",
                "country": country["country"],
                "label": country["label"],
                "severity": _severity(country["shutdown_risk"]),
                "status": "active" if country["shutdown_risk"] >= 70.0 else "watch",
                "shutdown_risk": country["shutdown_risk"],
                "estimated_users_impacted_m": _round(max(0.4, country["packet_flow_gbps"] * 0.035 + country["congestion_index"] / 25.0), 1),
                "confidence_ratio": _round(_clamp(0.34 + country["freshness_ratio"] * 0.28 + country["evidence_quality_score"] * 0.22 + (0.1 if country["validated_today"] else 0.0), 0.0, 1.0), 2),
                "reason": _shutdown_reason(country),
                "started_at": started_at.isoformat(),
                "advisory": country["advisory"],
            }
        )
    shutdown_alerts.sort(key=lambda row: row["shutdown_risk"], reverse=True)
    shutdown_alerts = shutdown_alerts[:8]

    cyber_attacks: list[dict[str, Any]] = []
    for flow in flows:
        if flow["attack_index"] < 52.0:
            continue
        started_at = generated_at - timedelta(minutes=5 + (_seed(flow["id"]) % 95))
        intensity_gbps = _round(flow["throughput_gbps"] * (0.24 + (flow["attack_index"] / 170.0)), 1)
        packets_mps = _round(flow["throughput_gbps"] * (0.38 + (flow["attack_index"] / 120.0)), 1)
        cyber_attacks.append(
            {
                "id": f"attack-{flow['id']}",
                "origin": flow["origin"],
                "origin_label": flow["origin_label"],
                "target": flow["destination"],
                "target_label": flow["destination_label"],
                "severity": _severity(flow["attack_index"]),
                "status": "active" if flow["attack_index"] >= 68.0 else "monitoring",
                "vector": _attack_vector(flow["id"], flow["attack_index"]),
                "attack_index": flow["attack_index"],
                "intensity_gbps": intensity_gbps,
                "packets_mps": packets_mps,
                "confidence_ratio": _round(_clamp(0.36 + (flow["attack_index"] / 180.0) + (flow["traffic_share"] * 0.18), 0.0, 1.0), 2),
                "started_at": started_at.isoformat(),
            }
        )
    cyber_attacks.sort(key=lambda row: (row["attack_index"], row["intensity_gbps"]), reverse=True)
    cyber_attacks = cyber_attacks[:8]

    avg_freshness = sum(country["freshness_ratio"] for country in visible) / max(len(visible), 1)
    avg_evidence = sum(country["evidence_quality_score"] for country in visible) / max(len(visible), 1)
    coverage_ratio = len(visible) / max(monitored_total, 1)
    validated_ratio = validated_count / max(monitored_total, 1)
    avg_congestion = sum(country["congestion_index"] for country in visible) / max(len(visible), 1)
    avg_attack = sum(country["attack_index"] for country in visible) / max(len(visible), 1)

    source_health_raw = [
        {
            "source": "BGP routing",
            "coverage_ratio": _round(min(1.0, 0.38 + coverage_ratio * 0.52), 2),
            "confidence_ratio": _round(min(1.0, 0.32 + avg_evidence * 0.42 + validated_ratio * 0.18), 2),
            "freshness_sec": int(round(22 + (1.0 - avg_freshness) * 78)),
            "detail": "Currently inferred from route instability proxies in country intelligence until direct routing collectors are connected.",
        },
        {
            "source": "CDN traffic",
            "coverage_ratio": _round(min(1.0, 0.44 + coverage_ratio * 0.44), 2),
            "confidence_ratio": _round(min(1.0, 0.36 + avg_evidence * 0.34 + (1.0 - avg_congestion / 100.0) * 0.16), 2),
            "freshness_sec": int(round(18 + (1.0 - avg_freshness) * 62)),
            "detail": "Using attention, congestion, and logistics proxies until direct edge traffic telemetry is available.",
        },
        {
            "source": "ISP telemetry",
            "coverage_ratio": _round(min(1.0, 0.34 + coverage_ratio * 0.4), 2),
            "confidence_ratio": _round(min(1.0, 0.28 + avg_evidence * 0.32 + validated_ratio * 0.14), 2),
            "freshness_sec": int(round(28 + (1.0 - avg_freshness) * 84)),
            "detail": "Country shutdown and impairment scores are estimated from mobility, energy, and logistics stress in phase 1.",
        },
        {
            "source": "Cloud metrics",
            "coverage_ratio": _round(min(1.0, 0.4 + coverage_ratio * 0.46), 2),
            "confidence_ratio": _round(min(1.0, 0.34 + avg_evidence * 0.36 + (1.0 - avg_attack / 100.0) * 0.12), 2),
            "freshness_sec": int(round(20 + (1.0 - avg_freshness) * 70)),
            "detail": "Backbone and control-plane posture is derived from current World Pulse operational signals pending direct cloud-region connectors.",
        },
    ]
    source_health = []
    for source in source_health_raw:
        source_health.append(
            {
                **source,
                "stage": "derived",
                "status": _source_status(source["coverage_ratio"], source["confidence_ratio"], int(source["freshness_sec"])),
            }
        )

    healthy_countries = sum(1 for country in visible if country["status"] == "stable")
    degraded_countries = len(visible) - healthy_countries
    global_packet_volume_gbps = _round(sum(flow["throughput_gbps"] for flow in flows), 1)
    congestion_weight_base = sum(flow["throughput_gbps"] for flow in flows) or 1.0
    global_congestion_index = _round(sum(flow["congestion_index"] * flow["throughput_gbps"] for flow in flows) / congestion_weight_base, 1) if flows else _round(avg_congestion, 1)
    cyber_attack_index = _round(sum(flow["attack_index"] for flow in flows) / max(len(flows), 1), 1) if flows else _round(avg_attack, 1)
    rerouted_prefixes = int(round(sum(max(0.0, flow["reroute_factor"] - 1.0) * 120.0 for flow in flows)))
    monitored_prefixes = int(round(monitored_total * 480 + sum(country["source_count"] for country in visible) * 24))
    source_status = "limited"
    if any(source["status"] == "healthy" for source in source_health):
        source_status = "derived-live"
    elif any(source["status"] == "degraded" for source in source_health):
        source_status = "degraded"

    top_corridors = sorted(flows, key=lambda flow: (flow["congestion_index"], flow["attack_index"], flow["throughput_gbps"]), reverse=True)[:8]

    return {
        "generated_at": generated_at_iso,
        "refresh_interval_sec": 20,
        "summary": {
            "mode": mode,
            "source_stage": "phase-1-derived",
            "source_status": source_status,
            "monitored_countries": monitored_total,
            "visible_countries": len(visible),
            "healthy_countries": healthy_countries,
            "degraded_countries": degraded_countries,
            "shutdown_alerts": len(shutdown_alerts),
            "active_attack_paths": sum(1 for flow in flows if flow["attack_index"] >= 55.0),
            "global_packet_volume_gbps": global_packet_volume_gbps,
            "global_congestion_index": global_congestion_index,
            "cyber_attack_index": cyber_attack_index,
            "rerouted_prefixes": rerouted_prefixes,
            "monitored_prefixes": monitored_prefixes,
        },
        "source_health": source_health,
        "countries": visible,
        "flows": flows,
        "cyber_attacks": cyber_attacks,
        "shutdown_alerts": shutdown_alerts,
        "top_corridors": top_corridors,
        "generated_from": {
            "mode": mode,
            "source_stage": "phase-1-derived",
            "latest_global_timestamp": latest_global_timestamp,
            "country_snapshot_count": monitored_total,
            "visible_country_count": len(visible),
            "note": "Derived from World Pulse country intelligence until direct BGP, CDN, ISP, and cloud collectors are connected.",
        },
    }
