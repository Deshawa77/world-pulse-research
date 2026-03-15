import { getAuthHeaders } from "./api";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export type CountryWeatherSnapshot = {
  latitude: number;
  longitude: number;
  observedAt: string;
  conditionCode: number;
  conditionLabel: string;
  temperatureC: number;
  feelsLikeC: number;
  humidityPct: number;
  precipitationMm: number;
  rainMm: number;
  windSpeedKmh: number;
  windGustKmh: number;
  windDirectionDeg: number;
  provider: "open-meteo" | "met-no";
  cached?: boolean;
  stale?: boolean;
  cacheAgeSec?: number;
  warning?: string;
};

function safeN(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalize(payload: Record<string, unknown>, lat: number, lon: number): CountryWeatherSnapshot {
  return {
    latitude: safeN(payload.latitude, lat),
    longitude: safeN(payload.longitude, lon),
    observedAt: String(payload.observedAt ?? new Date().toISOString()),
    conditionCode: Math.round(safeN(payload.conditionCode, 0)),
    conditionLabel: String(payload.conditionLabel ?? "Unknown conditions"),
    temperatureC: safeN(payload.temperatureC),
    feelsLikeC: safeN(payload.feelsLikeC, safeN(payload.temperatureC)),
    humidityPct: safeN(payload.humidityPct),
    precipitationMm: safeN(payload.precipitationMm),
    rainMm: safeN(payload.rainMm),
    windSpeedKmh: safeN(payload.windSpeedKmh),
    windGustKmh: safeN(payload.windGustKmh, safeN(payload.windSpeedKmh)),
    windDirectionDeg: safeN(payload.windDirectionDeg),
    provider: String(payload.provider || "open-meteo") === "met-no" ? "met-no" : "open-meteo",
    cached: Boolean(payload.cached),
    stale: Boolean(payload.stale),
    cacheAgeSec: safeN(payload.cacheAgeSec),
    warning: payload.warning ? String(payload.warning) : undefined,
  };
}

export async function getCountryWeatherByCoords(
  lat: number,
  lon: number,
  options?: { retries?: number; country?: string | null }
): Promise<CountryWeatherSnapshot> {
  const latitude = Number(lat);
  const longitude = Number(lon);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    throw new Error("Invalid coordinates for weather lookup");
  }

  const retries = Math.max(0, Math.min(3, Number(options?.retries ?? 2)));
  const endpoint = new URL("/dashboard/weather/current", API_URL);
  endpoint.searchParams.set("lat", String(latitude));
  endpoint.searchParams.set("lon", String(longitude));
  if (options?.country) endpoint.searchParams.set("country", String(options.country));

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...getAuthHeaders(),
  };

  let lastError: unknown = null;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const response = await fetch(endpoint.toString(), { method: "GET", headers });
      const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
      if (!response.ok) {
        const detail = data?.detail;
        throw new Error(typeof detail === "string" ? detail : `Weather endpoint failed (${response.status})`);
      }
      return normalize(data, latitude, longitude);
    } catch (error) {
      lastError = error;
      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, 220 * (attempt + 1)));
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error("Live weather temporarily unavailable");
}
