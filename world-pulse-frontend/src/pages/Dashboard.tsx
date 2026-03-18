import { lazy, Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../components/futuristic-dashboard.css";
import "./Dashboard.css";
import ConsoleNavigation from "../components/ConsoleNavigation";
import {
  buildWebSocketAuthUrl,
  getCountryDrilldown,
  getLiveCommandFeed,
  getLatestGlobalFeatures,
  getRiskMap,
  getRiskMapCoverage,
  getTrustReliability,
  refreshRiskMapBatch,
  type CountryDrilldownData,
  type LiveCommandFeed,
  type IntelligenceFeedItem,
  type RiskMapCoverage,
  type RiskMapPoint,
  type TrustReliabilitySnapshot,
} from "../services/api";
import { getCountryWeatherByCoords, type CountryWeatherSnapshot } from "../services/weather";

const CountryDrilldown = lazy(() => import("../components/CountryDrilldown"));
const BrainModelViewer = lazy(() => import("../components/BrainModelViewer"));
const GlobalIntelligenceFeed = lazy(() => import("../components/GlobalIntelligenceFeed"));
const PriorityWatchlist = lazy(() => import("../components/PriorityWatchlist"));
const SignalIntegrityBoard = lazy(() => import("../components/SignalIntegrityBoard"));
const BehavioralAnalyticsPanel = lazy(() => import("../components/BehavioralAnalyticsPanel"));
const SystemEventStream = lazy(() => import("../components/SystemEventStream"));

type Features = {
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
  forecast_risk_score?: number;
  forecast_risk_delta?: number;
  forecast_confidence?: number;
  forecast_horizon_hours?: number;
  top_topics: string[];
  timestamp: string;
};

type GlobalDoc = {
  features: Features;
};

type Snapshot = {
  timestamp: string;
  riskScore: number;
  moodScore: number;
  moodConfidence: number;
  moodUncertainty: number;
  moodVerifiedCountries: number;
  moodEligibleCountries: number;
  moodUsedCountries: number;
  moodExcludedCountries: number;
  forecastRiskScore: number;
  forecastRiskDelta: number;
  forecastConfidence: number;
  forecastHorizonHours: number;
  features: Record<string, number>;
  topics: string[];
};

type ConnectionState = "connecting" | "connected" | "reconnecting" | "disconnected";
type PanelKey = "risk" | "map" | "stream";

const HISTORY_KEY = "wp_v3_history";
const MAX_HISTORY = 1200;
const GLOBAL_MAP_WORLD_SCALE = 1.12;
const GLOBAL_MAP_ROTATION_DEG_PER_SEC = 4;

const DRIVER_LABELS: Record<string, string> = {
  news_sentiment: "News Sentiment",
  gdelt_sentiment: "GDELT Sentiment",
  crypto_return: "Crypto Return",
  crypto_volatility: "Crypto Volatility",
  stock_return: "Stock Return",
  stock_volatility: "Stock Volatility",
  weather_anomaly: "Weather Anomaly",
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
  AFG: { lat: 33.9, lon: 67.7 },
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
  IRQ: { lat: 33.2, lon: 43.7 },
  QAT: { lat: 25.3, lon: 51.2 },
  ARE: { lat: 24.3, lon: 54.4 },
  KWT: { lat: 29.3, lon: 47.5 },
  KEN: { lat: -0.0, lon: 37.9 },
  ETH: { lat: 9.1, lon: 40.5 },
  GHA: { lat: 7.9, lon: -1.0 },
  MAR: { lat: 31.8, lon: -7.1 },
  TUN: { lat: 34.0, lon: 9.6 },
};

function resolveCountryFocus(country: string, clickLat?: number, clickLon?: number): { lat: number; lon: number } | null {
  if (Number.isFinite(clickLat) && Number.isFinite(clickLon)) {
    return { lat: Number(clickLat), lon: Number(clickLon) };
  }
  return COUNTRY_FOCUS_COORDS[country] ?? null;
}

function safeN(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeRisk(score: number): number {
  const clamped = Math.max(0, Math.min(100, safeN(score, 50)));
  return Number(clamped.toFixed(2));
}

function formatDriverLabel(feature: string): string {
  const known = DRIVER_LABELS[feature];
  if (known) return known;
  return feature
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function deriveThreatMeta(score: number): { label: string; tone: "stable" | "guarded" | "elevated" | "critical" } {
  if (score >= 75) return { label: "Critical", tone: "critical" };
  if (score >= 50) return { label: "Elevated", tone: "elevated" };
  if (score >= 25) return { label: "Guarded", tone: "guarded" };
  return { label: "Stable", tone: "stable" };
}

function deriveTrendMeta(delta: number): { label: string; tone: "up" | "down" | "stable" } {
  if (delta >= 0.35) return { label: "Rising", tone: "up" };
  if (delta <= -0.35) return { label: "Cooling", tone: "down" };
  return { label: "Stable", tone: "stable" };
}

function formatTelemetryTime(value?: string | null): string {
  if (!value) return "No recent update";
  const stamp = new Date(value);
  if (!Number.isFinite(stamp.getTime())) return "No recent update";
  return stamp.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function buildSnapshot(doc: GlobalDoc): Snapshot {
  const riskScore = normalizeRisk(doc.features.global_risk_score);
  const moodVerifiedCountries = Math.max(0, Math.round(safeN(doc.features.global_mood_verified_countries, 0)));
  const moodEligibleCountries = Math.max(
    0,
    Math.round(safeN(doc.features.global_mood_eligible_countries, moodVerifiedCountries))
  );
  const moodUsedCountries = Math.max(
    0,
    Math.round(
      safeN(
        doc.features.global_mood_used_countries,
        safeN(doc.features.global_mood_contributing_countries, moodEligibleCountries)
      )
    )
  );
  const moodExcludedCountries = Math.max(
    0,
    Math.round(safeN(doc.features.global_mood_excluded_countries, Math.max(moodEligibleCountries - moodUsedCountries, 0)))
  );

  return {
    timestamp: doc.features.timestamp ?? new Date().toISOString(),
    riskScore,
    moodScore: normalizeRisk(safeN(doc.features.global_mood_score, riskScore)),
    moodConfidence: Math.max(0, Math.min(1, safeN(doc.features.global_mood_confidence, 0))),
    moodUncertainty: Math.max(0, safeN(doc.features.global_mood_uncertainty, 18)),
    moodVerifiedCountries,
    moodEligibleCountries,
    moodUsedCountries,
    moodExcludedCountries,
    forecastRiskScore: normalizeRisk(safeN(doc.features.forecast_risk_score, riskScore)),
    forecastRiskDelta: safeN(doc.features.forecast_risk_delta),
    forecastConfidence: Math.max(0, Math.min(1, safeN(doc.features.forecast_confidence, 0.35))),
    forecastHorizonHours: Math.max(1, Math.round(safeN(doc.features.forecast_horizon_hours, 24))),
    features: {
      news_sentiment: safeN(doc.features.news_sentiment),
      gdelt_sentiment: safeN(doc.features.gdelt_sentiment),
      crypto_return: safeN(doc.features.crypto_return),
      crypto_volatility: safeN(doc.features.crypto_volatility),
      stock_return: safeN(doc.features.stock_return),
      stock_volatility: safeN(doc.features.stock_volatility),
      weather_anomaly: safeN(doc.features.weather_anomaly),
    },
    topics: Array.isArray(doc.features.top_topics) ? doc.features.top_topics : ["no data"],
  };
}

function staleFor(msSinceUpdate: number, thresholdMs: number): boolean {
  return msSinceUpdate > thresholdMs;
}

function coverageFromRows(rows: RiskMapPoint[]): RiskMapCoverage {
  const total = rows.length;
  const verified = rows.filter((row) => row.validated_today).length;
  const no_data = rows.filter((row) => row.data_quality === "synthetic" || row.data_quality === "unknown").length;
  const stale = rows.filter((row) => row.data_quality === "stale").length;
  return {
    total,
    verified,
    no_data,
    stale,
    remaining: Math.max(total - verified, 0),
    coverage_pct: total ? Number(((verified / total) * 100).toFixed(2)) : 0,
  };
}

function mergeRiskMapRows(rows: RiskMapPoint[], updates: Iterable<RiskMapPoint>): RiskMapPoint[] {
  const next = Array.isArray(rows) ? [...rows] : [];
  const indexByCountry = new Map<string, number>();

  next.forEach((row, idx) => {
    if (row?.country) indexByCountry.set(row.country, idx);
  });

  for (const update of updates) {
    if (!update?.country) continue;
    const idx = indexByCountry.get(update.country);
    const merged = { ...(idx !== undefined ? next[idx] : {}), ...update } as RiskMapPoint;
    if (idx !== undefined) {
      next[idx] = merged;
    } else {
      indexByCountry.set(update.country, next.length);
      next.push(merged);
    }
  }

  return next;
}

function describeDashboardError(error: unknown): string {
  const message = String((error as { message?: string } | null)?.message || "Failed to refresh dashboard feed");
  const status = Number((error as { response?: { status?: number } } | null)?.response?.status || 0);

  if (message.includes("timeout") || (error as { code?: string } | null)?.code === "ECONNABORTED") {
    return "Dashboard request timed out. The backend is responding too slowly.";
  }
  if (status === 429) {
    return "Dashboard refresh is being rate-limited. Retry in a moment.";
  }
  if (status >= 500) {
    return "Dashboard service is temporarily unavailable.";
  }
  if (message === "Network Error") {
    return "Dashboard cannot reach the backend service.";
  }

  return message;
}

function DeferredPanelPlaceholder({ label }: { label: string }) {
  return (
    <div className="prediction-empty">
      <p>{label}</p>
    </div>
  );
}

export default function Dashboard() {
  const [history, setHistory] = useState<Snapshot[]>(() => readJson(HISTORY_KEY, [] as Snapshot[]));
  const [liveFeed, setLiveFeed] = useState<LiveCommandFeed>({
    incidents: [],
    ingestionHeartbeatSec: 0,
    modelDrift: 0,
    lastUpdated: new Date().toISOString(),
  });
  const [riskMap, setRiskMap] = useState<RiskMapPoint[]>([]);
  const [riskCoverage, setRiskCoverage] = useState<RiskMapCoverage>({ total: 0, verified: 0, no_data: 0, stale: 0, remaining: 0, coverage_pct: 0 });
  const [trustSnapshot, setTrustSnapshot] = useState<TrustReliabilitySnapshot | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [fpsLow, setFpsLow] = useState(false);
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  
  useEffect(() => {
    selectedCountryRef.current = selectedCountry;
  }, [selectedCountry]);

  useEffect(() => {
    if (!selectedCountry) {
      setSelectedCountryFocus(null);
      setSelectedCountryNews([]);
      setSelectedCountryWeather(null);
      setCountryWeatherError("");
    }
  }, [selectedCountry]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setShowDeferredPanels(true);
    }, 250);
    return () => window.clearTimeout(timer);
  }, []);
  
  const [countryData, setCountryData] = useState<CountryDrilldownData | null>(null);

  const [countryLoading, setCountryLoading] = useState(false);
  const [mapHover, setMapHover] = useState<{ country: string; risk: number; quality: string } | null>(null);
  const [selectedCountryNews, setSelectedCountryNews] = useState<IntelligenceFeedItem[]>([]);
  const [selectedCountryFocus, setSelectedCountryFocus] = useState<{ lat: number; lon: number } | null>(null);
  const [selectedCountryWeather, setSelectedCountryWeather] = useState<CountryWeatherSnapshot | null>(null);
  const [countryWeatherLoading, setCountryWeatherLoading] = useState(false);
  const [countryWeatherError, setCountryWeatherError] = useState("");
  const [errorText, setErrorText] = useState("");
  const [refreshingMap, setRefreshingMap] = useState(false);

  const [retries, setRetries] = useState(0);
  const [sentinelEnabled, setSentinelEnabled] = useState(true);
  const [showDeferredPanels, setShowDeferredPanels] = useState(false);
  const [recentSocketUpdates, setRecentSocketUpdates] = useState<Array<{ country: string; risk: number | null; timestamp: string; quality: string }>>([]);
  const [streamHeight, setStreamHeight] = useState<number | null>(null);

  const cacheRef = useRef<{
    liveFeed: { data: LiveCommandFeed | null; timestamp: number; ttl: number };
    riskMap: { data: RiskMapPoint[] | null; timestamp: number; ttl: number };
    riskCoverage: { data: RiskMapCoverage | null; timestamp: number; ttl: number };
    global: { data: any | null; timestamp: number; ttl: number };
    trust: { data: TrustReliabilitySnapshot | null; timestamp: number; ttl: number };
  }>({
    liveFeed: { data: null, timestamp: 0, ttl: 3000 },
    riskMap: { data: null, timestamp: 0, ttl: 5000 },
    riskCoverage: { data: null, timestamp: 0, ttl: 5000 },
    global: { data: null, timestamp: 0, ttl: 2000 },
    trust: { data: null, timestamp: 0, ttl: 5000 },
  });

  const inFlightRef = useRef<Set<string>>(new Set());

  const panelUpdated = useRef<Record<PanelKey, number>>({
    risk: Date.now(),
    map: Date.now(),
    stream: Date.now(),
  });
  
  const retriesRef = useRef(0);
  const mapRef = useRef<HTMLDivElement | null>(null);
  const leftColumnRef = useRef<HTMLDivElement | null>(null);
  const streamHostRef = useRef<HTMLElement | null>(null);
  const mapMounted = useRef(false);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);
  const rotationRef = useRef<number>(0);
  const rotationRafRef = useRef<number | null>(null);
  const isRotatingRef = useRef<boolean>(false);
  const selectedCountryRef = useRef<string | null>(null);
  const weatherCacheRef = useRef<Record<string, CountryWeatherSnapshot>>({});
  const initialRiskMapLoadedRef = useRef(false);
  const pendingRiskMapUpdatesRef = useRef<Map<string, RiskMapPoint>>(new Map());
  const pendingRiskMapFlushTimerRef = useRef<number | null>(null);

  const consumePendingRiskMapUpdates = (rows: RiskMapPoint[]) => {
    if (!pendingRiskMapUpdatesRef.current.size) return rows;
    const queuedUpdates = Array.from(pendingRiskMapUpdatesRef.current.values());
    pendingRiskMapUpdatesRef.current.clear();
    return mergeRiskMapRows(rows, queuedUpdates);
  };

  const flushQueuedRiskMapUpdates = () => {
    if (pendingRiskMapFlushTimerRef.current) {
      window.clearTimeout(pendingRiskMapFlushTimerRef.current);
      pendingRiskMapFlushTimerRef.current = null;
    }
    if (!pendingRiskMapUpdatesRef.current.size) return;

    setRiskMap((prev) => {
      const currentRows = Array.isArray(prev) ? prev : [];
      const mergedRows = consumePendingRiskMapUpdates(currentRows);
      setRiskCoverage((current) => ({
        ...coverageFromRows(mergedRows),
        latest_validation: current?.latest_validation,
      }));
      panelUpdated.current.map = Date.now();
      return mergedRows;
    });
  };

  const queueRiskMapUpdate = (update: RiskMapPoint) => {
    pendingRiskMapUpdatesRef.current.set(update.country, update);
    setRecentSocketUpdates((prev) => [{
      country: update.country,
      risk: typeof update.risk === "number" ? update.risk : null,
      timestamp: update.timestamp || update.feature_timestamp || new Date().toISOString(),
      quality: update.data_quality || (update.validated_today ? "verified" : "unknown"),
    }, ...prev].slice(0, 8));
    if (!initialRiskMapLoadedRef.current || pendingRiskMapFlushTimerRef.current) return;
    pendingRiskMapFlushTimerRef.current = window.setTimeout(flushQueuedRiskMapUpdates, 150);
  };

  const riskMapRows = Array.isArray(riskMap) ? riskMap : [];
  const coverageState = riskCoverage ?? { total: 0, verified: 0, no_data: 0, stale: 0, remaining: 0, coverage_pct: 0 };
  const liveFeedState = liveFeed ?? {
    incidents: [],
    ingestionHeartbeatSec: 0,
    modelDrift: 0,
    lastUpdated: new Date().toISOString(),
  };

  const active = history[history.length - 1] ?? null;
  const previous = history.length > 1 ? history[history.length - 2] : null;
  const riskDelta = active && previous ? active.riskScore - previous.riskScore : 0;
  const verifiedRiskMap = useMemo(() => riskMapRows.filter((row): row is RiskMapPoint & { risk: number } => Boolean(row.validated_today) && typeof row.risk === "number"), [riskMapRows]);
  const unverifiedRiskMap = useMemo(() => riskMapRows.filter((row) => !row.validated_today), [riskMapRows]);
  const selectedCountryFeedItems = useMemo(
    () => (selectedCountry ? selectedCountryNews.filter((item) => item.country === selectedCountry) : []),
    [selectedCountryNews, selectedCountry]
  );
  const effectiveCountryFocus = useMemo(
    () => (selectedCountry ? selectedCountryFocus ?? COUNTRY_FOCUS_COORDS[selectedCountry] ?? null : null),
    [selectedCountry, selectedCountryFocus]
  );
  const mapBeaconPoints = useMemo(() => {
    if (!selectedCountry || !selectedCountryFeedItems.length) {
      return [] as Array<{ lat?: number; lon?: number; headline: string; source: string }>;
    }

    return selectedCountryFeedItems.slice(0, 5).map((item, index) => {
      if (!effectiveCountryFocus) {
        return { headline: item.headline, source: item.source };
      }
      const phase = (index + 1) * 1.618;
      const latOffset = Math.sin(phase * 7.1) * 1.05;
      const lonOffset = Math.cos(phase * 5.3) * 1.35;
      return {
        lat: Math.max(-85, Math.min(85, effectiveCountryFocus.lat + latOffset)),
        lon: Math.max(-180, Math.min(180, effectiveCountryFocus.lon + lonOffset)),
        headline: item.headline,
        source: item.source,
      };
    });
  }, [selectedCountry, selectedCountryFeedItems, effectiveCountryFocus]);
  const weatherRainStrength = selectedCountryWeather
    ? Math.min(1, Math.max(safeN(selectedCountryWeather.rainMm), safeN(selectedCountryWeather.precipitationMm)) / 6)
    : 0;
  const weatherWindStrength = selectedCountryWeather
    ? Math.min(1, safeN(selectedCountryWeather.windSpeedKmh) / 55)
    : 0;
  const showRainAnimation = Boolean(selectedCountry && weatherRainStrength > 0);
  const showWindAnimation = Boolean(selectedCountry);
  const rainDropCount = Math.max(12, Math.min(72, Math.round(12 + weatherRainStrength * 60)));
  const windLineCount = Math.max(18, Math.min(40, Math.round(18 + weatherWindStrength * 22)));
  const topTopic = active?.topics?.find((topic) => topic && topic !== "no data") ?? "No dominant topic";
  const validationSummary = coverageState.latest_validation;
  const verifiedCoverageLabel = `${coverageState.verified} / ${coverageState.total || riskMapRows.length || 233}`;
  const globalRiskScore = active?.riskScore ?? 50;
  const globalMoodScore = active?.moodScore ?? 50;
  const globalMoodConfidence = active?.moodConfidence ?? Math.min(1, coverageState.coverage_pct / 100);
  const globalMoodUncertainty = active?.moodUncertainty ?? 18;
  const globalMoodEligibleCountries = active?.moodEligibleCountries ?? active?.moodVerifiedCountries ?? coverageState.verified;
  const globalMoodUsedCountries = active?.moodUsedCountries ?? globalMoodEligibleCountries;
  const globalMoodExcludedCountries = active?.moodExcludedCountries ?? Math.max(globalMoodEligibleCountries - globalMoodUsedCountries, 0);
  const globalMoodCountrySummary = `${globalMoodEligibleCountries} eligible, ${globalMoodUsedCountries} used, ${globalMoodExcludedCountries} excluded`;
  const forecastRiskScore = active?.forecastRiskScore ?? globalRiskScore;
  const forecastRiskDelta = active?.forecastRiskDelta ?? 0;
  const forecastConfidence = active?.forecastConfidence ?? 0.35;
  const forecastHorizonHours = active?.forecastHorizonHours ?? 24;
  const telemetryThreat = deriveThreatMeta(globalRiskScore);
  const telemetryTrend = deriveTrendMeta(riskDelta);
  const telemetryDrivers = (() => {
    const countryDrivers = countryData?.drivers?.length
      ? [...countryData.drivers]
          .sort((left, right) => Math.abs(right.contribution) - Math.abs(left.contribution))
          .map((driver) => formatDriverLabel(driver.feature))
      : [];
    const topicDrivers = topTopic !== "No dominant topic" ? [topTopic] : [];
    const globalDrivers = active?.features
      ? Object.entries(active.features)
          .sort((left, right) => Math.abs(right[1]) - Math.abs(left[1]))
          .map(([feature]) => formatDriverLabel(feature))
      : [];
    const merged = Array.from(new Set([...countryDrivers, ...topicDrivers, ...globalDrivers])).filter(Boolean);
    return merged.length ? merged.slice(0, 3) : ["Awaiting live signals"];
  })();
  const dockConnectionLabel = `${connectionState.charAt(0).toUpperCase()}${connectionState.slice(1)}`;
  const liveSignalCount = coverageState.verified || verifiedRiskMap.length || liveFeedState.incidents?.length || 0;
  const telemetryStatusLine = `${dockConnectionLabel} - ${liveSignalCount} verified signals - Updated ${formatTelemetryTime(liveFeedState.lastUpdated)}`;
  const trustFreshness = (trustSnapshot?.data_freshness ?? {}) as Record<string, unknown>;
  const trustConfidence = (trustSnapshot?.confidence ?? {}) as Record<string, unknown>;
  const qualityGate = (trustSnapshot as Record<string, unknown> | null)?.quality_gate as Record<string, unknown> | undefined;
  const qualityGateMetrics = (qualityGate?.metrics ?? {}) as Record<string, unknown>;
  const qualityGateActive = Boolean(qualityGate?.active);
  const qualityGateRollout = (qualityGate?.rollout ?? {}) as Record<string, unknown>;
  const qualityGateShadowMode = Boolean(qualityGateRollout.shadow_mode);
  const qualityGateDisplayActive = qualityGateActive && !qualityGateShadowMode;
  const qualityGateMessage = typeof qualityGate?.message === "string"
    ? qualityGate.message
    : (qualityGateActive ? "Reliability advisory" : "Coverage healthy");
  const qualityGateReasons = Array.isArray(qualityGate?.reasons) ? qualityGate.reasons.filter((x): x is string => typeof x === "string") : [];
  const qualityGateFreshnessPct = (safeN(qualityGateMetrics.freshness_ratio, 0) * 100).toFixed(0);
  const qualityGateDetail = qualityGateActive
    ? (qualityGateShadowMode
      ? "Shadow mode active: monitoring reliability; headline scores remain visible."
      : (qualityGateReasons.join(" | ") || "Global metrics downweighted due to insufficient reliability."))
    : "All quality thresholds are currently passing.";
  const staleSources = safeN(trustFreshness.stale_count, 0);
  const freshSources = safeN(trustFreshness.fresh_count, 0);
  const staleCoreSources = safeN(trustFreshness.stale_core_count, 0);
  const staleSupportingSources = safeN(trustFreshness.stale_supporting_count, Math.max(staleSources - staleCoreSources, 0));
  const freshnessOverallStatus = String(trustFreshness.overall_status ?? "healthy").toLowerCase();
  const reliabilityStatus = qualityGateActive
    ? "Degraded"
    : freshnessOverallStatus === "degraded"
      ? "Monitoring"
      : "Healthy";
  const moodUncertaintyDisplay = safeN(trustConfidence.global_mood_uncertainty, globalMoodUncertainty);
  const forecastConfidenceDisplay = Math.max(0, Math.min(1, safeN(trustConfidence.forecast_confidence, forecastConfidence)));
  const systemEventPackets = useMemo(() => {
    const packets: Array<{ id: string; timestamp: string; category: string; source: string; detail: string; status: string }> = [];
    const pushPacket = (packet: { id: string; timestamp?: string | null; category: string; source: string; detail: string; status: string }) => {
      packets.push({
        ...packet,
        timestamp: packet.timestamp || new Date().toISOString(),
      });
    };

    pushPacket({
      id: `ingestion-${liveFeedState.lastUpdated}`,
      timestamp: liveFeedState.lastUpdated,
      category: "Ingestion event",
      source: "Global node",
      detail: `${liveFeedState.incidents?.length ?? 0} incidents ingested, heartbeat ${liveFeedState.ingestionHeartbeatSec.toFixed(1)}s`,
      status: connectionState,
    });

    pushPacket({
      id: `model-${active?.timestamp ?? liveFeedState.lastUpdated}`,
      timestamp: active?.timestamp ?? liveFeedState.lastUpdated,
      category: "Model refresh",
      source: "Behavior model",
      detail: `Global risk ${globalRiskScore.toFixed(1)} / 100, forecast ${forecastRiskScore.toFixed(1)} / 100`,
      status: "Updated",
    });

    pushPacket({
      id: `validation-${validationSummary?.status ?? "pending"}`,
      timestamp: liveFeedState.lastUpdated,
      category: "Validation checkpoint",
      source: "Validation pipeline",
      detail: validationSummary?.sample_count
        ? `${validationSummary.status ?? "pending"} across ${validationSummary.sample_count} benchmark rows`
        : `Validation ${validationSummary?.status ?? "pending"}`,
      status: validationSummary?.status ?? "pending",
    });

    pushPacket({
      id: `pipeline-${qualityGateMessage}`,
      timestamp: trustSnapshot?.generated_at ?? liveFeedState.lastUpdated,
      category: "Pipeline status packet",
      source: "Reliability gate",
      detail: `${qualityGateMessage}. Fresh ${freshSources} / stale ${staleSources}${staleSupportingSources > 0 && staleCoreSources === 0 ? ` (${staleSupportingSources} supporting)` : ""}.`,
      status: reliabilityStatus,
    });

    Object.entries((trustSnapshot?.latest_ingestion ?? {}) as Record<string, unknown>)
      .slice(0, 4)
      .forEach(([source, value], index) => {
        pushPacket({
          id: `source-${source}-${index}`,
          timestamp: trustSnapshot?.generated_at ?? liveFeedState.lastUpdated,
          category: "Feed source update",
          source,
          detail: typeof value === "string" ? value : JSON.stringify(value),
          status: "Refreshed",
        });
      });

    recentSocketUpdates.slice(0, 4).forEach((update, index) => {
      pushPacket({
        id: `socket-${update.country}-${update.timestamp}-${index}`,
        timestamp: update.timestamp,
        category: "Websocket country update",
        source: update.country,
        detail: `Risk ${typeof update.risk === "number" ? update.risk.toFixed(1) : "n/a"} (${update.quality})`,
        status: "Streaming",
      });
    });

    return packets
      .sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime())
      .slice(0, 12);
  }, [
    active?.timestamp,
    connectionState,
    forecastRiskScore,
    freshSources,
    globalRiskScore,
    liveFeedState.incidents,
    liveFeedState.ingestionHeartbeatSec,
    liveFeedState.lastUpdated,
    qualityGateMessage,
    recentSocketUpdates,
    reliabilityStatus,
    staleSources,
    trustSnapshot?.generated_at,
    trustSnapshot?.latest_ingestion,
    validationSummary,
  ]);
  
  const panelStale = useMemo(() => {
    const now = Date.now();
    return {
      risk: staleFor(now - panelUpdated.current.risk, 12000),
      map: staleFor(now - panelUpdated.current.map, 12000),
      stream: staleFor(now - panelUpdated.current.stream, 12000),
    };
  }, [history.length, riskMapRows.length, coverageState.verified, recentSocketUpdates.length]);

  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-MAX_HISTORY)));
  }, [history]);

  useEffect(() => {
    let raf = 0;
    let prev = performance.now();
    let frames = 0;
    let acc = 0;
    const loop = (now: number) => {
      frames += 1;
      acc += now - prev;
      prev = now;
      if (acc >= 1000) {
        setFpsLow(frames < 28);
        frames = 0;
        acc = 0;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    let stop = false;
    let timer = 0;
    
    const isCacheValid = (key: keyof typeof cacheRef.current) => {
      const cache = cacheRef.current[key];
      return cache.data && (Date.now() - cache.timestamp) < cache.ttl;
    };

    const getCachedOrFetch = async <T,>(
      key: keyof typeof cacheRef.current,
      fetchFn: () => Promise<T>
    ): Promise<T> => {
      if (isCacheValid(key)) {
        return cacheRef.current[key].data as T;
      }

      if (inFlightRef.current.has(key)) {
        while (inFlightRef.current.has(key) && !stop) {
          await new Promise(r => setTimeout(r, 50));
        }
        if (stop) throw new Error("Stopped");
        const cachedAfterWait = cacheRef.current[key].data;
        if (cachedAfterWait == null) {
          throw new Error(`Failed to load ${String(key)}`);
        }
        return cachedAfterWait as T;
      }

      inFlightRef.current.add(key);
      try {
        const data = await fetchFn();
        cacheRef.current[key].data = data as any;
        cacheRef.current[key].timestamp = Date.now();
        return data;
      } finally {
        inFlightRef.current.delete(key);
      }
    };

    const pull = async () => {
      if (stop) return;
      setConnectionState(retriesRef.current > 0 ? "reconnecting" : "connecting");
      try {
        const [liveResult, mapRowsResult, coverageResult, globalResult, trustResult] = await Promise.allSettled([
          getCachedOrFetch("liveFeed", getLiveCommandFeed),
          getCachedOrFetch("riskMap", getRiskMap),
          getCachedOrFetch("riskCoverage", getRiskMapCoverage),
          getCachedOrFetch("global", getLatestGlobalFeatures),
          getCachedOrFetch("trust", () => getTrustReliability("online")),
        ]);

        const live = liveResult.status === "fulfilled"
          ? liveResult.value
          : { incidents: [], ingestionHeartbeatSec: 0, modelDrift: 0, lastUpdated: new Date().toISOString() };
        const mapRows = mapRowsResult.status === "fulfilled" ? mapRowsResult.value : [];
        const coverage = coverageResult.status === "fulfilled"
          ? coverageResult.value
          : { total: 0, verified: 0, no_data: 0, stale: 0, remaining: 0, coverage_pct: 0 };
        const nextMapRows = consumePendingRiskMapUpdates(Array.isArray(mapRows) ? mapRows : []);
        if (mapRowsResult.status === "fulfilled" || nextMapRows.length) {
          initialRiskMapLoadedRef.current = true;
        }
        const global = globalResult.status === "fulfilled" ? globalResult.value : null;
        const trust = trustResult.status === "fulfilled" ? trustResult.value : null;
        const features = global?.features;

        if (features) {
          const snap = buildSnapshot({ features } as GlobalDoc);
          setHistory((prev) => {
            const last = prev[prev.length - 1];
            if (last?.timestamp === snap.timestamp) {
              const next = [...prev];
              next[next.length - 1] = snap;
              return next;
            }
            return [...prev, snap].slice(-MAX_HISTORY);
          });
          panelUpdated.current.risk = Date.now();
        }

        setLiveFeed(live);
        setRiskMap(nextMapRows);
        setRiskCoverage({
          ...coverageFromRows(nextMapRows),
          latest_validation: coverage.latest_validation,
        });
        setTrustSnapshot(trust);
        panelUpdated.current.map = Date.now();
        panelUpdated.current.stream = Date.now();
        setErrorText("");
        retriesRef.current = 0;
        setRetries(0);
        setConnectionState("connected");
      } catch (e: any) {
        retriesRef.current += 1;
        setRetries(retriesRef.current);
        setConnectionState(retriesRef.current > 3 ? "disconnected" : "reconnecting");
        setErrorText(describeDashboardError(e));
        
        if (e?.response?.status === 429) {
          cacheRef.current.liveFeed.timestamp = 0;
          cacheRef.current.riskMap.timestamp = 0;
          cacheRef.current.riskCoverage.timestamp = 0;
          cacheRef.current.global.timestamp = 0;
          cacheRef.current.trust.timestamp = 0;
        }
      } finally {
        const baseDelay = retriesRef.current > 0 ? Math.min(15000, 2000 * (retriesRef.current + 1)) : 3000;
        const jitter = Math.random() * 500;
        timer = window.setTimeout(pull, baseDelay + jitter);
      }
    };
    
    pull();
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, []);

  useLayoutEffect(() => {
    const leftEl = leftColumnRef.current;
    const hostEl = streamHostRef.current;
    if (!leftEl || !hostEl) return;

    let frame = 0;
    const syncHeight = () => {
      if (frame) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const leftRect = leftEl.getBoundingClientRect();
        const hostRect = hostEl.getBoundingClientRect();
        const next = Math.max(280, Math.round(leftRect.bottom - hostRect.top));
        setStreamHeight((prev) => (prev === next ? prev : next));
      });
    };

    syncHeight();
    const observer = new ResizeObserver(syncHeight);
    observer.observe(leftEl);
    observer.observe(hostEl);
    window.addEventListener("resize", syncHeight);

    return () => {
      if (frame) cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", syncHeight);
    };
  }, [showDeferredPanels, selectedCountry, selectedCountryNews.length, recentSocketUpdates.length, history.length]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let connectTimer = 0;
    let retryTimer = 0;
    let closed = false;

    const connect = () => {
      if (closed) return;
      try {
        const wsUrl = buildWebSocketAuthUrl("/ws/country-risk-map");
        socket = new WebSocket(wsUrl);
      } catch {
        retryTimer = window.setTimeout(connect, 3000);
        return;
      }

      socket.onmessage = (event) => {
        try {
          const update = JSON.parse(event.data) as RiskMapPoint;
          if (!update?.country) return;
          queueRiskMapUpdate(update);
        } catch {
          // ignore malformed websocket payloads
        }
      };

      socket.onclose = () => {
        if (closed) return;
        retryTimer = window.setTimeout(connect, 3000);
      };

      socket.onerror = () => {
        // Let the browser/socket lifecycle handle failed connection attempts.
      };
    };

    // Delay the first connect so React StrictMode's dev-only mount/unmount cycle
    // can cancel it before a socket is opened and immediately closed.
    connectTimer = window.setTimeout(connect, 0);
    return () => {
      closed = true;
      window.clearTimeout(connectTimer);
      window.clearTimeout(retryTimer);
      if (pendingRiskMapFlushTimerRef.current) {
        window.clearTimeout(pendingRiskMapFlushTimerRef.current);
        pendingRiskMapFlushTimerRef.current = null;
      }
      pendingRiskMapUpdatesRef.current.clear();
      try { socket?.close(); } catch {}
    };
  }, []);

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
        const selectedRiskRow = riskMapRows.find((row) => row.country === selectedCountry) ?? null;
        const selectedRiskValue = normalizeRisk(selectedRiskRow?.risk ?? 0);

        const traces = selectedCountry
          ? [
              {
                type: "choropleth",
                locationmode: "ISO-3",
                locations: [selectedCountry],
                z: [selectedRiskValue],
                zmin: 0,
                zmax: 100,
                colorscale: [
                  [0, "#22c55e"],
                  [0.4, "#facc15"],
                  [0.7, "#fb923c"],
                  [1, "#ef4444"],
                ],
                hovertemplate: "%{location}<br>Risk: %{z:.1f}<extra></extra>",
                marker: {
                  line: { color: "#ff2d55", width: 2.6 },
                },
                showscale: false,
              },
            ] as any
          : riskMapRows.length
            ? [
                {
                  type: "choropleth",
                  locationmode: "ISO-3",
                  locations: unverifiedRiskMap.map((r) => r.country),
                  z: unverifiedRiskMap.map(() => 1),
                  zmin: 0,
                  zmax: 1,
                  colorscale: [
                    [0, "#334155"],
                    [1, "#64748b"],
                  ],
                  customdata: unverifiedRiskMap.map((r) => [r.data_quality ?? "unknown"]),
                  hovertemplate: "%{location}<br>Status: %{customdata[0]}<br>No verified same-day risk yet<extra></extra>",
                  showscale: false,
                },
                {
                  type: "choropleth",
                  locationmode: "ISO-3",
                  locations: verifiedRiskMap.map((r) => r.country),
                  z: verifiedRiskMap.map((r) => normalizeRisk(r.risk ?? 0)),
                  zmin: 0,
                  zmax: 100,
                  colorscale: [
                    [0, "#22c55e"],
                    [0.4, "#facc15"],
                    [0.7, "#fb923c"],
                    [1, "#ef4444"],
                  ],
                  customdata: verifiedRiskMap.map((r) => [r.data_quality ?? "verified"]),
                  hovertemplate: "%{location}<br>Risk: %{z:.1f}<br>Status: %{customdata[0]}<extra></extra>",
                  showscale: false,
                },
              ] as any
            : [
                {
                  type: "scattergeo",
                  lon: [],
                  lat: [],
                  mode: "markers",
                  hoverinfo: "skip",
                  showlegend: false,
                },
              ] as any;
        if (selectedCountry) {
          traces.push({
            type: "choropleth",
            locationmode: "ISO-3",
            locations: [selectedCountry],
            z: [1],
            zmin: 0,
            zmax: 1,
            colorscale: [
              [0, "rgba(0,0,0,0)"],
              [1, "rgba(0,0,0,0)"],
            ],
            marker: {
              line: { color: "#ff2d55", width: 2.6 },
            },
            hovertemplate: "%{location}<br>Selected country focus<extra></extra>",
            showscale: false,
          });
        }

        if (selectedCountry && mapBeaconPoints.length) {
          traces.push({
            type: "scattergeo",
            mode: "markers",
            ...(effectiveCountryFocus
              ? {
                  lon: mapBeaconPoints.map((point) => point.lon),
                  lat: mapBeaconPoints.map((point) => point.lat),
                }
              : {
                  locationmode: "ISO-3",
                  locations: mapBeaconPoints.map(() => selectedCountry),
                }),
            text: mapBeaconPoints.map((point) => `${point.headline}<br>${point.source}`),
            hovertemplate: "<b>News Beacon</b><br>%{text}<extra></extra>",
            marker: {
              size: 24,
              color: "rgba(255,45,85,0.22)",
              line: { color: "rgba(255,71,120,0.5)", width: 1 },
            },
            showlegend: false,
          });
          traces.push({
            type: "scattergeo",
            mode: "markers",
            ...(effectiveCountryFocus
              ? {
                  lon: mapBeaconPoints.map((point) => point.lon),
                  lat: mapBeaconPoints.map((point) => point.lat),
                }
              : {
                  locationmode: "ISO-3",
                  locations: mapBeaconPoints.map(() => selectedCountry),
                }),
            text: mapBeaconPoints.map((point) => `${point.headline}<br>${point.source}`),
            hovertemplate: "<b>News Beacon</b><br>%{text}<extra></extra>",
            marker: {
              size: 9,
              color: "#ff2d55",
              line: { color: "#ffd2dd", width: 1.2 },
              symbol: "circle",
            },
            showlegend: false,
          });
        }
        await Plotly.react(
          mapRef.current,
          traces,
          {
            margin: { l: 0, r: 0, b: 0, t: 0 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            uirevision: selectedCountry ? `country-focus-${selectedCountry}` : "global-behavior-map",
            geo: {
              domain: { x: [0, 1], y: [0, 1] },
              projection: selectedCountry
                ? { type: "mercator", scale: 1 }
                : {
                    type: "natural earth",
                    scale: GLOBAL_MAP_WORLD_SCALE,
                    rotation: { lon: rotationRef.current, lat: 0, roll: 0 },
                  },
              fitbounds: selectedCountry ? "locations" : false,
              center: effectiveCountryFocus ? { lon: effectiveCountryFocus.lon, lat: effectiveCountryFocus.lat } : undefined,
              lonaxis: effectiveCountryFocus ? { range: [effectiveCountryFocus.lon - 18, effectiveCountryFocus.lon + 18] } : undefined,
              lataxis: effectiveCountryFocus ? { range: [effectiveCountryFocus.lat - 12, effectiveCountryFocus.lat + 12] } : undefined,
              showframe: false,
              bgcolor: "rgba(0,0,0,0)",
              showland: true,
              landcolor: "rgba(51,65,85,0.45)",
              showcountries: true,
              countrycolor: "rgba(148,163,184,0.22)",
              coastlinecolor: "rgba(148,163,184,0.15)",
            },
              annotations: riskMapRows.length ? [] : [{
                text: "No live country risk data yet",
                x: 0.5,
                y: 0.02,
                xref: "paper",
                yref: "paper",
                showarrow: false,
                font: { color: "#94a3b8", size: 12 },
              }],
          } as any,
          { displayModeBar: false, responsive: true },
        );

        if (!mapMounted.current) {
          mapMounted.current = true;
          // Start auto-rotation once map is mounted
          if (plotlyRef.current && !selectedCountry) {
            startAutoRotation(plotlyRef.current);
          }
          (mapRef.current as any).on?.("plotly_hover", (e: any) => {

            const p = e?.points?.[0];
            if (!p) return;
            const quality = String(p.customdata?.[0] ?? "unknown");
            setMapHover({ country: String(p.location), risk: Number(p.z), quality });
          });
          (mapRef.current as any).on?.("plotly_click", (e: any) => {
            const p = e?.points?.[0];
            if (!p?.location) return;
            const country = String(p.location);
            setSelectedCountry(country);
            const lat = Number(p.lat);
            const lon = Number(p.lon);
            setSelectedCountryFocus(resolveCountryFocus(country, lat, lon));
          });
          (mapRef.current as any).on?.("plotly_unhover", () => setMapHover(null));
        }
      } catch {
        setErrorText("Unable to render map");
      }
    };
    
    drawMap();
    return () => {
      stopped = true;
    };
  }, [verifiedRiskMap, unverifiedRiskMap, selectedCountry, selectedCountryFocus, effectiveCountryFocus, mapBeaconPoints]);

  const startAutoRotation = (Plotly: any) => {
    if (isRotatingRef.current || !mapRef.current) return;
    isRotatingRef.current = true;
    let lastTick: number | null = null;

    const rotate = (timestamp: number) => {
      if (!isRotatingRef.current || !mapRef.current || selectedCountryRef.current) return;
      if (lastTick === null) {
        lastTick = timestamp;
      }
      const elapsedMs = Math.min(timestamp - lastTick, 64);
      lastTick = timestamp;
      rotationRef.current = (rotationRef.current + ((elapsedMs / 1000) * GLOBAL_MAP_ROTATION_DEG_PER_SEC)) % 360;

      Plotly.relayout(mapRef.current, {
        "geo.projection.rotation.lon": rotationRef.current,
        "geo.projection.scale": GLOBAL_MAP_WORLD_SCALE,
      }).catch(() => {});
      rotationRafRef.current = requestAnimationFrame(rotate);
    };
    rotationRafRef.current = requestAnimationFrame(rotate);
  };

  const stopAutoRotation = () => {
    isRotatingRef.current = false;
    if (rotationRafRef.current) {
      cancelAnimationFrame(rotationRafRef.current);
      rotationRafRef.current = null;
    }
  };
  useEffect(() => {
    if (!mapMounted.current || !plotlyRef.current) return;
    if (selectedCountry) {
      stopAutoRotation();
    } else {
      startAutoRotation(plotlyRef.current);
    }
    return () => {
      stopAutoRotation();
    };
  }, [selectedCountry, riskMapRows.length]);


  useEffect(() => {
    if (!selectedCountry) return;
    let closed = false;
    setCountryLoading(true);
    
    getCountryDrilldown(selectedCountry)
      .then((data) => {
        if (closed) return;
        setCountryData(data);
        panelUpdated.current.map = Date.now();
      })
      .catch(() => {
        if (!closed) setCountryData(null);
      })
      .finally(() => {
        if (!closed) setCountryLoading(false);
      });
      
    return () => {
      closed = true;
    };
  }, [selectedCountry, liveFeedState.lastUpdated]);

  useEffect(() => {
    if (!selectedCountry || !effectiveCountryFocus) {
      setSelectedCountryWeather(null);
      setCountryWeatherError("");
      return;
    }

    let canceled = false;
    let timer: number | null = null;

    const pullWeather = async () => {
      setCountryWeatherLoading(true);
      try {
        const snapshot = await getCountryWeatherByCoords(effectiveCountryFocus.lat, effectiveCountryFocus.lon, {
          retries: 2,
          country: selectedCountry,
        });
        if (canceled) return;
        weatherCacheRef.current[selectedCountry] = snapshot;
        setSelectedCountryWeather(snapshot);
        setCountryWeatherError(snapshot.warning || "");
      } catch {
        if (canceled) return;
        const cached = weatherCacheRef.current[selectedCountry] ?? null;
        if (cached) {
          setSelectedCountryWeather(cached);
          setCountryWeatherError("Live weather temporarily unavailable. Showing last successful snapshot.");
        } else {
          setSelectedCountryWeather(null);
          setCountryWeatherError("Live weather temporarily unavailable.");
        }
      } finally {
        if (!canceled) setCountryWeatherLoading(false);
      }
    };

    void pullWeather();
    timer = window.setInterval(() => {
      void pullWeather();
    }, 90000);

    return () => {
      canceled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [selectedCountry, effectiveCountryFocus?.lat, effectiveCountryFocus?.lon]);

  const triggerMapRefresh = async () => {
    setRefreshingMap(true);
    try {
      const ok = await refreshRiskMapBatch(50);
      cacheRef.current.riskMap.timestamp = 0;
      cacheRef.current.riskCoverage.timestamp = 0;
      if (!ok) setErrorText("Manual map refresh failed");
    } finally {
      setRefreshingMap(false);
    }
  };

  const navigate = useNavigate();

  return (
    <main className={`wp-shell dashboard-v2 ${fpsLow ? "motion-low" : "motion-rich"}`}>
      <div className="parallax-grid" />
      <ConsoleNavigation
        title={<>THE WORLD'S <span>PULSE</span></>}
        subtitle="Real-Time Global Human Behavior Intelligence"
        rightSlot={(
          <div className="wp-header-status">
            <span className="wp-status-pill">{connectionState}</span>
            <span className="wp-status-text">Heartbeat {liveFeedState.ingestionHeartbeatSec.toFixed(1)}s</span>
            <span className="wp-status-text">Verified {verifiedCoverageLabel}</span>
          </div>
        )}
        sectionTabs={[
          { label: "Overview", targetId: "dashboard-overview" },
          { label: "Global Behavior", targetId: "dashboard-global-behavior" },
          { label: "Analytics", targetId: "dashboard-operational-analytics" },
          { label: "Telemetry", targetId: "dashboard-system-events" },
        ]}
      />

      <section id="dashboard-overview" className="wp-intelligence-bar">
        <div className="wp-intelligence-primary">
          <span className="wp-intelligence-kicker">Live Intelligence</span>
          <span className="wp-intelligence-topic">Topic pressure {topTopic}</span>
          <span className="wp-intelligence-sep" />
          <span>{liveFeedState.incidents?.length ?? 0} active incidents</span>
        </div>
        <div className="wp-intelligence-secondary">
          <span>{new Date(liveFeedState.lastUpdated).toISOString().replace("T", " ").slice(0, 19)} UTC</span>
          <span>Heartbeat {liveFeedState.ingestionHeartbeatSec.toFixed(1)}s</span>
          <span>Drift {liveFeedState.modelDrift.toFixed(2)}</span>
          <span>Feed {connectionState}</span>
          <span>Updated {new Date(liveFeedState.lastUpdated).toLocaleTimeString()}</span>
        </div>
      </section>

      <section
        className="wp-intelligence-bar"
        style={
          qualityGateDisplayActive
            ? { borderColor: "rgba(248, 113, 113, 0.45)", background: "rgba(127, 29, 29, 0.14)" }
            : (qualityGateActive
              ? { borderColor: "rgba(251, 191, 36, 0.38)", background: "rgba(120, 53, 15, 0.14)" }
              : { borderColor: "rgba(52, 211, 153, 0.34)", background: "rgba(6, 78, 59, 0.14)" })
        }
      >
        <div className="wp-intelligence-primary">
          <span className="wp-intelligence-kicker">Data Quality Gate</span>
          <span className="wp-intelligence-topic">{qualityGateMessage}</span>
          <span className="wp-intelligence-sep" />
          <span>Verified countries {verifiedCoverageLabel} | Fresh data {qualityGateFreshnessPct}%</span>
        </div>
        <div className="wp-intelligence-secondary">
          <span>{qualityGateDetail}</span>
        </div>
      </section>
      <section className="wp-exec-grid">
        <article className="wp-card wp-exec-card">
          <div className="wp-exec-label">Global Mood</div>
          <strong className="wp-highlight">{`${globalMoodScore.toFixed(1)} +/- ${globalMoodUncertainty.toFixed(1)}`}</strong>
          <div className="wp-mini-meta"><span>Confidence</span><strong>{(globalMoodConfidence * 100).toFixed(0)}%</strong></div>
          <div className="wp-mini-meta wp-mini-meta--detail"><span>Countries</span><strong className="wp-mini-meta-detail">{globalMoodCountrySummary}</strong></div>
        </article>
        <article className="wp-card wp-exec-card">
          <div className="wp-exec-label">Verified Countries</div>
          <strong className="wp-highlight">{verifiedCoverageLabel}</strong>
          <div className="wp-mini-meta"><span>Coverage</span><strong>{coverageState.coverage_pct.toFixed(1)}%</strong></div>
          <div className="wp-mini-meta"><span>No-data / stale</span><strong>{coverageState.no_data + coverageState.stale}</strong></div>
        </article>
        <article className="wp-card wp-exec-card">
          <div className="wp-exec-label">Global Risk</div>
          <strong className="wp-highlight">{`${globalRiskScore.toFixed(1)} / 100`}</strong>
          <div className="wp-mini-meta"><span>Threat</span><strong>{telemetryThreat.label}</strong></div>
          <div className="wp-mini-meta"><span>Trend</span><strong>{qualityGateDisplayActive ? `${telemetryTrend.label} (banded)` : telemetryTrend.label}</strong></div>
        </article>
        <article className="wp-card wp-exec-card">
          <div className="wp-exec-label">Forecast</div>
          <strong className="wp-highlight">{forecastRiskScore.toFixed(1)} / 100</strong>
          <div className="wp-mini-meta"><span>{forecastHorizonHours}h delta</span><strong>{forecastRiskDelta >= 0 ? "+" : ""}{forecastRiskDelta.toFixed(2)}</strong></div>
          <div className="wp-mini-meta"><span>Confidence</span><strong>{(forecastConfidence * 100).toFixed(0)}%</strong></div>
        </article>
      </section>

      <section className="wp-ops-strip wp-ops-strip-flat">
        <div className="wp-ops-inline-block">
          <span className="wp-ops-label">Mode</span>
          <div className="wp-ops-status-line">
            <span>Analytics-first dashboard</span>
            <span>Workflow moved to Response Console</span>
          </div>
        </div>
        <div className="wp-ops-inline-block">
          <span className="wp-ops-label">Response</span>
          <div className="wp-command-row">
            <button onClick={() => navigate("/response-console")}>Open Response Console</button>
          </div>
        </div>
        <div className="wp-ops-inline-block wp-ops-inline-status">
          <span className="wp-ops-label">Status</span>
          <div className="wp-ops-status-line">
            <span>Retries {retries}</span>
            <span>Validation {validationSummary?.status ?? "pending"}</span>
            <span>No-data / stale {coverageState.no_data + coverageState.stale}</span>
          </div>
          {errorText ? <div className="map-fallback-error">{errorText}</div> : null}
        </div>
      </section>

      {/* Unified Intelligence Panel - Map + Global Intelligence (left) | Sentinel Core (right) */}
      <section id="dashboard-global-behavior" className="dashboard-layout">
        <div ref={leftColumnRef} className="left-column">
          <article className={`wp-card panel-frame map-intelligence-panel advanced-cyber-frame ${fpsLow ? "" : "panel-animated"}`}>
            <div className="panel-head">
              <h3>Global Behavior Map</h3>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <button onClick={triggerMapRefresh} disabled={refreshingMap}>{refreshingMap ? "Refreshing..." : "Refresh Next 50"}</button>
                {selectedCountry ? (
                  <button onClick={() => setSelectedCountry(null)}>Clear Country Focus</button>
                ) : null}
              </div>
            </div>
            {panelStale.map ? <div className="panel-stale">stale</div> : null}
            <div className="panel-content wp-map-surface map-surface-advanced">
              <div className="proposal-map-stage">
                <div ref={mapRef} className="echart-map" />
                {selectedCountry ? (
                  <div className="map-weather-overlay" aria-hidden="true">
                    {showRainAnimation ? (
                      <div className="map-rain-layer">
                        {Array.from({ length: rainDropCount }).map((_, idx) => (
                          <span
                            key={`rain-${idx}`}
                            style={{
                              left: `${(idx * 37) % 100}%`,
                              animationDelay: `${(idx % 9) * 0.18}s`,
                              animationDuration: `${0.75 + (((idx * 13) % 7) * 0.12)}s`,
                            }}
                          />
                        ))}
                      </div>
                    ) : null}
                    {showWindAnimation ? (
                      <div className="map-wind-layer">
                        {Array.from({ length: windLineCount }).map((_, idx) => (
                          <span
                            key={`wind-${idx}`}
                            style={{
                              top: `${(idx * 19) % 95}%`,
                              animationDelay: `${(idx % 8) * 0.28}s`,
                              animationDuration: `${1.8 + (((idx * 11) % 6) * 0.22)}s`,
                            }}
                          />
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {selectedCountry ? (
                  <div className="map-weather-live-chip">
                    {selectedCountryWeather ? (
                      <>
                        <strong>{selectedCountryWeather.conditionLabel}</strong>
                        <span>{selectedCountryWeather.temperatureC.toFixed(1)}C</span>
                        <span>Wind {selectedCountryWeather.windSpeedKmh.toFixed(1)} km/h</span>
                        <span>{selectedCountryWeather.provider === "open-meteo" ? "Open-Meteo" : "Met.no"}</span>
                      </>
                    ) : (
                      <strong>Live weather temporarily unavailable</strong>
                    )}
                    {countryWeatherLoading ? <span>Updating...</span> : null}
                  </div>
                ) : null}
                {mapHover ? (
                  <div className="map-hover-box map-hover-card">
                    <strong className="map-hover-title">{mapHover.country}</strong>
                    <span className="map-hover-risk">{mapHover.quality === "verified" ? `Risk Score: ${mapHover.risk.toFixed(1)}` : `Status: ${mapHover.quality}`}</span>
                  </div>
                ) : null}
              </div>
              <div className="proposal-map-meta">
                <p style={{ fontSize: 12, color: "#d1d5db" }}>
                  {coverageState.verified} / {coverageState.total || riskMapRows.length} countries verified today. Gray countries have no same-day source data yet. Click a country to zoom, inspect news beacons, and open drilldown analysis.
                </p>
                <p style={{ fontSize: 12, color: "#94a3b8" }}>
                  Latest validation: {validationSummary?.status ?? "not available"}{validationSummary?.sample_count ? `, ${validationSummary.sample_count} benchmark rows, Brier ${safeN(validationSummary.brier_score).toFixed(3)}` : ""}.
                </p>
              </div>
            </div>
          </article>

          <article className={`wp-card panel-frame global-intelligence-panel ${fpsLow ? "" : "panel-animated"}`}>
            <div className="panel-head futuristic-panel-header">
              <div className="header-glow cyan"></div>
              <h3>
                <span className="header-icon">GLB</span>
                Global Intelligence Feed
                <span className="header-badge">LIVE</span>
              </h3>
            </div>
            <div className="panel-content">
              {showDeferredPanels ? (
                <Suspense fallback={<DeferredPanelPlaceholder label="Loading global intelligence feed..." />}>
                  <GlobalIntelligenceFeed
                    maxRows={selectedCountry ? 6 : 5}
                    refreshInterval={5000}
                    selectedCountry={selectedCountry}
                    onVisibleItemsChange={setSelectedCountryNews}
                    onClearCountry={() => setSelectedCountry(null)}
                  />
                </Suspense>
              ) : (
                <DeferredPanelPlaceholder label="Preparing global intelligence feed..." />
              )}
            </div>
          </article>
        </div>

        <div className="right-column">
          <article className={`wp-card panel-frame sentinel-ai-panel brain-model-panel ${fpsLow ? "" : "panel-animated"}`}>
            <div className="panel-head futuristic-panel-header">
              <div className="header-glow pink"></div>
              <h3>
                <span className="header-icon">3D</span>
                Sentinel Intelligence Core
                <span className="header-badge">GLB</span>
              </h3>
            </div>
            <div className="panel-content brain-model-panel-content">
              <div className="brain-model-stage">
                {showDeferredPanels ? (
                  <Suspense fallback={<DeferredPanelPlaceholder label="Loading sentinel intelligence core..." />}>
                    <BrainModelViewer className="dashboard-brain-model" />
                  </Suspense>
                ) : (
                  <DeferredPanelPlaceholder label="Preparing sentinel intelligence core..." />
                )}
              </div>
              <div className="brain-telemetry-dock" role="status" aria-live="polite">
                <div className="brain-telemetry-summary-row">
                  <div className="brain-telemetry-card brain-telemetry-card-primary">
                    <span className="brain-telemetry-card-label">Risk Score</span>
                    <strong>{globalRiskScore.toFixed(1)}</strong>
                  </div>
                  <div className={`brain-telemetry-card brain-telemetry-card-tone tone-${telemetryThreat.tone}`}>
                    <span className="brain-telemetry-card-label">Threat Level</span>
                    <strong>{telemetryThreat.label}</strong>
                  </div>
                  <div className={`brain-telemetry-card brain-telemetry-card-tone tone-${telemetryTrend.tone}`}>
                    <span className="brain-telemetry-card-label">Trend</span>
                    <strong>{telemetryTrend.label}</strong>
                  </div>
                </div>
                <div className="brain-telemetry-drivers-row">
                  <span className="brain-telemetry-row-label">Top Drivers</span>
                  <div className="brain-telemetry-chip-list">
                    {telemetryDrivers.map((driver) => (
                      <span key={driver} className="brain-telemetry-chip">{driver}</span>
                    ))}
                  </div>
                </div>
                <div className="brain-telemetry-status-row">
                  <span className={`brain-telemetry-status-dot state-${connectionState}`} />
                  <span className="brain-telemetry-status-line">{telemetryStatusLine}</span>
                </div>
              </div>
            </div>
          </article>

          <section ref={streamHostRef} id="dashboard-system-events" className="hero-system-events">
            {showDeferredPanels ? (
              <Suspense fallback={<DeferredPanelPlaceholder label="Loading system event stream..." />}>
                <SystemEventStream
                  packets={systemEventPackets}
                  stale={panelStale.stream}
                  style={streamHeight ? { height: `${streamHeight}px` } : undefined}
                />
              </Suspense>
            ) : (
              <article className="wp-card panel-frame operator-response-panel">
                <div className="panel-content operational-panel-content">
                  <DeferredPanelPlaceholder label="Preparing system event stream..." />
                </div>
              </article>
            )}
          </section>
        </div>
      </section>

      <section id="dashboard-operational-analytics" className="operational-analytics-grid">
        {showDeferredPanels ? (
          <>
            <Suspense fallback={<DeferredPanelPlaceholder label="Loading behavioral analytics..." />}>
              <BehavioralAnalyticsPanel
                history={history}
                rows={riskMapRows}
                telemetryDrivers={telemetryDrivers}
                topTopic={topTopic}
                riskDelta={riskDelta}
                globalRiskScore={globalRiskScore}
                globalMoodScore={globalMoodScore}
                forecastRiskDelta={forecastRiskDelta}
                incidentCount={liveFeedState.incidents?.length ?? 0}
                coveragePct={coverageState.coverage_pct}
              />
            </Suspense>
            <Suspense fallback={<DeferredPanelPlaceholder label="Loading priority watchlist..." />}>
              <PriorityWatchlist
                rows={riskMapRows}
                incidents={liveFeedState.incidents ?? []}
                feedItems={selectedCountryNews}
                selectedCountry={selectedCountry}
                onSelectCountry={setSelectedCountry}
              />
            </Suspense>
            <Suspense fallback={<DeferredPanelPlaceholder label="Loading signal integrity board..." />}>
              <SignalIntegrityBoard
                coverage={coverageState}
                trustSnapshot={trustSnapshot}
                connectionState={connectionState}
                heartbeatSec={liveFeedState.ingestionHeartbeatSec}
                modelDrift={liveFeedState.modelDrift}
                validationStatus={validationSummary?.status ?? "pending"}
                moodConfidence={globalMoodConfidence}
                moodUncertainty={moodUncertaintyDisplay}
                forecastConfidence={forecastConfidenceDisplay}
                qualityGateMessage={qualityGateMessage}
                reliabilityStatus={reliabilityStatus}
                freshSources={freshSources}
                staleSources={staleSources}
              />
            </Suspense>
          </>
        ) : (
          <>
            <article className="wp-card panel-frame operational-panel analytics-hero-panel"><div className="panel-content operational-panel-content"><DeferredPanelPlaceholder label="Preparing behavioral analytics..." /></div></article>
            <article className="wp-card panel-frame operational-panel"><div className="panel-content operational-panel-content"><DeferredPanelPlaceholder label="Preparing priority watchlist..." /></div></article>
            <article className="wp-card panel-frame operational-panel"><div className="panel-content operational-panel-content"><DeferredPanelPlaceholder label="Preparing signal integrity board..." /></div></article>
          </>
        )}
      </section>

      {showDeferredPanels ? (
        <Suspense fallback={null}>
          <CountryDrilldown
            open={Boolean(selectedCountry)}
            loading={countryLoading}
            data={countryData}
            countryNews={selectedCountryFeedItems}
            liveIncidents={liveFeedState.incidents ?? []}
            threatLabel={deriveThreatMeta(safeN(countryData?.risk, globalRiskScore)).label}
            trendLabel={deriveTrendMeta(
              safeN(countryData?.risk, globalRiskScore) -
                safeN(countryData?.trend?.[Math.max((countryData?.trend?.length ?? 1) - 2, 0)]?.value, safeN(countryData?.risk, globalRiskScore))
            ).label}
            riskDelta={
              safeN(countryData?.risk, globalRiskScore) -
              safeN(countryData?.trend?.[Math.max((countryData?.trend?.length ?? 1) - 2, 0)]?.value, safeN(countryData?.risk, globalRiskScore))
            }
            topDrivers={
              countryData?.drivers?.length
                ? [...countryData.drivers]
                    .sort((left, right) => Math.abs(right.contribution) - Math.abs(left.contribution))
                    .slice(0, 3)
                    .map((driver) => formatDriverLabel(driver.feature))
                : telemetryDrivers
            }
            forecast={{
              score: normalizeRisk(
                safeN(countryData?.risk, globalRiskScore) +
                  (
                    safeN(countryData?.risk, globalRiskScore) -
                    safeN(countryData?.trend?.[Math.max((countryData?.trend?.length ?? 1) - 2, 0)]?.value, safeN(countryData?.risk, globalRiskScore))
                  ) * 2.2
              ),
              delta:
                (
                  safeN(countryData?.risk, globalRiskScore) -
                  safeN(countryData?.trend?.[Math.max((countryData?.trend?.length ?? 1) - 2, 0)]?.value, safeN(countryData?.risk, globalRiskScore))
                ) * 2.2,
              confidence: forecastConfidenceDisplay,
              horizonHours: 48,
            }}
            reliability={{
              status: reliabilityStatus,
              freshSources,
              staleSources,
              confidence: forecastConfidenceDisplay,
              uncertainty: moodUncertaintyDisplay,
              coverage: verifiedCoverageLabel,
            }}
            weather={selectedCountryWeather}
            weatherLoading={countryWeatherLoading}
            weatherError={countryWeatherError}
            onClose={() => setSelectedCountry(null)}
            workflowEnabled={false}
          />
        </Suspense>
      ) : null}

      <button
        onClick={() => setSentinelEnabled(!sentinelEnabled)}
        className={`sentinel-toggle ${sentinelEnabled ? "is-enabled" : "is-disabled"}`}
      >
        {sentinelEnabled ? "Sentinel AI ON" : "Sentinel AI OFF"}
      </button>
    </main>
  );
}





































