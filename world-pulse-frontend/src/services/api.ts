import axios, { AxiosHeaders } from "axios";

const CONFIGURED_API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const LOCAL_DEV_PRIMARY_URL_PATTERN = /^http:\/\/127\.0\.0\.1:(8000|8001|8002)\/?$/;
const LOCAL_DEV_DEFAULT_API_URL = "http://127.0.0.1:8000";
export const LOCAL_DEV_RECOVERY_API_URL = "http://127.0.0.1:8002";
const EXPLICIT_FALLBACK_API_URL = String(import.meta.env.VITE_API_FALLBACK_URL || "").trim();
const PRIMARY_API_URL = import.meta.env.DEV && CONFIGURED_API_URL === LOCAL_DEV_DEFAULT_API_URL
  ? LOCAL_DEV_RECOVERY_API_URL
  : CONFIGURED_API_URL;
const FALLBACK_API_URL = EXPLICIT_FALLBACK_API_URL
  || (import.meta.env.DEV && PRIMARY_API_URL === LOCAL_DEV_RECOVERY_API_URL ? LOCAL_DEV_DEFAULT_API_URL : "")
  || (import.meta.env.DEV && PRIMARY_API_URL !== LOCAL_DEV_RECOVERY_API_URL && LOCAL_DEV_PRIMARY_URL_PATTERN.test(CONFIGURED_API_URL)
    ? LOCAL_DEV_RECOVERY_API_URL
    : "")
  || "";
const API_KEY = String(import.meta.env.VITE_API_KEY || "").trim();
const USE_MOCK_API = String(import.meta.env.VITE_USE_MOCK_API || "").trim().toLowerCase() === "true";
const ACTIVE_API_URL_STORAGE_KEY = "wp_active_api_url";

function readPersistedApiUrl(): string {
  if (typeof window === "undefined") return PRIMARY_API_URL;
  const stored = String(window.localStorage.getItem(ACTIVE_API_URL_STORAGE_KEY) || "").trim();
  if (!stored || stored === PRIMARY_API_URL) return PRIMARY_API_URL;
  // Always recover to primary on a fresh page load. Fallback should only be used
  // transiently for in-session network failure, not persisted across reloads.
  window.localStorage.setItem(ACTIVE_API_URL_STORAGE_KEY, PRIMARY_API_URL);
  return PRIMARY_API_URL;
}

function setActiveApiUrl(url: string): void {
  activeApiUrl = url;
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACTIVE_API_URL_STORAGE_KEY, url);
}

let activeApiUrl = readPersistedApiUrl();

export const getActiveApiUrl = (): string => activeApiUrl;

function isNetworkFailure(error: unknown): boolean {
  const e = (error ?? {}) as { code?: string; message?: string; response?: unknown };
  if (e.response) return false;
  const code = String(e.code ?? "").toUpperCase();
  const message = String(e.message ?? "").toLowerCase();
  return code === "ECONNABORTED"
    || code === "ERR_NETWORK"
    || code === "ERR_CONNECTION_RESET"
    || message.includes("network error")
    || message.includes("connection refused")
    || message.includes("connection reset")
    || message.includes("timeout");
}

function shouldUseFallbackApi(): boolean {
  return Boolean(FALLBACK_API_URL && FALLBACK_API_URL !== PRIMARY_API_URL);
}

const MOCK_RISK_MAP: RiskMapPoint[] = [
  {
    country: "USA",
    risk: 0.62,
    validated_today: true,
    data_quality: "synthetic",
    source_count: 6,
    public_attention_score: 0.66,
    narrative_velocity_score: 0.58,
    coordination_risk_score: 0.31,
    mobility_disruption_score: 0.22,
    logistics_stress_score: 0.28,
    household_stress_score: 0.49,
    fuel_price_pressure: 0.43,
    food_price_pressure: 0.36,
    labor_stress_score: 0.29,
    fx_pressure_score: 0.17,
    remittance_stress_score: 0.12,
    energy_stress_score: 0.34,
    external_signal_freshness: 0.78,
    direct_behavior_score: 0.57,
    contextual_pressure_score: 0.41,
    evidence_quality_score: 0.64,
  },
  {
    country: "IND",
    risk: 0.68,
    validated_today: true,
    data_quality: "synthetic",
    source_count: 7,
    public_attention_score: 0.71,
    narrative_velocity_score: 0.63,
    coordination_risk_score: 0.39,
    mobility_disruption_score: 0.27,
    logistics_stress_score: 0.34,
    household_stress_score: 0.56,
    fuel_price_pressure: 0.51,
    food_price_pressure: 0.48,
    labor_stress_score: 0.42,
    fx_pressure_score: 0.29,
    remittance_stress_score: 0.22,
    energy_stress_score: 0.44,
    external_signal_freshness: 0.8,
    direct_behavior_score: 0.61,
    contextual_pressure_score: 0.47,
    evidence_quality_score: 0.66,
  },
  {
    country: "LKA",
    risk: 0.59,
    validated_today: true,
    data_quality: "synthetic",
    source_count: 5,
    public_attention_score: 0.61,
    narrative_velocity_score: 0.52,
    coordination_risk_score: 0.28,
    mobility_disruption_score: 0.18,
    logistics_stress_score: 0.26,
    household_stress_score: 0.54,
    fuel_price_pressure: 0.47,
    food_price_pressure: 0.41,
    labor_stress_score: 0.33,
    fx_pressure_score: 0.38,
    remittance_stress_score: 0.35,
    energy_stress_score: 0.45,
    external_signal_freshness: 0.72,
    direct_behavior_score: 0.55,
    contextual_pressure_score: 0.42,
    evidence_quality_score: 0.6,
  },
  {
    country: "GBR",
    risk: 0.46,
    validated_today: true,
    data_quality: "synthetic",
    source_count: 6,
    public_attention_score: 0.48,
    narrative_velocity_score: 0.37,
    coordination_risk_score: 0.19,
    mobility_disruption_score: 0.13,
    logistics_stress_score: 0.18,
    household_stress_score: 0.31,
    fuel_price_pressure: 0.28,
    food_price_pressure: 0.24,
    labor_stress_score: 0.2,
    fx_pressure_score: 0.14,
    remittance_stress_score: 0.09,
    energy_stress_score: 0.25,
    external_signal_freshness: 0.76,
    direct_behavior_score: 0.39,
    contextual_pressure_score: 0.29,
    evidence_quality_score: 0.67,
  },
  {
    country: "DEU",
    risk: 0.43,
    validated_today: true,
    data_quality: "synthetic",
    source_count: 6,
    public_attention_score: 0.42,
    narrative_velocity_score: 0.34,
    coordination_risk_score: 0.16,
    mobility_disruption_score: 0.14,
    logistics_stress_score: 0.19,
    household_stress_score: 0.29,
    fuel_price_pressure: 0.24,
    food_price_pressure: 0.21,
    labor_stress_score: 0.18,
    fx_pressure_score: 0.13,
    remittance_stress_score: 0.08,
    energy_stress_score: 0.22,
    external_signal_freshness: 0.77,
    direct_behavior_score: 0.36,
    contextual_pressure_score: 0.27,
    evidence_quality_score: 0.69,
  },
  {
    country: "BRA",
    risk: 0.57,
    validated_today: true,
    data_quality: "synthetic",
    source_count: 5,
    public_attention_score: 0.57,
    narrative_velocity_score: 0.49,
    coordination_risk_score: 0.24,
    mobility_disruption_score: 0.16,
    logistics_stress_score: 0.22,
    household_stress_score: 0.44,
    fuel_price_pressure: 0.37,
    food_price_pressure: 0.32,
    labor_stress_score: 0.27,
    fx_pressure_score: 0.25,
    remittance_stress_score: 0.11,
    energy_stress_score: 0.3,
    external_signal_freshness: 0.7,
    direct_behavior_score: 0.5,
    contextual_pressure_score: 0.35,
    evidence_quality_score: 0.58,
  },
];

const mockCoverage = (): RiskMapCoverage => ({
  total: 233,
  verified: MOCK_RISK_MAP.length,
  no_data: 233 - MOCK_RISK_MAP.length,
  stale: 0,
  remaining: 233 - MOCK_RISK_MAP.length,
  coverage_pct: Number(((MOCK_RISK_MAP.length / 233) * 100).toFixed(1)),
  latest_validation: { status: "mock", sample_count: MOCK_RISK_MAP.length, brier_score: 0.0 },
});

const mockLiveFeed = (): LiveCommandFeed => ({
  incidents: [
    "Local API offline: showing synthetic dashboard data",
    "Risk map is running in offline fallback mode",
    "Start backend on :8000 to restore live intelligence feeds",
  ],
  ingestionHeartbeatSec: 0,
  modelDrift: 0.21,
  lastUpdated: new Date().toISOString(),
});

const mockLatestGlobal = (): LatestGlobalResponse => ({
  timestamp: new Date().toISOString(),
  mode: "offline-fallback",
  version: 1,
  features: {
    timestamp: new Date().toISOString(),
    news_sentiment: 0.12,
    gdelt_sentiment: 0.09,
    crypto_return: 0.01,
    crypto_volatility: 0.34,
    stock_return: 0.02,
    stock_volatility: 0.28,
    weather_anomaly: 0.19,
    global_risk_score: 0.54,
    global_mood_score: 0.58,
    global_mood_confidence: 0.72,
    global_mood_uncertainty: 0.11,
    global_mood_verified_countries: MOCK_RISK_MAP.length,
    global_mood_eligible_countries: 233,
    global_mood_contributing_countries: MOCK_RISK_MAP.length,
    global_mood_used_countries: MOCK_RISK_MAP.length,
    global_mood_excluded_countries: 233 - MOCK_RISK_MAP.length,
    forecast_risk_score: 0.56,
    forecast_risk_delta: 0.02,
    forecast_confidence: 0.64,
    forecast_horizon_hours: 24,
    top_topics: ["offline fallback", "synthetic dashboard", "backend unavailable"],
  },
});

const mockInternetMapSnapshot = (): InternetMapSnapshot => {
  const generatedAt = new Date().toISOString();
  const countryLookup = Object.fromEntries(MOCK_RISK_MAP.map((entry) => [entry.country, entry]));
  const countries: InternetMapCountry[] = [
    {
      country: "USA",
      label: "United States",
      lat: 39.8,
      lon: -98.6,
      risk: Number(countryLookup.USA?.risk ?? 0.62),
      data_quality: "synthetic",
      validated_today: true,
      source_count: 6,
      freshness_ratio: 0.78,
      evidence_quality_score: 0.66,
      packet_flow_gbps: 814.2,
      congestion_index: 41.2,
      attack_index: 52.4,
      shutdown_risk: 28.5,
      stability_score: 61.4,
      signal_strength: 0.92,
      status: "stable",
      severity: "guarded",
      advisory: "Monitor Atlantic corridors for sustained edge saturation.",
    },
    {
      country: "GBR",
      label: "United Kingdom",
      lat: 55.4,
      lon: -3.4,
      risk: Number(countryLookup.GBR?.risk ?? 0.46),
      data_quality: "synthetic",
      validated_today: true,
      source_count: 6,
      freshness_ratio: 0.76,
      evidence_quality_score: 0.67,
      packet_flow_gbps: 642.8,
      congestion_index: 35.7,
      attack_index: 48.1,
      shutdown_risk: 24.2,
      stability_score: 67.3,
      signal_strength: 0.83,
      status: "stable",
      severity: "guarded",
      advisory: "Watch transatlantic congestion drift and route rebalancing.",
    },
    {
      country: "DEU",
      label: "Germany",
      lat: 51.2,
      lon: 10.4,
      risk: Number(countryLookup.DEU?.risk ?? 0.43),
      data_quality: "synthetic",
      validated_today: true,
      source_count: 6,
      freshness_ratio: 0.77,
      evidence_quality_score: 0.69,
      packet_flow_gbps: 611.9,
      congestion_index: 37.9,
      attack_index: 44.8,
      shutdown_risk: 25.4,
      stability_score: 65.8,
      signal_strength: 0.8,
      status: "stable",
      severity: "guarded",
      advisory: "Confirm whether continental congestion is correlated with transit maintenance.",
    },
    {
      country: "IND",
      label: "India",
      lat: 20.6,
      lon: 78.9,
      risk: Number(countryLookup.IND?.risk ?? 0.68),
      data_quality: "synthetic",
      validated_today: true,
      source_count: 7,
      freshness_ratio: 0.8,
      evidence_quality_score: 0.66,
      packet_flow_gbps: 922.4,
      congestion_index: 58.4,
      attack_index: 63.7,
      shutdown_risk: 46.8,
      stability_score: 42.3,
      signal_strength: 1.06,
      status: "volatile",
      severity: "elevated",
      advisory: "Correlate regional route drift with packet loss before escalation.",
    },
    {
      country: "LKA",
      label: "Sri Lanka",
      lat: 7.9,
      lon: 80.7,
      risk: Number(countryLookup.LKA?.risk ?? 0.59),
      data_quality: "synthetic",
      validated_today: true,
      source_count: 5,
      freshness_ratio: 0.72,
      evidence_quality_score: 0.6,
      packet_flow_gbps: 402.6,
      congestion_index: 63.9,
      attack_index: 49.7,
      shutdown_risk: 68.3,
      stability_score: 35.9,
      signal_strength: 0.88,
      status: "congested",
      severity: "high",
      advisory: "Watch national gateway continuity and mobile backbone availability.",
    },
    {
      country: "BRA",
      label: "Brazil",
      lat: -14.2,
      lon: -51.9,
      risk: Number(countryLookup.BRA?.risk ?? 0.57),
      data_quality: "synthetic",
      validated_today: true,
      source_count: 5,
      freshness_ratio: 0.7,
      evidence_quality_score: 0.58,
      packet_flow_gbps: 583.5,
      congestion_index: 49.4,
      attack_index: 55.6,
      shutdown_risk: 33.2,
      stability_score: 54.1,
      signal_strength: 0.82,
      status: "stable",
      severity: "guarded",
      advisory: "Review South Atlantic corridor saturation and attack noise.",
    },
  ];

  const flows: InternetMapFlow[] = [
    {
      id: "usa-gbr",
      origin: "USA",
      origin_label: "United States",
      origin_lat: 39.8,
      origin_lon: -98.6,
      destination: "GBR",
      destination_label: "United Kingdom",
      destination_lat: 55.4,
      destination_lon: -3.4,
      throughput_gbps: 702.4,
      congestion_index: 44.1,
      attack_index: 54.2,
      latency_ms: 88.4,
      packet_loss_pct: 2.34,
      reroute_factor: 1.19,
      anomaly_score: 52.1,
      traffic_share: 0.94,
      status: "stable",
      severity: "guarded",
    },
    {
      id: "usa-bra",
      origin: "USA",
      origin_label: "United States",
      origin_lat: 39.8,
      origin_lon: -98.6,
      destination: "BRA",
      destination_label: "Brazil",
      destination_lat: -14.2,
      destination_lon: -51.9,
      throughput_gbps: 618.6,
      congestion_index: 47.9,
      attack_index: 57.6,
      latency_ms: 95.1,
      packet_loss_pct: 2.71,
      reroute_factor: 1.24,
      anomaly_score: 57.8,
      traffic_share: 0.83,
      status: "degraded",
      severity: "elevated",
    },
    {
      id: "gbr-deu",
      origin: "GBR",
      origin_label: "United Kingdom",
      origin_lat: 55.4,
      origin_lon: -3.4,
      destination: "DEU",
      destination_label: "Germany",
      destination_lat: 51.2,
      destination_lon: 10.4,
      throughput_gbps: 521.5,
      congestion_index: 39.2,
      attack_index: 46.3,
      latency_ms: 42.8,
      packet_loss_pct: 1.88,
      reroute_factor: 1.11,
      anomaly_score: 44.7,
      traffic_share: 0.7,
      status: "stable",
      severity: "guarded",
    },
    {
      id: "deu-ind",
      origin: "DEU",
      origin_label: "Germany",
      origin_lat: 51.2,
      origin_lon: 10.4,
      destination: "IND",
      destination_label: "India",
      destination_lat: 20.6,
      destination_lon: 78.9,
      throughput_gbps: 744.9,
      congestion_index: 57.1,
      attack_index: 63.8,
      latency_ms: 122.7,
      packet_loss_pct: 3.46,
      reroute_factor: 1.31,
      anomaly_score: 66.3,
      traffic_share: 1,
      status: "degraded",
      severity: "elevated",
    },
    {
      id: "ind-lka",
      origin: "IND",
      origin_label: "India",
      origin_lat: 20.6,
      origin_lon: 78.9,
      destination: "LKA",
      destination_label: "Sri Lanka",
      destination_lat: 7.9,
      destination_lon: 80.7,
      throughput_gbps: 418.2,
      congestion_index: 65.4,
      attack_index: 58.6,
      latency_ms: 38.6,
      packet_loss_pct: 4.52,
      reroute_factor: 1.38,
      anomaly_score: 70.5,
      traffic_share: 0.56,
      status: "degraded",
      severity: "high",
    },
    {
      id: "usa-ind",
      origin: "USA",
      origin_label: "United States",
      origin_lat: 39.8,
      origin_lon: -98.6,
      destination: "IND",
      destination_label: "India",
      destination_lat: 20.6,
      destination_lon: 78.9,
      throughput_gbps: 736.8,
      congestion_index: 55.8,
      attack_index: 66.1,
      latency_ms: 161.5,
      packet_loss_pct: 3.82,
      reroute_factor: 1.34,
      anomaly_score: 67.9,
      traffic_share: 0.99,
      status: "degraded",
      severity: "elevated",
    },
  ];

  const cyberAttacks: InternetMapCyberAttack[] = [
    {
      id: "attack-usa-ind",
      origin: "USA",
      origin_label: "United States",
      target: "IND",
      target_label: "India",
      severity: "high",
      status: "active",
      vector: "Volumetric DDoS",
      attack_index: 66.1,
      intensity_gbps: 409.3,
      packets_mps: 678.4,
      confidence_ratio: 0.78,
      started_at: new Date(Date.now() - 18 * 60_000).toISOString(),
    },
    {
      id: "attack-deu-ind",
      origin: "DEU",
      origin_label: "Germany",
      target: "IND",
      target_label: "India",
      severity: "elevated",
      status: "monitoring",
      vector: "BGP Hijack Pressure",
      attack_index: 63.8,
      intensity_gbps: 338.7,
      packets_mps: 611.2,
      confidence_ratio: 0.73,
      started_at: new Date(Date.now() - 31 * 60_000).toISOString(),
    },
    {
      id: "attack-usa-bra",
      origin: "USA",
      origin_label: "United States",
      target: "BRA",
      target_label: "Brazil",
      severity: "elevated",
      status: "monitoring",
      vector: "DNS Amplification",
      attack_index: 57.6,
      intensity_gbps: 252.4,
      packets_mps: 499.8,
      confidence_ratio: 0.67,
      started_at: new Date(Date.now() - 43 * 60_000).toISOString(),
    },
  ];

  const shutdownAlerts: InternetMapShutdownAlert[] = [
    {
      id: "shutdown-lka",
      country: "LKA",
      label: "Sri Lanka",
      severity: "high",
      status: "watch",
      shutdown_risk: 68.3,
      estimated_users_impacted_m: 9.4,
      confidence_ratio: 0.72,
      reason: "Compounded energy, logistics, and congestion stress is elevating shutdown risk.",
      started_at: new Date(Date.now() - 54 * 60_000).toISOString(),
      advisory: "Watch national gateway continuity and mobile backbone availability.",
    },
    {
      id: "shutdown-ind",
      country: "IND",
      label: "India",
      severity: "elevated",
      status: "watch",
      shutdown_risk: 46.8,
      estimated_users_impacted_m: 18.2,
      confidence_ratio: 0.61,
      reason: "Regional congestion and route drift warrant shutdown monitoring in affected corridors.",
      started_at: new Date(Date.now() - 77 * 60_000).toISOString(),
      advisory: "Correlate route drift with subscriber-reachability changes before escalating.",
    },
  ];

  const sourceHealth: InternetMapSourceHealth[] = [
    {
      source: "BGP routing",
      stage: "derived",
      status: "degraded",
      coverage_ratio: 0.63,
      confidence_ratio: 0.58,
      freshness_sec: 34,
      detail: "Currently inferred from route instability proxies until direct routing collectors are connected.",
    },
    {
      source: "CDN traffic",
      stage: "derived",
      status: "healthy",
      coverage_ratio: 0.71,
      confidence_ratio: 0.66,
      freshness_sec: 24,
      detail: "Edge load is represented with derived congestion and attention signals in phase 1.",
    },
    {
      source: "ISP telemetry",
      stage: "derived",
      status: "limited",
      coverage_ratio: 0.52,
      confidence_ratio: 0.47,
      freshness_sec: 48,
      detail: "Shutdown risk is estimated from mobility, logistics, and energy stress until direct ISP feeds arrive.",
    },
    {
      source: "Cloud metrics",
      stage: "derived",
      status: "degraded",
      coverage_ratio: 0.68,
      confidence_ratio: 0.61,
      freshness_sec: 28,
      detail: "Backbone and control-plane posture is approximated from current operational signals pending direct cloud connectors.",
    },
  ];

  return {
    generated_at: generatedAt,
    refresh_interval_sec: 20,
    summary: {
      mode: "offline-fallback",
      source_stage: "phase-1-derived",
      source_status: "derived-live",
      monitored_countries: 233,
      visible_countries: countries.length,
      healthy_countries: countries.filter((country) => country.status === "stable").length,
      degraded_countries: countries.filter((country) => country.status !== "stable").length,
      shutdown_alerts: shutdownAlerts.length,
      active_attack_paths: cyberAttacks.length,
      global_packet_volume_gbps: flows.reduce((total, flow) => total + flow.throughput_gbps, 0),
      global_congestion_index: 51.6,
      cyber_attack_index: 59.2,
      rerouted_prefixes: 187,
      monitored_prefixes: 102340,
    },
    source_health: sourceHealth,
    countries,
    flows,
    cyber_attacks: cyberAttacks,
    shutdown_alerts: shutdownAlerts,
    top_corridors: [...flows].sort((left, right) => right.congestion_index - left.congestion_index).slice(0, 4),
    generated_from: {
      mode: "offline-fallback",
      source_stage: "phase-1-derived",
      latest_global_timestamp: generatedAt,
      country_snapshot_count: 233,
      visible_country_count: countries.length,
      collector_stages: ["derived", "scaffold"],
      raw_event_count: 48,
      normalized_event_count: 48,
      local_history_dir: "monitoring/internet_map/stream/history",
      persistence_enabled: true,
      note: "Synthetic snapshot used while backend internet-map data is unavailable.",
    },
    collector_summary: {
      captured_at: generatedAt,
      source_family_count: 4,
      total_records: 48,
      raw_event_count: 48,
      normalized_event_count: 48,
      stale_families: 1,
      down_families: 0,
      stages: ["derived", "scaffold"],
    },
    stream_status: {
      status: "ok",
      run_id: `internet_map_mock_${Date.now()}`,
      captured_at: generatedAt,
      active_attack_paths: cyberAttacks.length,
      shutdown_alerts: shutdownAlerts.length,
      collector_total_records: 48,
      raw_event_count: 48,
      normalized_event_count: 48,
      stale_families: 1,
      down_families: 0,
      cycle_latency_ms: 182,
      replay_history_points: 4,
      refresh_sources: false,
    },
    history: [
      {
        run_id: "internet_map_mock_1",
        captured_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
        global_congestion_index: 47.2,
        cyber_attack_index: 54.1,
        active_attack_paths: 2,
        shutdown_alerts: 1,
        source_status: "derived-live",
      },
      {
        run_id: "internet_map_mock_2",
        captured_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
        global_congestion_index: 49.6,
        cyber_attack_index: 56.5,
        active_attack_paths: 2,
        shutdown_alerts: 1,
        source_status: "derived-live",
      },
      {
        run_id: "internet_map_mock_3",
        captured_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
        global_congestion_index: 50.8,
        cyber_attack_index: 57.9,
        active_attack_paths: 3,
        shutdown_alerts: 2,
        source_status: "derived-live",
      },
      {
        run_id: "internet_map_mock_4",
        captured_at: generatedAt,
        global_congestion_index: 51.6,
        cyber_attack_index: 59.2,
        active_attack_paths: cyberAttacks.length,
        shutdown_alerts: shutdownAlerts.length,
        source_status: "derived-live",
      },
    ],
    governance: {
      provenance_mode: "raw_payload_refs_only",
      raw_payload_redacted: true,
      operator_feedback_enabled: true,
      confidence_method: "collector-and-derived-weighted",
      source_stages: ["derived", "scaffold"],
      browser_safe_payload: true,
      generated_at: generatedAt,
    },
    observability: {
      source_freshness: sourceHealth.map((item) => ({ source: item.source, status: item.status, freshness_sec: item.freshness_sec })),
      collector_health: {
        source_family_count: 4,
        total_records: 48,
        raw_event_count: 48,
        normalized_event_count: 48,
        stale_families: 1,
        down_families: 0,
      },
      snapshot_build: {
        latency_ms: 182,
        p95_target_ms: 800,
        within_target: true,
        cache_namespace: "internet_map",
        cache_ttl_sec: 12,
      },
      stream_delivery: {
        mode: "sse",
        poll_seconds: 12,
        replay_history_points: 4,
      },
      alert_quality: {
        active_queue_count: cyberAttacks.length + shutdownAlerts.length,
        suppressed_by_snooze: 0,
        false_positive_flags: 0,
      },
      slo_targets: {
        snapshot_api_p95_ms: 800,
        freshness_sec: 60,
        alert_delivery_cycles: 1,
      },
    },
    persistence: {
      collections: [
        "internet_raw_events",
        "internet_normalized_events",
        "internet_country_snapshots",
        "internet_flow_snapshots",
        "internet_alerts",
        "internet_source_health",
      ],
      history_points: 4,
      replay_available: true,
      local_history_dir: "monitoring/internet_map/stream/history",
      last_run_id: "internet_map_mock_4",
      latest_captured_at: generatedAt,
    },
    alert_ops_summary: {
      acknowledged: 1,
      snoozed_active: 0,
      escalated: 0,
      false_positive_flags: 0,
      total_actions: 1,
      suppressed_by_snooze: 0,
      active_queue_count: cyberAttacks.length + shutdownAlerts.length,
    },
    replay_available: true,
  };
};
const mockCountryDrilldown = (country: string): CountryDrilldownData => {
  const base = MOCK_RISK_MAP.find((entry) => entry.country === country.toUpperCase()) || MOCK_RISK_MAP[0];
  return {
    country: country.toUpperCase(),
    risk: Number(base.risk || 0),
    direct_behavior_score: base.direct_behavior_score,
    contextual_pressure_score: base.contextual_pressure_score,
    evidence_quality_score: base.evidence_quality_score,
    mobility_disruption_score: base.mobility_disruption_score,
    logistics_stress_score: base.logistics_stress_score,
    household_stress_score: base.household_stress_score,
    fuel_price_pressure: base.fuel_price_pressure,
    food_price_pressure: base.food_price_pressure,
    labor_stress_score: base.labor_stress_score,
    fx_pressure_score: base.fx_pressure_score,
    remittance_stress_score: base.remittance_stress_score,
    energy_stress_score: base.energy_stress_score,
    narrative_velocity_score: base.narrative_velocity_score,
    coordination_risk_score: base.coordination_risk_score,
    trend: [
      { timestamp: new Date(Date.now() - 172800000).toISOString(), value: Math.max(Number(base.risk || 0) - 5, 0) },
      { timestamp: new Date(Date.now() - 86400000).toISOString(), value: Math.max(Number(base.risk || 0) - 2, 0) },
      { timestamp: new Date().toISOString(), value: Number(base.risk || 0) },
    ],
    drivers: [
      { feature: 'public_attention_score', value: Number(base.public_attention_score || 0), contribution: 0.22 },
      { feature: 'household_stress_score', value: Number(base.household_stress_score || 0), contribution: 0.19 },
      { feature: 'fx_pressure_score', value: Number(base.fx_pressure_score || 0), contribution: 0.14 },
    ],
    events: [
      { id: `${country}-offline-1`, title: 'Offline fallback mode active', timestamp: new Date().toISOString(), severity: 'medium' },
    ],
    display_risk: Number(base.risk || 0),
    raw_risk_score: Number(base.risk || 0),
    confidence_score: Math.max(24, Math.min(92, Math.round((Number(base.evidence_quality_score || 48) * 0.7) + (Number(base.external_signal_freshness || 0) * 30)))),
    risk_band: Number(base.risk || 0) >= 75 ? "critical" : Number(base.risk || 0) >= 55 ? "elevated" : Number(base.risk || 0) >= 35 ? "guarded" : "stable",
    confidence_band: "moderate",
    source_status: base.validated_today ? "verified_live" : (base.data_quality === "stale" ? "stale_observation" : "derived_estimate"),
    gating_action: base.validated_today ? "allow" : "downgrade",
    country_quality_status: base.validated_today ? "country_ready" : "country_degraded",
    country_quality_reasons: base.validated_today ? [] : ["mock fallback data"],
    advisory: base.validated_today ? "Mock live country intelligence" : "Mock downgraded country intelligence",
    evidence_count: 3,
    score_semantics: {
      risk_score: "0-100 composite country risk score",
      confidence_score: "0-100 calibrated intelligence confidence",
      component_signals: "0-1 normalized signal intensity unless otherwise labeled",
    },
    confidenceInterval: { lower: Math.max(Number(base.risk || 0) - 8, 0), upper: Math.min(Number(base.risk || 0) + 8, 100) },
  };
};

