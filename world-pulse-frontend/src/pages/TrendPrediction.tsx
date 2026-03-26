import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import predictionService, {
  MODEL_FEATURE_DEFS,
  type PredictionLog,
  type HistoricalDataPoint,
  type SentimentForecast,
  type MarketReaction,
  type EventPrediction,
} from "../services/predictionService";

import API, {
  API_HEADERS,
  getAdvancedInsights,
  getGovernanceData,
  getLatestGlobalFeatures,
  getRiskMap,
  getTrustReliability,
  type AdvancedInsightsData,
  type GovernanceData,
  type LatestGlobalResponse,
  type RiskMapPoint,
  type TrustReliabilitySnapshot,
} from "../services/api";
import ConsoleNavigation from "../components/ConsoleNavigation";
import AdvancedAnalyticsPanel from "../components/AdvancedAnalyticsPanel";
import "../components/futuristic-dashboard.css";
import "./Dashboard.css";
import "./TrendPrediction.css";

const ModelGovernance = lazy(() => import("../components/ModelGovernance"));
const WorldGlobe3D = lazy(() => import("../components/WorldGlobe3D"));
const RiskCorrelationMatrix = lazy(() => import("../components/RiskCorrelationMatrix"));
const HistoricalPlayback = lazy(() => import("../components/HistoricalPlayback"));
const CountryComparison = lazy(() => import("../components/CountryComparison"));

type MLModel = {
  name: string;
  vote: number;
  confidence: number;
  color: string;
};

type PredictionData = {
  timestamp: string;
  prediction: number;
  probability: number;
  model_version: string;
  features: number[];
  feature_names?: string[];
  feature_keys?: string[];
  drift_score?: number;
  inference_probability?: number;
  raw_probability?: number;
  intelligence_adjustment?: number;
  intelligence_pressure?: number;
  confidence_weight?: number;
  source?: string;
  source_status?: string;
  calibration_status?: string;
  prediction_interval?: Record<string, number> | null;
  fallback_reason?: string | null;
  data_quality_status?: string;
  advisory?: string;
  reasons?: string[];
};

type SnapshotLike = {
  timestamp: string;
  score: number;
  features: Record<string, number>;
};

type PanelStatus = "live" | "no-data" | "error";

type RiskForecastPoint = {
  horizon: string;
  risk_score: number;
  confidence: number;
  p10?: number;
  p50?: number;
  p90?: number;
};

const PREDICTION_LOGS_CACHE_KEY = "wp_v1_prediction_logs";
const CURRENT_PREDICTION_CACHE_KEY = "wp_v1_current_prediction";
type Timeframe = "1h" | "6h" | "24h" | "7d";

const DEFAULT_FEATURE_NAMES = MODEL_FEATURE_DEFS.map((item) => item.label);
const DEFAULT_FEATURE_KEYS = MODEL_FEATURE_DEFS.map((item) => item.key);
const AUTO_REFRESH_INTERVAL_MS = 90000;

