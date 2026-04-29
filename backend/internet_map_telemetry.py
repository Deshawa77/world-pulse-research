from __future__ import annotations



from collections import defaultdict

from datetime import datetime, timedelta, timezone

from typing import Any

from backend.internet_map_thresholds import threshold_value



ATTACK_VECTORS = [

    "Volumetric DDoS",

    "BGP Hijack Pressure",

    "DNS Amplification",

    "Credential Flooding",

    "Control Plane Abuse",

]





def _safe_float(value: Any, fallback: float = 0.0) -> float:

    try:

        numeric = float(value)

    except (TypeError, ValueError):

        return fallback

    return numeric if numeric == numeric else fallback





def _clamp(value: float, lower: float, upper: float) -> float:

    return max(lower, min(upper, float(value)))





def _seed(value: str) -> int:

    return sum((index + 1) * ord(char) for index, char in enumerate(str(value or "").upper()))





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





def _country_status(congestion: float, attack: float, shutdown: float) -> str:

    if shutdown >= 74.0:

        return "shutdown-alert"

    if attack >= 72.0:

        return "under-attack"

    if congestion >= 68.0:

        return "congested"

    if max(congestion, attack, shutdown) >= 45.0:

        return "volatile"

    return "stable"





def _flow_status(congestion: float, attack: float, packet_loss_pct: float) -> str:

    if attack >= 72.0:

        return "contested"

    if congestion >= 68.0 or packet_loss_pct >= 4.0:

        return "degraded"

    return "stable"



def _flow_attack_signal_count(flow: dict[str, Any]) -> int:

    signals = 0

    if _safe_float(flow.get("attack_index")) >= float(threshold_value("flow_signals", "attack_index", 60.0)):

        signals += 1

    if _safe_float(flow.get("hijack_suspect_score")) >= float(threshold_value("flow_signals", "hijack_suspect_score", 0.22)):

        signals += 1

    if _safe_float(flow.get("control_plane_incident_score")) >= float(threshold_value("flow_signals", "control_plane_incident_score", 0.2)):

        signals += 1

    if _safe_float(flow.get("dns_error_ratio")) >= float(threshold_value("flow_signals", "dns_error_ratio", 0.14)):

        signals += 1

    if _safe_float(flow.get("edge_error_rate")) >= float(threshold_value("flow_signals", "edge_error_rate", 0.16)):

        signals += 1

    if _safe_float(flow.get("reroute_factor"), 1.0) >= float(threshold_value("flow_signals", "reroute_factor", 1.12)):

        signals += 1

    return signals



def _country_shutdown_signal_count(country: dict[str, Any]) -> int:

    signals = 0

    if _safe_float(country.get("shutdown_risk")) >= float(threshold_value("shutdown_signals", "shutdown_risk", 62.0)):

        signals += 1

    if _safe_float(country.get("subscriber_availability_ratio"), 1.0) <= float(threshold_value("shutdown_signals", "subscriber_availability_ratio", 0.8)):

        signals += 1

    if _safe_float(country.get("fixed_reachability_ratio"), 1.0) <= float(threshold_value("shutdown_signals", "fixed_reachability_ratio", 0.82)):

        signals += 1

    if _safe_float(country.get("mobile_reachability_ratio"), 1.0) <= float(threshold_value("shutdown_signals", "mobile_reachability_ratio", 0.8)):

        signals += 1

    if _safe_float(country.get("throughput_drop_pct")) >= float(threshold_value("shutdown_signals", "throughput_drop_pct", 22.0)):

        signals += 1

    if _safe_float(country.get("control_plane_incident_score")) >= float(threshold_value("shutdown_signals", "control_plane_incident_score", 0.18)):

        signals += 1

    return signals





def _measurement_weight(event: dict[str, Any]) -> float:

    mode = str(event.get("measurement_mode") or "synthetic").lower()

    base = 1.0 if mode == "direct" else 0.72 if mode in {"fixture", "sample"} else 0.45

    confidence = _safe_float(event.get("confidence_ratio"), 0.6)

    freshness = max(1.0, _safe_float(event.get("freshness_sec"), 60.0))

    freshness_boost = 1.0 / min(2.0, max(0.4, freshness / 45.0))

    return max(0.1, base * max(0.25, confidence) * freshness_boost)





