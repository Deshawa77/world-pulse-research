import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const API_KEY = import.meta.env.VITE_API_KEY || "super_secure_api_key";

const API = axios.create({
  baseURL: API_URL,
});

export const API_HEADERS = { "x-api-key": API_KEY };

export type LiveCommandFeed = {
  incidents: string[];
  ingestionHeartbeatSec: number;
  modelDrift: number;
  lastUpdated: string;
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
  models: Array<{ name: string; latencyMs: number; calibration: number; driftHint: string }>;
  disagreement: Array<{ left: string; right: string; value: number }>;
  calibrationTrend: Array<{ timestamp: string; value: number }>;
};

export type AlertActionPayload = {
  country: string;
  action: "acknowledge" | "snooze" | "assign";
  owner?: string;
  comment?: string;
};

function asNumber(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

async function safeGet<T>(url: string, fallback: T, params?: Record<string, string | number>): Promise<T> {
  try {
    const res = await API.get(url, { headers: API_HEADERS, params });
    return (res.data as T) ?? fallback;
  } catch {
    return fallback;
  }
}

export async function getLiveCommandFeed(): Promise<LiveCommandFeed> {
  const fallback: LiveCommandFeed = {
    incidents: ["Monitoring global signals..."],
    ingestionHeartbeatSec: 1,
    modelDrift: 0,
    lastUpdated: new Date().toISOString(),
  };

  const data = await safeGet<Record<string, unknown>>("/dashboard/live-feed", {}, { mode: "online" });
  return {
    incidents: Array.isArray(data.incidents) ? (data.incidents as string[]) : fallback.incidents,
    ingestionHeartbeatSec: asNumber(data.ingestionHeartbeatSec, fallback.ingestionHeartbeatSec),
    modelDrift: asNumber(data.modelDrift, fallback.modelDrift),
    lastUpdated: String(data.lastUpdated ?? fallback.lastUpdated),
  };
}

export async function getCountryDrilldown(country: string): Promise<CountryDrilldownData> {
  const now = Date.now();
  const fallback: CountryDrilldownData = {
    country,
    risk: 50,
    trend: Array.from({ length: 30 }, (_, i) => ({
      timestamp: new Date(now - (29 - i) * 60_000).toISOString(),
      value: 45 + Math.sin(i / 3) * 6,
    })),
    drivers: [
      { feature: "news_sentiment", value: 0.2, contribution: 0.12 },
      { feature: "market_volatility", value: 0.4, contribution: 0.2 },
      { feature: "weather_anomaly", value: 0.1, contribution: -0.06 },
    ],
    events: [
      { id: "evt-fallback-1", title: `${country} signal refresh`, timestamp: new Date().toISOString(), severity: "medium" },
    ],
    confidenceInterval: { lower: 44, upper: 56 },
  };

  const data = await safeGet<Partial<CountryDrilldownData>>(`/dashboard/country/${country}`, {}, { mode: "online" });
  return {
    country: data.country ?? fallback.country,
    risk: asNumber(data.risk, fallback.risk),
    trend: Array.isArray(data.trend) ? data.trend : fallback.trend,
    drivers: Array.isArray(data.drivers) ? data.drivers : fallback.drivers,
    events: Array.isArray(data.events) ? data.events : fallback.events,
    confidenceInterval: data.confidenceInterval ?? fallback.confidenceInterval,
  };
}

export async function getGovernanceData(): Promise<GovernanceData> {
  const now = Date.now();
  const fallback: GovernanceData = {
    models: [
      { name: "Global-RF", latencyMs: 120, calibration: 0.87, driftHint: "stable" },
      { name: "Global-GB", latencyMs: 95, calibration: 0.84, driftHint: "watch" },
      { name: "Global-LR", latencyMs: 50, calibration: 0.8, driftHint: "stable" },
    ],
    disagreement: [
      { left: "Global-RF", right: "Global-GB", value: 3.2 },
      { left: "Global-RF", right: "Global-LR", value: 2.4 },
      { left: "Global-GB", right: "Global-LR", value: 2.9 },
    ],
    calibrationTrend: Array.from({ length: 20 }, (_, i) => ({
      timestamp: new Date(now - (19 - i) * 300_000).toISOString(),
      value: 0.82 + Math.sin(i / 3) * 0.03,
    })),
  };

  const data = await safeGet<Partial<GovernanceData>>("/dashboard/governance", {}, { mode: "online" });
  return {
    models: Array.isArray(data.models) ? data.models : fallback.models,
    disagreement: Array.isArray(data.disagreement) ? data.disagreement : fallback.disagreement,
    calibrationTrend: Array.isArray(data.calibrationTrend) ? data.calibrationTrend : fallback.calibrationTrend,
  };
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
  try {
    const res = await API.post("/dashboard/scenario/run", { steps }, { headers: API_HEADERS });
    if (res.data?.baseline && res.data?.scenario && res.data?.timestamps) {
      return res.data as ScenarioResult;
    }
  } catch {
    // Fallback to deterministic local projection.
  }

  const base = 50 + Math.min(10, steps.length * 0.8);
  const scenario = Array.from({ length: 24 }, (_, i) => {
    const step = steps[i % Math.max(1, steps.length)] ?? { marketShock: 0, sentimentShock: 0, weatherShock: 0, label: "none" };
    const impulse = step.marketShock * 0.35 + step.sentimentShock * 0.35 + step.weatherShock * 0.3;
    return Math.max(0, Math.min(100, base + Math.sin(i / 3) * 4 + impulse * Math.exp(-i / 10)));
  });
  const baseline = scenario.map((x, i) => Math.max(0, Math.min(100, x - Math.sin(i / 4) * 2.2)));
  const now = Date.now();
  const timestamps = Array.from({ length: 24 }, (_, i) => new Date(now + i * 3_600_000).toISOString());
  return { baseline, scenario, timestamps };
}

export default API;
