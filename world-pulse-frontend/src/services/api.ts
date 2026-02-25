import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const API_KEY = import.meta.env.VITE_API_KEY || "super_secure_api_key";

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
  risk: number;
  timestamp?: string;
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
  const res = await API.get("/dashboard/risk-map", { headers: API_HEADERS, params: { mode: "online" } });
  return Array.isArray(res.data) ? (res.data as RiskMapPoint[]) : [];
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

export async function runScenarioSimulation(steps: ScenarioStep[]): Promise<ScenarioResult> {
  const res = await API.post("/dashboard/scenario/run", { steps }, { headers: API_HEADERS });
  return res.data as ScenarioResult;
}

export default API;