def _weighted_average(rows: list[dict[str, float]], default: float = 0.0) -> float:

    if not rows:

        return default

    total_weight = sum(item["weight"] for item in rows if item["weight"] > 0) or float(len(rows))

    return sum(item["value"] * item["weight"] for item in rows) / total_weight





def _max_value(rows: list[dict[str, float]], default: float = 0.0) -> float:

    return max((item["value"] for item in rows), default=default)





def _normalize_country(value: Any) -> str:

    return str(value or "").strip().upper()





def _normalize_region(origin: Any, destination: Any, region: Any) -> str:

    region_text = str(region or "").strip().upper()

    if region_text:

        return region_text

    left = _normalize_country(origin)

    right = _normalize_country(destination)

    if left and right:

        return f"{left}->{right}"

    return left or right or "GLB"





def _attack_vector(flow_id: str, hijack_score: float, dns_error_ratio: float, control_plane_score: float, edge_error_rate: float) -> str:

    if hijack_score >= 0.22:

        return "BGP Hijack Pressure"

    if control_plane_score >= 0.2:

        return "Control Plane Abuse"

    if dns_error_ratio >= 0.12:

        return "DNS Amplification"

    if edge_error_rate >= 0.18:

        return "Credential Flooding"

    return ATTACK_VECTORS[_seed(flow_id) % len(ATTACK_VECTORS)]





def _country_advisory(country: dict[str, Any]) -> str:

    if country["status"] == "shutdown-alert":

        return "Measured fixed/mobile reachability collapse suggests national access impairment; verify gateway and resolver continuity."

    if country["status"] == "under-attack":

        return "Correlate direct route volatility, DNS/API errors, and edge saturation before upstream escalation."

    if country["status"] == "congested":

        return "Inspect corridor utilization and egress saturation to determine whether load shedding or reroute actions are required."

    return "Monitor direct reachability and corridor telemetry for sustained divergence before alerting downstream operators."





def _build_metric_maps(normalized_events: list[dict[str, Any]]) -> tuple[dict[str, dict[str, list[dict[str, float]]]], dict[str, dict[str, list[dict[str, float]]]], dict[str, set[str]]]:

    flow_metrics: dict[str, dict[str, list[dict[str, float]]]] = defaultdict(lambda: defaultdict(list))

    country_metrics: dict[str, dict[str, list[dict[str, float]]]] = defaultdict(lambda: defaultdict(list))

    flow_families: dict[str, set[str]] = defaultdict(set)

    for event in normalized_events:

        metric_name = str(event.get("metric_name") or "").strip()

        if not metric_name:

            continue

        row = {

            "value": _safe_float(event.get("metric_value")),

            "weight": _measurement_weight(event),

        }

        region = _normalize_region(event.get("origin"), event.get("destination"), event.get("region"))

        country = _normalize_country(event.get("country"))

        family = str(event.get("source_family") or "unknown")

        flow_metrics[region][metric_name].append(row)

        flow_families[region].add(family)

        for code in {country, _normalize_country(event.get("origin")), _normalize_country(event.get("destination"))}:

            if code:

                country_metrics[code][metric_name].append(row)

    return flow_metrics, country_metrics, flow_families





def _summary_stage(source_health: list[dict[str, Any]], fallback: str) -> tuple[str, list[str], list[str]]:

    direct_families = [str(item.get("source_family") or item.get("source") or "") for item in source_health if str(item.get("measurement_mode") or "") == "direct"]

    measurement_modes = sorted({str(item.get("measurement_mode") or "unknown") for item in source_health})

    if len(direct_families) >= 4:

        return "phase-4-direct-live", direct_families, measurement_modes

    if direct_families:

        return "phase-4-direct-hybrid", direct_families, measurement_modes

    return fallback, direct_families, measurement_modes





