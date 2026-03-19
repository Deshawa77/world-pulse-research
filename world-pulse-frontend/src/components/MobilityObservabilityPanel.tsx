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
  const chartRows = useMemo(() => topCountries.slice(0, 5), [topCountries]);
  const combinedCountryCount = safeNumber(mobilitySnapshot?.combined_country_count);
  const overlapRatio = safeNumber(mobilitySnapshot?.crosscheck_overlap_ratio) * 100;
  const status = safeString(mobilitySnapshot?.status, "monitoring");
  const generatedAt = safeString(mobilitySnapshot?.generated_at, "");
  const mixChartRef = useRef<HTMLDivElement | null>(null);
  const mixChartInstanceRef = useRef<echarts.ECharts | null>(null);
  const barChartRef = useRef<HTMLDivElement | null>(null);
  const barChartInstanceRef = useRef<echarts.ECharts | null>(null);

  const mixSeries = useMemo(() => {
    if (!chartRows.length) {
      return [
        { name: "Displacement", value: 0 },
        { name: "Aviation", value: 0 },
        { name: "Logistics", value: 0 },
        { name: "Risk", value: 0 },
      ];
    }
    const avg = (key: string, absolute = false) => {
      const total = chartRows.reduce((sum, row) => sum + (absolute ? toAbsolute(row[key]) : toPercent(row[key])), 0);
      return Math.round((total / chartRows.length) * 10) / 10;
    };
    return [
      { name: "Displacement", value: avg("normalized_displaced_pressure") },
      { name: "Aviation", value: avg("aviation_disruption_score") },
      { name: "Logistics", value: avg("logistics_stress_score") },
      { name: "Risk", value: avg("risk_score", true) },
    ];
  }, [chartRows]);

  useEffect(() => {
    if (!mixChartRef.current) return;
    if (!mixChartInstanceRef.current) {
      mixChartInstanceRef.current = echarts.init(mixChartRef.current);
    }
    const chart = mixChartInstanceRef.current;
    const option: echarts.EChartsOption = {
      animationDuration: 450,
      animationDurationUpdate: 400,
      color: ["#1fd3ee", "#f56565", "#f0a93e", "#8b9bb4"],
      tooltip: {
        trigger: "item",
        formatter: "{b}: {c} / 100 ({d}%)",
        backgroundColor: "rgba(6, 18, 34, 0.96)",
        borderColor: "rgba(34, 211, 238, 0.28)",
        textStyle: { color: "#e2e8f0" },
      },
      legend: {
        bottom: 6,
        left: "center",
        textStyle: { color: "#94a3b8", fontSize: 11 },
        itemWidth: 10,
        itemHeight: 10,
      },
      graphic: [
        {
          type: "text",
          left: "center",
          top: "40%",
          style: {
            text: "Signal Mix",
            fill: "#e2e8f0",
            fontSize: 18,
            fontWeight: 700,
          },
        },
        {
          type: "text",
          left: "center",
          top: "52%",
          style: {
            text: `${combinedCountryCount} live`,
            fill: "#7dd3fc",
            fontSize: 12,
            fontWeight: 600,
          },
        },
      ],
      series: [
        {
          name: "Mobility Signal Mix",
          type: "pie",
          radius: ["56%", "74%"],
          center: ["50%", "46%"],
          avoidLabelOverlap: true,
          itemStyle: {
            borderColor: "#102033",
            borderWidth: 3,
          },
          label: { show: false },
          labelLine: { show: false },
          data: mixSeries,
        },
      ],
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
  }, [mixSeries, combinedCountryCount]);

  useEffect(() => {
    if (!barChartRef.current) return;
    if (!barChartInstanceRef.current) {
      barChartInstanceRef.current = echarts.init(barChartRef.current);
    }
    const chart = barChartInstanceRef.current;
    const labels = chartRows.map((row) => safeString(row.country_name, safeString(row.country, "UNK")));
    const severityValues = chartRows.map((row) => toPercent(row.severity_score));
    const riskValues = chartRows.map((row) => toAbsolute(row.risk_score));
    const option: echarts.EChartsOption = {
      animationDuration: 450,
      animationDurationUpdate: 400,
      color: ["#3b82f6", "#fb7185"],
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "rgba(6, 18, 34, 0.96)",
        borderColor: "rgba(34, 211, 238, 0.28)",
        textStyle: { color: "#e2e8f0" },
      },
      legend: {
        top: 4,
        right: 8,
        textStyle: { color: "#94a3b8", fontSize: 11 },
        itemWidth: 10,
        itemHeight: 10,
        data: ["Severity", "Risk"],
      },
      grid: {
        left: 42,
        right: 16,
        top: 42,
        bottom: 34,
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { color: "#94a3b8", fontSize: 11 },
        axisLine: { lineStyle: { color: "rgba(71, 85, 105, 0.35)" } },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLabel: { color: "#64748b", fontSize: 11 },
        splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.10)" } },
      },
      series: [
        {
          name: "Severity",
          type: "bar",
          barWidth: 22,
          data: severityValues,
          itemStyle: { borderRadius: [6, 6, 0, 0] },
        },
        {
          name: "Risk",
          type: "bar",
          barWidth: 22,
          data: riskValues,
          itemStyle: { borderRadius: [6, 6, 0, 0], opacity: 0.9 },
        },
      ],
    };
    chart.setOption(option, true);
    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(barChartRef.current);
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", handleResize);
    };
  }, [chartRows]);

  useEffect(() => () => {
    mixChartInstanceRef.current?.dispose();
    mixChartInstanceRef.current = null;
    barChartInstanceRef.current?.dispose();
    barChartInstanceRef.current = null;
  }, []);

  return (
    <article className="wp-card panel-frame operational-panel mobility-observability-panel">
      <div className="panel-head analytics-panel-head">
        <h3>Mobility Severity</h3>
        <span className={`analytics-pill ${status !== "healthy" ? "is-warning" : ""}`}>{status}</span>
      </div>
      <div className="panel-content operational-panel-content">
        <div className="operational-panel-intro">
          Live mobility severity shown as a cleaner chart board: a signal-mix donut and a country severity bar chart, both refreshing with the dashboard trust snapshot.
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
          <article className="mobility-observability-chart-card">
            <div className="mobility-observability-chart-title">Mobility Signal Mix</div>
            <div ref={mixChartRef} className="mobility-observability-mini-chart" aria-label="Mobility signal mix chart" />
          </article>
          <article className="mobility-observability-chart-card">
            <div className="mobility-observability-chart-title">Country Severity Impact</div>
            <div ref={barChartRef} className="mobility-observability-mini-chart" aria-label="Mobility severity bar chart" />
          </article>
        </div>
        <div className="mobility-observability-list" role="list" aria-label="Country mobility severity ranking">
          {chartRows.map((row, index) => (
            <div key={`${safeString(row.country, "UNK")}-${index}`} className="mobility-observability-row" role="listitem">
              <div className="mobility-observability-row-head">
                <div>
                  <strong>{safeString(row.country_name, safeString(row.country, "UNK"))}</strong>
                  <span>{safeString(row.country, "UNK")}</span>
                </div>
                <div>
                  <strong>{asPercent(row.severity_score)}</strong>
                  <span>Severity</span>
                </div>
                <div>
                  <strong>{asAbsolute(row.risk_score)}</strong>
                  <span>Risk Score</span>
                </div>
              </div>
              <div className="mobility-observability-row-grid">
                <div><strong>{asPercent(row.normalized_displaced_pressure)}</strong><span>Displacement</span></div>
                <div><strong>{asPercent(row.aviation_disruption_score)}</strong><span>Aviation</span></div>
                <div><strong>{asPercent(row.logistics_stress_score)}</strong><span>Logistics</span></div>
                <div><strong>{(safeNumber(row.freshness_score) * 100).toFixed(0)}%</strong><span>Freshness</span></div>
                <div><strong>{(safeNumber(row.confidence_score) * 100).toFixed(0)}%</strong><span>Confidence</span></div>
                <div><strong>{asAbsolute(row.direct_behavior_score)}</strong><span>Direct</span></div>
                <div><strong>{asAbsolute(row.contextual_pressure_score)}</strong><span>Context</span></div>
                <div><strong>{asPercent(row.household_stress_score)}</strong><span>Household</span></div>
                <div><strong>{asPercent(row.fuel_price_pressure)}</strong><span>Fuel</span></div>
                <div><strong>{asPercent(row.food_price_pressure)}</strong><span>Food</span></div>
                <div><strong>{asPercent(row.labor_stress_score)}</strong><span>Labor</span></div>
                <div><strong>{asPercent(row.fx_pressure_score)}</strong><span>FX</span></div>
                <div><strong>{asPercent(row.remittance_stress_score)}</strong><span>Remittance</span></div>
                <div><strong>{asPercent(row.energy_stress_score)}</strong><span>Energy</span></div>
              </div>
            </div>
          ))}
          {!chartRows.length ? <div className="watchlist-empty">Mobility severity will populate when displacement, aviation, or logistics snapshots arrive.</div> : null}
        </div>
      </div>
    </article>
  );
}
