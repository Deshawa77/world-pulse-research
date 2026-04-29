import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./HazardOperations.css";
import countryNames from "../../../data/country_names.json";
import {
  buildEventStreamAuthUrl,
  getDisasterEarlyWarning,
  getDisasterHotspotAlertTransitions,
  getDisasterHotspotHistory,
  getDisasterThermalMap,
  postDisasterAlertAction,
  type DisasterAlertActionPayload,
  type DisasterEarlyWarningResponse,
  type DisasterRegionalHotspot,
  type DisasterSourceFamily,
  type DisasterSourceHealth,
  type DisasterThermalCell,
  type DisasterThermalMapResponse,
  type HotspotAlertQueueItem,
  type HotspotAlertTransition,
  type HotspotHistoryPoint,
  type HotspotRegionHistoryResponse,
  type HotspotMover,
} from "../services/api";

type HotspotHazardKey = "all" | "earthquake" | "wildfire" | "flood" | "cyclone";
type WindowKey = "6h" | "24h" | "72h" | "5d";
type MapModeKey = "thermal" | "wildfire" | "flood" | "cyclone" | "seismic";
type IntelDeckTab = "forecasts" | "sources" | "pipeline";
type OpsDeckTab = "watch" | "queue" | "quality" | "movers";
type SourceFamilyFilter = "all" | DisasterSourceFamily;
type HotspotWithHazard = DisasterRegionalHotspot & { hazard: Exclude<HotspotHazardKey, "all"> };
type QueueItemWithHazard = HotspotAlertQueueItem & { hazard: Exclude<HotspotHazardKey, "all"> };
type AlertActionKey = DisasterAlertActionPayload["action"];

const HAZARD_ACCENT: Record<Exclude<HotspotHazardKey, "all">, string> = {
  earthquake: "#38bdf8",
  wildfire: "#fb923c",
  flood: "#22c55e",
  cyclone: "#a78bfa",
};

const HOTSPOT_HAZARDS = ["earthquake", "wildfire", "flood", "cyclone"] as const;
const SOURCE_FAMILIES: DisasterSourceFamily[] = [
  "satellite_imagery",
  "seismic_data",
  "weather_sensors",
  "ocean_sensors",
  "social_media_signals",
];
const GLOBAL_MAP_WORLD_SCALE = 0.94;
const COUNTRY_LABELS = countryNames as Record<string, string>;
const DEFAULT_THERMAL_COLORSCALE: Array<[number, string]> = [
  [0.0, "#041126"],
  [0.12, "#0b2e63"],
  [0.26, "#0c7bdc"],
  [0.42, "#1fd3e1"],
  [0.58, "#8ff35a"],
  [0.74, "#ffe45c"],
  [0.88, "#ff7d2f"],
  [1.0, "#f31245"],
];
const FORECAST_WINDOWS: WindowKey[] = ["6h", "24h", "72h", "5d"];
const MAP_MODE_OPTIONS: Array<{ key: MapModeKey; label: string; detail: string }> = [
  { key: "thermal", label: "Thermal", detail: "Surface heat and weather stress" },
  { key: "wildfire", label: "Wildfire Spread", detail: "Projected perimeter growth" },
  { key: "flood", label: "Flood Depth", detail: "Water extent and rainfall load" },
  { key: "cyclone", label: "Cyclone Cone", detail: "Track and intensity outlook" },
  { key: "seismic", label: "Seismic Anomaly", detail: "Precursor corridors and clusters" },
];
const PLAYBACK_STOPS: Array<{ label: string; detail: string; factor: number; horizonHours: number }> = [
  { label: "-72h", detail: "Historical baseline", factor: 0.72, horizonHours: -72 },
  { label: "-24h", detail: "Escalation build", factor: 0.86, horizonHours: -24 },
  { label: "Live", detail: "Current fused state", factor: 1.0, horizonHours: 0 },
  { label: "+24h", detail: "Near-term forecast", factor: 1.1, horizonHours: 24 },
  { label: "+72h", detail: "Regional forecast", factor: 1.22, horizonHours: 72 },
  { label: "+5d", detail: "Extended outlook", factor: 1.34, horizonHours: 120 },
];

const SOURCE_FAMILY_LABELS: Record<DisasterSourceFamily, string> = {
  satellite_imagery: "Satellite",
  seismic_data: "Seismic",
  weather_sensors: "Weather",
  ocean_sensors: "Ocean",
  social_media_signals: "Social",
};

const OPS_STATUS_LABELS: Record<string, string> = {
  new: "New",
  acknowledged: "Acknowledged",
  snoozed: "Snoozed",
  escalated: "Escalated",
  feedback: "Feedback",
};

const COUNTRY_FOCUS_COORDS: Record<string, { lat: number; lon: number }> = {
  USA: { lat: 39.8, lon: -98.6 },
  CAN: { lat: 56.1, lon: -106.3 },
  MEX: { lat: 23.6, lon: -102.6 },
  BRA: { lat: -14.2, lon: -51.9 },
  ARG: { lat: -38.4, lon: -63.6 },
  GBR: { lat: 55.4, lon: -3.4 },
  FRA: { lat: 46.2, lon: 2.2 },
  DEU: { lat: 51.2, lon: 10.4 },
  ESP: { lat: 40.4, lon: -3.7 },
  ITA: { lat: 42.8, lon: 12.5 },
  RUS: { lat: 61.5, lon: 105.3 },
  CHN: { lat: 35.9, lon: 104.2 },
  IND: { lat: 20.6, lon: 78.9 },
  JPN: { lat: 36.2, lon: 138.3 },
  KOR: { lat: 36.5, lon: 127.9 },
  AUS: { lat: -25.3, lon: 133.8 },
  ZAF: { lat: -30.6, lon: 22.9 },
  EGY: { lat: 26.8, lon: 30.8 },
  NGA: { lat: 9.1, lon: 8.7 },
  TUR: { lat: 38.9, lon: 35.2 },
  SAU: { lat: 23.9, lon: 45.1 },
  IDN: { lat: -0.8, lon: 113.9 },
  PAK: { lat: 30.4, lon: 69.3 },
  UKR: { lat: 48.4, lon: 31.2 },
  LKA: { lat: 7.9, lon: 80.7 },
  DZA: { lat: 28.0, lon: 1.7 },
  IRN: { lat: 32.4, lon: 53.7 },
  BGD: { lat: 23.7, lon: 90.4 },
  NPL: { lat: 28.4, lon: 84.1 },
  MMR: { lat: 21.2, lon: 96.0 },
  THA: { lat: 15.9, lon: 100.9 },
  VNM: { lat: 14.1, lon: 108.3 },
  MYS: { lat: 4.2, lon: 102.0 },
  PHL: { lat: 12.9, lon: 121.8 },
  NZL: { lat: -41.5, lon: 172.8 },
  NOR: { lat: 60.5, lon: 8.5 },
  SWE: { lat: 60.1, lon: 18.6 },
  FIN: { lat: 64.5, lon: 26.0 },
  POL: { lat: 52.1, lon: 19.4 },
  NLD: { lat: 52.1, lon: 5.3 },
  BEL: { lat: 50.8, lon: 4.5 },
  CHE: { lat: 46.8, lon: 8.2 },
  AUT: { lat: 47.6, lon: 14.1 },
  ISR: { lat: 31.0, lon: 34.8 },
  QAT: { lat: 25.3, lon: 51.2 },
  ARE: { lat: 24.3, lon: 54.4 },
  KWT: { lat: 29.3, lon: 47.5 },
  KEN: { lat: 0.0, lon: 37.9 },
  ETH: { lat: 9.1, lon: 40.5 },
  GHA: { lat: 7.9, lon: -1.0 },
  MAR: { lat: 31.8, lon: -7.1 },
  TUN: { lat: 34.0, lon: 9.6 },
};

function hotspotLabel(hotspot: DisasterRegionalHotspot): string {
  return hotspot.region_name ?? hotspot.display_label ?? hotspot.region_label ?? hotspot.region;
}

function hotspotSecondaryLabel(hotspot: DisasterRegionalHotspot): string {
  return hotspot.region_label ?? hotspot.region;
}

function hotspotLayerTitle(hazard: Exclude<HotspotHazardKey, "all">): string {
  if (hazard === "wildfire") return "Wildfire Theater";
  if (hazard === "flood") return "Flood Theater";
  if (hazard === "cyclone") return "Cyclone Theater";
  return "Seismic Theater";
}

function hazardLabel(hazard: HotspotHazardKey): string {
  return hazard === "all" ? "All Hazards" : hazard[0].toUpperCase() + hazard.slice(1);
}

function leadRegionLabel(summary: DisasterEarlyWarningResponse["summary"] | undefined, hazard: HotspotHazardKey): string {
  if (!summary) return "--";
  if (hazard === "wildfire") return summary.top_wildfire_region_name ?? "--";
  if (hazard === "flood") return summary.top_flood_region_name ?? "--";
  if (hazard === "cyclone") return summary.top_cyclone_region_name ?? "--";
  if (hazard === "earthquake") return summary.top_seismic_region_name ?? "--";
  if (summary.top_hazard === "wildfire") return summary.top_wildfire_region_name ?? "--";
  if (summary.top_hazard === "flood") return summary.top_flood_region_name ?? "--";
  if (summary.top_hazard === "cyclone") return summary.top_cyclone_region_name ?? "--";
  return summary.top_seismic_region_name ?? "--";
}

function sourceFamilyLabel(source: string): string {
  const key = String(source || "").trim() as DisasterSourceFamily;
  if (key in SOURCE_FAMILY_LABELS) return SOURCE_FAMILY_LABELS[key];
  return String(source || "").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function countryLabel(country: string | undefined | null): string {
  const code = String(country || "").trim().toUpperCase();
  return COUNTRY_LABELS[code] ?? (code || "Unknown");
}

function resolveCountryFocus(
  country: string,
  clickLat?: number | null,
  clickLon?: number | null,
  fallbackLat?: number | null,
  fallbackLon?: number | null,
): { lat: number; lon: number } | null {
  if (Number.isFinite(clickLat) && Number.isFinite(clickLon)) {
    return { lat: Number(clickLat), lon: Number(clickLon) };
  }
  if (Number.isFinite(fallbackLat) && Number.isFinite(fallbackLon)) {
    return { lat: Number(fallbackLat), lon: Number(fallbackLon) };
  }
  return COUNTRY_FOCUS_COORDS[country] ?? null;
}

function formatOpsStatus(status: string | undefined): string {
  const key = String(status || "new").toLowerCase();
  return OPS_STATUS_LABELS[key] ?? sourceFamilyLabel(key);
}

function formatTimestamp(value: string | undefined | null): string {
  if (!value) return "Pending";
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) return value;
  return stamp.toLocaleString();
}

function formatFreshness(minutes: number | null | undefined): string {
  if (!Number.isFinite(Number(minutes))) return "No heartbeat";
  const value = Number(minutes);
  if (value < 60) return `${Math.round(value)}m fresh`;
  if (value < 1440) return `${Math.round(value / 60)}h fresh`;
  return `${Math.round(value / 1440)}d old`;
}

function formatTemperature(value: number | null | undefined): string {
  if (!Number.isFinite(Number(value))) return "--";
  return `${Number(value).toFixed(1)}C`;
}

function formatThermalPercent(value: number | null | undefined): string {
  if (!Number.isFinite(Number(value))) return "--";
  return `${Math.round(Number(value) * 100)}%`;
}