const mockGovernance = (): GovernanceData => ({
  models: [
    { name: 'baseline', latencyMs: 42, calibration: 0.72, driftHint: 'stable', vote: 0.54, confidence: 0.7 },
    { name: 'contextual', latencyMs: 58, calibration: 0.69, driftHint: 'stable', vote: 0.57, confidence: 0.66 },
  ],
  disagreement: [{ left: 'baseline', right: 'contextual', value: 0.08 }],
  calibrationTrend: [
    { timestamp: new Date(Date.now() - 86400000).toISOString(), value: 0.7 },
    { timestamp: new Date().toISOString(), value: 0.72 },
  ],
  calibrationTrendByModel: {},
  selectedCalibrationModel: 'baseline',
});

const mockTrustReliability = (): TrustReliabilitySnapshot => ({
  generated_at: new Date().toISOString(),
  api_health: { status: 'offline-fallback' },
  uptime: { service: 'frontend-only' },
  data_freshness: { state: 'synthetic' },
  latest_ingestion: { checkpoint: 'backend unavailable' },
  source_health: {},
  coverage: { verified: MOCK_RISK_MAP.length, total: 233 },
  quality_gate: { degraded: false, reason: 'local fallback mode' },
  confidence: { score: 0.42 },
  mobility: { coverage_ratio: 0, status: 'offline' },
  economic: { country_count: 0, status: 'offline' },
  alerts: [{ severity: 'medium', source: 'frontend', message: 'Backend connection refused; using synthetic fallback data.' }],
  validation: { status: 'mock' },
});

const isOfflineApiError = (error: unknown): boolean => {
  if (!axios.isAxiosError(error)) return false;
  if (error.response) return false;
  const message = String(error.message || error.code || '').toLowerCase();
  return message.includes('network error') || message.includes('econnrefused') || message.includes('err_connection_refused');
};

const AUTH_STORAGE_KEYS = ["token", "role", "user_type", "name", "email"] as const;
let unauthorizedRedirectScheduled = false;

const clearStoredAuth = () => {
  if (typeof window === "undefined") return;
  AUTH_STORAGE_KEYS.forEach((key) => window.localStorage.removeItem(key));
};

const decodeJwtPayload = (token: string): Record<string, unknown> | null => {
  try {
    const [, payloadBase64] = token.split(".");
    if (!payloadBase64) return null;

    const normalized = payloadBase64.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    const decodeBase64 =
      typeof window !== "undefined" && typeof window.atob === "function"
        ? window.atob.bind(window)
        : typeof atob === "function"
          ? atob
          : null;

    if (!decodeBase64) return null;

    const payload = JSON.parse(decodeBase64(padded));
    return payload && typeof payload === "object" ? (payload as Record<string, unknown>) : null;
  } catch {
    return null;
  }
};

const isJwtExpired = (token: string): boolean => {
  const payload = decodeJwtPayload(token);
  const exp = Number(payload?.exp ?? 0);

  if (!Number.isFinite(exp) || exp <= 0) return false;
  return Date.now() >= exp * 1000;
};

const redirectToLogin = () => {
  if (typeof window === "undefined" || unauthorizedRedirectScheduled) return;
  if (window.location.pathname === "/login") return;

  unauthorizedRedirectScheduled = true;
  window.location.replace("/login");
};

const getStoredToken = () => {
  if (typeof window === "undefined") return "";

  const token = String(window.localStorage.getItem("token") || "").trim();
  if (!token) return "";

  if (isJwtExpired(token)) {
    clearStoredAuth();
    return "";
  }

  return token;
};

export const getAuthHeaders = (): Record<string, string> => {
  const token = getStoredToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return API_KEY ? { "x-api-key": API_KEY } : {};
};

const buildWebSocketBaseUrl = () => {
  const wsBase = activeApiUrl.replace(/^http/, "ws");
  return wsBase.endsWith("/") ? wsBase : `${wsBase}/`;
};

export const buildWebSocketAuthUrl = (pathOrUrl: string): string => {
  const trimmed = pathOrUrl.trim();
  let url: URL;

  if (/^wss?:\/\//i.test(trimmed)) {
    url = new URL(trimmed);
  } else {
    const normalizedPath = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
    url = new URL(normalizedPath, buildWebSocketBaseUrl());
  }

  url.searchParams.delete("token");
  url.searchParams.delete("api_key");

  const token = getStoredToken();
  if (token) {
    url.searchParams.set("token", token);
  } else if (API_KEY) {
    url.searchParams.set("api_key", API_KEY);
  }
  return url.toString();
};

export const buildEventStreamAuthUrl = (pathOrUrl: string): string => {
  const trimmed = pathOrUrl.trim();
  let url: URL;

  if (/^https?:\/\//i.test(trimmed)) {
    url = new URL(trimmed);
  } else {
    const normalizedPath = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
    url = new URL(normalizedPath, activeApiUrl.endsWith("/") ? activeApiUrl : `${activeApiUrl}/`);
  }

  url.searchParams.delete("token");
  url.searchParams.delete("api_key");

  const token = getStoredToken();
  if (token) {
    url.searchParams.set("token", token);
  } else if (API_KEY) {
    url.searchParams.set("api_key", API_KEY);
  }
  return url.toString();
};

export const COUNTRY_RISK_WS_URL = buildWebSocketAuthUrl("/ws/country-risk-map");

// Simple response cache to reduce 429 errors
interface CacheEntry {
  data: unknown;
  timestamp: number;
  ttl: number;
}

const responseCache = new Map<string, CacheEntry>();
const RETRYABLE_STATUS_CODES = new Set([408, 429, 500, 502, 503, 504]);

const API = axios.create({
  baseURL: activeApiUrl,
  timeout: 20000,
});

// Add auth headers and response caching interceptor
API.interceptors.request.use((config) => {
  config.baseURL = activeApiUrl;
  const cacheKey = `${config.method}:${config.url}:${JSON.stringify(config.params || {})}`;
  const cached = responseCache.get(cacheKey);

  if (cached && Date.now() - cached.timestamp < cached.ttl) {
    // Return cached response
    return Promise.reject({
      __cached: true,
      config,
      response: { data: cached.data, status: 200, statusText: "OK", headers: {}, config }
    });
  }

  const nextHeaders = AxiosHeaders.from(config.headers ?? {});
  nextHeaders.delete("x-api-key");
  nextHeaders.delete("X-API-KEY");
  nextHeaders.delete("X-Api-Key");
  nextHeaders.delete("Authorization");
  nextHeaders.delete("authorization");

  const authHeaders = getAuthHeaders();
  Object.entries(authHeaders).forEach(([key, value]) => {
    nextHeaders.set(key, value);
  });

  config.headers = nextHeaders;

  return config;
});

API.interceptors.response.use(
  (response) => {
    // Cache successful GET requests
    if (response.config.method?.toLowerCase() === "get") {
      const cacheKey = `${response.config.method}:${response.config.url}:${JSON.stringify(response.config.params || {})}`;
      // Different TTLs for different endpoints
      let ttl = 2000; // default 2s
      if (response.config.url?.includes("governance")) ttl = 10000; // 10s
      if (response.config.url?.includes("risk-map")) ttl = 5000; // 5s
      if (response.config.url?.includes("live-feed")) ttl = 3000; // 3s

      responseCache.set(cacheKey, {
        data: response.data,
        timestamp: Date.now(),
        ttl
      });
    }
    return response;
  },
  async (error) => {
    // Handle cached responses
    if (error.__cached) {
      return Promise.resolve(error.response);
    }
    const config = error?.config as ((typeof error.config) & { __retryCount?: number; __usedFallback?: boolean }) | undefined;
    const method = String(config?.method || "").toLowerCase();
    const status = Number(error?.response?.status || 0);

    if (status === 401) {
      clearStoredAuth();
      responseCache.clear();
      redirectToLogin();
      return Promise.reject(error);
    }

    const url = String(config?.url || "");
    const canFallbackMethod = method === "get" || url.startsWith("/auth/");

    if (config && canFallbackMethod && shouldUseFallbackApi() && isNetworkFailure(error) && !config.__usedFallback) {
      setActiveApiUrl(FALLBACK_API_URL);
      config.__usedFallback = true;
      config.baseURL = FALLBACK_API_URL;
      return API.request(config);
    }

    const isRetryableNetworkError =
      isNetworkFailure(error) ||
      RETRYABLE_STATUS_CODES.has(status);

    if (config && canFallbackMethod && isRetryableNetworkError) {
      const retryCount = config.__retryCount ?? 0;
      if (retryCount < 2) {
        config.__retryCount = retryCount + 1;
        await new Promise((resolve) => setTimeout(resolve, 700 * (retryCount + 1)));
        return API.request(config);
      }
    }
    return Promise.reject(error);
  }
);

// Clean up old cache entries periodically
setInterval(() => {
  const now = Date.now();
  for (const [key, entry] of responseCache.entries()) {
    if (now - entry.timestamp > entry.ttl * 2) {
      responseCache.delete(key);
    }
  }
}, 30000); // Clean every 30s

// Legacy constant retained for compatibility at call sites.
export const API_HEADERS: Record<string, string> = {};


export type LiveCommandFeed = {
  incidents: string[];
  ingestionHeartbeatSec: number;
  modelDrift: number;
  lastUpdated: string;
};

export type RiskMapPoint = {
  country: string;
  risk: number | null;
  display_risk?: number | null;
  raw_risk_score?: number | null;
  confidence_score?: number;
  risk_band?: "critical" | "escalating" | "elevated" | "guarded" | "stable" | string;
  confidence_band?: "high" | "moderate" | "limited" | "weak" | string;
  source_status?: string;
  gating_action?: "allow" | "downgrade" | "suppress" | string;
  country_quality_status?: string;
  country_quality_reasons?: string[];
  advisory?: string;
  evidence_count?: number;
  component_coverage_ratio?: number;
  score_semantics?: Record<string, string>;
  timestamp?: string;
  feature_timestamp?: string | null;
  validated_today?: boolean;
  data_quality?: "verified" | "synthetic" | "stale" | "unknown";
  source_count?: number;
  social_unrest_score?: number;
  google_trends_pressure?: number;
  public_attention_score?: number;
  narrative_velocity_score?: number;
  coordination_risk_score?: number;
  mobility_disruption_score?: number;
  logistics_stress_score?: number;
  household_stress_score?: number;
  fuel_price_pressure?: number;
  food_price_pressure?: number;
  labor_stress_score?: number;
  fx_pressure_score?: number;
  remittance_stress_score?: number;
  energy_stress_score?: number;
  weather_stress?: number;
  external_signal_freshness?: number;
  direct_behavior_score?: number;
  contextual_pressure_score?: number;
  evidence_quality_score?: number;
  war_state_rules?: string[];
  risk_delta_24h?: number;
  risk_delta_7d?: number;
  risk_trend_direction?: "worsening" | "improving" | "stable" | string;
  score_change_contributors?: Array<{ feature: string; value: number; delta?: number; contribution?: number }>;
  spillover_links?: Array<{ country: string; risk?: number; relationship?: string }>;
};

export type RiskMapCoverage = {
  total: number;
  verified: number;
  no_data: number;
  stale: number;
  suppressed?: number;
  remaining: number;
  coverage_pct: number;
  latest_validation?: {
    status?: string;
    sample_count?: number;
    brier_score?: number;
  };
};

export type GlobalForecastContract = {
  source?: string;
  source_status?: string;
  calibration_status?: string;
  gating_action?: string;
  prediction_available?: boolean;
  withheld?: boolean;
  risk_score?: number | null;
  confidence_ratio?: number;
  confidence_score?: number;
  risk_delta?: number;
  horizon_hours?: number;
  horizons?: Array<{
    hours?: number;
    label?: string;
    risk_score?: number;
    delta?: number;
    threat_label?: string;
  }>;
  prediction_interval?: { p10?: number; p50?: number; p90?: number } | null;
  advisory?: string;
  reasons?: string[];
  quality_status?: string;
  basis?: string;
  model_version?: string;
  generated_at?: string;
  score_semantics?: Record<string, string>;
};

export type GlobalOperationalFeatures = {
  timestamp: string;
  news_sentiment: number;
  gdelt_sentiment: number;
  crypto_return: number;
  crypto_volatility: number;
  stock_return: number;
  stock_volatility: number;
  weather_anomaly: number;
  global_risk_score: number;
  global_mood_score?: number;
  global_mood_confidence?: number;
  global_mood_uncertainty?: number;
  global_mood_verified_countries?: number;
  global_mood_eligible_countries?: number;
  global_mood_contributing_countries?: number;
  global_mood_used_countries?: number;
  global_mood_excluded_countries?: number;
  global_mood_screened_out_countries?: number;
  global_mood_total_countries?: number;
  global_mood_coverage_ratio?: number;
  global_mood_active_regions?: number;
  global_mood_method?: string;
  forecast_risk_score?: number | null;
  forecast_risk_delta?: number;
  forecast_confidence?: number;
  forecast_confidence_score?: number;
  forecast_horizon_hours?: number;
  forecast_basis?: string;
  forecast_source_status?: string;
  forecast_calibration_status?: string;
  forecast_gating_action?: string;
  forecast_prediction_available?: boolean;
  forecast_withheld?: boolean;
  forecast_prediction_interval?: { p10?: number; p50?: number; p90?: number } | null;
  forecast_advisory?: string;
  forecast_reasons?: string[];
  forecast_model_version?: string;
  forecast_generated_at?: string;
  forecast_contract?: GlobalForecastContract;
  top_topics: string[];
};

export type LatestGlobalResponse = {
  timestamp?: string;
  version?: number;
  mode?: string;
  features: GlobalOperationalFeatures;
};

export type InternetMapSummary = {
  mode?: string;
  source_stage?: string;
  source_status?: string;
  monitored_countries: number;
  visible_countries: number;
  healthy_countries: number;
  degraded_countries: number;
  shutdown_alerts: number;
  active_attack_paths: number;
  global_packet_volume_gbps: number;
  global_congestion_index: number;
  cyber_attack_index: number;
  rerouted_prefixes: number;
  monitored_prefixes: number;
};

export type InternetMapSourceHealth = {
  source: string;
  source_family?: string;
  source_name?: string;
  stage: string;
  status: string;
  coverage_ratio: number;
  confidence_ratio: number;
  freshness_sec: number;
  records?: number;
  detail?: string;
  advisory?: string;
  updated_at?: string;
  errors?: string[];
  provenance?: string;
  cache_hit?: boolean;
  refresh_requested?: boolean;
  rate_limited?: boolean;
  auth_mode?: string;
  request_attempts?: number;
};

export type InternetMapAlertOpsState = {
  status?: string;
  action_counts?: Record<string, number>;
  false_positive_count?: number;
  last_action?: string | null;
  last_timestamp?: string | null;
  owner?: string | null;
  assignee?: string | null;
  assignment_reason?: string | null;
  false_positive_reason?: string | null;
  comment?: string | null;
  snoozed_until?: string | null;
  team_queue?: string | null;
  escalation_destination?: string | null;
  escalation_level?: number;
  sla_due_at?: string | null;
  sla_hours?: number;
  sla_remaining_sec?: number | null;
  sla_breached?: boolean;
  is_snoozed?: boolean;
};

export type InternetMapCountry = {
  country: string;
  label: string;
  lat: number;
  lon: number;
  risk: number;
  data_quality?: string;
  validated_today?: boolean;
  source_count?: number;
  freshness_ratio?: number;
  evidence_quality_score?: number;
  packet_flow_gbps: number;
  congestion_index: number;
  attack_index: number;
  shutdown_risk: number;
  stability_score: number;
  signal_strength?: number;
  status: string;
  severity: string;
  advisory?: string;
  generated_at?: string;
  mode?: string;
  stage?: string;
  confidence_ratio?: number;
  freshness_sec?: number;
  subscriber_availability_ratio?: number;
  fixed_reachability_ratio?: number;
  mobile_reachability_ratio?: number;
  throughput_drop_pct?: number;
  outage_report_count?: number;
  subscribers_impacted_m?: number;
  control_plane_incident_score?: number;
  dns_error_ratio?: number;
  shutdown_signal_count?: number;
};

export type InternetMapFlow = {
  id: string;
  origin: string;
  origin_label: string;
  origin_lat: number;
  origin_lon: number;
  destination: string;
  destination_label: string;
  destination_lat: number;
  destination_lon: number;
  throughput_gbps: number;
  congestion_index: number;
  attack_index: number;
  latency_ms: number;
  packet_loss_pct: number;
  reroute_factor: number;
  anomaly_score: number;
  traffic_share: number;
  status: string;
  severity: string;
  confidence_ratio?: number;
  freshness_sec?: number;
  source_families?: string[];
  generated_at?: string;
  mode?: string;
  stage?: string;
  route_update_count?: number;
  announcement_count?: number;
  withdrawn_prefix_count?: number;
  as_path_churn_score?: number;
  hijack_suspect_score?: number;
  monitored_prefix_count?: number;
  edge_error_rate?: number;
  egress_saturation_ratio?: number;
  dns_error_ratio?: number;
  control_plane_incident_score?: number;
  api_error_ratio?: number;
  measurement_mode?: string;
  measured_signal_count?: number;
  attack_signal_count?: number;
};

export type InternetMapCyberAttack = {
  id: string;
  origin: string;
  origin_label: string;
  target: string;
  target_label: string;
  severity: string;
  status: string;
  vector: string;
  attack_index: number;
  intensity_gbps: number;
  packets_mps: number;
  confidence_ratio: number;
  started_at: string;
  flow_id?: string;
  alert_type?: string;
  alert_id?: string;
  dedupe_key?: string;
  ops_state?: InternetMapAlertOpsState;
  freshness_sec?: number;
  source_families?: string[];
  generated_at?: string;
  mode?: string;
  stage?: string;
  hijack_suspect_score?: number;
  control_plane_incident_score?: number;
  attack_signal_count?: number;
};

export type InternetMapShutdownAlert = {
  id: string;
  country: string;
  label: string;
  severity: string;
  status: string;
  shutdown_risk: number;
  estimated_users_impacted_m: number;
  confidence_ratio: number;
  reason: string;
  started_at: string;
  advisory: string;
  alert_type?: string;
  alert_id?: string;
  dedupe_key?: string;
  ops_state?: InternetMapAlertOpsState;
  freshness_sec?: number;
  source_families?: string[];
  generated_at?: string;
  mode?: string;
  stage?: string;
  subscriber_availability_ratio?: number;
  fixed_reachability_ratio?: number;
  mobile_reachability_ratio?: number;
  throughput_drop_pct?: number;
  control_plane_incident_score?: number;
  shutdown_signal_count?: number;
};

export type InternetMapGeneratedFrom = {
  mode?: string;
  source_stage?: string;
  latest_global_timestamp?: string;
  country_snapshot_count?: number;
  visible_country_count?: number;
  collector_stages?: string[];
  raw_event_count?: number;
  normalized_event_count?: number;
  local_history_dir?: string;
  persistence_enabled?: boolean;
  direct_source_families?: string[];
  measurement_modes?: string[];
  note?: string;
};

export type InternetMapCollectorSummary = {
  captured_at?: string;
  source_family_count?: number;
  total_records?: number;
  raw_event_count?: number;
  normalized_event_count?: number;
  stale_families?: number;
  down_families?: number;
  healthy_families?: number;
  direct_families?: number;
  cache_hit_families?: number;
  rate_limited_families?: number;
  auth_enabled_families?: number;
  served_from_cache?: boolean;
  stages?: string[];
  measurement_modes?: string[];
};

export type InternetMapStreamStatus = {
  status: string;
  run_id?: string;
  captured_at?: string | null;
  active_attack_paths?: number;
  shutdown_alerts?: number;
  collector_total_records?: number;
  raw_event_count?: number;
  normalized_event_count?: number;
  stale_families?: number;
  down_families?: number;
  cycle_latency_ms?: number;
  replay_history_points?: number;
  refresh_sources?: boolean;
};

export type InternetMapHistoryPoint = {
  run_id: string;
  captured_at: string;
  global_congestion_index: number;
  cyber_attack_index: number;
  active_attack_paths: number;
  shutdown_alerts: number;
  source_status: string;
  source_stage?: string;
  collector_total_records?: number;
};

export type InternetMapGovernance = {
  provenance_mode?: string;
  raw_payload_redacted?: boolean;
  operator_feedback_enabled?: boolean;
  assignment_enabled?: boolean;
  team_queue_enabled?: boolean;
  sla_tracking_enabled?: boolean;
  audit_reporting_enabled?: boolean;
  confidence_method?: string;
  source_stages?: string[];
  browser_safe_payload?: boolean;
  supported_actions?: string[];
  generated_at?: string;
  secret_loading?: {
    dotenv_fallback_loaded?: boolean;
    secret_file_loaded?: boolean;
    secret_file_configured?: boolean;
  };
};

