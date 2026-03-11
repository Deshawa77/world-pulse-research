import { useEffect, useMemo, useRef, useState } from "react";

import "../components/futuristic-dashboard.css";
import "./Dashboard.css";
import ConsoleNavigation from "../components/ConsoleNavigation";
import { lazy, Suspense } from "react";

import type { OperatorEvent } from "../components/EventLog";


import {
  COUNTRY_RISK_WS_URL,
  getCountryDrilldown,
  getLiveCommandFeed,
  getLatestGlobalFeatures,
  getRiskMap,
  getRiskMapCoverage,
  postAlertAction,
  refreshRiskMapBatch,
  type CountryDrilldownData,
  type LiveCommandFeed,
  type RiskMapCoverage,
  type RiskMapPoint,
} from "../services/api";

const CountryDrilldown = lazy(() => import("../components/CountryDrilldown"));
const EventLog = lazy(() => import("../components/EventLog"));
const BrainModelViewer = lazy(() => import("../components/BrainModelViewer"));
const DataBurstModal = lazy(() => import("../components/DataBurstModal"));
const GlobalIntelligenceFeed = lazy(() => import("../components/GlobalIntelligenceFeed"));
const CryptoMarketPulse = lazy(() => import("../components/CryptoMarketPulse"));
const GlobalDisasterMonitor = lazy(() => import("../components/GlobalDisasterMonitor"));
const EconomicIndicatorsFeed = lazy(() => import("../components/EconomicIndicatorsFeed"));
const HealthAlertStream = lazy(() => import("../components/HealthAlertStream"));
const GoogleTrendsRadar = lazy(() => import("../components/GoogleTrendsRadar"));

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
type PanelKey = "risk" | "map" | "stream" | "ops";

const HISTORY_KEY = "wp_v3_history";
const EVENTS_KEY = "wp_v3_events";
const MAX_HISTORY = 1200;

const DRIVER_LABELS: Record<string, string> = {
  news_sentiment: "News Sentiment",
  gdelt_sentiment: "GDELT Sentiment",
  crypto_return: "Crypto Return",
  crypto_volatility: "Crypto Volatility",
  stock_return: "Stock Return",
  stock_volatility: "Stock Volatility",
  weather_anomaly: "Weather Anomaly",
};

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

