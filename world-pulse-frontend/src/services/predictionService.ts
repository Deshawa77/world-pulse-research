import API, { API_HEADERS } from "./api";

export interface PredictionRequest {
  features?: number[];
  feature_names?: string[];
  feature_map?: Record<string, number>;
}

export interface PredictionResponse {
  model_version: string;
  schema_version?: string;
  feature_names?: string[];
  provided_feature_names?: string[];
  prediction: number;
  predicted_risk_score?: number;
  probability: number;
  drift_score: number | null;
  source?: string;
  source_status?: string;
  calibration_status?: string;
  prediction_interval?: Record<string, number> | null;
  fallback_reason?: string | null;
  data_quality_status?: string;
  advisory?: string;
  reasons?: string[];
}

export interface PredictionLog {
  _id: string;
  timestamp: string;
  model_version: string;
  schema_version?: string;
  feature_names?: string[];
  features: number[];
  prediction: number;
  probability: number;
  drift_score: number | null;
  role: string;
}

export interface HistoricalDataPoint {
  timestamp: string;
  risk_score: number;
  news_sentiment: number;
  gdelt_sentiment: number;
  crypto_return: number;
  crypto_volatility: number;
  stock_return: number;
  stock_volatility: number;
  weather_anomaly: number;
  global_behavior_index?: number;
  global_context_index?: number;
  global_attention_index?: number;
  global_disruption_index?: number;
  global_economic_stress_index?: number;
  direct_behavior_score?: number;
  contextual_pressure_score?: number;
  evidence_quality_score?: number;
  narrative_velocity_score?: number;
  coordination_risk_score?: number;
  mobility_disruption_score?: number;
  logistics_stress_score?: number;
  household_stress_score?: number;
  fuel_price_pressure?: number;
  food_price_pressure?: number;
  labor_stress_score?: number;
  fx_pressure_score?: number;
  remittance_stress_score?: number;
  energy_stress_score?: number;
  global_mood_score?: number;
  forecast_risk_score?: number;
  forecast_risk_delta?: number;
  forecast_confidence?: number;
  top_topic_pressure?: number;
  top_topics: string[];
}

export interface SentimentForecast {
  timestamp: string;
  current_sentiment: number;
  forecast_1h: number;
  forecast_6h: number;
  forecast_24h: number;
  forecast_7d: number;
  confidence: number;
  source?: string;
  source_status?: string;
  model_version?: string;
  calibration_status?: string;
  prediction_interval?: Record<string, number> | null;
  fallback_reason?: string | null;
  data_quality_status?: string;
  advisory?: string;
  reasons?: string[];
}

export interface MarketReaction {
  timestamp: string;
  event_type: string;
  sentiment_impact: number;
  crypto_reaction: number;
  stock_reaction: number;
  correlation_strength: number;
}

export interface EventPrediction {
  event_id: string;
  event_type: string;
  severity: number;
  predicted_risk_increase: number;
  affected_regions: string[];
  confidence: number;
  timestamp: string;
  source?: string;
  source_status?: string;
  model_version?: string;
  fallback_reason?: string | null;
}

export type PredictionFeatureMetric = {
  key: string;
  label: string;
  value: number;
  scale: "raw" | "absolute" | "normalized";
};

export interface PredictionFeatureProfile {
  modelFeatures: number[];
  modelFeatureNames: string[];
  modelFeatureKeys: string[];
  modelFeatureMap: Record<string, number>;
  intelligenceFeatures: PredictionFeatureMetric[];
  combinedFeatures: PredictionFeatureMetric[];
  intelligencePressure: number;
  confidenceWeight: number;
}

export interface PredictionBlend {
  probability: number;
  rawProbability: number;
  intelligencePressure: number;
  confidenceWeight: number;
  adjustment: number;
}