export type InternetMapObservability = {
  source_freshness?: Array<{ source: string; status: string; freshness_sec: number }>;
  collector_health?: {
    source_family_count?: number;
    total_records?: number;
    raw_event_count?: number;
    normalized_event_count?: number;
    stale_families?: number;
    down_families?: number;
    direct_families?: number;
    cache_hit_families?: number;
    rate_limited_families?: number;
    auth_enabled_families?: number;
    served_from_cache?: boolean;
  };
  snapshot_build?: {
    latency_ms?: number;
    p95_target_ms?: number;
    within_target?: boolean;
    cache_namespace?: string;
    cache_ttl_sec?: number;
  };
  stream_delivery?: {
    mode?: string;
    poll_seconds?: number;
    replay_history_points?: number;
  };
  alert_quality?: {
    active_queue_count?: number;
    suppressed_by_snooze?: number;
    false_positive_flags?: number;
    backtest_precision_proxy?: number;
    feedback_adjusted_precision_proxy?: number;
  };
  slo_targets?: {
    snapshot_api_p95_ms?: number;
    freshness_sec?: number;
    alert_delivery_cycles?: number;
  };
};

export type InternetMapReplayAnalytics = {
  window_hours?: number;
  history_points?: number;
  trend_direction?: string;
  congestion_delta?: number;
  attack_delta?: number;
  peak_congestion_index?: number;
  peak_attack_index?: number;
  peak_shutdown_alerts?: number;
  top_disrupted_countries?: Array<{ country: string; label: string; score: number; status?: string }>;
  top_contested_corridors?: Array<{ id: string; label: string; score: number; reroute_factor?: number; packet_loss_pct?: number }>;
  alert_counts?: { attack?: number; shutdown?: number };
};

export type InternetMapBacktestSummary = {
  generated_at?: string | null;
  status?: string;
  window_days?: number;
  overall?: {
    evaluated_alerts?: number;
    matched_follow_on_signals?: number;
    false_positives?: number;
    precision_proxy?: number;
    feedback_adjusted_precision_proxy?: number;
    feedback_false_positive_flags?: number;
    false_positive_rate?: number;
  };
  attack_alerts?: Record<string, unknown>;
  shutdown_alerts?: Record<string, unknown>;
};

export type InternetMapRetentionPolicy = {
  mongo_retention_days?: number;
  stream_history_retention_days?: number;
  backtest_retention_days?: number;
  collections?: string[];
  maintenance_script?: string;
};

export type InternetMapPersistence = {
  collections?: string[];
  history_points?: number;
  replay_available?: boolean;
  local_history_dir?: string;
  last_run_id?: string;
  latest_captured_at?: string;
};

export type InternetMapRuntimeStatus = {
  status?: string;
  scheduler_enabled?: boolean;
  in_progress?: boolean;
  queue_depth?: number;
  last_cycle_reason?: string;
  last_cycle_started_at?: string | null;
  last_cycle_finished_at?: string | null;
  last_cycle_status?: string;
  last_mode?: string;
  refresh_sources?: boolean;
  cycle_interval_sec?: number;
  backtest_interval_sec?: number;
  maintenance_interval_sec?: number;
  cycle_count?: number;
  error_count?: number;
  last_error?: string | null;
  last_backtest_at?: string | null;
  last_backtest_status?: string | null;
  last_maintenance_at?: string | null;
  last_maintenance_status?: string | null;
  run_id?: string | null;
  captured_at?: string | null;
  cycle_latency_ms?: number;
  collector_total_records?: number;
  source_stage?: string | null;
};

export type InternetMapOpsReport = {
  audit_window_hours?: number;
  total_actions?: number;
  actions_by_type?: Array<{ action: string; count: number }>;
  team_queues?: Array<{ queue: string; count: number }>;
  escalation_destinations?: Array<{ destination: string; count: number }>;
  top_operators?: Array<{ owner: string; count: number }>;
  recent_actions?: Array<{
    timestamp?: string;
    owner?: string;
    action?: string;
    dedupe_key?: string;
    team_queue?: string;
    escalation_destination?: string;
    severity?: string;
  }>;
};

export type InternetMapAlertOpsSummary = {
  acknowledged?: number;
  assigned?: number;
  snoozed_active?: number;
  escalated?: number;
  false_positive_flags?: number;
  total_actions?: number;
  suppressed_by_snooze?: number;
  active_queue_count?: number;
  breached_sla_count?: number;
  queue_breakdown?: Array<{ queue: string; count: number }>;
  escalation_breakdown?: Array<{ destination: string; count: number }>;
};

export type InternetMapSnapshot = {
  generated_at: string;
  refresh_interval_sec: number;
  summary: InternetMapSummary;
  source_health: InternetMapSourceHealth[];
  countries: InternetMapCountry[];
  flows: InternetMapFlow[];
  cyber_attacks: InternetMapCyberAttack[];
  shutdown_alerts: InternetMapShutdownAlert[];
  top_corridors: InternetMapFlow[];
  generated_from?: InternetMapGeneratedFrom;
  collector_summary?: InternetMapCollectorSummary;
  stream_status?: InternetMapStreamStatus;
  history?: InternetMapHistoryPoint[];
  governance?: InternetMapGovernance;
  observability?: InternetMapObservability;
  persistence?: InternetMapPersistence;
  replay_analytics?: InternetMapReplayAnalytics;
  backtest_summary?: InternetMapBacktestSummary;
  retention_policy?: InternetMapRetentionPolicy;
  runtime_status?: InternetMapRuntimeStatus;
  ops_reporting?: InternetMapOpsReport;
  alert_ops_summary?: InternetMapAlertOpsSummary;
  storage?: Record<string, unknown>;
  replay_available?: boolean;
};

export type InternetMapHistoryResponse = {
  items: InternetMapHistoryPoint[];
  replay_available: boolean;
  latest_captured_at?: string | null;
  stream_status?: InternetMapStreamStatus;
};

export type InternetMapPlaybackFrame = {
  run_id: string;
  captured_at: string;
  generated_at?: string;
  summary: InternetMapSummary;
  countries: InternetMapCountry[];
  flows: InternetMapFlow[];
  cyber_attacks: InternetMapCyberAttack[];
  shutdown_alerts: InternetMapShutdownAlert[];
  top_corridors: InternetMapFlow[];
  source_health?: InternetMapSourceHealth[];
  generated_from?: InternetMapGeneratedFrom;
  collector_summary?: InternetMapCollectorSummary;
  stream_status?: InternetMapStreamStatus;
};

export type InternetMapPlaybackResponse = {
  frames: InternetMapPlaybackFrame[];
  replay_available: boolean;
  latest_captured_at?: string | null;
  stream_status?: InternetMapStreamStatus;
};

export type InternetMapStreamStatusResponse = {
  run_id?: string;
  status?: string;
  captured_at?: string | null;
  collector_summary?: InternetMapCollectorSummary;
  stream_status?: InternetMapStreamStatus;
  runtime_status?: InternetMapRuntimeStatus;
  history?: InternetMapHistoryPoint[];
};

export type InternetMapAlertActionPayload = {
  alert_type: "attack" | "shutdown";
  country?: string;
  flow_id?: string;
  action: "acknowledge" | "assign" | "snooze" | "escalate" | "false_positive";
  owner?: string;
  assignee?: string;
  assignment_reason?: string;
  team_queue?: string;
  escalation_destination?: string;
  escalation_level?: number;
  sla_hours?: number;
  comment?: string;
  alert_id?: string;
  dedupe_key?: string;
  severity?: string;
  snooze_hours?: number;
  false_positive_reason?: string;
};

export type InternetMapAlertActionResponse = {
  ok: boolean;
  action?: string;
  dedupe_key?: string;
  assignee?: string | null;
  team_queue?: string | null;
  escalation_destination?: string | null;
  snoozed_until?: string | null;
  sla_due_at?: string | null;
};

export type CountryDrilldownData = {
  country: string;
  risk: number;
  display_risk?: number | null;
  raw_risk_score?: number | null;
  confidence_score?: number;
  risk_band?: string;
  confidence_band?: string;
  source_status?: string;
  gating_action?: string;
  country_quality_status?: string;
  country_quality_reasons?: string[];
  advisory?: string;
  evidence_count?: number;
  score_semantics?: Record<string, string>;
  direct_behavior_score?: number;
  contextual_pressure_score?: number;
  evidence_quality_score?: number;
  mobility_disruption_score?: number;
  logistics_stress_score?: number;
  household_stress_score?: number;
  fuel_price_pressure?: number;
  food_price_pressure?: number;
  labor_stress_score?: number;
  fx_pressure_score?: number;
  remittance_stress_score?: number;
  energy_stress_score?: number;
  narrative_velocity_score?: number;
  coordination_risk_score?: number;
  trend: Array<{ timestamp: string; value: number }>;
  drivers: Array<{ feature: string; value: number; contribution: number }>;
  events: Array<{ id: string; title: string; timestamp: string; severity: "low" | "medium" | "high" }>;
  confidenceInterval: { lower: number; upper: number };
};

export type GovernanceData = {
  models: Array<{ name: string; stage?: string; latencyMs: number; calibration: number; driftHint: string; vote?: number; confidence?: number }>;
  disagreement: Array<{ left: string; right: string; value: number }>;
  calibrationTrend: Array<{ timestamp: string; value: number }>;
  calibrationTrendByModel: Record<string, Array<{ timestamp: string; value: number }>>;
  selectedCalibrationModel?: string;
};

export type AlertActionPayload = {
  country: string;
  action: "acknowledge" | "snooze" | "assign";
  owner?: string;
  comment?: string;
};


const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const toFiniteNumber = (value: unknown, fallback = 0): number => {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
};

const toOptionalFiniteNumber = (value: unknown): number | undefined => {
  const next = Number(value);
  return Number.isFinite(next) ? next : undefined;
};

const toNullableFiniteNumber = (value: unknown): number | null => {
  const next = Number(value);
  return Number.isFinite(next) ? next : null;
};

const toValidTimestamp = (value: unknown, fallback: string): string => {
  if (typeof value !== "string") return fallback;
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? value : fallback;
};

const toStringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string") : [];

const RISK_DATA_QUALITIES = new Set<RiskMapPoint["data_quality"]>([
  "verified",
  "synthetic",
  "stale",
  "unknown",
]);

const normalizeLiveCommandFeed = (value: unknown): LiveCommandFeed => {
  const nowIso = new Date().toISOString();
  if (!isRecord(value)) {
    return {
      incidents: [],
      ingestionHeartbeatSec: 0,
      modelDrift: 0,
      lastUpdated: nowIso,
    };
  }

  return {
    incidents: toStringArray(value.incidents),
    ingestionHeartbeatSec: toFiniteNumber(value.ingestionHeartbeatSec),
    modelDrift: toFiniteNumber(value.modelDrift),
    lastUpdated: toValidTimestamp(value.lastUpdated, nowIso),
  };
};

const normalizeRiskMapPoint = (value: unknown): RiskMapPoint | null => {
  if (!isRecord(value)) return null;

  const country = typeof value.country === "string" ? value.country.trim().toUpperCase() : "";
  if (!country) return null;

  const dataQualityCandidate =
    typeof value.data_quality === "string" ? (value.data_quality as RiskMapPoint["data_quality"]) : undefined;
  const dataQuality = dataQualityCandidate && RISK_DATA_QUALITIES.has(dataQualityCandidate) ? dataQualityCandidate : "unknown";

  const timestamp = typeof value.timestamp === "string" ? value.timestamp : undefined;
  const featureTimestamp = typeof value.feature_timestamp === "string" ? value.feature_timestamp : undefined;
  const rawRisk = toNullableFiniteNumber(value.raw_risk_score ?? value.risk);
  const displayRisk = toNullableFiniteNumber(value.display_risk);
  const effectiveRisk = displayRisk ?? rawRisk;

  return {
    country,
    risk: effectiveRisk,
    display_risk: displayRisk,
    raw_risk_score: rawRisk,
    confidence_score: toOptionalFiniteNumber(value.confidence_score),
    risk_band: typeof value.risk_band === "string" ? value.risk_band : undefined,
    confidence_band: typeof value.confidence_band === "string" ? value.confidence_band : undefined,
    source_status: typeof value.source_status === "string" ? value.source_status : undefined,
    gating_action: typeof value.gating_action === "string" ? value.gating_action : undefined,
    country_quality_status: typeof value.country_quality_status === "string" ? value.country_quality_status : undefined,
    country_quality_reasons: toStringArray(value.country_quality_reasons),
    advisory: typeof value.advisory === "string" ? value.advisory : undefined,
    evidence_count: toOptionalFiniteNumber(value.evidence_count),
    component_coverage_ratio: toOptionalFiniteNumber(value.component_coverage_ratio),
    score_semantics: isRecord(value.score_semantics)
      ? Object.fromEntries(Object.entries(value.score_semantics).filter(([, entry]) => typeof entry === "string")) as Record<string, string>
      : undefined,
    timestamp,
    feature_timestamp: featureTimestamp,
    validated_today: Boolean(value.validated_today),
    data_quality: dataQuality,
    source_count: toOptionalFiniteNumber(value.source_count),
    social_unrest_score: toOptionalFiniteNumber(value.social_unrest_score),
    google_trends_pressure: toOptionalFiniteNumber(value.google_trends_pressure),
    public_attention_score: toOptionalFiniteNumber(value.public_attention_score),
    narrative_velocity_score: toOptionalFiniteNumber(value.narrative_velocity_score),
    coordination_risk_score: toOptionalFiniteNumber(value.coordination_risk_score),
    mobility_disruption_score: toOptionalFiniteNumber(value.mobility_disruption_score),
    logistics_stress_score: toOptionalFiniteNumber(value.logistics_stress_score),
    household_stress_score: toOptionalFiniteNumber(value.household_stress_score),
    fuel_price_pressure: toOptionalFiniteNumber(value.fuel_price_pressure),
    food_price_pressure: toOptionalFiniteNumber(value.food_price_pressure),
    labor_stress_score: toOptionalFiniteNumber(value.labor_stress_score),
    fx_pressure_score: toOptionalFiniteNumber(value.fx_pressure_score),
    remittance_stress_score: toOptionalFiniteNumber(value.remittance_stress_score),
    energy_stress_score: toOptionalFiniteNumber(value.energy_stress_score),
    weather_stress: toOptionalFiniteNumber(value.weather_stress),
    external_signal_freshness: toOptionalFiniteNumber(value.external_signal_freshness),
    direct_behavior_score: toOptionalFiniteNumber(value.direct_behavior_score),
    contextual_pressure_score: toOptionalFiniteNumber(value.contextual_pressure_score),
    evidence_quality_score: toOptionalFiniteNumber(value.evidence_quality_score),
    war_state_rules: toStringArray(value.war_state_rules),
    risk_delta_24h: toOptionalFiniteNumber(value.risk_delta_24h),
    risk_delta_7d: toOptionalFiniteNumber(value.risk_delta_7d),
    risk_trend_direction: typeof value.risk_trend_direction === "string" ? value.risk_trend_direction : undefined,
    score_change_contributors: Array.isArray(value.score_change_contributors)
      ? value.score_change_contributors
          .filter(isRecord)
          .map((item) => ({
            feature: typeof item.feature === "string" ? item.feature : "unknown",
            value: toFiniteNumber(item.value),
            delta: toOptionalFiniteNumber(item.delta),
            contribution: toOptionalFiniteNumber(item.contribution),
          }))
      : undefined,
    spillover_links: Array.isArray(value.spillover_links)
      ? value.spillover_links
          .filter(isRecord)
          .map((item) => ({
            country: typeof item.country === "string" ? item.country : "",
            risk: toOptionalFiniteNumber(item.risk),
            relationship: typeof item.relationship === "string" ? item.relationship : undefined,
          }))
          .filter((item) => item.country)
      : undefined,
  };
};

const normalizeRiskMapCoverage = (value: unknown): RiskMapCoverage => {
  if (!isRecord(value)) {
    return { total: 0, verified: 0, no_data: 0, stale: 0, suppressed: 0, remaining: 0, coverage_pct: 0 };
  }

  const latestValidation = isRecord(value.latest_validation)
    ? {
        status: typeof value.latest_validation.status === "string" ? value.latest_validation.status : undefined,
        sample_count: toOptionalFiniteNumber(value.latest_validation.sample_count),
        brier_score: toOptionalFiniteNumber(value.latest_validation.brier_score),
      }
    : undefined;

  return {
    total: Math.max(0, Math.round(toFiniteNumber(value.total))),
    verified: Math.max(0, Math.round(toFiniteNumber(value.verified))),
    no_data: Math.max(0, Math.round(toFiniteNumber(value.no_data))),
    stale: Math.max(0, Math.round(toFiniteNumber(value.stale))),
    suppressed: Math.max(0, Math.round(toFiniteNumber(value.suppressed))),
    remaining: Math.max(0, Math.round(toFiniteNumber(value.remaining))),
    coverage_pct: Math.max(0, toFiniteNumber(value.coverage_pct)),
    latest_validation: latestValidation,
  };
};

const normalizeCountryDrilldown = (value: unknown, fallbackCountry: string): CountryDrilldownData => {
  const nowIso = new Date().toISOString();

  if (!isRecord(value)) {
    return {
      country: fallbackCountry,
      risk: 0,
      display_risk: 0,
      raw_risk_score: 0,
      confidence_score: 0,
      country_quality_reasons: [],
      mobility_disruption_score: 0,
      logistics_stress_score: 0,
      household_stress_score: 0,
      fuel_price_pressure: 0,
      food_price_pressure: 0,
      labor_stress_score: 0,
      fx_pressure_score: 0,
      remittance_stress_score: 0,
      energy_stress_score: 0,
      narrative_velocity_score: 0,
      coordination_risk_score: 0,
      trend: [],
      drivers: [],
      events: [],
      confidenceInterval: { lower: 0, upper: 0 },
    };
  }

  const trend = Array.isArray(value.trend)
    ? value.trend
        .filter(isRecord)
        .map((entry) => ({
          timestamp: toValidTimestamp(entry.timestamp, nowIso),
          value: toFiniteNumber(entry.value),
        }))
    : [];

  const drivers = Array.isArray(value.drivers)
    ? value.drivers
        .filter(isRecord)
        .map((entry) => ({
          feature: typeof entry.feature === "string" ? entry.feature : "unknown",
          value: toFiniteNumber(entry.value),
          contribution: toFiniteNumber(entry.contribution),
        }))
    : [];

  const events = Array.isArray(value.events)
    ? value.events
        .filter(isRecord)
        .map((entry, index) => ({
          id: typeof entry.id === "string" ? entry.id : `${fallbackCountry}-${index}`,
          title: typeof entry.title === "string" ? entry.title : "Untitled event",
          timestamp: toValidTimestamp(entry.timestamp, nowIso),
          severity: (
            entry.severity === "low" || entry.severity === "medium" || entry.severity === "high"
              ? entry.severity
              : "low"
          ) as "low" | "medium" | "high",
        }))
    : [];

  const confidenceInterval = isRecord(value.confidenceInterval)
    ? {
        lower: toFiniteNumber(value.confidenceInterval.lower),
        upper: toFiniteNumber(value.confidenceInterval.upper),
      }
    : { lower: 0, upper: 0 };

  const rawRisk = toFiniteNumber(value.raw_risk_score ?? value.risk);
  const displayRisk = toOptionalFiniteNumber(value.display_risk);
  return {
    country: typeof value.country === "string" ? value.country : fallbackCountry,
    risk: Number.isFinite(Number(displayRisk)) ? Number(displayRisk) : rawRisk,
    display_risk: displayRisk,
    raw_risk_score: rawRisk,
    confidence_score: toOptionalFiniteNumber(value.confidence_score),
    risk_band: typeof value.risk_band === "string" ? value.risk_band : undefined,
    confidence_band: typeof value.confidence_band === "string" ? value.confidence_band : undefined,
    source_status: typeof value.source_status === "string" ? value.source_status : undefined,
    gating_action: typeof value.gating_action === "string" ? value.gating_action : undefined,
    country_quality_status: typeof value.country_quality_status === "string" ? value.country_quality_status : undefined,
    country_quality_reasons: toStringArray(value.country_quality_reasons),
    advisory: typeof value.advisory === "string" ? value.advisory : undefined,
    evidence_count: toOptionalFiniteNumber(value.evidence_count),
    score_semantics: isRecord(value.score_semantics)
      ? Object.fromEntries(Object.entries(value.score_semantics).filter(([, entry]) => typeof entry === "string")) as Record<string, string>
      : undefined,
    mobility_disruption_score: toOptionalFiniteNumber(value.mobility_disruption_score),
    logistics_stress_score: toOptionalFiniteNumber(value.logistics_stress_score),
    household_stress_score: toOptionalFiniteNumber(value.household_stress_score),
    fuel_price_pressure: toOptionalFiniteNumber(value.fuel_price_pressure),
    food_price_pressure: toOptionalFiniteNumber(value.food_price_pressure),
    labor_stress_score: toOptionalFiniteNumber(value.labor_stress_score),
    fx_pressure_score: toOptionalFiniteNumber(value.fx_pressure_score),
    remittance_stress_score: toOptionalFiniteNumber(value.remittance_stress_score),
    energy_stress_score: toOptionalFiniteNumber(value.energy_stress_score),
    narrative_velocity_score: toOptionalFiniteNumber(value.narrative_velocity_score),
    coordination_risk_score: toOptionalFiniteNumber(value.coordination_risk_score),
    direct_behavior_score: toOptionalFiniteNumber(value.direct_behavior_score),
    contextual_pressure_score: toOptionalFiniteNumber(value.contextual_pressure_score),
    evidence_quality_score: toOptionalFiniteNumber(value.evidence_quality_score),
    trend,
    drivers,
    events,
    confidenceInterval,
  };
};

const normalizeGovernanceData = (value: unknown): GovernanceData => {
  if (!isRecord(value)) {
    return { models: [], disagreement: [], calibrationTrend: [], calibrationTrendByModel: {}, selectedCalibrationModel: undefined };
  }

  const models = Array.isArray(value.models)
    ? value.models
        .filter(isRecord)
        .map((entry) => ({
          name: typeof entry.name === "string" ? entry.name : "unknown",
          latencyMs: toFiniteNumber(entry.latencyMs),
          calibration: toFiniteNumber(entry.calibration),
          driftHint: typeof entry.driftHint === "string" ? entry.driftHint : "n/a",
          vote: toOptionalFiniteNumber(entry.vote),
          confidence: toOptionalFiniteNumber(entry.confidence),
        }))
    : [];

  const disagreement = Array.isArray(value.disagreement)
    ? value.disagreement
        .filter(isRecord)
        .map((entry) => ({
          left: typeof entry.left === "string" ? entry.left : "unknown",
          right: typeof entry.right === "string" ? entry.right : "unknown",
          value: toFiniteNumber(entry.value),
        }))
    : [];

  const calibrationTrend = Array.isArray(value.calibrationTrend)
    ? value.calibrationTrend
        .filter(isRecord)
        .map((entry) => ({
          timestamp: toValidTimestamp(entry.timestamp, new Date().toISOString()),
          value: toFiniteNumber(entry.value),
        }))
    : [];

  const calibrationTrendByModel = isRecord(value.calibrationTrendByModel)
    ? Object.fromEntries(
        Object.entries(value.calibrationTrendByModel)
          .filter((entry): entry is [string, unknown] => typeof entry[0] === "string")
          .map(([modelName, trend]) => [
            modelName,
            Array.isArray(trend)
              ? trend
                  .filter(isRecord)
                  .map((entry) => ({
                    timestamp: toValidTimestamp(entry.timestamp, new Date().toISOString()),
                    value: toFiniteNumber(entry.value),
                  }))
              : [],
          ]),
      )
    : {};

  const selectedCalibrationModel = typeof value.selectedCalibrationModel === "string"
    ? value.selectedCalibrationModel
    : undefined;

  return {
    models,
    disagreement,
    calibrationTrend,
    calibrationTrendByModel,
    selectedCalibrationModel,
  };
};

export async function getLiveCommandFeed(): Promise<LiveCommandFeed> {
  if (USE_MOCK_API) return mockLiveFeed();
  const res = await API.get("/dashboard/live-feed", { headers: API_HEADERS, params: { mode: "online" } });
  return normalizeLiveCommandFeed(res.data);
}

export async function getRiskMap(): Promise<RiskMapPoint[]> {
  if (USE_MOCK_API) return MOCK_RISK_MAP;
  const res = await API.get("/country-intelligence/latest", { headers: API_HEADERS, params: { mode: "online", verified_only: false } });
  return Array.isArray(res.data)
    ? res.data
        .map(normalizeRiskMapPoint)
        .filter((entry): entry is RiskMapPoint => Boolean(entry))
    : [];
}

export async function getRiskMapCoverage(): Promise<RiskMapCoverage> {
  if (USE_MOCK_API) return mockCoverage();
  const res = await API.get("/dashboard/risk-map/coverage", { headers: API_HEADERS, params: { mode: "online" } });
  return normalizeRiskMapCoverage(res.data);
}

