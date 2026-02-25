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