function formatPercent(value: number | null | undefined, digits = 0): string {
  if (!Number.isFinite(Number(value))) return "--";
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function windowHours(window: WindowKey): number {
  if (window === "6h") return 6;
  if (window === "24h") return 24;
  if (window === "72h") return 72;
  return 120;
}

function sourceConfidenceScore(source: DisasterSourceHealth): number {
  const freshness = Number.isFinite(Number(source.freshness_minutes)) ? Number(source.freshness_minutes) : 720;
  const freshnessScore = clamp01(1 - (freshness / 720));
  const volumeScore = clamp01(Math.log10((Number(source.records) || 0) + 1) / 3);
  const statusBase = source.status === "up" ? 0.9 : source.status === "degraded" ? 0.62 : source.status === "stale" ? 0.46 : 0.22;
  const authPenalty = source.auth_failed ? 0.18 : 0;
  const ratePenalty = source.rate_limited ? 0.08 : 0;
  return clamp01((statusBase * 0.55) + (freshnessScore * 0.25) + (volumeScore * 0.2) - authPenalty - ratePenalty);
}

function sourceOutageLabel(source: DisasterSourceHealth): string {
  if (source.auth_failed) return "Auth blocked";
  if (source.rate_limited) return "Rate limited";
  if (source.status === "down") return "Outage";
  if (source.status === "stale") return "Stale feed";
  if (source.status === "degraded") return "Degraded";
  return "Nominal";
}

function mapModeLabel(mode: MapModeKey): string {
  return MAP_MODE_OPTIONS.find((item) => item.key === mode)?.label ?? mode;
}

function mapModeHazard(mode: MapModeKey): Exclude<HotspotHazardKey, "all"> | null {
  if (mode === "seismic") return "earthquake";
  if (mode === "thermal") return null;
  return mode;
}

function hazardToMapMode(hazard: HotspotHazardKey): MapModeKey {
  if (hazard === "all") return "thermal";
  if (hazard === "earthquake") return "seismic";
  return hazard;
}

function buildGeoRing(lat: number, lon: number, radius: number, points: number = 28): Array<{ lat: number; lon: number }> {
  const rows: Array<{ lat: number; lon: number }> = [];
  const cosLat = Math.max(Math.cos((lat * Math.PI) / 180), 0.3);
  for (let index = 0; index <= points; index += 1) {
    const theta = (Math.PI * 2 * index) / points;
    rows.push({
      lat: lat + (Math.sin(theta) * radius),
      lon: lon + ((Math.cos(theta) * radius) / cosLat),
    });
  }
  return rows;
}

function hotspotSeriesForWindow(hotspot: DisasterRegionalHotspot, window: WindowKey): HotspotHistoryPoint[] {
  const directKey = window === "5d" ? "72h" : window;
  const direct = hotspot.history?.[directKey];
  const baseSeries = Array.isArray(direct) && direct.length
    ? direct
    : (hotspot.trend_points ?? []).map((value, index) => ({
        timestamp: String(index),
        activity: Number(value) || 0,
        band: hotspot.hotspot_band,
      }));

  if (window !== "5d" || baseSeries.length < 2) return baseSeries;

  const last = Number(baseSeries[baseSeries.length - 1]?.activity || 0);
  const prior = Number(baseSeries[baseSeries.length - 2]?.activity || last);
  const drift = last - prior;
  const futureOne = clamp01(last + (drift * 1.4));
  const futureTwo = clamp01(futureOne + (drift * 1.1));
  return [
    ...baseSeries,
    { timestamp: "forecast-96h", activity: futureOne, band: hotspot.hotspot_band },
    { timestamp: "forecast-120h", activity: futureTwo, band: hotspot.hotspot_band },
  ];
}

function sparklinePath(points: HotspotHistoryPoint[] | undefined): string {
  const values = Array.isArray(points) && points.length ? points.map((point) => Number(point.activity) || 0) : [0.2, 0.24, 0.28, 0.31, 0.36, 0.42];
  const width = 160;
  const height = 44;
  const step = values.length > 1 ? width / (values.length - 1) : width;
  return values.map((value, index) => {
    const x = Number((index * step).toFixed(2));
    const y = Number((height - Math.max(0, Math.min(1, value)) * (height - 8) - 4).toFixed(2));
    return `${index === 0 ? "M" : "L"}${x},${y}`;
  }).join(" ");
}

function deltaValue(points: HotspotHistoryPoint[] | undefined): number {
  if (!Array.isArray(points) || points.length < 2) return 0;
  return Number((Number(points[points.length - 1]?.activity || 0) - Number(points[0]?.activity || 0)).toFixed(3));
}

function deltaLabel(delta: number): string {
  if (delta > 0.08) return `+${Math.round(delta * 100)} pts`;
  if (delta < -0.08) return `${Math.round(delta * 100)} pts`;
  return "Flat";
}

function metricPrimary(hotspot: DisasterRegionalHotspot): string {
  if (hotspot.event_type === "wildfire") return `Detections ${hotspot.hotspot_stats?.detection_count ?? hotspot.hotspot_stats?.event_count ?? 0}`;
  if (hotspot.event_type === "flood") return `Flood Hits ${hotspot.hotspot_stats?.flood_detection_count ?? hotspot.hotspot_stats?.event_count ?? 0}`;
  if (hotspot.event_type === "cyclone") return `Storm Hits ${hotspot.hotspot_stats?.storm_detection_count ?? hotspot.hotspot_stats?.event_count ?? 0}`;
  return `Quakes ${hotspot.hotspot_stats?.quake_count ?? hotspot.hotspot_stats?.event_count ?? 0}`;
}

function metricSecondary(hotspot: DisasterRegionalHotspot): string {
  if (hotspot.event_type === "wildfire") return `Max C ${(hotspot.hotspot_stats?.max_temperature ?? hotspot.hotspot_stats?.intensity_peak ?? 0).toFixed(1)}`;
  if (hotspot.event_type === "flood") return `Rain ${(hotspot.hotspot_stats?.max_rainfall ?? hotspot.hotspot_stats?.intensity_peak ?? 0).toFixed(0)}mm`;
  if (hotspot.event_type === "cyclone") return `Wind ${(hotspot.hotspot_stats?.max_wind_speed ?? hotspot.hotspot_stats?.intensity_peak ?? 0).toFixed(0)}km/h`;
  return `Max M ${(hotspot.hotspot_stats?.max_magnitude ?? hotspot.hotspot_stats?.intensity_peak ?? 0).toFixed(1)}`;
}

function priorityBandTone(value: string | undefined): string {
  const band = String(value || "monitor").toLowerCase();
  if (band === "critical") return "critical";
  if (band === "active") return "active";
  if (band === "monitor") return "monitor";
  return "guarded";
}

function hotspotMatchesSourceFamily(hotspot: DisasterRegionalHotspot | null | undefined, sourceFamily: SourceFamilyFilter): boolean {
  if (sourceFamily === "all") return true;
  return Array.isArray(hotspot?.signal_sources) && hotspot.signal_sources.includes(sourceFamily);
}

function queueMatchesSourceFamily(item: HotspotAlertQueueItem | null | undefined, sourceFamily: SourceFamilyFilter): boolean {
  if (sourceFamily === "all") return true;
  return Array.isArray(item?.signal_sources) && item.signal_sources.includes(sourceFamily);
}

function thermalCellMatchesSourceFamily(cell: DisasterThermalCell | null | undefined, sourceFamily: SourceFamilyFilter): boolean {
  if (sourceFamily === "all") return true;
  return Array.isArray(cell?.signal_sources) && cell.signal_sources.includes(sourceFamily);
}

function flattenHotspots(forecast: DisasterEarlyWarningResponse | null): HotspotWithHazard[] {
  if (!forecast?.regional_hotspots) return [];
  const entries: HotspotWithHazard[] = [];
  for (const hazard of HOTSPOT_HAZARDS) {
    for (const item of forecast.regional_hotspots[hazard] ?? []) entries.push({ ...item, hazard });
  }
  return entries;
}

function flattenQueue(queue: DisasterEarlyWarningResponse["alert_queue"]): QueueItemWithHazard[] {
  const items: QueueItemWithHazard[] = [];
  for (const hazard of HOTSPOT_HAZARDS) {
    for (const item of queue?.[hazard] ?? []) items.push({ ...item, hazard });
  }
  return items.sort((a, b) => (Number(b.adjusted_activity ?? b.activity) || 0) - (Number(a.adjusted_activity ?? a.activity) || 0));
}

function flattenMovers(trend: DisasterEarlyWarningResponse["trend_comparison"], key: "accelerating_fastest" | "cooling_fastest", hazard: HotspotHazardKey): Array<HotspotMover & { hazard: Exclude<HotspotHazardKey, "all"> }> {
  const items: Array<HotspotMover & { hazard: Exclude<HotspotHazardKey, "all"> }> = [];
  const hazards = hazard === "all" ? HOTSPOT_HAZARDS : ([hazard] as Array<Exclude<HotspotHazardKey, "all">>);
  for (const hazardKey of hazards) {
    for (const item of trend?.[hazardKey]?.[key] ?? []) items.push({ ...item, hazard: hazardKey });
  }
  return items.sort((a, b) => key === "cooling_fastest" ? a.delta - b.delta : b.delta - a.delta).slice(0, 6);
}

function getSourceHealthEntries(forecast: DisasterEarlyWarningResponse | null): DisasterSourceHealth[] {
  if (forecast?.source_health?.length) return forecast.source_health;
  return SOURCE_FAMILIES.map((source_family) => ({
    source_family,
    status: "unknown",
    records: 0,
    last_success: null,
    freshness_minutes: null,
    component_sources: [],
    advisory: "Awaiting source heartbeat",
    errors: [],
  }));
}

function buildActionPayload(item: QueueItemWithHazard | null, hotspot: HotspotWithHazard | null): Omit<DisasterAlertActionPayload, "action"> | null {
  if (item) return { hazard: item.hazard, region: item.region, country: "GLB", alert_id: item.alert_id, dedupe_key: item.dedupe_key };
  if (hotspot) return { hazard: hotspot.hazard, region: hotspot.region, country: "GLB" };
  return null;
}

function calibrationTone(value: string | undefined): "stable" | "guarded" | "critical" {
  const status = String(value || "").toLowerCase();
  if (status.includes("well") || status.includes("correlated")) return "stable";
  if (status.includes("guard") || status.includes("pending")) return "guarded";
  return "critical";
}

export default function HazardOperations() {
  const navigate = useNavigate();
  const mainRef = useRef<HTMLElement | null>(null);
  const mapRef = useRef<HTMLDivElement | null>(null);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);
  const [forecast, setForecast] = useState<DisasterEarlyWarningResponse | null>(null);
  const [selectedHazard, setSelectedHazard] = useState<HotspotHazardKey>("all");
  const [selectedWindow, setSelectedWindow] = useState<WindowKey>("24h");
  const [selectedSourceFamily, setSelectedSourceFamily] = useState<SourceFamilyFilter>("all");
  const [selectedHotspot, setSelectedHotspot] = useState<HotspotWithHazard | null>(null);
  const [selectedHistory, setSelectedHistory] = useState<HotspotRegionHistoryResponse | null>(null);
  const [transitions, setTransitions] = useState<HotspotAlertTransition[]>([]);
  const [actionBusyKey, setActionBusyKey] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string>("");
  const [thermalMap, setThermalMap] = useState<DisasterThermalMapResponse | null>(null);
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  const [selectedCountryFocus, setSelectedCountryFocus] = useState<{ lat: number; lon: number } | null>(null);
  const [selectedThermalCell, setSelectedThermalCell] = useState<DisasterThermalCell | null>(null);
  const [selectedMapMode, setSelectedMapMode] = useState<MapModeKey>("thermal");
  const [playbackIndex, setPlaybackIndex] = useState<number>(2);
  const [selectedIntelTab, setSelectedIntelTab] = useState<IntelDeckTab>("forecasts");
  const [selectedOpsTab, setSelectedOpsTab] = useState<OpsDeckTab>("queue");

  const refreshForecast = async () => {
    const payload = await getDisasterEarlyWarning();
    setForecast(payload);
  };

  useEffect(() => {
    let canceled = false;
    let fallbackTimer: number | null = null;
    const load = async () => {
      try {
        const payload = await getDisasterEarlyWarning();
        if (!canceled) setForecast(payload);
      } catch {
        if (!canceled) setForecast(null);
      }
    };

    const ensureFallback = () => {
      if (fallbackTimer !== null) return;
      fallbackTimer = window.setInterval(() => void load(), 90000);
    };

    void load();
    const streamUrl = buildEventStreamAuthUrl("/api/disasters/alerts/stream?mode=live&poll_seconds=12");
    const stream = new EventSource(streamUrl);
    const onAlerts = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as DisasterEarlyWarningResponse;
        if (!canceled) setForecast(payload);
      } catch {
        ensureFallback();
      }
    };

    stream.addEventListener("disaster_alerts", onAlerts as EventListener);
    stream.onerror = () => {
      ensureFallback();
    };

    return () => {
      canceled = true;
      stream.removeEventListener("disaster_alerts", onAlerts as EventListener);
      stream.close();
      if (fallbackTimer !== null) window.clearInterval(fallbackTimer);
    };
  }, []);

  useEffect(() => {
    let canceled = false;
    void getDisasterHotspotAlertTransitions(72, 24, selectedHazard === "all" ? undefined : selectedHazard)
      .then((payload) => {
        if (!canceled) setTransitions(Array.isArray(payload.items) ? payload.items : []);
      })
      .catch(() => {
        if (!canceled) setTransitions([]);
      });
    return () => {
      canceled = true;
    };
  }, [selectedHazard]);

  useEffect(() => {
    if (!selectedHotspot) {
      setSelectedHistory(null);
      return;
    }
    let canceled = false;
    void getDisasterHotspotHistory(selectedHotspot.region, 72, selectedHotspot.hazard)
      .then((payload) => {
        if (!canceled) setSelectedHistory(payload);
      })
      .catch(() => {
        if (!canceled) setSelectedHistory(null);
      });
    return () => {
      canceled = true;
    };
  }, [selectedHotspot]);

  useEffect(() => {
    let canceled = false;
    void getDisasterThermalMap(
      selectedCountry ?? undefined,
      selectedHazard === "all" ? undefined : selectedHazard,
      selectedCountryFocus?.lat,
      selectedCountryFocus?.lon,
    )
      .then((payload) => {
        if (!canceled) setThermalMap(payload);
      })
      .catch(() => {
        if (!canceled) setThermalMap(null);
      });
    return () => {
      canceled = true;
    };
  }, [forecast?.generated_at, selectedCountry, selectedHazard, selectedCountryFocus?.lat, selectedCountryFocus?.lon]);

  useEffect(() => {
    if (selectedHazard === "all") return;
    setSelectedMapMode(hazardToMapMode(selectedHazard));
  }, [selectedHazard]);

  const allHotspots = useMemo(() => flattenHotspots(forecast), [forecast]);
  const hotspotLookup = useMemo(() => {
    const lookup = new Map<string, HotspotWithHazard>();
    for (const hotspot of allHotspots) lookup.set(`${hotspot.hazard}:${hotspot.region}`, hotspot);
    return lookup;
  }, [allHotspots]);
  const sourceHealthEntries = useMemo(() => getSourceHealthEntries(forecast), [forecast]);
  const activeSourceFamilies = useMemo(() => {
    const families = forecast?.source_families?.length ? forecast.source_families : SOURCE_FAMILIES;
    return SOURCE_FAMILIES.filter((family) => families.includes(family));
  }, [forecast]);
  const thermalCountries = useMemo(() => thermalMap?.countries ?? [], [thermalMap]);
  const thermalCountryLookup = useMemo(() => {
    const lookup = new Map<string, DisasterThermalMapResponse["countries"][number]>();
    for (const row of thermalCountries) lookup.set(row.country, row);
    return lookup;
  }, [thermalCountries]);
  const thermalCells = useMemo(() => {
    return (thermalMap?.cells ?? [])
      .filter((cell) => thermalCellMatchesSourceFamily(cell, selectedSourceFamily))
      .sort((a, b) => Number(b.thermal_index || 0) - Number(a.thermal_index || 0));
  }, [selectedSourceFamily, thermalMap]);
  const selectedCountrySummary = useMemo(() => {
    if (!selectedCountry) return null;
    return thermalCountries.find((row) => row.country === selectedCountry) ?? null;
  }, [selectedCountry, thermalCountries]);
  const countrySectorCells = useMemo(() => {
    if (!selectedCountry) return [];
    return thermalCells
      .filter((cell) => cell.country === selectedCountry)
      .sort((a, b) => Number(b.temperature_c || 0) - Number(a.temperature_c || 0))
      .slice(0, 24);
  }, [selectedCountry, thermalCells]);
  const activeThermalPool = selectedCountry ? countrySectorCells : thermalCells;
  const activeThermalCell = useMemo(() => {
    if (!activeThermalPool.length) return null;
    if (!selectedThermalCell) return activeThermalPool[0];
    return activeThermalPool.find((cell) => cell.cell_id === selectedThermalCell.cell_id) ?? activeThermalPool[0];
  }, [activeThermalPool, selectedThermalCell]);
  const thermalFocus = thermalMap?.focus;
  const playbackStop = PLAYBACK_STOPS[Math.min(playbackIndex, PLAYBACK_STOPS.length - 1)] ?? PLAYBACK_STOPS[2];
  const mapModeHazardKey = mapModeHazard(selectedMapMode);

  const visibleHotspots = useMemo(() => {
    return allHotspots
      .filter((item) => selectedHazard === "all" || item.hazard === selectedHazard)
      .filter((item) => hotspotMatchesSourceFamily(item, selectedSourceFamily))
      .slice(0, selectedHazard === "all" ? 12 : 8);
  }, [allHotspots, selectedHazard, selectedSourceFamily]);

  const hotspotQueue = useMemo(() => {
    return flattenQueue(forecast?.alert_queue)
      .filter((item) => selectedHazard === "all" || item.hazard === selectedHazard)
      .filter((item) => queueMatchesSourceFamily(item, selectedSourceFamily));
  }, [forecast, selectedHazard, selectedSourceFamily]);

  const visibleForecasts = useMemo(() => {
    return (forecast?.forecasts ?? []).filter((item) => {
      const hazardMatch = selectedHazard === "all" || item.event_type === selectedHazard;
      const sourceMatch = selectedSourceFamily === "all" || (item.signal_sources ?? []).includes(selectedSourceFamily);
      return hazardMatch && sourceMatch;
    });
  }, [forecast, selectedHazard, selectedSourceFamily]);

  const forecastByHazard = useMemo(() => {
    const lookup = new Map<Exclude<HotspotHazardKey, "all">, DisasterEarlyWarningResponse["forecasts"][number] | null>();
    for (const hazard of HOTSPOT_HAZARDS) {
      const matches = (forecast?.forecasts ?? [])
        .filter((item) => item.event_type === hazard)
        .sort((left, right) => ((Number(right.likelihood) || 0) * 0.6 + (Number(right.severity_score) || 0) * 0.4) - ((Number(left.likelihood) || 0) * 0.6 + (Number(left.severity_score) || 0) * 0.4));
      lookup.set(hazard, matches[0] ?? null);
    }
    return lookup;
  }, [forecast]);

  const hotspotByHazard = useMemo(() => {
    const lookup = new Map<Exclude<HotspotHazardKey, "all">, HotspotWithHazard | null>();
    for (const hazard of HOTSPOT_HAZARDS) {
      const matches = allHotspots
        .filter((item) => item.hazard === hazard)
        .sort((left, right) => (Number(right.hotspot_score ?? right.activity_score ?? 0) - Number(left.hotspot_score ?? left.activity_score ?? 0)));
      lookup.set(hazard, matches[0] ?? null);
    }
    return lookup;
  }, [allHotspots]);

  const sourceIntelCards = useMemo(() => {
    return sourceHealthEntries.map((source) => ({
      ...source,
      confidence_score: sourceConfidenceScore(source),
      outage_label: sourceOutageLabel(source),
      throughput_label: source.records >= 1000
        ? `${(source.records / 1000).toFixed(1)}k rows`
        : `${source.records} rows`,
    }));
  }, [sourceHealthEntries]);

  const hazardForecastCards = useMemo(() => {
    return HOTSPOT_HAZARDS.map((hazard) => {
      const forecastPacket = forecastByHazard.get(hazard);
      const hotspot = hotspotByHazard.get(hazard);
      const baseLikelihood = clamp01(Number(forecastPacket?.likelihood ?? hotspot?.likelihood ?? hotspot?.hotspot_score ?? hotspot?.activity_score ?? 0.18));
      const baseSeverity = clamp01(Number(forecastPacket?.severity_score ?? hotspot?.severity_score ?? hotspot?.hotspot_score ?? 0.24));
      const baseConfidence = clamp01(Number(forecastPacket?.confidence ?? hotspot?.confidence ?? hotspot?.hotspot_confidence ?? 0.48));
      const horizonMultipliers: Record<WindowKey, { likelihood: number; severity: number; confidence: number }> = hazard === "wildfire"
        ? { "6h": { likelihood: 0.94, severity: 0.9, confidence: 1.0 }, "24h": { likelihood: 1.0, severity: 1.0, confidence: 0.98 }, "72h": { likelihood: 1.14, severity: 1.16, confidence: 0.94 }, "5d": { likelihood: 1.26, severity: 1.3, confidence: 0.9 } }
        : hazard === "flood"
          ? { "6h": { likelihood: 0.9, severity: 0.88, confidence: 1.0 }, "24h": { likelihood: 1.0, severity: 1.0, confidence: 0.98 }, "72h": { likelihood: 1.18, severity: 1.2, confidence: 0.92 }, "5d": { likelihood: 1.3, severity: 1.26, confidence: 0.88 } }
          : hazard === "cyclone"
            ? { "6h": { likelihood: 0.96, severity: 0.94, confidence: 1.0 }, "24h": { likelihood: 1.02, severity: 1.04, confidence: 0.98 }, "72h": { likelihood: 1.18, severity: 1.22, confidence: 0.94 }, "5d": { likelihood: 1.34, severity: 1.36, confidence: 0.9 } }
            : { "6h": { likelihood: 0.98, severity: 0.92, confidence: 1.0 }, "24h": { likelihood: 1.0, severity: 1.0, confidence: 0.98 }, "72h": { likelihood: 1.06, severity: 1.08, confidence: 0.94 }, "5d": { likelihood: 1.1, severity: 1.12, confidence: 0.9 } };
      const windows = FORECAST_WINDOWS.map((windowKey) => ({
        window: windowKey,
        likelihood: clamp01(baseLikelihood * horizonMultipliers[windowKey].likelihood),
        severity: clamp01(baseSeverity * horizonMultipliers[windowKey].severity),
        confidence: clamp01(baseConfidence * horizonMultipliers[windowKey].confidence),
      }));
      const stats = hotspot?.hotspot_stats ?? {};
      const metrics = hazard === "wildfire"
        ? [
            { label: "Projected Perimeter", value: `${Math.round((Number(hotspot?.hotspot_score ?? baseLikelihood) * 420) * playbackStop.factor)} km2` },
            { label: "Heat Peak", value: `${Number(stats.max_temperature ?? forecastPacket?.feature_values?.surface_temperature ?? 0).toFixed(1)} C` },
            { label: "Wind Assist", value: `${Math.round(Number(stats.max_wind_speed ?? forecastPacket?.feature_values?.wind_speed ?? 18))} km/h` },
          ]
        : hazard === "flood"
          ? [
              { label: "Rain Load", value: `${Math.round(Number(stats.max_rainfall ?? forecastPacket?.feature_values?.rainfall_accumulation ?? 86))} mm` },
              { label: "Depth Proxy", value: `${Math.round(baseSeverity * 3.8 * playbackStop.factor * 10) / 10} m` },
              { label: "Water Extent", value: `${Math.round(baseLikelihood * 240 * playbackStop.factor)} km2` },
            ]
          : hazard === "cyclone"
            ? [
                { label: "Track Span", value: `${Math.round((windowHours(selectedWindow) + 180) * 1.7)} km` },
                { label: "Wind Core", value: `${Math.round(Number(stats.max_wind_speed ?? forecastPacket?.feature_values?.max_wind_speed ?? 92) * playbackStop.factor)} km/h` },
                { label: "Pressure Drop", value: `${Math.round(1008 - (baseSeverity * 62))} hPa` },
              ]
            : [
                { label: "Anomaly Likelihood", value: formatPercent(baseLikelihood) },
                { label: "Swarm Cluster", value: `${Math.round(Number(stats.quake_count ?? forecastPacket?.feature_values?.swarm_frequency ?? 18))} signals` },
                { label: "Peak Magnitude Proxy", value: `M ${Number(stats.max_magnitude ?? forecastPacket?.feature_values?.magnitude_proxy ?? 5.6).toFixed(1)}` },
              ];
      const title = hazard === "earthquake" ? "Earthquake Anomaly Likelihood" : hazard === "wildfire" ? "Wildfire Spread Prediction" : hazard === "flood" ? "Flood Forecast" : "Cyclone Trajectory + Intensity";
      const summary = hazard === "earthquake"
        ? "Precursor likelihood, corridor clustering, and anomaly confidence. This remains anomaly scoring, not deterministic prediction."
        : hazard === "wildfire"
          ? "Projected perimeter growth from heat signatures, wind stress, and corroborating narrative shifts."
          : hazard === "flood"
            ? "Rainfall accumulation, flood depth proxy, and district water-extent outlook."
            : "Cone-of-risk trajectory built from ocean heat, pressure, and storm motion continuity.";
      return {
        hazard,
        title,
        summary,
        forecastPacket,
        hotspot,
        windows,
        metrics,
        signals: (forecastPacket?.top_contributing_signals?.length ? forecastPacket.top_contributing_signals : hotspot?.top_contributing_signals ?? []).slice(0, 4),
        recommendedAction: forecastPacket?.recommended_action ?? `Escalate ${hazardLabel(hazard)} watch if corroboration holds through the next fused cycle.`,
        modelLabel: forecastPacket?.model_type ?? (hazard === "earthquake" ? "Seismic anomaly scorer" : hazard === "cyclone" ? "Ocean-track fusion model" : "Fusion forecast model"),
      };
    });
  }, [allHotspots, forecast, forecastByHazard, hotspotByHazard, playbackStop.factor, selectedWindow]);

  const pipelineStages = useMemo(() => {
    const totalRows = sourceHealthEntries.reduce((sum, source) => sum + (Number(source.records) || 0), 0);
    const avgConfidence = sourceIntelCards.length
      ? sourceIntelCards.reduce((sum, source) => sum + source.confidence_score, 0) / sourceIntelCards.length
      : 0;
    return [
      { key: "ingestion", label: "Satellite / Seismic / Weather / Ocean / Social Ingestion", detail: `${sourceIntelCards.filter((source) => source.status === "up").length}/${sourceIntelCards.length} live families online`, metric: `${totalRows} rows`, progress: avgConfidence },
      { key: "processing", label: "CV + Time-Series Detection", detail: "Computer vision, anomaly scoring, and sensor normalization", metric: `${forecast?.forecasts?.length ?? 0} forecast packets`, progress: clamp01((forecast?.forecasts?.length ?? 0) / 12) },
      { key: "fusion", label: "Stream Fusion", detail: "Cross-source corroboration with district-level aggregation", metric: `${activeSourceFamilies.length} fused families`, progress: clamp01(activeSourceFamilies.length / SOURCE_FAMILIES.length) },
      { key: "risk", label: "Risk Scoring", detail: "Lead-time calibrated hazard scoring and explainability", metric: `${forecast?.summary?.critical_or_high_count ?? 0} high / critical`, progress: clamp01((forecast?.summary?.critical_or_high_count ?? 0) / 12) },
      { key: "alert", label: "Alert Systems", detail: "Dedupe, operator actions, escalation, and streaming alerts", metric: `${forecast?.alert_ops_summary?.active_queue_count ?? hotspotQueue.length} active`, progress: clamp01((forecast?.alert_ops_summary?.active_queue_count ?? hotspotQueue.length) / 12) },
    ];
  }, [activeSourceFamilies.length, forecast, hotspotQueue.length, sourceHealthEntries, sourceIntelCards]);

  const alertLadder = useMemo(() => {
    const allBands = [
      ...allHotspots.map((item) => String(item.hotspot_band || "monitor").toLowerCase()),
      ...hotspotQueue.map((item) => String(item.priority_band || "monitor").toLowerCase()),
    ];
    const monitor = allBands.filter((band) => band === "monitor" || band === "guarded").length;
    const active = allBands.filter((band) => band === "active").length;
    const critical = allBands.filter((band) => band === "critical").length;
    const watch = Math.max(Number(forecast?.summary?.watch_count ?? 0), hotspotQueue.length);
    const selectedOpsBand = selectedHotspot
      ? hotspotQueue.find((item) => item.region === selectedHotspot.region && item.hazard === selectedHotspot.hazard)?.priority_band
      : null;
    const currentBand = String(selectedOpsBand ?? selectedHotspot?.hotspot_band ?? "monitor").toLowerCase();
    return [
      { key: "monitor", label: "Monitor", count: monitor, active: currentBand === "monitor" || currentBand === "guarded" },
      { key: "watch", label: "Watch", count: watch, active: currentBand === "watch" },
      { key: "active", label: "Active", count: active, active: currentBand === "active" },
      { key: "critical", label: "Critical", count: critical, active: currentBand === "critical" },
    ];
  }, [allHotspots, forecast?.summary?.watch_count, hotspotQueue, selectedHotspot?.hotspot_band]);

  const selectedHazardForecast = useMemo(() => {
    const hazard = selectedHotspot?.hazard ?? (selectedHazard === "all" ? mapModeHazardKey ?? "wildfire" : selectedHazard);
    return forecastByHazard.get(hazard as Exclude<HotspotHazardKey, "all">) ?? null;
  }, [forecastByHazard, mapModeHazardKey, selectedHazard, selectedHotspot?.hazard]);

  const explainabilityPanels = useMemo(() => {
    const sourcePool = new Set<string>([
      ...(activeThermalCell?.signal_sources ?? []),
      ...(selectedHazardForecast?.signal_sources ?? []),
      ...(selectedHotspot?.signal_sources ?? []),
    ]);
    const signalPool = [
      ...(selectedHazardForecast?.top_contributing_signals ?? []),
      ...(selectedHotspot?.top_contributing_signals ?? []),
    ].slice(0, 6);
    return [
      { title: "Satellite heat signatures rising", body: sourcePool.has("satellite_imagery") ? "Computer vision detections and thermal cells are reinforcing the current hazard picture." : "Satellite evidence is not dominant in this region yet." },
      { title: "Wind + humidity favor spread", body: sourcePool.has("weather_sensors") ? `Weather sensors show ${Math.round(activeThermalCell?.wind_kph ?? 18)} km/h wind and ${Math.round(activeThermalCell?.humidity_pct ?? 52)}% humidity in the active district.` : "Weather corroboration is thin, so spread forecasts remain conservative." },
      { title: "Seismic swarm frequency elevated", body: sourcePool.has("seismic_data") ? "Clustered precursor signals and anomaly scoring are above background, so the page frames this as anomaly likelihood rather than deterministic prediction." : "No strong seismic corroboration in the current fused packet." },
      { title: "Social signal spike confirms event chatter", body: sourcePool.has("social_media_signals") ? "Narrative velocity is supporting the alert, but social signals remain confidence-adjusting evidence rather than primary truth." : "Social corroboration is low, so model confidence leans on physical sensors first." },
    ].map((panel, index) => ({ ...panel, signal: signalPool[index] ?? null }));
  }, [activeThermalCell?.humidity_pct, activeThermalCell?.signal_sources, activeThermalCell?.wind_kph, selectedHazardForecast?.signal_sources, selectedHazardForecast?.top_contributing_signals, selectedHotspot?.signal_sources, selectedHotspot?.top_contributing_signals]);

  const districtMetrics = useMemo(() => {
    const rainfall = Number(selectedHazardForecast?.feature_values?.rainfall_accumulation ?? selectedHotspot?.hotspot_stats?.max_rainfall ?? activeThermalCell?.humidity_pct ?? 0);
    const pressure = Number(selectedHotspot?.hotspot_stats?.pressure_proxy ?? selectedHazardForecast?.feature_values?.pressure_proxy ?? 1008 - ((activeThermalCell?.hazard_pressure ?? 0.3) * 64));
    const anomaly = Number(selectedHazardForecast?.feature_values?.seismic_anomaly_score ?? selectedHotspot?.hotspot_score ?? activeThermalCell?.thermal_index ?? 0.2);
    return {
      rainfall_mm: rainfall,
      pressure_hpa: pressure,
      anomaly_score: anomaly,
      recommended_action: selectedHazardForecast?.recommended_action
        ?? (selectedHotspot
          ? hotspotQueue.find((item) => item.region === selectedHotspot.region && item.hazard === selectedHotspot.hazard)?.recommended_action
          : null)
        ?? "Hold district watch until the next fused sensor cycle confirms or cools the signal.",
      top_signals: (selectedHazardForecast?.top_contributing_signals?.length ? selectedHazardForecast.top_contributing_signals : selectedHotspot?.top_contributing_signals ?? []).slice(0, 5),
    };
  }, [activeThermalCell?.hazard_pressure, activeThermalCell?.humidity_pct, activeThermalCell?.thermal_index, hotspotQueue, selectedHazardForecast, selectedHotspot]);

  const modelQualityRows = useMemo(() => {
    const overall = forecast?.backtest_summary?.overall;
    const hazards = forecast?.backtest_summary?.hazards ?? {};
    return HOTSPOT_HAZARDS.map((hazard) => {
      const row = hazards[hazard];
      return {
        hazard,
        precision: Number(row?.precision_proxy ?? overall?.precision_proxy ?? forecast?.stream_status?.backtest_precision_proxy ?? 0),
        falsePositiveRate: Number(row?.false_positive_rate ?? overall?.false_positive_rate ?? 0),
        avgLead: Number(row?.avg_lead_time_hours ?? forecastByHazard.get(hazard)?.lead_time_hours ?? 0),
        avgConfidence: Number(row?.avg_confidence ?? forecastByHazard.get(hazard)?.confidence ?? 0),
      };
    });
  }, [forecast, forecastByHazard]);
  const strongestModelRow = useMemo(
    () => [...modelQualityRows].sort((left, right) => right.precision - left.precision)[0] ?? null,
    [modelQualityRows],
  );
  const weakestModelRow = useMemo(
    () => [...modelQualityRows].sort((left, right) => left.precision - right.precision)[0] ?? null,
    [modelQualityRows],
  );
  const calibrationRows = useMemo(() => {
    return HOTSPOT_HAZARDS.map((hazard) => {
      const forecastPacket = forecastByHazard.get(hazard);
      const hotspot = hotspotByHazard.get(hazard);
      const notes = [
        ...(forecastPacket?.calibration_adjustments?.notes ?? []),
        ...(hotspot?.calibration_adjustments?.notes ?? []),
      ].filter(Boolean).slice(0, 3);
      return {
        hazard,
        status: forecastPacket?.calibration_status ?? hotspot?.calibration_status ?? "pending_review",
        penalty: Number(forecastPacket?.calibration_adjustments?.penalty ?? hotspot?.calibration_adjustments?.penalty ?? 0),
        region: forecastPacket?.region_name ?? hotspot?.region_name ?? hotspot?.display_label ?? hotspot?.region ?? "--",
        notes,
      };
    });
  }, [forecastByHazard, hotspotByHazard]);

  const accelerating = useMemo(() => {
    return flattenMovers(forecast?.trend_comparison, "accelerating_fastest", selectedHazard).filter((item) => {
      return hotspotMatchesSourceFamily(hotspotLookup.get(`${item.hazard}:${item.region}`), selectedSourceFamily);
    });
  }, [forecast, hotspotLookup, selectedHazard, selectedSourceFamily]);

  const cooling = useMemo(() => {
    return flattenMovers(forecast?.trend_comparison, "cooling_fastest", selectedHazard).filter((item) => {
      return hotspotMatchesSourceFamily(hotspotLookup.get(`${item.hazard}:${item.region}`), selectedSourceFamily);
    });
  }, [forecast, hotspotLookup, selectedHazard, selectedSourceFamily]);

  useEffect(() => {
    if (!visibleHotspots.length) {
      setSelectedHotspot(null);
      return;
    }
    if (!selectedHotspot) {
      setSelectedHotspot(visibleHotspots[0]);
      return;
    }
    const next = visibleHotspots.find((item) => item.region === selectedHotspot.region && item.hazard === selectedHotspot.hazard);
    setSelectedHotspot(next ?? visibleHotspots[0]);
  }, [selectedHotspot?.hazard, selectedHotspot?.region, visibleHotspots]);

  useEffect(() => {
    if (!activeThermalPool.length) {
      setSelectedThermalCell(null);
      return;
    }
    if (!selectedThermalCell) {
      setSelectedThermalCell(activeThermalPool[0]);
      return;
    }
    const next = activeThermalPool.find((cell) => cell.cell_id === selectedThermalCell.cell_id);
    setSelectedThermalCell(next ?? activeThermalPool[0]);
  }, [activeThermalPool, selectedThermalCell?.cell_id]);

  const selectedQueueItem = useMemo(() => {
    if (!selectedHotspot) return null;
    return hotspotQueue.find((item) => item.region === selectedHotspot.region && item.hazard === selectedHotspot.hazard) ?? null;
  }, [hotspotQueue, selectedHotspot]);

  const selectedForecast = useMemo(() => {
    if (!selectedHotspot) return null;
    return (forecast?.forecasts ?? []).find((item) => item.region === selectedHotspot.region && item.event_type === selectedHotspot.hazard) ?? null;
  }, [forecast, selectedHotspot]);

  const activeSeries = selectedWindow === "5d"
    ? (selectedHotspot ? hotspotSeriesForWindow(selectedHotspot, "5d") : [])
    : (selectedHistory?.history?.[selectedWindow] ?? (selectedHotspot ? hotspotSeriesForWindow(selectedHotspot, selectedWindow) : []));
  const selectedDelta = selectedHistory?.delta_badge?.delta ?? deltaValue(activeSeries);
  const topSummary = forecast?.summary;
  const watchDeckHotspots = visibleHotspots.slice(0, 6);
  const queuePreview = hotspotQueue.slice(0, 8);
  const selectedTransitionItems = selectedHotspot
    ? transitions.filter((item) => item.region === selectedHotspot.region && (item.hazard ?? selectedHotspot.hazard) === selectedHotspot.hazard).slice(0, 5)
    : [];
  const leadRegion = leadRegionLabel(topSummary, selectedHazard);

  const focusSignalSources = useMemo(() => {
    const values = new Set<string>();
    for (const source of selectedQueueItem?.signal_sources ?? []) values.add(source);
    for (const source of selectedHotspot?.signal_sources ?? []) values.add(source);
    for (const source of selectedForecast?.signal_sources ?? []) values.add(source);
    return Array.from(values);
  }, [selectedForecast, selectedHotspot, selectedQueueItem]);

  const focusSignals = useMemo(() => {
    const values = new Set<string>();
    for (const signal of selectedQueueItem?.top_contributing_signals ?? []) values.add(signal);
    for (const signal of selectedHotspot?.top_contributing_signals ?? []) values.add(signal);
    for (const signal of selectedForecast?.top_contributing_signals ?? []) values.add(signal);
    return Array.from(values).slice(0, 6);
  }, [selectedForecast, selectedHotspot, selectedQueueItem]);

  const focusActionPayload = buildActionPayload(selectedQueueItem, selectedHotspot);
  const liveSourceCount = sourceHealthEntries.filter((item) => item.status === "up").length;
  const mapBriefTitle = activeThermalCell
    ? `${countryLabel(activeThermalCell.country)} / ${activeThermalCell.district_label ?? activeThermalCell.sector_label}`
    : selectedCountrySummary
      ? countryLabel(selectedCountrySummary.country)
      : selectedHotspot
        ? hotspotLabel(selectedHotspot)
        : "Global Thermal Theater";
  const mapBriefCopy = activeThermalCell
    ? `${formatTemperature(activeThermalCell.temperature_c)} surface temperature with ${formatThermalPercent(activeThermalCell.thermal_index)} thermal intensity, ${formatThermalPercent(activeThermalCell.hazard_pressure)} hazard pressure, and ${Math.round(activeThermalCell.lead_time_hours)}h lead time.`
    : selectedCountrySummary
      ? `${countryLabel(selectedCountrySummary.country)} averages ${formatTemperature(selectedCountrySummary.avg_temperature_c)} across ${(thermalFocus?.district_count ?? countrySectorCells.length) || selectedCountrySummary.sample_count} visible sectors. Click a sector to inspect local wind, humidity, and source contributors.`
      : selectedHotspot
        ? `${selectedHotspot.hazard.toUpperCase()} activity ${Math.round((selectedHotspot.hotspot_score ?? selectedHotspot.activity_score ?? 0) * 100)}% with confidence ${Math.round((selectedHotspot.hotspot_confidence ?? selectedHotspot.confidence ?? 0) * 100)}%.`
        : `Click any country on the ${mapModeLabel(selectedMapMode).toLowerCase()} map to open its district-level thermal surface and metrics.`;
  const mapBriefSources = activeThermalCell?.signal_sources ?? [];

  const submitAlertAction = async (action: AlertActionKey, item?: QueueItemWithHazard | null) => {
    const basePayload = buildActionPayload(item ?? null, item ? null : selectedHotspot);
    if (!basePayload) return;
    const dedupeKey = basePayload.dedupe_key ?? `${basePayload.hazard}:${basePayload.region}`;
    setActionBusyKey(`${action}:${dedupeKey}`);
    setActionNotice("");
    const response = await postDisasterAlertAction({
      ...basePayload,
      action,
      comment: action === "false_positive"
        ? "Flagged by operator for model feedback review."
        : action === "escalate"
          ? "Escalated for rapid operator review."
          : action === "snooze"
            ? "Temporarily snoozed while monitoring for confirmation."
            : "Acknowledged by operator.",
      false_positive_reason: action === "false_positive" ? "operator_review" : undefined,
      snooze_hours: action === "snooze" ? 6 : undefined,
    });
    setActionBusyKey(null);
    if (!response?.ok) {
      setActionNotice("Alert action failed. The queue stayed unchanged.");
      return;
    }
    setActionNotice(`${formatOpsStatus(action)} recorded for ${basePayload.region}.`);
    await refreshForecast();
  };
  useEffect(() => {
    let stopped = false;
    const loadPlotly = async () => {
      if (plotlyRef.current) return plotlyRef.current;
      if (!plotlyLoadingRef.current) {
        plotlyLoadingRef.current = import("plotly.js-dist-min").then((mod) => {
          plotlyRef.current = (mod as any).default ?? mod;
          return plotlyRef.current;
        });
      }
      return plotlyLoadingRef.current;
    };

    const drawMap = async () => {
      if (!mapRef.current) return;
      try {
        const Plotly = await loadPlotly();
        if (stopped || !mapRef.current) return;

        const playbackFactor = playbackStop.factor;
        const colorscale = selectedMapMode === "wildfire"
          ? [[0, "#1a0a07"], [0.3, "#7c2d12"], [0.55, "#ea580c"], [0.8, "#facc15"], [1, "#fff7ae"]]
          : selectedMapMode === "flood"
            ? [[0, "#03101d"], [0.25, "#0f4c81"], [0.5, "#0ea5e9"], [0.75, "#67e8f9"], [1, "#e0fbff"]]
            : selectedMapMode === "cyclone"
              ? [[0, "#0b0c1f"], [0.25, "#312e81"], [0.5, "#6366f1"], [0.75, "#a78bfa"], [1, "#f5ecff"]]
              : selectedMapMode === "seismic"
                ? [[0, "#06111f"], [0.25, "#164e63"], [0.5, "#06b6d4"], [0.75, "#7dd3fc"], [1, "#f0f9ff"]]
                : (thermalMap?.colorscale?.length ? thermalMap.colorscale : DEFAULT_THERMAL_COLORSCALE);
        const countryRows = Object.keys(COUNTRY_LABELS).map((countryCode) => {
          const row = thermalCountryLookup.get(countryCode);
          const thermalValue = row?.thermal_index ?? 0.04;
          const riskValue = clamp01((row?.risk_score ?? 18) / 100);
          const weatherValue = row?.weather_stress ?? 0.12;
          const modeValue = selectedMapMode === "wildfire"
            ? clamp01(((thermalValue * 0.52) + (weatherValue * 0.32) + (riskValue * 0.16)) * playbackFactor)
            : selectedMapMode === "flood"
              ? clamp01(((weatherValue * 0.52) + (riskValue * 0.24) + (thermalValue * 0.24)) * playbackFactor)
              : selectedMapMode === "cyclone"
                ? clamp01(((riskValue * 0.44) + (weatherValue * 0.26) + (thermalValue * 0.3)) * playbackFactor)
                : selectedMapMode === "seismic"
                  ? clamp01(((riskValue * 0.46) + (thermalValue * 0.34) + (weatherValue * 0.2)) * playbackFactor)
                  : thermalValue;
          return {
            country: countryCode,
            country_name: countryLabel(countryCode),
            avg_temperature_label: row ? `Avg Temp ${formatTemperature(row.avg_temperature_c)}` : "Click for local heat",
            thermal_label: row ? `${mapModeLabel(selectedMapMode)} ${formatThermalPercent(modeValue)}` : "Modeled drilldown on click",
            risk_label: row ? `Risk ${Math.round(row.risk_score)}` : "Risk populates on drilldown",
            weather_label: row ? `Weather Stress ${formatThermalPercent(row.weather_stress)}` : "Weather metrics on drilldown",
            sample_label: row ? `${row.sample_count} live samples` : "No live sample yet",
            surface_value: modeValue,
            center_lat: row?.center_lat ?? null,
            center_lon: row?.center_lon ?? null,
          };
        });
        const cellRows = (selectedCountry ? countrySectorCells : thermalCells).slice(0, selectedCountry ? 60 : 260);
        const modeHotspots = (mapModeHazardKey ? visibleHotspots.filter((item) => item.hazard === mapModeHazardKey) : visibleHotspots)
          .filter((item) => typeof item.center_lat === "number" && typeof item.center_lon === "number");
        const cellMetricValues = cellRows.map((cell) => {
          if (selectedMapMode === "wildfire") return clamp01(((cell.hazard_pressure * 0.58) + (cell.weather_stress * 0.28) + (cell.thermal_index * 0.14)) * playbackFactor) * 100;
          if (selectedMapMode === "flood") return clamp01((((cell.humidity_pct / 100) * 0.34) + (cell.hazard_pressure * 0.4) + (cell.weather_stress * 0.26)) * playbackFactor) * 100;
          if (selectedMapMode === "cyclone") return clamp01((((cell.wind_kph / 140) * 0.4) + (cell.hazard_pressure * 0.34) + (cell.risk_score / 100 * 0.26)) * playbackFactor) * 100;
          if (selectedMapMode === "seismic") return clamp01(((cell.thermal_index * 0.22) + (cell.hazard_pressure * 0.46) + (cell.risk_score / 100 * 0.32)) * playbackFactor) * 100;
          return cell.temperature_c;
        });
        const minMetricValue = cellMetricValues.length ? Math.min(...cellMetricValues) : 0;
        const maxMetricValue = cellMetricValues.length ? Math.max(...cellMetricValues) : (selectedMapMode === "thermal" ? 42 : 100);
        const focusLat = selectedCountryFocus?.lat ?? thermalFocus?.center_lat ?? selectedCountrySummary?.center_lat ?? null;
        const focusLon = selectedCountryFocus?.lon ?? thermalFocus?.center_lon ?? selectedCountrySummary?.center_lon ?? null;
        const traces: any[] = [];

        if (countryRows.length) {
          traces.push({
            type: "choropleth",
            locationmode: "ISO-3",
            locations: countryRows.map((item) => item.country),
            z: countryRows.map((item) => item.surface_value),
            zmin: 0,
            zmax: 1,
            colorscale,
            showscale: false,
            customdata: countryRows.map((item) => ["country", item.country, item.country_name, item.avg_temperature_label, item.thermal_label, item.risk_label, item.weather_label, item.sample_label]),
            hovertemplate: "<b>%{customdata[2]}</b><br>%{customdata[3]}<br>%{customdata[4]}<br>%{customdata[5]}<br>%{customdata[6]}<br>%{customdata[7]}<extra></extra>",
            marker: { line: { color: "rgba(122, 160, 196, 0.18)", width: 0.55 } },
            name: "country-surface",
          });
        }

        if (selectedCountry) {
          traces.push({
            type: "choropleth",
            locationmode: "ISO-3",
            locations: [selectedCountry],
            z: [selectedCountrySummary?.thermal_index ?? 0.8],
            zmin: 0,
            zmax: 1,
            colorscale: [[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
            showscale: false,
            hoverinfo: "skip",
            marker: { line: { color: "rgba(255,255,255,0.92)", width: 1.6 } },
            name: "selected-country-outline",
          });
        }

        if (cellRows.length) {
          traces.push({
            type: "scattergeo",
            mode: "markers",
            lon: cellRows.map((cell) => cell.lon),
            lat: cellRows.map((cell) => cell.lat),
            customdata: cellRows.map((cell) => [
              "cell",
              cell.cell_id,
              cell.country,
              countryLabel(cell.country),
              cell.district_label ?? cell.sector_label,
              cell.active_hazard,
              (cell.signal_sources ?? []).map((source) => sourceFamilyLabel(source)).join(", "),
              cell.sample_type ?? "observed",
              cell.temperature_c,
              cell.thermal_index,
              cell.hazard_pressure,
              cell.confidence,
              cell.wind_kph,
              cell.humidity_pct,
              cell.lead_time_hours,
            ]),
            hovertemplate: "<b>%{customdata[4]}</b><br>%{customdata[3]}<br>Temp %{customdata[8]:.1f}C<br>Thermal %{customdata[9]:.0%}<br>Hazard %{customdata[10]:.0%}<br>Confidence %{customdata[11]:.0%}<br>Wind %{customdata[12]:.0f} km/h<br>Humidity %{customdata[13]:.0f}%<br>Lead %{customdata[14]:.0f}h<extra></extra>",
            marker: {
              symbol: selectedMapMode === "cyclone" ? "diamond" : selectedMapMode === "seismic" ? "circle-open-dot" : "square",
              size: selectedCountry ? 24 : 16,
              color: cellMetricValues,
              cmin: selectedMapMode === "thermal" ? Math.min(minMetricValue, 0) : 0,
              cmax: selectedMapMode === "thermal" ? Math.max(maxMetricValue, minMetricValue + 10) : 100,
              colorscale,
              opacity: selectedCountry ? 0.92 : selectedMapMode === "thermal" ? 0.62 : 0.54,
              line: { color: "rgba(255,255,255,0.12)", width: selectedCountry ? 0.8 : 0.45 },
            },
            showlegend: false,
            name: "thermal-cells",
          });
        }

        if (modeHotspots.length) {
          traces.push({
            type: "scattergeo",
            mode: "markers",
            lon: modeHotspots.map((item) => item.center_lon),
            lat: modeHotspots.map((item) => item.center_lat),
            customdata: modeHotspots.map((item) => [
              "hotspot",
              item.region,
              item.hazard,
              hotspotSecondaryLabel(item),
              hotspotLabel(item),
              item.hotspot_score ?? item.activity_score ?? 0,
              item.hotspot_confidence ?? item.confidence ?? 0,
            ]),
            hovertemplate: "<b>%{customdata[4]}</b><br>%{customdata[3]}<br>Activity %{customdata[5]:.0%}<br>Confidence %{customdata[6]:.0%}<extra></extra>",
            marker: {
              size: modeHotspots.map((item) => 10 + ((item.hotspot_score ?? item.activity_score ?? 0.25) * 14 * playbackFactor)),
              color: modeHotspots.map((item) => HAZARD_ACCENT[item.hazard]),
              opacity: 0.92,
              line: { color: "rgba(226,232,240,0.88)", width: 1.05 },
            },
            showlegend: false,
            name: "hazard-hotspots",
          });
        }

        if (selectedMapMode === "wildfire") {
          modeHotspots.slice(0, 6).forEach((item) => {
            const radiusOne = (1.1 + ((item.hotspot_score ?? item.activity_score ?? 0.28) * 2.6)) * playbackFactor;
            const radiusTwo = radiusOne * 1.55;
            [radiusOne, radiusTwo].forEach((radius, index) => {
              const ring = buildGeoRing(Number(item.center_lat), Number(item.center_lon), radius, 36);
              traces.push({
                type: "scattergeo",
                mode: "lines",
                lon: ring.map((point) => point.lon),
                lat: ring.map((point) => point.lat),
                hoverinfo: "skip",
                line: { color: index === 0 ? "rgba(251,146,60,0.55)" : "rgba(250,204,21,0.38)", width: index === 0 ? 2.2 : 1.4 },
                showlegend: false,
              });
            });
          });
        }

        if (selectedMapMode === "flood") {
          modeHotspots.slice(0, 6).forEach((item) => {
            const extent = buildGeoRing(Number(item.center_lat), Number(item.center_lon), (1.3 + ((item.hotspot_score ?? item.activity_score ?? 0.28) * 3.2)) * playbackFactor, 36);
            traces.push({
              type: "scattergeo",
              mode: "lines",
              lon: extent.map((point) => point.lon),
              lat: extent.map((point) => point.lat),
              hoverinfo: "skip",
              fill: "toself",
              fillcolor: "rgba(34, 211, 238, 0.12)",
              line: { color: "rgba(56, 189, 248, 0.48)", width: 1.6 },
              showlegend: false,
            });
          });
        }

        if (selectedMapMode === "cyclone") {
          modeHotspots.slice(0, 4).forEach((item) => {
            const startLat = Number(item.center_lat);
            const startLon = Number(item.center_lon);
            const score = Number(item.hotspot_score ?? item.activity_score ?? 0.32);
            const trackLat = [startLat, startLat + (1.6 * playbackFactor), startLat + (3.4 * playbackFactor), startLat + (5.3 * playbackFactor)];
            const trackLon = [startLon, startLon + (2.1 * playbackFactor), startLon + (4.9 * playbackFactor), startLon + (7.6 * playbackFactor)];
            traces.push({
              type: "scattergeo",
              mode: "lines+markers",
              lon: trackLon,
              lat: trackLat,
              hoverinfo: "skip",
              line: { color: "rgba(167,139,250,0.82)", width: 2.4 },
              marker: { size: [6, 8, 10, 12].map((size) => size + (score * 10)), color: "rgba(196,181,253,0.9)" },
              showlegend: false,
            });
            const coneLon = [startLon - (0.8 * score), trackLon[3] + (2.2 * score * playbackFactor), trackLon[3] - (1.7 * score * playbackFactor), startLon - (0.8 * score)];
            const coneLat = [startLat - (0.7 * score), trackLat[3] + (2.8 * score * playbackFactor), trackLat[3] - (2.4 * score * playbackFactor), startLat - (0.7 * score)];
            traces.push({
              type: "scattergeo",
              mode: "lines",
              lon: coneLon,
              lat: coneLat,
              hoverinfo: "skip",
              fill: "toself",
              fillcolor: "rgba(167,139,250,0.13)",
              line: { color: "rgba(167,139,250,0.44)", width: 1.4 },
              showlegend: false,
            });
          });
        }

        if (selectedMapMode === "seismic") {
          modeHotspots.slice(0, 6).forEach((item) => {
            const startLat = Number(item.center_lat);
            const startLon = Number(item.center_lon);
            const score = Number(item.hotspot_score ?? item.activity_score ?? 0.24);
            traces.push({
              type: "scattergeo",
              mode: "lines",
              lon: [startLon - (3.4 * playbackFactor), startLon - (1.1 * playbackFactor), startLon + (1.8 * playbackFactor), startLon + (4.4 * playbackFactor)],
              lat: [startLat - (1.5 * score), startLat + (0.2 * score), startLat - (0.6 * score), startLat + (1.2 * score)],
              hoverinfo: "skip",
              line: { color: "rgba(34,211,238,0.7)", width: 2.2, dash: "dot" },
              showlegend: false,
            });
            const anomalyRing = buildGeoRing(startLat, startLon, (0.8 + (score * 2.1)) * playbackFactor, 30);
            traces.push({
              type: "scattergeo",
              mode: "lines",
              lon: anomalyRing.map((point) => point.lon),
              lat: anomalyRing.map((point) => point.lat),
              hoverinfo: "skip",
              line: { color: "rgba(103,232,249,0.56)", width: 1.6 },
              showlegend: false,
            });
          });
        }
        if (activeThermalCell) {
          traces.push({
            type: "scattergeo",
            mode: "markers",
            lon: [activeThermalCell.lon],
            lat: [activeThermalCell.lat],
            hoverinfo: "skip",
            marker: { size: selectedCountry ? 34 : 24, color: "rgba(0,0,0,0)", line: { color: "rgba(255,255,255,0.96)", width: 1.8 } },
            showlegend: false,
          });
        }

        if (selectedHotspot && typeof selectedHotspot.center_lat === "number" && typeof selectedHotspot.center_lon === "number") {
          traces.push({
            type: "scattergeo",
            mode: "markers",
            lon: [selectedHotspot.center_lon],
            lat: [selectedHotspot.center_lat],
            hoverinfo: "skip",
            marker: { size: 30, color: "rgba(0,0,0,0)", line: { color: HAZARD_ACCENT[selectedHotspot.hazard], width: 2.4 } },
            showlegend: false,
          });
        }

        await Plotly.react(mapRef.current, traces, {
          margin: { l: 0, r: 0, b: 0, t: 0 },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          uirevision: `hazard-ops-${selectedMapMode}-${selectedHazard}-${selectedWindow}-${selectedSourceFamily}-${selectedCountry ?? "global"}-${playbackStop.label}`,
          clickmode: "event+select",
          geo: {
            domain: { x: [0.01, 0.99], y: [0.02, 0.99] },
            projection: { type: "natural earth", scale: selectedCountry ? Math.max(Number(thermalFocus?.zoom_scale ?? 3.2), 2.8) : GLOBAL_MAP_WORLD_SCALE },
            center: selectedCountry && Number.isFinite(Number(focusLat)) && Number.isFinite(Number(focusLon)) ? { lat: Number(focusLat), lon: Number(focusLon) } : undefined,
            showframe: false,
            bgcolor: "rgba(0,0,0,0)",
            showland: true,
            landcolor: "rgba(20, 33, 53, 0.92)",
            showocean: true,
            oceancolor: "rgba(2, 8, 18, 0.98)",
            showcountries: true,
            countrycolor: "rgba(148,163,184,0.2)",
            coastlinecolor: "rgba(148,163,184,0.14)",
            lakecolor: "rgba(2, 8, 18, 0.98)",
          },
        } as any, { displayModeBar: false, responsive: true });

        const mapNode = mapRef.current as any;
        mapNode?.removeAllListeners?.("plotly_click");
        mapNode?.on?.("plotly_click", (event: any) => {
          const point = event?.points?.[0];
          const custom = Array.isArray(point?.customdata) ? point.customdata : [];
          const kind = String(custom[0] ?? "");
          const traceType = String(point?.data?.type ?? "");
          const traceName = String(point?.data?.name ?? "");
          const locationCode = String(point?.location ?? custom[1] ?? "").toUpperCase();

          if ((traceType === "choropleth" || traceName === "country-surface") && locationCode) {
            const summary = thermalCountryLookup.get(locationCode) ?? null;
            setSelectedCountry(locationCode);
            setSelectedCountryFocus(resolveCountryFocus(locationCode, point?.lat, point?.lon, summary?.center_lat ?? null, summary?.center_lon ?? null));
            setSelectedThermalCell(null);
            return;
          }

          if (kind === "cell" || traceName === "thermal-cells") {
            const cellId = String(custom[1] ?? "");
            const nextCell = thermalCells.find((cell) => cell.cell_id === cellId) ?? cellRows.find((cell) => cell.cell_id === cellId) ?? null;
            if (!nextCell) return;
            setSelectedCountry(nextCell.country);
            setSelectedCountryFocus(resolveCountryFocus(nextCell.country, point?.lat, point?.lon, nextCell.lat, nextCell.lon));
            setSelectedThermalCell(nextCell);
            return;
          }

          if (kind === "hotspot" || traceName === "hazard-hotspots") {
            const region = String(custom[1] ?? "");
            const hazard = String(custom[2] ?? "") as Exclude<HotspotHazardKey, "all">;
            if (!region || !hazard) return;
            setSelectedHotspot(allHotspots.find((item) => item.region === region && item.hazard === hazard) ?? null);
          }
        });
      } catch {
        // Keep the rest of the page usable if Plotly fails.
      }
    };

    void drawMap();
    return () => {
      stopped = true;
    };
  }, [
    activeThermalCell,
    allHotspots,
    countrySectorCells,
    selectedCountry,
    selectedCountryFocus?.lat,
    selectedCountryFocus?.lon,
    selectedCountrySummary,
    selectedHazard,
    selectedHotspot,
    selectedSourceFamily,
    selectedWindow,
    thermalCells,
    thermalCountries,
    thermalCountryLookup,
    thermalFocus,
    thermalMap,
    visibleHotspots,
    selectedMapMode,
    playbackStop.label,
    playbackStop.factor,
  ]);

  return (
    <main ref={mainRef} className="hazard-ops-shell">
      <div className="hazard-ops-backdrop" />
      <header className="hazard-ops-topbar">
        <div className="hazard-ops-topbar-copy">
          <span className="hazard-ops-kicker">World Pulse / Disaster Warning Grid</span>
          <h1>Global Early Warning</h1>
          <p>A live operational surface for hazard scoring, source-family confidence, and explainable alert actions.</p>
        </div>
        <div className="hazard-ops-header-meta">
          <div><span>Last Update</span><strong>{formatTimestamp(forecast?.last_updated)}</strong></div>
          <div><span>Scope</span><strong>{hazardLabel(selectedHazard)}</strong></div>
          <div><span>Source Filter</span><strong>{selectedSourceFamily === "all" ? "All Families" : sourceFamilyLabel(selectedSourceFamily)}</strong></div>
          <button type="button" onClick={() => navigate("/dashboard")}>Back To Dashboard</button>
        </div>
      </header>

      <section id="hazard-ops-overview" className="hazard-ops-hero-grid">
        <article className="hazard-ops-hero-panel">
          <span className="hazard-ops-eyebrow">Operational Bridge</span>
          <h2>{selectedHazard === "all" ? "Cross-Hazard Triage" : hotspotLayerTitle(selectedHazard)}</h2>
          <p>Filter by hazard or source family, review why an alert exists, and take operator action without leaving the page.</p>
          <div className="hazard-ops-chip-stack">
            <div className="hazard-ops-chip-row">
              {(["all", "earthquake", "wildfire", "flood", "cyclone"] as HotspotHazardKey[]).map((hazard) => (
                <button key={hazard} type="button" className={selectedHazard === hazard ? "is-active" : ""} onClick={() => setSelectedHazard(hazard)}>{hazardLabel(hazard)}</button>
              ))}
            </div>
            <div className="hazard-ops-chip-row is-source-row">
              <button type="button" className={selectedSourceFamily === "all" ? "is-active" : ""} onClick={() => setSelectedSourceFamily("all")}>All Sources</button>
              {activeSourceFamilies.map((family) => (
                <button key={family} type="button" className={selectedSourceFamily === family ? "is-active" : ""} onClick={() => setSelectedSourceFamily(family)}>{sourceFamilyLabel(family)}</button>
              ))}
            </div>
            <div className="hazard-ops-chip-row is-window-row">
              {FORECAST_WINDOWS.map((windowKey) => (
                <button key={windowKey} type="button" className={selectedWindow === windowKey ? "is-active" : ""} onClick={() => setSelectedWindow(windowKey)}>{windowKey}</button>
              ))}
            </div>
          </div>
        </article>

        <article className="hazard-ops-summary-panel">
          <div className="hazard-ops-summary-grid">
            <div><span>Lead Region</span><strong>{leadRegion}</strong></div>
            <div><span>Critical / High</span><strong>{topSummary?.critical_or_high_count ?? 0}</strong></div>
            <div><span>Visible Queue</span><strong>{hotspotQueue.length}</strong></div>
            <div><span>Forecast Packets</span><strong>{visibleForecasts.length}</strong></div>
            <div><span>Live Families</span><strong>{liveSourceCount} / {sourceHealthEntries.length}</strong></div>
            <div><span>Suppressed</span><strong>{forecast?.alert_ops_summary?.suppressed_by_snooze ?? 0}</strong></div>
          </div>
          <div className="hazard-ops-ops-summary">
            <span>Alert Ops</span>
            <div><strong>{forecast?.alert_ops_summary?.acknowledged ?? 0}</strong><small>Acknowledged</small></div>
            <div><strong>{forecast?.alert_ops_summary?.snoozed_active ?? 0}</strong><small>Snoozed</small></div>
            <div><strong>{forecast?.alert_ops_summary?.escalated ?? 0}</strong><small>Escalated</small></div>
            <div><strong>{forecast?.alert_ops_summary?.false_positive_flags ?? 0}</strong><small>Feedback Flags</small></div>
          </div>
        </article>
      </section>

      <section className="hazard-ops-deck-card hazard-ops-intel-board">
        <div className="hazard-ops-card-head">
          <div>
            <span className="hazard-ops-eyebrow">Mission Control</span>
            <strong>Forecast, Source, and Pipeline Deck</strong>
            <p>One clean workspace for forecast posture, source health, and processing stages instead of stacking every intelligence layer at once.</p>
          </div>
          <span className="hazard-ops-count-pill">
            {selectedIntelTab === "forecasts"
              ? `${hazardForecastCards.length} hazards`
              : selectedIntelTab === "sources"
                ? `${sourceIntelCards.length} source families`
                : `${pipelineStages.length} stages`}
          </span>
        </div>
        <div className="hazard-ops-deck-tabs">
          <button type="button" className={selectedIntelTab === "forecasts" ? "is-active" : ""} onClick={() => setSelectedIntelTab("forecasts")}>Forecast Board</button>
          <button type="button" className={selectedIntelTab === "sources" ? "is-active" : ""} onClick={() => setSelectedIntelTab("sources")}>Source Intel</button>
          <button type="button" className={selectedIntelTab === "pipeline" ? "is-active" : ""} onClick={() => setSelectedIntelTab("pipeline")}>Pipeline</button>
        </div>

        {selectedIntelTab === "forecasts" ? (
          <div className="hazard-ops-forecast-board is-embedded">
            {hazardForecastCards.map((card) => (
              <article key={card.hazard} className={`hazard-ops-forecast-card hazard-${card.hazard} ${selectedHazard === card.hazard ? "is-active" : ""}`}>
                <div className="hazard-ops-card-head compact">
                  <div>
                    <span className="hazard-ops-eyebrow">{card.modelLabel}</span>
                    <strong>{card.title}</strong>
                    <p>{card.summary}</p>
                  </div>
                  <button
                    type="button"
                    className="hazard-ops-forecast-focus"
                    onClick={() => {
                      setSelectedHazard(card.hazard);
                      setSelectedMapMode(hazardToMapMode(card.hazard));
                      if (card.hotspot) setSelectedHotspot(card.hotspot);
                    }}
                  >
                    Open
                  </button>
                </div>
                <div className="hazard-ops-forecast-window-grid">
                  {card.windows.map((windowItem) => (
                    <button
                      key={`${card.hazard}-${windowItem.window}`}
                      type="button"
                      className={selectedWindow === windowItem.window ? "is-active" : ""}
                      onClick={() => {
                        setSelectedWindow(windowItem.window);
                        setSelectedHazard(card.hazard);
                        setSelectedMapMode(hazardToMapMode(card.hazard));
                      }}
                    >
                      <span>{windowItem.window}</span>
                      <strong>{formatPercent(windowItem.likelihood)}</strong>
                      <small>Severity {formatPercent(windowItem.severity)}</small>
                      <small>Confidence {formatPercent(windowItem.confidence)}</small>
                    </button>
                  ))}
                </div>
                <div className="hazard-ops-forecast-metrics">
                  {card.metrics.map((metric) => <div key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong></div>)}
                </div>
                <div className="hazard-ops-pill-group compact">
                  {card.signals.length ? card.signals.map((signal) => <span key={signal} className="hazard-ops-signal-pill">{signal}</span>) : <span className="hazard-ops-signal-pill is-muted">Awaiting driver summary</span>}
                </div>
                <div className="hazard-ops-forecast-action">{card.recommendedAction}</div>
              </article>
            ))}
          </div>
        ) : selectedIntelTab === "sources" ? (
          <div className="hazard-ops-source-grid is-embedded">
            {sourceIntelCards.map((source) => {
              const active = selectedSourceFamily === source.source_family;
              return (
                <button key={source.source_family} type="button" className={`hazard-ops-source-card status-${source.status} ${active ? "is-active" : ""}`} onClick={() => setSelectedSourceFamily(active ? "all" : source.source_family)}>
                  <div className="hazard-ops-source-topline">
                    <strong>{sourceFamilyLabel(source.source_family)}</strong>
                    <span className={`hazard-ops-status-pill is-${source.status}`}>{source.status}</span>
                  </div>
                  <p>{source.advisory ?? "Awaiting source heartbeat"}</p>
                  <div className="hazard-ops-source-meta">
                    <span>{formatFreshness(source.freshness_minutes)}</span>
                    <span>{source.throughput_label}</span>
                    <span>{source.outage_label}</span>
                  </div>
                  <div className="hazard-ops-source-confidence">
                    <div className="hazard-ops-source-confidence-bar"><span style={{ width: `${Math.max(12, Math.round(source.confidence_score * 100))}%` }} /></div>
                    <strong>{formatPercent(source.confidence_score)}</strong>
                  </div>
                  <div className="hazard-ops-source-components">
                    {(source.component_sources ?? []).slice(0, 3).map((item) => <span key={item}>{sourceFamilyLabel(item)}</span>)}
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="hazard-ops-pipeline-ribbon is-embedded">
            {pipelineStages.map((stage) => (
              <article key={stage.key} className="hazard-ops-pipeline-stage">
                <span className="hazard-ops-eyebrow">{stage.key}</span>
                <strong>{stage.label}</strong>
                <p>{stage.detail}</p>
                <div className="hazard-ops-pipeline-meter"><span style={{ width: `${Math.max(12, Math.round(stage.progress * 100))}%` }} /></div>
                <small>{stage.metric}</small>
              </article>
            ))}
          </div>
        )}
      </section>

      <section id="hazard-ops-map" className="hazard-ops-main-grid">
        <article className="hazard-ops-map-card">
          <div className="hazard-ops-card-head">
            <div>
              <span className="hazard-ops-eyebrow">{mapModeLabel(selectedMapMode)} / AI Theater</span>
              <strong>{selectedCountry ? `${countryLabel(selectedCountry)} ${mapModeLabel(selectedMapMode)} Drilldown` : `Global ${mapModeLabel(selectedMapMode)} Operations Map`}</strong>
              <p>{selectedCountry ? `District-level cells for ${countryLabel(selectedCountry)} now show temperature, stress, rainfall, pressure, anomaly likelihood, and action guidance.` : "Switch map modes to move from thermal context into wildfire spread, flood depth, cyclone cone, or seismic anomaly views."}</p>
            </div>
            <div className="hazard-ops-thermal-head-side">
              <div className="hazard-ops-legend-row">
                {HOTSPOT_HAZARDS.map((hazard) => <span key={hazard}><i style={{ background: HAZARD_ACCENT[hazard] }} />{hazard}</span>)}
              </div>
              <div className="hazard-ops-thermal-scale">
                <span>Cold</span>
                <div className="hazard-ops-thermal-scale-bar" />
                <span>Critical Heat</span>
              </div>
              {selectedCountry ? <button type="button" className="hazard-ops-clear-button" onClick={() => { setSelectedCountry(null); setSelectedCountryFocus(null); setSelectedThermalCell(null); }}>Back To Global Map</button> : null}
            </div>
          </div>

          <div className="hazard-ops-map-mode-row">
            {MAP_MODE_OPTIONS.map((mode) => (
              <button
                key={mode.key}
                type="button"
                className={selectedMapMode === mode.key ? "is-active" : ""}
                onClick={() => {
                  setSelectedMapMode(mode.key);
                  setSelectedHazard(mode.key === "thermal" ? "all" : (mapModeHazard(mode.key) ?? "all"));
                }}
              >
                <strong>{mode.label}</strong>
                <span>{mode.detail}</span>
              </button>
            ))}
          </div>

          <div className="hazard-ops-playback-card">
            <div className="hazard-ops-card-head compact">
              <div>
                <span className="hazard-ops-eyebrow">Playback / Forecast Timeline</span>
                <strong>{playbackStop.label}</strong>
                <p>{playbackStop.detail}. The map and forecast overlays rescale as you scrub from baseline to +5 day outlook.</p>
              </div>
              <span className="hazard-ops-count-pill">{playbackStop.horizonHours >= 0 ? `+${playbackStop.horizonHours}h` : `${playbackStop.horizonHours}h`}</span>
            </div>
            <input className="hazard-ops-playback-slider" type="range" min={0} max={PLAYBACK_STOPS.length - 1} step={1} value={playbackIndex} onChange={(event) => setPlaybackIndex(Number(event.target.value))} />
            <div className="hazard-ops-playback-labels">
              {PLAYBACK_STOPS.map((stop, index) => (
                <button key={stop.label} type="button" className={playbackIndex === index ? "is-active" : ""} onClick={() => setPlaybackIndex(index)}>
                  <strong>{stop.label}</strong>
                  <span>{stop.detail}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="hazard-ops-map-stage-wrap">
            <div className="hazard-ops-map-stage"><div ref={mapRef} className="hazard-ops-map-canvas" /></div>
            <div className="hazard-ops-map-note">
              <span className="hazard-ops-eyebrow">Live Brief</span>
              <strong>{mapBriefTitle}</strong>
              <p>{mapBriefCopy}</p>
              <div className="hazard-ops-pill-group compact">
                <span className="hazard-ops-source-pill">Mode {mapModeLabel(selectedMapMode)}</span>
                <span className="hazard-ops-source-pill">Playback {playbackStop.label}</span>
                {mapBriefSources.slice(0, 3).map((source) => <span key={source} className="hazard-ops-source-pill">{sourceFamilyLabel(source)}</span>)}
              </div>
            </div>
          </div>

          <div className="hazard-ops-thermal-detail">
            <div className="hazard-ops-card-head compact">
              <div>
                <span className="hazard-ops-eyebrow">Country Drilldown</span>
                <strong>{selectedCountry ? `${countryLabel(selectedCountry)} District Metrics` : "Select A Country"}</strong>
                <p>{selectedCountry ? `Heat-colored districts or sectors for ${countryLabel(selectedCountry)} with full local forecast context.` : "Click any country to open district-level metrics, explainability, and recommended action for that country."}</p>
              </div>
              <span className="hazard-ops-count-pill">{selectedCountry ? `${countrySectorCells.length} sectors` : "Global view"}</span>
            </div>

            {selectedCountry ? (
              <>
                <div className="hazard-ops-thermal-summary-grid">
                  <div className="hazard-ops-thermal-summary-card"><span>Avg Temp</span><strong>{formatTemperature(thermalFocus?.avg_temperature_c ?? selectedCountrySummary?.avg_temperature_c)}</strong></div>
                  <div className="hazard-ops-thermal-summary-card"><span>Peak Temp</span><strong>{formatTemperature(thermalFocus?.peak_temperature_c ?? activeThermalCell?.temperature_c)}</strong></div>
                  <div className="hazard-ops-thermal-summary-card"><span>District Count</span><strong>{thermalFocus?.district_count ?? countrySectorCells.length}</strong></div>
                  <div className="hazard-ops-thermal-summary-card"><span>Hazard Pressure</span><strong>{formatThermalPercent(thermalFocus?.avg_hazard_pressure)}</strong></div>
                  <div className="hazard-ops-thermal-summary-card"><span>Risk Score</span><strong>{Math.round(Number(thermalFocus?.country_risk_score ?? selectedCountrySummary?.risk_score ?? 0))}</strong></div>
                  <div className="hazard-ops-thermal-summary-card"><span>Source Confidence</span><strong>{formatThermalPercent(thermalFocus?.source_confidence ?? selectedCountrySummary?.source_confidence)}</strong></div>
                </div>

                <div className="hazard-ops-thermal-sector-grid">
                  {countrySectorCells.map((cell) => {
                    const selected = activeThermalCell?.cell_id === cell.cell_id;
                    return (
                      <button
                        key={cell.cell_id}
                        type="button"
                        className={`hazard-ops-thermal-sector-card ${selected ? "is-selected" : ""}`}
                        onClick={() => {
                          setSelectedThermalCell(cell);
                          setSelectedCountryFocus({ lat: cell.lat, lon: cell.lon });
                        }}
                      >
                        <div className="hazard-ops-thermal-sector-head">
                          <div>
                            <strong>{cell.district_label ?? cell.sector_label}</strong>
                            <small>{cell.city_anchor ? `${cell.city_anchor} anchor` : cell.sample_type === "modeled" ? "Modeled sector" : "Observed sector"}</small>
                          </div>
                          <span>{String(cell.active_hazard || "thermal").toUpperCase()}</span>
                        </div>
                        <div className="hazard-ops-thermal-reading">
                          <strong>{formatTemperature(cell.temperature_c)}</strong>
                          <span>{formatThermalPercent(cell.thermal_index)} thermal</span>
                        </div>
                        <div className="hazard-ops-thermal-bar"><span style={{ width: `${Math.max(10, Math.round((cell.thermal_index ?? 0) * 100))}%` }} /></div>
                        <div className="hazard-ops-thermal-metrics">
                          <span>Temperature / Stress {formatTemperature(cell.temperature_c)} / {formatThermalPercent(cell.weather_stress)}</span>
                          <span>Rainfall {Math.round(districtMetrics.rainfall_mm)} mm</span>
                          <span>Wind {Math.round(cell.wind_kph)} km/h</span>
                          <span>Pressure {Math.round(districtMetrics.pressure_hpa)} hPa</span>
                          <span>Anomaly {formatThermalPercent(districtMetrics.anomaly_score)}</span>
                          <span>Confidence {formatThermalPercent(cell.confidence)}</span>
                        </div>
                        <div className="hazard-ops-pill-group compact">
                          {(cell.signal_sources ?? []).slice(0, 4).map((source) => <span key={source} className="hazard-ops-source-pill">{sourceFamilyLabel(source)}</span>)}
                        </div>
                      </button>
                    );
                  })}
                </div>

                <div className="hazard-ops-district-panel">
                  <div className="hazard-ops-card-head compact">
                    <div>
                      <span className="hazard-ops-eyebrow">District Explainability</span>
                      <strong>{activeThermalCell ? `${activeThermalCell.district_label ?? activeThermalCell.sector_label} / ${countryLabel(activeThermalCell.country)}` : "Awaiting district selection"}</strong>
                      <p>{activeThermalCell ? "This panel fuses local cell conditions with hazard forecasts, source contributors, and recommended action." : "Select a district cell to inspect its explainability stack."}</p>
                    </div>
                    <span className={`hazard-ops-band-pill is-${priorityBandTone(selectedQueueItem?.priority_band ?? selectedHotspot?.hotspot_band ?? activeThermalCell?.active_hazard)}`}>{String(selectedQueueItem?.priority_band ?? selectedHotspot?.hotspot_band ?? "monitor").toUpperCase()}</span>
                  </div>
                  <div className="hazard-ops-district-metric-grid">
                    <div><span>Temperature / Stress</span><strong>{activeThermalCell ? `${formatTemperature(activeThermalCell.temperature_c)} / ${formatThermalPercent(activeThermalCell.weather_stress)}` : "--"}</strong></div>
                    <div><span>Rainfall / Wind / Pressure</span><strong>{`${Math.round(districtMetrics.rainfall_mm)} mm / ${Math.round(activeThermalCell?.wind_kph ?? 0)} km/h / ${Math.round(districtMetrics.pressure_hpa)} hPa`}</strong></div>
                    <div><span>Anomaly Score</span><strong>{formatThermalPercent(districtMetrics.anomaly_score)}</strong></div>
                    <div><span>Confidence</span><strong>{formatThermalPercent(activeThermalCell?.confidence ?? selectedHazardForecast?.confidence ?? 0)}</strong></div>
                  </div>
                  <div className="hazard-ops-pill-group compact">
                    {districtMetrics.top_signals.length ? districtMetrics.top_signals.map((signal) => <span key={signal} className="hazard-ops-signal-pill">{signal}</span>) : <span className="hazard-ops-signal-pill is-muted">Awaiting top contributing signals</span>}
                  </div>
                  <div className="hazard-ops-recommended-action is-district-action">
                    <span className="hazard-ops-eyebrow">Recommended Action</span>
                    <p>{districtMetrics.recommended_action}</p>
                  </div>
                  <div className="hazard-ops-explainability-grid">
                    {explainabilityPanels.map((panel) => (
                      <article key={panel.title} className="hazard-ops-explainability-card">
                        <strong>{panel.title}</strong>
                        <p>{panel.body}</p>
                        {panel.signal ? <span>{panel.signal}</span> : null}
                      </article>
                    ))}
                  </div>
                </div>
              </>
            ) : <div className="hazard-ops-empty">Click any country on the selected map mode to open district-level temperature, stress, rainfall, pressure, anomaly, and action guidance.</div>}
          </div>
        </article>

        <aside id="hazard-ops-focus" className="hazard-ops-focus-card">
          <div className="hazard-ops-card-head compact">
            <div>
              <span className="hazard-ops-eyebrow">Operational Focus</span>
              <strong>{selectedHotspot ? hotspotLabel(selectedHotspot) : "No active selection"}</strong>
              <p>{selectedHotspot ? hotspotSecondaryLabel(selectedHotspot) : "Choose a hotspot from the map or queue."}</p>
            </div>
            <span className={`hazard-ops-band-pill is-${priorityBandTone(selectedQueueItem?.priority_band ?? selectedHotspot?.hotspot_band)}`}>{String(selectedQueueItem?.priority_band ?? selectedHotspot?.hotspot_band ?? "guarded").toUpperCase()}</span>
          </div>

          <div className="hazard-ops-alert-ladder">
            {alertLadder.map((step) => (
              <div key={step.key} className={`hazard-ops-alert-step ${step.active ? "is-active" : ""} is-${step.key}`}>
                <span>{step.label}</span>
                <strong>{step.count}</strong>
              </div>
            ))}
          </div>

          {selectedHotspot ? (
            <div className="hazard-ops-focus-core">
              <div className="hazard-ops-focus-stats">
                <div><span>Activity</span><strong>{Math.round((selectedQueueItem?.adjusted_activity ?? selectedHotspot.hotspot_score ?? selectedHotspot.activity_score ?? 0) * 100)}%</strong></div>
                <div><span>Confidence</span><strong>{Math.round((selectedQueueItem?.confidence ?? selectedHotspot.hotspot_confidence ?? selectedHotspot.confidence ?? 0) * 100)}%</strong></div>
                <div><span>Lead Time</span><strong>{Math.round(selectedQueueItem?.lead_time_hours ?? selectedForecast?.lead_time_hours ?? selectedHotspot.lead_time_hours ?? 0)}h</strong></div>
                <div><span>Ops State</span><strong>{formatOpsStatus(selectedQueueItem?.ops_state?.status)}</strong></div>
              </div>

              <div className="hazard-ops-recommended-action">
                <span className="hazard-ops-eyebrow">Recommended Action</span>
                <p>{selectedQueueItem?.recommended_action ?? selectedForecast?.recommended_action ?? "Continue monitoring until the alert reaches the active queue threshold."}</p>
              </div>

              <div className="hazard-ops-corroboration-note">
                <strong>AI Corroboration</strong>
                <p>Satellite, seismic, weather, ocean, and social signals are fused here. Social signals adjust confidence and help corroborate narrative acceleration, but they are not treated as primary truth over physical sensors.</p>
              </div>

              <div className="hazard-ops-action-row">
                {(["acknowledge", "snooze", "escalate", "false_positive"] as AlertActionKey[]).map((action) => {
                  const actionKey = `${action}:${focusActionPayload?.dedupe_key ?? focusActionPayload?.hazard ?? "none"}`;
                  return <button key={action} type="button" className={`hazard-ops-action-button action-${action}`} disabled={!focusActionPayload || actionBusyKey === actionKey} onClick={() => void submitAlertAction(action)}>{actionBusyKey === actionKey ? "Working..." : formatOpsStatus(action)}</button>;
                })}
              </div>
              {actionNotice ? <div className="hazard-ops-action-notice">{actionNotice}</div> : null}

              <div className="hazard-ops-meta-grid">
                <div><span>Threshold</span><strong>{selectedQueueItem?.threshold_reason ?? "Below active alert threshold"}</strong></div>
                <div><span>Dedupe</span><strong>{selectedQueueItem?.dedupe_key ?? `${selectedHotspot.hazard}:${selectedHotspot.region}`}</strong></div>
                <div><span>Feedback Adjustment</span><strong>{Math.round((selectedQueueItem?.feedback_adjustment ?? 0) * 100)} pts</strong></div>
                <div><span>Last Operator Touch</span><strong>{formatTimestamp(selectedQueueItem?.ops_state?.last_timestamp)}</strong></div>
              </div>

              <div className="hazard-ops-pill-group">
                {focusSignalSources.length ? focusSignalSources.map((source) => <span key={source} className="hazard-ops-source-pill">{sourceFamilyLabel(source)}</span>) : <span className="hazard-ops-source-pill is-muted">No source family tags</span>}
              </div>

              <div className="hazard-ops-pill-group is-signal-group">
                {focusSignals.length ? focusSignals.map((signal) => <span key={signal} className="hazard-ops-signal-pill">{signal}</span>) : <span className="hazard-ops-signal-pill is-muted">No explainability notes yet</span>}
              </div>

              <div className="hazard-ops-history-card">
                <div className="hazard-ops-history-head"><span className="hazard-ops-eyebrow">Trend Signal</span><strong>{deltaLabel(selectedDelta)}</strong></div>
                <svg viewBox="0 0 160 44" preserveAspectRatio="none"><path d={sparklinePath(activeSeries)} /></svg>
              </div>

              <div className="hazard-ops-transition-list">
                {selectedTransitionItems.length ? selectedTransitionItems.map((item) => (
                  <div key={`${item.hazard}-${item.region}-${item.timestamp}`} className="hazard-ops-transition-item">
                    <strong>{item.to_band.toUpperCase()}</strong>
                    <span>{formatTimestamp(item.timestamp)}</span>
                    <span>{item.from_band ? `${item.from_band} -> ${item.to_band}` : item.to_band}</span>
                  </div>
                )) : <div className="hazard-ops-empty compact">No recent threshold transitions for this region.</div>}
              </div>
            </div>
          ) : <div className="hazard-ops-empty">Pick a hotspot to open source contributors, thresholds, and operator controls.</div>}
        </aside>

      </section>

      <section id="hazard-ops-operations" className="hazard-ops-deck-card hazard-ops-operations-board">
        <div className="hazard-ops-card-head">
          <div>
            <span className="hazard-ops-eyebrow">Operations Deck</span>
            <strong>Queue, Watchlist, Movers, and Model Quality</strong>
            <p>Review one operational layer at a time so the page stays focused instead of forcing every secondary panel onto the screen at once.</p>
          </div>
          <span className="hazard-ops-count-pill">
            {selectedOpsTab === "watch"
              ? `${watchDeckHotspots.length} watch regions`
              : selectedOpsTab === "queue"
                ? `${queuePreview.length} queue alerts`
                : selectedOpsTab === "quality"
                  ? `${modelQualityRows.length} hazard models`
                  : `${accelerating.length + cooling.length} mover rows`}
          </span>
        </div>

        <div className="hazard-ops-deck-tabs is-ops">
          <button type="button" className={selectedOpsTab === "queue" ? "is-active" : ""} onClick={() => setSelectedOpsTab("queue")}>Alert Queue</button>
          <button type="button" className={selectedOpsTab === "watch" ? "is-active" : ""} onClick={() => setSelectedOpsTab("watch")}>Watch Deck</button>
          <button type="button" className={selectedOpsTab === "quality" ? "is-active" : ""} onClick={() => setSelectedOpsTab("quality")}>Model Quality</button>
          <button type="button" className={selectedOpsTab === "movers" ? "is-active" : ""} onClick={() => setSelectedOpsTab("movers")}>Movers</button>
        </div>

        <div className="hazard-ops-ops-deck-body">
          {selectedOpsTab === "watch" ? (
            <div className="hazard-ops-watchdeck-grid">
              {watchDeckHotspots.map((hotspot) => {
                const series = hotspotSeriesForWindow(hotspot, selectedWindow);
                const delta = deltaValue(series);
                return (
                  <button key={`${hotspot.hazard}-${hotspot.region}`} type="button" className={`hazard-ops-hotspot-card hazard-${hotspot.hazard} ${selectedHotspot?.region === hotspot.region && selectedHotspot?.hazard === hotspot.hazard ? "is-selected" : ""}`} onClick={() => setSelectedHotspot(hotspot)}>
                    <div className="hazard-ops-hotspot-head">
                      <div><strong>{hotspotLabel(hotspot)}</strong><small>{hotspotSecondaryLabel(hotspot)}</small></div>
                      <span>{hotspot.hazard.toUpperCase()}</span>
                    </div>
                    <div className="hazard-ops-sparkline"><svg viewBox="0 0 160 44" preserveAspectRatio="none"><path d={sparklinePath(series)} /></svg><span>{String(hotspot.activity_trend ?? "steady").toUpperCase()}</span></div>
                    <div className={`hazard-ops-delta is-${delta > 0.08 ? "up" : delta < -0.08 ? "down" : "flat"}`}><strong>{deltaLabel(delta)}</strong><span>{selectedWindow}</span></div>
                    <div className="hazard-ops-metrics"><span>Activity {Math.round((hotspot.hotspot_score ?? 0) * 100)}%</span><span>{metricPrimary(hotspot)}</span><span>{metricSecondary(hotspot)}</span></div>
                    <div className="hazard-ops-pill-group compact">{(hotspot.signal_sources ?? []).slice(0, 3).map((source) => <span key={source} className="hazard-ops-source-pill">{sourceFamilyLabel(source)}</span>)}</div>
                  </button>
                );
              })}
              {!watchDeckHotspots.length ? <div className="hazard-ops-empty">No hotspots available for this filter.</div> : null}
            </div>
          ) : selectedOpsTab === "queue" ? (
            <div className="hazard-ops-list">
              {queuePreview.map((item) => {
                const actionBase = `${item.hazard}:${item.region}`;
                return (
                  <article key={item.dedupe_key ?? actionBase} className={`hazard-ops-list-card hazard-${item.hazard}`}>
                    <div
                      className="hazard-ops-list-select"
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelectedHotspot(hotspotLookup.get(actionBase) ?? null)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedHotspot(hotspotLookup.get(actionBase) ?? null);
                        }
                      }}
                    >
                      <div className="hazard-ops-list-topline">
                        <strong>{item.region_name ?? item.display_label ?? item.region}</strong>
                        <span className={`hazard-ops-band-pill is-${priorityBandTone(item.priority_band)}`}>{item.priority_band.toUpperCase()}</span>
                      </div>
                      <span>{item.region_label ?? item.region}</span>
                      <span>{item.threshold_reason ?? "Threshold rule unavailable"}</span>
                    </div>
                    <div className="hazard-ops-list-meta">
                      <div className="hazard-ops-pill-group compact">{(item.signal_sources ?? []).slice(0, 4).map((source) => <span key={source} className="hazard-ops-source-pill">{sourceFamilyLabel(source)}</span>)}</div>
                      <div className="hazard-ops-queue-stats"><span>{Math.round((item.adjusted_activity ?? item.activity) * 100)}% adjusted</span><span>{formatOpsStatus(item.ops_state?.status)}</span></div>
                    </div>
                    <div className="hazard-ops-inline-actions">
                      {(["acknowledge", "snooze", "escalate", "false_positive"] as AlertActionKey[]).map((action) => {
                        const actionKey = `${action}:${item.dedupe_key ?? actionBase}`;
                        return <button key={action} type="button" className={`hazard-ops-inline-button action-${action}`} disabled={actionBusyKey === actionKey} onClick={() => void submitAlertAction(action, item)}>{actionBusyKey === actionKey ? "..." : formatOpsStatus(action)}</button>;
                      })}
                    </div>
                  </article>
                );
              })}
              {!queuePreview.length ? <div className="hazard-ops-empty compact">Queue is empty for this scope.</div> : null}
            </div>
          ) : selectedOpsTab === "quality" ? (
            <>
              <div className="hazard-ops-quality-summary-grid">
                <div><span>Precision</span><strong>{formatPercent(forecast?.backtest_summary?.overall?.precision_proxy ?? forecast?.stream_status?.backtest_precision_proxy ?? 0)}</strong></div>
                <div><span>False Positive Rate</span><strong>{formatPercent(forecast?.backtest_summary?.overall?.false_positive_rate ?? 0)}</strong></div>
                <div><span>Latency</span><strong>{Math.round(Number(forecast?.stream_status?.cycle_latency_ms ?? 0))} ms</strong></div>
                <div><span>Model Rows</span><strong>{Math.round(Number(forecast?.stream_status?.model_monitor_rows ?? 0))}</strong></div>
              </div>
              <div className="hazard-ops-quality-spotlight-grid">
                <article className="hazard-ops-quality-card">
                  <span>Strongest hazard</span>
                  <strong>{strongestModelRow ? hazardLabel(strongestModelRow.hazard) : "--"}</strong>
                  <p>
                    Precision {formatPercent(strongestModelRow?.precision ?? 0)} with average confidence{" "}
                    {formatPercent(strongestModelRow?.avgConfidence ?? 0)}.
                  </p>
                </article>
                <article className="hazard-ops-quality-card is-warning">
                  <span>Needs tuning</span>
                  <strong>{weakestModelRow ? hazardLabel(weakestModelRow.hazard) : "--"}</strong>
                  <p>
                    False positives {formatPercent(weakestModelRow?.falsePositiveRate ?? 0)} and average lead{" "}
                    {Math.round(weakestModelRow?.avgLead ?? 0)}h.
                  </p>
                </article>
                <article className="hazard-ops-quality-card">
                  <span>Backtest window</span>
                  <strong>{forecast?.backtest_summary?.window_days ?? 30} days</strong>
                  <p>{forecast?.backtest_summary?.overall?.evaluated_alerts ?? 0} evaluated alerts in the latest run.</p>
                </article>
              </div>
              <div className="hazard-ops-quality-list">
                {modelQualityRows.map((row) => (
                  <div key={row.hazard} className={`hazard-ops-quality-row hazard-${row.hazard}`}>
                    <strong>{hazardLabel(row.hazard)}</strong>
                    <span>Precision {formatPercent(row.precision)}</span>
                    <span>False + {formatPercent(row.falsePositiveRate)}</span>
                    <span>Lead {Math.round(row.avgLead)}h</span>
                    <span>Confidence {formatPercent(row.avgConfidence)}</span>
                  </div>
                ))}
              </div>
              <div className="hazard-ops-quality-calibration-grid">
                {calibrationRows.map((row) => (
                  <article key={`calibration:${row.hazard}`} className={`hazard-ops-quality-card is-${calibrationTone(row.status)}`}>
                    <div className="hazard-ops-quality-card__topline">
                      <strong>{hazardLabel(row.hazard)}</strong>
                      <span>{String(row.status).replace(/_/g, " ")}</span>
                    </div>
                    <p>{row.region} is the current calibration focus region.</p>
                    <div className="hazard-ops-pill-group compact">
                      <span className="hazard-ops-source-pill">Penalty {(row.penalty * 100).toFixed(1)} pts</span>
                      {(row.notes || []).map((note) => <span key={`${row.hazard}:${note}`} className="hazard-ops-source-pill">{note}</span>)}
                    </div>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <div className="hazard-ops-movers-grid">
              <article className="hazard-ops-mover-card">
                <div className="hazard-ops-card-head compact">
                  <div>
                    <span className="hazard-ops-eyebrow">Acceleration Feed</span>
                    <strong>Accelerating Fastest</strong>
                    <p>Regions rising fastest inside the selected time window.</p>
                  </div>
                </div>
                <div className="hazard-ops-list compact-list">
                  {accelerating.map((item) => <button key={`up-${item.hazard}-${item.region}`} type="button" className={`hazard-ops-list-item hazard-${item.hazard}`} onClick={() => setSelectedHotspot(hotspotLookup.get(`${item.hazard}:${item.region}`) ?? null)}><strong>{item.region_name ?? item.display_label ?? item.region}</strong><span>{item.region_label ?? item.region}</span><span>+{Math.round(item.delta * 100)} pts</span></button>)}
                  {!accelerating.length ? <div className="hazard-ops-empty compact">No rising movers for this scope.</div> : null}
                </div>
              </article>

              <article className="hazard-ops-mover-card">
                <div className="hazard-ops-card-head compact">
                  <div>
                    <span className="hazard-ops-eyebrow">Cooling Feed</span>
                    <strong>Cooling Fastest</strong>
                    <p>Regions de-escalating most aggressively in the chosen window.</p>
                  </div>
                </div>
                <div className="hazard-ops-list compact-list">
                  {cooling.map((item) => <button key={`down-${item.hazard}-${item.region}`} type="button" className={`hazard-ops-list-item hazard-${item.hazard}`} onClick={() => setSelectedHotspot(hotspotLookup.get(`${item.hazard}:${item.region}`) ?? null)}><strong>{item.region_name ?? item.display_label ?? item.region}</strong><span>{item.region_label ?? item.region}</span><span>{Math.round(item.delta * 100)} pts</span></button>)}
                  {!cooling.length ? <div className="hazard-ops-empty compact">No cooling movers for this scope.</div> : null}
                </div>
              </article>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