export async function getLatestGlobalFeatures(): Promise<LatestGlobalResponse> {
  if (USE_MOCK_API) return mockLatestGlobal();
  const res = await API.get("/features/global/latest", { headers: API_HEADERS, params: { mode: "online" } });
  return res.data as LatestGlobalResponse;
}

export async function getInternetMapSnapshot(): Promise<InternetMapSnapshot> {
  if (USE_MOCK_API) return mockInternetMapSnapshot();
  try {
    const res = await API.get("/dashboard/internet-map", { headers: API_HEADERS, params: { mode: "online" } });
    return res.data as InternetMapSnapshot;
  } catch (error) {
    if (isOfflineApiError(error)) return mockInternetMapSnapshot();
    throw error;
  }
}

export async function getInternetMapHistory(limit = 24): Promise<InternetMapHistoryResponse> {
  if (USE_MOCK_API) {
    const snapshot = mockInternetMapSnapshot();
    return {
      items: snapshot.history ?? [],
      replay_available: Boolean(snapshot.replay_available),
      latest_captured_at: snapshot.stream_status?.captured_at ?? snapshot.generated_at,
      stream_status: snapshot.stream_status,
    };
  }
  try {
    const res = await API.get("/dashboard/internet-map/history", { headers: API_HEADERS, params: { limit } });
    return res.data as InternetMapHistoryResponse;
  } catch (error) {
    if (isOfflineApiError(error)) {
      const snapshot = mockInternetMapSnapshot();
      return {
        items: snapshot.history ?? [],
        replay_available: Boolean(snapshot.replay_available),
        latest_captured_at: snapshot.stream_status?.captured_at ?? snapshot.generated_at,
        stream_status: snapshot.stream_status,
      };
    }
    throw error;
  }
}

export async function getInternetMapPlayback(limit = 36): Promise<InternetMapPlaybackResponse> {
  const buildMockPlayback = (): InternetMapPlaybackResponse => {
    const snapshot = mockInternetMapSnapshot();
    const history = [...(snapshot.history ?? [])].slice(0, Math.max(1, limit));
    const baseline = history.length
      ? history
      : [{
          run_id: `mock-playback-${snapshot.generated_at}`,
          captured_at: snapshot.generated_at,
          global_congestion_index: snapshot.summary.global_congestion_index,
          cyber_attack_index: snapshot.summary.cyber_attack_index,
          active_attack_paths: snapshot.summary.active_attack_paths,
          shutdown_alerts: snapshot.summary.shutdown_alerts,
          source_status: snapshot.summary.source_status,
          source_stage: snapshot.summary.source_stage,
          collector_total_records: snapshot.collector_summary?.total_records ?? 0,
        }];
    const frameCount = baseline.length;
    const frames = baseline.map((item, index) => {
      const drift = (index - frameCount / 2) * 2.2;
      return {
        run_id: item.run_id,
        captured_at: item.captured_at,
        generated_at: item.captured_at,
        summary: {
          ...snapshot.summary,
          global_congestion_index: Math.max(0, Math.min(100, item.global_congestion_index + drift)),
          cyber_attack_index: Math.max(0, Math.min(100, item.cyber_attack_index + drift * 0.7)),
          active_attack_paths: item.active_attack_paths,
          shutdown_alerts: item.shutdown_alerts,
          source_status: item.source_status,
          source_stage: item.source_stage ?? snapshot.summary.source_stage,
        },
        countries: snapshot.countries.map((country) => ({
          ...country,
          congestion_index: Math.max(0, Math.min(100, country.congestion_index + drift * (country.country === "IND" || country.country === "LKA" ? 1.25 : 0.45))),
          attack_index: Math.max(0, Math.min(100, country.attack_index + drift * (country.country === "USA" ? 0.85 : 0.35))),
          shutdown_risk: Math.max(0, Math.min(100, country.shutdown_risk + drift * (country.country === "LKA" ? 1.1 : 0.25))),
        })),
        flows: snapshot.flows.map((flow) => ({
          ...flow,
          congestion_index: Math.max(0, Math.min(100, flow.congestion_index + drift * (flow.origin === "IND" || flow.destination === "IND" ? 1.15 : 0.5))),
          attack_index: Math.max(0, Math.min(100, flow.attack_index + drift * (flow.origin === "USA" || flow.destination === "USA" ? 0.9 : 0.4))),
          packet_loss_pct: Math.max(0, flow.packet_loss_pct + drift * 0.04),
        })),
        cyber_attacks: snapshot.cyber_attacks,
        shutdown_alerts: snapshot.shutdown_alerts,
        top_corridors: snapshot.top_corridors,
        source_health: snapshot.source_health,
        generated_from: snapshot.generated_from,
        collector_summary: snapshot.collector_summary,
        stream_status: snapshot.stream_status,
      } satisfies InternetMapPlaybackFrame;
    });
    return {
      frames,
      replay_available: Boolean(frames.length),
      latest_captured_at: frames.length ? frames[frames.length - 1].captured_at : snapshot.generated_at,
      stream_status: snapshot.stream_status,
    };
  };

  if (USE_MOCK_API) return buildMockPlayback();
  try {
    const res = await API.get("/dashboard/internet-map/playback", { headers: API_HEADERS, params: { limit } });
    return res.data as InternetMapPlaybackResponse;
  } catch (error) {
    if (isOfflineApiError(error)) return buildMockPlayback();
    throw error;
  }
}

export async function getInternetMapStreamStatus(refresh = false, refreshSources = false): Promise<InternetMapStreamStatusResponse | null> {
  if (USE_MOCK_API) {
    const snapshot = mockInternetMapSnapshot();
    return {
      run_id: snapshot.stream_status?.run_id,
      status: snapshot.stream_status?.status,
      captured_at: snapshot.stream_status?.captured_at ?? snapshot.generated_at,
      collector_summary: snapshot.collector_summary,
      stream_status: snapshot.stream_status,
      history: snapshot.history,
    };
  }
  try {
    const res = await API.get("/api/internet-map/stream/status", {
      headers: API_HEADERS,
      params: { mode: "online", refresh, refresh_sources: refreshSources },
    });
    return res.data as InternetMapStreamStatusResponse;
  } catch {
    return null;
  }
}

export async function postInternetMapAlertAction(payload: InternetMapAlertActionPayload): Promise<InternetMapAlertActionResponse | null> {
  try {
    const res = await API.post("/api/internet-map/alerts/action", payload, { headers: API_HEADERS });
    return res.data as InternetMapAlertActionResponse;
  } catch {
    return null;
  }
}

export async function getInternetMapBacktest(): Promise<InternetMapBacktestSummary | null> {
  try {
    const res = await API.get("/dashboard/internet-map/backtest", { headers: API_HEADERS });
    return res.data as InternetMapBacktestSummary;
  } catch {
    return null;
  }
}

export async function runInternetMapBacktest(days = 30): Promise<InternetMapBacktestSummary | null> {
  try {
    const res = await API.post("/api/internet-map/backtests/run", null, { headers: API_HEADERS, params: { days } });
    return res.data as InternetMapBacktestSummary;
  } catch {
    return null;
  }
}

export async function runInternetMapMaintenance(retentionDays = 30, streamRetentionDays = 30, backtestRetentionDays = 90, collectorRetentionDays = 30): Promise<Record<string, unknown> | null> {
  try {
    const res = await API.post("/api/internet-map/maintenance/prune", null, {
      headers: API_HEADERS,
      params: {
        retention_days: retentionDays,
        stream_retention_days: streamRetentionDays,
        backtest_retention_days: backtestRetentionDays,
        collector_retention_days: collectorRetentionDays,
      },
    });
    return res.data as Record<string, unknown>;
  } catch {
    return null;
  }
}

export async function runInternetMapStreamCycle(refreshSources = true): Promise<InternetMapStreamStatusResponse | null> {
  try {
    const res = await API.post("/api/internet-map/stream/run-cycle", null, {
      headers: API_HEADERS,
      params: { mode: "online", refresh_sources: refreshSources },
    });
    return {
      run_id: res.data?.run_id,
      status: res.data?.status,
      captured_at: res.data?.captured_at,
      collector_summary: res.data?.collector_summary,
      stream_status: res.data?.stream_status,
      runtime_status: res.data?.payload?.runtime_status ?? res.data?.runtime_status,
      history: res.data?.payload?.history,
    } as InternetMapStreamStatusResponse;
  } catch {
    return null;
  }
}
export async function refreshRiskMapBatch(batchSize = 50): Promise<boolean> {
  try {
    await API.post("/dashboard/risk-map/refresh", { batch_size: batchSize, max_records: 4 }, { headers: API_HEADERS });
    return true;
  } catch {
    return false;
  }
}

export async function getCountryDrilldown(country: string): Promise<CountryDrilldownData> {
  if (USE_MOCK_API) return mockCountryDrilldown(country);
  try {
    const res = await API.get(`/country-intelligence/${country}`, { headers: API_HEADERS, params: { mode: "online" } });
    return normalizeCountryDrilldown(res.data, country);
  } catch (error) {
    if (isOfflineApiError(error)) return mockCountryDrilldown(country);
    throw error;
  }
}

export async function getGovernanceData(): Promise<GovernanceData> {
  if (USE_MOCK_API) return mockGovernance();
  try {
    const res = await API.get("/dashboard/governance", { headers: API_HEADERS, params: { mode: "online" } });
    return normalizeGovernanceData(res.data);
  } catch (error) {
    if (isOfflineApiError(error)) return mockGovernance();
    throw error;
  }
}

export async function postAlertAction(payload: AlertActionPayload): Promise<boolean> {
  try {
    await API.post("/dashboard/alerts/action", payload, { headers: API_HEADERS });
    return true;
  } catch {
    return false;
  }
}

export type DisasterAlertActionPayload = {
  hazard: string;
  region: string;
  country?: string;
  action: "acknowledge" | "snooze" | "escalate" | "false_positive";
  owner?: string;
  comment?: string;
  alert_id?: string;
  dedupe_key?: string;
  snooze_hours?: number;
  false_positive_reason?: string;
};

export type DisasterAlertActionResponse = {
  ok: boolean;
  action?: string;
  dedupe_key?: string;
  snoozed_until?: string | null;
};

export async function postDisasterAlertAction(payload: DisasterAlertActionPayload): Promise<DisasterAlertActionResponse | null> {
  try {
    const res = await API.post("/api/disasters/alerts/action", payload, { headers: API_HEADERS });
    return res.data as DisasterAlertActionResponse;
  } catch {
    return null;
  }
}

export type UserRole = "admin" | "user";
export type UserType = "researcher" | "policy" | "student" | "developer";

export type UserProfile = {
  id?: string;
  email: string;
  name: string;
  organization?: string | null;
  role: UserRole;
  user_type: UserType;
  active: boolean;
  deactivated_at?: string | null;
  deactivated_by?: string | null;
  created_at?: string;
  updated_at?: string;
  auth_type?: string;
};

const normalizeUserRole = (value: unknown): UserRole => {
  return String(value).toLowerCase() === "admin" ? "admin" : "user";
};

const normalizeUserType = (value: unknown, fallback: UserType = "researcher"): UserType => {
  const candidate = String(value || "").toLowerCase();
  if (candidate === "researcher" || candidate === "policy" || candidate === "student" || candidate === "developer") {
    return candidate;
  }
  return fallback;
};

const normalizeUserProfile = (value: unknown): UserProfile => {
  if (!isRecord(value)) {
    return {
      email: "",
      name: "",
      role: "user",
      user_type: "researcher",
      active: true,
      deactivated_at: null,
      deactivated_by: null,
    };
  }

  const role = normalizeUserRole(value.role);
  const userTypeFallback: UserType = role === "admin" ? "developer" : "researcher";

  return {
    id: typeof value.id === "string" ? value.id : undefined,
    email: typeof value.email === "string" ? value.email : "",
    name: typeof value.name === "string" ? value.name : "",
    organization: typeof value.organization === "string" ? value.organization : null,
    role,
    user_type: normalizeUserType(value.user_type, userTypeFallback),
    active: value.active !== false,
    deactivated_at: typeof value.deactivated_at === "string" ? value.deactivated_at : null,
    deactivated_by: typeof value.deactivated_by === "string" ? value.deactivated_by : null,
    created_at: typeof value.created_at === "string" ? value.created_at : undefined,
    updated_at: typeof value.updated_at === "string" ? value.updated_at : undefined,
    auth_type: typeof value.auth_type === "string" ? value.auth_type : undefined,
  };
};

export async function getCurrentUser(): Promise<UserProfile> {
  const res = await API.get("/auth/me", { headers: API_HEADERS });
  return normalizeUserProfile(res.data);
}

export async function updateCurrentUserProfile(payload: { name?: string; organization?: string | null }): Promise<UserProfile> {
  const res = await API.patch("/auth/me", payload, { headers: API_HEADERS });
  return normalizeUserProfile(res.data);
}

export async function changeCurrentUserPassword(payload: {
  current_password: string;
  new_password: string;
}): Promise<{ message: string }> {
  const res = await API.post("/auth/change-password", payload, { headers: API_HEADERS });
  return {
    message: typeof res.data?.message === "string" ? res.data.message : "Password updated successfully",
  };
}

export async function getAdminUsers(): Promise<UserProfile[]> {
  const res = await API.get("/admin/users", { headers: API_HEADERS });
  const payload = isRecord(res.data) ? res.data : {};
  const rows = Array.isArray(payload.users) ? payload.users : [];
  return rows
    .filter(isRecord)
    .map((row) => normalizeUserProfile(row));
}

export async function updateAdminUserAccess(
  email: string,
  payload: Partial<Pick<UserProfile, "role" | "user_type">>
): Promise<UserProfile> {
  const res = await API.patch(`/admin/users/${encodeURIComponent(email)}/access`, payload, { headers: API_HEADERS });
  return normalizeUserProfile(res.data);
}

export async function updateAdminUserStatus(email: string, active: boolean): Promise<UserProfile> {
  const res = await API.patch(
    `/admin/users/${encodeURIComponent(email)}/status`,
    { active },
    { headers: API_HEADERS }
  );
  return normalizeUserProfile(res.data);
}

export type HealthStatus = {
  status: string;
  [key: string]: unknown;
};

export type HealthDependenciesResponse = {
  status?: string;
  dependencies?: Record<string, unknown>;
};

export type ObservabilityMetrics = {
  runtime?: Record<string, unknown>;
  security?: Record<string, unknown>;
};

export type ObservabilityModelSummary = Record<string, unknown>;
export type ObservabilityStreamingSummary = Record<string, unknown>;
export type ValidationSummary = Record<string, unknown>;

export async function getHealthLive(): Promise<HealthStatus> {
  const res = await API.get("/health/live", { headers: API_HEADERS });
  return (res.data ?? {}) as HealthStatus;
}

export async function getHealthReady(): Promise<HealthStatus> {
  const res = await API.get("/health/ready", { headers: API_HEADERS });
  return (res.data ?? {}) as HealthStatus;
}

export async function getHealthDependencies(mode: string = "online"): Promise<HealthDependenciesResponse> {
  const res = await API.get("/health/dependencies", { headers: API_HEADERS, params: { mode } });
  return (res.data ?? {}) as HealthDependenciesResponse;
}

export async function getObservabilityMetrics(): Promise<ObservabilityMetrics> {
  const res = await API.get("/observability/metrics", { headers: API_HEADERS });
  return (res.data ?? {}) as ObservabilityMetrics;
}

export async function getObservabilityModel(window: number = 200): Promise<ObservabilityModelSummary> {
  const res = await API.get("/observability/model", { headers: API_HEADERS, params: { window } });
  return (res.data ?? {}) as ObservabilityModelSummary;
}

export async function getObservabilityStreaming(): Promise<ObservabilityStreamingSummary> {
  const res = await API.get("/observability/streaming", { headers: API_HEADERS });
  return (res.data ?? {}) as ObservabilityStreamingSummary;
}

export async function getCountryRiskValidationSummary(): Promise<ValidationSummary> {
  const res = await API.get("/observability/country-risk-validation", { headers: API_HEADERS });
  return (res.data ?? {}) as ValidationSummary;
}

export async function getGlobalMoodValidationSummary(): Promise<ValidationSummary> {
  const res = await API.get("/observability/global-mood-validation", { headers: API_HEADERS });
  return (res.data ?? {}) as ValidationSummary;
}

export type ValidationHistoryResponse = {
  rows: ValidationSummary[];
  limit: number;
};

export type BacktestSummary = Record<string, unknown>;
export type BacktestHistoryResponse = {
  rows: BacktestSummary[];
  limit: number;
};

export type TrustReliabilitySnapshot = {
  generated_at?: string;
  api_health?: Record<string, unknown>;
  uptime?: Record<string, unknown>;
  data_freshness?: Record<string, unknown>;
  latest_ingestion?: Record<string, unknown>;
  source_health?: Record<string, unknown>;
  coverage?: Record<string, unknown>;
  quality_gate?: Record<string, unknown>;
  confidence?: Record<string, unknown>;
  mobility?: Record<string, unknown>;
  economic?: Record<string, unknown>;
  alerts?: Array<Record<string, unknown>>;
  validation?: Record<string, unknown>;
};

export async function getCountryRiskValidationHistory(limit: number = 30): Promise<ValidationHistoryResponse> {
  const res = await API.get("/observability/country-risk-validation/history", { headers: API_HEADERS, params: { limit } });
  const payload = isRecord(res.data) ? res.data : {};
  return {
    rows: Array.isArray(payload.rows) ? (payload.rows as ValidationSummary[]) : [],
    limit: Number.isFinite(Number(payload.limit)) ? Number(payload.limit) : limit,
  };
}

export async function getGlobalMoodValidationHistory(limit: number = 30): Promise<ValidationHistoryResponse> {
  const res = await API.get("/observability/global-mood-validation/history", { headers: API_HEADERS, params: { limit } });
  const payload = isRecord(res.data) ? res.data : {};
  return {
    rows: Array.isArray(payload.rows) ? (payload.rows as ValidationSummary[]) : [],
    limit: Number.isFinite(Number(payload.limit)) ? Number(payload.limit) : limit,
  };
}

export async function getCountryRiskBacktestSummary(): Promise<BacktestSummary> {
  const res = await API.get("/observability/country-risk-backtest", { headers: API_HEADERS });
  return (res.data ?? {}) as BacktestSummary;
}

export async function getGlobalMoodBacktestSummary(): Promise<BacktestSummary> {
  const res = await API.get("/observability/global-mood-backtest", { headers: API_HEADERS });
  return (res.data ?? {}) as BacktestSummary;
}

export async function runObservabilityBacktests(days: number = 60): Promise<Record<string, unknown>> {
  const res = await API.post("/observability/backtests/run", null, { headers: API_HEADERS, params: { days } });
  return (res.data ?? {}) as Record<string, unknown>;
}

export async function getTrustReliability(mode: string = "online"): Promise<TrustReliabilitySnapshot> {
  if (USE_MOCK_API) return mockTrustReliability();
  try {
    const res = await API.get("/trust/reliability", { headers: API_HEADERS, params: { mode } });
    const payload = isRecord(res.data) ? res.data : {};
    return {
      generated_at: typeof payload.generated_at === "string" ? payload.generated_at : undefined,
      api_health: isRecord(payload.api_health) ? payload.api_health : {},
      uptime: isRecord(payload.uptime) ? payload.uptime : {},
      data_freshness: isRecord(payload.data_freshness) ? payload.data_freshness : {},
      latest_ingestion: isRecord(payload.latest_ingestion) ? payload.latest_ingestion : {},
      source_health: isRecord(payload.source_health) ? payload.source_health : {},
      coverage: isRecord(payload.coverage) ? payload.coverage : {},
      quality_gate: isRecord(payload.quality_gate) ? payload.quality_gate : {},
      confidence: isRecord(payload.confidence) ? payload.confidence : {},
      mobility: isRecord(payload.mobility) ? payload.mobility : {},
      economic: isRecord(payload.economic) ? payload.economic : {},
      alerts: Array.isArray(payload.alerts) ? (payload.alerts as Array<Record<string, unknown>>) : [],
      validation: isRecord(payload.validation) ? payload.validation : {},
    };
  } catch (error) {
    if (isOfflineApiError(error)) return mockTrustReliability();
    throw error;
  }
}

export async function getTrustCountryBacktests(limit: number = 30): Promise<BacktestHistoryResponse> {
  const res = await API.get("/trust/backtests/country", { headers: API_HEADERS, params: { limit } });
  const payload = isRecord(res.data) ? res.data : {};
  return {
    rows: Array.isArray(payload.rows) ? (payload.rows as BacktestSummary[]) : [],
    limit: Number.isFinite(Number(payload.limit)) ? Number(payload.limit) : limit,
  };
}

export async function getTrustGlobalMoodBacktests(limit: number = 30): Promise<BacktestHistoryResponse> {
  const res = await API.get("/trust/backtests/global-mood", { headers: API_HEADERS, params: { limit } });
  const payload = isRecord(res.data) ? res.data : {};
  return {
    rows: Array.isArray(payload.rows) ? (payload.rows as BacktestSummary[]) : [],
    limit: Number.isFinite(Number(payload.limit)) ? Number(payload.limit) : limit,
  };
}

export type SystemMonitoringResponse = {
  server_status?: Record<string, unknown>;
  api_health?: Record<string, unknown>;
  data_pipeline_status?: Record<string, unknown>;
  uptime_statistics?: Record<string, unknown>;
  mobility?: Record<string, unknown>;
  economic?: Record<string, unknown>;
  alerts?: Array<Record<string, unknown>>;
};

export type SecurityLogEvent = {
  _id?: string;
  timestamp?: string;
  event_type?: string;
  status?: string;
  detail?: string;
  email?: string | null;
  client_ip?: string | null;
  meta?: Record<string, unknown>;
};

export type SecurityLogsResponse = {
  window_minutes?: number;
  generated_at?: string;
  login_attempts?: Record<string, unknown>;
  suspicious_activity?: Record<string, unknown>;
  jwt_token_monitoring?: Record<string, unknown>;
  events: SecurityLogEvent[];
};

const normalizeSecurityLogEvent = (value: unknown): SecurityLogEvent | null => {
  if (!isRecord(value)) return null;
  return {
    _id: typeof value._id === "string" ? value._id : undefined,
    timestamp: typeof value.timestamp === "string" ? value.timestamp : undefined,
    event_type: typeof value.event_type === "string" ? value.event_type : undefined,
    status: typeof value.status === "string" ? value.status : undefined,
    detail: typeof value.detail === "string" ? value.detail : undefined,
    email: typeof value.email === "string" ? value.email : null,
    client_ip: typeof value.client_ip === "string" ? value.client_ip : null,
    meta: isRecord(value.meta) ? value.meta : {},
  };
};

export async function getAdminSystemMonitoring(mode: string = "online"): Promise<SystemMonitoringResponse> {
  const res = await API.get("/admin/system-monitoring", { headers: API_HEADERS, params: { mode } });
  const payload = isRecord(res.data) ? res.data : {};
  return {
    server_status: isRecord(payload.server_status) ? payload.server_status : {},
    api_health: isRecord(payload.api_health) ? payload.api_health : {},
    data_pipeline_status: isRecord(payload.data_pipeline_status) ? payload.data_pipeline_status : {},
    uptime_statistics: isRecord(payload.uptime_statistics) ? payload.uptime_statistics : {},
    mobility: isRecord((isRecord(payload.data_pipeline_status) ? payload.data_pipeline_status.mobility : undefined)) ? (payload.data_pipeline_status as Record<string, unknown>).mobility as Record<string, unknown> : {},
  };
}

export async function getAdminSecurityLogs(
  limit: number = 100,
  minutes: number = 1440
): Promise<SecurityLogsResponse> {
  const res = await API.get("/admin/security-logs", {
    headers: API_HEADERS,
    params: { limit, minutes },
  });

  const payload = isRecord(res.data) ? res.data : {};
  const rows = Array.isArray(payload.events) ? payload.events : [];

  return {
    window_minutes: Number.isFinite(Number(payload.window_minutes)) ? Number(payload.window_minutes) : undefined,
    generated_at: typeof payload.generated_at === "string" ? payload.generated_at : undefined,
    login_attempts: isRecord(payload.login_attempts) ? payload.login_attempts : {},
    suspicious_activity: isRecord(payload.suspicious_activity) ? payload.suspicious_activity : {},
    jwt_token_monitoring: isRecord(payload.jwt_token_monitoring) ? payload.jwt_token_monitoring : {},
    events: rows
      .map(normalizeSecurityLogEvent)
      .filter((row): row is SecurityLogEvent => Boolean(row)),
  };
}
export type ScenarioStep = {
  label: string;
  marketShock: number;
  sentimentShock: number;
  weatherShock: number;
};

export type ScenarioResult = {
  baseline: number[];
  scenario: number[];
  timestamps: string[];
};

export type SentinelDriver = {
  feature: string;
  impact: number;
  display_name?: string;
};

export type SentinelData = {
  timestamp: string;
  risk_score: number;
  risk_delta: number;
  risk_trend: "increasing" | "decreasing" | "stable";
  threat_level: "stable" | "guarded" | "elevated" | "critical";
  top_drivers: SentinelDriver[];
  multi_domain_signal: boolean;
  active_domains?: string[];
  confidence: number;
  analysis_text: string;
};