export const MODEL_FEATURE_DEFS = [
  { key: "news_sentiment", label: "News Sentiment", scale: "raw" },
  { key: "gdelt_sentiment", label: "GDELT Sentiment", scale: "raw" },
  { key: "crypto_return", label: "Crypto Return", scale: "raw" },
  { key: "crypto_volatility", label: "Crypto Volatility", scale: "raw" },
  { key: "stock_return", label: "Stock Return", scale: "raw" },
  { key: "stock_volatility", label: "Stock Volatility", scale: "raw" },
  { key: "weather_anomaly", label: "Weather Anomaly", scale: "raw" },
  { key: "direct_behavior_score", label: "Direct Behavior", scale: "normalized" },
  { key: "contextual_pressure_score", label: "Contextual Pressure", scale: "normalized" },
  { key: "evidence_quality_score", label: "Evidence Quality", scale: "normalized" },
  { key: "narrative_velocity_score", label: "Narrative Velocity", scale: "normalized" },
  { key: "coordination_risk_score", label: "Coordination Risk", scale: "normalized" },
  { key: "mobility_disruption_score", label: "Mobility Disruption", scale: "normalized" },
  { key: "logistics_stress_score", label: "Logistics Stress", scale: "normalized" },
  { key: "household_stress_score", label: "Household Stress", scale: "normalized" },
  { key: "fuel_price_pressure", label: "Fuel Price Pressure", scale: "normalized" },
  { key: "food_price_pressure", label: "Food Price Pressure", scale: "normalized" },
  { key: "labor_stress_score", label: "Labor Stress", scale: "normalized" },
  { key: "fx_pressure_score", label: "FX Pressure", scale: "normalized" },
  { key: "remittance_stress_score", label: "Remittance Stress", scale: "normalized" },
  { key: "energy_stress_score", label: "Energy Stress", scale: "normalized" },
  { key: "global_behavior_index", label: "Global Behavior", scale: "absolute" },
  { key: "global_context_index", label: "Global Context", scale: "absolute" },
  { key: "global_attention_index", label: "Global Attention", scale: "absolute" },
  { key: "global_disruption_index", label: "Global Disruption", scale: "absolute" },
  { key: "global_economic_stress_index", label: "Global Economic Stress", scale: "absolute" },
  { key: "global_mood_score", label: "Global Mood", scale: "absolute" },
  { key: "forecast_risk_score", label: "Forecast Risk", scale: "absolute" },
  { key: "forecast_risk_delta", label: "Forecast Risk Delta", scale: "raw" },
  { key: "forecast_confidence", label: "Forecast Confidence", scale: "normalized" },
  { key: "top_topic_pressure", label: "Top Topic Pressure", scale: "absolute" },
] as const;

export const INTELLIGENCE_FEATURE_DEFS = [
  { key: "direct_behavior_score", label: "Direct Behavior", scale: "normalized", weight: 12 },
  { key: "contextual_pressure_score", label: "Contextual Pressure", scale: "normalized", weight: 13 },
  { key: "evidence_quality_score", label: "Evidence Quality", scale: "normalized", weight: 10 },
  { key: "narrative_velocity_score", label: "Narrative Velocity", scale: "normalized", weight: 9 },
  { key: "coordination_risk_score", label: "Coordination Risk", scale: "normalized", weight: 9 },
  { key: "mobility_disruption_score", label: "Mobility Disruption", scale: "normalized", weight: 10 },
  { key: "logistics_stress_score", label: "Logistics Stress", scale: "normalized", weight: 9 },
  { key: "household_stress_score", label: "Household Stress", scale: "normalized", weight: 10 },
  { key: "fuel_price_pressure", label: "Fuel Price Pressure", scale: "normalized", weight: 7 },
  { key: "food_price_pressure", label: "Food Price Pressure", scale: "normalized", weight: 7 },
  { key: "labor_stress_score", label: "Labor Stress", scale: "normalized", weight: 8 },
  { key: "fx_pressure_score", label: "FX Pressure", scale: "normalized", weight: 7 },
  { key: "remittance_stress_score", label: "Remittance Stress", scale: "normalized", weight: 7 },
  { key: "energy_stress_score", label: "Energy Stress", scale: "normalized", weight: 8 },
  { key: "global_behavior_index", label: "Global Behavior", scale: "absolute", weight: 14 },
  { key: "global_context_index", label: "Global Context", scale: "absolute", weight: 12 },
  { key: "global_attention_index", label: "Global Attention", scale: "absolute", weight: 10 },
  { key: "global_disruption_index", label: "Global Disruption", scale: "absolute", weight: 12 },
  { key: "global_economic_stress_index", label: "Global Economic Stress", scale: "absolute", weight: 11 },
  { key: "global_mood_score", label: "Global Mood", scale: "absolute", weight: 8 },
  { key: "forecast_risk_score", label: "Forecast Risk", scale: "absolute", weight: 10 },
  { key: "forecast_risk_delta", label: "Forecast Delta", scale: "raw", weight: 5 },
  { key: "forecast_confidence", label: "Forecast Confidence", scale: "normalized", weight: 9 },
  { key: "top_topic_pressure", label: "Top Topic Pressure", scale: "absolute", weight: 7 },
] as const;

