import { useEffect, useState } from "react";
import API from "../services/api";

// Types for the advanced analytics data
interface MLPredictions {
  predictions: {
    horizon: string;
    risk_score: number;
    confidence: number;
  }[];
  model_type: string;
}

interface Anomaly {
  timestamp: string;
  anomaly_score: number;
  features: Record<string, number>;
  severity: "low" | "medium" | "high" | "critical";
}

interface CausalLink {
  source: string;
  target: string;
  strength: number;
}

interface SentimentMomentum {
  velocity: number;
  acceleration: number;
  trend: "accelerating" | "decelerating" | "stable";
  rsi: number;
  macd_signal: string;
}

interface AIReport {
  title: string;
  summary: string;
  key_findings: string[];
  recommendations: string[];
  risk_level: string;
}

interface AdvancedInsights {
  timestamp: string;
  predictions: MLPredictions;
  anomalies: Anomaly[];
  causal_graph: CausalLink[];
  sentiment_momentum: SentimentMomentum;
  ai_report: AIReport;
}

export default function AdvancedAnalyticsPanel() {
  const [activeTab, setActiveTab] = useState<
    "predictions" | "anomalies" | "causal" | "momentum" | "report"
  >("predictions");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AdvancedInsights | null>(null);

  useEffect(() => {
    fetchAdvancedInsights();
  }, []);

  const fetchAdvancedInsights = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await API.get("/analytics/advanced/insights");
      setData(response.data);
    } catch (err) {
      console.error("Failed to fetch advanced insights:", err);
      setError("Failed to load advanced analytics data");
    } finally {
      setLoading(false);
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "critical":
        return "text-red-500";
      case "high":
        return "text-orange-500";
      case "medium":
        return "text-yellow-500";
      default:
        return "text-green-500";
    }
  };

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case "accelerating":
        return "↗↗";
      case "decelerating":
        return "↘↘";
      default:
        return "→→";
    }
  };

  return (
    <div className="advanced-analytics-panel">
      <div className="panel-header">
        <h3>🤖 Advanced Analytics</h3>
        <button onClick={fetchAdvancedInsights} disabled={loading}>
          {loading ? "⟳" : "↻"} Refresh
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="tab-navigation">
        <button
          className={activeTab === "predictions" ? "active" : ""}
          onClick={() => setActiveTab("predictions")}
        >
          🔮 Predictions
        </button>
        <button
          className={activeTab === "anomalies" ? "active" : ""}
          onClick={() => setActiveTab("anomalies")}
        >
          ⚠️ Anomalies
        </button>
        <button
          className={activeTab === "causal" ? "active" : ""}
          onClick={() => setActiveTab("causal")}
        >
          🔗 Causal
        </button>
        <button
          className={activeTab === "momentum" ? "active" : ""}
          onClick={() => setActiveTab("momentum")}
        >
          📈 Momentum
        </button>
        <button
          className={activeTab === "report" ? "active" : ""}
          onClick={() => setActiveTab("report")}
        >
          📄 Report
        </button>
      </div>

      <div className="panel-content">
        {loading ? (
          <div className="loading">Loading advanced analytics...</div>
        ) : data ? (
          <>
            {activeTab === "predictions" && (
              <div className="predictions-tab">
                <h4>Multi-Step Ahead Crisis Predictions</h4>
                <div className="predictions-grid">
                  {data.predictions?.predictions?.map((pred, idx) => (
                    <div key={idx} className="prediction-card">
                      <div className="horizon">{pred.horizon}</div>
                      <div className="risk-score">{pred.risk_score.toFixed(1)}</div>
                      <div className="confidence">
                        Confidence: {(pred.confidence * 100).toFixed(1)}%
                      </div>
                      <div className="risk-bar">
                        <div
                          className="risk-fill"
                          style={{ width: `${pred.risk_score}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="model-info">
                  Model: {data.predictions?.model_type || "LSTM/Statistical Hybrid"}
                </div>
              </div>
            )}

            {activeTab === "anomalies" && (
              <div className="anomalies-tab">
                <h4>Anomaly Detection (Autoencoder)</h4>
                {data.anomalies?.length > 0 ? (
                  <div className="anomalies-list">
                    {data.anomalies.map((anomaly, idx) => (
                      <div key={idx} className="anomaly-card">
                        <div className="anomaly-header">
                          <span className="timestamp">
                            {new Date(anomaly.timestamp).toLocaleString()}
                          </span>
                          <span
                            className={`severity ${getSeverityColor(
                              anomaly.severity
                            )}`}
                          >
                            {anomaly.severity.toUpperCase()}
                          </span>
                        </div>
                        <div className="anomaly-score">
                          Score: {anomaly.anomaly_score.toFixed(4)}
                        </div>
                        <div className="feature-importance">
                          <h5>Contributing Features:</h5>
                          <div className="feature-bars">
                            {Object.entries(anomaly.features || {})
                              .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
                              .slice(0, 5)
                              .map(([feature, value]) => (
                                <div key={feature} className="feature-row">
                                  <span className="feature-name">{feature}</span>
                                  <div className="feature-bar">
                                    <div
                                      className="feature-fill"
                                      style={{
                                        width: `${Math.min(
                                          100,
                                          Math.abs(value) * 100
                                        )}%`,
                                      }}
                                    />
                                  </div>
                                </div>
                              ))}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="no-data">No anomalies detected</div>
                )}
              </div>
            )}

            {activeTab === "causal" && (
              <div className="causal-tab">
                <h4>Causal Discovery</h4>
                {data.causal_graph?.length > 0 ? (
                  <div className="causal-graph">
                    <div className="causal-legend">
                      <span>← causes →</span>
                    </div>
                    <div className="causal-edges">
                      {data.causal_graph.map((link, idx) => (
                        <div key={idx} className="causal-link">
                          <span className="source">{link.source}</span>
                          <span className="arrow">→</span>
                          <span className="target">{link.target}</span>
                          <span className="strength">
                            ({link.strength.toFixed(2)})
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="no-data">
                    Building causal graph from historical data...
                  </div>
                )}
              </div>
            )}

            {activeTab === "momentum" && (
              <div className="momentum-tab">
                <h4>Sentiment Momentum Analysis</h4>
                {data.sentiment_momentum && (
                  <div className="momentum-metrics">
                    <div className="metric-card">
                      <div className="metric-label">Velocity</div>
                      <div className="metric-value">
                        {data.sentiment_momentum.velocity.toFixed(4)}
                      </div>
                      <div className="metric-description">
                        Rate of sentiment change
                      </div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-label">Acceleration</div>
                      <div className="metric-value">
                        {data.sentiment_momentum.acceleration.toFixed(4)}
                      </div>
                      <div className="metric-description">
                        Change in velocity
                      </div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-label">Trend</div>
                      <div className="metric-value trend-value">
                        {getTrendIcon(data.sentiment_momentum.trend)}{" "}
                        {data.sentiment_momentum.trend}
                      </div>
                      <div className="metric-description">
                        Current momentum direction
                      </div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-label">RSI</div>
                      <div className="metric-value">
                        {data.sentiment_momentum.rsi.toFixed(2)}
                      </div>
                      <div className="metric-description">
                        Relative Strength Index
                      </div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-label">MACD Signal</div>
                      <div className="metric-value">
                        {data.sentiment_momentum.macd_signal}
                      </div>
                      <div className="metric-description">
                        Moving Average Convergence
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "report" && (
              <div className="report-tab">
                <h4>AI-Generated Crisis Report</h4>
                {data.ai_report && (
                  <div className="ai-report">
                    <div className="report-header">
                      <h5>{data.ai_report.title}</h5>
                      <span
                        className={`risk-badge ${data.ai_report.risk_level.toLowerCase()}`}
                      >
                        {data.ai_report.risk_level} Risk
                      </span>
                    </div>
                    <div className="report-summary">
                      {data.ai_report.summary}
                    </div>
                    <div className="report-section">
                      <h6>Key Findings:</h6>
                      <ul>
                        {data.ai_report.key_findings?.map((finding, idx) => (
                          <li key={idx}>{finding}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="report-section">
                      <h6>Recommendations:</h6>
                      <ul>
                        {data.ai_report.recommendations?.map((rec, idx) => (
                          <li key={idx}>{rec}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        ) : (
          <div className="no-data">
            No advanced analytics data available
          </div>
        )}
      </div>

      <style>{`
        .advanced-analytics-panel {
          background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
          border-radius: 12px;
          padding: 20px;
          color: #e0e0e0;
          font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }

        .panel-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 20px;
        }

        .panel-header h3 {
          margin: 0;
          font-size: 1.4rem;
          background: linear-gradient(90deg, #00d4ff, #7b2cbf);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .panel-header button {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          border: none;
          color: white;
          padding: 8px 16px;
          border-radius: 6px;
          cursor: pointer;
          font-size: 0.9rem;
        }

        .panel-header button:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .error-message {
          background: rgba(255, 0, 0, 0.1);
          border: 1px solid #ff4444;
          color: #ff4444;
          padding: 10px;
          border-radius: 6px;
          margin-bottom: 15px;
        }

        .tab-navigation {
          display: flex;
          gap: 5px;
          margin-bottom: 20px;
          flex-wrap: wrap;
        }

        .tab-navigation button {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          color: #a0a0a0;
          padding: 8px 12px;
          border-radius: 6px;
          cursor: pointer;
          font-size: 0.85rem;
          transition: all 0.3s;
        }

        .tab-navigation button.active {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          border-color: transparent;
        }

        .tab-navigation button:hover:not(.active) {
          background: rgba(255, 255, 255, 0.1);
        }

        .panel-content {
          min-height: 300px;
        }

        .loading, .no-data {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 200px;
          color: #888;
        }

        /* Predictions Tab */
        .predictions-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 15px;
          margin-bottom: 15px;
        }

        .prediction-card {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          padding: 15px;
          text-align: center;
        }

        .prediction-card .horizon {
          font-size: 0.9rem;
          color: #888;
          margin-bottom: 8px;
        }

        .prediction-card .risk-score {
          font-size: 2rem;
          font-weight: bold;
          background: linear-gradient(90deg, #00d4ff, #7b2cbf);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .prediction-card .confidence {
          font-size: 0.8rem;
          color: #888;
          margin: 8px 0;
        }

        .risk-bar {
          height: 4px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 2px;
          overflow: hidden;
        }

        .risk-fill {
          height: 100%;
          background: linear-gradient(90deg, #00ff88, #ffaa00, #ff4444);
          transition: width 0.5s;
        }

        .model-info {
          font-size: 0.8rem;
          color: #666;
          text-align: center;
        }

        /* Anomalies Tab */
        .anomalies-list {
          display: flex;
          flex-direction: column;
          gap: 15px;
        }

        .anomaly-card {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          padding: 15px;
        }

        .anomaly-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 10px;
        }

        .timestamp {
          font-size: 0.85rem;
          color: #888;
        }

        .severity {
          font-weight: bold;
          font-size: 0.85rem;
        }

        .anomaly-score {
          font-size: 1.2rem;
          margin-bottom: 10px;
        }

        .feature-bars {
          display: flex;
          flex-direction: column;
          gap: 5px;
        }

        .feature-row {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .feature-name {
          font-size: 0.8rem;
          width: 120px;
          color: #aaa;
        }

        .feature-bar {
          flex: 1;
          height: 4px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 2px;
          overflow: hidden;
        }

        .feature-fill {
          height: 100%;
          background: linear-gradient(90deg, #00d4ff, #7b2cbf);
        }

        /* Causal Tab */
        .causal-edges {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .causal-link {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 6px;
        }

        .source, .target {
          font-weight: bold;
          color: #00d4ff;
        }

        .arrow {
          color: #888;
        }

        .strength {
          color: #666;
          font-size: 0.85rem;
        }

        /* Momentum Tab */
        .momentum-metrics {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 15px;
        }

        .metric-card {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          padding: 15px;
          text-align: center;
        }

        .metric-label {
          font-size: 0.85rem;
          color: #888;
          margin-bottom: 8px;
        }

        .metric-value {
          font-size: 1.5rem;
          font-weight: bold;
          color: #00d4ff;
        }

        .trend-value {
          font-size: 1.2rem;
        }

        .metric-description {
          font-size: 0.75rem;
          color: #666;
          margin-top: 5px;
        }

        /* Report Tab */
        .ai-report {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          padding: 20px;
        }

        .report-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 15px;
        }

        .report-header h5 {
          margin: 0;
          font-size: 1.2rem;
        }

        .risk-badge {
          padding: 4px 12px;
          border-radius: 12px;
          font-size: 0.85rem;
          font-weight: bold;
        }

        .risk-badge.low {
          background: rgba(0, 255, 136, 0.2);
          color: #00ff88;
        }

        .risk-badge.medium {
          background: rgba(255, 170, 0, 0.2);
          color: #ffaa00;
        }

        .risk-badge.high {
          background: rgba(255, 68, 68, 0.2);
          color: #ff4444;
        }

        .risk-badge.critical {
          background: rgba(255, 0, 0, 0.3);
          color: #ff0000;
        }

        .report-summary {
          margin-bottom: 20px;
          line-height: 1.6;
        }

        .report-section {
          margin-bottom: 15px;
        }

        .report-section h6 {
          margin: 0 0 10px 0;
          color: #888;
          font-size: 0.9rem;
        }

        .report-section ul {
          margin: 0;
          padding-left: 20px;
        }

        .report-section li {
          margin-bottom: 5px;
          line-height: 1.5;
        }
      `}</style>
    </div>
  );
}
