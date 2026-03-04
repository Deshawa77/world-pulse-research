import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import predictionService, {
  type PredictionLog,
  type HistoricalDataPoint,
  type SentimentForecast,
  type MarketReaction,
  type EventPrediction,
} from "../services/predictionService";

import API, {
  API_HEADERS,
  getGovernanceData,
  getRiskMap,
  type GovernanceData,
  type RiskMapPoint,
} from "../services/api";
import ModelGovernance from "../components/ModelGovernance";
import WorldGlobe3D from "../components/WorldGlobe3D";
import RiskCorrelationMatrix from "../components/RiskCorrelationMatrix";
import HistoricalPlayback from "../components/HistoricalPlayback";
import CountryComparison from "../components/CountryComparison";
import AdvancedAnalyticsPanel from "../components/AdvancedAnalyticsPanel";
import "../components/futuristic-dashboard.css";

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
  drift_score?: number;
};

type SnapshotLike = {
  timestamp: string;
  score: number;
  features: Record<string, number>;
};

type PanelStatus = "live" | "no-data" | "error";


const FEATURE_NAMES = [
  "News Sentiment",
  "GDELT Sentiment",
  "Crypto Return",
  "Crypto Volatility",
  "Stock Return",
  "Stock Volatility",
  "Weather Anomaly",
];

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

function computeRangeForTimeframe(selectedTimeframe: "1h" | "6h" | "24h" | "7d") {
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
      top_topics: Array.isArray(row.top_topics)
        ? (row.top_topics as string[])
        : Array.isArray(nested.top_topics)
        ? (nested.top_topics as string[])
        : [],
    };
  });
}