export async function runScenarioSimulation(steps: ScenarioStep[]): Promise<ScenarioResult> {
  const res = await API.post("/dashboard/scenario/run", { steps }, { headers: API_HEADERS });
  return res.data as ScenarioResult;
}

export type IntelligenceFeedItem = {

  id: string;
  country: string;
  country_name: string;
  headline: string;
  summary: string;
  full_article: string;
  source: string;
  source_url: string;
  risk_score: number;
  timestamp: string;
  category: string;
  relevance_score?: number;
};

export async function getGlobalIntelligenceFeed(params?: { country?: string | null; limit?: number }): Promise<IntelligenceFeedItem[]> {
  try {
    const res = await API.get("/dashboard/global-intelligence-feed", {
      headers: API_HEADERS,
      params: {
        country: params?.country || undefined,
        limit: params?.limit,
      },
    });
    return Array.isArray(res.data) ? (res.data as IntelligenceFeedItem[]) : [];
  } catch {
    return [];
  }
}

export async function getSentinelData(): Promise<SentinelData> {
  const res = await API.get("/api/sentinel/latest", { headers: API_HEADERS });
  return res.data as SentinelData;
}

// =====================================================
// REAL-TIME FEATURES API
// =====================================================

export type CryptoItem = {
  id: string;
  coin_id: string;
  name: string;
  symbol: string;
  price_usd: number;
  change_24h: number;
  change_percent: number;
  volume_24h: number;
  market_cap: number;
  timestamp: string;
  sparkline: number[];
};

export type CryptoPulseData = {
  items: CryptoItem[];
  last_updated: string;
  total_count: number;
};

export type DisasterItem = {
  id: string;
  type: "earthquake" | "weather" | "wildfire" | "flood" | "storm" | "volcano" | "humanitarian" | "conflict";
  title: string;
  location: string;
  coordinates?: {
    lat: number;
    lon: number;
  };
  magnitude?: number;
  severity: "critical" | "elevated" | "guarded";
  depth_km?: number;
  tsunami_risk?: boolean;
  description?: string;
  temperature?: number;
  wind_speed?: number;
  timestamp: string;
  source: string;
  confidence?: number;
  signal_value?: number;
  category?: string;
  is_fallback_observation?: boolean;
  context_tag?: "live" | "older_7d";
  is_broadened_context?: boolean;
};

export type DisasterMonitorData = {
  items: DisasterItem[];
  last_updated: string;
  total_count: number;
};

export type CurrencyRate = {
  pair: string;
  rate: number;
  change_24h: number;
  change_percent: number;
};

export type EconomicRelease = {
  id: string;
  indicator: string;
  value: number;
  date: string;
  timestamp: string;
};

export type KeyIndicator = {
  value: number;
  change: number;
  source: string;
};

export type EconomicIndicatorsData = {
  currency_rates: CurrencyRate[];
  economic_releases: EconomicRelease[];
  key_indicators: {
    interest_rate: KeyIndicator;
    inflation_rate: KeyIndicator;
    unemployment: KeyIndicator;
  };
  last_updated: string;
};

export type HealthAlert = {
  id: string;
  disease: string;
  type: string;
  severity: "critical" | "elevated" | "guarded";
  location: string;
  cases: number | null;
  deaths: number | null;
  indicator_value?: number | null;
  indicator_value_raw?: string | null;
  status: "active" | "monitoring";
  timestamp: string;
  source: string;
  description: string;
  context_tag?: "live" | "older_30d";
  is_broadened_context?: boolean;
};

export type VaccinationData = {
  global_coverage: number;
  target_coverage: number;
  doses_administered: number;
  campaigns_active: number;
};

export type HealthAlertsData = {
  outbreaks: HealthAlert[];
  vaccination: VaccinationData;
  last_updated: string;
  total_active: number;
  context_mode?: "live_only" | "broadened";
  broadened_context_added?: number;
  broaden_context_enabled?: boolean;
};

export type TrendItem = {
  id: string;
  topic: string;
  category: string;
  search_volume: number;
  interest_score: number;
  velocity: number;
  trend_direction: "rising" | "stable" | "falling";
  breakout: boolean;
  timestamp: string;
  related_queries: string[];
  source_mode?: "trending_searches" | "interest_over_time" | string;
  region?: string;
};

export type TrendsSummary = {
  total_trending: number;
  rising_topics: number;
  breakout_topics: number;
  top_category: string;
};

export type TrendsRadarData = {
  trends: TrendItem[];
  summary: TrendsSummary;
  last_updated: string;
};


export type CausalDriver = {
  feature: string;
  label: string;
  value: number;
  weight: number;
  impact: number;
  direction: "upward" | "downward";
};

export type CausalGraphNode = {
  id: string;
  label: string;
  value: number;
  type: "target" | "driver";
};

export type CausalGraphEdge = {
  source: string;
  target: string;
  weight: number;
  polarity: "positive" | "negative";
};

export type CausalExplanationResponse = {
  scope: "global" | "country";
  country?: string | null;
  mode: string;
  risk_score: number;
  risk_delta?: number;
  threat_level: "stable" | "guarded" | "elevated" | "critical";
  drivers: CausalDriver[];
  root_cause_graph: {
    nodes: CausalGraphNode[];
    edges: CausalGraphEdge[];
  };
  evidence: Array<{
    title: string;
    detail: string;
    confidence: number;
  }>;
  timestamp: string;
  data_freshness_minutes?: number | null;
  summary: string;
};

export type CounterfactualResponse = {
  country?: string | null;
  scope: "global" | "country";
  mode: string;
  timestamp: string;
  base_risk_score: number;
  projected_risk_score: number;
  projected_risk_delta: number;
  trajectory: "improving" | "stable" | "worsening";
  confidence: number;
  feature_impacts: Array<{
    feature: string;
    before: number;
    after: number;
    shock: number;
    estimated_risk_delta: number;
  }>;
};

export type ActionPlanResponse = {
  country?: string | null;
  scope: "global" | "country";
  mode: string;
  timestamp: string;
  risk_score: number;
  threat_level: string;
  projected_total_risk_reduction: number;
  recommendations: Array<{
    feature: string;
    title: string;
    action: string;
    priority: "high" | "medium" | "low";
    eta_hours: number;
    expected_risk_reduction: number;
    confidence: number;
  }>;
};

export type PolicyReplayResponse = {
  country?: string | null;
  scope: "global" | "country";
  mode: string;
  timestamp: string;
  interventions: string[];
  baseline_series: Array<{ timestamp: string; risk: number }>;
  simulated_series: Array<{ timestamp: string; risk: number }>;
  baseline_final_risk: number;
  simulated_final_risk: number;
  projected_delta: number;
};

export async function getCryptoPulse(limit: number = 10): Promise<CryptoPulseData> {
  try {
    const res = await API.get("/dashboard/crypto-pulse", { 
      headers: API_HEADERS, 
      params: { limit } 
    });
    const data = (res.data ?? {}) as Partial<CryptoPulseData>;
    return {
      items: Array.isArray(data.items) ? data.items : [],
      last_updated: typeof data.last_updated === "string" ? data.last_updated : new Date().toISOString(),
      total_count: Number.isFinite(Number(data.total_count)) ? Number(data.total_count) : Array.isArray(data.items) ? data.items.length : 0,
    };
  } catch {
    return { items: [], last_updated: new Date().toISOString(), total_count: 0 };
  }
}

export async function getDisasterMonitor(limit: number = 20): Promise<DisasterMonitorData> {
  try {
    const res = await API.get("/dashboard/disaster-monitor", { 
      headers: API_HEADERS, 
      params: { limit } 
    });
    const data = (res.data ?? {}) as Partial<DisasterMonitorData>;
    return {
      items: Array.isArray(data.items) ? data.items : [],
      last_updated: typeof data.last_updated === "string" ? data.last_updated : new Date().toISOString(),
      total_count: Number.isFinite(Number(data.total_count)) ? Number(data.total_count) : Array.isArray(data.items) ? data.items.length : 0,
    };
  } catch {
    return { items: [], last_updated: new Date().toISOString(), total_count: 0 };
  }
}

export async function getEconomicIndicators(): Promise<EconomicIndicatorsData> {
  try {
    const res = await API.get("/dashboard/economic-indicators", { headers: API_HEADERS });
    const data = (res.data ?? {}) as Partial<EconomicIndicatorsData>;
    return {
      currency_rates: Array.isArray(data.currency_rates) ? data.currency_rates : [],
      economic_releases: Array.isArray(data.economic_releases) ? data.economic_releases : [],
      key_indicators: data.key_indicators ?? {
        interest_rate: { value: 0, change: 0, source: "Unavailable" },
        inflation_rate: { value: 0, change: 0, source: "Unavailable" },
        unemployment: { value: 0, change: 0, source: "Unavailable" },
      },
      last_updated: typeof data.last_updated === "string" ? data.last_updated : new Date().toISOString(),
    };
  } catch {
    return {
      currency_rates: [],
      economic_releases: [],
      key_indicators: {
        interest_rate: { value: 0, change: 0, source: "Unavailable" },
        inflation_rate: { value: 0, change: 0, source: "Unavailable" },
        unemployment: { value: 0, change: 0, source: "Unavailable" },
      },
      last_updated: new Date().toISOString(),
    };
  }
}

export async function getHealthAlerts(limit: number = 10): Promise<HealthAlertsData> {
  try {
    const res = await API.get("/dashboard/health-alerts", { 
      headers: API_HEADERS, 
      params: { limit } 
    });
    const data = (res.data ?? {}) as Partial<HealthAlertsData>;
    return {
      outbreaks: Array.isArray(data.outbreaks) ? data.outbreaks : [],
      vaccination: data.vaccination ?? {
        global_coverage: 0,
        target_coverage: 0,
        doses_administered: 0,
        campaigns_active: 0,
      },
      last_updated: typeof data.last_updated === "string" ? data.last_updated : new Date().toISOString(),
      total_active: Number.isFinite(Number(data.total_active)) ? Number(data.total_active) : Array.isArray(data.outbreaks) ? data.outbreaks.length : 0,
    };
  } catch {
    return {
      outbreaks: [],
      vaccination: {
        global_coverage: 0,
        target_coverage: 0,
        doses_administered: 0,
        campaigns_active: 0,
      },
      last_updated: new Date().toISOString(),
      total_active: 0,
    };
  }
}

export async function getTrendsRadar(limit: number = 20): Promise<TrendsRadarData> {
  try {
    const res = await API.get("/dashboard/trends-radar", { 
      headers: API_HEADERS, 
      params: { limit } 
    });
    const data = (res.data ?? {}) as Partial<TrendsRadarData>;
    return {
      trends: Array.isArray(data.trends) ? data.trends : [],
      summary: data.summary ?? {
        total_trending: 0,
        rising_topics: 0,
        breakout_topics: 0,
        top_category: "None",
      },
      last_updated: typeof data.last_updated === "string" ? data.last_updated : new Date().toISOString(),
    };
  } catch {
    return {
      trends: [],
      summary: {
        total_trending: 0,
        rising_topics: 0,
        breakout_topics: 0,
        top_category: "None",
      },
      last_updated: new Date().toISOString(),
    };
  }
}

// =====================================================
// ADVANCED ANALYTICS API
// =====================================================

export type MLPrediction = {
  horizon: string;
  risk_score: number;
  confidence: number;
  interval?: {
    p10: number;
    p50: number;
    p90: number;
  };
  probability_high_risk?: number;
  blend?: {
    neural_weight: number;
    stat_weight: number;
  };
  latency_ms?: number;
};

export type MLPredictionsData = {
  predictions: MLPrediction[];
  model_type: string;
  source?: string;
  source_status?: string;
  calibration_status?: string;
  fallback_reason?: string | null;
};

export type AdvancedMLObservability = {
  prediction_latency_ms?: number;
  model_age_hours?: number;
  model_version?: string;
  calibration_error?: Record<string, number>;
  calibration_mode?: Record<string, string>;
  feature_quality?: {
    active_features?: number;
    features?: Record<
      string,
      {
        variance?: number;
        staleness_hours?: number;
        quality?: number;
        gated?: boolean;
      }
    >;
  };
};

export type AnomalyData = {
  timestamp: string;
  anomaly_score: number;
  features: Record<string, number>;
  severity: "low" | "medium" | "high" | "critical";
};

export type CausalLink = {
  source: string;
  target: string;
  strength: number;
};

export type SentimentMomentumData = {
  velocity: number;
  acceleration: number;
  trend: "accelerating" | "decelerating" | "stable";
  rsi: number;
  macd_signal: string;
};

export type AIReportData = {
  title: string;
  summary: string;
  key_findings: string[];
  recommendations: string[];
  risk_level: string;
};

export type AdvancedFeatureSnapshotEntry = {
  key: string;
  label: string;
  value: number;
  raw_value?: number;
  normalized_value?: number;
  importance?: number;
  direction?: "positive" | "negative" | string;
  scale?: "normalized" | "absolute_100" | "return" | "volatility" | "sentiment" | string;
};

export type AdvancedInsightsData = {
  timestamp: string;
  generated_at?: string;
  predictions: MLPredictionsData;
  forecast_contract?: GlobalForecastContract;
  anomalies: AnomalyData[];
  causal_graph: CausalLink[];
  sentiment_momentum: SentimentMomentumData;
  ai_report: AIReportData;
  feature_snapshot?: AdvancedFeatureSnapshotEntry[];
  governance?: GovernanceData;
  ml_observability?: AdvancedMLObservability;
  data_quality_status?: string;
  advisory?: string;
  reasons?: string[];
};

export async function getMLPredictions(): Promise<MLPredictionsData> {
  const res = await API.get("/analytics/advanced/ml-predictions", { headers: API_HEADERS });
  return res.data as MLPredictionsData;
}

export async function getAnomalies(): Promise<AnomalyData[]> {
  const res = await API.get("/analytics/advanced/anomalies", { headers: API_HEADERS });
  return res.data as AnomalyData[];
}

export async function getCausalGraph(): Promise<CausalLink[]> {
  const res = await API.get("/analytics/advanced/causal", { headers: API_HEADERS });
  return res.data as CausalLink[];
}

export async function getSentimentMomentum(): Promise<SentimentMomentumData> {
  const res = await API.get("/analytics/advanced/sentiment-momentum", { headers: API_HEADERS });
  return res.data as SentimentMomentumData;
}

export async function getAIReport(reportType: string = "brief"): Promise<AIReportData> {
  const res = await API.get("/analytics/advanced/report", { 
    headers: API_HEADERS,
    params: { report_type: reportType }
  });
  return res.data as AIReportData;
}

export async function getAdvancedInsights(): Promise<AdvancedInsightsData> {
  try {
    const res = await API.get("/analytics/advanced/insights", { headers: API_HEADERS, timeout: 35000 });
    return res.data as AdvancedInsightsData;
  } catch (primaryError) {
    const timedOut = axios.isAxiosError(primaryError) && String(primaryError.code || "").toUpperCase() === "ECONNABORTED";
    if (isOfflineApiError(primaryError) || timedOut) {
      throw primaryError;
    }

    const [predictions, anomalies, causal, momentum, report, governance] = await Promise.allSettled([
      API.get("/analytics/advanced/ml-predictions", { headers: API_HEADERS, timeout: 25000 }),
      API.get("/analytics/advanced/anomalies", { headers: API_HEADERS, timeout: 15000 }),
      API.get("/analytics/advanced/causal", { headers: API_HEADERS, timeout: 15000 }),
      API.get("/analytics/advanced/sentiment-momentum", { headers: API_HEADERS, timeout: 15000 }),
      API.get("/analytics/advanced/report", { headers: API_HEADERS, params: { report_type: "brief" }, timeout: 20000 }),
      API.get("/dashboard/governance", { headers: API_HEADERS, params: { mode: "online" }, timeout: 15000 }),
    ]);

    const hasAny = [predictions, anomalies, causal, momentum, report, governance].some((r) => r.status === "fulfilled");
    if (!hasAny) throw primaryError;

    const fallbackPredictions = predictions.status === "fulfilled"
      ? ({
          source: "advanced_analytics",
          source_status: "fallback",
          calibration_status: "fallback",
          fallback_reason: "Canonical advanced insights endpoint was unavailable, so stitched endpoint fallbacks were used.",
          ...(predictions.value.data as MLPredictionsData),
        } as MLPredictionsData)
      : {
          predictions: [],
          model_type: "unavailable",
          source: "advanced_analytics",
          source_status: "model_unavailable",
          calibration_status: "fallback",
          fallback_reason: "Canonical advanced insights endpoint was unavailable.",
        };

    const firstPrediction = Array.isArray(fallbackPredictions.predictions) ? fallbackPredictions.predictions[0] : undefined;
    return {
      timestamp: new Date().toISOString(),
      generated_at: new Date().toISOString(),
      predictions: fallbackPredictions,
      forecast_contract: {
        source: "advanced_analytics",
        source_status: fallbackPredictions.source_status,
        calibration_status: fallbackPredictions.calibration_status,
        gating_action: "downgrade",
        prediction_available: Boolean(firstPrediction),
        withheld: !firstPrediction,
        risk_score: firstPrediction?.risk_score ?? null,
        confidence_ratio: firstPrediction?.confidence ?? 0,
        confidence_score: Math.round((firstPrediction?.confidence ?? 0) * 10000) / 100,
        risk_delta: 0,
        horizon_hours: 24,
        prediction_interval: firstPrediction?.interval ?? null,
        advisory: "Canonical advanced insights endpoint unavailable; page is using stitched advanced fallbacks.",
        reasons: ["canonical advanced insights unavailable"],
        quality_status: "fallback",
        basis: "stitched_fallback",
        model_version: fallbackPredictions.model_type,
        generated_at: new Date().toISOString(),
      },
      anomalies: anomalies.status === "fulfilled" && Array.isArray(anomalies.value.data)
        ? (anomalies.value.data as AnomalyData[])
        : [],
      causal_graph: causal.status === "fulfilled" && Array.isArray(causal.value.data)
        ? (causal.value.data as CausalLink[])
        : [],
      sentiment_momentum:
        momentum.status === "fulfilled"
          ? (momentum.value.data as SentimentMomentumData)
          : { velocity: 0, acceleration: 0, trend: "stable", rsi: 50, macd_signal: "neutral" },
      ai_report:
        report.status === "fulfilled"
          ? (report.value.data as AIReportData)
          : {
              title: "Advanced Analytics Partial Report",
              summary: "Some analytics components were unavailable in time.",
              key_findings: [],
              recommendations: [],
              risk_level: "moderate",
            },
      governance: governance.status === "fulfilled" ? (governance.value.data as GovernanceData) : undefined,
      data_quality_status: "fallback",
      advisory: "Canonical advanced insights endpoint unavailable; page is using stitched advanced fallbacks.",
      reasons: ["canonical advanced insights unavailable"],
    };
  }
}

export default API;




export async function getCausalExplanations(country?: string | null, mode: string = "online"): Promise<CausalExplanationResponse> {
  const params: Record<string, string> = { mode };
  if (country) params.country = country;
  const res = await API.get("/dashboard/causal-explanations", { headers: API_HEADERS, params });
  return res.data as CausalExplanationResponse;
}

export async function runCounterfactual(
  scenario: Record<string, number>,
  country?: string | null,
  mode: string = "online"
): Promise<CounterfactualResponse> {
  const res = await API.post(
    "/dashboard/counterfactual",
    { scenario, country: country || null, mode },
    { headers: API_HEADERS }
  );
  return res.data as CounterfactualResponse;
}

export async function getActionPlan(
  country?: string | null,
  mode: string = "online",
  maxActions: number = 4
): Promise<ActionPlanResponse> {
  const res = await API.post(
    "/dashboard/action-plan",
    { country: country || null, mode, max_actions: maxActions },
    { headers: API_HEADERS }
  );
  return res.data as ActionPlanResponse;
}

export async function runPolicyReplay(
  interventions: string[],
  country?: string | null,
  horizonDays: number = 30,
  mode: string = "online"
): Promise<PolicyReplayResponse> {
  const res = await API.post(
    "/dashboard/policy-replay",
    {
      country: country || null,
      mode,
      horizon_days: horizonDays,
      interventions,
    },
    { headers: API_HEADERS }
  );
  return res.data as PolicyReplayResponse;
}










export type DisasterForecast = {
  event_type: string;
  country: string;
  likelihood: number;
  severity_score: number;
  confidence: number;
  lead_time_hours: number;
  signal_sources: string[];
  top_contributing_signals: string[];
  recommended_action: string;
  updated_at: string;
  model_type?: string;
  model_status?: string;
  model_version?: string;
  region?: string;
  region_name?: string;
  regional_hotspots_count?: number;
  feature_values?: Record<string, number>;
  calibration_status?: string;
  calibration_adjustments?: {
    penalty?: number;
    notes?: string[];
  };
};

export type HotspotHistoryPoint = {
  timestamp: string;
  activity: number;
  band?: string;
  event_count?: number;
  intensity_peak?: number;
  quake_count?: number;
  max_magnitude?: number;
  max_temperature?: number;
  rainfall_peak?: number;
  max_wind_speed?: number;
};

export type DisasterRegionalHotspot = {
  event_type: string;
  region: string;
  region_name?: string;
  region_label?: string;
  display_label?: string;
  center_lat?: number;
  center_lon?: number;
  likelihood: number;
  severity_score: number;
  confidence: number;
  lead_time_hours: number;
  signal_sources?: string[];
  top_contributing_signals?: string[];
  updated_at: string;
  activity_score?: number;
  hotspot_score?: number;
  hotspot_confidence?: number;
  hotspot_band?: string;
  activity_trend?: "accelerating" | "cooling" | "steady" | string;
  trend_points?: number[];
  calibration_status?: string;
  calibration_adjustments?: {
    penalty?: number;
    notes?: string[];
  };
  history?: Partial<Record<"6h" | "24h" | "72h", HotspotHistoryPoint[]>>;
  hotspot_stats?: {
    event_count?: number;
    intensity_peak?: number;
    quake_count?: number;
    max_magnitude?: number;
    strong_event_count?: number;
    major_event_count?: number;
    detection_count?: number;
    weather_trigger_count?: number;
    smoke_signal_count?: number;
    max_temperature?: number;
    max_wind_speed?: number;
    cross_source_hits?: number;
    flood_detection_count?: number;
    max_rainfall?: number;
    surge_proxy?: number;
    storm_detection_count?: number;
    ocean_heat_proxy?: number;
    pressure_proxy?: number;
  };
};

export type HotspotMover = {
  hazard?: string;
  region: string;
  region_name?: string;
  region_label?: string;
  display_label?: string;
  delta: number;
  current_band: string;
  current_activity: number;
  latest_timestamp: string;
};

export type DisasterSourceFamily = "satellite_imagery" | "seismic_data" | "weather_sensors" | "ocean_sensors" | "social_media_signals";

export type DisasterSourceHealth = {
  source_family: DisasterSourceFamily;
  status: string;
  records: number;
  last_success?: string | null;
  freshness_minutes?: number | null;
  component_sources: string[];
  rate_limited?: boolean;
  auth_failed?: boolean;
  advisory?: string;
  errors?: string[];
};

export type DisasterAlertOpsState = {
  status: string;
  action_counts?: Partial<Record<"acknowledge" | "snooze" | "escalate" | "false_positive", number>>;
  false_positive_count?: number;
  last_action?: string | null;
  last_timestamp?: string | null;
  owner?: string | null;
  comment?: string | null;
  snoozed_until?: string | null;
  is_snoozed?: boolean;
};

export type DisasterAlertOpsSummary = {
  acknowledged: number;
  snoozed_active: number;
  escalated: number;
  false_positive_flags: number;
  total_actions: number;
  suppressed_by_snooze: number;
  active_queue_count: number;
};

export type HotspotAlertQueueItem = {
  hazard?: string;
  region: string;
  region_name?: string;
  region_label?: string;
  display_label?: string;
  priority_band: string;
  activity: number;
  confidence: number;
  timestamp: string;
  signals: string[];
  signal_sources?: DisasterSourceFamily[];
  top_contributing_signals?: string[];
  recommended_action?: string;
  lead_time_hours?: number;
  alert_id?: string;
  dedupe_key?: string;
  threshold_met?: boolean;
  threshold_reason?: string;
  feedback_adjustment?: number;
  adjusted_activity?: number;
  ops_state?: DisasterAlertOpsState;
};

export type HotspotAlertTransition = {
  hazard?: string;
  region: string;
  region_name?: string;
  region_label?: string;
  timestamp: string;
  from_band?: string | null;
  to_band: string;
  delta_activity: number;
};

export type HotspotHistoryHealth = {
  status: string;
  latest_captured_at?: string | null;
  age_minutes?: number | null;
  advisory?: string;
};

export type HotspotRegionHistoryResponse = {
  hazard?: string;
  region: string;
  region_name?: string;
  region_label?: string;
  display_label?: string;
  status: string;
  history: Partial<Record<"6h" | "24h" | "72h", HotspotHistoryPoint[]>>;
  latest?: DisasterRegionalHotspot | Record<string, unknown> | null;
  delta_badge?: { label: string; delta: number };
  alert_history: HotspotAlertTransition[];
};


