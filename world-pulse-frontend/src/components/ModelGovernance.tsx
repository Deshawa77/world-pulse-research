import { useEffect, useMemo, useRef, useState } from "react";
import type { GovernanceData } from "../services/api";

type Props = {
  data: GovernanceData;
};

type ModelMeta = {
  name: string;
  chip: string;
  shortLabel: string;
  fullLabel: string;
};

const MODEL_COLORS = ["#22d3ee", "#38bdf8", "#fbbf24", "#a3e635", "#f472b6"];
const SIGNAL_LINE_COLORS = ["#ff5f6d", "#f59e0b", "#c0266b", "#14b8a6", "#60a5fa"];

function clamp(value: number, min = 0, max = 100) {
  return Math.max(min, Math.min(max, value));
}

function buildSignalValues(points: Array<{ timestamp: string; value: number }>, targetPoints: number, fallback: number): number[] {
  if (targetPoints <= 0) return [];
  const values = points.map((point) => clamp(point.value * 100, 0, 100));

  if (values.length === 0) {
    return Array.from({ length: targetPoints }, (_, idx) => {
      const wave = Math.sin((idx / Math.max(1, targetPoints - 1)) * Math.PI * 3);
      return clamp(fallback + (wave * 8), 6, 98);
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

function toTitleToken(token: string) {
  const lower = token.toLowerCase();

  if (["gb", "rf", "lstm", "rnn", "ml"].includes(lower)) return lower.toUpperCase();
  if (lower === "reg") return "Reg";
  if (lower === "logistic") return "Logistic";
  if (lower === "auto") return "Auto";
  if (lower === "global") return "Global";
  if (lower === "expanded") return "Expanded";
  if (lower === "baseline") return "Baseline";
  if (lower === "contextual") return "Contextual";
  if (lower === "model") return "Model";
  if (lower === "ensemble") return "Ensemble";

  return token.charAt(0).toUpperCase() + token.slice(1);
}

function humanizeText(value: string) {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map(toTitleToken)
    .join(" ");
}

function truncateLabel(label: string, maxLength: number) {
  if (label.length <= maxLength) return label;
  return `${label.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

function prettifyModelName(name: string) {
  const withoutTimestamp = name
    .replace(/_20\d{6,}(?:_\d{4,6})?$/i, "")
    .replace(/-20\d{6,}(?:-\d{4,6})?$/i, "")
    .replace(/^expanded_global_expanded_/i, "expanded_global_")
    .replace(/^expanded_expanded_/i, "expanded_")
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .trim();

  const normalized = withoutTimestamp
    .replace(/\bgb reg\b/gi, "GB Reg")
    .replace(/\bgb model\b/gi, "GB Model")
    .replace(/\brf model\b/gi, "RF Model")
    .replace(/\blogistic model\b/gi, "Logistic")
    .replace(/\bauto gb\b/gi, "Auto GB")
    .replace(/\bauto rf\b/gi, "Auto RF");

  return humanizeText(normalized) || humanizeText(name);
}

function getCompactModelLabel(name: string) {
  const lower = name.toLowerCase();

  if (lower.includes("logistic")) return "Logistic";
  if (lower.includes("gb_reg")) return "GB Reg";
  if (lower.includes("gb_model")) return "GB Model";
  if (lower.includes("rf")) return "RF";
  if (lower.includes("lstm")) return "LSTM";
  if (lower.includes("baseline")) return "Baseline";
  if (lower.includes("contextual")) return "Contextual";

  return truncateLabel(prettifyModelName(name), 18);
}

function buildModelMeta(models: GovernanceData["models"]): ModelMeta[] {
  const labelCounts = new Map<string, number>();

  return models.map((model, index) => {
    const fullLabel = prettifyModelName(model.name);
    const compactLabel = getCompactModelLabel(model.name);
    const seen = labelCounts.get(compactLabel) ?? 0;
    labelCounts.set(compactLabel, seen + 1);

    return {
      name: model.name,
      chip: `M${index + 1}`,
      shortLabel: seen === 0 ? compactLabel : `${compactLabel} ${seen + 1}`,
      fullLabel,
    };
  });
}
function getDriftValue(driftHint: string) {
  const parsed = Number.parseFloat(driftHint);
  if (Number.isFinite(parsed)) return parsed;

  const normalized = driftHint.toLowerCase();
  if (normalized.includes("alert") || normalized.includes("high")) return 0.35;
  if (normalized.includes("watch") || normalized.includes("warn") || normalized.includes("medium")) return 0.18;
  if (normalized.includes("stable") || normalized.includes("low")) return 0.05;
  return 0;
}

function getStatusColor(driftHint: string) {
  const drift = getDriftValue(driftHint);
  if (drift < 0.1) return "#22c55e";
  if (drift < 0.3) return "#fbbf24";
  return "#fb7185";
}

function getStatusText(driftHint: string) {
  const drift = getDriftValue(driftHint);
  if (drift < 0.1) return "Optimal";
  if (drift < 0.3) return "Watch";
  return "Alert";
}

function formatPercent(value: number, decimals = 1) {
  return `${(value * 100).toFixed(decimals)}%`;
}

function formatDriftHint(driftHint: string) {
  const parsed = Number.parseFloat(driftHint);
  if (Number.isFinite(parsed)) return formatPercent(parsed);
  return humanizeText(driftHint);
}

function getModelHealth(model: GovernanceData["models"][number]) {
  const latencyReadiness = clamp(100 - (model.latencyMs / 8));
  const calibration = clamp((model.calibration || 0) * 100);
  const stability = clamp(100 - (getDriftValue(model.driftHint) * 120));
  return (latencyReadiness + calibration + stability) / 3;
}

function getDisagreementTone(value: number, maxValue: number) {
  const intensity = maxValue > 0 ? value / maxValue : 0;

  if (intensity > 0.75 || value >= 0.08) {
    return { color: "#fb7185", label: "Elevated divergence" };
  }

  if (intensity > 0.4 || value >= 0.04) {
    return { color: "#fbbf24", label: "Needs review" };
  }

  return { color: "#22d3ee", label: "Aligned outputs" };
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

  const comparisonModels = useMemo(() => data.models.slice(0, 5), [data.models]);
  const modelMeta = useMemo(() => buildModelMeta(data.models), [data.models]);
  const modelMetaByName = useMemo(() => new Map(modelMeta.map((meta) => [meta.name, meta])), [modelMeta]);

  useEffect(() => {
    if (selectedModel && data.models.some((model) => model.name === selectedModel)) {
      return;
    }

    const preferred = data.selectedCalibrationModel;
    if (preferred && data.models.some((model) => model.name === preferred)) {
      setSelectedModel(preferred);
      return;
    }

    setSelectedModel(data.models[0]?.name ?? null);
  }, [data.models, data.selectedCalibrationModel, selectedModel]);

  const trendModelName = selectedModel && data.models.some((model) => model.name === selectedModel)
    ? selectedModel
    : data.selectedCalibrationModel && data.models.some((model) => model.name === data.selectedCalibrationModel)
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
    return data.models.find((model) => model.name === trendModelName) ?? data.models[0];
  }, [data.models, trendModelName]);

  const selectedModelMeta = selectedModelEntry
    ? modelMetaByName.get(selectedModelEntry.name) ?? null
    : null;

  const controlModelEntry = useMemo(() => {
    if (!data.models.length) return null;

    if (data.selectedCalibrationModel) {
      return data.models.find((model) => model.name === data.selectedCalibrationModel)
        ?? selectedModelEntry
        ?? data.models[0];
    }

    return selectedModelEntry ?? data.models[0];
  }, [data.models, data.selectedCalibrationModel, selectedModelEntry]);

  const controlModelMeta = controlModelEntry
    ? modelMetaByName.get(controlModelEntry.name) ?? null
    : null;

  const governanceHealthScore = useMemo(() => {
    if (!data.models.length) return 0;
    const total = data.models.reduce((sum, model) => sum + getModelHealth(model), 0);
    return Math.round(total / data.models.length);
  }, [data.models]);

  const averageCalibration = useMemo(() => {
    if (!data.models.length) return 0;
    return data.models.reduce((sum, model) => sum + (model.calibration || 0), 0) / data.models.length;
  }, [data.models]);

  const averageLatency = useMemo(() => {
    if (!data.models.length) return 0;
    return data.models.reduce((sum, model) => sum + model.latencyMs, 0) / data.models.length;
  }, [data.models]);

  const maxDisagreement = useMemo(
    () => data.disagreement.reduce((max, entry) => Math.max(max, entry.value), 0),
    [data.disagreement],
  );

  const rankedDisagreements = useMemo(
    () => [...data.disagreement].sort((left, right) => right.value - left.value).slice(0, 8),
    [data.disagreement],
  );

  const highestDisagreement = rankedDisagreements[0] ?? null;
  const highestDisagreementTone = highestDisagreement
    ? getDisagreementTone(highestDisagreement.value, maxDisagreement)
    : null;

  const modelsNeedingAttention = useMemo(
    () => data.models.filter((model) => getDriftValue(model.driftHint) >= 0.1).length,
    [data.models],
  );

  const hasAlert = useMemo(
    () => data.models.some((model) => getDriftValue(model.driftHint) > 0.3),
    [data.models],
  );
  useEffect(() => {
    let closed = false;

    async function renderComparisonChart() {
      if (!comparisonChartRef.current || comparisonModels.length === 0) return;
      const mod = await import("plotly.js-dist-min");
      const Plotly = (mod as any).default ?? mod;
      if (closed || !comparisonChartRef.current) return;

      const latencyScores = comparisonModels.map((model) => clamp(100 - (model.latencyMs / 8)));
      const calibrationScores = comparisonModels.map((model) => clamp((model.calibration || 0) * 100));
      const stabilityScores = comparisonModels.map((model) => clamp(100 - (getDriftValue(model.driftHint) * 120)));
      const pointCounts = new Map<string, number>();
      const plottedPoints = comparisonModels.map((_, index) => {
        const baseX = latencyScores[index];
        const baseY = calibrationScores[index];
        const bucket = `${Math.round(baseX * 2) / 2}:${Math.round(baseY * 2) / 2}`;
        const seen = pointCounts.get(bucket) ?? 0;
        pointCounts.set(bucket, seen + 1);
        const spread = Math.floor(seen / 2) + 1;
        const sign = seen % 2 === 0 ? 1 : -1;

        return {
          x: clamp(baseX + (sign * spread * 1.6), 5, 99),
          y: clamp(baseY + ((-sign) * spread * 1.8), 4, 98),
        };
      });

      const traces = comparisonModels.map((model, index) => {
        const meta = modelMetaByName.get(model.name);
        const chip = meta?.chip ?? `M${index + 1}`;
        const fullLabel = meta?.fullLabel ?? prettifyModelName(model.name);

        return {
          type: "scatter",
          mode: "markers+text",
          x: [plottedPoints[index].x],
          y: [plottedPoints[index].y],
          text: [chip],
          textposition: "middle center",
          textfont: {
            color: "#03131d",
            size: 11,
            family: '"Segoe UI", "Helvetica Neue", Arial, sans-serif',
          },
          cliponaxis: false,
          marker: {
            size: [18 + (stabilityScores[index] * 0.2)],
            color: MODEL_COLORS[index % MODEL_COLORS.length],
            opacity: 0.88,
            line: { color: "rgba(3, 10, 20, 0.96)", width: 2.5 },
            sizemode: "diameter",
          },
          customdata: [stabilityScores[index]],
          name: fullLabel,
          hovertemplate:
            `<b>${chip} · ${fullLabel}</b><br>` +
            "Latency readiness: %{x:.1f}<br>" +
            "Calibration: %{y:.1f}<br>" +
            "Stability: %{customdata:.1f}<extra></extra>",
        };
      });

      const layout = {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#9fb0cf", family: '"Segoe UI", "Helvetica Neue", Arial, sans-serif' },
        margin: { l: 48, r: 16, t: 18, b: 44 },
        xaxis: {
          range: [0, 104],
          gridcolor: "rgba(148, 163, 184, 0.14)",
          zeroline: false,
          tickfont: { color: "#90a4c4", size: 10 },
          automargin: true,
          title: { text: "Latency readiness", font: { color: "#7dd3fc", size: 11 } },
        },
        yaxis: {
          range: [0, 100],
          gridcolor: "rgba(148, 163, 184, 0.14)",
          automargin: true,
          tickfont: { color: "#d6e6fb", size: 10 },
          title: { text: "Calibration", font: { color: "#8fdcff", size: 11 } },
        },
        hoverlabel: {
          bgcolor: "rgba(3, 10, 20, 0.96)",
          bordercolor: "rgba(56, 189, 248, 0.28)",
          font: { color: "#e8f6ff", size: 11 },
        },
        shapes: [
          {
            type: "rect",
            x0: 66,
            y0: 68,
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
            text: "Target envelope",
            showarrow: false,
            xanchor: "right",
            font: { color: "#4ade80", size: 10 },
          },
        ],
        showlegend: false,
        hovermode: "closest",
        dragmode: false,
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
  }, [comparisonModels, modelMetaByName]);

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
      const stability = clamp(100 - (getDriftValue(selectedModelEntry.driftHint) * 120));
      const healthScore = Math.round((latencyReadiness + calibration + stability) / 3);

      const trace = {
        type: "pie",
        labels: ["Latency", "Calibration", "Stability"],
        values: [latencyReadiness, calibration, stability],
        hole: 0.7,
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
          y: -0.12,
          font: { color: "#9fb0cf", size: 10 },
        },
        annotations: [
          {
            text: `<b>${healthScore}%</b><br>health`,
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
      const signalModels = comparisonModels;
      const signalPoints = 20;
      const signalX = Array.from({ length: signalPoints }, (_, index) => index + 1);
      const lineSeries = signalModels.map((model, index) => {
        const sourceSeries = data.calibrationTrendByModel[model.name] ?? data.calibrationTrend;
        const fallback = clamp((model.calibration || 0.5) * 100, 12, 92);
        const values = buildSignalValues(sourceSeries, signalPoints, fallback);
        const meta = modelMetaByName.get(model.name);

        return {
          type: "scatter",
          mode: "lines+markers",
          x: signalX,
          y: values,
          line: {
            color: SIGNAL_LINE_COLORS[index % SIGNAL_LINE_COLORS.length],
            width: 2.8,
            shape: "spline",
            smoothing: 0.85,
          },
          marker: {
            size: 7,
            color: "#fbbf24",
            line: { color: SIGNAL_LINE_COLORS[index % SIGNAL_LINE_COLORS.length], width: 2 },
            opacity: 0.95,
          },
          name: meta?.shortLabel ?? model.name,
          hovertemplate: `${meta?.chip ?? `M${index + 1}`} · ${meta?.fullLabel ?? model.name}<br>Point %{x}: %{y:.1f}%<extra></extra>`,
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
  }, [comparisonModels, data.calibrationTrend, data.calibrationTrendByModel, trendSeries, modelMetaByName]);

  return (
    <div className="futuristic-governance">
      <div className="governance-header">
        <div className="governance-heading-group">
          <h3>
            <span className="governance-icon">SYS</span>
            Model Governance
            <span className="governance-badge">Control</span>
          </h3>
          <p className="governance-subtitle">
            Readiness, calibration, and disagreement across the active model fleet.
          </p>
        </div>
        <div className="status-indicator">
          <span
            className="status-dot"
            style={{
              background: hasAlert ? "#fb7185" : "#22c55e",
              boxShadow: `0 0 ${pulseState === 0 ? 14 : 8}px ${hasAlert ? "#fb7185" : "#22c55e"}`,
            }}
          />
          <div>
            <span style={{ color: hasAlert ? "#fb7185" : "#22c55e" }}>
              {hasAlert ? "Drift detected" : "System healthy"}
            </span>
            <small>{modelsNeedingAttention > 0 ? `${modelsNeedingAttention} models in watch state` : "No model needs intervention"}</small>
          </div>
        </div>
      </div>

      <div className="governance-summary-grid">
        <div className="governance-summary-card accent-cyan">
          <span className="summary-eyebrow">Control focus</span>
          <div className="summary-value-row">
            <span className="summary-chip">{controlModelMeta?.chip ?? "--"}</span>
            <span className="summary-title">{controlModelMeta?.shortLabel ?? "No active model"}</span>
          </div>
          <p className="summary-copy" title={controlModelMeta?.fullLabel ?? undefined}>
            {controlModelMeta?.fullLabel ?? "Calibration target unavailable."}
          </p>
        </div>

        <div className="governance-summary-card accent-violet">
          <span className="summary-eyebrow">Fleet health</span>
          <div className="summary-value">{governanceHealthScore}</div>
          <p className="summary-copy">Composite of latency readiness, calibration, and stability.</p>
        </div>

        <div className="governance-summary-card accent-amber">
          <span className="summary-eyebrow">Average calibration</span>
          <div className="summary-value">{formatPercent(averageCalibration)}</div>
          <p className="summary-copy">Average latency {averageLatency.toFixed(0)}ms across {data.models.length || 0} models.</p>
        </div>
        <div className="governance-summary-card accent-rose">
          <span className="summary-eyebrow">Peak disagreement</span>
          <div className="summary-value" style={{ color: highestDisagreementTone?.color ?? "#e8f6ff" }}>
            {highestDisagreement ? formatPercent(highestDisagreement.value) : "0.0%"}
          </div>
          <p className="summary-copy">
            {highestDisagreement
              ? `${modelMetaByName.get(highestDisagreement.left)?.chip ?? "M?"} vs ${modelMetaByName.get(highestDisagreement.right)?.chip ?? "M?"}`
              : "Consensus holding across model pairs."}
          </p>
        </div>
      </div>

      <div className="governance-comparison-section">
        <div className="governance-section-header">
          <div>
            <div className="section-label">Model Comparison</div>
            <p className="section-copy">
              Latency readiness versus calibration. Bubble size reflects stability, and chart chips map to the legend.
            </p>
          </div>
          <div className="section-note">{comparisonModels.length} active models</div>
        </div>

        <div className="governance-comparison-layout">
          <div className="governance-comparison-stage">
            <div ref={comparisonChartRef} className="governance-comparison-chart" style={{ height: 300 }} />
          </div>

          <div className="comparison-model-list">
            {comparisonModels.map((model, index) => {
              const meta = modelMetaByName.get(model.name);
              const statusColor = getStatusColor(model.driftHint);
              const statusText = getStatusText(model.driftHint);
              const modelColor = MODEL_COLORS[index % MODEL_COLORS.length];

              return (
                <button
                  type="button"
                  key={model.name}
                  className={`comparison-model-item ${selectedModel === model.name ? "selected" : ""}`}
                  onClick={() => setSelectedModel(model.name)}
                  title={meta?.fullLabel ?? model.name}
                >
                  <span
                    className="comparison-model-chip"
                    style={{
                      color: modelColor,
                      borderColor: `${modelColor}55`,
                      background: `${modelColor}1a`,
                    }}
                  >
                    {meta?.chip ?? `M${index + 1}`}
                  </span>
                  <div className="comparison-model-copy">
                    <div className="comparison-model-head">
                      <span className="comparison-model-title">{meta?.shortLabel ?? prettifyModelName(model.name)}</span>
                      <span
                        className="comparison-model-status"
                        style={{
                          color: statusColor,
                          borderColor: `${statusColor}44`,
                          background: `${statusColor}14`,
                        }}
                      >
                        {statusText}
                      </span>
                    </div>
                    <div className="comparison-model-subtitle">{meta?.fullLabel ?? model.name}</div>
                    <div className="comparison-model-metrics">
                      <span>Cal {formatPercent(model.calibration)}</span>
                      <span>Lat {model.latencyMs.toFixed(0)}ms</span>
                      <span>Drift {formatDriftHint(model.driftHint)}</span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="governance-visual-grid">
        <div className="governance-visual-card">
          <div className="governance-section-header compact">
            <div>
              <div className="section-label">Health Composition</div>
              <p className="section-copy">Distribution of readiness, calibration, and stability for the selected model.</p>
            </div>
            {selectedModelMeta && <div className="section-note">{selectedModelMeta.chip}</div>}
          </div>
          {selectedModelMeta && (
            <div className="visual-model-context" title={selectedModelMeta.fullLabel}>
              {selectedModelMeta.fullLabel}
            </div>
          )}
          <div ref={healthDonutRef} className="governance-donut-chart" />
        </div>

        <div className="governance-visual-card">
          <div className="governance-section-header compact">
            <div>
              <div className="section-label">Calibration Area Pulse</div>
              <p className="section-copy">Short-horizon calibration movement for the active control model.</p>
            </div>
          </div>
          <div ref={pulseAreaRef} className="governance-area-chart" />
        </div>
      </div>

      <div className="governance-metrics">
        <div className="governance-section-header compact">
          <div>
            <div className="section-label">Model Metrics</div>
            <p className="section-copy">Select any card to sync the health and trend views.</p>
          </div>
        </div>
        <div className="metrics-grid">
          {data.models.map((model, index) => {
            const isSelected = selectedModel === model.name;
            const statusColor = getStatusColor(model.driftHint);
            const statusText = getStatusText(model.driftHint);
            const modelColor = MODEL_COLORS[index % MODEL_COLORS.length];
            const meta = modelMetaByName.get(model.name);

            return (
              <div
                key={model.name}
                className={`model-metric-card ${isSelected ? "selected" : ""}`}
                onClick={() => setSelectedModel(isSelected ? null : model.name)}
                style={{
                  borderColor: isSelected ? `${modelColor}88` : "rgba(56, 189, 248, 0.16)",
                  boxShadow: isSelected
                    ? `0 18px 40px rgba(2, 6, 23, 0.34), 0 0 0 1px ${modelColor}33`
                    : "0 18px 40px rgba(2, 6, 23, 0.26)",
                }}
              >
                <div className="model-card-heading">
                  <span
                    className="model-card-chip"
                    style={{
                      color: modelColor,
                      borderColor: `${modelColor}55`,
                      background: `${modelColor}14`,
                    }}
                  >
                    {meta?.chip ?? `M${index + 1}`}
                  </span>
                  <div className="model-name-stack">
                    <div className="model-name" style={{ color: modelColor }}>
                      {meta?.shortLabel ?? prettifyModelName(model.name)}
                    </div>
                    <div className="model-name-subtitle" title={meta?.fullLabel ?? model.name}>
                      {meta?.fullLabel ?? model.name}
                    </div>
                  </div>
                </div>

                <div className="metric-gauge">
                  <div className="gauge-label">Latency</div>
                  <div className="gauge-bar-container">
                    <div
                      className="gauge-bar-fill"
                      style={{
                        width: `${clamp(100 - (model.latencyMs / 5))}%`,
                        background: `linear-gradient(90deg, ${modelColor}55, ${modelColor})`,
                      }}
                    />
                    <div className="gauge-grid-lines">
                      <span /><span /><span /><span />
                    </div>
                  </div>
                  <div className="gauge-value" style={{ color: modelColor }}>
                    {model.latencyMs.toFixed(0)}ms
                  </div>
                </div>

                <div className="metric-gauge">
                  <div className="gauge-label">Calibration</div>
                  <div className="gauge-bar-container">
                    <div
                      className="gauge-bar-fill"
                      style={{
                        width: `${clamp(model.calibration * 100)}%`,
                        background: `linear-gradient(90deg, rgba(34, 211, 238, 0.75), ${model.calibration > 0.8 ? "#22d3ee" : "#fbbf24"})`,
                      }}
                    />
                    <div className="gauge-grid-lines">
                      <span /><span /><span /><span />
                    </div>
                  </div>
                  <div className="gauge-value" style={{ color: model.calibration > 0.8 ? "#22d3ee" : "#fbbf24" }}>
                    {formatPercent(model.calibration)}
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
                  <span className="drift-value">Drift {formatDriftHint(model.driftHint)}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {rankedDisagreements.length > 0 && (
        <div className="governance-disagreement">
          <div className="governance-section-header compact">
            <div>
              <div className="section-label">Model Disagreement Matrix</div>
              <p className="section-copy">Highest-output divergence pairs, sorted from most to least concerning.</p>
            </div>
          </div>
          <div className="disagreement-heatmap">
            {rankedDisagreements.map((entry, index) => {
              const tone = getDisagreementTone(entry.value, maxDisagreement);
              const leftMeta = modelMetaByName.get(entry.left);
              const rightMeta = modelMetaByName.get(entry.right);
              const intensity = maxDisagreement > 0 ? entry.value / maxDisagreement : 0;

              return (
                <div
                  key={`${entry.left}-${entry.right}`}
                  className={`disagreement-cell ${index === 0 ? "top" : ""}`}
                  style={{
                    background: `linear-gradient(180deg, ${tone.color}12, rgba(8, 15, 28, 0.94))`,
                    borderColor: `${tone.color}40`,
                  }}
                  title={`${leftMeta?.fullLabel ?? entry.left} vs ${rightMeta?.fullLabel ?? entry.right}`}
                >
                  <div className="disagreement-cell-header">
                    <div className="disagreement-pair-chip-row">
                      <span className="disagreement-model-chip">{leftMeta?.chip ?? "M?"}</span>
                      <span className="disagreement-arrow" style={{ color: tone.color }}>↔</span>
                      <span className="disagreement-model-chip">{rightMeta?.chip ?? "M?"}</span>
                    </div>
                    <div className="cell-value" style={{ color: tone.color }}>
                      {formatPercent(entry.value)}
                    </div>
                  </div>
                  <div className="cell-models">
                    {(leftMeta?.shortLabel ?? prettifyModelName(entry.left))} vs {(rightMeta?.shortLabel ?? prettifyModelName(entry.right))}
                  </div>
                  <div className="cell-caption">{tone.label}</div>
                  <div className="cell-bar-track">
                    <div
                      className="cell-bar"
                      style={{
                        width: `${intensity * 100}%`,
                        background: `linear-gradient(90deg, ${tone.color}, ${tone.color}88)`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {trendSeries.length > 0 && (
        <div className="governance-trend">
          <div className="governance-section-header compact">
            <div>
              <div className="section-label">Calibration Trend</div>
              <p className="section-copy">Live calibration track for the selected model and supporting comparison signals.</p>
            </div>
            <div className="governance-select-row">
              <label className="governance-select-label">
                Model
                <select
                  value={trendModelName ?? ""}
                  onChange={(event) => setSelectedModel(event.target.value || null)}
                  className="governance-select"
                >
                  {data.models.map((model) => {
                    const meta = modelMetaByName.get(model.name);
                    return (
                      <option key={model.name} value={model.name}>
                        {meta ? `${meta.chip} · ${meta.shortLabel}` : model.name}
                      </option>
                    );
                  })}
                </select>
              </label>
            </div>
          </div>
          <div className="trend-stats">
            <div className="trend-stat">
              <div className="stat-label">Current</div>
              <div className="stat-value" style={{ color: "#22d3ee" }}>
                {formatPercent(trendCurrent)}
              </div>
            </div>
            <div className="trend-stat">
              <div className="stat-label">Average</div>
              <div className="stat-value" style={{ color: "#fbbf24" }}>
                {formatPercent(trendAverage)}
              </div>
            </div>
            <div className="trend-stat">
              <div className="stat-label">Direction</div>
              <div className="stat-value" style={{ color: trendIsUp ? "#22d3ee" : "#fb7185" }}>
                {trendIsUp ? "Rising" : "Falling"}
              </div>
            </div>
          </div>
          <div ref={trendAreaRef} className="trend-area-chart" />
        </div>
      )}
    </div>
  );
}
