import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const API_KEY = import.meta.env.VITE_API_KEY || "super_secure_api_key";
export const COUNTRY_RISK_WS_URL = `${API_URL.replace(/^http/, "ws")}/ws/country-risk-map?api_key=${encodeURIComponent(API_KEY)}`;

// Simple response cache to reduce 429 errors
interface CacheEntry {
  data: any;
  timestamp: number;
  ttl: number;
}

const responseCache = new Map<string, CacheEntry>();

const API = axios.create({
  baseURL: API_URL,
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
  (error) => {
    // Handle cached responses
    if (error.__cached) {
      return Promise.resolve(error.response);
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

export async function getLiveCommandFeed(): Promise<LiveCommandFeed> {
  const res = await API.get("/dashboard/live-feed", { headers: API_HEADERS, params: { mode: "online" } });
  return res.data as LiveCommandFeed;
}

export async function getRiskMap(): Promise<RiskMapPoint[]> {
  const res = await API.get("/dashboard/risk-map", { headers: API_HEADERS, params: { mode: "online", verified_only: false } });
  return Array.isArray(res.data) ? (res.data as RiskMapPoint[]) : [];
}

export async function getRiskMapCoverage(): Promise<RiskMapCoverage> {
  const res = await API.get("/dashboard/risk-map/coverage", { headers: API_HEADERS, params: { mode: "online" } });
  return res.data as RiskMapCoverage;
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
  return res.data as CountryDrilldownData;
}

export async function getGovernanceData(): Promise<GovernanceData> {
  const res = await API.get("/dashboard/governance", { headers: API_HEADERS, params: { mode: "online" } });
  return res.data as GovernanceData;
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
  const res = await API.get("/dashboard/global-intelligence-feed", { headers: API_HEADERS });
  return Array.isArray(res.data) ? (res.data as IntelligenceFeedItem[]) : [];
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
  const res = await API.get("/dashboard/crypto-pulse", { 
    headers: API_HEADERS, 
    params: { limit } 
  });
  return res.data as CryptoPulseData;
}

export async function getDisasterMonitor(limit: number = 20): Promise<DisasterMonitorData> {
  const res = await API.get("/dashboard/disaster-monitor", { 
    headers: API_HEADERS, 
    params: { limit } 
  });
  return res.data as DisasterMonitorData;
}

export async function getEconomicIndicators(): Promise<EconomicIndicatorsData> {
  const res = await API.get("/dashboard/economic-indicators", { headers: API_HEADERS });
  return res.data as EconomicIndicatorsData;
}

export async function getHealthAlerts(limit: number = 10): Promise<HealthAlertsData> {
  const res = await API.get("/dashboard/health-alerts", { 
    headers: API_HEADERS, 
    params: { limit } 
  });
  return res.data as HealthAlertsData;
}

export async function getTrendsRadar(limit: number = 20): Promise<TrendsRadarData> {
  const res = await API.get("/dashboard/trends-radar", { 
    headers: API_HEADERS, 
    params: { limit } 
  });
  return res.data as TrendsRadarData;
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
