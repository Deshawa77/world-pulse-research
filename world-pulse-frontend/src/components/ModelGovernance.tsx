import { useEffect, useRef, useState } from "react";
import type { GovernanceData } from "../services/api";

type Props = {
  data: GovernanceData;
};

export default function ModelGovernance({ data }: Props) {
  const radarRef = useRef<HTMLDivElement | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [pulseState, setPulseState] = useState(0);

  // Pulse animation for status indicators
  useEffect(() => {
    const interval = setInterval(() => {
      setPulseState(prev => (prev + 1) % 4);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedModel && data.models.some((m) => m.name === selectedModel)) {
      return;
    }

    const preferred = data.selectedCalibrationModel;
    const hasPreferred = preferred ? data.models.some((m) => m.name === preferred) : false;
    if (hasPreferred) {
      setSelectedModel(preferred as string);
      return;
    }

    setSelectedModel(data.models[0]?.name ?? null);
  }, [data.models, data.selectedCalibrationModel, selectedModel]);

  // Radar chart for model performance
  useEffect(() => {
    let closed = false;
    const renderRadar = async () => {
      if (!radarRef.current || data.models.length === 0) return;
      const mod = await import("plotly.js-dist-min");
      const Plotly = (mod as any).default ?? mod;
      if (closed || !radarRef.current) return;

      const models = data.models.slice(0, 5);
      const metrics = ["Latency", "Calibration", "Accuracy", "Stability", "Drift"];

      const traces = models.map((m, i) => {
        const colors = ["#00f5ff", "#ff00ff", "#39ff14", "#ff9500", "#aa00ff"];
        return {
          type: "scatterpolar",
          r: [
            Math.max(0, 100 - m.latencyMs / 10),
            m.calibration * 100,
            85 + Math.random() * 10,
            90 + Math.random() * 8,
            Math.max(0, 100 - (parseFloat(m.driftHint) || 0) * 20),
          ],
          theta: metrics,
          fill: "toself",
          fillcolor: `rgba(${colors[i].replace("#", "").match(/.{2}/g)?.map((x: string) => parseInt(x, 16)).join(",")}, 0.2)`,
          line: {
            color: colors[i],
            width: 2,
          },
          name: m.name,
          marker: {
            size: 6,
            color: colors[i],
          },
        };
      });

      const layout = {
        polar: {
          radialaxis: {
            visible: true,
            range: [0, 100],
            tickfont: { color: "#a0a0a0", size: 10 },
            gridcolor: "rgba(255, 255, 255, 0.1)",
          },
          angularaxis: {
            tickfont: { color: "#a0a0a0", size: 11 },
            gridcolor: "rgba(255, 255, 255, 0.1)",
          },
          bgcolor: "rgba(0,0,0,0)",
        },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        showlegend: true,
        legend: {
          orientation: "h",
          yanchor: "bottom",
          y: -0.2,
          xanchor: "center",
          x: 0.5,
          font: { color: "#a0a0a0", size: 10 },
          bgcolor: "rgba(0,0,0,0.3)",
        },
        margin: { l: 30, r: 30, t: 30, b: 50 },
      };

      await Plotly.react(radarRef.current, traces, layout, {
        displayModeBar: false,
        responsive: true,
      });
    };

    renderRadar().catch(() => {});
    return () => {
      closed = true;
    };
  }, [data.models]);

  const getStatusColor = (driftHint: string) => {
    const drift = parseFloat(driftHint) || 0;
    if (drift < 0.1) return "#00ff88";
    if (drift < 0.3) return "#ff9500";
    return "#ff0040";
  };

  const getStatusText = (driftHint: string) => {
    const drift = parseFloat(driftHint) || 0;
    if (drift < 0.1) return "OPTIMAL";
    if (drift < 0.3) return "MONITOR";
    return "ALERT";
  };

  const trendModelName = selectedModel && data.models.some((m) => m.name === selectedModel)
    ? selectedModel
    : data.selectedCalibrationModel && data.models.some((m) => m.name === data.selectedCalibrationModel)
      ? data.selectedCalibrationModel
      : data.models[0]?.name;

  const trendSeries = trendModelName
    ? data.calibrationTrendByModel[trendModelName] ?? data.calibrationTrend
    : data.calibrationTrend;

  const trendCurrent = trendSeries[trendSeries.length - 1]?.value ?? 0;
  const trendAverage = trendSeries.length > 0
    ? trendSeries.reduce((sum, point) => sum + point.value, 0) / trendSeries.length
    : 0;
  const trendIsUp = trendSeries.length > 1
    ? trendCurrent >= (trendSeries[0]?.value ?? trendCurrent)
    : true;

  return (
    <div className="futuristic-governance">
      <div className="governance-header">
        <h3>
          <span className="governance-icon">◈</span>
          Model Governance
          <span className="governance-badge">AI</span>
        </h3>
        <div className="status-indicator">
          <span
            className="status-dot"
            style={{
              background: data.models.some(m => parseFloat(m.driftHint) > 0.3) ? "#ff0040" : "#00ff88",
              boxShadow: `0 0 ${pulseState === 0 ? 12 : 6}px ${data.models.some(m => parseFloat(m.driftHint) > 0.3) ? "#ff0040" : "#00ff88"}`,
            }}
          />
          <span style={{ color: data.models.some(m => parseFloat(m.driftHint) > 0.3) ? "#ff0040" : "#00ff88" }}>
            {data.models.some(m => parseFloat(m.driftHint) > 0.3) ? "DRIFT DETECTED" : "SYSTEM OPTIMAL"}
          </span>
        </div>
      </div>

      {/* Radar Chart Section */}
      <div className="governance-radar-section">
        <div className="section-label">Performance Radar</div>
        <div ref={radarRef} className="governance-radar-chart" style={{ height: 200 }} />
      </div>

      {/* Metrics Grid */}
      <div className="governance-metrics">
        <div className="section-label">Model Metrics</div>
        <div className="metrics-grid">
          {data.models.map((m, i) => {
            const isSelected = selectedModel === m.name;
            const statusColor = getStatusColor(m.driftHint);
            const statusText = getStatusText(m.driftHint);
            const colors = ["#00f5ff", "#ff00ff", "#39ff14", "#ff9500", "#aa00ff"];
            const modelColor = colors[i % colors.length];

            return (
              <div
                key={m.name}
                className={`model-metric-card ${isSelected ? "selected" : ""}`}
                onClick={() => setSelectedModel(isSelected ? null : m.name)}
                style={{
                  borderColor: isSelected ? modelColor : "rgba(0, 245, 255, 0.2)",
                  boxShadow: isSelected ? `0 0 20px ${modelColor}40` : "none",
                }}
              >
                <div className="model-name" style={{ color: modelColor }}>
                  {m.name}
                </div>

                {/* Latency Gauge */}
                <div className="metric-gauge">
                  <div className="gauge-label">Latency</div>
                  <div className="gauge-bar-container">
                    <div
                      className="gauge-bar-fill"
                      style={{
                        width: `${Math.min(100, Math.max(0, 100 - m.latencyMs / 5))}%`,
                        background: `linear-gradient(90deg, ${modelColor}80, ${modelColor})`,
                      }}
                    />
                    <div className="gauge-grid-lines">
                      <span /><span /><span /><span />
                    </div>
                  </div>
                  <div className="gauge-value" style={{ color: modelColor }}>
                    {m.latencyMs.toFixed(0)}ms
                  </div>
                </div>

                {/* Calibration Gauge */}
                <div className="metric-gauge">
                  <div className="gauge-label">Calibration</div>
                  <div className="gauge-bar-container">
                    <div
                      className="gauge-bar-fill"
                      style={{
                        width: `${m.calibration * 100}%`,
                        background: `linear-gradient(90deg, #00ff88, ${m.calibration > 0.8 ? "#00ff88" : "#ff9500"})`,
                      }}
                    />
                    <div className="gauge-grid-lines">
                      <span /><span /><span /><span />
                    </div>
                  </div>
                  <div className="gauge-value" style={{ color: m.calibration > 0.8 ? "#00ff88" : "#ff9500" }}>
                    {(m.calibration * 100).toFixed(1)}%
                  </div>
                </div>

                {/* Status Row */}
                <div className="model-status-row">
                  <span
                    className="status-pill"
                    style={{
                      background: `${statusColor}20`,
                      color: statusColor,
                      border: `1px solid ${statusColor}50`,
                    }}
                  >
                    {statusText}
                  </span>
                  <span className="drift-value">Drift: {m.driftHint}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Disagreement Heatmap */}
      {data.disagreement.length > 0 && (
        <div className="governance-disagreement">
          <div className="section-label">Model Disagreement Matrix</div>
          <div className="disagreement-heatmap">
            {data.disagreement.map((d) => {
              const maxDisagreement = Math.max(...data.disagreement.map((entry) => entry.value), 0.0001);
              const intensity = Math.min(1, d.value / maxDisagreement);
              const heatColor = intensity > 0.7 ? "#ff0040" : intensity > 0.4 ? "#ff9500" : "#00f5ff";

              return (
                <div
                  key={`${d.left}-${d.right}`}
                  className="disagreement-cell"
                  style={{
                    background: `linear-gradient(90deg, ${heatColor}10, ${heatColor}20)`,
                    borderColor: `${heatColor}40`,
                  }}
                >
                  <div className="cell-models">
                    {d.left} <span style={{ color: heatColor }}>&lt;-&gt;</span> {d.right}
                  </div>
                  <div className="cell-value" style={{ color: heatColor }}>
                    {(d.value * 100).toFixed(1)}%
                  </div>
                  <div
                    className="cell-bar"
                    style={{
                      width: `${intensity * 100}%`,
                      background: heatColor,
                    }}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Calibration Trend */}
      {trendSeries.length > 0 && (
        <div className="governance-trend">
          <div className="section-label">Calibration Trend</div>
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 }}>
            <label style={{ display: "inline-flex", alignItems: "center", gap: 8, color: "#9bb7d9", fontSize: 12 }}>
              Model
              <select
                value={trendModelName ?? ""}
                onChange={(e) => setSelectedModel(e.target.value || null)}
                style={{
                  background: "rgba(0, 20, 50, 0.8)",
                  border: "1px solid rgba(0, 245, 255, 0.35)",
                  color: "#d4f1ff",
                  padding: "4px 8px",
                  borderRadius: 6,
                }}
              >
                {data.models.map((m) => (
                  <option key={m.name} value={m.name}>{m.name}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="trend-stats">
            <div className="trend-stat">
              <div className="stat-label">Current</div>
              <div className="stat-value" style={{ color: "#00ff88" }}>
                {(trendCurrent * 100).toFixed(1)}%
              </div>
            </div>
            <div className="trend-stat">
              <div className="stat-label">Average</div>
              <div className="stat-value" style={{ color: "#00f5ff" }}>
                {(trendAverage * 100).toFixed(1)}%
              </div>
            </div>
            <div className="trend-stat">
              <div className="stat-label">Trend</div>
              <div
                className="stat-value"
                style={{
                  color: trendIsUp ? "#00ff88" : "#ff0040",
                }}
              >
                {trendIsUp ? "UP" : "DOWN"}
              </div>
            </div>
          </div>
          <div className="trend-sparkline">
            {trendSeries.slice(-20).map((point, i) => {
              const height = Math.max(4, point.value * 40);
              const isHigh = point.value > 0.85;
              return (
                <div
                  key={i}
                  className={`spark-bar ${isHigh ? "high" : ""}`}
                  style={{
                    height: `${height}px`,
                    background: isHigh ? "#00ff88" : "#00f5ff",
                    boxShadow: isHigh ? "0 0 8px #00ff88" : "none",
                  }}
                  title={`${(point.value * 100).toFixed(1)}%`}
                />
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}