export type DisasterBacktestHazardSummary = {
  hazard: string;
  evaluated_alerts: number;
  matched_follow_on_events: number;
  false_positives: number;
  precision_proxy: number;
  false_positive_rate: number;
  avg_confidence: number;
  avg_lead_time_hours: number;
  top_true_positive_regions?: Record<string, number>;
  top_false_positive_regions?: Record<string, number>;
};

export type DisasterBacktestSummary = {
  generated_at?: string | null;
  status?: string;
  window_days?: number;
  hazards?: Record<string, DisasterBacktestHazardSummary>;
  overall?: {
    evaluated_alerts: number;
    matched_follow_on_events: number;
    false_positives: number;
    precision_proxy: number;
    false_positive_rate: number;
    weighted_avg_confidence: number;
  };
};

export type DisasterStreamStatus = {
  status: string;
  run_id?: string;
  captured_at?: string | null;
  refresh_sources?: boolean;
  cycle_latency_ms?: number;
  model_monitor_rows?: number;
  collector_total_records?: number;
  stale_families?: number;
  down_families?: number;
  backtest_precision_proxy?: number;
  forecast_count?: number;
  active_alerts?: number;
};

export type DisasterEarlyWarningResponse = {
  generated_at: string;
  country: string;
  summary: {
    critical_or_high_count: number;
    watch_count: number;
    top_hazard?: string | null;
    top_seismic_region?: string | null;
    top_seismic_region_name?: string | null;
    top_wildfire_region?: string | null;
    top_wildfire_region_name?: string | null;
    top_flood_region?: string | null;
    top_flood_region_name?: string | null;
    top_cyclone_region?: string | null;
    top_cyclone_region_name?: string | null;
  };
  forecasts: DisasterForecast[];
  regional_hotspots?: {
    earthquake?: DisasterRegionalHotspot[];
    wildfire?: DisasterRegionalHotspot[];
    flood?: DisasterRegionalHotspot[];
    cyclone?: DisasterRegionalHotspot[];
  };
  hotspot_history_health?: HotspotHistoryHealth;
  trend_comparison?: Partial<Record<"earthquake" | "wildfire" | "flood" | "cyclone", {
    accelerating_fastest: HotspotMover[];
    cooling_fastest: HotspotMover[];
  }>>;
  alert_queue?: Partial<Record<"earthquake" | "wildfire" | "flood" | "cyclone", HotspotAlertQueueItem[]>>;
  source_families?: DisasterSourceFamily[];
  source_health?: DisasterSourceHealth[];
  alert_ops_summary?: DisasterAlertOpsSummary;
  legend?: {
    bands: Array<{ key: string; label: string; color: string }>;
    trend_windows: Array<{ key: string; hours: number }>;
    hazards?: Array<{ key: string; label: string }>;
  };
  named_region_metadata_version?: string;
  recent_alert_transitions?: Partial<Record<"earthquake" | "wildfire" | "flood" | "cyclone", HotspotAlertTransition[]>>;
  stream_status?: DisasterStreamStatus;
  backtest_summary?: DisasterBacktestSummary;
  seismic_anomaly?: Record<string, unknown>;
  cyclone_tracker?: Record<string, unknown>;
  method: string;
  notes: string[];
  last_updated: string;
};


export type DisasterThermalCountry = {
  country: string;
  country_name?: string;
  avg_temperature_c: number;
  thermal_index: number;
  risk_score: number;
  weather_stress: number;
  source_confidence: number;
  sample_count: number;
  center_lat?: number | null;
  center_lon?: number | null;
};

export type DisasterThermalCell = {
  cell_id: string;
  country: string;
  lat: number;
  lon: number;
  sector_label: string;
  district_label?: string;
  temperature_c: number;
  thermal_index: number;
  hazard_pressure: number;
  confidence: number;
  risk_score: number;
  weather_stress: number;
  lead_time_hours: number;
  wind_kph: number;
  humidity_pct: number;
  active_hazard: string;
  signal_sources: string[];
  sample_type?: string;
  city_anchor?: string;
};

export type DisasterThermalFocus = {
  center_lat?: number | null;
  center_lon?: number | null;
  avg_temperature_c?: number | null;
  peak_temperature_c?: number | null;
  peak_thermal_index?: number | null;
  avg_hazard_pressure?: number | null;
  district_count?: number;
  zoom_scale?: number;
  country_risk_score?: number;
  source_confidence?: number;
};

export type DisasterThermalMapResponse = {
  generated_at: string;
  selected_country?: string | null;
  hazard_filter?: string;
  colorscale?: Array<[number, string]>;
  countries: DisasterThermalCountry[];
  cells: DisasterThermalCell[];
  focus?: DisasterThermalFocus;
};

const DISASTER_SOURCE_FAMILY_VALUES: DisasterSourceFamily[] = [
  "satellite_imagery",
  "seismic_data",
  "weather_sensors",
  "ocean_sensors",
  "social_media_signals",
];

function normalizeDisasterSourceFamilies(value: unknown): DisasterSourceFamily[] {
  if (!Array.isArray(value)) return [];
  const allowed = new Set<string>(DISASTER_SOURCE_FAMILY_VALUES);
  return value
    .map((entry) => String(entry || "").trim())
    .filter((entry): entry is DisasterSourceFamily => allowed.has(entry));
}

function normalizeDisasterSourceHealth(value: unknown): DisasterSourceHealth[] {
  if (!Array.isArray(value)) return [];
  const rows: DisasterSourceHealth[] = [];
  for (const entry of value) {
    const row = (entry ?? {}) as Partial<DisasterSourceHealth>;
    const family = normalizeDisasterSourceFamilies([row.source_family])[0];
    if (!family) continue;
    rows.push({
      source_family: family,
      status: typeof row.status === "string" ? row.status : "unknown",
      records: Number.isFinite(Number(row.records)) ? Number(row.records) : 0,
      last_success: typeof row.last_success === "string" ? row.last_success : null,
      freshness_minutes: Number.isFinite(Number(row.freshness_minutes)) ? Number(row.freshness_minutes) : null,
      component_sources: Array.isArray(row.component_sources) ? row.component_sources.map((item) => String(item || "")).filter(Boolean) : [],
      rate_limited: Boolean(row.rate_limited),
      auth_failed: Boolean(row.auth_failed),
      advisory: typeof row.advisory === "string" ? row.advisory : undefined,
      errors: Array.isArray(row.errors) ? row.errors.map((item) => String(item || "")).filter(Boolean) : [],
    });
  }
  return rows;
}

function normalizeHotspotAlertQueueItems(value: unknown): HotspotAlertQueueItem[] {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => {
    const item = (entry ?? {}) as Partial<HotspotAlertQueueItem>;
    return {
      hazard: typeof item.hazard === "string" ? item.hazard : undefined,
      region: typeof item.region === "string" ? item.region : "unknown",
      region_name: typeof item.region_name === "string" ? item.region_name : undefined,
      region_label: typeof item.region_label === "string" ? item.region_label : undefined,
      display_label: typeof item.display_label === "string" ? item.display_label : undefined,
      priority_band: typeof item.priority_band === "string" ? item.priority_band : "monitor",
      activity: Number.isFinite(Number(item.activity)) ? Number(item.activity) : 0,
      confidence: Number.isFinite(Number(item.confidence)) ? Number(item.confidence) : 0,
      timestamp: typeof item.timestamp === "string" ? item.timestamp : new Date().toISOString(),
      signals: Array.isArray(item.signals) ? item.signals.map((signal) => String(signal || "")).filter(Boolean) : [],
      signal_sources: normalizeDisasterSourceFamilies(item.signal_sources),
      top_contributing_signals: Array.isArray(item.top_contributing_signals) ? item.top_contributing_signals.map((signal) => String(signal || "")).filter(Boolean) : [],
      recommended_action: typeof item.recommended_action === "string" ? item.recommended_action : undefined,
      lead_time_hours: Number.isFinite(Number(item.lead_time_hours)) ? Number(item.lead_time_hours) : undefined,
      alert_id: typeof item.alert_id === "string" ? item.alert_id : undefined,
      dedupe_key: typeof item.dedupe_key === "string" ? item.dedupe_key : undefined,
      threshold_met: typeof item.threshold_met === "boolean" ? item.threshold_met : undefined,
      threshold_reason: typeof item.threshold_reason === "string" ? item.threshold_reason : undefined,
      feedback_adjustment: Number.isFinite(Number(item.feedback_adjustment)) ? Number(item.feedback_adjustment) : undefined,
      adjusted_activity: Number.isFinite(Number(item.adjusted_activity)) ? Number(item.adjusted_activity) : undefined,
      ops_state: item.ops_state && typeof item.ops_state === "object"
        ? {
            status: typeof item.ops_state.status === "string" ? item.ops_state.status : "new",
            action_counts: item.ops_state.action_counts,
            false_positive_count: Number.isFinite(Number(item.ops_state.false_positive_count)) ? Number(item.ops_state.false_positive_count) : 0,
            last_action: typeof item.ops_state.last_action === "string" ? item.ops_state.last_action : null,
            last_timestamp: typeof item.ops_state.last_timestamp === "string" ? item.ops_state.last_timestamp : null,
            owner: typeof item.ops_state.owner === "string" ? item.ops_state.owner : null,
            comment: typeof item.ops_state.comment === "string" ? item.ops_state.comment : null,
            snoozed_until: typeof item.ops_state.snoozed_until === "string" ? item.ops_state.snoozed_until : null,
            is_snoozed: Boolean(item.ops_state.is_snoozed),
          }
        : undefined,
    } satisfies HotspotAlertQueueItem;
  });
}


function normalizeDisasterBacktestSummary(value: unknown): DisasterBacktestSummary | undefined {
  if (!value || typeof value !== "object") return undefined;
  const row = value as Partial<DisasterBacktestSummary>;
  const overall = row.overall && typeof row.overall === "object"
    ? {
        evaluated_alerts: Number.isFinite(Number(row.overall.evaluated_alerts)) ? Number(row.overall.evaluated_alerts) : 0,
        matched_follow_on_events: Number.isFinite(Number(row.overall.matched_follow_on_events)) ? Number(row.overall.matched_follow_on_events) : 0,
        false_positives: Number.isFinite(Number(row.overall.false_positives)) ? Number(row.overall.false_positives) : 0,
        precision_proxy: Number.isFinite(Number(row.overall.precision_proxy)) ? Number(row.overall.precision_proxy) : 0,
        false_positive_rate: Number.isFinite(Number(row.overall.false_positive_rate)) ? Number(row.overall.false_positive_rate) : 0,
        weighted_avg_confidence: Number.isFinite(Number(row.overall.weighted_avg_confidence)) ? Number(row.overall.weighted_avg_confidence) : 0,
      }
    : undefined;
  return {
    generated_at: typeof row.generated_at === "string" ? row.generated_at : null,
    status: typeof row.status === "string" ? row.status : undefined,
    window_days: Number.isFinite(Number(row.window_days)) ? Number(row.window_days) : undefined,
    hazards: row.hazards && typeof row.hazards === "object" ? row.hazards as Record<string, DisasterBacktestHazardSummary> : undefined,
    overall,
  };
}

function normalizeDisasterStreamStatus(value: unknown): DisasterStreamStatus | undefined {
  if (!value || typeof value !== "object") return undefined;
  const row = value as Partial<DisasterStreamStatus>;
  return {
    status: typeof row.status === "string" ? row.status : "idle",
    run_id: typeof row.run_id === "string" ? row.run_id : undefined,
    captured_at: typeof row.captured_at === "string" ? row.captured_at : null,
    refresh_sources: typeof row.refresh_sources === "boolean" ? row.refresh_sources : undefined,
    cycle_latency_ms: Number.isFinite(Number(row.cycle_latency_ms)) ? Number(row.cycle_latency_ms) : undefined,
    model_monitor_rows: Number.isFinite(Number(row.model_monitor_rows)) ? Number(row.model_monitor_rows) : undefined,
    collector_total_records: Number.isFinite(Number(row.collector_total_records)) ? Number(row.collector_total_records) : undefined,
    stale_families: Number.isFinite(Number(row.stale_families)) ? Number(row.stale_families) : undefined,
    down_families: Number.isFinite(Number(row.down_families)) ? Number(row.down_families) : undefined,
    backtest_precision_proxy: Number.isFinite(Number(row.backtest_precision_proxy)) ? Number(row.backtest_precision_proxy) : undefined,
    forecast_count: Number.isFinite(Number(row.forecast_count)) ? Number(row.forecast_count) : undefined,
    active_alerts: Number.isFinite(Number(row.active_alerts)) ? Number(row.active_alerts) : undefined,
  };
}

function isValidDisasterEarlyWarningResponse(data: unknown): data is DisasterEarlyWarningResponse {
  const candidate = data as DisasterEarlyWarningResponse | null;
  return Boolean(
    candidate
    && typeof candidate === "object"
    && candidate.summary
    && Array.isArray(candidate.forecasts)
  );
}


function normalizeDisasterThermalMapResponse(data: Partial<DisasterThermalMapResponse> | null | undefined): DisasterThermalMapResponse {
  return {
    generated_at: typeof data?.generated_at === "string" ? data.generated_at : new Date().toISOString(),
    selected_country: typeof data?.selected_country === "string" ? data.selected_country : null,
    hazard_filter: typeof data?.hazard_filter === "string" ? data.hazard_filter : "all",
    colorscale: Array.isArray(data?.colorscale)
      ? data.colorscale
          .map((entry) => Array.isArray(entry) && entry.length >= 2 ? [Number(entry[0]) || 0, String(entry[1] || "")] as [number, string] : null)
          .filter((entry): entry is [number, string] => Boolean(entry && entry[1]))
      : [],
    countries: Array.isArray(data?.countries)
      ? data.countries.map((row) => ({
          country: typeof row.country === "string" ? row.country : "GLB",
          country_name: typeof row.country_name === "string" ? row.country_name : undefined,
          avg_temperature_c: Number.isFinite(Number(row.avg_temperature_c)) ? Number(row.avg_temperature_c) : 0,
          thermal_index: Number.isFinite(Number(row.thermal_index)) ? Number(row.thermal_index) : 0,
          risk_score: Number.isFinite(Number(row.risk_score)) ? Number(row.risk_score) : 0,
          weather_stress: Number.isFinite(Number(row.weather_stress)) ? Number(row.weather_stress) : 0,
          source_confidence: Number.isFinite(Number(row.source_confidence)) ? Number(row.source_confidence) : 0,
          sample_count: Number.isFinite(Number(row.sample_count)) ? Number(row.sample_count) : 0,
          center_lat: Number.isFinite(Number(row.center_lat)) ? Number(row.center_lat) : null,
          center_lon: Number.isFinite(Number(row.center_lon)) ? Number(row.center_lon) : null,
        }))
      : [],
    cells: Array.isArray(data?.cells)
      ? data.cells.map((row) => ({
          cell_id: typeof row.cell_id === "string" ? row.cell_id : crypto.randomUUID(),
          country: typeof row.country === "string" ? row.country : "GLB",
          lat: Number.isFinite(Number(row.lat)) ? Number(row.lat) : 0,
          lon: Number.isFinite(Number(row.lon)) ? Number(row.lon) : 0,
          sector_label: typeof row.sector_label === "string" ? row.sector_label : "Sector",
          district_label: typeof row.district_label === "string" ? row.district_label : undefined,
          temperature_c: Number.isFinite(Number(row.temperature_c)) ? Number(row.temperature_c) : 0,
          thermal_index: Number.isFinite(Number(row.thermal_index)) ? Number(row.thermal_index) : 0,
          hazard_pressure: Number.isFinite(Number(row.hazard_pressure)) ? Number(row.hazard_pressure) : 0,
          confidence: Number.isFinite(Number(row.confidence)) ? Number(row.confidence) : 0,
          risk_score: Number.isFinite(Number(row.risk_score)) ? Number(row.risk_score) : 0,
          weather_stress: Number.isFinite(Number(row.weather_stress)) ? Number(row.weather_stress) : 0,
          lead_time_hours: Number.isFinite(Number(row.lead_time_hours)) ? Number(row.lead_time_hours) : 0,
          wind_kph: Number.isFinite(Number(row.wind_kph)) ? Number(row.wind_kph) : 0,
          humidity_pct: Number.isFinite(Number(row.humidity_pct)) ? Number(row.humidity_pct) : 0,
          active_hazard: typeof row.active_hazard === "string" ? row.active_hazard : "thermal",
          signal_sources: Array.isArray(row.signal_sources) ? row.signal_sources.map((item) => String(item || "")).filter(Boolean) : [],
          sample_type: typeof row.sample_type === "string" ? row.sample_type : undefined,
          city_anchor: typeof row.city_anchor === "string" ? row.city_anchor : undefined,
        }))
      : [],
    focus: data?.focus && typeof data.focus === "object"
      ? {
          center_lat: Number.isFinite(Number(data.focus.center_lat)) ? Number(data.focus.center_lat) : null,
          center_lon: Number.isFinite(Number(data.focus.center_lon)) ? Number(data.focus.center_lon) : null,
          avg_temperature_c: Number.isFinite(Number(data.focus.avg_temperature_c)) ? Number(data.focus.avg_temperature_c) : null,
          peak_temperature_c: Number.isFinite(Number(data.focus.peak_temperature_c)) ? Number(data.focus.peak_temperature_c) : null,
          peak_thermal_index: Number.isFinite(Number(data.focus.peak_thermal_index)) ? Number(data.focus.peak_thermal_index) : null,
          avg_hazard_pressure: Number.isFinite(Number(data.focus.avg_hazard_pressure)) ? Number(data.focus.avg_hazard_pressure) : null,
          district_count: Number.isFinite(Number(data.focus.district_count)) ? Number(data.focus.district_count) : 0,
          zoom_scale: Number.isFinite(Number(data.focus.zoom_scale)) ? Number(data.focus.zoom_scale) : undefined,
          country_risk_score: Number.isFinite(Number(data.focus.country_risk_score)) ? Number(data.focus.country_risk_score) : undefined,
          source_confidence: Number.isFinite(Number(data.focus.source_confidence)) ? Number(data.focus.source_confidence) : undefined,
        }
      : undefined,
  };
}

function normalizeDisasterEarlyWarningResponse(data: Partial<DisasterEarlyWarningResponse> | null | undefined): DisasterEarlyWarningResponse {
  return {
    generated_at: typeof data?.generated_at === "string" ? data.generated_at : new Date().toISOString(),
    country: typeof data?.country === "string" ? data.country : "GLB",
    summary: {
      critical_or_high_count: Number.isFinite(Number(data?.summary?.critical_or_high_count)) ? Number(data?.summary?.critical_or_high_count) : 0,
      watch_count: Number.isFinite(Number(data?.summary?.watch_count)) ? Number(data?.summary?.watch_count) : 0,
      top_hazard: typeof data?.summary?.top_hazard === "string" ? data.summary.top_hazard : null,
      top_seismic_region: typeof data?.summary?.top_seismic_region === "string" ? data.summary.top_seismic_region : null,
      top_seismic_region_name: typeof data?.summary?.top_seismic_region_name === "string" ? data.summary.top_seismic_region_name : null,
      top_wildfire_region: typeof data?.summary?.top_wildfire_region === "string" ? data.summary.top_wildfire_region : null,
      top_wildfire_region_name: typeof data?.summary?.top_wildfire_region_name === "string" ? data.summary.top_wildfire_region_name : null,
      top_flood_region: typeof data?.summary?.top_flood_region === "string" ? data.summary.top_flood_region : null,
      top_flood_region_name: typeof data?.summary?.top_flood_region_name === "string" ? data.summary.top_flood_region_name : null,
      top_cyclone_region: typeof data?.summary?.top_cyclone_region === "string" ? data.summary.top_cyclone_region : null,
      top_cyclone_region_name: typeof data?.summary?.top_cyclone_region_name === "string" ? data.summary.top_cyclone_region_name : null,
    },
    forecasts: Array.isArray(data?.forecasts) ? data.forecasts : [],
    regional_hotspots: data?.regional_hotspots && typeof data.regional_hotspots === "object"
      ? {
          earthquake: Array.isArray(data.regional_hotspots.earthquake) ? data.regional_hotspots.earthquake : [],
          wildfire: Array.isArray(data.regional_hotspots.wildfire) ? data.regional_hotspots.wildfire : [],
          flood: Array.isArray(data.regional_hotspots.flood) ? data.regional_hotspots.flood : [],
          cyclone: Array.isArray(data.regional_hotspots.cyclone) ? data.regional_hotspots.cyclone : [],
        }
      : undefined,
    hotspot_history_health: data?.hotspot_history_health,
    trend_comparison: data?.trend_comparison,
    alert_queue: data?.alert_queue && typeof data.alert_queue === "object"
      ? {
          earthquake: normalizeHotspotAlertQueueItems(data.alert_queue.earthquake),
          wildfire: normalizeHotspotAlertQueueItems(data.alert_queue.wildfire),
          flood: normalizeHotspotAlertQueueItems(data.alert_queue.flood),
          cyclone: normalizeHotspotAlertQueueItems(data.alert_queue.cyclone),
        }
      : undefined,
    source_families: normalizeDisasterSourceFamilies(data?.source_families),
    source_health: normalizeDisasterSourceHealth(data?.source_health),
    alert_ops_summary: data?.alert_ops_summary
      ? {
          acknowledged: Number.isFinite(Number(data.alert_ops_summary.acknowledged)) ? Number(data.alert_ops_summary.acknowledged) : 0,
          snoozed_active: Number.isFinite(Number(data.alert_ops_summary.snoozed_active)) ? Number(data.alert_ops_summary.snoozed_active) : 0,
          escalated: Number.isFinite(Number(data.alert_ops_summary.escalated)) ? Number(data.alert_ops_summary.escalated) : 0,
          false_positive_flags: Number.isFinite(Number(data.alert_ops_summary.false_positive_flags)) ? Number(data.alert_ops_summary.false_positive_flags) : 0,
          total_actions: Number.isFinite(Number(data.alert_ops_summary.total_actions)) ? Number(data.alert_ops_summary.total_actions) : 0,
          suppressed_by_snooze: Number.isFinite(Number(data.alert_ops_summary.suppressed_by_snooze)) ? Number(data.alert_ops_summary.suppressed_by_snooze) : 0,
          active_queue_count: Number.isFinite(Number(data.alert_ops_summary.active_queue_count)) ? Number(data.alert_ops_summary.active_queue_count) : 0,
        }
      : undefined,
    legend: data?.legend,
    named_region_metadata_version: typeof data?.named_region_metadata_version === "string" ? data.named_region_metadata_version : undefined,
    recent_alert_transitions: data?.recent_alert_transitions,
    stream_status: normalizeDisasterStreamStatus(data?.stream_status),
    backtest_summary: normalizeDisasterBacktestSummary(data?.backtest_summary),
    seismic_anomaly: data?.seismic_anomaly && typeof data.seismic_anomaly === "object" ? data.seismic_anomaly as Record<string, unknown> : undefined,
    cyclone_tracker: data?.cyclone_tracker && typeof data.cyclone_tracker === "object" ? data.cyclone_tracker as Record<string, unknown> : undefined,
    method: typeof data?.method === "string" ? data.method : "api fallback",
    notes: Array.isArray(data?.notes) ? data.notes : [],
    last_updated: typeof data?.last_updated === "string" ? data.last_updated : new Date().toISOString(),
  };
}

