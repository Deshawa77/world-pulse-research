import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const API_KEY = import.meta.env.VITE_API_KEY || "super_secure_api_key";
export const COUNTRY_RISK_WS_URL = `${API_URL.replace(/^http/, "ws")}/ws/country-risk-map?api_key=${encodeURIComponent(API_KEY)}`;

// Simple response cache to reduce 429 errors
interface CacheEntry {
  data: unknown;
  timestamp: number;
  ttl: number;
}

const responseCache = new Map<string, CacheEntry>();
const RETRYABLE_STATUS_CODES = new Set([408, 429, 500, 502, 503, 504]);

const API = axios.create({
  baseURL: API_URL,
  timeout: 20000,
});

// Add response caching interceptor
API.interceptors.request.use((config) => {
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

     const config = error?.config as (typeof error.config & { __retryCount?: number }) | undefined;
     const method = String(config?.method || "").toLowerCase();
     const status = Number(error?.response?.status || 0);
     const isRetryableNetworkError =
       error?.code === "ECONNABORTED" ||
       error?.message === "Network Error" ||
       RETRYABLE_STATUS_CODES.has(status);

     if (config && method === "get" && isRetryableNetworkError) {
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

export const API_HEADERS = { "x-api-key": API_KEY };


export type LiveCommandFeed = {
  incidents: string[];
  ingestionHeartbeatSec: number;
  modelDrift: number;
  lastUpdated: string;
};

export type RiskMapPoint = {
  country: string;
  risk: number | null;
  timestamp?: string;
  feature_timestamp?: string | null;
  validated_today?: boolean;
  data_quality?: "verified" | "synthetic" | "stale" | "unknown";
  source_count?: number;
  social_unrest_score?: number;
  google_trends_pressure?: number;
  weather_stress?: number;
  external_signal_freshness?: number;
  war_state_rules?: string[];
};

export type RiskMapCoverage = {
  total: number;
  verified: number;
  no_data: number;
  stale: number;
  remaining: number;
  coverage_pct: number;
  latest_validation?: {
    status?: string;
    sample_count?: number;
    brier_score?: number;
  };
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
  forecast_risk_score?: number;
  forecast_risk_delta?: number;
  forecast_confidence?: number;
  forecast_horizon_hours?: number;
  forecast_basis?: string;
  top_topics: string[];
};

export type LatestGlobalResponse = {
  timestamp?: string;
  version?: number;
  mode?: string;
  features: GlobalOperationalFeatures;
};

export type CountryDrilldownData = {
  country: string;
  risk: number;
  trend: Array<{ timestamp: string; value: number }>;
  drivers: Array<{ feature: string; value: number; contribution: number }>;
  events: Array<{ id: string; title: string; timestamp: string; severity: "low" | "medium" | "high" }>;
  confidenceInterval: { lower: number; upper: number };
};

export type GovernanceData = {
  models: Array<{ name: string; latencyMs: number; calibration: number; driftHint: string; vote?: number; confidence?: number }>;
  disagreement: Array<{ left: string; right: string; value: number }>;
  calibrationTrend: Array<{ timestamp: string; value: number }>;
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

  return {
    country,
    risk: toNullableFiniteNumber(value.risk),
    timestamp,
    feature_timestamp: featureTimestamp,
    validated_today: Boolean(value.validated_today),
    data_quality: dataQuality,
    source_count: toOptionalFiniteNumber(value.source_count),
    social_unrest_score: toOptionalFiniteNumber(value.social_unrest_score),
    google_trends_pressure: toOptionalFiniteNumber(value.google_trends_pressure),
    weather_stress: toOptionalFiniteNumber(value.weather_stress),
    external_signal_freshness: toOptionalFiniteNumber(value.external_signal_freshness),
    war_state_rules: toStringArray(value.war_state_rules),
  };
};

const normalizeRiskMapCoverage = (value: unknown): RiskMapCoverage => {
  if (!isRecord(value)) {
    return { total: 0, verified: 0, no_data: 0, stale: 0, remaining: 0, coverage_pct: 0 };
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

  return {
    country: typeof value.country === "string" ? value.country : fallbackCountry,
    risk: toFiniteNumber(value.risk),
    trend,
    drivers,
    events,
    confidenceInterval,
  };
};

const normalizeGovernanceData = (value: unknown): GovernanceData => {
  if (!isRecord(value)) {
    return { models: [], disagreement: [], calibrationTrend: [] };
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

  return {
    models,
    disagreement,
    calibrationTrend,
  };
};

export async function getLiveCommandFeed(): Promise<LiveCommandFeed> {
  const res = await API.get("/dashboard/live-feed", { headers: API_HEADERS, params: { mode: "online" } });
  return normalizeLiveCommandFeed(res.data);
}

export async function getRiskMap(): Promise<RiskMapPoint[]> {
  const res = await API.get("/dashboard/risk-map", { headers: API_HEADERS, params: { mode: "online", verified_only: false } });
  return Array.isArray(res.data)
    ? res.data
        .map(normalizeRiskMapPoint)
        .filter((entry): entry is RiskMapPoint => Boolean(entry))
    : [];
}

export async function getRiskMapCoverage(): Promise<RiskMapCoverage> {
  const res = await API.get("/dashboard/risk-map/coverage", { headers: API_HEADERS, params: { mode: "online" } });
  return normalizeRiskMapCoverage(res.data);
}

export async function getLatestGlobalFeatures(): Promise<LatestGlobalResponse> {
  const res = await API.get("/features/global/latest", { headers: API_HEADERS, params: { mode: "online" } });
  return res.data as LatestGlobalResponse;
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
  const res = await API.get(`/dashboard/country/${country}`, { headers: API_HEADERS, params: { mode: "online" } });
  return normalizeCountryDrilldown(res.data, country);
}

export async function getGovernanceData(): Promise<GovernanceData> {
  const res = await API.get("/dashboard/governance", { headers: API_HEADERS, params: { mode: "online" } });
  return normalizeGovernanceData(res.data);
}

export async function postAlertAction(payload: AlertActionPayload): Promise<boolean> {
  try {
    await API.post("/dashboard/alerts/action", payload, { headers: API_HEADERS });
    return true;
  } catch {
    return false;
  }
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
};

export async function getGlobalIntelligenceFeed(): Promise<IntelligenceFeedItem[]> {
  try {
    const res = await API.get("/dashboard/global-intelligence-feed", { headers: API_HEADERS });
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
  type: "earthquake" | "weather";
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
  cases: number;
  deaths: number;
  status: "active" | "monitoring";
  timestamp: string;
  source: string;
  description: string;
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
};

export type MLPredictionsData = {
  predictions: MLPrediction[];
  model_type: string;
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

export type AdvancedInsightsData = {
  timestamp: string;
  predictions: MLPredictionsData;
  anomalies: AnomalyData[];
  causal_graph: CausalLink[];
  sentiment_momentum: SentimentMomentumData;
  ai_report: AIReportData;
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
  const res = await API.get("/analytics/advanced/insights", { headers: API_HEADERS });
  return res.data as AdvancedInsightsData;
}

export default API;
