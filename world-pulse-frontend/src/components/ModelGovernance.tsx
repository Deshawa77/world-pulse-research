import { useEffect, useMemo, useRef, useState } from "react";
import type { GovernanceData } from "../services/api";

type Props = {
  data: GovernanceData;
};

const MODEL_COLORS = ["#22d3ee", "#38bdf8", "#fbbf24", "#a3e635", "#94a3b8"];
const SIGNAL_LINE_COLORS = ["#ff5f6d", "#f59e0b", "#c0266b"];

function clamp(value: number, min = 0, max = 100) {
  return Math.max(min, Math.min(max, value));
}

function buildSignalValues(points: Array<{ timestamp: string; value: number }>, targetPoints: number, fallback: number): number[] {
  if (targetPoints <= 0) return [];
  const values = points.map((point) => clamp(point.value * 100, 0, 100));

  if (values.length === 0) {
    return Array.from({ length: targetPoints }, (_, idx) => {
      const wave = Math.sin((idx / Math.max(1, targetPoints - 1)) * Math.PI * 3);
      return clamp(fallback + wave * 8, 6, 98);
    });
  }

  if (values.length === 1) {
    return Array.from({ length: targetPoints }, () => values[0]);
  }

  return Array.from({ length: targetPoints }, (_, idx) => {
    const sourceIndex = (idx * (values.length - 1)) / Math.max(1, targetPoints - 1);
    const lower = Math.floor(sourceIndex);
    const upper = Math.ceil(sourceIndex);
    if (lower === upper) return values[lower];
    const ratio = sourceIndex - lower;
    return clamp((values[lower] * (1 - ratio)) + (values[upper] * ratio), 0, 100);
  });
}