type ApiErrorLike = {
  code?: string;
  message?: string;
  response?: { status?: number };
};

function safeN(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function clamp(value: number, min = 0, max = 1): number {
  return Math.max(min, Math.min(max, value));
}

function normalizeUnitValue(value: unknown, fallback = 0): number {
  const n = safeN(value, fallback);
  if (n > 1 && n <= 100) return n / 100;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

function isBlockedByClientError(error: unknown): boolean {
  const e = (error ?? {}) as ApiErrorLike;
  const code = String(e.code ?? "").toLowerCase();
  const message = String(e.message ?? "").toLowerCase();
  return code.includes("blocked_by_client") || message.includes("blocked_by_client");
}

function isNotFoundError(error: unknown): boolean {
  const e = (error ?? {}) as ApiErrorLike;
  return e.response?.status === 404;
}

export function buildPredictionFeatureProfile(raw: Record<string, unknown> | null | undefined): PredictionFeatureProfile {
  const source = (raw ?? {}) as Record<string, unknown>;
  const modelFeatures: PredictionFeatureMetric[] = MODEL_FEATURE_DEFS.map((def) => ({
    key: def.key,
    label: def.label,
    scale: def.scale,
    value: safeN(source[def.key], 0),
  }));
  const intelligenceFeatures: PredictionFeatureMetric[] = INTELLIGENCE_FEATURE_DEFS.map((def) => ({
    key: def.key,
    label: def.label,
    scale: def.scale,
    value: safeN(source[def.key], 0),
  }));

  const totalWeight = INTELLIGENCE_FEATURE_DEFS.reduce((sum, item) => sum + item.weight, 0);
  const intelligencePressure = clamp(
    INTELLIGENCE_FEATURE_DEFS.reduce((sum, item) => sum + normalizeUnitValue(source[item.key], 0) * item.weight, 0) / Math.max(totalWeight, 1),
    0,
    1,
  );
  const confidenceWeight = clamp(0.35 + normalizeUnitValue(source.forecast_confidence, 0.55) * 0.65, 0.35, 1);

  const modelFeatureMap = Object.fromEntries(modelFeatures.map((item) => [item.key, item.value]));

  return {
    modelFeatures: modelFeatures.map((item) => item.value),
    modelFeatureNames: modelFeatures.map((item) => item.label),
    modelFeatureKeys: modelFeatures.map((item) => item.key),
    modelFeatureMap,
    intelligenceFeatures,
    combinedFeatures: modelFeatures,
    intelligencePressure,
    confidenceWeight,
  };
}

export function blendPredictionProbability(baseProbability: unknown, raw: Record<string, unknown> | null | undefined): PredictionBlend {
  const rawProbability = clamp(normalizeUnitValue(baseProbability, 0.5), 0, 1);
  const profile = buildPredictionFeatureProfile(raw);
  const intelligenceShare = 0.18 + (profile.confidenceWeight * 0.12);
  const baselineShare = 1 - intelligenceShare;
  const weightedBlend = (rawProbability * baselineShare) + (profile.intelligencePressure * intelligenceShare);
  const adjustment = (profile.intelligencePressure - 0.5) * 0.24 * profile.confidenceWeight;
  const probability = clamp(weightedBlend + adjustment, 0, 1);
  return {
    probability,
    rawProbability,
    intelligencePressure: profile.intelligencePressure,
    confidenceWeight: profile.confidenceWeight,
    adjustment,
  };
}

class PredictionService {
  buildFeatureProfile(raw: Record<string, unknown> | null | undefined): PredictionFeatureProfile {
    return buildPredictionFeatureProfile(raw);
  }

  blendPrediction(baseProbability: unknown, raw: Record<string, unknown> | null | undefined): PredictionBlend {
    return blendPredictionProbability(baseProbability, raw);
  }

  async getPrediction(payload: PredictionRequest): Promise<PredictionResponse> {
    const response = await API.post("/predict", payload, { headers: API_HEADERS });
    return response.data;
  }

  async getPredictionLogs(limit: number = 50): Promise<PredictionLog[]> {
    const response = await API.get("/prediction_logs", {
      headers: API_HEADERS,
      params: { limit },
    });
    const payload = response.data as unknown;
    const rows = Array.isArray(payload)
      ? payload
      : Array.isArray((payload as { logs?: unknown[] } | null)?.logs)
      ? (payload as { logs: unknown[] }).logs
      : Array.isArray((payload as { data?: unknown[] } | null)?.data)
      ? (payload as { data: unknown[] }).data
      : [];

    return rows
      .filter((row): row is PredictionLog => Boolean(row && typeof row === "object"))
      .sort((a, b) => {
        const aTs = new Date(a.timestamp).getTime();
        const bTs = new Date(b.timestamp).getTime();
        return Number.isFinite(bTs - aTs) ? bTs - aTs : 0;
      });
  }

  async getHistoricalData(
    startDate?: string,
    endDate?: string,
    limit: number = 1000
  ): Promise<HistoricalDataPoint[]> {
    const params: Record<string, string | number> = { limit };
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;

    const response = await API.get("/features/global/history", {
      headers: API_HEADERS,
      params,
    });
    return response.data;
  }

  async getSentimentForecast(): Promise<SentimentForecast> {
    const response = await API.get("/analytics/sentiment-forecast", {
      headers: API_HEADERS,
    });
    return response.data;
  }

  async getMarketReactions(limit: number = 100): Promise<MarketReaction[]> {
    const response = await API.get("/analytics/market-reactions", {
      headers: API_HEADERS,
      params: { limit },
    });
    return response.data;
  }

  async getEventPredictions(limit: number = 233): Promise<EventPrediction[]> {
    try {
      const response = await API.get("/analytics/incidents-outlook", {
        headers: API_HEADERS,
        params: { limit },
      });
      return Array.isArray(response.data) ? response.data : [];
    } catch (error) {
      if (isBlockedByClientError(error) || isNotFoundError(error)) {
        return [];
      }
      throw error;
    }
  }

  async exportData(
    format: "csv" | "json" | "xlsx",
    dateRange?: { start: string; end: string }
  ): Promise<Blob> {
    const params: Record<string, string> = { format };
    if (dateRange) {
      params.start_date = dateRange.start;
      params.end_date = dateRange.end;
    }

    const response = await API.get("/analytics/export", {
      headers: API_HEADERS,
      params,
      responseType: "blob",
    });
    return response.data;
  }

  async compareEvents(
    eventIds: string[]
  ): Promise<{ events: EventPrediction[]; comparison: Record<string, number> }> {
    const response = await API.post(
      "/analytics/compare-events",
      { event_ids: eventIds },
      { headers: API_HEADERS }
    );
    return response.data;
  }

  downloadExport(blob: Blob, filename: string) {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  }
}

export const predictionService = new PredictionService();
export default predictionService;
