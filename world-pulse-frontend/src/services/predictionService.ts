import API, { API_HEADERS } from "./api";

export interface PredictionRequest {
  features: number[];
}

export interface PredictionResponse {
  model_version: string;
  prediction: number;
  probability: number;
  drift_score: number | null;
}

export interface PredictionLog {
  _id: string;
  timestamp: string;
  model_version: string;
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
  top_topics: string[];
}

export interface SentimentForecast {
  timestamp: string;
  current_sentiment: number;
  forecast_1h: number;
  forecast_6h: number;
  forecast_24h: number;
  confidence: number;
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
}

type ApiErrorLike = {
  code?: string;
  message?: string;
  response?: { status?: number };
};

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

class PredictionService {
  async getPrediction(features: number[]): Promise<PredictionResponse> {
    const response = await API.post("/predict", { features }, { headers: API_HEADERS });
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

  async getEventPredictions(): Promise<EventPrediction[]> {
    try {
      const response = await API.get("/analytics/incidents-outlook", {
        headers: API_HEADERS,
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


