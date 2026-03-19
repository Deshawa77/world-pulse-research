import { useEffect, useMemo, useRef, useState } from "react";
import type { GovernanceData } from "../services/api";

type Props = {
  data: GovernanceData;
};

const MODEL_COLORS = ["#22d3ee", "#38bdf8", "#fbbf24", "#a3e635", "#94a3b8"];

function clamp(value: number, min = 0, max = 100) {
  return Math.max(min, Math.min(max, value));
}

export default function ModelGovernance({ data }: Props) {
  const comparisonChartRef = useRef<HTMLDivElement | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [pulseState, setPulseState] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setPulseState((prev) => (prev + 1) % 4);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedModel && data.models.some((m) => m.name === selectedModel)) {
      return;
    }

    const preferred = data.selectedCalibrationModel;
    if (preferred && data.models.some((m) => m.name === preferred)) {
      setSelectedModel(preferred);
      return;
    }

    setSelectedModel(data.models[0]?.name ?? null);
  }, [data.models, data.selectedCalibrationModel, selectedModel]);

  useEffect(() => {
    let closed = false;

    async function renderComparisonChart() {
      if (!comparisonChartRef.current || data.models.length === 0) return;
      const mod = await import("plotly.js-dist-min");
      const Plotly = (mod as any).default ?? mod;
      if (closed || !comparisonChartRef.current) return;

      const models = data.models.slice(0, 5);
      const labels = models.map((m) => m.name);
      const latencyScores = models.map((m) => clamp(100 - (m.latencyMs / 8)));
      const calibrationScores = models.map((m) => clamp((m.calibration || 0) * 100));
      const stabilityScores = models.map((m) => clamp(100 - ((parseFloat(m.driftHint) || 0) * 120)));

      const traces = [
        {
          type: "bar",
          orientation: "h",
          y: labels,
          x: latencyScores,
          name: "Latency Readiness",
          marker: { color: "rgba(34, 211, 238, 0.88)" },
          hovertemplate: "%{y}<br>Latency readiness: %{x:.1f}<extra></extra>",
        },
        {
          type: "bar",
          orientation: "h",
          y: labels,
          x: calibrationScores,
          name: "Calibration",
          marker: { color: "rgba(56, 189, 248, 0.72)" },
          hovertemplate: "%{y}<br>Calibration: %{x:.1f}<extra></extra>",
        },
        {
          type: "scatter",
          mode: "lines+markers",
          y: labels,
          x: stabilityScores,
          name: "Stability",
          marker: {
            color: "#fbbf24",
            size: 9,
            line: { color: "rgba(8, 15, 28, 0.95)", width: 2 },
          },
          line: { color: "#fbbf24", width: 2 },
          hovertemplate: "%{y}<br>Stability: %{x:.1f}<extra></extra>",
        },
      ];

      const layout = {
        barmode: "group",
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#9fb0cf", family: '"Segoe UI", "Helvetica Neue", Arial, sans-serif' },
        margin: { l: 180, r: 28, t: 14, b: 36 },
        legend: {
          orientation: "h",
          x: 0,
          y: 1.18,
          font: { color: "#a9bfd9", size: 11 },
          bgcolor: "rgba(7, 12, 22, 0.82)",
          bordercolor: "rgba(56, 189, 248, 0.16)",
          borderwidth: 1,
        },
        xaxis: {
          range: [0, 100],
          gridcolor: "rgba(148, 163, 184, 0.14)",
          zeroline: false,
          tickfont: { color: "#90a4c4", size: 10 },
          title: { text: "Normalized Health", font: { color: "#7dd3fc", size: 11 } },
        },
        yaxis: {
          tickfont: { color: "#d6e6fb", size: 11 },
          automargin: true,
        },
      };

      await Plotly.react(comparisonChartRef.current, traces, layout, {
        displayModeBar: false,
        responsive: true,
      });
    }

    renderComparisonChart().catch(() => {});
    return () => {
      closed = true;
    };
  }, [data.models]);

  const hasAlert = useMemo(
    () => data.models.some((m) => (parseFloat(m.driftHint) || 0) > 0.3),
    [data.models],
  );

  const getStatusColor = (driftHint: string) => {
    const drift = parseFloat(driftHint) || 0;
    if (drift < 0.1) return "#22c55e";
    if (drift < 0.3) return "#fbbf24";
    return "#fb7185";
  };

  const getStatusText = (driftHint: string) => {
    const drift = parseFloat(driftHint) || 0;
    if (drift < 0.1) return "Optimal";
    if (drift < 0.3) return "Watch";
    return "Alert";
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
          <span className="governance-icon">SYS</span>
          Model Governance
          <span className="governance-badge">Control</span>
        </h3>
        <div className="status-indicator">
          <span
            className="status-dot"
            style={{
              background: hasAlert ? "#fb7185" : "#22c55e",
              boxShadow: `0 0 ${pulseState === 0 ? 12 : 6}px ${hasAlert ? "#fb7185" : "#22c55e"}`,
            }}
          />
          <span style={{ color: hasAlert ? "#fb7185" : "#22c55e" }}>
            {hasAlert ? "Drift detected" : "System healthy"}
          </span>
        </div>
      </div>

      <div className="governance-comparison-section">
        <div className="section-label">Model Comparison</div>
        <div ref={comparisonChartRef} className="governance-comparison-chart" style={{ height: 240 }} />
      </div>

      <div className="governance-metrics">
        <div className="section-label">Model Metrics</div>
        <div className="metrics-grid">
          {data.models.map((m, i) => {
            const isSelected = selectedModel === m.name;
            const statusColor = getStatusColor(m.driftHint);
            const statusText = getStatusText(m.driftHint);
            const modelColor = MODEL_COLORS[i % MODEL_COLORS.length];

            return (
              <div
                key={m.name}
                className={`model-metric-card ${isSelected ? "selected" : ""}`}
                onClick={() => setSelectedModel(isSelected ? null : m.name)}
                style={{
                  borderColor: isSelected ? `${modelColor}88` : "rgba(56, 189, 248, 0.16)",
                  boxShadow: isSelected ? `0 18px 40px rgba(2, 6, 23, 0.34), 0 0 0 1px ${modelColor}33` : "0 18px 40px rgba(2, 6, 23, 0.26)",
                }}
              >
                <div className="model-name" style={{ color: modelColor }}>
                  {m.name}
                </div>

                <div className="metric-gauge">
                  <div className="gauge-label">Latency</div>
                  <div className="gauge-bar-container">
                    <div
                      className="gauge-bar-fill"
                      style={{
                        width: `${clamp(100 - m.latencyMs / 5)}%`,
                        background: `linear-gradient(90deg, ${modelColor}66, ${modelColor})`,
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

                <div className="metric-gauge">
                  <div className="gauge-label">Calibration</div>
                  <div className="gauge-bar-container">
                    <div
                      className="gauge-bar-fill"
                      style={{
                        width: `${clamp(m.calibration * 100)}%`,
                        background: `linear-gradient(90deg, rgba(34, 211, 238, 0.75), ${m.calibration > 0.8 ? "#22d3ee" : "#fbbf24"})`,
                      }}
                    />
                    <div className="gauge-grid-lines">
                      <span /><span /><span /><span />
                    </div>
                  </div>
                  <div className="gauge-value" style={{ color: m.calibration > 0.8 ? "#22d3ee" : "#fbbf24" }}>
                    {(m.calibration * 100).toFixed(1)}%
                  </div>
                </div>

                <div className="model-status-row">
                  <span
                    className="status-pill"
                    style={{
                      background: `${statusColor}1a`,
                      color: statusColor,
                      border: `1px solid ${statusColor}40`,
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

      {data.disagreement.length > 0 && (
        <div className="governance-disagreement">
          <div className="section-label">Model Disagreement Matrix</div>
          <div className="disagreement-heatmap">
            {data.disagreement.map((d) => {
              const maxDisagreement = Math.max(...data.disagreement.map((entry) => entry.value), 0.0001);
              const intensity = Math.min(1, d.value / maxDisagreement);
              const heatColor = intensity > 0.7 ? "#fb7185" : intensity > 0.4 ? "#fbbf24" : "#22d3ee";

              return (
                <div
                  key={`${d.left}-${d.right}`}
                  className="disagreement-cell"
                  style={{
                    background: `linear-gradient(90deg, ${heatColor}12, rgba(8, 15, 28, 0.92))`,
                    borderColor: `${heatColor}3f`,
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
                  background: "rgba(9, 17, 30, 0.96)",
                  border: "1px solid rgba(56, 189, 248, 0.24)",
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
              <div className="stat-value" style={{ color: "#22d3ee" }}>
                {(trendCurrent * 100).toFixed(1)}%
              </div>
            </div>
            <div className="trend-stat">
              <div className="stat-label">Average</div>
              <div className="stat-value" style={{ color: "#fbbf24" }}>
                {(trendAverage * 100).toFixed(1)}%
              </div>
            </div>
            <div className="trend-stat">
              <div className="stat-label">Trend</div>
              <div className="stat-value" style={{ color: trendIsUp ? "#22d3ee" : "#fb7185" }}>
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
                    background: isHigh ? "#fbbf24" : "#22d3ee",
                    boxShadow: isHigh ? "0 0 8px rgba(251, 191, 36, 0.35)" : "none",
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