def apply_direct_internet_signals(payload: dict[str, Any], normalized_events: list[dict[str, Any]], source_health: list[dict[str, Any]]) -> dict[str, Any]:

    if not payload:

        return payload

    flow_metrics, country_metrics, flow_families = _build_metric_maps(normalized_events)

    generated_at_value = str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat())

    generated_at = datetime.fromisoformat(generated_at_value.replace("Z", "+00:00"))



    prior_attacks = {str(item.get("flow_id") or item.get("id") or "").lower(): item for item in (payload.get("cyber_attacks") or [])}

    prior_shutdowns = {str(item.get("country") or "").upper(): item for item in (payload.get("shutdown_alerts") or [])}



    flows: list[dict[str, Any]] = []

    for item in (payload.get("flows") or []):

        flow = dict(item)

        region = _normalize_region(flow.get("origin"), flow.get("destination"), None)

        metrics = flow_metrics.get(region) or flow_metrics.get(_normalize_region(flow.get("destination"), flow.get("origin"), None)) or {}

        measured_latency = _weighted_average(metrics.get("edge_latency_ms") or [], _safe_float(flow.get("latency_ms")))

        measured_throughput = _weighted_average(metrics.get("edge_throughput_gbps") or [], _safe_float(flow.get("throughput_gbps")))

        packet_loss = _weighted_average(metrics.get("edge_packet_loss_pct") or [], _safe_float(flow.get("packet_loss_pct")))

        edge_error_rate = _weighted_average(metrics.get("edge_error_rate") or [], 0.0)

        pop_utilization = _max_value(metrics.get("pop_utilization_ratio") or [], 0.0)

        corridor_utilization = _max_value(metrics.get("corridor_utilization_ratio") or [], 0.0)

        withdrawals = _weighted_average(metrics.get("withdrawn_prefix_count") or [], 0.0)

        route_updates = _weighted_average(metrics.get("route_update_count") or [], 0.0)

        announcements = _weighted_average(metrics.get("announcement_count") or [], 0.0)

        churn_score = _max_value(metrics.get("as_path_churn_score") or [], 0.0)

        reroute_factor = max(_safe_float(flow.get("reroute_factor"), 1.0), _weighted_average(metrics.get("reroute_factor") or [], _safe_float(flow.get("reroute_factor"), 1.0)))

        hijack_score = _max_value(metrics.get("hijack_suspect_score") or [], 0.0)

        monitored_prefix_count = _weighted_average(metrics.get("monitored_prefix_count") or [], 0.0)

        region_health = _weighted_average(metrics.get("region_health_score") or [], 1.0)

        egress_saturation = _max_value(metrics.get("egress_saturation_ratio") or [], 0.0)

        dns_error_ratio = _weighted_average(metrics.get("dns_error_ratio") or [], 0.0)

        control_plane_score = _max_value(metrics.get("control_plane_incident_score") or [], 0.0)

        api_error_ratio = _weighted_average(metrics.get("api_error_ratio") or [], 0.0)

        measured_signal_count = sum(1 for value in metrics.values() if value)



        latency_component = _clamp((measured_latency - 35.0) / 1.6, 0.0, 100.0)

        loss_component = _clamp(packet_loss * 17.0, 0.0, 100.0)

        utilization_component = _clamp(max(pop_utilization, corridor_utilization, egress_saturation) * 100.0, 0.0, 100.0)

        health_penalty = _clamp((1.0 - region_health) * 100.0, 0.0, 100.0)

        congestion_index = round(_clamp(max(_safe_float(flow.get("congestion_index")) * 0.62, 0.34 * latency_component + 0.28 * loss_component + 0.24 * utilization_component + 0.14 * health_penalty), 0.0, 100.0), 1)

        attack_index = round(_clamp(max(_safe_float(flow.get("attack_index")) * 0.58, 100.0 * (0.28 * hijack_score + 0.18 * edge_error_rate + 0.16 * dns_error_ratio + 0.16 * control_plane_score + 0.12 * churn_score + 0.10 * max(0.0, reroute_factor - 1.0))), 0.0, 100.0), 1)

        anomaly_score = round(_clamp((0.48 * congestion_index) + (0.36 * attack_index) + (0.16 * min(packet_loss * 12.0, 100.0)), 0.0, 100.0), 1)

        flow.update({

            "latency_ms": round(measured_latency, 1),

            "throughput_gbps": round(measured_throughput, 1),

            "packet_loss_pct": round(packet_loss, 2),

            "congestion_index": congestion_index,

            "attack_index": attack_index,

            "reroute_factor": round(reroute_factor, 2),

            "anomaly_score": anomaly_score,

            "route_update_count": round(route_updates, 2),

            "announcement_count": round(announcements, 2),

            "withdrawn_prefix_count": round(withdrawals, 2),

            "as_path_churn_score": round(churn_score, 3),

            "hijack_suspect_score": round(hijack_score, 3),

            "monitored_prefix_count": round(monitored_prefix_count, 1),

            "edge_error_rate": round(edge_error_rate, 3),

            "egress_saturation_ratio": round(egress_saturation, 3),

            "dns_error_ratio": round(dns_error_ratio, 3),

            "control_plane_incident_score": round(control_plane_score, 3),

            "api_error_ratio": round(api_error_ratio, 3),

            "measurement_mode": "direct" if measured_signal_count else flow.get("measurement_mode", "synthetic"),

            "measured_signal_count": measured_signal_count,

            "source_families": sorted({*(flow.get("source_families") or []), *flow_families.get(region, set())}),

            "status": _flow_status(congestion_index, attack_index, packet_loss),

            "severity": _severity(max(congestion_index, attack_index, packet_loss * 8.0)),

            "confidence_ratio": round(_clamp(max(_safe_float(flow.get("confidence_ratio"), 0.5), 0.52 + (0.08 if measured_signal_count else 0.0) + min(0.18, len(flow_families.get(region, set())) * 0.04)), 0.0, 0.99), 2),

        })

        flows.append(flow)



    peak_throughput = max((_safe_float(row.get("throughput_gbps")) for row in flows), default=1.0)

    for flow in flows:

        flow["traffic_share"] = round(_safe_float(flow.get("throughput_gbps")) / peak_throughput, 3) if peak_throughput else 0.0

    flows.sort(key=lambda row: (_safe_float(row.get("anomaly_score")), _safe_float(row.get("throughput_gbps"))), reverse=True)

    payload["flows"] = flows[:18]



    countries: list[dict[str, Any]] = []

    for item in (payload.get("countries") or []):

        country = dict(item)

        code = _normalize_country(country.get("country"))

        metrics = country_metrics.get(code) or {}

        related_flows = [flow for flow in payload.get("flows") or [] if code in {flow.get("origin"), flow.get("destination")}]

        availability = _weighted_average(metrics.get("subscriber_availability_ratio") or [], max(0.0, 1.0 - _safe_float(country.get("shutdown_risk")) / 100.0))

        fixed_ratio = _weighted_average(metrics.get("fixed_reachability_ratio") or [], availability)

        mobile_ratio = _weighted_average(metrics.get("mobile_reachability_ratio") or [], availability)

        throughput_drop = _weighted_average(metrics.get("throughput_drop_pct") or [], 0.0)

        outage_reports = _weighted_average(metrics.get("outage_report_count") or [], 0.0)

        impacted_users = max(_weighted_average(metrics.get("subscribers_impacted_m") or [], 0.0), _safe_float((prior_shutdowns.get(code) or {}).get("estimated_users_impacted_m"), 0.0))

        control_plane = max(_max_value(metrics.get("control_plane_incident_score") or [], 0.0), max((_safe_float(flow.get("control_plane_incident_score")) for flow in related_flows), default=0.0))

        dns_error = max(_max_value(metrics.get("dns_error_ratio") or [], 0.0), max((_safe_float(flow.get("dns_error_ratio")) for flow in related_flows), default=0.0))

        average_flow_congestion = sum(_safe_float(flow.get("congestion_index")) for flow in related_flows) / max(len(related_flows), 1) if related_flows else _safe_float(country.get("congestion_index"))

        peak_flow_attack = max((_safe_float(flow.get("attack_index")) for flow in related_flows), default=_safe_float(country.get("attack_index")))

        withdrawal_pressure = sum(_safe_float(flow.get("withdrawn_prefix_count")) for flow in related_flows)

        packet_flow = max(_safe_float(country.get("packet_flow_gbps")), sum(_safe_float(flow.get("throughput_gbps")) for flow in related_flows) / max(1.0, 1.5 if related_flows else 1.0))

        congestion_index = round(_clamp(max(_safe_float(country.get("congestion_index")) * 0.62, average_flow_congestion, throughput_drop * 0.88), 0.0, 100.0), 1)

        attack_index = round(_clamp(max(_safe_float(country.get("attack_index")) * 0.6, peak_flow_attack, 100.0 * (0.32 * control_plane + 0.18 * dns_error)), 0.0, 100.0), 1)

        shutdown_risk = round(_clamp(max(_safe_float(country.get("shutdown_risk")) * 0.54, 100.0 * (0.34 * (1.0 - min(availability, fixed_ratio, mobile_ratio)) + 0.2 * (throughput_drop / 100.0) + 0.14 * control_plane + 0.12 * dns_error + 0.1 * min(1.0, withdrawal_pressure / 12.0) + 0.1 * min(1.0, average_flow_congestion / 100.0))), 0.0, 100.0), 1)

        country.update({

            "packet_flow_gbps": round(packet_flow, 1),

            "congestion_index": congestion_index,

            "attack_index": attack_index,

            "shutdown_risk": shutdown_risk,

            "status": _country_status(congestion_index, attack_index, shutdown_risk),

            "severity": _severity(max(congestion_index, attack_index, shutdown_risk)),

            "advisory": _country_advisory({"status": _country_status(congestion_index, attack_index, shutdown_risk)}),

            "confidence_ratio": round(_clamp(max(_safe_float(country.get("confidence_ratio"), 0.5), 0.54 + min(0.24, len(related_flows) * 0.03)), 0.0, 0.99), 2),

            "subscriber_availability_ratio": round(availability, 3),

            "fixed_reachability_ratio": round(fixed_ratio, 3),

            "mobile_reachability_ratio": round(mobile_ratio, 3),

            "throughput_drop_pct": round(throughput_drop, 2),

            "outage_report_count": round(outage_reports, 1),

            "subscribers_impacted_m": round(max(0.0, impacted_users), 2),

            "control_plane_incident_score": round(control_plane, 3),

            "dns_error_ratio": round(dns_error, 3),

            "freshness_sec": int(min([country.get("freshness_sec") or 999] + [flow.get("freshness_sec") or 999 for flow in related_flows])),

        })

        countries.append(country)

    countries.sort(key=lambda row: max(_safe_float(row.get("shutdown_risk")), _safe_float(row.get("attack_index")), _safe_float(row.get("congestion_index"))), reverse=True)

    payload["countries"] = countries



    attacks: list[dict[str, Any]] = []

    for flow in payload.get("flows") or []:

        attack_signal_count = _flow_attack_signal_count(flow)

        if attack_signal_count < int(threshold_value("alert_filters", "min_attack_signals", 2)) and _safe_float(flow.get("attack_index")) < float(threshold_value("alert_filters", "attack_index_gate", 66.0)) and _safe_float(flow.get("hijack_suspect_score")) < float(threshold_value("alert_filters", "attack_hijack_gate", 0.26)):

            continue

        flow_key = str(flow.get("id") or f"{flow.get('origin','').lower()}-{flow.get('destination','').lower()}")

        prior = prior_attacks.get(flow_key.lower()) or {}

        started_at = str(prior.get("started_at") or (generated_at - timedelta(minutes=5 + (_seed(flow_key) % 95))).isoformat())

        attacks.append({

            "id": str(prior.get("id") or f"attack-{flow_key}"),

            "origin": flow.get("origin"),

            "origin_label": flow.get("origin_label"),

            "target": flow.get("destination"),

            "target_label": flow.get("destination_label"),

            "severity": _severity(_safe_float(flow.get("attack_index"))),

            "status": "active" if _safe_float(flow.get("attack_index")) >= float(threshold_value("alert_filters", "attack_active_index", 74.0)) or attack_signal_count >= int(threshold_value("alert_filters", "attack_active_signals", 4)) else "investigate" if attack_signal_count >= int(threshold_value("alert_filters", "attack_investigate_signals", 3)) else "monitoring",

            "vector": _attack_vector(flow_key, _safe_float(flow.get("hijack_suspect_score")), _safe_float(flow.get("dns_error_ratio")), _safe_float(flow.get("control_plane_incident_score")), _safe_float(flow.get("edge_error_rate"))),

            "attack_index": _safe_float(flow.get("attack_index")),

            "intensity_gbps": round(_safe_float(flow.get("throughput_gbps")) * (0.24 + (_safe_float(flow.get("attack_index")) / 170.0)), 1),

            "packets_mps": round(_safe_float(flow.get("throughput_gbps")) * (0.38 + (_safe_float(flow.get("attack_index")) / 120.0)), 1),

            "confidence_ratio": round(_clamp(max(_safe_float(prior.get("confidence_ratio"), 0.5), 0.5 + min(0.26, attack_signal_count * 0.08) + min(0.12, len(flow.get("source_families") or []) * 0.03)), 0.0, 0.99), 2),

            "attack_signal_count": attack_signal_count,

            "started_at": started_at,

            "flow_id": flow_key,

            "hijack_suspect_score": round(_safe_float(flow.get("hijack_suspect_score")), 3),

            "control_plane_incident_score": round(_safe_float(flow.get("control_plane_incident_score")), 3),

            "source_families": flow.get("source_families") or [],

        })

    attacks.sort(key=lambda row: (_safe_float(row.get("attack_index")), _safe_float(row.get("intensity_gbps"))), reverse=True)

    payload["cyber_attacks"] = attacks[:8]



    shutdowns: list[dict[str, Any]] = []

    for country in payload.get("countries") or []:

        shutdown_signal_count = _country_shutdown_signal_count(country)

        if shutdown_signal_count < int(threshold_value("alert_filters", "min_shutdown_signals", 2)) and _safe_float(country.get("shutdown_risk")) < float(threshold_value("alert_filters", "shutdown_risk_gate", 64.0)) and _safe_float(country.get("subscriber_availability_ratio"), 1.0) > float(threshold_value("alert_filters", "shutdown_availability_gate", 0.78)):

            continue

        code = str(country.get("country") or "").upper()

        prior = prior_shutdowns.get(code) or {}

        started_at = str(prior.get("started_at") or (generated_at - timedelta(minutes=12 + (_seed(code) % 180))).isoformat())

        availability = min(_safe_float(country.get("subscriber_availability_ratio"), 1.0), _safe_float(country.get("fixed_reachability_ratio"), 1.0), _safe_float(country.get("mobile_reachability_ratio"), 1.0))

        if availability <= float(threshold_value("alert_filters", "shutdown_reason_availability", 0.65)):

            reason = "Measured fixed and mobile reachability fell sharply, indicating a high-probability access-network impairment."

        elif _safe_float(country.get("control_plane_incident_score")) >= float(threshold_value("alert_filters", "shutdown_reason_control_plane", 0.18)):

            reason = "Direct control-plane and DNS degradation is corroborating national shutdown risk."

        else:

            reason = "Measured throughput loss and outage reports indicate a sustained internet-continuity incident."

        shutdowns.append({

            "id": str(prior.get("id") or f"shutdown-{code.lower()}"),

            "country": code,

            "label": country.get("label"),

            "severity": _severity(_safe_float(country.get("shutdown_risk"))),

            "status": "active" if _safe_float(country.get("shutdown_risk")) >= float(threshold_value("alert_filters", "shutdown_active_risk", 74.0)) or availability <= float(threshold_value("alert_filters", "shutdown_active_availability", 0.68)) or shutdown_signal_count >= int(threshold_value("alert_filters", "shutdown_active_signals", 4)) else "watch",

            "shutdown_risk": _safe_float(country.get("shutdown_risk")),

            "estimated_users_impacted_m": round(max(_safe_float(country.get("subscribers_impacted_m")), _safe_float(prior.get("estimated_users_impacted_m"), 0.0), _safe_float(country.get("packet_flow_gbps")) * 0.02), 1),

            "confidence_ratio": round(_clamp(max(_safe_float(prior.get("confidence_ratio"), 0.48), 0.52 + min(0.28, shutdown_signal_count * 0.07) + (0.08 if availability < 0.8 else 0.0)), 0.0, 0.99), 2),

            "shutdown_signal_count": shutdown_signal_count,

            "reason": reason,

            "started_at": started_at,

            "advisory": country.get("advisory"),

            "subscriber_availability_ratio": round(_safe_float(country.get("subscriber_availability_ratio"), 1.0), 3),

            "fixed_reachability_ratio": round(_safe_float(country.get("fixed_reachability_ratio"), 1.0), 3),

            "mobile_reachability_ratio": round(_safe_float(country.get("mobile_reachability_ratio"), 1.0), 3),

            "throughput_drop_pct": round(_safe_float(country.get("throughput_drop_pct")), 2),

            "control_plane_incident_score": round(_safe_float(country.get("control_plane_incident_score")), 3),

            "source_families": ["isp_telemetry", "bgp_routing", "cloud_metrics"],

        })

    shutdowns.sort(key=lambda row: _safe_float(row.get("shutdown_risk")), reverse=True)

    payload["shutdown_alerts"] = shutdowns[:8]

    payload["top_corridors"] = sorted(payload.get("flows") or [], key=lambda row: (_safe_float(row.get("congestion_index")), _safe_float(row.get("attack_index")), _safe_float(row.get("throughput_gbps"))), reverse=True)[:8]



    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

    healthy_countries = sum(1 for country in payload.get("countries") or [] if str(country.get("status") or "") == "stable")

    degraded_countries = len(payload.get("countries") or []) - healthy_countries

    global_packet_volume = round(sum(_safe_float(flow.get("throughput_gbps")) for flow in payload.get("flows") or []), 1)

    throughput_weight = sum(_safe_float(flow.get("throughput_gbps")) for flow in payload.get("flows") or []) or 1.0

    global_congestion = round(sum(_safe_float(flow.get("congestion_index")) * _safe_float(flow.get("throughput_gbps")) for flow in payload.get("flows") or []) / throughput_weight, 1) if payload.get("flows") else 0.0

    attack_index = round(sum(_safe_float(flow.get("attack_index")) for flow in payload.get("flows") or []) / max(len(payload.get("flows") or []), 1), 1)

    rerouted_prefixes = int(round(sum(max(0.0, _safe_float(flow.get("withdrawn_prefix_count"))) + max(0.0, _safe_float(flow.get("reroute_factor"), 1.0) - 1.0) * 100.0 for flow in payload.get("flows") or [])))

    monitored_prefixes = int(round(sum(_safe_float(flow.get("monitored_prefix_count")) for flow in payload.get("flows") or []))) or int(summary.get("monitored_prefixes") or 0)

    source_stage, direct_families, measurement_modes = _summary_stage(source_health, str(summary.get("source_stage") or "phase-1-derived"))

    summary.update({

        "source_stage": source_stage,

        "source_status": "direct-live" if len(direct_families) >= 4 else "direct-hybrid" if direct_families else str(summary.get("source_status") or "limited"),

        "healthy_countries": healthy_countries,

        "degraded_countries": degraded_countries,

        "shutdown_alerts": len(payload.get("shutdown_alerts") or []),

        "active_attack_paths": len(payload.get("cyber_attacks") or []),

        "global_packet_volume_gbps": global_packet_volume,

        "global_congestion_index": global_congestion,

        "cyber_attack_index": attack_index,

        "rerouted_prefixes": rerouted_prefixes,

        "monitored_prefixes": monitored_prefixes,

    })

    payload["summary"] = summary



    generated_from = payload.get("generated_from") if isinstance(payload.get("generated_from"), dict) else {}

    generated_from.update({

        "source_stage": source_stage,

        "direct_source_families": direct_families,

        "measurement_modes": measurement_modes,

        "note": "Internet-map corridors are now overlaid with direct BGP, CDN, ISP, and cloud telemetry when configured feeds are available.",

    })

    payload["generated_from"] = generated_from

    return payload