export default function ModelGovernance({ data }: Props) {
  const comparisonChartRef = useRef<HTMLDivElement | null>(null);
  const healthDonutRef = useRef<HTMLDivElement | null>(null);
  const pulseAreaRef = useRef<HTMLDivElement | null>(null);
  const trendAreaRef = useRef<HTMLDivElement | null>(null);
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

  const selectedModelEntry = useMemo(() => {
    if (!data.models.length) return null;
    return data.models.find((m) => m.name === trendModelName) ?? data.models[0];
  }, [data.models, trendModelName]);

  useEffect(() => {
    let closed = false;

    async function renderComparisonChart() {
      if (!comparisonChartRef.current || data.models.length === 0) return;
      const mod = await import("plotly.js-dist-min");
      const Plotly = (mod as any).default ?? mod;
      if (closed || !comparisonChartRef.current) return;

      const models = data.models.slice(0, 5);
      const latencyScores = models.map((m) => clamp(100 - (m.latencyMs / 8)));
      const calibrationScores = models.map((m) => clamp((m.calibration || 0) * 100));
      const stabilityScores = models.map((m) => clamp(100 - ((parseFloat(m.driftHint) || 0) * 120)));
      const pointCounts = new Map<string, number>();
      const plottedPoints = models.map((_, idx) => {
        const baseX = latencyScores[idx];
        const baseY = calibrationScores[idx];
        const bucket = `${Math.round(baseX * 2) / 2}:${Math.round(baseY * 2) / 2}`;
        const seen = pointCounts.get(bucket) ?? 0;
        pointCounts.set(bucket, seen + 1);
        const spread = Math.floor(seen / 2) + 1;
        const sign = seen % 2 === 0 ? 1 : -1;
        return {
          x: clamp(baseX + (sign * spread * 1.8), 3, 99),
          y: clamp(baseY + ((-sign) * spread * 2.2), 2, 98),
        };
      });

      const traces = models.map((m, idx) => ({
        type: "scatter",
        mode: "markers+text",
        x: [plottedPoints[idx].x],
        y: [plottedPoints[idx].y],
        text: [m.name],
        textposition: plottedPoints[idx].x > 90 ? "middle left" : plottedPoints[idx].x < 12 ? "middle right" : "top center",
        textfont: { color: "#c9dcf8", size: 10 },
        cliponaxis: false,
        marker: {
          size: [12 + (stabilityScores[idx] * 0.28)],
          color: MODEL_COLORS[idx % MODEL_COLORS.length],
          opacity: 0.86,
          line: { color: "rgba(8, 15, 28, 0.94)", width: 2 },
          sizemode: "diameter",
        },
        customdata: [stabilityScores[idx]],
        name: m.name,
        hovertemplate:
          "<b>%{text}</b><br>" +
          "Latency readiness: %{x:.1f}<br>" +
          "Calibration: %{y:.1f}<br>" +
          "Stability: %{customdata:.1f}<extra></extra>",
      }));

      const layout = {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#9fb0cf", family: '"Segoe UI", "Helvetica Neue", Arial, sans-serif' },
        margin: { l: 40, r: 20, t: 16, b: 42 },
        legend: {
          orientation: "v",
          x: 1.02,
          y: 1.0,
          font: { color: "#a9bfd9", size: 10 },
          bgcolor: "rgba(7, 12, 22, 0.72)",
          bordercolor: "rgba(56, 189, 248, 0.16)",
          borderwidth: 1,
        },
        xaxis: {
          range: [0, 104],
          gridcolor: "rgba(148, 163, 184, 0.14)",
          zeroline: false,
          tickfont: { color: "#90a4c4", size: 10 },
          automargin: true,
          title: { text: "Latency Readiness", font: { color: "#7dd3fc", size: 11 } },
        },
        yaxis: {
          range: [0, 100],
          gridcolor: "rgba(148, 163, 184, 0.14)",
          automargin: true,
          tickfont: { color: "#d6e6fb", size: 10 },
          title: { text: "Calibration", font: { color: "#8fdcff", size: 11 } },
        },
        shapes: [
          {
            type: "rect",
            x0: 65,
            y0: 65,
            x1: 100,
            y1: 100,
            fillcolor: "rgba(34, 197, 94, 0.08)",
            line: { width: 0 },
          },
          {
            type: "line",
            x0: 0,
            y0: 50,
            x1: 100,
            y1: 50,
            line: { color: "rgba(148, 163, 184, 0.16)", width: 1, dash: "dot" },
          },
          {
            type: "line",
            x0: 50,
            y0: 0,
            x1: 50,
            y1: 100,
            line: { color: "rgba(148, 163, 184, 0.16)", width: 1, dash: "dot" },
          },
        ],
        annotations: [
          {
            x: 98,
            y: 98,
            xref: "x",
            yref: "y",
            text: "High confidence zone",
            showarrow: false,
            xanchor: "right",
            font: { color: "#4ade80", size: 10 },
          },
        ],
        showlegend: false,
        hovermode: "closest",
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

  useEffect(() => {
    let closed = false;

    async function renderHealthDonut() {
      if (!healthDonutRef.current || !selectedModelEntry) return;
      const mod = await import("plotly.js-dist-min");
      const Plotly = (mod as any).default ?? mod;
      if (closed || !healthDonutRef.current) return;
      const targetHeight = Math.max(160, healthDonutRef.current.clientHeight || 210);

      const latencyReadiness = clamp(100 - (selectedModelEntry.latencyMs / 8));
      const calibration = clamp((selectedModelEntry.calibration || 0) * 100);
      const stability = clamp(100 - ((parseFloat(selectedModelEntry.driftHint) || 0) * 120));

      const trace = {
        type: "pie",
        labels: ["Latency", "Calibration", "Stability"],
        values: [latencyReadiness, calibration, stability],
        hole: 0.68,
        sort: false,
        textinfo: "none",
        marker: {
          colors: ["#22d3ee", "#a78bfa", "#fbbf24"],
          line: { color: "rgba(3, 10, 20, 0.96)", width: 2 },
        },
        hovertemplate: "%{label}: %{value:.1f}<extra></extra>",
      };

      const layout = {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        margin: { l: 6, r: 6, t: 6, b: 28 },
        height: targetHeight,
        showlegend: true,
        legend: {
          orientation: "h",
          x: 0.5,
          xanchor: "center",
          y: -0.1,
          font: { color: "#9fb0cf", size: 10 },
        },
        annotations: [
          {
            text: `<b>${Math.round((latencyReadiness + calibration + stability) / 3)}</b><br>health`,
            showarrow: false,
            font: { color: "#d7ecff", size: 12 },
          },
        ],
      };

      await Plotly.react(healthDonutRef.current, [trace], layout, {
        displayModeBar: false,
        responsive: true,
      });
    }

    renderHealthDonut().catch(() => {});
    return () => {
      closed = true;
    };
  }, [selectedModelEntry]);

  useEffect(() => {
    let closed = false;

    async function renderTrendArea() {
      if (trendSeries.length === 0) return;
      const mod = await import("plotly.js-dist-min");
      const Plotly = (mod as any).default ?? mod;
      if (closed) return;

      const xValues = trendSeries.map((point) => point.timestamp);
      const yValues = trendSeries.map((point) => clamp(point.value * 100, 0, 100));

      const pulseTrace = {
        type: "scatter",
        mode: "lines+markers",
        x: xValues,
        y: yValues,
        line: { color: "#a78bfa", width: 2.5, shape: "spline" },
        marker: { color: "#22d3ee", size: 6 },
        fill: "tozeroy",
        fillcolor: "rgba(167, 139, 250, 0.18)",
        hovertemplate: "Calibration %{y:.1f}%<extra></extra>",
      };

      if (pulseAreaRef.current) {
        const pulseTarget = pulseAreaRef.current;
        const targetHeight = Math.max(160, pulseTarget.clientHeight || 210);
        const pulseLayout = {
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          margin: { l: 36, r: 12, t: 8, b: 30 },
          height: targetHeight,
          xaxis: {
            showgrid: false,
            tickfont: { color: "#8ea6c8", size: 10 },
            nticks: 4,
          },
          yaxis: {
            range: [0, 100],
            gridcolor: "rgba(148, 163, 184, 0.14)",
            tickfont: { color: "#8ea6c8", size: 10 },
            ticksuffix: "%",
          },
        };

        await Plotly.react(pulseTarget, [pulseTrace], pulseLayout, {
          displayModeBar: false,
          responsive: true,
        });
      }

      if (!trendAreaRef.current) return;

      const trendTarget = trendAreaRef.current;
      const trendHeight = Math.max(180, trendTarget.clientHeight || 230);
      const signalModels = data.models.slice(0, 5);
      const signalPoints = 20;
      const signalX = Array.from({ length: signalPoints }, (_, idx) => idx + 1);
      const lineSeries = signalModels.map((model, idx) => {
        const sourceSeries = data.calibrationTrendByModel[model.name] ?? data.calibrationTrend;
        const fallback = clamp((model.calibration || 0.5) * 100, 12, 92);
        const values = buildSignalValues(sourceSeries, signalPoints, fallback);
        return {
          type: "scatter",
          mode: "lines+markers",
          x: signalX,
          y: values,
          line: {
            color: SIGNAL_LINE_COLORS[idx % SIGNAL_LINE_COLORS.length],
            width: 2.8,
            shape: "spline",
            smoothing: 0.85,
          },
          marker: {
            size: 8,
            color: "#fbbf24",
            line: { color: SIGNAL_LINE_COLORS[idx % SIGNAL_LINE_COLORS.length], width: 2 },
            opacity: 0.95,
          },
          name: model.name,
          hovertemplate: `${model.name}<br>Point %{x}: %{y:.1f}%<extra></extra>`,
        };
      });

      const signalLayout = {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(12, 10, 14, 0.96)",
        margin: { l: 20, r: 20, t: 14, b: 32 },
        height: trendHeight,
        showlegend: false,
        hovermode: "x",
        xaxis: {
          range: [0.8, signalPoints + 0.4],
          showgrid: false,
          showticklabels: false,
          showline: true,
          linecolor: "rgba(176, 54, 48, 0.72)",
          linewidth: 2,
          tickmode: "linear",
          dtick: 1.5,
          ticklen: 7,
          tickwidth: 2,
          tickcolor: "rgba(176, 54, 48, 0.56)",
          fixedrange: true,
        },
        yaxis: {
          range: [0, 100],
          showgrid: false,
          showticklabels: false,
          zeroline: false,
          fixedrange: true,
        },
        shapes: [
          {
            type: "line",
            x0: 0.85,
            y0: 0,
            x1: 0.85,
            y1: 7,
            line: { color: "rgba(176, 54, 48, 0.72)", width: 2 },
          },
          {
            type: "line",
            x0: signalPoints + 0.15,
            y0: 0,
            x1: signalPoints + 0.15,
            y1: 7,
            line: { color: "rgba(176, 54, 48, 0.72)", width: 2 },
          },
        ],
      };

      await Plotly.react(trendTarget, lineSeries, signalLayout, {
        displayModeBar: false,
        responsive: true,
      });
    }

    renderTrendArea().catch(() => {});
    return () => {
      closed = true;
    };
  }, [data.calibrationTrend, data.calibrationTrendByModel, data.models, trendSeries]);

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

      <div className="governance-visual-grid">
        <div className="governance-visual-card">
          <div className="section-label">Health Composition</div>
          <div ref={healthDonutRef} className="governance-donut-chart" />
        </div>
        <div className="governance-visual-card">
          <div className="section-label">Calibration Area Pulse</div>
          <div ref={pulseAreaRef} className="governance-area-chart" />
        </div>
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
          <div ref={trendAreaRef} className="trend-area-chart" />
        </div>
      )}
    </div>
  );
}
