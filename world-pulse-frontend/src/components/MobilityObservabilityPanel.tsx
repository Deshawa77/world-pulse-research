import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts";

type Props = {
  mobilitySnapshot: Record<string, unknown> | null;
};

type MobilityRow = Record<string, unknown>;

function safeNumber(value: unknown, fallback = 0): number {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function safeString(value: unknown, fallback = "n/a"): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function sourceRow(snapshot: Record<string, unknown> | null, key: string): Record<string, unknown> {
  const sources = snapshot?.sources;
  if (!sources || typeof sources !== "object") return {};
  const value = (sources as Record<string, unknown>)[key];
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asPercent(value: unknown): string {
  return `${(safeNumber(value) * 100).toFixed(1)} / 100`;
}

function asAbsolute(value: unknown): string {
  return `${safeNumber(value).toFixed(1)} / 100`;
}

function formatClock(value: unknown): string {
  const raw = safeString(value, "");
  if (!raw) return "n/a";
  const stamp = new Date(raw);
  if (Number.isNaN(stamp.getTime())) return raw;
  return stamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function toPercent(value: unknown): number {
  return Math.round(safeNumber(value) * 1000) / 10;
}

function toAbsolute(value: unknown): number {
  return Math.round(safeNumber(value) * 10) / 10;
}

export default function MobilityObservabilityPanel({ mobilitySnapshot }: Props) {
  const displacement = sourceRow(mobilitySnapshot, "displacement");
  const aviation = sourceRow(mobilitySnapshot, "aviation");
  const logistics = sourceRow(mobilitySnapshot, "logistics");
  const topCountries = useMemo(
    () => (Array.isArray(mobilitySnapshot?.top_countries)
      ? (mobilitySnapshot?.top_countries as MobilityRow[])
      : []),
    [mobilitySnapshot],
  );
  const chartRows = useMemo(() => topCountries.slice(0, 6), [topCountries]);
  const combinedCountryCount = safeNumber(mobilitySnapshot?.combined_country_count);
  const overlapRatio = safeNumber(mobilitySnapshot?.crosscheck_overlap_ratio) * 100;
  const status = safeString(mobilitySnapshot?.status, "monitoring");
  const generatedAt = safeString(mobilitySnapshot?.generated_at, "");
  const mixChartRef = useRef<HTMLDivElement | null>(null);
  const mixChartInstanceRef = useRef<echarts.ECharts | null>(null);
  const trendChartRef = useRef<HTMLDivElement | null>(null);
  const trendChartInstanceRef = useRef<echarts.ECharts | null>(null);

  const labels = useMemo(
    () => chartRows.map((row) => safeString(row.country_name, safeString(row.country, "UNK"))),
    [chartRows],
  );
  const displacementSeries = useMemo(
    () => chartRows.map((row) => toPercent(row.normalized_displaced_pressure)),
    [chartRows],
  );
  const aviationSeries = useMemo(
    () => chartRows.map((row) => toPercent(row.aviation_disruption_score)),
    [chartRows],
  );
  const logisticsSeries = useMemo(
    () => chartRows.map((row) => toPercent(row.logistics_stress_score)),
    [chartRows],
  );
  const severityValues = useMemo(
    () => chartRows.map((row) => toPercent(row.severity_score)),
    [chartRows],
  );
  const riskValues = useMemo(
    () => chartRows.map((row) => Math.min(100, toAbsolute(row.risk_score) * 10)),
    [chartRows],
  );

  const averageSeverity = useMemo(() => {
    if (!severityValues.length) return 0;
    return severityValues.reduce((sum, value) => sum + value, 0) / severityValues.length;
  }, [severityValues]);

  const averageRisk = useMemo(() => {
    if (!riskValues.length) return 0;
    return riskValues.reduce((sum, value) => sum + value, 0) / riskValues.length;
  }, [riskValues]);

  useEffect(() => {
    if (!mixChartRef.current) return;
    if (!mixChartInstanceRef.current) {
      mixChartInstanceRef.current = echarts.init(mixChartRef.current);
    }
    const chart = mixChartInstanceRef.current;
    const option: echarts.EChartsOption = {
      animationDuration: 650,
      animationDurationUpdate: 450,
      color: ["#7c6cf6", "#61a9ff", "#2dd4bf"],
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "rgba(8, 18, 34, 0.96)",
        borderColor: "rgba(124, 108, 246, 0.32)",
        textStyle: { color: "#e2e8f0" },
      },
      legend: {
        top: 0,
        left: 0,
        icon: "circle",
        itemWidth: 9,
        itemHeight: 9,
        textStyle: { color: "#8ea2bd", fontSize: 11 },
        data: ["Displacement", "Aviation", "Logistics"],
      },
      grid: {
        left: 32,
        right: 16,
        top: 42,
        bottom: 28,
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { color: "#94a3b8", fontSize: 11, interval: 0 },
        axisLine: { lineStyle: { color: "rgba(148, 163, 184, 0.14)" } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        max: 100,
        axisLabel: { color: "#64748b", fontSize: 11 },
        splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.08)" } },
      },
      series: [
        {
          name: "Displacement",
          type: "bar",
          stack: "composition",
          barWidth: 28,
          itemStyle: { color: "#7c6cf6", borderRadius: [10, 10, 0, 0] },
          emphasis: { focus: "series" },
          data: displacementSeries,
        },
        {
          name: "Aviation",
          type: "bar",
          stack: "composition",
          barWidth: 28,
          itemStyle: { color: "#61a9ff" },
          emphasis: { focus: "series" },
          data: aviationSeries,
        },
        {
          name: "Logistics",
          type: "bar",
          stack: "composition",
          barWidth: 28,
          itemStyle: { color: "#2dd4bf", borderRadius: [10, 10, 0, 0] },
          emphasis: { focus: "series" },
          data: logisticsSeries,
        },
      ],
      graphic: labels.length
        ? []
        : [{
            type: "text",
            left: "center",
            top: "middle",
            style: {
              text: "Awaiting mobility source rows",
              fill: "#94a3b8",
              fontSize: 13,
              fontWeight: 600,
            },
          }],
    };
    chart.setOption(option, true);
    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(mixChartRef.current);
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", handleResize);
    };
  }, [aviationSeries, displacementSeries, labels, logisticsSeries, severityValues]);

  useEffect(() => {
    if (!trendChartRef.current) return;
    if (!trendChartInstanceRef.current) {
      trendChartInstanceRef.current = echarts.init(trendChartRef.current);
    }
    const chart = trendChartInstanceRef.current;
    const option: echarts.EChartsOption = {
      animationDuration: 700,
      animationDurationUpdate: 480,
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(8, 18, 34, 0.96)",
        borderColor: "rgba(35, 163, 255, 0.28)",
        textStyle: { color: "#e2e8f0" },
      },
      grid: {
        left: 16,
        right: 20,
        top: 20,
        bottom: 22,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: labels,
        axisLabel: { color: "#8b95a7", fontSize: 11, margin: 14 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLabel: { color: "#65748b", fontSize: 11 },
        splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.08)" } },
      },
      series: [
        {
          name: "Risk Score",
          type: "bar",
          barWidth: 22,
          data: riskValues,
          itemStyle: {
            borderRadius: [10, 10, 0, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(255, 111, 120, 0.95)" },
              { offset: 1, color: "rgba(255, 111, 120, 0.58)" },
            ]),
          },
        },
        {
          name: "Severity",
          type: "line",
          smooth: 0.5,
          symbol: "circle",
          symbolSize: 10,
          data: severityValues,
          lineStyle: {
            width: 4,
            color: "#2693f2",
            shadowBlur: 12,
            shadowColor: "rgba(38, 147, 242, 0.25)",
          },
          itemStyle: {
            color: "#1b1b1b",
            borderColor: "#2693f2",
            borderWidth: 4,
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(38, 147, 242, 0.28)" },
              { offset: 0.6, color: "rgba(38, 147, 242, 0.08)" },
              { offset: 1, color: "rgba(38, 147, 242, 0.01)" },
            ]),
          },
        },
      ],
      graphic: labels.length
        ? []
        : [{
            type: "text",
            left: "center",
            top: "middle",
            style: {
              text: "Country ranking will appear here",
              fill: "#94a3b8",
              fontSize: 13,
              fontWeight: 600,
            },
          }],
    };
    chart.setOption(option, true);
    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(trendChartRef.current);
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", handleResize);
    };
  }, [labels, riskValues, severityValues]);

  useEffect(() => () => {
    mixChartInstanceRef.current?.dispose();
    mixChartInstanceRef.current = null;
    trendChartInstanceRef.current?.dispose();
    trendChartInstanceRef.current = null;
  }, []);

  return (
    <article className="wp-card panel-frame operational-panel mobility-observability-panel mobility-observability-panel--full">
      <div className="panel-head analytics-panel-head">
        <h3>Mobility Severity</h3>
        <span className={`analytics-pill ${status !== "healthy" ? "is-warning" : ""}`}>{status}</span>
      </div>
      <div className="panel-content operational-panel-content">
        <div className="operational-panel-intro">
          Live mobility severity using direct backend metrics only: stacked displacement, aviation, and logistics scores on the left, with severity and risk score on the right.
        </div>
        <div className="mobility-observability-grid">
          <article className="mobility-observability-card">
            <span>Displacement</span>
            <strong>{safeNumber(displacement.country_count)}</strong>
            <small>Last update {safeString(displacement.last_updated, "n/a")}</small>
          </article>
          <article className="mobility-observability-card">
            <span>Aviation</span>
            <strong>{safeNumber(aviation.country_count)}</strong>
            <small>Last update {safeString(aviation.last_updated, "n/a")}</small>
          </article>
          <article className="mobility-observability-card">
            <span>Logistics</span>
            <strong>{safeNumber(logistics.country_count)}</strong>
            <small>Last update {safeString(logistics.last_updated, "n/a")}</small>
          </article>
          <article className="mobility-observability-card">
            <span>Combined Coverage</span>
            <strong>{combinedCountryCount}</strong>
            <small>{overlapRatio.toFixed(1)}% displacement/aviation overlap</small>
          </article>
        </div>
        <div className="mobility-observability-meta">
          <span className="mobility-observability-live">Live chart refreshes with the dashboard trust snapshot.</span>
          <span>Snapshot {formatClock(generatedAt || displacement.last_updated || aviation.last_updated || logistics.last_updated)}</span>
        </div>
        <div className="mobility-observability-chart-board">
          <article className="mobility-observability-chart-card mobility-observability-chart-card--wide mobility-observability-chart-card--light">
            <div className="mobility-observability-chart-title">Signal Composition by Country</div>
            <div className="mobility-observability-chart-subtitle">Actual displacement, aviation disruption, and logistics stress scores for each country.</div>
            <div ref={mixChartRef} className="mobility-observability-mini-chart mobility-observability-mini-chart--tall" aria-label="Mobility signal composition chart" />
          </article>
          <article className="mobility-observability-chart-card mobility-observability-chart-card--dark-trend">
            <div className="mobility-observability-trend-top">
              <div className="mobility-observability-trend-kpis">
                <div className="mobility-observability-trend-stat">
                  <strong>{combinedCountryCount}</strong>
                  <span>Countries</span>
                </div>
                <div className="mobility-observability-trend-stat mobility-observability-trend-stat--wide">
                  <strong>{averageSeverity.toFixed(1)} / 100</strong>
                  <span>Avg Severity</span>
                  <em>{averageRisk.toFixed(1)} avg risk score</em>
                </div>
              </div>
            </div>
            <div className="mobility-observability-chart-title">Severity vs Risk Pressure</div>
            <div className="mobility-observability-chart-subtitle">Severity score line over actual risk score bars for the same countries.</div>
            <div ref={trendChartRef} className="mobility-observability-mini-chart mobility-observability-mini-chart--trend" aria-label="Mobility severity trend chart" />
          </article>
        </div>
        <div className="mobility-observability-list" role="list" aria-label="Country mobility severity ranking">
          {chartRows.map((row, index) => (
            <div key={`${safeString(row.country, "UNK")}-${index}`} className="mobility-observability-row mobility-observability-row--compact" role="listitem">
              <div className="mobility-observability-row-summary">
                <div className="mobility-observability-row-country">
                  <strong>{safeString(row.country_name, safeString(row.country, "UNK"))}</strong>
                  <span>{safeString(row.country, "UNK")}</span>
                </div>
                <div className="mobility-observability-row-score">
                  <strong>{asPercent(row.severity_score)}</strong>
                  <span>Severity</span>
                </div>
                <div className="mobility-observability-row-score">
                  <strong>{asAbsolute(row.risk_score)}</strong>
                  <span>Risk Score</span>
                </div>
                <div className="mobility-observability-row-score">
                  <strong>{(safeNumber(row.confidence_score) * 100).toFixed(0)}%</strong>
                  <span>Confidence</span>
                </div>
              </div>
              <div className="mobility-observability-pill-row">
                <div className="mobility-observability-pill"><strong>{asPercent(row.normalized_displaced_pressure)}</strong><span>Displacement</span></div>
                <div className="mobility-observability-pill"><strong>{asPercent(row.aviation_disruption_score)}</strong><span>Aviation</span></div>
                <div className="mobility-observability-pill"><strong>{asPercent(row.logistics_stress_score)}</strong><span>Logistics</span></div>
                <div className="mobility-observability-pill"><strong>{(safeNumber(row.freshness_score) * 100).toFixed(0)}%</strong><span>Freshness</span></div>
                <div className="mobility-observability-pill"><strong>{asAbsolute(row.direct_behavior_score)}</strong><span>Direct</span></div>
                <div className="mobility-observability-pill"><strong>{asAbsolute(row.contextual_pressure_score)}</strong><span>Context</span></div>
              </div>
            </div>
          ))}
          {!chartRows.length ? <div className="watchlist-empty">Mobility severity will populate when displacement, aviation, or logistics snapshots arrive.</div> : null}
        </div>
      </div>
    </article>
  );
}
