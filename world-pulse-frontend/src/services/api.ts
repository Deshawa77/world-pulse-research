import axios, { AxiosHeaders } from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const API_KEY = import.meta.env.VITE_API_KEY || "super_secure_api_key";

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
  const wsBase = API_URL.replace(/^http/, "ws");
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
  baseURL: API_URL,
  timeout: 20000,
});

// Add auth headers and response caching interceptor
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
    const config = error?.config as (typeof error.config & { __retryCount?: number }) | undefined;
    const method = String(config?.method || "").toLowerCase();
    const status = Number(error?.response?.status || 0);

    if (status === 401) {
      clearStoredAuth();
      responseCache.clear();
      redirectToLogin();
      return Promise.reject(error);
    }

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
    validation: isRecord(payload.validation) ? payload.validation : {},
  };
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

export type AdvancedInsightsData = {
  timestamp: string;
  predictions: MLPredictionsData;
  anomalies: AnomalyData[];
  causal_graph: CausalLink[];
  sentiment_momentum: SentimentMomentumData;
  ai_report: AIReportData;
  ml_observability?: AdvancedMLObservability;
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
    const [predictions, anomalies, causal, momentum, report] = await Promise.allSettled([
      API.get("/analytics/advanced/ml-predictions", { headers: API_HEADERS, timeout: 25000 }),
      API.get("/analytics/advanced/anomalies", { headers: API_HEADERS, timeout: 15000 }),
      API.get("/analytics/advanced/causal", { headers: API_HEADERS, timeout: 15000 }),
      API.get("/analytics/advanced/sentiment-momentum", { headers: API_HEADERS, timeout: 15000 }),
      API.get("/analytics/advanced/report", { headers: API_HEADERS, params: { report_type: "brief" }, timeout: 20000 }),
    ]);

    const hasAny = [predictions, anomalies, causal, momentum, report].some((r) => r.status === "fulfilled");
    if (!hasAny) throw primaryError;

    return {
      timestamp: new Date().toISOString(),
      predictions:
        predictions.status === "fulfilled"
          ? (predictions.value.data as MLPredictionsData)
          : { predictions: [], model_type: "unavailable" },
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