const mockDisasterEarlyWarning = (): DisasterEarlyWarningResponse => ({
  generated_at: new Date().toISOString(),
  country: 'GLB',
  summary: {
    critical_or_high_count: 2,
    watch_count: 2,
    top_hazard: 'wildfire',
    top_seismic_region: 'seismic_03_01',
    top_seismic_region_name: 'Aleutian Arc',
    top_wildfire_region: 'wildfire_06_03',
    top_wildfire_region_name: 'California Chaparral',
    top_flood_region: 'flood_06_14',
    top_flood_region_name: 'Ganges-Brahmaputra Delta',
    top_cyclone_region: 'cyclone_05_14',
    top_cyclone_region_name: 'Bay of Bengal Cyclone Basin',
  },
  forecasts: [
    {
      event_type: 'wildfire',
      country: 'GLB',
      region: 'wildfire_06_03',
      region_name: 'California Chaparral',
      likelihood: 0.71,
      severity_score: 0.76,
      confidence: 0.64,
      lead_time_hours: 18,
      signal_sources: ['weather', 'world_state'],
      top_contributing_signals: ['heat stress', 'fire detection clustering'],
      recommended_action: 'Prioritize wildfire patrol zones and response readiness.',
      updated_at: new Date().toISOString(),
      model_type: 'offline_mock',
      model_status: 'mock',
      model_version: 'mock-v1',
      feature_values: { heat_score: 0.78, wind_score: 0.52 },
    },
    {
      event_type: 'earthquake',
      country: 'GLB',
      region: 'seismic_03_01',
      region_name: 'Aleutian Arc',
      likelihood: 0.62,
      severity_score: 0.66,
      confidence: 0.57,
      lead_time_hours: 12,
      signal_sources: ['seismic'],
      top_contributing_signals: ['regional seismic sequence', 'hotspot clustering'],
      recommended_action: 'Review readiness for this active seismic region and monitor the next 12 hours closely.',
      updated_at: new Date().toISOString(),
      model_type: 'offline_mock',
      model_status: 'mock',
      model_version: 'mock-v1',
      feature_values: { max_magnitude_score: 0.61 },
    },
  ],
  regional_hotspots: {
    earthquake: [
      {
        event_type: 'earthquake',
        region: 'seismic_03_01',
        region_name: 'Aleutian Arc',
        region_label: '30N / 140W sector',
        display_label: 'Aleutian Arc (30N / 140W sector)',
        center_lat: 28,
        center_lon: -142,
        likelihood: 0.62,
        severity_score: 0.66,
        confidence: 0.57,
        lead_time_hours: 12,
        updated_at: new Date().toISOString(),
        activity_score: 0.71,
        hotspot_score: 0.71,
        hotspot_confidence: 0.61,
        hotspot_band: 'active',
        activity_trend: 'accelerating',
        trend_points: [0.31, 0.36, 0.41, 0.49, 0.58, 0.71],
        hotspot_stats: { event_count: 11, intensity_peak: 3.4, quake_count: 11, max_magnitude: 3.4, strong_event_count: 1, major_event_count: 0 },
      },
    ],
    wildfire: [
      {
        event_type: 'wildfire',
        region: 'wildfire_06_03',
        region_name: 'California Chaparral',
        region_label: '35N / 119W sector',
        display_label: 'California Chaparral (35N / 119W sector)',
        center_lat: 35,
        center_lon: -119,
        likelihood: 0.73,
        severity_score: 0.75,
        confidence: 0.65,
        lead_time_hours: 18,
        updated_at: new Date().toISOString(),
        activity_score: 0.78,
        hotspot_score: 0.78,
        hotspot_confidence: 0.68,
        hotspot_band: 'critical',
        activity_trend: 'accelerating',
        trend_points: [0.35, 0.39, 0.48, 0.55, 0.67, 0.78],
        hotspot_stats: { event_count: 24, intensity_peak: 41.2, detection_count: 24, weather_trigger_count: 8, smoke_signal_count: 5, max_temperature: 41.2, max_wind_speed: 32.6, cross_source_hits: 2 },
      },
      {
        event_type: 'wildfire',
        region: 'wildfire_02_16',
        region_name: 'Mediterranean Fire Belt',
        region_label: '38N / 12E sector',
        display_label: 'Mediterranean Fire Belt (38N / 12E sector)',
        center_lat: 38,
        center_lon: 12,
        likelihood: 0.59,
        severity_score: 0.61,
        confidence: 0.56,
        lead_time_hours: 18,
        updated_at: new Date().toISOString(),
        activity_score: 0.59,
        hotspot_score: 0.59,
        hotspot_confidence: 0.58,
        hotspot_band: 'active',
        activity_trend: 'steady',
        trend_points: [0.44, 0.45, 0.47, 0.48, 0.54, 0.59],
        hotspot_stats: { event_count: 13, intensity_peak: 37.4, detection_count: 13, weather_trigger_count: 4, smoke_signal_count: 2, max_temperature: 37.4, max_wind_speed: 28.1, cross_source_hits: 2 },
      },
    ],
    flood: [
      {
        event_type: 'flood',
        region: 'flood_06_14',
        region_name: 'Ganges-Brahmaputra Delta',
        region_label: '24N / 90E sector',
        display_label: 'Ganges-Brahmaputra Delta (24N / 90E sector)',
        center_lat: 24,
        center_lon: 90,
        likelihood: 0.68,
        severity_score: 0.72,
        confidence: 0.62,
        lead_time_hours: 24,
        updated_at: new Date().toISOString(),
        activity_score: 0.72,
        hotspot_score: 0.72,
        hotspot_confidence: 0.66,
        hotspot_band: 'critical',
        activity_trend: 'accelerating',
        trend_points: [0.36, 0.41, 0.49, 0.56, 0.63, 0.72],
        hotspot_stats: { event_count: 16, intensity_peak: 88.0, flood_detection_count: 16, max_rainfall: 88.0, max_wind_speed: 24.1, surge_proxy: 0.74, cross_source_hits: 2 },
      },
    ],
    cyclone: [
      {
        event_type: 'cyclone',
        region: 'cyclone_05_14',
        region_name: 'Bay of Bengal Cyclone Basin',
        region_label: '18N / 88E sector',
        display_label: 'Bay of Bengal Cyclone Basin (18N / 88E sector)',
        center_lat: 18,
        center_lon: 88,
        likelihood: 0.66,
        severity_score: 0.69,
        confidence: 0.61,
        lead_time_hours: 30,
        updated_at: new Date().toISOString(),
        activity_score: 0.69,
        hotspot_score: 0.69,
        hotspot_confidence: 0.64,
        hotspot_band: 'active',
        activity_trend: 'steady',
        trend_points: [0.48, 0.5, 0.53, 0.58, 0.63, 0.69],
        hotspot_stats: { event_count: 9, intensity_peak: 74.0, storm_detection_count: 9, max_wind_speed: 74.0, ocean_heat_proxy: 0.64, pressure_proxy: 0.61, cross_source_hits: 2 },
      },
    ],
  },
  hotspot_history_health: { status: 'healthy', latest_captured_at: new Date().toISOString(), age_minutes: 3, advisory: 'Hotspot history is live' },
  trend_comparison: {
    earthquake: {
      accelerating_fastest: [
        { hazard: 'earthquake', region: 'seismic_03_01', region_name: 'Aleutian Arc', region_label: '30N / 140W sector', display_label: 'Aleutian Arc (30N / 140W sector)', delta: 0.21, current_band: 'active', current_activity: 0.71, latest_timestamp: new Date().toISOString() },
      ],
      cooling_fastest: [],
    },
    wildfire: {
      accelerating_fastest: [
        { hazard: 'wildfire', region: 'wildfire_06_03', region_name: 'California Chaparral', region_label: '35N / 119W sector', display_label: 'California Chaparral (35N / 119W sector)', delta: 0.24, current_band: 'critical', current_activity: 0.78, latest_timestamp: new Date().toISOString() },
      ],
      cooling_fastest: [
        { hazard: 'wildfire', region: 'wildfire_02_16', region_name: 'Mediterranean Fire Belt', region_label: '38N / 12E sector', display_label: 'Mediterranean Fire Belt (38N / 12E sector)', delta: -0.05, current_band: 'active', current_activity: 0.59, latest_timestamp: new Date().toISOString() },
      ],
    },
    flood: {
      accelerating_fastest: [
        { hazard: 'flood', region: 'flood_06_14', region_name: 'Ganges-Brahmaputra Delta', region_label: '24N / 90E sector', display_label: 'Ganges-Brahmaputra Delta (24N / 90E sector)', delta: 0.19, current_band: 'critical', current_activity: 0.72, latest_timestamp: new Date().toISOString() },
      ],
      cooling_fastest: [],
    },
    cyclone: {
      accelerating_fastest: [
        { hazard: 'cyclone', region: 'cyclone_05_14', region_name: 'Bay of Bengal Cyclone Basin', region_label: '18N / 88E sector', display_label: 'Bay of Bengal Cyclone Basin (18N / 88E sector)', delta: 0.11, current_band: 'active', current_activity: 0.69, latest_timestamp: new Date().toISOString() },
      ],
      cooling_fastest: [],
    },
  },
  alert_queue: {
    earthquake: [
      { hazard: 'earthquake', region: 'seismic_03_01', region_name: 'Aleutian Arc', region_label: '30N / 140W sector', priority_band: 'active', activity: 0.71, confidence: 0.61, timestamp: new Date().toISOString(), signals: ['regional seismic sequence', 'hotspot clustering'] },
    ],
    wildfire: [
      { hazard: 'wildfire', region: 'wildfire_06_03', region_name: 'California Chaparral', region_label: '35N / 119W sector', priority_band: 'critical', activity: 0.78, confidence: 0.68, timestamp: new Date().toISOString(), signals: ['fire detection clustering', 'heat stress'] },
    ],
    flood: [
      { hazard: 'flood', region: 'flood_06_14', region_name: 'Ganges-Brahmaputra Delta', region_label: '24N / 90E sector', priority_band: 'critical', activity: 0.72, confidence: 0.66, timestamp: new Date().toISOString(), signals: ['rainfall clustering', 'flood event detections'] },
    ],
    cyclone: [
      { hazard: 'cyclone', region: 'cyclone_05_14', region_name: 'Bay of Bengal Cyclone Basin', region_label: '18N / 88E sector', priority_band: 'active', activity: 0.69, confidence: 0.64, timestamp: new Date().toISOString(), signals: ['storm track clustering', 'wind field intensification'] },
    ],
  },
  legend: {
    bands: [
      { key: 'critical', label: 'Critical', color: '#f87171' },
      { key: 'active', label: 'Active', color: '#fbbf24' },
      { key: 'monitor', label: 'Monitor', color: '#38bdf8' },
      { key: 'guarded', label: 'Guarded', color: '#94a3b8' },
    ],
    trend_windows: [
      { key: '6h', hours: 6 },
      { key: '24h', hours: 24 },
      { key: '72h', hours: 72 },
    ],
    hazards: [
      { key: 'earthquake', label: 'Earthquake' },
      { key: 'wildfire', label: 'Wildfire' },
      { key: 'flood', label: 'Flood' },
      { key: 'cyclone', label: 'Cyclone' },
    ],
  },
  named_region_metadata_version: 'multi-hazard-v2',
  method: 'offline fallback',
  notes: ['Backend unavailable; using mock disaster warning data.'],
  last_updated: new Date().toISOString(),
});

export async function getDisasterEarlyWarning(country?: string): Promise<DisasterEarlyWarningResponse> {
  if (USE_MOCK_API) return mockDisasterEarlyWarning();

  try {
    const res = await API.get('/dashboard/disaster-early-warning', { headers: API_HEADERS, params: country ? { country } : undefined });
    if (isValidDisasterEarlyWarningResponse(res.data)) {
      return normalizeDisasterEarlyWarningResponse(res.data);
    }
  } catch (error) {
    if (isOfflineApiError(error)) return mockDisasterEarlyWarning();
  }

  try {
    const monitorRes = await API.get('/dashboard/disaster-monitor', {
      headers: API_HEADERS,
      params: { limit: 20 },
    });
    const forecastSummary = (monitorRes.data ?? {}).forecast_summary as Partial<DisasterEarlyWarningResponse> | undefined;
    if (forecastSummary) {
      return normalizeDisasterEarlyWarningResponse(forecastSummary);
    }
  } catch (error) {
    if (isOfflineApiError(error)) return mockDisasterEarlyWarning();
  }

  return mockDisasterEarlyWarning();
}



export async function getDisasterThermalMap(country?: string, hazard?: string, focusLat?: number, focusLon?: number): Promise<DisasterThermalMapResponse> {
  if (USE_MOCK_API) {
    return normalizeDisasterThermalMapResponse({
      generated_at: new Date().toISOString(),
      selected_country: country ?? null,
      hazard_filter: hazard ?? "all",
      countries: [{ country: country ?? "USA", country_name: "United States", avg_temperature_c: 31.2, thermal_index: 0.82, risk_score: 61, weather_stress: 0.42, source_confidence: 0.8, sample_count: 8, center_lat: 37.2, center_lon: -96.4 }],
      cells: [
        { cell_id: "mock-1", country: country ?? "USA", lat: focusLat ?? 37.7, lon: focusLon ?? -95.4, sector_label: "Sector 01", district_label: "Sector 01", temperature_c: 33.1, thermal_index: 0.88, hazard_pressure: 0.61, confidence: 0.74, risk_score: 61, weather_stress: 0.42, lead_time_hours: 18, wind_kph: 22, humidity_pct: 54, active_hazard: hazard ?? "wildfire", signal_sources: ["weather_sensors", "satellite_imagery"], sample_type: "observed" },
        { cell_id: "mock-2", country: country ?? "USA", lat: (focusLat ?? 37.7) + 1.4, lon: (focusLon ?? -95.4) + 1.1, sector_label: "Sector 02", district_label: "Sector 02", temperature_c: 29.4, thermal_index: 0.67, hazard_pressure: 0.33, confidence: 0.68, risk_score: 61, weather_stress: 0.42, lead_time_hours: 24, wind_kph: 16, humidity_pct: 48, active_hazard: hazard ?? "flood", signal_sources: ["weather_sensors"], sample_type: "modeled" },
      ],
      focus: { center_lat: focusLat ?? 37.7, center_lon: focusLon ?? -95.4, avg_temperature_c: 31.2, peak_temperature_c: 33.1, peak_thermal_index: 0.88, avg_hazard_pressure: 0.47, district_count: 2, zoom_scale: 3.2, country_risk_score: 61, source_confidence: 0.8 },
    });
  }
  const res = await API.get('/api/disasters/thermal-map', { headers: API_HEADERS, params: { country, hazard, focus_lat: focusLat, focus_lon: focusLon } });
  return normalizeDisasterThermalMapResponse((res.data ?? {}) as Partial<DisasterThermalMapResponse>);
}

export async function getDisasterHotspotHistory(region: string, hours: number = 72, hazard?: string): Promise<HotspotRegionHistoryResponse> {
  if (USE_MOCK_API) {
    return {
      region,
      region_name: 'Mock Hotspot Region',
      region_label: '0N / 0E sector',
      display_label: 'Mock Hotspot Region (0N / 0E sector)',
      status: 'active',
      history: {
        '6h': [{ timestamp: new Date().toISOString(), activity: 0.42, band: 'monitor' }],
        '24h': [{ timestamp: new Date().toISOString(), activity: 0.38, band: 'monitor' }],
        '72h': [{ timestamp: new Date().toISOString(), activity: 0.31, band: 'guarded' }],
      },
      latest: null,
      delta_badge: { label: 'flat', delta: 0 },
      alert_history: [],
    };
  }
  const res = await API.get('/api/disasters/hotspots/history', { headers: API_HEADERS, params: { region, hours, hazard } });
  return res.data as HotspotRegionHistoryResponse;
}

export async function getDisasterHotspotTopMovers(hours: number = 24, limit: number = 6, hazard?: string): Promise<{ accelerating_fastest: HotspotMover[]; cooling_fastest: HotspotMover[] }> {
  if (USE_MOCK_API) {
    const trend = mockDisasterEarlyWarning().trend_comparison?.[(hazard as "earthquake" | "wildfire") || "earthquake"];
    return trend || { accelerating_fastest: [], cooling_fastest: [] };
  }
  const res = await API.get('/api/disasters/hotspots/top-movers', { headers: API_HEADERS, params: { hours, limit, hazard } });
  return res.data as { accelerating_fastest: HotspotMover[]; cooling_fastest: HotspotMover[] };
}

export async function getDisasterHotspotAlertTransitions(hours: number = 72, limit: number = 20, hazard?: string): Promise<{ items: HotspotAlertTransition[]; history_health?: HotspotHistoryHealth }> {
  if (USE_MOCK_API) {
    return { items: [] };
  }
  const res = await API.get('/api/disasters/hotspots/alert-transitions', { headers: API_HEADERS, params: { hours, limit, hazard } });
  return res.data as { items: HotspotAlertTransition[]; history_health?: HotspotHistoryHealth };
}

export type SeismicRegionalHotspot = DisasterRegionalHotspot;




export type PlanetaryGeography = {
  scope?: string;
  country?: string | null;
  origin?: string | null;
  destination?: string | null;
  region?: string | null;
  from_country?: string | null;
  to_country?: string | null;
};

export type PlanetaryTopDimension = {
  metric: string;
  value: number;
  subsystem?: string;
};

export type PlanetaryGlobalSummary = {
  generated_at: string;
  freshness_sec: number;
  confidence_ratio: number;
  global_stress_level: number;
  conflict_escalation_probability: number;
  economic_panic_indicator: number;
  migration_pressure_index: number;
  infrastructure_fragility_score: number;
  quality_gate?: {
    active?: boolean;
    message?: string;
    reasons?: string[];
  };
  top_contributing_dimensions?: PlanetaryTopDimension[];
  provenance_summary?: Record<string, unknown>;
};

export type PlanetaryCountrySnapshot = {
  country: string;
  generated_at: string;
  freshness_sec: number;
  confidence_ratio: number;
  signal_scores?: Record<string, number>;
  top_alerts?: Array<{ type?: string; severity?: string; reason?: string }>;
  source_health?: Record<string, unknown>;
  provenance_summary?: Record<string, unknown>;
  risk_band?: string;
  confidence_band?: string;
  display_risk?: number;
  raw_risk_score?: number;
  risk_delta_24h?: number;
  risk_delta_7d?: number;
  risk_trend_direction?: string;
  spillover_links?: Array<{ country?: string; risk?: number; relationship?: string }>;
  advisory?: string;
};

export type PlanetaryCorridorSnapshot = {
  corridor_id: string;
  from_region?: { country?: string; label?: string };
  to_region?: { country?: string; label?: string };
  generated_at: string;
  freshness_sec: number;
  confidence_ratio: number;
  flow_metrics?: {
    throughput_gbps?: number;
    latency_ms?: number;
    packet_loss_pct?: number;
    reroute_factor?: number;
    congestion_index?: number;
    attack_index?: number;
    anomaly_score?: number;
    traffic_share?: number;
  };
  severity_score?: number;
  related_entities?: string[];
  provenance_summary?: Record<string, unknown>;
};

export type PlanetaryHazardForecast = {
  forecast_id: string;
  hazard_type: string;
  region: string;
  country: string;
  generated_at: string;
  forecast_horizon?: Record<string, unknown>;
  likelihood: number;
  severity_score: number;
  confidence_ratio: number;
  top_contributing_signals?: string[];
  recommended_action?: string;
  provenance_refs?: Array<Record<string, unknown>>;
};

export type PlanetaryAlertEvent = {
  alert_id: string;
  alert_type: string;
  generated_at: string;
  geography?: PlanetaryGeography;
  severity_score: number;
  confidence_ratio: number;
  freshness_sec: number;
  related_entities_or_regions?: string[];
  summary: string;
  recommended_action?: string;
  status?: string;
  assignment?: Record<string, unknown>;
  sla_state?: Record<string, unknown>;
  provenance_refs?: Array<Record<string, unknown>>;
  dedupe_key?: string;
  ops_state?: Record<string, unknown>;
};

export type PlanetaryReplayFrame = {
  frame_id: string;
  generated_at: string;
  frame_timestamp: string;
  frame_type: string;
  geography?: PlanetaryGeography;
  snapshot_refs?: string[];
  alert_refs?: string[];
  confidence_summary?: Record<string, unknown>;
  source_health_summary?: Record<string, unknown>;
};

export type PlanetaryRuntimeStatus = {
  runtime_name: string;
  generated_at: string;
  status: string;
  last_success_at?: string | null;
  last_error_at?: string | null;
  freshness_sec: number;
  queue_depth: number;
  cycle_latency_ms: number;
  cache_hit_ratio: number;
  error_summary?: string | null;
};

export type PlanetaryRuntimeManifest = {
  captured_at?: string;
  run_id?: string;
  mode?: string;
  contract_version?: string;
  platform_scope?: string;
  behavior_country_count?: number;
  behavior_replay_count?: number;
  command_theater_count?: number;
  command_watchlist_count?: number;
  graph_focus_count?: number;
  disaster_focus_count?: number;
  freshness_sec?: number | null;
  runtime_status?: Record<string, unknown>;
  [key: string]: unknown;
};

export type PlanetaryRuntimeStatusResponse = {
  contract_version: string;
  generated_at: string;
  status?: string;
  enabled: boolean;
  interval_seconds: number;
  source_refresh_interval_seconds: number;
  backtest_interval_seconds: number;
  cycle_count?: number;
  last_started_at?: string | null;
  last_completed_at?: string | null;
  last_run_id?: string | null;
  last_reason?: string | null;
  last_error?: string | null;
  last_refresh_sources?: boolean;
  last_run_backtests?: boolean;
  manifest?: PlanetaryRuntimeManifest | null;
  behavior_surface?: PlanetaryBehaviorOperatorSurfaceResponse | null;
  command_layer?: PlanetaryCommandLayerResponse | null;
};

export type PlanetaryBehaviorGlobalSnapshot = {
  contract_version?: string;
  generated_at: string;
  mode?: string;
  freshness_sec: number;
  confidence_ratio: number;
  global_stress_level: number;
  global_behavior_index: number;
  global_context_index: number;
  global_attention_index: number;
  global_disruption_index: number;
  global_economic_stress_index: number;
  economic_panic_indicator: number;
  migration_pressure_index: number;
  global_mood_score?: number;
  global_mood_confidence?: number;
  top_contributing_metrics?: string[];
  top_stressed_countries?: Array<{
    country: string;
    display_risk: number;
    risk_band: string;
    confidence_ratio: number;
    advisory?: string;
  }>;
  quality_gate?: Record<string, unknown>;
  source_health?: Record<string, unknown>;
  provenance_summary?: Record<string, unknown>;
};

export type PlanetarySourceEvent = {
  event_id: string;
  timestamp: string;
  ingested_at?: string;
  source_family: string;
  source_name: string;
  source_provenance?: Record<string, unknown>;
  geography?: PlanetaryGeography;
  raw_payload_ref?: string;
  freshness_sec?: number;
  licensing_or_usage_tier?: string;
  metric_name?: string;
  metric_value?: number;
  event_type?: string;
  scope?: string;
  subsystem?: string;
  run_id?: string;
  mode?: string;
  confidence_ratio?: number;
};

export type PlanetaryNormalizedSignal = {
  signal_id: string;
  timestamp: string;
  generated_at?: string;
  signal_type: string;
  source_family: string;
  source_name: string;
  geography?: PlanetaryGeography;
  entity_refs?: string[];
  metric_name?: string;
  metric_value?: number;
  severity_score?: number;
  confidence_ratio?: number;
  freshness_sec?: number;
  provenance_refs?: Array<Record<string, unknown>>;
  scope?: string;
  subsystem?: string;
  run_id?: string;
  mode?: string;
};

export type PlanetaryWorldEntity = {
  entity_id: string;
  entity_type: string;
  canonical_name: string;
  aliases?: string[];
  geography?: PlanetaryGeography;
  valid_from?: string | null;
  valid_to?: string | null;
  confidence_ratio?: number;
  provenance_refs?: Array<Record<string, unknown>>;
  last_updated_at?: string;
  current_risk_score?: number;
};

export type PlanetaryWorldRelationship = {
  relationship_id: string;
  relationship_type: string;
  source_entity_id: string;
  target_entity_id: string;
  timestamp: string;
  geography?: PlanetaryGeography;
  strength_score: number;
  confidence_ratio: number;
  provenance_refs?: Array<Record<string, unknown>>;
  supporting_evidence_refs?: Array<Record<string, unknown>>;
};

export type PlanetarySignalStoreManifest = {
  status?: string;
  captured_at?: string;
  run_id?: string;
  subsystem?: string;
  mode?: string;
  source_event_count?: number;
  normalized_signal_count?: number;
  source_families?: Record<string, number>;
  signal_types?: Record<string, number>;
  mongo_inserted?: Record<string, number>;
};

export type PlanetaryGraphSnapshotManifest = {
  status?: string;
  captured_at?: string;
  run_id?: string;
  mode?: string;
  world_entity_count?: number;
  world_relationship_count?: number;
  entity_types?: Record<string, number>;
  relationship_types?: Record<string, number>;
  mongo_inserted?: Record<string, number>;
};

export type PlanetaryFusionStoreManifest = {
  status?: string;
  captured_at?: string;
  run_id?: string;
  mode?: string;
  country_fusion_count?: number;
  timeline_frame_count?: number;
  correlation_chain_count?: number;
  fusion_bands?: Record<string, number>;
  chain_types?: Record<string, number>;
  frame_types?: Record<string, number>;
  mongo_inserted?: Record<string, number>;
};

export type PlanetaryAlertOpsSummary = {
  acknowledged?: number;
  assigned?: number;
  snoozed_active?: number;
  false_positive_flags?: number;
  breached_sla_count?: number;
  active_queue_count?: number;
  suppressed_by_snooze?: number;
  queue_breakdown?: Array<{ queue: string; count: number }>;
};

export type PlanetaryCountryFusionSnapshot = {
  fusion_id: string;
  country: string;
  generated_at: string;
  freshness_sec: number;
  confidence_ratio: number;
  fused_score: number;
  fusion_band: string;
  state_vector?: Record<string, number>;
  subsystem_scores?: Record<string, number>;
  related_alert_ids?: string[];
  related_hazard_forecasts?: string[];
  related_corridors?: string[];
  signal_count?: number;
  recommended_action?: string;
  provenance_summary?: Record<string, unknown>;
  correlation_chain_ids?: string[];
};

export type PlanetaryCorrelationStage = {
  stage: string;
  metric: string;
  value: number;
  subsystem?: string;
};

export type PlanetaryCorrelationChain = {
  chain_id: string;
  chain_type: string;
  generated_at: string;
  timestamp: string;
  country: string;
  region?: string;
  summary: string;
  recommended_action?: string;
  likelihood: number;
  confidence_ratio: number;
  freshness_sec?: number;
  stages?: PlanetaryCorrelationStage[];
  alert_refs?: string[];
  entity_refs?: string[];
};