function safeN(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeRisk(score: number): number {
  const clamped = Math.max(0, Math.min(100, safeN(score, 50)));
  return Number(clamped.toFixed(2));
}

function hashCountryCode(code: string): number {
  let hash = 0;
  for (let i = 0; i < code.length; i += 1) {
    hash = ((hash << 5) - hash) + code.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function computeRangeForTimeframe(selectedTimeframe: Timeframe) {
  const end = new Date();
  const start = new Date(end);
  if (selectedTimeframe === "1h") start.setHours(start.getHours() - 1);
  if (selectedTimeframe === "6h") start.setHours(start.getHours() - 6);
  if (selectedTimeframe === "24h") start.setHours(start.getHours() - 24);
  if (selectedTimeframe === "7d") start.setDate(start.getDate() - 7);
  return { start: start.toISOString(), end: end.toISOString() };
}

function normalizeHistoricalRows(rows: unknown[]): HistoricalDataPoint[] {
  return rows.map((raw, idx) => {
    const row = (raw ?? {}) as Record<string, unknown>;
    const nested = (row.features ?? {}) as Record<string, unknown>;
    const timestampCandidate = row.timestamp ?? nested.timestamp;
    const timestamp = typeof timestampCandidate === "string" && timestampCandidate
      ? timestampCandidate
      : new Date(Date.now() - (rows.length - idx) * 3600000).toISOString();

    return {
      timestamp,
      risk_score: safeN(row.risk_score ?? row.global_risk_score ?? nested.risk_score ?? nested.global_risk_score, 50),
      news_sentiment: safeN(row.news_sentiment ?? nested.news_sentiment),
      gdelt_sentiment: safeN(row.gdelt_sentiment ?? nested.gdelt_sentiment),
      crypto_return: safeN(row.crypto_return ?? nested.crypto_return),
      crypto_volatility: safeN(row.crypto_volatility ?? nested.crypto_volatility),
      stock_return: safeN(row.stock_return ?? nested.stock_return),
      stock_volatility: safeN(row.stock_volatility ?? nested.stock_volatility),
      weather_anomaly: safeN(row.weather_anomaly ?? nested.weather_anomaly),
      global_behavior_index: safeN(row.global_behavior_index ?? nested.global_behavior_index),
      global_context_index: safeN(row.global_context_index ?? nested.global_context_index),
      global_attention_index: safeN(row.global_attention_index ?? nested.global_attention_index),
      global_disruption_index: safeN(row.global_disruption_index ?? nested.global_disruption_index),
      global_economic_stress_index: safeN(row.global_economic_stress_index ?? nested.global_economic_stress_index),
      direct_behavior_score: safeN(row.direct_behavior_score ?? nested.direct_behavior_score ?? row.global_behavior_index ?? nested.global_behavior_index),
      contextual_pressure_score: safeN(row.contextual_pressure_score ?? nested.contextual_pressure_score ?? row.global_context_index ?? nested.global_context_index),
      evidence_quality_score: safeN(row.evidence_quality_score ?? nested.evidence_quality_score),
      narrative_velocity_score: safeN(row.narrative_velocity_score ?? nested.narrative_velocity_score),
      coordination_risk_score: safeN(row.coordination_risk_score ?? nested.coordination_risk_score),
      mobility_disruption_score: safeN(row.mobility_disruption_score ?? nested.mobility_disruption_score),
      logistics_stress_score: safeN(row.logistics_stress_score ?? nested.logistics_stress_score),
      household_stress_score: safeN(row.household_stress_score ?? nested.household_stress_score),
      fuel_price_pressure: safeN(row.fuel_price_pressure ?? nested.fuel_price_pressure),
      food_price_pressure: safeN(row.food_price_pressure ?? nested.food_price_pressure),
      labor_stress_score: safeN(row.labor_stress_score ?? nested.labor_stress_score),
      fx_pressure_score: safeN(row.fx_pressure_score ?? nested.fx_pressure_score),
      remittance_stress_score: safeN(row.remittance_stress_score ?? nested.remittance_stress_score),
      energy_stress_score: safeN(row.energy_stress_score ?? nested.energy_stress_score),
      global_mood_score: safeN(row.global_mood_score ?? nested.global_mood_score),
      forecast_risk_score: safeN(row.forecast_risk_score ?? nested.forecast_risk_score),
      forecast_risk_delta: safeN(row.forecast_risk_delta ?? nested.forecast_risk_delta),
      forecast_confidence: safeN(row.forecast_confidence ?? nested.forecast_confidence),
      top_topic_pressure: safeN(row.top_topic_pressure ?? nested.top_topic_pressure),
      top_topics: Array.isArray(row.top_topics)
        ? (row.top_topics as string[])
        : Array.isArray(nested.top_topics)
        ? (nested.top_topics as string[])
        : [],
    };
  });
}

function readPredictionLogsCache(): PredictionLog[] {
  try {
    const raw = localStorage.getItem(PREDICTION_LOGS_CACHE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as PredictionLog[]) : [];
  } catch {
    return [];
  }
}

function writePredictionLogsCache(logs: PredictionLog[]) {
  try {
    localStorage.setItem(PREDICTION_LOGS_CACHE_KEY, JSON.stringify(logs.slice(0, 1000)));
  } catch {
    // Ignore localStorage write failures.
  }
}

function readCurrentPredictionCache(): PredictionData | null {
  try {
    const raw = localStorage.getItem(CURRENT_PREDICTION_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PredictionData;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function writeCurrentPredictionCache(prediction: PredictionData) {
  try {
    localStorage.setItem(CURRENT_PREDICTION_CACHE_KEY, JSON.stringify(prediction));
  } catch {
    // Ignore localStorage write failures.
  }
}

function parseTimestampMs(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const direct = new Date(trimmed).getTime();
  if (Number.isFinite(direct)) return direct;
  const normalized = trimmed.includes(" ") && !trimmed.includes("T")
    ? trimmed.replace(" ", "T")
    : trimmed;
  const secondPass = new Date(normalized).getTime();
  return Number.isFinite(secondPass) ? secondPass : null;
}

function normalizeUnitValue(value: unknown, fallback = 0): number {
  const n = safeN(value, fallback);
  if (n > 1 && n <= 100) return n / 100;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

function toHundredScale(value: unknown, fallback = 0): number {
  const n = safeN(value, fallback);
  if (n < 0) return 0;
  if (n <= 1.5) return n * 100;
  if (n > 100) return 100;
  return n;
}

function toNormalizedScale(value: unknown, fallback = 0): number {
  const n = safeN(value, fallback);
  if (n < 0) return 0;
  if (n <= 1.5) return n;
  if (n <= 100) return n / 100;
  return 1;
}

function preferHundredScale(primary: unknown, secondary: unknown, fallback = 0): number {
  const primaryValue = Number(primary);
  if (Number.isFinite(primaryValue) && Math.abs(primaryValue) > 0) {
    return toHundredScale(primaryValue, fallback);
  }
  return toHundredScale(secondary, fallback);
}

function formatInsightMetric(value: number, defaultText = "N/A"): string {
  if (!Number.isFinite(value)) return defaultText;
  const abs = Math.abs(value);
  if (abs > 0 && abs < 0.01) return value.toFixed(4);
  return value.toFixed(2);
}

function normalizeSeverityLevel(value: unknown): number {
  const level = Math.round(safeN(value, 1));
  return Math.max(1, Math.min(10, level));
}

function getSeverityLabel(level: number): string {
  if (level >= 9) return "Critical";
  if (level >= 7) return "High";
  if (level >= 4) return "Moderate";
  return "Low";
}

function normalizeEventTypeLabel(value: unknown): string {
  const raw = String(value ?? "").trim();
  if (!raw) return "Risk Signal";
  const normalized = raw.replace(/[_.-]+/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
  if (normalized === "country risk signal") return "Country Risk Shift";
  return normalized
    .split(" ")
    .map((token) => token ? token[0].toUpperCase() + token.slice(1) : "")
    .join(" ");
}

function filterLogsForTimeframe(logs: PredictionLog[], timeframe: Timeframe): PredictionLog[] {
  const now = Date.now();
  const windowMsByTimeframe: Record<Timeframe, number> = {
    "1h": 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
  };

  const windowMs = windowMsByTimeframe[timeframe];
  return logs
    .filter((log) => {
      const ts = parseTimestampMs(log.timestamp);
      return ts !== null && now - ts <= windowMs;
    })
    .sort((a, b) => {
      const aTs = parseTimestampMs(a.timestamp) ?? 0;
      const bTs = parseTimestampMs(b.timestamp) ?? 0;
      return aTs - bTs;
    });
}
function computePearsonCorrelation(a: number[], b: number[]): number | null {
  const n = Math.min(a.length, b.length);
  if (n < 2) return null;
  const x = a.slice(0, n);
  const y = b.slice(0, n);
  const meanX = x.reduce((sum, v) => sum + v, 0) / n;
  const meanY = y.reduce((sum, v) => sum + v, 0) / n;
  let num = 0;
  let denX = 0;
  let denY = 0;
  for (let i = 0; i < n; i += 1) {
    const dx = x[i] - meanX;
    const dy = y[i] - meanY;
    num += dx * dy;
    denX += dx * dx;
    denY += dy * dy;
  }
  const den = Math.sqrt(denX * denY);
  if (!Number.isFinite(den) || den <= 1e-9) return null;
  return Math.max(-1, Math.min(1, num / den));
}
function buildLogsFromHistory(rows: HistoricalDataPoint[]): PredictionLog[] {
  return rows.map((row, idx) => ({
    _id: `history-${idx}`,
    timestamp: row.timestamp || new Date().toISOString(),
    model_version: "history-derived",
    schema_version: "expanded_global_v1",
    feature_names: MODEL_FEATURE_DEFS.map((item) => item.key),
    features: MODEL_FEATURE_DEFS.map((item) => safeN((row as unknown as Record<string, unknown>)[item.key])),
    prediction: safeN(row.risk_score) / 100,
    probability: safeN(row.risk_score) / 100,
    drift_score: null,
    role: "system",
  }));
}

function deriveSentimentForecastFromHistory(rows: HistoricalDataPoint[]): SentimentForecast | null {
  if (!rows.length) return null;
  const riskSeries = rows.map((row) => safeN(row.risk_score)).filter((value) => Number.isFinite(value));
  if (!riskSeries.length) return null;
  const last = rows[rows.length - 1];
  const current = safeN(last.risk_score, riskSeries[riskSeries.length - 1]);
  const first = riskSeries[0];
  const confidence = rows.length >= 6 ? 0.75 : 0.55;
  const proposed24 = current + ((riskSeries.length >= 2 ? (riskSeries[riskSeries.length - 1] - first) / Math.max(1, riskSeries.length - 1) : 0) * 24);
  const recentPeak = Math.max(current, ...riskSeries.slice(-12));
  const supportFloor = Math.max(
    current >= 65 ? current - 6 : current >= 50 ? current - 8 : current - 12,
    recentPeak - (current >= 65 ? 8 : 12),
  );
  const target24 = Math.max(Math.min(proposed24, 100), Math.max(0, supportFloor));
  const interpolate = (hours: number) => {
    if (hours >= 24) return target24;
    const progress = 1 - Math.exp(-hours / 9);
    return current + ((target24 - current) * progress);
  };
  const forecast1h = interpolate(1);
  const forecast6h = interpolate(6);
  const forecast24h = target24;
  const forecast7d = Math.max(supportFloor, forecast24h + Math.max(0, forecast24h - current) * 0.35);

  return {
    timestamp: last.timestamp || new Date().toISOString(),
    current_sentiment: current,
    forecast_1h: forecast1h,
    forecast_6h: forecast6h,
    forecast_24h: forecast24h,
    forecast_7d: forecast7d,
    confidence,
    source: "bounded_risk_projection",
    source_status: "derived_estimate",
    model_version: "history_structural_projection_v2",
    calibration_status: "structural_guarded",
    prediction_interval: null,
    fallback_reason: "Derived in the client from historical risk support so weak trend noise cannot force an unrealistic unwind.",
    data_quality_status: "estimated",
    advisory: "Structurally bounded risk outlook",
    reasons: ["client-side structural support"],
  };
}

function deriveMarketReactionsFromHistory(rows: HistoricalDataPoint[]): MarketReaction[] {
  if (rows.length < 2) return [];

  const reactions: MarketReaction[] = [];
  for (let i = 1; i < rows.length; i += 1) {
    const prev = rows[i - 1];
    const curr = rows[i];
    const crypto = safeN(curr.crypto_return) - safeN(prev.crypto_return);
    const stock = safeN(curr.stock_return) - safeN(prev.stock_return);
    reactions.push({
      timestamp: curr.timestamp || new Date().toISOString(),
      event_type: "Feature shift",
      sentiment_impact: safeN(curr.news_sentiment) - safeN(prev.news_sentiment),
      crypto_reaction: crypto,
      stock_reaction: stock,
      correlation_strength: Math.min(1, Math.abs(crypto + stock)),
    });
  }

  return reactions.slice(-30).reverse();
}

function PanelHeader({
  title,
  subtitle,
  status,
}: {
  title: string;
  subtitle: string;
  status: PanelStatus;
}) {
  const statusLabel = status === "live" ? "Live" : status === "error" ? "Error" : "No data";
  return (
    <div className="prediction-card-head">
      <div className="prediction-card-title-wrap">
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>
      <span className={`prediction-status prediction-status-${status}`}>{statusLabel}</span>
    </div>
  );
}

function DeferredPanelPlaceholder({ label }: { label: string }) {
  return (
    <div className="prediction-empty">
      <p>{label}</p>
    </div>
  );
}


function formatSourceLabel(value: unknown): string {
  const raw = String(value ?? "").trim();
  if (!raw) return "Unknown";
  const normalized = raw.replace(/[_.-]+/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
  if (normalized === "live model") return "Live model";
  if (normalized === "degraded live model") return "Live model (degraded)";
  if (normalized === "derived estimate") return "Derived estimate";
  if (normalized === "historical reconstruction") return "Historical reconstruction";
  if (normalized === "trend extrapolation") return "Trend extrapolation";
  if (normalized === "playback reconstruction") return "Playback reconstruction";
  if (normalized === "fallback") return "Fallback";
  if (normalized === "model unavailable") return "Model unavailable";
  return normalized.split(" ").map((token) => token ? token[0].toUpperCase() + token.slice(1) : "").join(" ");
}

function isLiveModelStatus(value: unknown): boolean {
  return String(value ?? "").trim().toLowerCase() === "live_model";
}

function summarizeTrustQuality(snapshot: TrustReliabilitySnapshot | null): { label: string; detail: string } {
  const qualityGate = (snapshot?.quality_gate ?? {}) as Record<string, unknown>;
  const active = Boolean(qualityGate.active);
  const message = typeof qualityGate.message === "string" && qualityGate.message
    ? qualityGate.message
    : active
    ? "Reliability degraded"
    : "Coverage healthy";
  const reasons = Array.isArray(qualityGate.reasons)
    ? qualityGate.reasons.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    : [];
  return {
    label: active ? "Degraded" : "Healthy",
    detail: reasons.length ? `${message}: ${reasons.join(" | ")}` : message,
  };
}

export default function TrendPrediction() {
  const navigate = useNavigate();
  const token = localStorage.getItem("token");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [predictionLogs, setPredictionLogs] = useState<PredictionLog[]>(() => readPredictionLogsCache());
  const [sentimentForecast, setSentimentForecast] = useState<SentimentForecast | null>(null);
  const [marketReactions, setMarketReactions] = useState<MarketReaction[]>([]);
  const [eventPredictions, setEventPredictions] = useState<EventPrediction[]>([]);
  const [latestFeatures, setLatestFeatures] = useState<number[]>([]);
  const [latestFeatureNames, setLatestFeatureNames] = useState<string[]>(DEFAULT_FEATURE_NAMES);
  const [latestFeatureKeys, setLatestFeatureKeys] = useState<string[]>(DEFAULT_FEATURE_KEYS);
  const [, setLatestFeaturesLoaded] = useState(false);
  const [currentPrediction, setCurrentPrediction] = useState<PredictionData | null>(() => readCurrentPredictionCache());
  const [selectedTimeframe, setSelectedTimeframe] = useState<Timeframe>("24h");
  const [modelEnsemble, setModelEnsemble] = useState<MLModel[]>([]);
  const [governanceData, setGovernanceData] = useState<GovernanceData>({
    models: [],
    disagreement: [],
    calibrationTrend: [],
    calibrationTrendByModel: {},
    selectedCalibrationModel: undefined,
  });
  const [riskMap, setRiskMap] = useState<RiskMapPoint[]>([]);
  const [historicalData, setHistoricalData] = useState<HistoricalDataPoint[]>([]);
  const [plotlyReady, setPlotlyReady] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");
  const [lastCanonicalRefreshAt, setLastCanonicalRefreshAt] = useState("");
  const [playbackFrame, setPlaybackFrame] = useState<SnapshotLike | null>(null);
  const [playbackActive, setPlaybackActive] = useState(false);
  const [showHeavyPanels, setShowHeavyPanels] = useState(false);
  const [trustSnapshot, setTrustSnapshot] = useState<TrustReliabilitySnapshot | null>(null);
  const [advancedInsights, setAdvancedInsights] = useState<AdvancedInsightsData | null>(null);
  const [latestGlobalDoc, setLatestGlobalDoc] = useState<LatestGlobalResponse | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const mlChartRef = useRef<HTMLDivElement | null>(null);
  const sentimentChartRef = useRef<HTMLDivElement | null>(null);
  const marketChartRef = useRef<HTMLDivElement | null>(null);
  const featureChartRef = useRef<HTMLDivElement | null>(null);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);
  const loadRequestIdRef = useRef(0);
  const hasLoadedOnceRef = useRef(false);

  function finishPrimaryLoad(requestId: number) {
    if (requestId !== loadRequestIdRef.current) return;
    setLastUpdatedAt(new Date().toISOString());
    setLoading(false);
    setRefreshing(false);
    hasLoadedOnceRef.current = true;
  }

  useEffect(() => {
    if (!token) {
      navigate("/login");
      return;
    }
    loadData({ showSpinner: !hasLoadedOnceRef.current });
  }, [token, navigate, selectedTimeframe]);

  useEffect(() => {
    setShowHeavyPanels(false);
    const timer = window.setTimeout(() => {
      setShowHeavyPanels(true);
    }, 200);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!token || playbackActive) return undefined;
    const interval = window.setInterval(() => {
      loadData({ showSpinner: false });
    }, AUTO_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [token, playbackActive, selectedTimeframe]);

  async function loadPlotly() {
    if (plotlyRef.current) return plotlyRef.current;
    if (!plotlyLoadingRef.current) {
      plotlyLoadingRef.current = import("plotly.js-dist-min")
        .then((mod) => {
          plotlyRef.current = (mod as any).default ?? mod;
          setPlotlyReady(true);
          return plotlyRef.current;
        })
        .catch((e) => {
          plotlyLoadingRef.current = null;
          throw e;
        });
    }
    return plotlyLoadingRef.current;
  }

  async function loadData(options: { showSpinner?: boolean } = {}) {
    const showSpinner = Boolean(options.showSpinner);
    const requestId = ++loadRequestIdRef.current;
    if (showSpinner || !hasLoadedOnceRef.current) {
      setLoading(true);
      setLatestFeaturesLoaded(false);
    } else {
      setRefreshing(true);
    }
    setError("");

    try {
      loadPlotly().catch((e) => {
        console.error("Failed to load Plotly:", e);
        if (requestId === loadRequestIdRef.current) {
          setError((current) => current || "Failed to initialize chart engine");
        }
      });

      const logLimits: Record<Timeframe, number> = {
        "1h": 24,
        "6h": 120,
        "24h": 240,
        "7d": 1000,
      };
      const { start, end } = computeRangeForTimeframe(selectedTimeframe);

      const logsPromise = predictionService.getPredictionLogs(logLimits[selectedTimeframe]);
      const featuresPromise = API.get("/features/global/latest", {
        headers: API_HEADERS,
        params: { mode: "online" },
      });
      const trustPromise = getTrustReliability("online");
      const advancedPromise = getAdvancedInsights();
      let logs: PredictionLog[] = readPredictionLogsCache();
      try {
        const logsRes = await logsPromise;
        const fetchedLogs = Array.isArray(logsRes) ? logsRes : [];
        if (fetchedLogs.length) {
          logs = fetchedLogs;
          writePredictionLogsCache(fetchedLogs);
        }
      } catch (e) {
        console.error("Prediction logs load failed:", e);
      }
      const filteredLogs = filterLogsForTimeframe(logs, selectedTimeframe);
      const effectiveLogs = filteredLogs.length
        ? filteredLogs
        : logs.length
        ? [...logs].sort((a, b) => {
            const aTs = parseTimestampMs(a.timestamp) ?? 0;
            const bTs = parseTimestampMs(b.timestamp) ?? 0;
            return aTs - bTs;
          })
        : filteredLogs;
      if (requestId !== loadRequestIdRef.current) return;
      setPredictionLogs(effectiveLogs);

      let resolvedHistory: HistoricalDataPoint[] = [];

      let features: any = null;
      try {
        const featuresRes = await featuresPromise;
        features = featuresRes.data?.features;
      } catch (e) {
        console.error("Latest features load failed:", e);
      }

      try {
        const trust = await trustPromise;
        if (requestId === loadRequestIdRef.current) setTrustSnapshot(trust);
      } catch (e) {
        console.error("Trust reliability load failed:", e);
      }

      let resolvedCurrentPrediction: PredictionData | null = currentPrediction;
      if (features) {
        const featureProfile = predictionService.buildFeatureProfile(features as Record<string, unknown>);
        const combinedFeatureVector = featureProfile.combinedFeatures.map((item) => safeN(item.value));
        const combinedFeatureNames = featureProfile.combinedFeatures.map((item) => item.label);
        const combinedFeatureKeys = featureProfile.combinedFeatures.map((item) => item.key);
        setLatestFeatures(combinedFeatureVector);
        setLatestFeatureNames(combinedFeatureNames);
        setLatestFeatureKeys(combinedFeatureKeys);
        setLatestFeaturesLoaded(true);
        const unifiedRiskUnit = normalizeUnitValue(
          features.system_global_risk_score ?? features.global_risk_score,
          0.5,
        );
        const baseProfile = predictionService.buildFeatureProfile(features as Record<string, unknown>);
        const basePrediction: PredictionData = {
          timestamp: new Date().toISOString(),
          prediction: unifiedRiskUnit,
          probability: unifiedRiskUnit,
          raw_probability: unifiedRiskUnit,
          inference_probability: unifiedRiskUnit,
          intelligence_adjustment: 0,
          intelligence_pressure: baseProfile.intelligencePressure,
          confidence_weight: baseProfile.confidenceWeight,
          model_version: "global_snapshot_contract",
          features: combinedFeatureVector,
          feature_names: combinedFeatureNames,
          feature_keys: combinedFeatureKeys,
          source: "global_features_latest",
          source_status: "derived_estimate",
          calibration_status: "not_calibrated",
          prediction_interval: null,
          fallback_reason: "Displayed from latest global risk features while canonical forecast sync completes.",
          data_quality_status: "estimated",
          advisory: "Live global snapshot",
          reasons: ["no live model response"],
        };

        setCurrentPrediction(basePrediction);
        writeCurrentPredictionCache(basePrediction);
        resolvedCurrentPrediction = basePrediction;

      }

      // Real-data fallback #1: latest prediction-log features.
      if (!features && Array.isArray(effectiveLogs) && effectiveLogs.length) {
        const latestLogFeatures = Array.isArray(effectiveLogs[effectiveLogs.length - 1]?.features)
          ? effectiveLogs[effectiveLogs.length - 1].features
          : [];
        if (latestLogFeatures.length >= 7) {
          setLatestFeatures(latestLogFeatures.map((v: unknown) => safeN(v)));
          const latestLogNames = Array.isArray(effectiveLogs[effectiveLogs.length - 1]?.feature_names)
            ? effectiveLogs[effectiveLogs.length - 1].feature_names!
            : DEFAULT_FEATURE_NAMES.slice(0, latestLogFeatures.length);
          setLatestFeatureNames(latestLogNames.map((name, idx) => MODEL_FEATURE_DEFS.find((item) => item.key === name)?.label || name || `Feature ${idx + 1}`));
          setLatestFeatureKeys(latestLogNames.slice(0, latestLogFeatures.length));
          setLatestFeaturesLoaded(true);
        }
      }

      // Real-data fallback #2: latest historical row features.
      // Real-data fallback #2: derive current prediction from latest prediction log.
      if (!resolvedCurrentPrediction && effectiveLogs.length) {
        const latestLog = effectiveLogs[effectiveLogs.length - 1];
        const fallbackFeatures = Array.isArray(latestLog.features)
          ? latestLog.features.map((v: unknown) => safeN(v))
          : latestFeatures;
        const fallbackPrediction = {
          timestamp: latestLog.timestamp || new Date().toISOString(),
          prediction: safeN(latestLog.prediction),
          probability: safeN(latestLog.probability, 0.5),
          raw_probability: safeN(latestLog.probability, 0.5),
          inference_probability: safeN(latestLog.probability, 0.5),
          model_version: latestLog.model_version || "unknown",
          features: fallbackFeatures,
          feature_names: Array.isArray(latestLog.feature_names) && latestLog.feature_names.length === fallbackFeatures.length
            ? latestLog.feature_names.map((name, idx) => MODEL_FEATURE_DEFS.find((item) => item.key === name)?.label || name || `Feature ${idx + 1}`)
            : DEFAULT_FEATURE_NAMES.slice(0, fallbackFeatures.length),
          feature_keys: Array.isArray(latestLog.feature_names) && latestLog.feature_names.length === fallbackFeatures.length
            ? latestLog.feature_names
            : DEFAULT_FEATURE_KEYS.slice(0, fallbackFeatures.length),
          drift_score: latestLog.drift_score ?? undefined,
          source: "prediction_log_cache",
          source_status: "historical_reconstruction",
          calibration_status: "unknown",
          prediction_interval: null,
          fallback_reason: "Reconstructed from the latest stored prediction log because live inference was unavailable.",
          data_quality_status: "estimated",
          advisory: "Historical reconstruction",
          reasons: ["prediction log fallback"],
        };
        setCurrentPrediction(fallbackPrediction);
        writeCurrentPredictionCache(fallbackPrediction);
        resolvedCurrentPrediction = fallbackPrediction;
      }

      finishPrimaryLoad(requestId);

      const [advancedResult, governanceResult, forecastResult, reactionsResult, eventsResult, mapResult, historyResult, globalResult] = await Promise.allSettled([
        advancedPromise,
        getGovernanceData(),
        predictionService.getSentimentForecast(),
        predictionService.getMarketReactions(30),
        predictionService.getEventPredictions(233),
        getRiskMap(),
        predictionService.getHistoricalData(start, end, selectedTimeframe === "7d" ? 1000 : 400),
        getLatestGlobalFeatures(),
      ]);

      if (requestId !== loadRequestIdRef.current) return;

      resolvedHistory = historyResult.status === "fulfilled"
        ? normalizeHistoricalRows(historyResult.value as unknown[])
        : [];
      setHistoricalData(resolvedHistory);

      if (globalResult.status === "fulfilled") {
        setLatestGlobalDoc(globalResult.value);
      }

      if (advancedResult.status === "fulfilled") {
        const advancedPayload = advancedResult.value;
        setAdvancedInsights(advancedPayload);
        setLastCanonicalRefreshAt(String(advancedPayload.generated_at || advancedPayload.timestamp || new Date().toISOString()));

        const directGovernance = governanceResult.status === "fulfilled" ? governanceResult.value : null;
        const payloadGovernance = advancedPayload.governance ?? null;
        const governance = directGovernance && (!payloadGovernance || directGovernance.models.length >= payloadGovernance.models.length)
          ? directGovernance
          : payloadGovernance;

        if (governance) {
          setGovernanceData(governance);
          setModelEnsemble(
            governance.models.map((m, idx) => ({
              name: m.name,
              vote: normalizeRisk(m.vote ?? 50),
              confidence: safeN(m.confidence, m.calibration),
              color: ["#22d3ee", "#a3e635", "#60a5fa", "#f472b6", "#fbbf24"][idx % 5],
            })),
          );
        } else {
          setGovernanceData({ models: [], disagreement: [], calibrationTrend: [], calibrationTrendByModel: {}, selectedCalibrationModel: undefined });
          setModelEnsemble([]);
        }

        const forecastContract = advancedPayload.forecast_contract;
        const primaryForecast = Array.isArray(advancedPayload.predictions?.predictions) ? advancedPayload.predictions.predictions[0] : undefined;
        if (primaryForecast || forecastContract) {
          const canonicalRiskUnit = forecastContract?.risk_score != null
            ? normalizeUnitValue(safeN(forecastContract.risk_score, 50), 0.5)
            : normalizeUnitValue(safeN(primaryForecast?.risk_score, 50), 0.5);
          const snapshot = Array.isArray(advancedPayload.feature_snapshot) ? advancedPayload.feature_snapshot : [];
          const snapshotValues = snapshot.map((item) => safeN(item.value));
          const snapshotNames = snapshot.map((item) => item.label || item.key);
          const snapshotKeys = snapshot.map((item) => item.key);
          const canonicalPrediction: PredictionData = {
            ...(resolvedCurrentPrediction || {
              timestamp: advancedPayload.timestamp || new Date().toISOString(),
              prediction: canonicalRiskUnit,
              probability: canonicalRiskUnit,
              model_version: String(forecastContract?.model_version || advancedPayload.ml_observability?.model_version || advancedPayload.predictions?.model_type || "advanced_analytics"),
              features: snapshotValues.length ? snapshotValues : latestFeatures,
            }),
            timestamp: advancedPayload.timestamp || new Date().toISOString(),
            prediction: forecastContract?.withheld ? 0 : canonicalRiskUnit,
            probability: forecastContract?.withheld ? 0 : canonicalRiskUnit,
            raw_probability: forecastContract?.withheld ? 0 : canonicalRiskUnit,
            inference_probability: forecastContract?.withheld ? 0 : canonicalRiskUnit,
            confidence_weight: forecastContract?.withheld ? 0 : safeN(forecastContract?.confidence_ratio, safeN(primaryForecast?.confidence, canonicalRiskUnit)),
            model_version: String(forecastContract?.model_version || advancedPayload.ml_observability?.model_version || advancedPayload.predictions?.model_type || "advanced_analytics"),
            features: snapshotValues.length ? snapshotValues : (resolvedCurrentPrediction?.features || latestFeatures),
            feature_names: snapshotNames.length ? snapshotNames : (resolvedCurrentPrediction?.feature_names || latestFeatureNames),
            feature_keys: snapshotKeys.length ? snapshotKeys : (resolvedCurrentPrediction?.feature_keys || latestFeatureKeys),
            source: advancedPayload.predictions?.source || forecastContract?.source,
            source_status: forecastContract?.source_status || advancedPayload.predictions?.source_status,
            calibration_status: forecastContract?.calibration_status || advancedPayload.predictions?.calibration_status,
            prediction_interval: forecastContract?.prediction_interval ?? primaryForecast?.interval ?? null,
            fallback_reason: advancedPayload.predictions?.fallback_reason ?? forecastContract?.advisory ?? null,
            data_quality_status: advancedPayload.data_quality_status || forecastContract?.quality_status,
            advisory: forecastContract?.advisory || advancedPayload.advisory,
            reasons: forecastContract?.reasons || advancedPayload.reasons,
          };
          setCurrentPrediction(canonicalPrediction);
          writeCurrentPredictionCache(canonicalPrediction);
          resolvedCurrentPrediction = canonicalPrediction;
        }
      } else {
        console.error("Advanced insights load failed:", advancedResult.reason);
        setAdvancedInsights(null);
        setLastCanonicalRefreshAt("");
        if (governanceResult.status === "fulfilled") {
          const governance = governanceResult.value;
          setGovernanceData(governance);
          setModelEnsemble(
            governance.models.map((m, idx) => ({
              name: m.name,
              vote: normalizeRisk(m.vote ?? 50),
              confidence: safeN(m.confidence, m.calibration),
              color: ["#22d3ee", "#a3e635", "#60a5fa", "#f472b6", "#fbbf24"][idx % 5],
            })),
          );
        } else {
          setGovernanceData({ models: [], disagreement: [], calibrationTrend: [], calibrationTrendByModel: {}, selectedCalibrationModel: undefined });
          setModelEnsemble([]);
        }
      }

      if (forecastResult.status === "fulfilled") {
        setSentimentForecast(forecastResult.value);
      } else {
        console.error("Sentiment forecast load failed:", forecastResult.reason);
        setSentimentForecast(deriveSentimentForecastFromHistory(resolvedHistory));
      }

      if (reactionsResult.status === "fulfilled") {
        setMarketReactions(Array.isArray(reactionsResult.value) ? reactionsResult.value : []);
      } else {
        console.error("Market reactions load failed:", reactionsResult.reason);
        setMarketReactions(deriveMarketReactionsFromHistory(resolvedHistory));
      }

      if (eventsResult.status === "fulfilled") {
        setEventPredictions(Array.isArray(eventsResult.value) ? eventsResult.value : []);
      } else {
        console.error("Event predictions load failed:", eventsResult.reason);
        setEventPredictions([]);
      }

      if (mapResult.status === "fulfilled") {
        setRiskMap(mapResult.value);
      } else {
        setRiskMap([]);
        console.error("Risk map load failed:", mapResult.reason);
      }

      if (historyResult.status !== "fulfilled") {
        console.error("Historical deep-intel load failed:", historyResult.reason);
      }

      if (!features && resolvedHistory.length) {
        const latestRow = resolvedHistory[resolvedHistory.length - 1];
        setLatestFeatures(MODEL_FEATURE_DEFS.map((item) => safeN((latestRow as unknown as Record<string, unknown>)[item.key])));
        setLatestFeatureNames(MODEL_FEATURE_DEFS.map((item) => item.label));
        setLatestFeatureKeys(MODEL_FEATURE_DEFS.map((item) => item.key));
        setLatestFeaturesLoaded(true);
      }

      if (!effectiveLogs.length && resolvedHistory.length) {
        const historyLogs = buildLogsFromHistory(resolvedHistory);
        setPredictionLogs(historyLogs);
        writePredictionLogsCache(historyLogs);
        if (!resolvedCurrentPrediction && historyLogs.length) {
          const latest = historyLogs[historyLogs.length - 1];
          const historyFeatures = Array.isArray(latest.features) ? latest.features.map((v: unknown) => safeN(v)) : latestFeatures;
          const fromHistoryPrediction: PredictionData = {
            timestamp: latest.timestamp,
            prediction: safeN(latest.prediction),
            probability: safeN(latest.probability, 0.5),
            raw_probability: safeN(latest.probability, 0.5),
            inference_probability: safeN(latest.probability, 0.5),
            model_version: latest.model_version || "history-derived",
            features: historyFeatures,
            feature_names: Array.isArray(latest.feature_names) && latest.feature_names.length === historyFeatures.length
              ? latest.feature_names.map((name, idx) => MODEL_FEATURE_DEFS.find((item) => item.key === name)?.label || name || `Feature ${idx + 1}`)
              : DEFAULT_FEATURE_NAMES.slice(0, historyFeatures.length),
            feature_keys: Array.isArray(latest.feature_names) && latest.feature_names.length === historyFeatures.length
              ? latest.feature_names
              : DEFAULT_FEATURE_KEYS.slice(0, historyFeatures.length),
            drift_score: latest.drift_score ?? undefined,
            source: "historical_feature_rows",
            source_status: "historical_reconstruction",
            calibration_status: "unknown",
            prediction_interval: null,
            fallback_reason: "Built from historical feature rows because neither live inference nor prediction logs were available.",
            data_quality_status: "estimated",
            advisory: "Historical reconstruction",
            reasons: ["history-derived fallback"],
          };
          setCurrentPrediction(fromHistoryPrediction);
          writeCurrentPredictionCache(fromHistoryPrediction);
        }
      }
    } catch (err: any) {
      if (requestId !== loadRequestIdRef.current) return;
      if (!predictionLogs.length) {
        const cachedLogs = readPredictionLogsCache();
        if (cachedLogs.length) setPredictionLogs(cachedLogs);
      }
      if (!currentPrediction) {
        const cachedPrediction = readCurrentPredictionCache();
        if (cachedPrediction) setCurrentPrediction(cachedPrediction);
      }
      setError(err?.message || "Failed to load prediction data");
      finishPrimaryLoad(requestId);
    }
  }

  const playbackTimestampMs = useMemo(
    () => (playbackActive && playbackFrame ? parseTimestampMs(playbackFrame.timestamp) : null),
    [playbackActive, playbackFrame],
  );

  const visibleHistoricalData = useMemo(() => {
    if (playbackTimestampMs === null) return historicalData;
    const sliced = historicalData.filter((row) => {
      const ts = parseTimestampMs(row.timestamp);
      return ts !== null && ts <= playbackTimestampMs;
    });
    return sliced.length ? sliced : historicalData;
  }, [historicalData, playbackTimestampMs]);

  const activePredictionData = useMemo<PredictionData | null>(() => {
    if (!playbackActive || !playbackFrame) return currentPrediction;
    return {
      timestamp: playbackFrame.timestamp,
      prediction: playbackFrame.score / 100,
      probability: playbackFrame.score / 100,
      model_version: "playback-replay",
      features: MODEL_FEATURE_DEFS.map((item) => safeN(playbackFrame.features[item.key])),
      feature_names: MODEL_FEATURE_DEFS.map((item) => item.label),
      feature_keys: MODEL_FEATURE_DEFS.map((item) => item.key),
      drift_score: currentPrediction?.drift_score,
      source: "historical_playback",
      source_status: "historical_reconstruction",
      calibration_status: "not_applicable",
      prediction_interval: null,
      fallback_reason: "Playback mode rehydrates a historical frame instead of calling live inference.",
      data_quality_status: currentPrediction?.data_quality_status,
      advisory: "Playback reconstruction",
      reasons: ["playback mode"],
    };
  }, [playbackActive, playbackFrame, currentPrediction]);

  const canonicalFeatureSnapshot = useMemo(() => (Array.isArray(advancedInsights?.feature_snapshot) ? advancedInsights.feature_snapshot : []), [advancedInsights]);

  const activeFeatureVector = useMemo<number[]>(() => {
    if (!playbackActive && canonicalFeatureSnapshot.length) {
      return canonicalFeatureSnapshot.map((entry) => safeN(entry.value));
    }
    if (activePredictionData && Array.isArray(activePredictionData.features) && activePredictionData.features.length) {
      return activePredictionData.features.map((v: unknown) => safeN(v));
    }
    return latestFeatures;
  }, [playbackActive, canonicalFeatureSnapshot, activePredictionData, latestFeatures]);

  const activeFeatureNames = useMemo<string[]>(() => {
    if (!playbackActive && canonicalFeatureSnapshot.length === activeFeatureVector.length) {
      return canonicalFeatureSnapshot.map((entry) => entry.label || entry.key);
    }
    if (activePredictionData && Array.isArray(activePredictionData.feature_names) && activePredictionData.feature_names.length === activeFeatureVector.length) {
      return activePredictionData.feature_names;
    }
    if (latestFeatureNames.length === activeFeatureVector.length) {
      return latestFeatureNames;
    }
    if (activeFeatureVector.length <= DEFAULT_FEATURE_NAMES.length) {
      return DEFAULT_FEATURE_NAMES.slice(0, activeFeatureVector.length);
    }
    return activeFeatureVector.map((_, idx) => `Feature ${idx + 1}`);
  }, [playbackActive, canonicalFeatureSnapshot, activePredictionData, activeFeatureVector, latestFeatureNames]);

  const activeFeatureKeys = useMemo<string[]>(() => {
    if (!playbackActive && canonicalFeatureSnapshot.length === activeFeatureVector.length) {
      return canonicalFeatureSnapshot.map((entry) => entry.key);
    }
    if (activePredictionData && Array.isArray(activePredictionData.feature_keys) && activePredictionData.feature_keys.length === activeFeatureVector.length) {
      return activePredictionData.feature_keys;
    }
    if (latestFeatureKeys.length === activeFeatureVector.length) {
      return latestFeatureKeys;
    }
    if (activeFeatureVector.length <= DEFAULT_FEATURE_KEYS.length) {
      return DEFAULT_FEATURE_KEYS.slice(0, activeFeatureVector.length);
    }
    return activeFeatureVector.map((_, idx) => `feature_${idx + 1}`);
  }, [playbackActive, canonicalFeatureSnapshot, activePredictionData, activeFeatureVector, latestFeatureKeys]);

  const activeFeatureEntries = useMemo(
    () => activeFeatureVector.map((value, idx) => ({
      key: activeFeatureKeys[idx] || `feature_${idx + 1}`,
      label: activeFeatureNames[idx] || `Feature ${idx + 1}`,
      value: safeN(value),
    })),
    [activeFeatureKeys, activeFeatureNames, activeFeatureVector],
  );

  const featureImportanceEntries = useMemo(() => {
    if (!playbackActive && canonicalFeatureSnapshot.length) {
      return canonicalFeatureSnapshot
        .map((entry, idx) => {
          const rawValue = safeN((entry as any).raw_value ?? entry.value);
          const displayValue = safeN(entry.value);
          const normalizedValue = safeN((entry as any).normalized_value, rawValue);
          const importance = Math.max(0, safeN((entry as any).importance, Math.abs(normalizedValue) * 100));
          const direction = String((entry as any).direction || (normalizedValue >= 0 ? "positive" : "negative"));
          return {
            key: entry.key || `feature_${idx + 1}`,
            label: entry.label || entry.key || `Feature ${idx + 1}`,
            rawValue,
            displayValue,
            normalizedValue,
            importance,
            direction,
            scale: String((entry as any).scale || "normalized"),
          };
        })
        .sort((left, right) => right.importance - left.importance)
        .slice(0, 10);
    }

    return activeFeatureEntries
      .map((entry) => ({
        key: entry.key,
        label: entry.label,
        rawValue: entry.value,
        displayValue: entry.value,
        normalizedValue: entry.value,
        importance: Math.min(100, Math.abs(entry.value) * 100),
        direction: entry.value >= 0 ? "positive" : "negative",
        scale: "fallback",
      }))
      .sort((left, right) => right.importance - left.importance)
      .slice(0, 10);
  }, [playbackActive, canonicalFeatureSnapshot, activeFeatureEntries]);

  const topRiskDriver = useMemo(() => {
    if (!activeFeatureEntries.length) return "No live feature vector";
    return [...activeFeatureEntries].sort((a, b) => Math.abs(b.value) - Math.abs(a.value))[0]?.label || "No live feature vector";
  }, [activeFeatureEntries]);

  const pressureTrendUp = useMemo(() => {
    const keys = new Set([
      "global_context_index",
      "global_disruption_index",
      "global_economic_stress_index",
      "forecast_risk_score",
      "forecast_risk_delta",
      "top_topic_pressure",
      "contextual_pressure_score",
      "mobility_disruption_score",
      "logistics_stress_score",
      "household_stress_score",
      "energy_stress_score",
    ]);
    const pressureEntries = activeFeatureEntries.filter((entry) => keys.has(entry.key));
    if (!pressureEntries.length) return false;
    const avgPressure = pressureEntries.reduce((sum, entry) => sum + normalizeUnitValue(entry.value, 0), 0) / pressureEntries.length;
    return avgPressure > 0.32;
  }, [activeFeatureEntries]);

  const latestGlobalFeatures = useMemo<Record<string, unknown>>(
    () => ((latestGlobalDoc?.features ?? {}) as Record<string, unknown>),
    [latestGlobalDoc],
  );

  const insightFeatureSnapshot = useMemo(() => {
    const pick = (...keys: string[]) => {
      let zeroCandidate: number | undefined;
      for (const key of keys) {
        const entryValueRaw = activeFeatureEntries.find((entry) => entry.key === key)?.value;
        const entryValue = typeof entryValueRaw === "number" ? entryValueRaw : Number.NaN;
        if (Number.isFinite(entryValue)) {
          if (Math.abs(entryValue) > 0) return entryValue;
          zeroCandidate = entryValue;
        }
        const liveValue = Number(latestGlobalFeatures[key]);
        if (Number.isFinite(liveValue)) {
          if (Math.abs(liveValue) > 0) return liveValue;
          if (zeroCandidate === undefined) zeroCandidate = liveValue;
        }
      }
      return zeroCandidate;
    };

    return {
      directBehavior: pick("direct_behavior_score", "global_behavior_index"),
      contextualPressure: pick("contextual_pressure_score", "global_context_index"),
      evidenceQuality: pick("evidence_quality_score"),
      logisticsStress: pick("logistics_stress_score"),
      householdStress: pick("household_stress_score"),
      energyStress: pick("energy_stress_score"),
    };
  }, [activeFeatureEntries, latestGlobalFeatures]);

  const activeRiskForecast = useMemo<RiskForecastPoint[]>(() => {
    const contractHorizons = Array.isArray(advancedInsights?.forecast_contract?.horizons)
      ? advancedInsights?.forecast_contract?.horizons
      : [];
    if (contractHorizons.length) {
      return contractHorizons.map((item) => ({
        horizon: String(item.label ?? `${safeN(item.hours, 24)}h`),
        risk_score: safeN(item.risk_score, 50),
        confidence: safeN(advancedInsights?.forecast_contract?.confidence_ratio, 0.5),
        p10: safeN(advancedInsights?.forecast_contract?.prediction_interval?.p10, safeN(item.risk_score, 50)),
        p50: safeN(advancedInsights?.forecast_contract?.prediction_interval?.p50, safeN(item.risk_score, 50)),
        p90: safeN(advancedInsights?.forecast_contract?.prediction_interval?.p90, safeN(item.risk_score, 50)),
      }));
    }

    const predictions = advancedInsights?.predictions?.predictions;
    if (Array.isArray(predictions) && predictions.length) {
      return predictions.map((item) => ({
        horizon: String(item.horizon ?? "Unknown"),
        risk_score: safeN(item.risk_score, 50),
        confidence: safeN(item.confidence, 0.5),
        p10: safeN(item.interval?.p10, safeN(item.risk_score, 50)),
        p50: safeN(item.interval?.p50, safeN(item.risk_score, 50)),
        p90: safeN(item.interval?.p90, safeN(item.risk_score, 50)),
      }));
    }

    if (activePredictionData) {
      const currentRisk = normalizeUnitValue(activePredictionData.probability, 0.5) * 100;
      return [{
        horizon: "Current",
        risk_score: currentRisk,
        confidence: safeN(activePredictionData.confidence_weight, safeN(activePredictionData.probability, 0.5)),
        p10: currentRisk,
        p50: currentRisk,
        p90: currentRisk,
      }];
    }

    return [];
  }, [advancedInsights, activePredictionData]);

  const activeSentimentForecast = useMemo<SentimentForecast | null>(() => {
    if (playbackActive) {
      const derived = deriveSentimentForecastFromHistory(visibleHistoricalData);
      if (derived) {
        return {
          ...derived,
          source: "historical_playback",
          source_status: "historical_reconstruction",
          fallback_reason: "Playback mode is replaying historical sentiment rather than showing live forecast service output.",
          advisory: "Playback reconstruction",
          reasons: ["playback mode"],
        };
      }
      return sentimentForecast;
    }
    return sentimentForecast;
  }, [playbackActive, visibleHistoricalData, sentimentForecast]);

  const activeMarketReactions = useMemo<MarketReaction[]>(() => {
    if (playbackActive) {
      return deriveMarketReactionsFromHistory(visibleHistoricalData);
    }
    return marketReactions;
  }, [playbackActive, visibleHistoricalData, marketReactions]);

  const domainSignalHistory = useMemo(() => {
    const rows = playbackActive ? visibleHistoricalData : historicalData;
    return rows.slice(-24).map((row, idx) => {
      const ts = parseTimestampMs(row.timestamp);
      return {
        label: ts !== null ? new Date(ts).toLocaleTimeString() : `Snapshot ${idx + 1}`,
        direct_behavior: preferHundredScale(row.global_behavior_index, row.direct_behavior_score),
        contextual_pressure: preferHundredScale(row.global_context_index, row.contextual_pressure_score),
        attention_pressure: toHundredScale(row.global_attention_index),
        disruption_pressure: toHundredScale(row.global_disruption_index),
        economic_stress: toHundredScale(row.global_economic_stress_index),
        logistics_stress: toHundredScale(row.logistics_stress_score),
        household_stress: toHundredScale(row.household_stress_score),
      };
    });
  }, [playbackActive, visibleHistoricalData, historicalData]);

  const activeEventPredictions = useMemo<EventPrediction[]>(() => {
    if (playbackTimestampMs === null) return eventPredictions;
    const filtered = eventPredictions.filter((row) => {
      const ts = parseTimestampMs(row.timestamp);
      return ts !== null && ts <= playbackTimestampMs;
    });
    return filtered.length ? filtered : eventPredictions;
  }, [eventPredictions, playbackTimestampMs]);

  const mlSeries = useMemo(() => {
    if (!playbackActive && activeRiskForecast.length) {
      return activeRiskForecast.map((point) => ({
        label: point.horizon,
        prediction: normalizeUnitValue(point.risk_score, 0.5),
        probabilityPct: safeN(point.confidence, 0.5) * 100,
      }));
    }

    if (playbackActive && visibleHistoricalData.length) {
      return visibleHistoricalData.map((row, idx) => {
        const ts = parseTimestampMs(row.timestamp);
        const p = normalizeUnitValue(safeN(row.risk_score) / 100, 0.5);
        return {
          label: ts !== null ? new Date(ts).toLocaleString() : `Point ${idx + 1}`,
          prediction: p,
          probabilityPct: p * 100,
        };
      });
    }

    return [];
  }, [playbackActive, activeRiskForecast, visibleHistoricalData]);  // Render ML Prediction Chart

  useEffect(() => {
    if (!mlChartRef.current || !plotlyRef.current || !plotlyReady) return;
    if (!mlSeries.length) return;

    const timestamps = mlSeries.map((point) => point.label);
    const predictions = mlSeries.map((point) => point.prediction);
    const probabilities = mlSeries.map((point) => point.probabilityPct);

    const data = [
      {
        x: timestamps,
        y: predictions,
        type: "scatter",
        mode: "lines+markers",
        name: "Risk Prediction",
        line: { color: "#2f8cff", width: 4, shape: "spline" },
        marker: { size: 8, color: "#2f8cff", line: { color: "#0a1428", width: 2 } },
        fill: "tozeroy",
        fillcolor: "rgba(47, 140, 255, 0.22)",
        hovertemplate: "Risk: %{y:.2f}<extra></extra>",
      },
      {
        x: timestamps,
        y: probabilities,
        type: "scatter",
        mode: "lines+markers",
        name: "Confidence %",
        line: { color: "rgba(173, 189, 214, 0.72)", width: 3, dash: "dot", shape: "spline" },
        marker: { size: 6, color: "rgba(173, 189, 214, 0.9)" },
        yaxis: "y2",
        hovertemplate: "Confidence: %{y:.1f}%<extra></extra>",
      },
    ];

    const layout = {
      title: {
        text: "ML Risk Predictions Over Time",
        font: { color: "#eaf3ff", size: 16 },
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#d6e4ff" },
      hovermode: "x unified",
      hoverlabel: {
        bgcolor: "rgba(10, 25, 46, 0.96)",
        bordercolor: "rgba(125, 211, 252, 0.55)",
        font: { color: "#eaf3ff", size: 12 },
      },
      xaxis: {
        gridcolor: "rgba(148, 163, 184, 0.16)",
        tickfont: { color: "#d6e4ff", size: 12 },
        linecolor: "rgba(148, 163, 184, 0.28)",
        tickcolor: "rgba(148, 163, 184, 0.28)",
        zeroline: false,
      },
      yaxis: {
        title: "Risk Level (0-1)",
        titlefont: { color: "#c4d7ff" },
        gridcolor: "rgba(148, 163, 184, 0.16)",
        tickfont: { color: "#d6e4ff", size: 12 },
        linecolor: "rgba(148, 163, 184, 0.28)",
        tickcolor: "rgba(148, 163, 184, 0.28)",
        zeroline: false,
        range: [0, 1],
      },
      yaxis2: {
        title: "Confidence %",
        titlefont: { color: "#fbbf24" },
        overlaying: "y",
        side: "right",
        range: [0, 100],
        tickfont: { color: "#d7e3f5", size: 12 },
        showgrid: false,
      },
      legend: {
        font: { color: "#d6e4ff" },
        x: 0.02,
        y: 1.12,
        orientation: "h",
        bgcolor: "rgba(12, 31, 56, 0.74)",
        bordercolor: "rgba(96, 165, 250, 0.35)",
        borderwidth: 1,
      },
      margin: { t: 56, r: 66, b: 56, l: 70 },
    };

    plotlyRef.current.react(mlChartRef.current, data, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [mlSeries, plotlyReady]);


  // Render Risk Forecast Chart
  useEffect(() => {
    if (!sentimentChartRef.current || !plotlyRef.current || !plotlyReady) return;
    if (!activeRiskForecast.length && !activeSentimentForecast) return;

    const usingAdvancedForecast = activeRiskForecast.length > 1;
    const forecastPoints = usingAdvancedForecast
      ? activeRiskForecast
      : [{
          horizon: "Current",
          risk_score: safeN(activeSentimentForecast?.current_sentiment, 0),
          confidence: safeN(activeSentimentForecast?.confidence, 0.5),
          p10: safeN(activeSentimentForecast?.current_sentiment, 0),
          p50: safeN(activeSentimentForecast?.current_sentiment, 0),
          p90: safeN(activeSentimentForecast?.current_sentiment, 0),
        }, {
          horizon: "1h",
          risk_score: safeN(activeSentimentForecast?.forecast_1h, 0),
          confidence: safeN(activeSentimentForecast?.confidence, 0.5),
          p10: safeN(activeSentimentForecast?.forecast_1h, 0),
          p50: safeN(activeSentimentForecast?.forecast_1h, 0),
          p90: safeN(activeSentimentForecast?.forecast_1h, 0),
        }, {
          horizon: "6h",
          risk_score: safeN(activeSentimentForecast?.forecast_6h, 0),
          confidence: safeN(activeSentimentForecast?.confidence, 0.5),
          p10: safeN(activeSentimentForecast?.forecast_6h, 0),
          p50: safeN(activeSentimentForecast?.forecast_6h, 0),
          p90: safeN(activeSentimentForecast?.forecast_6h, 0),
        }, {
          horizon: "24h",
          risk_score: safeN(activeSentimentForecast?.forecast_24h, 0),
          confidence: safeN(activeSentimentForecast?.confidence, 0.5),
          p10: safeN(activeSentimentForecast?.forecast_24h, 0),
          p50: safeN(activeSentimentForecast?.forecast_24h, 0),
          p90: safeN(activeSentimentForecast?.forecast_24h, 0),
        }, {
          horizon: "7d",
          risk_score: safeN(activeSentimentForecast?.forecast_7d, safeN(activeSentimentForecast?.forecast_24h, 0)),
          confidence: safeN(activeSentimentForecast?.confidence, 0.5),
          p10: safeN(activeSentimentForecast?.forecast_7d, safeN(activeSentimentForecast?.forecast_24h, 0)),
          p50: safeN(activeSentimentForecast?.forecast_7d, safeN(activeSentimentForecast?.forecast_24h, 0)),
          p90: safeN(activeSentimentForecast?.forecast_7d, safeN(activeSentimentForecast?.forecast_24h, 0)),
        }];

    const x = forecastPoints.map((point) => point.horizon);
    const risk = forecastPoints.map((point) => point.risk_score);
    const p10 = forecastPoints.map((point) => safeN(point.p10, point.risk_score));
    const p90 = forecastPoints.map((point) => safeN(point.p90, point.risk_score));
    const confidence = forecastPoints.map((point) => safeN(point.confidence, 0.5) * 100);

    const forecastData = [
      {
        x,
        y: p90,
        type: "scatter",
        mode: "lines",
        name: "P90",
        line: { color: "rgba(56, 189, 248, 0.0)", width: 0 },
        hoverinfo: "skip",
        showlegend: false,
      },
      {
        x,
        y: p10,
        type: "scatter",
        mode: "lines",
        name: "Prediction Interval",
        line: { color: "rgba(56, 189, 248, 0.0)", width: 0 },
        fill: "tonexty",
        fillcolor: "rgba(56, 189, 248, 0.14)",
        hoverinfo: "skip",
      },
      {
        x,
        y: risk,
        type: "scatter",
        mode: "lines+markers+text",
        name: usingAdvancedForecast ? "Calibrated Risk Forecast" : "Trend Extrapolation",
        line: { color: "#7c9bff", width: 4, shape: "spline" },
        marker: {
          size: 9,
          color: ["#2ad1f5", "#3fa1ff", "#7c9bff", "#b084ff", "#f59e0b"].slice(0, x.length),
          line: { color: "#0a1428", width: 2 },
        },
        text: risk.map((v) => v.toFixed(1)),
        textposition: "top center",
        textfont: { color: "#edf3ff", size: 12 },
        hovertemplate: "Forecast: %{y:.2f}<extra></extra>",
      },
      {
        x,
        y: confidence,
        type: "scatter",
        mode: "lines+markers",
        name: "Confidence %",
        line: { color: "rgba(251, 191, 36, 0.95)", width: 3, dash: "dot" },
        marker: { size: 6, color: "rgba(251, 191, 36, 0.95)" },
        yaxis: "y2",
        hovertemplate: "Confidence: %{y:.1f}%<extra></extra>",
      },
    ];

    const layout = {
      title: {
        text: usingAdvancedForecast ? "Advanced Multi-Horizon Risk Forecast" : `Trend Extrapolation (Confidence: ${(confidence[0] ?? 0).toFixed(0)}%)`,
        font: { color: "#eaf3ff", size: 16 },
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#d6e4ff" },
      hovermode: "x unified",
      hoverlabel: {
        bgcolor: "rgba(10, 25, 46, 0.96)",
        bordercolor: "rgba(125, 211, 252, 0.55)",
        font: { color: "#eaf3ff", size: 12 },
      },
      xaxis: {
        gridcolor: "rgba(148, 163, 184, 0.14)",
        tickfont: { color: "#d6e4ff", size: 12 },
        linecolor: "rgba(148, 163, 184, 0.28)",
        tickcolor: "rgba(148, 163, 184, 0.28)",
        zeroline: false,
      },
      yaxis: {
        title: usingAdvancedForecast ? "Risk Score" : "Sentiment Score",
        titlefont: { color: "#c4d7ff" },
        gridcolor: "rgba(148, 163, 184, 0.16)",
        tickfont: { color: "#d6e4ff", size: 12 },
        linecolor: "rgba(148, 163, 184, 0.28)",
        tickcolor: "rgba(148, 163, 184, 0.28)",
        zeroline: false,
        range: usingAdvancedForecast ? [0, 100] : [-100, 100],
      },
      yaxis2: {
        title: "Confidence %",
        titlefont: { color: "#fbbf24" },
        overlaying: "y",
        side: "right",
        range: [0, 100],
        tickfont: { color: "#d7e3f5", size: 12 },
        showgrid: false,
      },
      legend: {
        font: { color: "#d6e4ff" },
        x: 0.02,
        y: 1.12,
        orientation: "h",
        bgcolor: "rgba(12, 31, 56, 0.74)",
        bordercolor: "rgba(96, 165, 250, 0.35)",
        borderwidth: 1,
      },
      margin: { t: 62, r: 56, b: 56, l: 70 },
    };

    plotlyRef.current.react(sentimentChartRef.current, forecastData, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [activeRiskForecast, activeSentimentForecast, plotlyReady]);

  // Render Feature Importance Chart
  useEffect(() => {
    if (!featureChartRef.current || !plotlyRef.current || !plotlyReady) return;
    if (!featureImportanceEntries.length) return;

    const labels = featureImportanceEntries.map((entry) => entry.label);
    const importance = featureImportanceEntries.map((entry) => safeN(entry.importance, 0));
    const rawLabels = featureImportanceEntries.map((entry) => {
      if (entry.scale === "normalized") return `${entry.displayValue.toFixed(1)}% signal`;
      if (entry.scale === "absolute_100") return `${entry.displayValue.toFixed(1)} / 100`;
      if (entry.scale === "return") return `${entry.displayValue.toFixed(2)}% return`;
      if (entry.scale === "volatility") return `${entry.displayValue.toFixed(2)} vol`;
      return `${entry.displayValue.toFixed(3)}`;
    });
    const markerColors = featureImportanceEntries.map((entry) =>
      entry.direction === "negative" ? "#ff6b6b" : "#38bdf8"
    );

    const data = [
      {
        x: labels,
        y: importance,
        type: "scatter",
        mode: "lines+markers+text",
        name: "Importance",
        line: {
          color: "rgba(167, 139, 250, 0.95)",
          width: 4,
          shape: "spline",
        },
        marker: {
          size: 12,
          color: markerColors,
          line: { color: "#f8fbff", width: 1.5 },
          symbol: "circle",
        },
        fill: "tozeroy",
        fillcolor: "rgba(167, 139, 250, 0.18)",
        text: importance.map((value) => `${value.toFixed(0)}%`),
        textposition: "top center",
        textfont: { color: "#edf3ff", size: 11 },
        customdata: featureImportanceEntries.map((entry, idx) => [rawLabels[idx], entry.direction, entry.key]),
        hovertemplate: "%{x}<br>Importance: %{y:.1f}%<br>Value: %{customdata[0]}<br>Direction: %{customdata[1]}<extra></extra>",
      },
      {
        x: labels,
        y: importance,
        type: "bar",
        name: "Signal Shadow",
        marker: {
          color: markerColors.map((color) => color === "#ff6b6b" ? "rgba(255,107,107,0.18)" : "rgba(56,189,248,0.18)"),
          line: { color: "rgba(255,255,255,0.06)", width: 1 },
        },
        hoverinfo: "skip",
        opacity: 0.55,
      },
    ];

    const layout = {
      title: {
        text: "Animated Feature Importance Signals",
        font: { color: "#eaf3ff", size: 16 },
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#d6e4ff" },
      hovermode: "x unified",
      hoverlabel: {
        bgcolor: "rgba(10, 25, 46, 0.96)",
        bordercolor: "rgba(167, 139, 250, 0.55)",
        font: { color: "#eaf3ff", size: 12 },
      },
      xaxis: {
        gridcolor: "rgba(148, 163, 184, 0.08)",
        tickfont: { color: "#d6e4ff", size: 11 },
        tickangle: -24,
        linecolor: "rgba(148, 163, 184, 0.22)",
        tickcolor: "rgba(148, 163, 184, 0.22)",
        zeroline: false,
      },
      yaxis: {
        title: "Importance %",
        titlefont: { color: "#c4d7ff" },
        gridcolor: "rgba(148, 163, 184, 0.14)",
        tickfont: { color: "#d6e4ff", size: 12 },
        linecolor: "rgba(148, 163, 184, 0.22)",
        tickcolor: "rgba(148, 163, 184, 0.22)",
        zeroline: false,
        range: [0, Math.max(100, Math.ceil(Math.max(0.001, ...featureImportanceEntries.map((entry) => safeN(entry.importance, 0))) / 10) * 10)],
      },
      legend: {
        font: { color: "#d6e4ff" },
        x: 0.02,
        y: 1.12,
        orientation: "h",
        bgcolor: "rgba(12, 31, 56, 0.74)",
        bordercolor: "rgba(167, 139, 250, 0.28)",
        borderwidth: 1,
      },
      margin: { t: 64, r: 28, b: 100, l: 56 },
      bargap: 0.48,
      transition: { duration: 650, easing: "cubic-in-out" },
    };

    plotlyRef.current.react(featureChartRef.current, data, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [featureImportanceEntries, plotlyReady]);

  // Render Cross-Domain Pressure Chart
  useEffect(() => {
    if (!marketChartRef.current || !plotlyRef.current || !plotlyReady) return;
    if (!domainSignalHistory.length) return;

    const labels = domainSignalHistory.map((row) => row.label);
    const data = [
      {
        x: labels,
        y: domainSignalHistory.map((row) => row.contextual_pressure),
        type: "scatter",
        mode: "lines+markers",
        name: "Context Pressure",
        marker: { color: "#2ad1f5", size: 7, line: { color: "#0a1428", width: 2 } },
        line: { color: "#2ad1f5", width: 3, shape: "spline" },
        hovertemplate: "Context: %{y:.2f}<extra></extra>",
      },
      {
        x: labels,
        y: domainSignalHistory.map((row) => row.attention_pressure),
        type: "scatter",
        mode: "lines+markers",
        name: "Attention",
        marker: { color: "#7dd3fc", size: 7, line: { color: "#0b1730", width: 2 } },
        line: { color: "#7dd3fc", width: 3 },
        hovertemplate: "Attention: %{y:.2f}<extra></extra>",
      },
      {
        x: labels,
        y: domainSignalHistory.map((row) => row.disruption_pressure),
        type: "scatter",
        mode: "lines+markers",
        name: "Disruption",
        marker: { color: "#f59e0b", size: 7, line: { color: "#0b1730", width: 2 } },
        line: { color: "#f59e0b", width: 3 },
        hovertemplate: "Disruption: %{y:.2f}<extra></extra>",
      },
      {
        x: labels,
        y: domainSignalHistory.map((row) => row.economic_stress),
        type: "scatter",
        mode: "lines+markers",
        name: "Economic Stress",
        marker: { color: "#f472b6", size: 7, line: { color: "#0b1730", width: 2 } },
        line: { color: "#f472b6", width: 3 },
        hovertemplate: "Economic: %{y:.2f}<extra></extra>",
      },
      {
        x: labels,
        y: domainSignalHistory.map((row) => row.logistics_stress),
        type: "scatter",
        mode: "lines+markers",
        name: "Logistics",
        marker: { color: "#a3e635", size: 7, line: { color: "#0b1730", width: 2 } },
        line: { color: "#a3e635", width: 3, dash: "dot" },
        hovertemplate: "Logistics: %{y:.2f}<extra></extra>",
      },
    ];

    const layout = {
      title: {
        text: "Cross-Domain Pressure Signals",
        font: { color: "#eaf3ff", size: 16 },
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#d6e4ff" },
      hovermode: "x unified",
      hoverlabel: {
        bgcolor: "rgba(10, 25, 46, 0.96)",
        bordercolor: "rgba(125, 211, 252, 0.55)",
        font: { color: "#eaf3ff", size: 12 },
      },
      xaxis: {
        gridcolor: "rgba(148, 163, 184, 0.14)",
        tickfont: { color: "#d6e4ff", size: 12 },
        linecolor: "rgba(148, 163, 184, 0.28)",
        tickcolor: "rgba(148, 163, 184, 0.28)",
        zeroline: false,
        tickangle: -30,
      },
      yaxis: {
        title: "Signal Intensity",
        titlefont: { color: "#c4d7ff" },
        gridcolor: "rgba(148, 163, 184, 0.16)",
        tickfont: { color: "#d6e4ff", size: 12 },
        linecolor: "rgba(148, 163, 184, 0.28)",
        tickcolor: "rgba(148, 163, 184, 0.28)",
        zeroline: false,
      },
      legend: {
        font: { color: "#d6e4ff" },
        x: 0.02,
        y: 1.1,
        orientation: "h",
        bgcolor: "rgba(12, 31, 56, 0.74)",
        bordercolor: "rgba(96, 165, 250, 0.35)",
        borderwidth: 1,
      },
      margin: { t: 56, r: 42, b: 96, l: 70 },
    };

    plotlyRef.current.react(marketChartRef.current, data, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [domainSignalHistory, plotlyReady]);

  // Load Plotly on mount
  useEffect(() => {
    loadPlotly().catch((e) => {
      console.error("Failed to load Plotly:", e);
      setError("Failed to initialize chart engine");
    });
  }, []);

  const disagreement = useMemo(() => {
    if (!modelEnsemble.length) return 0;
    const votes = modelEnsemble.map((m) => m.vote);
    return Number((Math.max(...votes) - Math.min(...votes)).toFixed(2));
  }, [modelEnsemble]);

  const canonicalForecastPoint = useMemo(() => activeRiskForecast.find((point) => String(point.horizon).toLowerCase() === "24h") || activeRiskForecast[0] || null, [activeRiskForecast]);

  const avgConfidence = useMemo(() => {
    const contractConfidence = safeN(advancedInsights?.forecast_contract?.confidence_ratio, NaN);
    if (Number.isFinite(contractConfidence)) {
      return contractConfidence;
    }
    if (activeRiskForecast.length) {
      return activeRiskForecast.reduce((acc, row) => acc + safeN(row.confidence, 0), 0) / activeRiskForecast.length;
    }
    if (!modelEnsemble.length) return 0;
    return modelEnsemble.reduce((acc, m) => acc + m.confidence, 0) / modelEnsemble.length;
  }, [activeRiskForecast, modelEnsemble]);

  const canonicalRiskDisplay = useMemo<number | null>(() => {
    if (String(advancedInsights?.predictions?.source_status ?? "").trim().toLowerCase() === "withheld") return null;
    const liveRisk = safeN((latestGlobalDoc?.features as Record<string, unknown> | undefined)?.global_risk_score, NaN);
    if (Number.isFinite(liveRisk)) return normalizeRisk(liveRisk);
    if (canonicalForecastPoint) return safeN(canonicalForecastPoint.risk_score, 50);
    if (activePredictionData) return normalizeUnitValue(activePredictionData.probability, 0.5) * 100;
    return 50;
  }, [advancedInsights, canonicalForecastPoint, activePredictionData, latestGlobalDoc]);

  const deepHistory = useMemo<SnapshotLike[]>(
    () => historicalData.map((row) => ({
      timestamp: row.timestamp,
      score: normalizeRisk(row.risk_score),
      features: {
        news_sentiment: safeN(row.news_sentiment),
        gdelt_sentiment: safeN(row.gdelt_sentiment),
        crypto_return: safeN(row.crypto_return),
        crypto_volatility: safeN(row.crypto_volatility),
        stock_return: safeN(row.stock_return),
        stock_volatility: safeN(row.stock_volatility),
        weather_anomaly: safeN(row.weather_anomaly),
        direct_behavior_score: safeN(row.direct_behavior_score),
        contextual_pressure_score: safeN(row.contextual_pressure_score),
        evidence_quality_score: safeN(row.evidence_quality_score),
        narrative_velocity_score: safeN(row.narrative_velocity_score),
        coordination_risk_score: safeN(row.coordination_risk_score),
        mobility_disruption_score: safeN(row.mobility_disruption_score),
        logistics_stress_score: safeN(row.logistics_stress_score),
        household_stress_score: safeN(row.household_stress_score),
        fuel_price_pressure: safeN(row.fuel_price_pressure),
        food_price_pressure: safeN(row.food_price_pressure),
        labor_stress_score: safeN(row.labor_stress_score),
        fx_pressure_score: safeN(row.fx_pressure_score),
        remittance_stress_score: safeN(row.remittance_stress_score),
        energy_stress_score: safeN(row.energy_stress_score),
        global_behavior_index: safeN(row.global_behavior_index),
        global_context_index: safeN(row.global_context_index),
        global_attention_index: safeN(row.global_attention_index),
        global_disruption_index: safeN(row.global_disruption_index),
        global_economic_stress_index: safeN(row.global_economic_stress_index),
      },
    })),
    [historicalData],
  );

  const deepHistoryResolved = useMemo<SnapshotLike[]>(() => {
    if (deepHistory.length >= 2) return deepHistory;

    const fromLogs: SnapshotLike[] = predictionLogs
      .filter((log) => Boolean(log?.timestamp))
      .map((log) => {
        const f = Array.isArray(log.features) ? log.features : [];
        return {
          timestamp: log.timestamp,
          score: normalizeRisk((safeN(log.probability, 0.5) * 100)),
          features: {
            news_sentiment: safeN(f[0]),
            gdelt_sentiment: safeN(f[1]),
            crypto_return: safeN(f[2]),
            crypto_volatility: safeN(f[3]),
            stock_return: safeN(f[4]),
            stock_volatility: safeN(f[5]),
            weather_anomaly: safeN(f[6]),
          },
        };
      })
      .slice(-120);
    if (fromLogs.length >= 2) return fromLogs;

    return [];
  }, [deepHistory, predictionLogs, currentPrediction?.probability, latestFeatures]);

  const deepHistoryForPanels = useMemo<SnapshotLike[]>(() => {
    if (playbackTimestampMs === null) return deepHistoryResolved;
    const filtered = deepHistoryResolved.filter((row) => {
      const ts = parseTimestampMs(row.timestamp);
      return ts !== null && ts <= playbackTimestampMs;
    });
    return filtered.length >= 2 ? filtered : deepHistoryResolved;
  }, [deepHistoryResolved, playbackTimestampMs]);

  const activeGlobeData = useMemo(() => {
    const playbackAnchor = deepHistoryForPanels[deepHistoryForPanels.length - 1];
    const playbackRisk = playbackAnchor ? normalizeRisk(playbackAnchor.score) : null;
    const validRiskMap = riskMap.filter((r): r is RiskMapPoint & { risk: number } => typeof r.risk === "number");

    if (validRiskMap.length) {
      return validRiskMap.map((r) => {
        const code = (r.country || "").toUpperCase();
        if (!playbackActive || playbackRisk === null) {
          return {
            country: r.country,
            countryCode: code,
            risk: normalizeRisk(r.risk),
            lat: 0,
            lng: 0,
          };
        }

        const h = hashCountryCode(code);
        const drift = (((h % 17) - 8) / 8) * 3; // deterministic +/-3 spread
        const blended = (normalizeRisk(r.risk) * 0.35) + (playbackRisk * 0.65) + drift;
        return {
          country: r.country,
          countryCode: code,
          risk: normalizeRisk(blended),
          lat: 0,
          lng: 0,
        };
      });
    }

    return [];
  }, [riskMap, deepHistoryForPanels, playbackActive]);

  const comparisonCountries = useMemo(() => {
    const latest = deepHistoryForPanels[deepHistoryForPanels.length - 1];
    const baseFeatures = latest?.features ?? {
      news_sentiment: 0,
      gdelt_sentiment: 0,
      crypto_return: 0,
      crypto_volatility: 0,
      stock_return: 0,
      stock_volatility: 0,
      weather_anomaly: 0,
      direct_behavior_score: 0,
      contextual_pressure_score: 0,
      evidence_quality_score: 0,
      narrative_velocity_score: 0,
      coordination_risk_score: 0,
      mobility_disruption_score: 0,
      logistics_stress_score: 0,
      household_stress_score: 0,
      energy_stress_score: 0,
    };
    const latestTimestamp = latest?.timestamp ?? new Date().toISOString();
    const fromRiskMap = riskMap
      .filter((r): r is RiskMapPoint & { risk: number } => typeof r.risk === "number" && Boolean(r.country))
      .map((r) => {
        const code = (r.country || "").toUpperCase();
        return {
          country: r.country,
          countryCode: code,
          risk: normalizeRisk(toHundredScale(r.risk, 0)),
          timestamp: String((r as Record<string, unknown>).timestamp || latestTimestamp),
          features: {
            news_sentiment: safeN(baseFeatures.news_sentiment),
            gdelt_sentiment: safeN(baseFeatures.gdelt_sentiment),
            crypto_return: safeN(baseFeatures.crypto_return),
            crypto_volatility: safeN(baseFeatures.crypto_volatility),
            stock_return: safeN(baseFeatures.stock_return),
            stock_volatility: safeN(baseFeatures.stock_volatility),
            weather_anomaly: safeN(baseFeatures.weather_anomaly),
            direct_behavior_score: toHundredScale(r.direct_behavior_score, baseFeatures.direct_behavior_score),
            contextual_pressure_score: toHundredScale(r.contextual_pressure_score, baseFeatures.contextual_pressure_score),
            evidence_quality_score: toHundredScale(r.evidence_quality_score, baseFeatures.evidence_quality_score),
            narrative_velocity_score: toNormalizedScale(r.narrative_velocity_score, baseFeatures.narrative_velocity_score),
            coordination_risk_score: toNormalizedScale(r.coordination_risk_score, baseFeatures.coordination_risk_score),
            mobility_disruption_score: toNormalizedScale(r.mobility_disruption_score, baseFeatures.mobility_disruption_score),
            logistics_stress_score: toNormalizedScale(r.logistics_stress_score, baseFeatures.logistics_stress_score),
            household_stress_score: toNormalizedScale(r.household_stress_score, baseFeatures.household_stress_score),
            energy_stress_score: toNormalizedScale(r.energy_stress_score, baseFeatures.energy_stress_score),
          },
        };
      });
    if (fromRiskMap.length >= 2) return fromRiskMap;

    const fallbackFromEvents = Array.from(
      new Set(
        activeEventPredictions.flatMap((e) =>
          (e.affected_regions || [])
            .filter((region) => typeof region === "string" && region.length === 3)
            .map((region) => region.toUpperCase()),
        ),
      ),
    ).slice(0, 8).map((code, idx) => ({
      country: code,
      countryCode: code,
      risk: normalizeRisk(45 + (idx * 7) + (activeEventPredictions[idx]?.predicted_risk_increase ?? 0)),
      timestamp: latestTimestamp,
      features: {
        news_sentiment: safeN(baseFeatures.news_sentiment + idx * 0.03),
        gdelt_sentiment: safeN(baseFeatures.gdelt_sentiment - idx * 0.02),
        crypto_return: safeN(baseFeatures.crypto_return + idx * 0.01),
        crypto_volatility: safeN(Math.max(0, baseFeatures.crypto_volatility + idx * 0.01)),
        stock_return: safeN(baseFeatures.stock_return - idx * 0.008),
        stock_volatility: safeN(Math.max(0, baseFeatures.stock_volatility + idx * 0.012)),
        weather_anomaly: safeN(Math.max(0, baseFeatures.weather_anomaly + idx * 0.02)),
        direct_behavior_score: toHundredScale(baseFeatures.direct_behavior_score + idx * 0.02),
        contextual_pressure_score: toHundredScale(baseFeatures.contextual_pressure_score + idx * 0.025),
        evidence_quality_score: toHundredScale(Math.max(0, baseFeatures.evidence_quality_score - idx * 0.01)),
        narrative_velocity_score: safeN(Math.max(0, baseFeatures.narrative_velocity_score + idx * 0.015)),
        coordination_risk_score: safeN(Math.max(0, baseFeatures.coordination_risk_score + idx * 0.02)),
        mobility_disruption_score: safeN(Math.max(0, baseFeatures.mobility_disruption_score + idx * 0.018)),
        logistics_stress_score: safeN(Math.max(0, baseFeatures.logistics_stress_score + idx * 0.02)),
        household_stress_score: safeN(Math.max(0, baseFeatures.household_stress_score + idx * 0.018)),
        energy_stress_score: safeN(Math.max(0, baseFeatures.energy_stress_score + idx * 0.017)),
      },
    }));

    return fallbackFromEvents;
  }, [deepHistoryForPanels, riskMap, activeEventPredictions]);

  const marketCorrelation = useMemo(() => {
    if (!activeMarketReactions.length) return null;
    const sentiment = activeMarketReactions.map((row) => safeN(row.sentiment_impact));
    const market = activeMarketReactions.map((row) => (safeN(row.crypto_reaction) + safeN(row.stock_reaction)) / 2);
    const pearson = computePearsonCorrelation(sentiment, market);
    if (pearson !== null) return pearson;
    const avgFallback = activeMarketReactions.reduce((acc, row) => acc + safeN(row.correlation_strength), 0) / activeMarketReactions.length;
    return Number.isFinite(avgFallback) ? avgFallback : null;
  }, [activeMarketReactions]);

  const canonicalSourceStatus = String(advancedInsights?.forecast_contract?.source_status ?? advancedInsights?.predictions?.source_status ?? activePredictionData?.source_status ?? "").trim().toLowerCase();
  const predictionsWithheld = canonicalSourceStatus === "withheld";
  const trustQuality = summarizeTrustQuality(trustSnapshot);
  const predictionsDegraded = canonicalSourceStatus.includes("degraded") || (!predictionsWithheld && trustQuality.label === "Degraded");
  const hasMlData = mlSeries.length > 0;
  const hasFeatureData = featureImportanceEntries.length > 0;
  const hasSentimentData = !predictionsWithheld && (activeRiskForecast.length > 0 || Boolean(activeSentimentForecast));
  const hasMarketData = domainSignalHistory.length > 0;
  const hasEventData = !predictionsWithheld && activeEventPredictions.length > 0;
  const hasInsightsData = Boolean(activePredictionData) || hasFeatureData || hasMarketData || (advancedInsights?.anomalies?.length || 0) > 0;
  const hasAdvancedData =
    governanceData.models.length > 0 ||
    activeGlobeData.length > 0 ||
    deepHistoryForPanels.length > 1 ||
    comparisonCountries.length > 1 ||
    (advancedInsights?.anomalies?.length || 0) > 0;
  const activePredictionSourceLabel = formatSourceLabel(advancedInsights?.forecast_contract?.source_status ?? advancedInsights?.predictions?.source_status ?? latestGlobalDoc?.features?.forecast_source_status ?? activePredictionData?.source_status);
  const sentimentSourceLabel = formatSourceLabel(advancedInsights?.forecast_contract?.source_status ?? advancedInsights?.predictions?.source_status ?? (activeSentimentForecast?.source_status ?? activeSentimentForecast?.source));
  const eventSourceLabel = formatSourceLabel(activeEventPredictions[0]?.source_status ?? activeEventPredictions[0]?.source);
  const honestSubtitle = !playbackActive && isLiveModelStatus(activePredictionData?.source_status) && trustQuality.label === "Healthy"
    ? "ML-Powered Risk Forecasting and market intelligence."
    : "Risk forecasting with explicit live, derived, degraded, and fallback provenance.";

  const mlStatus: PanelStatus = error ? "error" : hasMlData ? "live" : "no-data";
  const featureStatus: PanelStatus = error ? "error" : hasFeatureData ? "live" : "no-data";
  const sentimentStatus: PanelStatus = error ? "error" : hasSentimentData ? "live" : "no-data";
  const marketStatus: PanelStatus = error ? "error" : hasMarketData ? "live" : "no-data";
  const eventsStatus: PanelStatus = error ? "error" : hasEventData ? "live" : "no-data";
  const insightsStatus: PanelStatus = error ? "error" : hasInsightsData ? "live" : "no-data";
  const advancedStatus: PanelStatus = error ? "error" : hasAdvancedData ? "live" : "no-data";
  const canonicalStatusBadge = predictionsWithheld ? "Unavailable" : (predictionsDegraded ? "Degraded" : undefined);
  const heroStatusTone = playbackActive ? "playback" : predictionsWithheld ? "withheld" : predictionsDegraded ? "degraded" : "live";
  const heroStatusLabel = playbackActive ? "Playback" : predictionsWithheld ? "Withheld" : predictionsDegraded ? "Degraded" : "Live";
  const predictionHealthLabel = predictionsWithheld ? "Suppressed" : (predictionsDegraded ? "Degraded" : trustQuality.label);
  const selectedTimeframeLabel = selectedTimeframe === "1h" ? "1 hour window" : selectedTimeframe === "6h" ? "6 hour window" : selectedTimeframe === "24h" ? "24 hour window" : "7 day window";
  const activeModelVersionLabel = playbackActive
    ? "historical playback model state"
    : (advancedInsights?.forecast_contract?.model_version || activePredictionData?.model_version || "canonical forecast contract");
  const navControlTone = refreshing ? "refreshing" : heroStatusTone;
  const navControlStatusLabel = refreshing ? "Refreshing" : (playbackActive ? "Playback" : predictionHealthLabel);
  function handlePlaybackFrameChange(frame: SnapshotLike | null) {
    setPlaybackFrame(frame);
  }

  function handlePlaybackStateChange(isPlaying: boolean) {
    setPlaybackActive(isPlaying);
  }

  function stopPlaybackMode() {
    setPlaybackActive(false);
    setPlaybackFrame(null);
  }

  if (loading) {
    return (
      <main className="wp-loading">
        <section className="wp-loading-card">
          <h1>TREND PREDICTION</h1>
          <p>Loading ML prediction models...</p>
          {error && <p className="err">{error}</p>}
        </section>
      </main>
    );
  }

  return (
    <main className="wp-shell prediction-page">
      <ConsoleNavigation
        title={<>TREND <span>PREDICTION</span></>}
        subtitle={honestSubtitle}
        sectionRightSlot={(
          <div className="prediction-nav-controls" aria-label="Forecast controls">
            <div className="prediction-nav-timeframes" role="group" aria-label="Forecast window">
              {(["1h", "6h", "24h", "7d"] as const).map((tf) => (
                <button
                  key={tf}
                  type="button"
                  className={selectedTimeframe === tf ? "active" : ""}
                  onClick={() => setSelectedTimeframe(tf)}
                >
                  {tf === "1h" && "1H"}
                  {tf === "6h" && "6H"}
                  {tf === "24h" && "24H"}
                  {tf === "7d" && "7D"}
                </button>
              ))}
            </div>
            {playbackActive ? (
              <button type="button" className="prediction-nav-action prediction-nav-action-secondary" onClick={stopPlaybackMode}>
                Live
              </button>
            ) : null}
            <button
              type="button"
              className="prediction-nav-action prediction-nav-action-refresh"
              onClick={() => loadData({ showSpinner: false })}
              disabled={refreshing}
            >
              {refreshing ? "Refreshing..." : "Refresh"}
            </button>
            <span className={`prediction-nav-state prediction-nav-state-${navControlTone}`}>
              {navControlStatusLabel}
            </span>
          </div>
        )}
        sectionTabs={[
          { label: "Summary", targetId: "prediction-summary", badge: canonicalStatusBadge },
          { label: "Deep Intel", targetId: "prediction-deep-intel" },
          { label: "Prediction History", targetId: "prediction-history", badge: canonicalStatusBadge },
          { label: "Signals", targetId: "prediction-signals", badge: predictionsDegraded ? "Degraded" : undefined },
          { label: "Support", targetId: "prediction-support" },
        ]}
      />

      <section id="prediction-summary" className="wp-intelligence-bar prediction-intelligence-bar">
        <div className="wp-intelligence-primary">
          <span className="wp-intelligence-kicker">Forecast Command</span>
          <span className="wp-intelligence-topic">
            {predictionsWithheld
              ? (advancedInsights?.predictions?.fallback_reason || "Canonical forecast output is currently withheld by the quality gate.")
              : playbackActive
              ? "Historical playback is active so you can inspect how the forecast evolved over time."
              : (advancedInsights?.advisory || activePredictionData?.advisory || trustQuality.detail)}
          </span>
        </div>
        <div className="wp-intelligence-secondary">
          <span>{playbackActive ? "Playback mode" : "Live model state"}</span>
          <span>{selectedTimeframeLabel}</span>
          <span>{predictionHealthLabel}</span>
          <span>Updated {playbackActive && playbackFrame
            ? new Date(playbackFrame.timestamp).toLocaleTimeString()
            : lastCanonicalRefreshAt
            ? new Date(lastCanonicalRefreshAt).toLocaleTimeString()
            : lastUpdatedAt
            ? new Date(lastUpdatedAt).toLocaleTimeString()
            : "--:--:--"}</span>
        </div>
      </section>

      <section className="wp-exec-grid prediction-exec-grid">
        <article className="wp-card wp-exec-card prediction-exec-card prediction-exec-card-primary">
          <div className="prediction-exec-topline">
            <div className="wp-exec-label">Canonical Risk</div>
            <span className={`prediction-hero-status prediction-hero-status-${heroStatusTone}`}>{heroStatusLabel}</span>
          </div>
          <strong className="wp-highlight prediction-exec-value">
            {canonicalRiskDisplay !== null ? `${canonicalRiskDisplay.toFixed(1)} / 100` : "WITHHELD"}
          </strong>
          <div className="wp-mini-meta">
            <span>Source</span>
            <strong>{activePredictionSourceLabel || "Canonical forecast"}</strong>
          </div>
          <div className="wp-mini-meta wp-mini-meta--detail">
            <span>Brief</span>
            <strong className="wp-mini-meta-detail">
              {predictionsWithheld
                ? (advancedInsights?.predictions?.fallback_reason || "Canonical forecast output is currently withheld by the quality gate.")
                : (advancedInsights?.advisory || activePredictionData?.advisory || trustQuality.detail)}
            </strong>
          </div>
        </article>

        <article className="wp-card wp-exec-card prediction-exec-card">
          <div className="wp-exec-label">Confidence</div>
          <strong className="wp-highlight prediction-exec-value">{predictionsWithheld ? "0.0%" : `${(avgConfidence * 100).toFixed(1)}%`}</strong>
          <div className="wp-mini-meta">
            <span>Reliability</span>
            <strong>{predictionHealthLabel}</strong>
          </div>
          <div className="wp-mini-meta">
            <span>Forecast Window</span>
            <strong>{selectedTimeframeLabel}</strong>
          </div>
        </article>

        <article className="wp-card wp-exec-card prediction-exec-card">
          <div className="wp-exec-label">Active Model</div>
          <strong className="prediction-exec-inline">{predictionsWithheld ? "Quality gate" : (activePredictionSourceLabel || "Canonical forecast")}</strong>
          <div className="wp-mini-meta">
            <span>Version</span>
            <strong>{activeModelVersionLabel}</strong>
          </div>
          <div className="wp-mini-meta">
            <span>Mode</span>
            <strong>{playbackActive ? "Historical playback" : "Canonical live contract"}</strong>
          </div>
        </article>

        <article className="wp-card wp-exec-card prediction-exec-card">
          <div className="wp-exec-label">Last Update</div>
          <strong className="prediction-exec-inline">{playbackActive && playbackFrame
            ? new Date(playbackFrame.timestamp).toLocaleTimeString()
            : lastCanonicalRefreshAt
            ? new Date(lastCanonicalRefreshAt).toLocaleTimeString()
            : lastUpdatedAt
            ? new Date(lastUpdatedAt).toLocaleTimeString()
            : "--:--:--"}</strong>
          <div className="wp-mini-meta">
            <span>Date</span>
            <strong>{playbackActive && playbackFrame
              ? new Date(playbackFrame.timestamp).toLocaleDateString()
              : lastCanonicalRefreshAt
              ? new Date(lastCanonicalRefreshAt).toLocaleDateString()
              : lastUpdatedAt
              ? new Date(lastUpdatedAt).toLocaleDateString()
              : "Awaiting refresh"}</strong>
          </div>
          <div className="wp-mini-meta">
            <span>Reference</span>
            <strong>{playbackActive ? "Playback frame" : (lastCanonicalRefreshAt ? "Canonical refresh" : "Latest data refresh")}</strong>
          </div>
        </article>
      </section>


      <section id="prediction-deep-intel" className="prediction-deep-intel">
        <div className="prediction-deep-intel-grid">
          <article className="wp-card panel-animated prediction-deep-card">
            <PanelHeader
              title="3D Risk Globe"
              subtitle={playbackActive ? "Playback-adjusted global distribution" : "Rotating distribution from live risk-map snapshots"}
              status={activeGlobeData.length ? "live" : advancedStatus}
            />
            {activeGlobeData.length ? (
              showHeavyPanels ? (
                <Suspense fallback={<DeferredPanelPlaceholder label="Loading 3D globe..." />}>
                  <WorldGlobe3D data={activeGlobeData} autoRotate={true} height={460} />
                </Suspense>
              ) : (
                <DeferredPanelPlaceholder label="Preparing 3D globe..." />
              )
            ) : (
              <div className="prediction-empty">
                <p>No risk-map data available for globe rendering.</p>
                <button onClick={() => loadData({ showSpinner: false })}>Retry</button>
              </div>
            )}
          </article>
          <article className="wp-card panel-animated prediction-deep-card">
            <PanelHeader
              title="Correlation Matrix"
              subtitle="Feature interactions derived from real historical snapshots"
              status={deepHistoryForPanels.length > 1 ? "live" : advancedStatus}
            />
            {deepHistoryForPanels.length > 1 ? (
              showHeavyPanels ? (
                <Suspense fallback={<DeferredPanelPlaceholder label="Loading correlation matrix..." />}>
                  <RiskCorrelationMatrix
                    data={deepHistoryForPanels.map((h) => ({
                      features: {
                        news_sentiment: h.features.news_sentiment,
                        gdelt_sentiment: h.features.gdelt_sentiment,
                        crypto_return: h.features.crypto_return,
                        crypto_volatility: h.features.crypto_volatility,
                        stock_return: h.features.stock_return,
                        stock_volatility: h.features.stock_volatility,
                        weather_anomaly: h.features.weather_anomaly,
                        direct_behavior_score: h.features.direct_behavior_score,
                        contextual_pressure_score: h.features.contextual_pressure_score,
                        evidence_quality_score: h.features.evidence_quality_score,
                        narrative_velocity_score: h.features.narrative_velocity_score,
                        coordination_risk_score: h.features.coordination_risk_score,
                        mobility_disruption_score: h.features.mobility_disruption_score,
                        logistics_stress_score: h.features.logistics_stress_score,
                        household_stress_score: h.features.household_stress_score,
                        fuel_price_pressure: h.features.fuel_price_pressure,
                        food_price_pressure: h.features.food_price_pressure,
                        labor_stress_score: h.features.labor_stress_score,
                        fx_pressure_score: h.features.fx_pressure_score,
                        remittance_stress_score: h.features.remittance_stress_score,
                        energy_stress_score: h.features.energy_stress_score,
                        global_behavior_index: h.features.global_behavior_index,
                        global_context_index: h.features.global_context_index,
                        global_attention_index: h.features.global_attention_index,
                        global_disruption_index: h.features.global_disruption_index,
                        global_economic_stress_index: h.features.global_economic_stress_index,
                        global_risk_score: h.score,
                      },
                      timestamp: h.timestamp,
                    }))}
                    height={460}
                  />
                </Suspense>
              ) : (
                <DeferredPanelPlaceholder label="Preparing correlation matrix..." />
              )
            ) : (
              <div className="prediction-empty">
                <p>Need at least two historical snapshots for correlations.</p>
                <button onClick={() => loadData({ showSpinner: false })}>Retry</button>
              </div>
            )}
          </article>
          <article className="wp-card panel-animated prediction-deep-card">
            <PanelHeader
              title="Historical Playback"
              subtitle="Timeline replay of risk progression"
              status={deepHistoryResolved.length > 1 ? "live" : advancedStatus}
            />
            {deepHistoryResolved.length > 1 ? (
              showHeavyPanels ? (
                <Suspense fallback={<DeferredPanelPlaceholder label="Loading playback timeline..." />}>
                  <HistoricalPlayback
                    data={deepHistoryResolved}
                    height={500}
                    onFrameChange={handlePlaybackFrameChange}
                    onPlaybackStateChange={handlePlaybackStateChange}
                  />
                </Suspense>
              ) : (
                <DeferredPanelPlaceholder label="Preparing playback timeline..." />
              )
            ) : (
              <div className="prediction-empty">
                <p>Need more history to enable playback.</p>
                <button onClick={() => loadData({ showSpinner: false })}>Retry</button>
              </div>
            )}
          </article>
          <article className="wp-card panel-animated prediction-deep-card">
            <PanelHeader
              title="Country Comparison"
              subtitle="Cross-country comparative analytics"
              status={comparisonCountries.length > 1 ? "live" : advancedStatus}
            />
            {comparisonCountries.length > 1 ? (
              showHeavyPanels ? (
                <Suspense fallback={<DeferredPanelPlaceholder label="Loading country comparison..." />}>
                  <CountryComparison countries={comparisonCountries} height={500} />
                </Suspense>
              ) : (
                <DeferredPanelPlaceholder label="Preparing country comparison..." />
              )
            ) : (
              <div className="prediction-empty">
                <p>Need more country points for meaningful comparison.</p>
                <button onClick={() => loadData({ showSpinner: false })}>Retry</button>
              </div>
            )}
          </article>
        </div>
      </section>

      <section id="prediction-history" className="prediction-row prediction-row-core">
        <article className="wp-card panel-animated prediction-card-large">
          <PanelHeader
            title="Canonical Forecast Track"
            subtitle="Canonical advanced forecast track, with explicit withheld and downgraded states"
            status={mlStatus}
          />
          {hasMlData ? (
            <div ref={mlChartRef} className="prediction-chart" />
          ) : (
            <div className="prediction-empty">
              <p>{predictionsWithheld ? (advancedInsights?.predictions?.fallback_reason || "Predictions are currently withheld by the quality gate.") : "No canonical advanced forecast track is available for this timeframe."}</p>
              <button onClick={() => loadData({ showSpinner: false })}>Retry</button>
            </div>
          )}
        </article>
        <article className="wp-card panel-animated prediction-card-small">
          <PanelHeader
              title="Feature Importance"
            subtitle={playbackActive ? "Playback frame feature vector" : "Canonical feature snapshot from advanced insights"}
            status={featureStatus}
          />
          {hasFeatureData ? (
            <>
              <div className="wp-mini-meta" style={{ marginBottom: "12px", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
                <span>{playbackActive ? "Playback-derived feature shape" : "Normalized importance from canonical advanced insights"}</span>
                <span>{featureImportanceEntries[0] ? `${featureImportanceEntries[0].label} leads at ${featureImportanceEntries[0].importance.toFixed(0)}%` : "Awaiting ranked features"}</span>
              </div>
              <div ref={featureChartRef} className="prediction-chart" />
            </>
          ) : (
            <div className="prediction-empty">
              <p>No canonical feature snapshot is available yet.</p>
              <button onClick={() => loadData({ showSpinner: false })}>Retry</button>
            </div>
          )}
        </article>
      </section>

      <section id="prediction-signals" className="prediction-row prediction-row-signals">
        <article className="wp-card panel-animated prediction-card-medium">
          <PanelHeader
            title="Risk Forecast"
            subtitle={`Multi-horizon risk outlook (${formatSourceLabel(advancedInsights?.predictions?.source_status ?? (activeSentimentForecast?.source_status ?? activeSentimentForecast?.source)).toLowerCase()})`}
            status={sentimentStatus}
          />
          {hasSentimentData ? (
            <>
              <div className="wp-mini-meta" style={{ marginBottom: "12px", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
                <span>{sentimentSourceLabel}</span>
                <span>{predictionsWithheld ? (advancedInsights?.predictions?.fallback_reason || "Predictions withheld by quality gate") : (predictionsDegraded ? (advancedInsights?.predictions?.fallback_reason || "Forecast confidence downgraded by reliability policy") : (advancedInsights?.advisory || activeSentimentForecast?.advisory || activeSentimentForecast?.fallback_reason || "Canonical advanced forecast"))}</span>
              </div>
              <div ref={sentimentChartRef} className="prediction-chart" />
              <div className="forecast-legend">
                <div className="legend-item">
                  <span className="dot" style={{ background: "#22d3ee" }} />
                  <span>Current</span>
                </div>
                <div className="legend-item">
                  <span className="dot" style={{ background: "#38bdf8" }} />
                  <span>1h</span>
                </div>
                <div className="legend-item">
                  <span className="dot" style={{ background: "#7dd3fc" }} />
                  <span>6h</span>
                </div>
                <div className="legend-item">
                  <span className="dot" style={{ background: "#fbbf24" }} />
                  <span>24h</span>
                </div>
                <div className="legend-item">
                  <span className="dot" style={{ background: "#f97316" }} />
                  <span>7d</span>
                </div>
              </div>
            </>
          ) : (
            <div className="prediction-empty">
              <p>{predictionsWithheld ? (advancedInsights?.predictions?.fallback_reason || "Forecast suppressed by quality gate.") : "No canonical risk forecast was returned."}</p>
              <button onClick={() => loadData({ showSpinner: false })}>Retry</button>
            </div>
          )}
        </article>
        <article className="wp-card panel-animated prediction-card-medium">
          <PanelHeader
            title="Cross-Domain Pressure"
            subtitle="Behavior, attention, disruption, logistics, and economic stress signals over time"
            status={marketStatus}
          />
          {hasMarketData ? (
            <>
              {predictionsDegraded && !predictionsWithheld ? (
                <div className="wp-mini-meta" style={{ marginBottom: "12px", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
                  <span>Downgraded view</span>
                  <span>Cross-domain context remains visible, but predictive confidence is currently downgraded.</span>
                </div>
              ) : null}
              <div ref={marketChartRef} className="prediction-chart" />
            </>
          ) : (
            <div className="prediction-empty">
              <p>No cross-domain signal history is available right now.</p>
              <button onClick={() => loadData({ showSpinner: false })}>Retry</button>
            </div>
          )}
        </article>
      </section>

      <section id="prediction-support" className="prediction-row prediction-row-support">
        <article className="wp-card panel-animated prediction-card-medium">
          <PanelHeader
            title="Event-Based Predictions"
            subtitle={`Country-level risk outlook (${eventSourceLabel.toLowerCase()})`}
            status={eventsStatus}
          />
          {hasEventData ? (
            <>
              {(activeEventPredictions[0]?.fallback_reason || activeEventPredictions[0]?.source_status) ? (
                <div className="wp-mini-meta" style={{ marginBottom: "12px", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
                  <span>{eventSourceLabel}</span>
                  <span>{activeEventPredictions[0]?.fallback_reason || "Derived country baseline deltas"}</span>
                </div>
              ) : null}
            <div className="event-predictions">
              {activeEventPredictions.map((event) => {
                const severityLevel = normalizeSeverityLevel(event.severity);
                const severityLabel = getSeverityLabel(severityLevel);
                const eventTypeLabel = normalizeEventTypeLabel(event.event_type);
                const riskDelta = safeN(event.predicted_risk_increase);
                const riskDeltaLabel = `${riskDelta >= 0 ? "+" : ""}${riskDelta.toFixed(2)}%`;
                const eventTimestampMs = parseTimestampMs(event.timestamp);
                const regions = Array.isArray(event.affected_regions)
                  ? event.affected_regions.filter((region) => Boolean(String(region || "").trim()))
                  : [];

                return (
                  <div key={event.event_id} className="event-card">
                    <div className="event-header">
                      <span className={`severity-badge severity-${severityLevel}`}>{severityLabel}</span>
                      <span className="severity-score">{severityLevel}/10</span>
                      <span className="event-type">{eventTypeLabel}</span>
                    </div>
                    <div className="event-details">
                      <div className="event-metrics-grid">
                        <div className="wp-mini-meta event-metric">
                          <span>Projected Risk Delta</span>
                          <strong className={`risk-increase ${riskDelta >= 0 ? "trend-up" : "trend-down"}`}>{riskDeltaLabel}</strong>
                        </div>
                        <div className="wp-mini-meta event-metric">
                          <span>Confidence</span>
                          <strong>{(safeN(event.confidence) * 100).toFixed(0)}%</strong>
                        </div>
                      </div>
                      <div className="affected-regions">
                        {(regions.length ? regions : ["Global"]).slice(0, 8).map((region) => (
                          <span key={region} className={`region-tag${region === "Global" ? " region-tag-muted" : ""}`}>
                            {region}
                          </span>
                        ))}
                      </div>
                      <div className="event-time">
                        Expected window: {eventTimestampMs !== null ? new Date(eventTimestampMs).toLocaleString() : "Unknown"}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            </>
          ) : (
            <div className="prediction-empty">
              <p>{predictionsWithheld ? (advancedInsights?.predictions?.fallback_reason || "Event predictions withheld by quality gate.") : "No event predictions are available for the selected range."}</p>
              <button onClick={() => loadData({ showSpinner: false })}>Retry</button>
            </div>
          )}
        </article>
        <article className="wp-card panel-animated prediction-card-medium">
          <PanelHeader
            title="Prediction Insights"
            subtitle="Condensed decision signal summary from the canonical advanced insights payload"
            status={insightsStatus}
          />
          {hasInsightsData ? (
            <div className="insights-panel">
              <div className="insight-item">
                <span className="insight-label">Top Risk Driver</span>
                <strong className="insight-value">
                  {topRiskDriver}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Market Correlation</span>
                <strong className="insight-value">
                  {marketCorrelation !== null ? formatInsightMetric(marketCorrelation) : "N/A"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Pressure Trend</span>
                <strong
                  className={`insight-value ${
                    pressureTrendUp ? "trend-up" : "trend-down"
                  }`}
                >
                  {pressureTrendUp ? "Escalating" : "Contained"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Direct Behavior</span>
                <strong className="insight-value">
                  {insightFeatureSnapshot.directBehavior !== undefined ? formatInsightMetric(insightFeatureSnapshot.directBehavior) : "N/A"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Context Pressure</span>
                <strong className="insight-value">
                  {insightFeatureSnapshot.contextualPressure !== undefined ? formatInsightMetric(insightFeatureSnapshot.contextualPressure) : "N/A"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Evidence Quality</span>
                <strong className="insight-value">
                  {insightFeatureSnapshot.evidenceQuality !== undefined ? formatInsightMetric(insightFeatureSnapshot.evidenceQuality) : "N/A"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Drift Score</span>
                <strong className="insight-value">
                  {activePredictionData?.drift_score?.toFixed(4) || "0.0000"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Model Disagreement</span>
                <strong className="insight-value">{disagreement.toFixed(2)}</strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Logistics Stress</span>
                <strong className="insight-value">
                  {insightFeatureSnapshot.logisticsStress !== undefined ? formatInsightMetric(insightFeatureSnapshot.logisticsStress) : "N/A"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Household Stress</span>
                <strong className="insight-value">
                  {insightFeatureSnapshot.householdStress !== undefined ? formatInsightMetric(insightFeatureSnapshot.householdStress) : "N/A"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Energy Stress</span>
                <strong className="insight-value">
                  {insightFeatureSnapshot.energyStress !== undefined ? formatInsightMetric(insightFeatureSnapshot.energyStress) : "N/A"}
                </strong>
              </div>
            </div>
          ) : (
            <div className="prediction-empty">
              <p>Insights will appear once real prediction data is available.</p>
              <button onClick={() => loadData({ showSpinner: false })}>Retry</button>
            </div>
          )}
        </article>
      </section>

      <section className="prediction-deep-intel">
        <div className="prediction-deep-intel-grid">
          <article className="wp-card panel-animated prediction-deep-card prediction-deep-card-wide prediction-deep-card-auto">
            <PanelHeader
              title="Advanced Analytics"
              subtitle="Anomalies, causality, and generated reports"
              status={advancedStatus}
            />
            {showHeavyPanels ? (
              <AdvancedAnalyticsPanel />
            ) : (
              <DeferredPanelPlaceholder label="Preparing advanced analytics workspace..." />
            )}
          </article>
          <article className="wp-card panel-animated prediction-deep-card prediction-deep-card-wide">
            <PanelHeader
              title="Model Governance"
              subtitle={`Ensemble behavior and calibration integrity for ${advancedInsights?.ml_observability?.model_version || governanceData.selectedCalibrationModel || "the active canonical model"}`}
              status={governanceData.models.length ? "live" : advancedStatus}
            />
            {showHeavyPanels ? (
              <Suspense fallback={<DeferredPanelPlaceholder label="Loading model governance..." />}>
                <ModelGovernance data={governanceData} />
              </Suspense>
            ) : (
              <DeferredPanelPlaceholder label="Preparing model governance..." />
            )}
          </article>
        </div>
      </section>
      <footer className="wp-footer">
        <button onClick={() => navigate("/dashboard")}>Back to Dashboard</button>
        <span>Last updated: {lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleTimeString() : "--:--:--"}</span>
        {error && <span className="err">{error}</span>}
      </footer>
    </main>
  );
}




