def build_internet_replay_analytics(

    history_rows: list[dict[str, Any]],

    country_snapshots_collection,

    flow_snapshots_collection,

    alert_collection,

    *,

    hours: int = 24,

    limit: int = 6,

) -> dict[str, Any]:

    sorted_history = sorted(

        [row for row in history_rows if row.get("captured_at")],

        key=lambda row: str(row.get("captured_at")),

    )

    current = sorted_history[-1] if sorted_history else {}

    baseline = sorted_history[0] if sorted_history else {}

    congestion_delta = round(_safe_float(current.get("global_congestion_index")) - _safe_float(baseline.get("global_congestion_index")), 1) if sorted_history else 0.0

    attack_delta = round(_safe_float(current.get("cyber_attack_index")) - _safe_float(baseline.get("cyber_attack_index")), 1) if sorted_history else 0.0

    trend = "rising" if congestion_delta > 4.0 or attack_delta > 4.0 else "cooling" if congestion_delta < -4.0 and attack_delta < -2.0 else "steady"

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(hours, 1))).isoformat()

    top_countries: list[dict[str, Any]] = []

    top_corridors: list[dict[str, Any]] = []

    alert_counts = {"attack": 0, "shutdown": 0}

    try:

        country_docs = list(country_snapshots_collection.find({"captured_at": {"$gte": cutoff}}, {"_id": 0, "country": 1, "label": 1, "shutdown_risk": 1, "attack_index": 1, "congestion_index": 1, "status": 1}).limit(6000))

        country_rollup: dict[str, dict[str, Any]] = {}

        for row in country_docs:

            code = _normalize_country(row.get("country"))

            current_row = country_rollup.get(code)

            score = max(_safe_float(row.get("shutdown_risk")), _safe_float(row.get("attack_index")), _safe_float(row.get("congestion_index")))

            if not current_row or score > current_row["score"]:

                country_rollup[code] = {

                    "country": code,

                    "label": row.get("label") or code,

                    "score": round(score, 1),

                    "status": row.get("status"),

                }

        top_countries = sorted(country_rollup.values(), key=lambda item: _safe_float(item.get("score")), reverse=True)[:limit]

    except Exception:

        top_countries = []

    try:

        flow_docs = list(flow_snapshots_collection.find({"captured_at": {"$gte": cutoff}}, {"_id": 0, "id": 1, "origin": 1, "destination": 1, "congestion_index": 1, "attack_index": 1, "reroute_factor": 1, "packet_loss_pct": 1}).limit(6000))

        flow_rollup: dict[str, dict[str, Any]] = {}

        for row in flow_docs:

            key = str(row.get("id") or "")

            score = max(_safe_float(row.get("congestion_index")), _safe_float(row.get("attack_index")))

            if not key:

                continue

            current_row = flow_rollup.get(key)

            if not current_row or score > current_row["score"]:

                flow_rollup[key] = {

                    "id": key,

                    "label": f"{row.get('origin')} to {row.get('destination')}",

                    "score": round(score, 1),

                    "reroute_factor": round(_safe_float(row.get("reroute_factor"), 1.0), 2),

                    "packet_loss_pct": round(_safe_float(row.get("packet_loss_pct")), 2),

                }

        top_corridors = sorted(flow_rollup.values(), key=lambda item: _safe_float(item.get("score")), reverse=True)[:limit]

    except Exception:

        top_corridors = []

    try:

        alert_counts = {

            "attack": int(alert_collection.count_documents({"captured_at": {"$gte": cutoff}, "alert_type": "attack"})),

            "shutdown": int(alert_collection.count_documents({"captured_at": {"$gte": cutoff}, "alert_type": "shutdown"})),

        }

    except Exception:

        pass

    return {

        "window_hours": int(max(hours, 1)),

        "history_points": len(sorted_history),

        "trend_direction": trend,

        "congestion_delta": congestion_delta,

        "attack_delta": attack_delta,

        "peak_congestion_index": max((_safe_float(row.get("global_congestion_index")) for row in sorted_history), default=0.0),

        "peak_attack_index": max((_safe_float(row.get("cyber_attack_index")) for row in sorted_history), default=0.0),

        "peak_shutdown_alerts": max((int(row.get("shutdown_alerts") or 0) for row in sorted_history), default=0),

        "top_disrupted_countries": top_countries,

        "top_contested_corridors": top_corridors,

        "alert_counts": alert_counts,

    }