export type PlanetaryFusionTimelineFrame = {
  frame_id: string;
  generated_at: string;
  frame_timestamp: string;
  frame_type: string;
  summary: string;
  country?: string;
  confidence_ratio?: number;
  severity_score?: number;
  subsystems?: string[];
  snapshot_refs?: string[];
  alert_refs?: string[];
  chain_refs?: string[];
};

export type PlanetaryMapReplayCountry = {
  country: string;
  fused_score: number;
  confidence_ratio?: number;
  freshness_sec?: number;
  fusion_band?: string;
  subsystem_scores?: Record<string, number>;
  recommended_action?: string;
};

export type PlanetaryMapReplayCorridor = {
  corridor_id: string;
  from_region?: string;
  to_region?: string;
  from_country?: string;
  to_country?: string;
  severity_score?: number;
  confidence_ratio?: number;
  related_entities?: string[];
  provenance_summary?: Record<string, unknown> | unknown[];
};

export type PlanetaryMapReplayMarker = {
  marker_id: string;
  kind: "hazard" | "alert";
  country?: string;
  region?: string;
  label?: string;
  severity_score?: number;
  confidence_ratio?: number;
  likelihood?: number;
  geography?: PlanetaryGeography;
};

export type PlanetaryMapReplayFrame = {
  contract_version: string;
  platform_scope: string;
  run_id: string;
  frame_id: string;
  captured_at: string;
  generated_at: string;
  frame_timestamp: string;
  mode?: string;
  summary?: string;
  global_summary?: PlanetaryGlobalSummary;
  countries: PlanetaryMapReplayCountry[];
  corridors: PlanetaryMapReplayCorridor[];
  hotspots: PlanetaryMapReplayMarker[];
  graph_focus?: Array<Record<string, unknown>>;
  theaters?: Array<Record<string, unknown>>;
  disaster_focus?: Array<Record<string, unknown>>;
  behavior_replay?: PlanetaryFusionTimelineFrame[];
  calibration_snapshot?: Record<string, unknown>;
  replay_bundle?: {
    country_codes?: string[];
    corridor_ids?: string[];
    hazard_ids?: string[];
    alert_ids?: string[];
    entity_ids?: string[];
  };
};

export type PlanetaryOverviewResponse = {
  contract_version: string;
  generated_at: string;
  mode: string;
  global_summary: PlanetaryGlobalSummary;
  country_snapshots: PlanetaryCountrySnapshot[];
  corridor_snapshots: PlanetaryCorridorSnapshot[];
  hazard_forecasts: PlanetaryHazardForecast[];
  alert_events: PlanetaryAlertEvent[];
  world_entities: PlanetaryWorldEntity[];
  world_relationships: PlanetaryWorldRelationship[];
  replay_frames: PlanetaryReplayFrame[];
  runtime_status: PlanetaryRuntimeStatus[];
  behavior_global_snapshot?: PlanetaryBehaviorGlobalSnapshot;
  behavior_signal_store?: PlanetarySignalStoreManifest;
  graph_snapshot?: PlanetaryGraphSnapshotManifest;
  country_fusion_snapshots?: PlanetaryCountryFusionSnapshot[];
  fusion_timeline?: PlanetaryFusionTimelineFrame[];
  correlation_chains?: PlanetaryCorrelationChain[];
  fusion_store?: PlanetaryFusionStoreManifest;
  alert_ops_summary?: PlanetaryAlertOpsSummary;
};

export type PlanetaryReplayMapFramesResponse = {
  contract_version: string;
  generated_at: string;
  replay_frames: PlanetaryMapReplayFrame[];
  latest_frame?: PlanetaryMapReplayFrame | null;
};

export type PlanetarySourceEventResponse = {
  contract_version: string;
  contract_family: string;
  generated_at: string;
  subsystem?: string;
  count: number;
  source_events: PlanetarySourceEvent[];
};

export type PlanetaryNormalizedSignalResponse = {
  contract_version: string;
  contract_family: string;
  generated_at: string;
  subsystem?: string;
  count: number;
  normalized_signals: PlanetaryNormalizedSignal[];
};

export type PlanetaryWorldEntityResponse = {
  contract_version: string;
  contract_family: string;
  generated_at: string;
  count: number;
  world_entities: PlanetaryWorldEntity[];
};

export type PlanetaryWorldRelationshipResponse = {
  contract_version: string;
  contract_family: string;
  generated_at: string;
  count: number;
  world_relationships: PlanetaryWorldRelationship[];
};

export async function getPlanetaryOverview(refresh = false): Promise<PlanetaryOverviewResponse> {
  const res = await API.get("/api/planetary-intelligence/overview", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      refresh,
      country_limit: 10,
      corridor_limit: 8,
      hazard_limit: 8,
      replay_limit: 8,
    },
  });
  return res.data as PlanetaryOverviewResponse;
}

export async function getPlanetaryBehaviorSourceEvents(limit = 24, refresh = false): Promise<PlanetarySourceEventResponse> {
  const res = await API.get("/api/planetary-intelligence/behavior/source-events", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      limit,
      refresh,
    },
  });
  return res.data as PlanetarySourceEventResponse;
}

export async function getPlanetaryBehaviorNormalizedSignals(limit = 24, refresh = false): Promise<PlanetaryNormalizedSignalResponse> {
  const res = await API.get("/api/planetary-intelligence/behavior/normalized-signals", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      limit,
      refresh,
    },
  });
  return res.data as PlanetaryNormalizedSignalResponse;
}

export async function getPlanetaryGraphEntities(limit = 24, refresh = false): Promise<PlanetaryWorldEntityResponse> {
  const res = await API.get("/api/planetary-intelligence/graph/entities", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      limit,
      refresh,
    },
  });
  return res.data as PlanetaryWorldEntityResponse;
}

export async function getPlanetaryGraphRelationships(limit = 28, refresh = false): Promise<PlanetaryWorldRelationshipResponse> {
  const res = await API.get("/api/planetary-intelligence/graph/relationships", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      limit,
      refresh,
    },
  });
  return res.data as PlanetaryWorldRelationshipResponse;
}


export type PlanetaryCountryFusionResponse = {
  contract_version: string;
  generated_at: string;
  count: number;
  country_fusion_snapshots: PlanetaryCountryFusionSnapshot[];
};

export type PlanetaryFusionTimelineResponse = {
  contract_version: string;
  generated_at: string;
  count: number;
  fusion_timeline: PlanetaryFusionTimelineFrame[];
};

export type PlanetaryCorrelationChainResponse = {
  contract_version: string;
  generated_at: string;
  count: number;
  correlation_chains: PlanetaryCorrelationChain[];
};

export type PlanetaryAlertActionPayload = {
  alert_type: string;
  action: "acknowledge" | "assign" | "snooze" | "false_positive";
  alert_id?: string;
  dedupe_key?: string;
  country?: string;
  region?: string;
  severity?: string;
  owner?: string;
  assignee?: string;
  assignment_reason?: string;
  team_queue?: string;
  sla_hours?: number;
  comment?: string;
  snooze_hours?: number;
  false_positive_reason?: string;
  chain_id?: string;
};

export type PlanetaryAlertActionResponse = {
  ok: boolean;
  action?: string;
  dedupe_key?: string;
  assignee?: string | null;
  team_queue?: string | null;
  snoozed_until?: string | null;
  sla_due_at?: string | null;
};


export async function getPlanetaryCountryFusionSnapshots(limit = 24, refresh = false): Promise<PlanetaryCountryFusionResponse> {
  const res = await API.get("/api/planetary-intelligence/fusion/country-snapshots", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      limit,
      refresh,
    },
  });
  return res.data as PlanetaryCountryFusionResponse;
}

export async function getPlanetaryFusionTimeline(limit = 24, refresh = false): Promise<PlanetaryFusionTimelineResponse> {
  const res = await API.get("/api/planetary-intelligence/fusion/timeline", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      limit,
      refresh,
    },
  });
  return res.data as PlanetaryFusionTimelineResponse;
}

export async function getPlanetaryReplayMapFrames(limit = 24, refresh = false): Promise<PlanetaryReplayMapFramesResponse> {
  const res = await API.get("/api/planetary-intelligence/replay/map-frames", {
    headers: API_HEADERS,
    params: {
      limit,
      refresh,
    },
  });
  return res.data as PlanetaryReplayMapFramesResponse;
}

export async function getPlanetaryCorrelationChains(limit = 18, refresh = false): Promise<PlanetaryCorrelationChainResponse> {
  const res = await API.get("/api/planetary-intelligence/fusion/correlation-chains", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      limit,
      refresh,
    },
  });
  return res.data as PlanetaryCorrelationChainResponse;
}

export async function postPlanetaryAlertAction(payload: PlanetaryAlertActionPayload): Promise<PlanetaryAlertActionResponse> {
  const res = await API.post("/api/planetary-intelligence/alerts/action", payload, { headers: API_HEADERS });
  return res.data as PlanetaryAlertActionResponse;
}


export type PlanetaryOperatorEvent = {
  timestamp: string;
  action?: string;
  actor?: string;
  alert_id?: string;
  alert_type?: string;
  dedupe_key?: string;
  country?: string;
  chain_id?: string;
  assignee?: string | null;
  team_queue?: string | null;
  status?: string | null;
  comment?: string | null;
  snoozed_until?: string | null;
  sla_due_at?: string | null;
};

export type PlanetaryEvidenceSummary = {
  confidence_ratio?: number;
  freshness_sec?: number;
  subsystem_scores?: Record<string, number>;
  state_vector?: Record<string, number>;
  provenance_count?: number;
  signal_count?: number;
  source_event_count?: number;
  alert_count?: number;
  entity_count?: number;
  relationship_count?: number;
  timeline_count?: number;
  operator_history_count?: number;
};

export type PlanetaryCountryFusionDetailResponse = {
  contract_version: string;
  generated_at: string;
  country: string;
  fusion_snapshot?: PlanetaryCountryFusionSnapshot | null;
  country_snapshot?: PlanetaryCountrySnapshot | null;
  related_correlation_chains: PlanetaryCorrelationChain[];
  supporting_alerts: PlanetaryAlertEvent[];
  supporting_hazard_forecasts: PlanetaryHazardForecast[];
  supporting_corridors: PlanetaryCorridorSnapshot[];
  supporting_signals: PlanetaryNormalizedSignal[];
  supporting_source_events: PlanetarySourceEvent[];
  related_entities: PlanetaryWorldEntity[];
  related_relationships: PlanetaryWorldRelationship[];
  supporting_timeline: PlanetaryFusionTimelineFrame[];
  operator_history: PlanetaryOperatorEvent[];
  provenance_refs: Array<Record<string, unknown>>;
  evidence_summary: PlanetaryEvidenceSummary;
};

export type PlanetaryCorrelationChainDetailResponse = {
  contract_version: string;
  generated_at: string;
  chain_id: string;
  correlation_chain?: PlanetaryCorrelationChain | null;
  related_country_fusion?: PlanetaryCountryFusionSnapshot | null;
  supporting_alerts: PlanetaryAlertEvent[];
  supporting_signals: PlanetaryNormalizedSignal[];
  supporting_source_events: PlanetarySourceEvent[];
  supporting_hazard_forecasts: PlanetaryHazardForecast[];
  supporting_corridors: PlanetaryCorridorSnapshot[];
  related_entities: PlanetaryWorldEntity[];
  related_relationships: PlanetaryWorldRelationship[];
  supporting_timeline: PlanetaryFusionTimelineFrame[];
  operator_history: PlanetaryOperatorEvent[];
  provenance_refs: Array<Record<string, unknown>>;
  evidence_summary: PlanetaryEvidenceSummary;
};

export type PlanetaryAlertDetailResponse = {
  contract_version: string;
  generated_at: string;
  alert_id: string;
  alert?: PlanetaryAlertEvent | null;
  related_country_fusion?: PlanetaryCountryFusionSnapshot | null;
  related_correlation_chains: PlanetaryCorrelationChain[];
  supporting_signals: PlanetaryNormalizedSignal[];
  supporting_source_events: PlanetarySourceEvent[];
  supporting_hazard_forecasts: PlanetaryHazardForecast[];
  supporting_corridors: PlanetaryCorridorSnapshot[];
  related_entities: PlanetaryWorldEntity[];
  related_relationships: PlanetaryWorldRelationship[];
  supporting_timeline: PlanetaryFusionTimelineFrame[];
  operator_history: PlanetaryOperatorEvent[];
  provenance_refs: Array<Record<string, unknown>>;
  evidence_summary: PlanetaryEvidenceSummary;
};

export type PlanetaryCorridorDetailResponse = {
  contract_version: string;
  generated_at: string;
  corridor_id: string;
  corridor_snapshot?: PlanetaryCorridorSnapshot | null;
  country_scope: string[];
  related_country_snapshots: PlanetaryCountrySnapshot[];
  related_country_fusion_snapshots: PlanetaryCountryFusionSnapshot[];
  related_correlation_chains: PlanetaryCorrelationChain[];
  supporting_alerts: PlanetaryAlertEvent[];
  supporting_hazard_forecasts: PlanetaryHazardForecast[];
  supporting_corridors: PlanetaryCorridorSnapshot[];
  supporting_signals: PlanetaryNormalizedSignal[];
  supporting_source_events: PlanetarySourceEvent[];
  related_entities: PlanetaryWorldEntity[];
  related_relationships: PlanetaryWorldRelationship[];
  supporting_timeline: PlanetaryFusionTimelineFrame[];
  operator_history: PlanetaryOperatorEvent[];
  provenance_refs: Array<Record<string, unknown>>;
  evidence_summary: PlanetaryEvidenceSummary;
};

export type PlanetaryEntityProfileResponse = {
  contract_version: string;
  generated_at: string;
  query: string;
  matched_alias?: string | null;
  entity?: PlanetaryWorldEntity | null;
  country_scope: string[];
  neighborhood_entities: PlanetaryWorldEntity[];
  neighborhood_relationships: PlanetaryWorldRelationship[];
  related_alerts: PlanetaryAlertEvent[];
  related_hazard_forecasts: PlanetaryHazardForecast[];
  related_corridors: PlanetaryCorridorSnapshot[];
  related_fusion_snapshots: PlanetaryCountryFusionSnapshot[];
  related_correlation_chains: PlanetaryCorrelationChain[];
  related_timeline: PlanetaryFusionTimelineFrame[];
  operator_history: PlanetaryOperatorEvent[];
  evidence_summary: PlanetaryEvidenceSummary;
};

export type PlanetaryGraphNeighborhoodResponse = {
  contract_version: string;
  generated_at: string;
  query: string;
  matched_alias?: string | null;
  entity?: PlanetaryWorldEntity | null;
  neighborhood_entities: PlanetaryWorldEntity[];
  neighborhood_relationships: PlanetaryWorldRelationship[];
};

export type PlanetaryCalibrationReportResponse = {
  contract_version: string;
  generated_at?: string;
  notes?: string[];
  disaster_likelihood?: Record<string, unknown>;
  behavior_thresholds?: Record<string, unknown>;
  fusion_scoring?: Record<string, unknown>;
  backtests?: Record<string, number>;
};

export async function getPlanetaryCountryFusionDetail(country: string, refresh = false): Promise<PlanetaryCountryFusionDetailResponse> {
  const res = await API.get("/api/planetary-intelligence/fusion/country-detail", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      country,
      refresh,
    },
  });
  return res.data as PlanetaryCountryFusionDetailResponse;
}

export async function getPlanetaryCorrelationChainDetail(chainId: string, refresh = false): Promise<PlanetaryCorrelationChainDetailResponse> {
  const res = await API.get("/api/planetary-intelligence/fusion/correlation-detail", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      chain_id: chainId,
      refresh,
    },
  });
  return res.data as PlanetaryCorrelationChainDetailResponse;
}

export async function getPlanetaryAlertDetail(alertId: string, refresh = false): Promise<PlanetaryAlertDetailResponse> {
  const res = await API.get("/api/planetary-intelligence/alerts/detail", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      alert_id: alertId,
      refresh,
    },
  });
  return res.data as PlanetaryAlertDetailResponse;
}

export async function getPlanetaryCorridorDetail(corridorId: string, refresh = false): Promise<PlanetaryCorridorDetailResponse> {
  const res = await API.get("/api/planetary-intelligence/corridors/detail", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      corridor_id: corridorId,
      refresh,
    },
  });
  return res.data as PlanetaryCorridorDetailResponse;
}

export async function getPlanetaryEntityProfile(entityQuery: string, refresh = false, entityType?: string): Promise<PlanetaryEntityProfileResponse> {
  const res = await API.get("/api/planetary-intelligence/graph/entity-profile", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      entity_query: entityQuery,
      entity_type: entityType,
      refresh,
    },
  });
  return res.data as PlanetaryEntityProfileResponse;
}

export async function getPlanetaryGraphNeighborhood(entityQuery: string, refresh = false, entityType?: string): Promise<PlanetaryGraphNeighborhoodResponse> {
  const res = await API.get("/api/planetary-intelligence/graph/neighborhood", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      entity_query: entityQuery,
      entity_type: entityType,
      refresh,
    },
  });
  return res.data as PlanetaryGraphNeighborhoodResponse;
}

export async function getPlanetaryCalibrationReport(refresh = false): Promise<PlanetaryCalibrationReportResponse> {
  const res = await API.get("/api/planetary-intelligence/calibration/report", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      refresh,
    },
  });
  return res.data as PlanetaryCalibrationReportResponse;
}

export type PlanetaryBehaviorReplayFrame = {
  frame_id: string;
  frame_timestamp: string;
  country: string;
  signal_count: number;
  severity_score: number;
  confidence_ratio: number;
  source_families?: Record<string, number>;
  signal_types?: Record<string, number>;
};

export type PlanetaryBehaviorOperatorSurfaceResponse = {
  contract_version: string;
  generated_at: string;
  subsystem: string;
  global_behavior_snapshot: PlanetaryBehaviorGlobalSnapshot;
  country_count: number;
  top_countries: PlanetaryCountrySnapshot[];
  narrative_watch: PlanetaryNormalizedSignal[];
  replay_frames: PlanetaryBehaviorReplayFrame[];
  source_health?: {
    normalized_signal_families?: Record<string, number>;
    source_event_families?: Record<string, number>;
    signal_types?: Record<string, number>;
  };
  regional_heat?: Array<{
    country: string;
    signal_count: number;
    avg_severity: number;
    avg_confidence: number;
  }>;
};

export type PlanetaryGraphSummaryTopEntity = {
  entity_id: string;
  canonical_name?: string;
  entity_type?: string;
  confidence_ratio?: number;
  current_risk_score?: number;
  relationship_degree: number;
  top_relationship_types?: Record<string, number>;
  country_scope?: string[];
};

export type PlanetaryGraphSummaryResponse = {
  contract_version: string;
  generated_at: string;
  entity_count: number;
  relationship_count: number;
  entity_type_counts?: Record<string, number>;
  relationship_type_counts?: Record<string, number>;
  top_entities: PlanetaryGraphSummaryTopEntity[];
  country_hotspots?: Record<string, number>;
  query_spots?: PlanetaryWorldEntity[];
};

export type PlanetaryGraphSearchResult = {
  entity_id: string;
  canonical_name?: string;
  entity_type?: string;
  aliases?: string[];
  country_scope?: string[];
  confidence_ratio?: number;
  current_risk_score?: number;
  relationship_degree?: number;
};

export type PlanetaryGraphSearchResponse = {
  contract_version: string;
  generated_at: string;
  query: string;
  matched_alias?: string | null;
  resolved_entity?: PlanetaryWorldEntity | null;
  count: number;
  results: PlanetaryGraphSearchResult[];
};

export type PlanetaryDisasterCommandSurfaceResponse = {
  contract_version: string;
  generated_at: string;
  forecast_count: number;
  hazard_counts?: Record<string, number>;
  forecast_lead_hours?: Record<string, number>;
  top_regions?: Array<{
    forecast_id?: string;
    hazard_type?: string;
    country?: string;
    region?: string;
    likelihood?: number;
    severity_score?: number;
    confidence_ratio?: number;
    forecast_horizon?: number;
    recommended_action?: string;
    calibration_status?: string;
    calibration_adjustments?: Record<string, unknown>;
  }>;
  source_posture?: Array<{
    source_family?: string;
    status?: string;
    freshness_minutes?: number;
    records?: number;
    confidence_ratio?: number;
  }>;
  stream_status?: Record<string, unknown>;
  backtest_summary?: {
    overall?: Record<string, unknown>;
    hazards?: Record<string, unknown>;
  };
  hotspot_summary?: Record<string, number>;
};

export type PlanetaryCommandLayerResponse = {
  contract_version: string;
  generated_at: string;
  global_kpis?: Record<string, unknown>;
  theaters?: Array<{
    country: string;
    fusion_risk: number;
    alert_pressure: number;
    hazard_pressure: number;
    chain_pressure: number;
    alerts: number;
    hazards: number;
    chains: number;
    recommended_action?: string;
    overall_pressure: number;
  }>;
  incident_watchlist?: Array<{
    kind: string;
    id?: string;
    label?: string;
    country?: string;
    severity_score?: number;
    confidence_ratio?: number;
    recommended_action?: string;
  }>;
  replay_readiness?: Record<string, number>;
  queue_breakdown?: Array<Record<string, unknown>>;
  validation_summary?: Record<string, unknown>;
  graph_command_focus?: PlanetaryGraphSummaryTopEntity[];
  disaster_command_focus?: Array<Record<string, unknown>>;
  behavior_command_focus?: PlanetaryCountrySnapshot[];
};

export async function getPlanetaryBehaviorOperatorSurface(refresh = false): Promise<PlanetaryBehaviorOperatorSurfaceResponse> {
  const res = await API.get("/api/planetary-intelligence/behavior/operator-surface", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      country_limit: 16,
      limit: 12,
      refresh,
    },
  });
  return res.data as PlanetaryBehaviorOperatorSurfaceResponse;
}

export async function getPlanetaryBehaviorReplay(refresh = false): Promise<{ contract_version: string; generated_at: string; count: number; replay_frames: PlanetaryBehaviorReplayFrame[] }> {
  const res = await API.get("/api/planetary-intelligence/behavior/replay", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      limit: 16,
      refresh,
    },
  });
  return res.data as { contract_version: string; generated_at: string; count: number; replay_frames: PlanetaryBehaviorReplayFrame[] };
}

export async function getPlanetaryGraphSummary(refresh = false): Promise<PlanetaryGraphSummaryResponse> {
  const res = await API.get("/api/planetary-intelligence/graph/summary", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      limit: 12,
      refresh,
    },
  });
  return res.data as PlanetaryGraphSummaryResponse;
}

export async function searchPlanetaryGraph(query: string, refresh = false, entityType?: string): Promise<PlanetaryGraphSearchResponse> {
  const res = await API.get("/api/planetary-intelligence/graph/search", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      query,
      entity_type: entityType,
      limit: 12,
      refresh,
    },
  });
  return res.data as PlanetaryGraphSearchResponse;
}

export async function getPlanetaryDisasterCommand(refresh = false, runBacktests = false): Promise<PlanetaryDisasterCommandSurfaceResponse> {
  const res = await API.get("/api/planetary-intelligence/disaster/command", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      hazard_limit: 12,
      refresh,
      run_backtests: runBacktests,
    },
  });
  return res.data as PlanetaryDisasterCommandSurfaceResponse;
}

export async function getPlanetaryDisasterBacktests(run = false): Promise<Record<string, unknown>> {
  const res = await API.get("/api/planetary-intelligence/disaster/backtests", {
    headers: API_HEADERS,
    params: {
      run,
    },
  });
  return res.data as Record<string, unknown>;
}

export async function getPlanetaryCommandLayer(refresh = false, runBacktests = false): Promise<PlanetaryCommandLayerResponse> {
  const res = await API.get("/api/planetary-intelligence/command-layer", {
    headers: API_HEADERS,
    params: {
      mode: "online",
      country_limit: 18,
      hazard_limit: 10,
      replay_limit: 12,
      refresh,
      run_backtests: runBacktests,
    },
  });
  return res.data as PlanetaryCommandLayerResponse;
}

export async function getPlanetaryRuntimeStatus(refresh = false): Promise<PlanetaryRuntimeStatusResponse> {
  const res = await API.get("/api/planetary-intelligence/runtime/status", {
    headers: API_HEADERS,
    params: {
      refresh,
    },
  });
  return res.data as PlanetaryRuntimeStatusResponse;
}

export async function postPlanetaryRuntimeMaterialize(refreshSources = false, runBacktests = false): Promise<{
  ok: boolean;
  run_id?: string;
  captured_at?: string;
  runtime_manifest?: PlanetaryRuntimeManifest | null;
}> {
  const res = await API.post(
    "/api/planetary-intelligence/runtime/materialize",
    null,
    {
      headers: API_HEADERS,
      params: {
        refresh_sources: refreshSources,
        run_backtests: runBacktests,
      },
    },
  );
  return res.data as {
    ok: boolean;
    run_id?: string;
    captured_at?: string;
    runtime_manifest?: PlanetaryRuntimeManifest | null;
  };
}