function deriveSentimentForecastFromHistory(rows: HistoricalDataPoint[]): SentimentForecast | null {
  if (!rows.length) return null;
  const last = rows[rows.length - 1];
  const first = rows[0];
  const current = safeN(last.news_sentiment);
  const slope = rows.length >= 2
    ? (current - safeN(first.news_sentiment)) / Math.max(1, rows.length - 1)
    : 0;
  const confidence = rows.length >= 6 ? 0.75 : 0.55;

  return {
    timestamp: last.timestamp || new Date().toISOString(),
    current_sentiment: current,
    forecast_1h: current + slope,
    forecast_6h: current + (slope * 6),
    forecast_24h: current + (slope * 24),
    confidence,
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

export default function TrendPrediction() {
  const navigate = useNavigate();
  const token = localStorage.getItem("token");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [predictionLogs, setPredictionLogs] = useState<PredictionLog[]>([]);
  const [sentimentForecast, setSentimentForecast] = useState<SentimentForecast | null>(null);
  const [marketReactions, setMarketReactions] = useState<MarketReaction[]>([]);
  const [eventPredictions, setEventPredictions] = useState<EventPrediction[]>([]);
  const [latestFeatures, setLatestFeatures] = useState<number[]>([0, 0, 0, 0, 0, 0, 0]);
  const [currentPrediction, setCurrentPrediction] = useState<PredictionData | null>(null);
  const [selectedTimeframe, setSelectedTimeframe] = useState<"1h" | "6h" | "24h" | "7d">("24h");
  const [modelEnsemble, setModelEnsemble] = useState<MLModel[]>([]);
  const [governanceData, setGovernanceData] = useState<GovernanceData>({
    models: [],
    disagreement: [],
    calibrationTrend: [],
  });
  const [riskMap, setRiskMap] = useState<RiskMapPoint[]>([]);
  const [historicalData, setHistoricalData] = useState<HistoricalDataPoint[]>([]);
  const [plotlyReady, setPlotlyReady] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");

  const mlChartRef = useRef<HTMLDivElement | null>(null);
  const sentimentChartRef = useRef<HTMLDivElement | null>(null);
  const marketChartRef = useRef<HTMLDivElement | null>(null);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);

  useEffect(() => {
    if (!token) {
      navigate("/login");
      return;
    }
    loadData();
  }, [token, navigate, selectedTimeframe]);

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

  async function loadData() {
    setLoading(true);
    setError("");

    try {
      await loadPlotly();
      const logLimits: Record<"1h" | "6h" | "24h" | "7d", number> = {
        "1h": 24,
        "6h": 120,
        "24h": 240,
        "7d": 1000,
      };
      const logs = await predictionService.getPredictionLogs(logLimits[selectedTimeframe]);
      setPredictionLogs(Array.isArray(logs) ? logs : []);

      // Fetch latest global features for prediction
      const featuresRes = await API.get("/features/global/latest", {
        headers: API_HEADERS,
        params: { mode: "online" },
      });

      const features = featuresRes.data?.features;
      if (features) {
        const featureVector = [
          safeN(features.news_sentiment),
          safeN(features.gdelt_sentiment),
          safeN(features.crypto_return),
          safeN(features.crypto_volatility),
          safeN(features.stock_return),
          safeN(features.stock_volatility),
          safeN(features.weather_anomaly),
        ];
        setLatestFeatures(featureVector);

        // Get current prediction
        const predRes = await predictionService.getPrediction(featureVector);
        setCurrentPrediction({
          timestamp: new Date().toISOString(),
          prediction: predRes.prediction,
          probability: predRes.probability,
          model_version: predRes.model_version,
          features: featureVector,
        });

      }

      const [forecastResult, reactionsResult, eventsResult, governanceResult] = await Promise.allSettled([
        predictionService.getSentimentForecast(),
        predictionService.getMarketReactions(30),
        predictionService.getEventPredictions(),
        getGovernanceData(),
      ]);

      const { start, end } = computeRangeForTimeframe(selectedTimeframe);
      const [mapResult, historyResult] = await Promise.allSettled([
        getRiskMap(),
        predictionService.getHistoricalData(start, end, selectedTimeframe === "7d" ? 1000 : 400),
      ]);

      const resolvedHistory = historyResult.status === "fulfilled"
        ? normalizeHistoricalRows(historyResult.value as unknown[])
        : [];
      setHistoricalData(resolvedHistory);

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

      if (governanceResult.status === "fulfilled") {
        const governance = governanceResult.value;
        setGovernanceData(governance);
        setModelEnsemble(
          governance.models.map((m, idx) => ({
            name: m.name,
            vote: normalizeRisk(m.vote ?? 50),
            confidence: safeN(m.confidence, m.calibration),
            color: ["#22d3ee", "#a3e635", "#60a5fa", "#f472b6"][idx % 4],
          })),
        );
      } else {
        console.error("Governance load failed:", governanceResult.reason);
        setGovernanceData({ models: [], disagreement: [], calibrationTrend: [] });
        setModelEnsemble([]);
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

      // Fallback to latest real prediction-log features when current features endpoint is empty.
      if (!features && Array.isArray(logs) && logs.length) {
        const latestLogFeatures = Array.isArray(logs[0]?.features) ? logs[0].features : [];
        if (latestLogFeatures.length >= 7) {
          setLatestFeatures([
            safeN(latestLogFeatures[0]),
            safeN(latestLogFeatures[1]),
            safeN(latestLogFeatures[2]),
            safeN(latestLogFeatures[3]),
            safeN(latestLogFeatures[4]),
            safeN(latestLogFeatures[5]),
            safeN(latestLogFeatures[6]),
          ]);
        }
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load prediction data");
    } finally {
      setLastUpdatedAt(new Date().toISOString());
      setLoading(false);
    }
  }

  // Render ML Prediction Chart
  useEffect(() => {
    if (!mlChartRef.current || !plotlyRef.current || !plotlyReady) return;

    const logs = predictionLogs.length
      ? predictionLogs
      : currentPrediction
      ? [{
          timestamp: currentPrediction.timestamp,
          prediction: currentPrediction.prediction,
          probability: currentPrediction.probability,
        } as PredictionLog]
      : [];
    if (!logs.length) return;

    const timestamps = logs.map((log) =>
      new Date(log.timestamp).toLocaleTimeString()
    );
    const predictions = logs.map((log) => safeN(log.prediction));
    const probabilities = logs.map((log) => safeN(log.probability) * 100);

    const data = [
      {
        x: timestamps,
        y: predictions,
        type: "scatter",
        mode: "lines+markers",
        name: "Risk Prediction",
        line: { color: "#ef4444", width: 3 },
        marker: { size: 8, color: "#ef4444" },
      },
      {
        x: timestamps,
        y: probabilities,
        type: "scatter",
        mode: "lines",
        name: "Confidence %",
        line: { color: "#22d3ee", width: 2, dash: "dash" },
        yaxis: "y2",
      },
    ];

    const layout = {
      title: {
        text: "ML Risk Predictions Over Time",
        font: { color: "#e7efff", size: 18 },
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#9fb0cf" },
      xaxis: {
        gridcolor: "rgba(146,170,210,0.2)",
        tickfont: { color: "#9fb0cf" },
      },
      yaxis: {
        title: "Risk Level (0-1)",
        gridcolor: "rgba(146,170,210,0.2)",
        tickfont: { color: "#9fb0cf" },
        range: [0, 1],
      },
      yaxis2: {
        title: "Confidence %",
        overlaying: "y",
        side: "right",
        range: [0, 100],
        tickfont: { color: "#22d3ee" },
      },
      legend: {
        font: { color: "#9fb0cf" },
        x: 0.02,
        y: 0.98,
      },
      margin: { t: 50, r: 60, b: 40, l: 60 },
    };

    plotlyRef.current.react(mlChartRef.current, data, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [predictionLogs, currentPrediction, plotlyReady]);

  // Render Sentiment Forecast Chart
  useEffect(() => {
    if (!sentimentChartRef.current || !sentimentForecast || !plotlyRef.current || !plotlyReady) return;

    const currentSentiment = safeN(sentimentForecast.current_sentiment);
    const forecast1h = safeN(sentimentForecast.forecast_1h);
    const forecast6h = safeN(sentimentForecast.forecast_6h);
    const forecast24h = safeN(sentimentForecast.forecast_24h);
    const confidencePct = safeN(sentimentForecast.confidence) * 100;

    const forecastData = [
      {
        x: ["Current", "1h Forecast", "6h Forecast", "24h Forecast"],
        y: [
          currentSentiment,
          forecast1h,
          forecast6h,
          forecast24h,
        ],
        type: "bar",
        marker: {
          color: ["#22d3ee", "#60a5fa", "#818cf8", "#a78bfa"],
        },
        text: [
          currentSentiment.toFixed(1),
          forecast1h.toFixed(1),
          forecast6h.toFixed(1),
          forecast24h.toFixed(1),
        ],
        textposition: "outside",
        textfont: { color: "#e7efff" },
      },
    ];

    const layout = {
      title: {
        text: `Sentiment Forecast (Confidence: ${confidencePct.toFixed(0)}%)`,
        font: { color: "#e7efff", size: 18 },
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#9fb0cf" },
      xaxis: {
        gridcolor: "rgba(146,170,210,0.2)",
        tickfont: { color: "#9fb0cf" },
      },
      yaxis: {
        title: "Sentiment Score",
        gridcolor: "rgba(146,170,210,0.2)",
        tickfont: { color: "#9fb0cf" },
        range: [-100, 100],
      },
      margin: { t: 60, r: 30, b: 40, l: 60 },
    };

    plotlyRef.current.react(sentimentChartRef.current, forecastData, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [sentimentForecast, plotlyReady]);

  // Render Market Reaction Chart
  useEffect(() => {
    if (!marketChartRef.current || !marketReactions.length || !plotlyRef.current || !plotlyReady) return;

    const events = marketReactions.map((r) => r.event_type || "Event");
    const sentimentImpacts = marketReactions.map((r) => safeN(r.sentiment_impact));
    const cryptoReactions = marketReactions.map((r) => safeN(r.crypto_reaction));
    const stockReactions = marketReactions.map((r) => safeN(r.stock_reaction));

    const data = [
      {
        x: events,
        y: sentimentImpacts,
        type: "bar",
        name: "Sentiment Impact",
        marker: { color: "#22d3ee" },
      },
      {
        x: events,
        y: cryptoReactions,
        type: "bar",
        name: "Crypto Reaction %",
        marker: { color: "#f472b6" },
      },
      {
        x: events,
        y: stockReactions,
        type: "bar",
        name: "Stock Reaction %",
        marker: { color: "#a3e635" },
      },
    ];

    const layout = {
      title: {
        text: "Market Reaction to Events",
        font: { color: "#e7efff", size: 18 },
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#9fb0cf" },
      barmode: "group",
      xaxis: {
        gridcolor: "rgba(146,170,210,0.2)",
        tickfont: { color: "#9fb0cf" },
      },
      yaxis: {
        title: "Impact %",
        gridcolor: "rgba(146,170,210,0.2)",
        tickfont: { color: "#9fb0cf" },
      },
      legend: {
        font: { color: "#9fb0cf" },
        x: 0.02,
        y: 0.98,
      },
      margin: { t: 50, r: 30, b: 80, l: 60 },
    };

    plotlyRef.current.react(marketChartRef.current, data, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [marketReactions, plotlyReady]);

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

  const avgConfidence = useMemo(() => {
    if (!modelEnsemble.length) return 0;
    return modelEnsemble.reduce((acc, m) => acc + m.confidence, 0) / modelEnsemble.length;
  }, [modelEnsemble]);

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

  const globeData = useMemo(
    () => riskMap.map((r) => ({
      country: r.country,
      countryCode: r.country,
      risk: normalizeRisk(r.risk),
      lat: 0,
      lng: 0,
    })),
    [riskMap],
  );

  const comparisonCountries = useMemo(() => {
    const latest = deepHistoryResolved[deepHistoryResolved.length - 1];
    const baseFeatures = latest?.features ?? {
      news_sentiment: 0,
      gdelt_sentiment: 0,
      crypto_return: 0,
      crypto_volatility: 0,
      stock_return: 0,
      stock_volatility: 0,
      weather_anomaly: 0,
    };
    const fromRiskMap = riskMap.map((r) => {
      const risk = normalizeRisk(r.risk);
      const code = (r.country || "").toUpperCase();
      const h = hashCountryCode(code);
      const driftA = ((h % 23) - 11) / 110;
      const driftB = (((h >> 3) % 19) - 9) / 90;
      const pressure = (risk - 50) / 100;
      return {
        country: r.country,
        countryCode: code,
        risk,
        timestamp: latest?.timestamp ?? new Date().toISOString(),
        features: {
          news_sentiment: safeN(baseFeatures.news_sentiment + pressure * 0.3 + driftA * 0.2),
          gdelt_sentiment: safeN(baseFeatures.gdelt_sentiment + pressure * 0.26 - driftB * 0.14),
          crypto_return: safeN(baseFeatures.crypto_return - pressure * 0.06 + driftA * 0.03),
          crypto_volatility: safeN(Math.max(0, baseFeatures.crypto_volatility + Math.abs(pressure) * 0.08 + Math.abs(driftB) * 0.04)),
          stock_return: safeN(baseFeatures.stock_return - pressure * 0.05 + driftB * 0.02),
          stock_volatility: safeN(Math.max(0, baseFeatures.stock_volatility + Math.abs(pressure) * 0.07 + Math.abs(driftA) * 0.04)),
          weather_anomaly: safeN(Math.max(0, baseFeatures.weather_anomaly + Math.abs(driftA) * 0.3 + Math.max(0, pressure) * 0.12)),
        },
      };
    });
    if (fromRiskMap.length >= 2) return fromRiskMap;

    const fallbackFromEvents = Array.from(
      new Set(
        eventPredictions.flatMap((e) =>
          (e.affected_regions || [])
            .filter((region) => typeof region === "string" && region.length === 3)
            .map((region) => region.toUpperCase()),
        ),
      ),
    ).slice(0, 8).map((code, idx) => ({
      country: code,
      countryCode: code,
      risk: normalizeRisk(45 + (idx * 7) + (eventPredictions[idx]?.predicted_risk_increase ?? 0)),
      timestamp: latest?.timestamp ?? new Date().toISOString(),
      features: {
        news_sentiment: safeN(baseFeatures.news_sentiment + idx * 0.03),
        gdelt_sentiment: safeN(baseFeatures.gdelt_sentiment - idx * 0.02),
        crypto_return: safeN(baseFeatures.crypto_return + idx * 0.01),
        crypto_volatility: safeN(Math.max(0, baseFeatures.crypto_volatility + idx * 0.01)),
        stock_return: safeN(baseFeatures.stock_return - idx * 0.008),
        stock_volatility: safeN(Math.max(0, baseFeatures.stock_volatility + idx * 0.012)),
        weather_anomaly: safeN(Math.max(0, baseFeatures.weather_anomaly + idx * 0.02)),
      },
    }));

    return fallbackFromEvents;
  }, [deepHistoryResolved, riskMap, eventPredictions]);

  const hasMlData = predictionLogs.length > 0 || Boolean(currentPrediction);
  const hasFeatureData = latestFeatures.some((value) => Math.abs(safeN(value)) > 0);
  const hasSentimentData = Boolean(sentimentForecast);
  const hasMarketData = marketReactions.length > 0;
  const hasEventData = eventPredictions.length > 0;
  const hasInsightsData = Boolean(currentPrediction) || hasFeatureData || hasMarketData;
  const hasAdvancedData =
    governanceData.models.length > 0 ||
    riskMap.length > 0 ||
    deepHistoryResolved.length > 1 ||
    comparisonCountries.length > 1;

  const mlStatus: PanelStatus = error ? "error" : hasMlData ? "live" : "no-data";
  const featureStatus: PanelStatus = error ? "error" : hasFeatureData ? "live" : "no-data";
  const sentimentStatus: PanelStatus = error ? "error" : hasSentimentData ? "live" : "no-data";
  const marketStatus: PanelStatus = error ? "error" : hasMarketData ? "live" : "no-data";
  const eventsStatus: PanelStatus = error ? "error" : hasEventData ? "live" : "no-data";
  const insightsStatus: PanelStatus = error ? "error" : hasInsightsData ? "live" : "no-data";
  const advancedStatus: PanelStatus = error ? "error" : hasAdvancedData ? "live" : "no-data";

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
    <main className="wp-shell">
      <header className="wp-top">
        <div className="wp-burger" onClick={() => navigate("/dashboard")}>
          <span />
          <span />
          <span />
        </div>
        <div>
          <h1>
            TREND <span>PREDICTION</span>
          </h1>
          <p>ML-Powered Risk Forecasting & Market Intelligence</p>
        </div>
        <div className="wp-actions-inline">
          <button onClick={() => navigate("/dashboard")}>Dashboard</button>
          <button onClick={() => navigate("/historical-trends")}>Historical</button>
          <button onClick={() => navigate("/about")}>About</button>
          <button onClick={() => navigate("/contact")}>Contact</button>
          <button 
            onClick={() => {
              localStorage.removeItem("token");
              navigate("/login");
            }}
            style={{ color: "#ff6b6b" }}
          >
            Logout
          </button>
        </div>

      </header>

      <section className="prediction-summary-sticky">
        <article className="wp-card prediction-summary-card">
          <span className="prediction-summary-label">Risk Score</span>
          <strong className="prediction-summary-value">
            {currentPrediction ? (currentPrediction.probability * 100).toFixed(1) : "50.0"}
          </strong>
          <small>/100 global risk probability</small>
        </article>
        <article className="wp-card prediction-summary-card">
          <span className="prediction-summary-label">Confidence</span>
          <strong className="prediction-summary-value">{(avgConfidence * 100).toFixed(1)}%</strong>
          <small>ensemble average confidence</small>
        </article>
        <article className="wp-card prediction-summary-card">
          <span className="prediction-summary-label">Active Model</span>
          <strong className="prediction-summary-value">{currentPrediction?.model_version || "v1.0.0"}</strong>
          <small>production inference model</small>
        </article>
        <article className="wp-card prediction-summary-card">
          <span className="prediction-summary-label">Last Update</span>
          <strong className="prediction-summary-value">
            {lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleTimeString() : "--:--:--"}
          </strong>
          <small>latest data refresh</small>
        </article>
        <article className="wp-card prediction-summary-controls">
          <div className="prediction-summary-controls-head">Timeframe + Refresh</div>
          <div className="timeframe-buttons">
            {(["1h", "6h", "24h", "7d"] as const).map((tf) => (
              <button
                key={tf}
                className={selectedTimeframe === tf ? "active" : ""}
                onClick={() => setSelectedTimeframe(tf)}
              >
                {tf === "1h" && "1 Hour"}
                {tf === "6h" && "6 Hours"}
                {tf === "24h" && "24 Hours"}
                {tf === "7d" && "7 Days"}
              </button>
            ))}
          </div>
          <button onClick={loadData}>Refresh Predictions</button>
        </article>
      </section>

      <section className="prediction-deep-intel">
        <div className="prediction-deep-intel-grid">
          <article className="wp-card panel-animated prediction-deep-card">
            <PanelHeader
              title="3D Risk Globe"
              subtitle="Rotating distribution from live risk-map snapshots"
              status={riskMap.length ? "live" : advancedStatus}
            />
            {riskMap.length ? (
              <WorldGlobe3D data={globeData} autoRotate={true} height={460} />
            ) : (
              <div className="prediction-empty">
                <p>No risk-map data available for globe rendering.</p>
                <button onClick={loadData}>Retry</button>
              </div>
            )}
          </article>
          <article className="wp-card panel-animated prediction-deep-card">
            <PanelHeader
              title="Correlation Matrix"
              subtitle="Feature interactions derived from real historical snapshots"
              status={deepHistoryResolved.length > 1 ? "live" : advancedStatus}
            />
            {deepHistoryResolved.length > 1 ? (
              <RiskCorrelationMatrix
                data={deepHistoryResolved.map((h) => ({
                  features: {
                    news_sentiment: h.features.news_sentiment,
                    gdelt_sentiment: h.features.gdelt_sentiment,
                    crypto_return: h.features.crypto_return,
                    crypto_volatility: h.features.crypto_volatility,
                    stock_return: h.features.stock_return,
                    stock_volatility: h.features.stock_volatility,
                    weather_anomaly: h.features.weather_anomaly,
                    global_risk_score: h.score,
                  },
                  timestamp: h.timestamp,
                }))}
                height={460}
              />
            ) : (
              <div className="prediction-empty">
                <p>Need at least two historical snapshots for correlations.</p>
                <button onClick={loadData}>Retry</button>
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
              <HistoricalPlayback data={deepHistoryResolved} height={500} />
            ) : (
              <div className="prediction-empty">
                <p>Need more history to enable playback.</p>
                <button onClick={loadData}>Retry</button>
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
              <CountryComparison countries={comparisonCountries} height={500} />
            ) : (
              <div className="prediction-empty">
                <p>Need more country points for meaningful comparison.</p>
                <button onClick={loadData}>Retry</button>
              </div>
            )}
          </article>
        </div>
      </section>

      <section className="prediction-row prediction-row-core">
        <article className="wp-card panel-animated prediction-card-large">
          <PanelHeader
            title="ML Prediction History"
            subtitle="Risk trajectory and confidence trends from real prediction logs"
            status={mlStatus}
          />
          {hasMlData ? (
            <div ref={mlChartRef} className="prediction-chart" />
          ) : (
            <div className="prediction-empty">
              <p>No real prediction history available for this timeframe.</p>
              <button onClick={loadData}>Retry</button>
            </div>
          )}
        </article>
        <article className="wp-card panel-animated prediction-card-small">
          <PanelHeader
            title="Feature Importance"
            subtitle="Current live feature vector driving predictions"
            status={featureStatus}
          />
          {hasFeatureData ? (
            <div className="feature-importance">
              {latestFeatures.map((value, idx) => (
                <div key={idx} className="feature-bar">
                  <div className="wp-mini-meta">
                    <span>{FEATURE_NAMES[idx]}</span>
                    <span>{value.toFixed(3)}</span>
                  </div>
                  <div className="importance-track">
                    <div
                      className="importance-fill"
                      style={{
                        width: `${Math.min(100, Math.abs(value) * 50)}%`,
                        background:
                          value > 0
                            ? "linear-gradient(90deg, #22d3ee, #60a5fa)"
                            : "linear-gradient(90deg, #ef4444, #f87171)",
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="prediction-empty">
              <p>No live feature data found yet.</p>
              <button onClick={loadData}>Retry</button>
            </div>
          )}
        </article>
      </section>

      <section className="prediction-row prediction-row-signals">
        <article className="wp-card panel-animated prediction-card-medium">
          <PanelHeader
            title="Sentiment Forecast"
            subtitle="Current and projected sentiment from historical feature signals"
            status={sentimentStatus}
          />
          {hasSentimentData ? (
            <>
              <div ref={sentimentChartRef} className="prediction-chart" />
              <div className="forecast-legend">
                <div className="legend-item">
                  <span className="dot" style={{ background: "#22d3ee" }} />
                  <span>Current</span>
                </div>
                <div className="legend-item">
                  <span className="dot" style={{ background: "#60a5fa" }} />
                  <span>1h</span>
                </div>
                <div className="legend-item">
                  <span className="dot" style={{ background: "#818cf8" }} />
                  <span>6h</span>
                </div>
                <div className="legend-item">
                  <span className="dot" style={{ background: "#a78bfa" }} />
                  <span>24h</span>
                </div>
              </div>
            </>
          ) : (
            <div className="prediction-empty">
              <p>No backend sentiment forecast was returned.</p>
              <button onClick={loadData}>Retry</button>
            </div>
          )}
        </article>
        <article className="wp-card panel-animated prediction-card-medium">
          <PanelHeader
            title="Market Reaction Forecast"
            subtitle="Impact projections across sentiment, crypto, and stock responses"
            status={marketStatus}
          />
          {hasMarketData ? (
            <div ref={marketChartRef} className="prediction-chart" />
          ) : (
            <div className="prediction-empty">
              <p>No market reaction entries available right now.</p>
              <button onClick={loadData}>Retry</button>
            </div>
          )}
        </article>
      </section>

      <section className="prediction-row prediction-row-support">
        <article className="wp-card panel-animated prediction-card-medium">
          <PanelHeader
            title="Event-Based Predictions"
            subtitle="Severity-ranked event risk deltas and impacted regions"
            status={eventsStatus}
          />
          {hasEventData ? (
            <div className="event-predictions">
              {eventPredictions.map((event) => (
                <div key={event.event_id} className="event-card">
                  <div className="event-header">
                    <span className={`severity-badge severity-${event.severity}`}>
                      S{event.severity}
                    </span>
                    <span className="event-type">{event.event_type}</span>
                  </div>
                  <div className="event-details">
                    <div className="wp-mini-meta">
                      <span>Risk Increase</span>
                      <strong className="risk-increase">+{event.predicted_risk_increase}%</strong>
                    </div>
                    <div className="wp-mini-meta">
                      <span>Confidence</span>
                      <span>{(event.confidence * 100).toFixed(0)}%</span>
                    </div>
                    <div className="affected-regions">
                      {event.affected_regions.map((region) => (
                        <span key={region} className="region-tag">
                          {region}
                        </span>
                      ))}
                    </div>
                    <div className="event-time">
                      Expected: {new Date(event.timestamp).toLocaleDateString()}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="prediction-empty">
              <p>No event predictions are available for the selected range.</p>
              <button onClick={loadData}>Retry</button>
            </div>
          )}
        </article>
        <article className="wp-card panel-animated prediction-card-medium">
          <PanelHeader
            title="Prediction Insights"
            subtitle="Condensed decision signal summary from live analytics"
            status={insightsStatus}
          />
          {hasInsightsData ? (
            <div className="insights-panel">
              <div className="insight-item">
                <span className="insight-label">Top Risk Driver</span>
                <strong className="insight-value">
                  {latestFeatures[0] > latestFeatures[1] ? "News Sentiment" : "GDELT Sentiment"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Market Correlation</span>
                <strong className="insight-value">
                  {marketReactions.length
                    ? (marketReactions.reduce((acc, row) => acc + row.correlation_strength, 0) / marketReactions.length).toFixed(2)
                    : "0.00"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Volatility Trend</span>
                <strong
                  className={`insight-value ${
                    latestFeatures[3] > 0 ? "trend-up" : "trend-down"
                  }`}
                >
                  {latestFeatures[3] > 0 ? "Upward" : "Downward"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Drift Score</span>
                <strong className="insight-value">
                  {currentPrediction?.drift_score?.toFixed(4) || "0.0000"}
                </strong>
              </div>
              <div className="insight-item">
                <span className="insight-label">Model Disagreement</span>
                <strong className="insight-value">{disagreement.toFixed(2)}</strong>
              </div>
            </div>
          ) : (
            <div className="prediction-empty">
              <p>Insights will appear once real prediction data is available.</p>
              <button onClick={loadData}>Retry</button>
            </div>
          )}
        </article>
      </section>

      <section className="prediction-advanced-wrap">
        <div className="prediction-advanced-head">
          <div>
            <div className="prediction-advanced-kicker">Deep Intelligence</div>
            <h2>Advanced Analytics</h2>
            <p>Governance, geospatial risk, correlation, playback, and country comparison.</p>
          </div>
          <div className="prediction-advanced-actions">
            <span className={`prediction-status prediction-status-${advancedStatus}`}>
              {advancedStatus === "live" ? "Live" : advancedStatus === "error" ? "Error" : "No data"}
            </span>
          </div>
        </div>
      </section>

      <section className="prediction-deep-intel">
        <div className="prediction-deep-intel-grid">
          <article className="wp-card panel-animated prediction-deep-card prediction-deep-card-wide">
            <PanelHeader
              title="Model Governance"
              subtitle="Ensemble behavior and calibration integrity"
              status={governanceData.models.length ? "live" : advancedStatus}
            />
            <ModelGovernance data={governanceData} />
          </article>
          <article className="wp-card panel-animated prediction-deep-card prediction-deep-card-wide">
            <PanelHeader
              title="Advanced Analytics"
              subtitle="Anomalies, causality, and generated reports"
              status={advancedStatus}
            />
            <AdvancedAnalyticsPanel />
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