function formatRelativeTime(value?: string | null): string {
  if (!value) return "No recent update";
  const stamp = new Date(value).getTime();
  if (!Number.isFinite(stamp)) return "No recent update";
  const deltaSec = Math.max(0, Math.floor((Date.now() - stamp) / 1000));
  if (deltaSec < 15) return "Just now";
  if (deltaSec < 60) return `${deltaSec}s ago`;
  const deltaMin = Math.floor(deltaSec / 60);
  if (deltaMin < 60) return `${deltaMin}m ago`;
  const deltaHr = Math.floor(deltaMin / 60);
  if (deltaHr < 24) return `${deltaHr}h ago`;
  return `${Math.floor(deltaHr / 24)}d ago`;
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
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [fpsLow, setFpsLow] = useState(false);
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  
  useEffect(() => {
    selectedCountryRef.current = selectedCountry;
  }, [selectedCountry]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setShowDeferredPanels(true);
    }, 250);
    return () => window.clearTimeout(timer);
  }, []);
  
  const [countryData, setCountryData] = useState<CountryDrilldownData | null>(null);

  const [countryLoading, setCountryLoading] = useState(false);
  const [operatorEvents, setOperatorEvents] = useState<OperatorEvent[]>(() => readJson(EVENTS_KEY, [] as OperatorEvent[]));
  const [mapHover, setMapHover] = useState<{ country: string; risk: number; quality: string } | null>(null);
  const [dataBurstOpen, setDataBurstOpen] = useState(false);
  const [dataBurstCountry, setDataBurstCountry] = useState<string>("");
  const [dataBurstRisk, setDataBurstRisk] = useState<number>(0);
  const [errorText, setErrorText] = useState("");
  const [refreshingMap, setRefreshingMap] = useState(false);

  const [retries, setRetries] = useState(0);
  const [activePreset, setActivePreset] = useState<"analyst" | "ops" | "executive">("analyst");
  const [sentinelEnabled, setSentinelEnabled] = useState(true);
  const [showDeferredPanels, setShowDeferredPanels] = useState(false);

  const cacheRef = useRef<{
    liveFeed: { data: LiveCommandFeed | null; timestamp: number; ttl: number };
    riskMap: { data: RiskMapPoint[] | null; timestamp: number; ttl: number };
    riskCoverage: { data: RiskMapCoverage | null; timestamp: number; ttl: number };
    global: { data: any | null; timestamp: number; ttl: number };
  }>({
    liveFeed: { data: null, timestamp: 0, ttl: 3000 },
    riskMap: { data: null, timestamp: 0, ttl: 5000 },
    riskCoverage: { data: null, timestamp: 0, ttl: 5000 },
    global: { data: null, timestamp: 0, ttl: 2000 },
  });

  const inFlightRef = useRef<Set<string>>(new Set());

  const panelUpdated = useRef<Record<PanelKey, number>>({
    risk: Date.now(),
    map: Date.now(),
    stream: Date.now(),
    ops: Date.now(),
  });
  
  const retriesRef = useRef(0);
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapMounted = useRef(false);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);
  const rotationRef = useRef<number>(0);
  const rotationRafRef = useRef<number | null>(null);
  const isRotatingRef = useRef<boolean>(false);
  const selectedCountryRef = useRef<string | null>(null);
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
  const topTopic = active?.topics?.find((topic) => topic && topic !== "no data") ?? "No dominant topic";
  const validationSummary = coverageState.latest_validation;
  const liveFreshness = formatRelativeTime(liveFeedState.lastUpdated);
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
  const telemetryStatusLine = `${dockConnectionLabel} • ${liveSignalCount} verified signals • Updated ${formatTelemetryTime(liveFeedState.lastUpdated)}`;
  const domainCards = [
    {
      title: "Multi-Source Signal Fusion",
      value: verifiedCoverageLabel,
      detail: "Countries with verified same-day intelligence on the live map",
    },
    {
      title: "Sentiment + NLP",
      value: topTopic,
      detail: "Leading behavior topic extracted from the latest global intelligence signals",
    },
    {
      title: "Predictive Outlook",
      value: `${forecastRiskScore.toFixed(1)} / 100`,
      detail: `${forecastHorizonHours}h risk forecast with ${forecastRiskDelta >= 0 ? "rising" : "cooling"} momentum ${forecastRiskDelta >= 0 ? "+" : ""}${forecastRiskDelta.toFixed(2)} | confidence ${(forecastConfidence * 100).toFixed(0)}%`,
    },
    {
      title: "Reliability + Validation",
      value: validationSummary?.status === "ok" ? "Validated" : connectionState,
      detail: validationSummary?.sample_count
        ? `${validationSummary.sample_count} benchmark rows, Brier ${safeN(validationSummary.brier_score).toFixed(3)}`
        : `Feed ${connectionState}, latest stream ${liveFreshness}`,
    },
  ];
  
  const panelStale = useMemo(() => {
    const now = Date.now();
    return {
      risk: staleFor(now - panelUpdated.current.risk, 12000),
      map: staleFor(now - panelUpdated.current.map, 12000),
      stream: staleFor(now - panelUpdated.current.stream, 12000),
      ops: staleFor(now - panelUpdated.current.ops, 30000),
    };
  }, [history.length, operatorEvents.length, riskMapRows.length, coverageState.verified]);

  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-MAX_HISTORY)));
  }, [history]);

  useEffect(() => {
    localStorage.setItem(EVENTS_KEY, JSON.stringify(operatorEvents.slice(0, 200)));
  }, [operatorEvents]);

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
        const [liveResult, mapRowsResult, coverageResult, globalResult] = await Promise.allSettled([
          getCachedOrFetch("liveFeed", getLiveCommandFeed),
          getCachedOrFetch("riskMap", getRiskMap),
          getCachedOrFetch("riskCoverage", getRiskMapCoverage),
          getCachedOrFetch("global", getLatestGlobalFeatures),
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

  useEffect(() => {
    let socket: WebSocket | null = null;
    let connectTimer = 0;
    let retryTimer = 0;
    let closed = false;

    const connect = () => {
      if (closed) return;
      try {
        socket = new WebSocket(COUNTRY_RISK_WS_URL);
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
        const traces = riskMapRows.length ? [
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
        ] as any : [
          {
            type: "scattergeo",
            lon: [],
            lat: [],
            mode: "markers",
            hoverinfo: "skip",
            showlegend: false,
          },
        ] as any;
        await Plotly.react(
          mapRef.current,
          traces,
          {
            margin: { l: 0, r: 0, b: 0, t: 0 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            geo: {
              projection: { type: "natural earth" },
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
            const risk = Number(p.z);
            setSelectedCountry(country);
            setDataBurstCountry(country);
            setDataBurstRisk(risk);
            setDataBurstOpen(true);
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
  }, [verifiedRiskMap, unverifiedRiskMap]);

  const startAutoRotation = (Plotly: any) => {
    if (isRotatingRef.current || !mapRef.current) return;
    isRotatingRef.current = true;
    
    const rotate = () => {
      if (!isRotatingRef.current || !mapRef.current || selectedCountryRef.current) return;
      rotationRef.current = rotationRef.current + 0.5;

      Plotly.relayout(mapRef.current, {
        "geo.projection.rotation.lon": rotationRef.current,
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

  const addEvent = async (action: OperatorEvent["action"], comment?: string, owner = "ops-team") => {
    const evt: OperatorEvent = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      timestamp: new Date().toISOString(),
      actor: owner,
      action,
      comment,
    };
    setOperatorEvents((prev) => [evt, ...prev].slice(0, 200));
    panelUpdated.current.ops = Date.now();
    if (selectedCountry) {
      await postAlertAction({
        country: selectedCountry,
        action: action === "assign" ? "assign" : action,
        owner,
        comment,
      });
    }
  };

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
          { label: "Live Domains", targetId: "dashboard-live-domains" },
          { label: "Operator Log", targetId: "dashboard-operator-log" },
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

      <section className="wp-exec-grid">
        <article className="wp-card wp-exec-card">
          <div className="wp-exec-label">Global Mood</div>
          <strong className="wp-highlight">{globalMoodScore.toFixed(1)} +/- {globalMoodUncertainty.toFixed(1)}</strong>
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
          <strong className="wp-highlight">{globalRiskScore.toFixed(1)} / 100</strong>
          <div className="wp-mini-meta"><span>Threat</span><strong>{telemetryThreat.label}</strong></div>
          <div className="wp-mini-meta"><span>Trend</span><strong>{telemetryTrend.label}</strong></div>
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
          <span className="wp-ops-label">Preset</span>
          <div className="wp-preset-group">
            <button className={activePreset === "analyst" ? "is-active" : ""} onClick={() => setActivePreset("analyst")}>Analyst</button>
            <button className={activePreset === "ops" ? "is-active" : ""} onClick={() => setActivePreset("ops")}>Ops</button>
            <button className={activePreset === "executive" ? "is-active" : ""} onClick={() => setActivePreset("executive")}>Executive</button>
          </div>
        </div>
        <div className="wp-ops-inline-block">
          <span className="wp-ops-label">Actions</span>
          <div className="wp-command-row">
            <button onClick={() => addEvent("acknowledge", "global acknowledge")}>Acknowledge</button>
            <button onClick={() => addEvent("snooze", "15m snooze")}>Snooze</button>
            <button onClick={() => addEvent("assign", "escalated", "analyst-1")}>Assign</button>
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

      <section className="proposal-summary-grid">
        {domainCards.map((card) => (
          <article key={card.title} className="wp-card proposal-summary-card">
            <h3>{card.title}</h3>
            <strong className="wp-highlight proposal-summary-value">{card.value}</strong>
            <p className="proposal-summary-detail">{card.detail}</p>
          </article>
        ))}
      </section>

      {/* Unified Intelligence Panel - Map + Global Intelligence (left) | Sentinel AI (right) */}
      <section id="dashboard-global-behavior" className="dashboard-layout">
        <div className="left-column">
            {/* Map Intelligence - Top Left */}
            <article className={`wp-card panel-frame map-intelligence-panel advanced-cyber-frame ${fpsLow ? "" : "panel-animated"}`}>
              <div className="panel-head">
                <h3>Global Behavior Map</h3>
                <button onClick={triggerMapRefresh} disabled={refreshingMap}>{refreshingMap ? "Refreshing..." : "Refresh Next 50"}</button>
              </div>
              {panelStale.map ? <div className="panel-stale">stale</div> : null}
              <div className="panel-content wp-map-surface map-surface-advanced">
                <div className="proposal-map-stage">
                  <div ref={mapRef} className="echart-map" />
                  {mapHover ? (
                    <div className="map-hover-box map-hover-card">
                      <strong className="map-hover-title">{mapHover.country}</strong>
                      <span className="map-hover-risk">{mapHover.quality === "verified" ? `Risk Score: ${mapHover.risk.toFixed(1)}` : `Status: ${mapHover.quality}`}</span>
                    </div>
                  ) : null}
                </div>
                <div className="proposal-map-meta">
                  <p style={{ fontSize: 12, color: "#d1d5db" }}>
                    {coverageState.verified} / {coverageState.total || riskMapRows.length} countries verified today. Gray countries have no same-day source data yet. Click a country for drilldown analysis.
                  </p>
                  <p style={{ fontSize: 12, color: "#94a3b8" }}>
                    Latest validation: {validationSummary?.status ?? "not available"}{validationSummary?.sample_count ? `, ${validationSummary.sample_count} benchmark rows, Brier ${safeN(validationSummary.brier_score).toFixed(3)}` : ""}.
                  </p>
                </div>
              </div>
            </article>

            {/* Global Intelligence Feed - Bottom Left */}
            <article className={`wp-card panel-frame global-intelligence-panel ${fpsLow ? "" : "panel-animated"}`}>
              <div className="panel-head futuristic-panel-header">
                <div className="header-glow cyan"></div>
                <h3>
                  <span className="header-icon">ðŸŒ</span>
                  Global Intelligence Feed
                  <span className="header-badge">LIVE</span>
                </h3>
              </div>
              <div className="panel-content">
                {showDeferredPanels ? (
                  <Suspense fallback={<DeferredPanelPlaceholder label="Loading global intelligence feed..." />}>
                    <GlobalIntelligenceFeed maxRows={3} refreshInterval={5000} />
                  </Suspense>
                ) : (
                  <DeferredPanelPlaceholder label="Preparing global intelligence feed..." />
                )}
              </div>
            </article>
        </div>

        <div className="right-column">
            {/* Brain Model - Right Side */}
            <article className={`wp-card panel-frame sentinel-ai-panel brain-model-panel ${fpsLow ? "" : "panel-animated"}`}>
              <div className="panel-head futuristic-panel-header">
                <div className="header-glow pink"></div>
                <h3>
                  <span className="header-icon">3D</span>
                  Neural Brain Model
                  <span className="header-badge">GLB</span>
                </h3>
              </div>
              <div className="panel-content brain-model-panel-content">
                <div className="brain-model-stage">
                  {showDeferredPanels ? (
                    <Suspense fallback={<DeferredPanelPlaceholder label="Loading neural brain model..." />}>
                      <BrainModelViewer className="dashboard-brain-model" />
                    </Suspense>
                  ) : (
                    <DeferredPanelPlaceholder label="Preparing neural brain model..." />
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
        </div>
      </section>



      {/* Real-Time Intelligence Grid - 2 Columns */}
      <section id="dashboard-live-domains" className="realtime-intelligence-grid">
        {/* Crypto Market Pulse */}
        <article className={`wp-card panel-frame realtime-domain-card ${fpsLow ? "" : "panel-animated"}`}>

          <div className="panel-head futuristic-panel-header domain-header domain-header-amber">
            <div className="header-glow domain-header-glow domain-header-glow-amber"></div>
            <h3>
              <span className="header-icon">â‚¿</span>
              Crypto Market Pulse
              <span className="header-badge domain-badge domain-badge-amber">LIVE</span>
            </h3>
          </div>
          <div className="panel-content panel-content-scrollless">
            {showDeferredPanels ? (
              <Suspense fallback={<DeferredPanelPlaceholder label="Loading crypto market pulse..." />}>
                <CryptoMarketPulse maxItems={5} refreshInterval={15000} />
              </Suspense>
            ) : (
              <DeferredPanelPlaceholder label="Preparing crypto market pulse..." />
            )}
          </div>
        </article>

        {/* Global Disaster Monitor */}
        <article className={`wp-card panel-frame realtime-domain-card ${fpsLow ? "" : "panel-animated"}`}>

          <div className="panel-head futuristic-panel-header domain-header domain-header-red">
            <div className="header-glow domain-header-glow domain-header-glow-red"></div>
            <h3>
              <span className="header-icon">ðŸŒ‹</span>
              Global Disaster Monitor
              <span className="header-badge domain-badge domain-badge-red">LIVE</span>
            </h3>
          </div>
          <div className="panel-content panel-content-scrollless">
            {showDeferredPanels ? (
              <Suspense fallback={<DeferredPanelPlaceholder label="Loading disaster monitor..." />}>
                <GlobalDisasterMonitor maxItems={6} refreshInterval={20000} />
              </Suspense>
            ) : (
              <DeferredPanelPlaceholder label="Preparing disaster monitor..." />
            )}
          </div>
        </article>

        {/* Economic Indicators Feed */}
        <article className={`wp-card panel-frame realtime-domain-card ${fpsLow ? "" : "panel-animated"}`}>

          <div className="panel-head futuristic-panel-header domain-header domain-header-green">
            <div className="header-glow domain-header-glow domain-header-glow-green"></div>
            <h3>
              <span className="header-icon">ðŸ“Š</span>
              Economic Indicators
              <span className="header-badge domain-badge domain-badge-green">LIVE</span>
            </h3>
          </div>
          <div className="panel-content panel-content-scrollless">
            {showDeferredPanels ? (
              <Suspense fallback={<DeferredPanelPlaceholder label="Loading economic indicators..." />}>
                <EconomicIndicatorsFeed refreshInterval={30000} />
              </Suspense>
            ) : (
              <DeferredPanelPlaceholder label="Preparing economic indicators..." />
            )}
          </div>
        </article>

        {/* Health Alert Stream */}
        <article className={`wp-card panel-frame realtime-domain-card ${fpsLow ? "" : "panel-animated"}`}>

          <div className="panel-head futuristic-panel-header domain-header domain-header-pink">
            <div className="header-glow domain-header-glow domain-header-glow-pink"></div>
            <h3>
              <span className="header-icon">ðŸ¥</span>
              Health Alert Stream
              <span className="header-badge domain-badge domain-badge-pink">LIVE</span>
            </h3>
          </div>
          <div className="panel-content panel-content-scrollless">
            {showDeferredPanels ? (
              <Suspense fallback={<DeferredPanelPlaceholder label="Loading health alert stream..." />}>
                <HealthAlertStream maxItems={6} refreshInterval={25000} />
              </Suspense>
            ) : (
              <DeferredPanelPlaceholder label="Preparing health alert stream..." />
            )}
          </div>
        </article>

        {/* Google Trends Radar - Full Width */}
        <article className={`wp-card panel-frame realtime-domain-card realtime-domain-card-wide ${fpsLow ? "" : "panel-animated"}`}>

          <div className="panel-head futuristic-panel-header domain-header domain-header-violet">
            <div className="header-glow domain-header-glow domain-header-glow-violet"></div>
            <h3>
              <span className="header-icon">ðŸ“ˆ</span>
              Google Trends Radar
              <span className="header-badge domain-badge domain-badge-violet">LIVE</span>
            </h3>
          </div>
          <div className="panel-content panel-content-scrollless">
            {showDeferredPanels ? (
              <Suspense fallback={<DeferredPanelPlaceholder label="Loading trends radar..." />}>
                <GoogleTrendsRadar maxItems={8} refreshInterval={30000} />
              </Suspense>
            ) : (
              <DeferredPanelPlaceholder label="Preparing trends radar..." />
            )}
          </div>
        </article>
      </section>

      {/* Operator Workflow - Full Width */}
      <section id="dashboard-operator-log" style={{ margin: "0 16px 16px" }}>
        <article className={`wp-card panel-frame operator-panel operator-panel-card ${fpsLow ? "" : "panel-animated"}`}>
          <div className="panel-head futuristic-panel-header domain-header domain-header-orange">
            <div className="header-glow domain-header-glow domain-header-glow-orange"></div>
            <h3>
              <span className="header-icon">âš¡</span>
              Operator Workflow And Reliability Log
              <span className="header-badge domain-badge domain-badge-orange">OPS</span>
            </h3>
          </div>
          <div className="panel-content panel-content-scrollless">
            {panelStale.ops ? <div className="panel-stale">stale</div> : null}
            {showDeferredPanels ? (
              <Suspense fallback={<DeferredPanelPlaceholder label="Loading operator log..." />}>
                <EventLog events={operatorEvents} />
              </Suspense>
            ) : (
              <DeferredPanelPlaceholder label="Preparing operator log..." />
            )}
          </div>
        </article>
      </section>

      {showDeferredPanels ? (
        <Suspense fallback={null}>
          <CountryDrilldown
            open={Boolean(selectedCountry)}
            loading={countryLoading}
            data={countryData}
            events={operatorEvents}
            onClose={() => setSelectedCountry(null)}
            onAcknowledge={(comment) => {
              void addEvent("acknowledge", comment);
            }}
            onSnooze={(comment) => {
              void addEvent("snooze", comment);
            }}
            onAssign={(owner, comment) => {
              void addEvent("assign", comment, owner);
            }}
          />

          <DataBurstModal
            isOpen={dataBurstOpen}
            onClose={() => setDataBurstOpen(false)}
            region={dataBurstCountry}
            riskScore={dataBurstRisk}
            threatLevel={dataBurstRisk > 75 ? "critical" : dataBurstRisk > 50 ? "elevated" : dataBurstRisk > 25 ? "guarded" : "stable"}
            countryData={{
              alerts: [
                { id: "1", title: "Geopolitical tension rising", severity: "high", timestamp: new Date().toISOString(), source: "GDELT" },
                { id: "2", title: "Market volatility detected", severity: "medium", timestamp: new Date().toISOString(), source: "Financial" },
              ],
              news: [
                { id: "1", headline: "Regional stability concerns emerge", sentiment: -0.4, source: "Reuters", timestamp: new Date().toISOString() },
                { id: "2", headline: "Economic indicators show mixed signals", sentiment: 0.1, source: "Bloomberg", timestamp: new Date().toISOString() },
              ],
              metrics: {
                riskHistory: Array.from({ length: 24 }, (_, i) => ({
                  timestamp: new Date(Date.now() - i * 3600000).toISOString(),
                  value: Math.max(0, Math.min(100, dataBurstRisk + (Math.random() - 0.5) * 20)),
                })).reverse(),
                sentimentTrend: [],
                volatilityIndex: Math.random() * 0.5 + 0.2,
                eventCount: Math.floor(Math.random() * 10) + 1,
              },
            }}
          />
        </Suspense>
      ) : null}

      <button
        onClick={() => setSentinelEnabled(!sentinelEnabled)}
        className={`sentinel-toggle ${sentinelEnabled ? "is-enabled" : "is-disabled"}`}
      >
        {sentinelEnabled ? "ðŸ¤– Sentinel AI ON" : "ðŸ¤– Sentinel AI OFF"}
      </button>
    </main>
  );
}










