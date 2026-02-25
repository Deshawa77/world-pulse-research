import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import predictionService, {
  type PredictionLog,
  type SentimentForecast,
  type MarketReaction,
  type EventPrediction,
} from "../services/predictionService";

import API, { API_HEADERS } from "../services/api";

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
  }, [token, navigate]);

  async function loadPlotly() {
    if (plotlyRef.current) return plotlyRef.current;
    if (!plotlyLoadingRef.current) {
      plotlyLoadingRef.current = import("plotly.js-dist-min")
        .then((mod) => {
          plotlyRef.current = (mod as any).default ?? mod;
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
      // Fetch prediction logs
      const logs = await predictionService.getPredictionLogs(100);
      setPredictionLogs(logs);

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

        // Simulate ensemble models (in production, these would come from backend)
        const baseRisk = normalizeRisk(features.global_risk_score ?? 50);
        setModelEnsemble([
          { name: "Gradient Boosting", vote: normalizeRisk(baseRisk + 2.3), confidence: 0.86, color: "#22d3ee" },
          { name: "Random Forest", vote: normalizeRisk(baseRisk - 1.1), confidence: 0.81, color: "#a3e635" },
          { name: "Logistic Regression", vote: normalizeRisk(baseRisk + 0.4), confidence: 0.74, color: "#60a5fa" },
          { name: "Neural Network", vote: normalizeRisk(baseRisk + 1.8), confidence: 0.79, color: "#f472b6" },
        ]);
      }

      // Fetch sentiment forecast (mock data for now, replace with actual API)
      setSentimentForecast({
        timestamp: new Date().toISOString(),
        current_sentiment: safeN(features?.news_sentiment, 0) * 100,
        forecast_1h: safeN(features?.news_sentiment, 0) * 100 + Math.random() * 10 - 5,
        forecast_6h: safeN(features?.news_sentiment, 0) * 100 + Math.random() * 20 - 10,
        forecast_24h: safeN(features?.news_sentiment, 0) * 100 + Math.random() * 30 - 15,
        confidence: 0.82,
      });

      // Fetch market reactions (mock data for now)
      setMarketReactions([
        {
          timestamp: new Date(Date.now() - 3600000).toISOString(),
          event_type: "News Sentiment Shift",
          sentiment_impact: 15,
          crypto_reaction: -2.3,
          stock_reaction: -0.8,
          correlation_strength: 0.73,
        },
        {
          timestamp: new Date(Date.now() - 7200000).toISOString(),
          event_type: "Weather Anomaly",
          sentiment_impact: -8,
          crypto_reaction: 0.5,
          stock_reaction: -1.2,
          correlation_strength: 0.61,
        },
        {
          timestamp: new Date(Date.now() - 10800000).toISOString(),
          event_type: "Economic Report",
          sentiment_impact: 22,
          crypto_reaction: 3.1,
          stock_reaction: 1.5,
          correlation_strength: 0.85,
        },
      ]);

      // Fetch event predictions (mock data for now)
      setEventPredictions([
        {
          event_id: "evt-001",
          event_type: "Geopolitical Tension",
          severity: 7,
          predicted_risk_increase: 12,
          affected_regions: ["Middle East", "Europe"],
          confidence: 0.78,
          timestamp: new Date(Date.now() + 86400000).toISOString(),
        },
        {
          event_id: "evt-002",
          event_type: "Economic Announcement",
          severity: 5,
          predicted_risk_increase: 8,
          affected_regions: ["North America", "Asia"],
          confidence: 0.71,
          timestamp: new Date(Date.now() + 172800000).toISOString(),
        },
        {
          event_id: "evt-003",
          event_type: "Natural Disaster Risk",
          severity: 6,
          predicted_risk_increase: 15,
          affected_regions: ["Asia Pacific"],
          confidence: 0.65,
          timestamp: new Date(Date.now() + 259200000).toISOString(),
        },
      ]);
    } catch (err: any) {
      setError(err?.message || "Failed to load prediction data");
    } finally {
      setLoading(false);
    }
  }

  // Render ML Prediction Chart
  useEffect(() => {
    if (!mlChartRef.current || !predictionLogs.length || !plotlyRef.current) return;

    const timestamps = predictionLogs.map((log) =>
      new Date(log.timestamp).toLocaleTimeString()
    );
    const predictions = predictionLogs.map((log) => log.prediction);
    const probabilities = predictionLogs.map((log) => log.probability * 100);

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

    plotlyRef.current.newPlot(mlChartRef.current, data, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [predictionLogs]);

  // Render Sentiment Forecast Chart
  useEffect(() => {
    if (!sentimentChartRef.current || !sentimentForecast || !plotlyRef.current) return;

    const forecastData = [
      {
        x: ["Current", "1h Forecast", "6h Forecast", "24h Forecast"],
        y: [
          sentimentForecast.current_sentiment,
          sentimentForecast.forecast_1h,
          sentimentForecast.forecast_6h,
          sentimentForecast.forecast_24h,
        ],
        type: "bar",
        marker: {
          color: ["#22d3ee", "#60a5fa", "#818cf8", "#a78bfa"],
        },
        text: [
          sentimentForecast.current_sentiment.toFixed(1),
          sentimentForecast.forecast_1h.toFixed(1),
          sentimentForecast.forecast_6h.toFixed(1),
          sentimentForecast.forecast_24h.toFixed(1),
        ],
        textposition: "outside",
        textfont: { color: "#e7efff" },
      },
    ];

    const layout = {
      title: {
        text: `Sentiment Forecast (Confidence: ${(sentimentForecast.confidence * 100).toFixed(0)}%)`,
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

    plotlyRef.current.newPlot(sentimentChartRef.current, forecastData, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [sentimentForecast]);

  // Render Market Reaction Chart
  useEffect(() => {
    if (!marketChartRef.current || !marketReactions.length || !plotlyRef.current) return;

    const events = marketReactions.map((r) => r.event_type);
    const sentimentImpacts = marketReactions.map((r) => r.sentiment_impact);
    const cryptoReactions = marketReactions.map((r) => r.crypto_reaction);
    const stockReactions = marketReactions.map((r) => r.stock_reaction);

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

    plotlyRef.current.newPlot(marketChartRef.current, data, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [marketReactions]);

  // Load Plotly on mount
  useEffect(() => {
    loadPlotly();
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
          <span className="top-icon pulse-dot" onClick={() => navigate("/dashboard")}>
            📊 Dashboard
          </span>
          <span className="top-icon float-icon" onClick={() => navigate("/historical-trends")}>
            📈 Historical
          </span>
          <span className="top-icon blink-icon">👤 Admin</span>
        </div>
      </header>

      {/* Timeframe Selector */}
      <section className="wp-strip">
        <article className="wp-card timeframe-selector">
          <h3>Analysis Timeframe</h3>
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
        </article>

        <article className="wp-card">
          <h3>Current Risk Score</h3>
          <div className="wp-gauge-wrap">
            <div
              className="wp-gauge"
              style={{ ["--risk" as any]: `${currentPrediction?.probability ? currentPrediction.probability * 100 : 50}` }}
            >
              <div className="wp-gauge-hole" />
            </div>
            <strong className="wp-highlight">
              {currentPrediction ? (currentPrediction.probability * 100).toFixed(1) : "50.0"} / 100
            </strong>
            <div
              className={`lvl-${
                (currentPrediction?.probability || 0.5) > 0.75
                  ? "critical"
                  : (currentPrediction?.probability || 0.5) > 0.45
                  ? "elevated"
                  : "low"
              }`}
            >
              {(currentPrediction?.probability || 0.5) > 0.75
                ? "Critical"
                : (currentPrediction?.probability || 0.5) > 0.45
                ? "Elevated"
                : "Low"}
            </div>
          </div>
        </article>

        <article className="wp-card">
          <h3>Model Confidence</h3>
          <div className="confidence-display">
            <strong className="wp-highlight">{(avgConfidence * 100).toFixed(1)}%</strong>
            <div className="confidence-bar">
              <div
                className="confidence-fill"
                style={{ width: `${avgConfidence * 100}%` }}
              />
            </div>
            <div className="wp-mini-meta">
              <span>Disagreement</span>
              <strong>{disagreement.toFixed(2)}</strong>
            </div>
          </div>
        </article>

        <article className="wp-card">
          <h3>Active Model</h3>
          <div className="model-info">
            <strong className="wp-highlight">
              {currentPrediction?.model_version || "v1.0.0"}
            </strong>
            <div className="wp-mini-meta">
              <span>Last Update</span>
              <span>{new Date().toLocaleTimeString()}</span>
            </div>
          </div>
        </article>
      </section>

      {/* ML Prediction Graphs */}
      <section className="wp-grid">
        <article className="wp-card panel-animated">
          <h2>ML Prediction History</h2>
          <div ref={mlChartRef} className="prediction-chart" />
        </article>

        <article className="wp-card panel-animated">
          <h2>Feature Importance</h2>
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
        </article>
      </section>

      {/* Sentiment Forecast & Market Reaction */}
      <section className="wp-grid">
        <article className="wp-card panel-animated">
          <h2>Sentiment Forecast</h2>
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
        </article>

        <article className="wp-card panel-animated">
          <h2>Market Reaction Forecast</h2>
          <div ref={marketChartRef} className="prediction-chart" />
        </article>
      </section>

      {/* Ensemble Models & Event Predictions */}
      <section className="wp-grid-3">
        <article className="wp-card panel-animated">
          <h3>Ensemble Model Votes</h3>
          <div className="ensemble-models">
            {modelEnsemble.map((model) => (
              <div key={model.name} className="model-vote">
                <div className="wp-mini-meta">
                  <span style={{ color: model.color }}>{model.name}</span>
                  <strong>{model.vote.toFixed(2)}</strong>
                </div>
                <div className="vote-bar">
                  <div
                    className="vote-fill"
                    style={{
                      width: `${model.vote}%`,
                      background: model.color,
                    }}
                  />
                </div>
                <div className="confidence-text">
                  Confidence: {(model.confidence * 100).toFixed(0)}%
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="wp-card panel-animated">
          <h3>Event-Based Predictions</h3>
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
        </article>

        <article className="wp-card panel-animated">
          <h3>Prediction Insights</h3>
          <div className="insights-panel">
            <div className="insight-item">
              <span className="insight-label">Top Risk Driver</span>
              <strong className="insight-value">
                {latestFeatures[0] > latestFeatures[1] ? "News Sentiment" : "GDELT Sentiment"}
              </strong>
            </div>
            <div className="insight-item">
              <span className="insight-label">Market Correlation</span>
              <strong className="insight-value">{(0.65 + Math.random() * 0.2).toFixed(2)}</strong>
            </div>
            <div className="insight-item">
              <span className="insight-label">Volatility Trend</span>
              <strong
                className={`insight-value ${
                  latestFeatures[3] > 0 ? "trend-up" : "trend-down"
                }`}
              >
                {latestFeatures[3] > 0 ? "↗ Rising" : "↘ Falling"}
              </strong>
            </div>
            <div className="insight-item">
              <span className="insight-label">Drift Score</span>
              <strong className="insight-value">
                {currentPrediction?.drift_score?.toFixed(4) || "0.0000"}
              </strong>
            </div>
          </div>
        </article>
      </section>

      <footer className="wp-footer">
        <button onClick={loadData}>Refresh Predictions</button>
        <button onClick={() => navigate("/dashboard")}>Back to Dashboard</button>
        <span>Last updated: {new Date().toLocaleTimeString()}</span>
        {error && <span className="err">{error}</span>}
      </footer>
    </main>
  );
}
