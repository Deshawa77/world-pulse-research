import { useEffect, useState } from "react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import {
  getAdminSystemMonitoring,
  getTrustReliability,
  type SystemMonitoringResponse,
  type TrustReliabilitySnapshot,
} from "../services/api";
import "./Dashboard.css";
import "./SystemMonitoring.css";
import "../components/futuristic-dashboard.css";

function compactJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

function displayValue(value: unknown): string {
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "-";
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "true" : "false";
  return "-";
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatNumber(value: unknown, digits: number = 2): string {
  const numeric = toNumber(value);
  if (numeric === null) return "-";
  return numeric.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function toPercent(value: unknown, scale: "ratio" | "percent" = "ratio"): number | null {
  const numeric = toNumber(value);
  if (numeric === null) return null;
  const result = scale === "percent" ? numeric : numeric * 100;
  return Math.max(0, Math.min(100, result));
}

function formatTimestamp(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "-";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return String(value);
  return date.toLocaleString();
}

function hoursSince(value: unknown): number | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  const diffMs = Date.now() - date.getTime();
  return diffMs >= 0 ? diffMs / (1000 * 60 * 60) : 0;
}

function toneFromStatus(status: unknown): "good" | "warn" | "bad" | "neutral" {
  const text = String(status || "").toLowerCase();
  if (["ready", "ok", "healthy", "alive", "running", "connected", "true", "up"].includes(text)) return "good";
  if (["degraded", "warning", "stale", "monitoring", "unknown"].includes(text)) return "warn";
  if (["failed", "down", "error", "false", "disconnected"].includes(text)) return "bad";
  return "neutral";
}

function CircleMeter({
  label,
  value,
  subtitle,
  variant = "good",
}: {
  label: string;
  value: number | null;
  subtitle: string;
  variant?: "good" | "warn" | "bad" | "neutral";
}) {
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(100, value ?? 0));
  const dash = (pct / 100) * circumference;
  return (
    <div className={`system-meter system-meter-${variant}`}>
      <span>{label}</span>
      <div className="system-meter-svg-wrap">
        <svg viewBox="0 0 100 100" aria-hidden="true">
          <circle className="system-meter-track" cx="50" cy="50" r={radius} />
          <circle
            className="system-meter-fill"
            cx="50"
            cy="50"
            r={radius}
            strokeDasharray={`${dash} ${circumference - dash}`}
          />
        </svg>
        <strong>{value === null ? "-" : `${pct.toFixed(0)}%`}</strong>
      </div>
      <p>{subtitle}</p>
    </div>
  );
}

export default function SystemMonitoring() {
  const [data, setData] = useState<SystemMonitoringResponse | null>(null);
  const [trust, setTrust] = useState<TrustReliabilitySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadData = async () => {
    setLoading(true);
    setError("");
    try {
      const [response, trustSnapshot] = await Promise.all([
        getAdminSystemMonitoring("online"),
        getTrustReliability("online"),
      ]);
      setData(response);
      setTrust(trustSnapshot);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load system monitoring data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const serverStatus = (data?.server_status ?? {}) as Record<string, unknown>;
  const apiHealth = (data?.api_health ?? {}) as Record<string, unknown>;
  const dataPipeline = (data?.data_pipeline_status ?? {}) as Record<string, unknown>;
  const uptimeStats = (data?.uptime_statistics ?? {}) as Record<string, unknown>;
  const trustFreshness = (trust?.data_freshness ?? {}) as Record<string, unknown>;
  const trustConfidence = (trust?.confidence ?? {}) as Record<string, unknown>;
  const trustValidation = (trust?.validation ?? {}) as Record<string, unknown>;
  const trustSourceHealth = (trust?.source_health ?? {}) as Record<string, unknown>;
  const mobilitySnapshot = ((data?.mobility ?? trust?.mobility) ?? {}) as Record<string, unknown>;
  const mobilitySources = (mobilitySnapshot.sources ?? {}) as Record<string, unknown>;
  const mobilityTrend = (mobilitySnapshot.trend ?? {}) as Record<string, unknown>;
  const mobilityDisplacement = (mobilitySources.displacement ?? {}) as Record<string, unknown>;
  const mobilityAviation = (mobilitySources.aviation ?? {}) as Record<string, unknown>;
  const combinedDaily = Array.isArray(mobilityTrend.combined_daily) ? (mobilityTrend.combined_daily as Array<Record<string, unknown>>) : [];
  const economicSnapshot = ((data?.economic ?? trust?.economic) ?? {}) as Record<string, unknown>;
  const economicAverages = (economicSnapshot.averages ?? {}) as Record<string, unknown>;
  const economicTrend = (economicSnapshot.trend ?? {}) as Record<string, unknown>;
  const economicTopCountries = Array.isArray(economicSnapshot.top_countries) ? (economicSnapshot.top_countries as Array<Record<string, unknown>>) : [];
  const operationalAlerts = Array.isArray(data?.alerts) ? data.alerts : Array.isArray(trust?.alerts) ? trust.alerts : [];
  const sourceHealthRows = Array.isArray(trustSourceHealth.sources) ? (trustSourceHealth.sources as Array<Record<string, unknown>>) : [];
  const economicHealthRows = sourceHealthRows.filter((row) => {
    const source = String(row.source ?? "");
    return source.startsWith("worldbank_behavior_") || source === "fred_behavior" || source === "eia_behavior" || source === "frankfurter_behavior";
  });

  const readyHealth = (apiHealth.ready ?? {}) as Record<string, unknown>;

  const serverStatusTone = toneFromStatus(serverStatus.status);
  const apiLiveTone = toneFromStatus((apiHealth.live as Record<string, unknown>)?.status);
  const apiReadyTone = toneFromStatus(readyHealth.status);
  const dbTone = toneFromStatus(readyHealth.database);
  const modelTone = toneFromStatus(readyHealth.model_loaded);

  const dependencyRows = Object.entries((dataPipeline.dependencies ?? {}) as Record<string, unknown>)
    .map(([name, value]) => ({
      name: name.replace(/_/g, " "),
      status: String(value ?? "-"),
      tone: toneFromStatus(value),
    }))
    .slice(0, 8);

  const uptimeSeconds = toNumber(uptimeStats.uptime_seconds) ?? 0;
  const totalRequests = toNumber(uptimeStats.total_requests) ?? 0;
  const totalErrors = toNumber(uptimeStats.total_errors) ?? 0;
  const requestsPerMin = toNumber(uptimeStats.requests_per_minute) ?? 0;
  const predictions = toNumber(uptimeStats.total_predictions) ?? 0;
  const errorRatePct = toPercent(uptimeStats.error_rate, "ratio") ?? 0;

  const throughputBars = [
    { label: "Requests", value: totalRequests },
    { label: "Predictions", value: predictions },
    { label: "Req / min", value: requestsPerMin },
    { label: "Errors", value: totalErrors },
  ];
  const throughputMax = Math.max(1, ...throughputBars.map((row) => row.value));

  const latestIngestion = (dataPipeline.latest_ingestion ?? {}) as Record<string, unknown>;
  const ingestionRows = Object.entries(latestIngestion).map(([source, timestamp]) => {
    const ageHours = hoursSince(timestamp);
    const tone = ageHours === null ? "bad" : ageHours <= 24 ? "good" : ageHours <= 72 ? "warn" : "bad";
    return {
      source: source.replace(/_/g, " "),
      timestamp,
      ageHours,
      tone: tone as "good" | "warn" | "bad",
    };
  });
  const knownIngestionRows = ingestionRows.filter((row) => row.ageHours !== null);
  const ingestionFreshCount = knownIngestionRows.filter((row) => (row.ageHours ?? 9999) <= 24).length;
  const ingestionFreshPct = knownIngestionRows.length ? (ingestionFreshCount / knownIngestionRows.length) * 100 : null;

  const trustFreshCount = toNumber(trustFreshness.fresh_count) ?? 0;
  const trustStaleCount = toNumber(trustFreshness.stale_count) ?? 0;
  const trustKnownCount = trustFreshCount + trustStaleCount;
  const trustFreshPct = trustKnownCount ? (trustFreshCount / trustKnownCount) * 100 : null;
  const trustOverallTone = toneFromStatus(trustFreshness.overall_status);

  const countryBacktest = (trustValidation.country_backtest ?? {}) as Record<string, unknown>;
  const globalBacktest = (trustValidation.global_backtest ?? {}) as Record<string, unknown>;
  const trustBars = [
    {
      label: "Freshness",
      value: trustFreshPct ?? 0,
      tone: trustFreshPct !== null && trustFreshPct >= 60 ? "good" : trustFreshPct !== null && trustFreshPct >= 35 ? "warn" : "bad",
    },
    {
      label: "Country quality",
      value: Math.max(0, 100 - ((toNumber(countryBacktest.weighted_brier_score) ?? 0) * 100)),
      tone: "good",
    },
    {
      label: "Global quality",
      value: Math.max(0, 100 - ((toNumber(globalBacktest.weighted_mae) ?? 0) * 100)),
      tone: "warn",
    },
  ] as Array<{ label: string; value: number; tone: "good" | "warn" | "bad" }>;

  const displacementCoverage = toNumber(mobilityDisplacement.country_count) ?? 0;
  const aviationCoverage = toNumber(mobilityAviation.country_count) ?? 0;
  const overlapRatioPct = toPercent(mobilitySnapshot.crosscheck_overlap_ratio, "ratio") ?? 0;
  const mobilityCoverageBars = [
    { label: "Displacement", value: displacementCoverage, tone: "good" as const },
    { label: "Aviation", value: aviationCoverage, tone: "warn" as const },
  ];
  const mobilityCoverageMax = Math.max(1, ...mobilityCoverageBars.map((row) => row.value));

  const trendPoints = combinedDaily
    .map((row) => ({
      period: String(row.period ?? row.date ?? ""),
      value: toNumber(row.country_count) ?? 0,
    }))
    .filter((row) => row.period)
    .slice(-8);
  const trendMax = Math.max(1, ...trendPoints.map((row) => row.value), 1);
  const trendMin = Math.min(...trendPoints.map((row) => row.value), 0);
  const trendSpan = Math.max(1, trendMax - trendMin);
  const chartWidth = 320;
  const chartHeight = 92;
  const trendPolyline = trendPoints
    .map((point, index) => {
      const x = trendPoints.length <= 1 ? chartWidth / 2 : (index / (trendPoints.length - 1)) * chartWidth;
      const y = chartHeight - ((point.value - trendMin) / trendSpan) * chartHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const economicHealthChartRows = economicHealthRows
    .map((row) => {
      const status = String(row.status ?? "unknown");
      const records = toNumber(row.records) ?? 0;
      return {
        label: String(row.source_label ?? row.source ?? "source"),
        status,
        records,
        tone: toneFromStatus(status),
      };
    })
    .slice(0, 10);
  const economicHealthMax = Math.max(1, ...economicHealthChartRows.map((row) => row.records), 1);

  const alertSeverityRows = operationalAlerts.reduce<Record<string, number>>((acc, row) => {
    const key = String(row.severity ?? "unknown").toLowerCase();
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  const alertSeverityChart = Object.entries(alertSeverityRows).map(([severity, count]) => ({
    severity,
    count,
    tone: severity === "high" || severity === "critical" ? "bad" : severity === "medium" ? "warn" : severity === "low" ? "good" : "neutral",
  })) as Array<{ severity: string; count: number; tone: "good" | "warn" | "bad" | "neutral" }>;
  const alertSeverityTotal = alertSeverityChart.reduce((sum, row) => sum + row.count, 0);

  const economicStressRows = [
    { label: "Household", value: toPercent(economicAverages.household_stress_score, "ratio") ?? 0, tone: "warn" as const },
    { label: "Fuel", value: toPercent(economicAverages.fuel_price_pressure, "ratio") ?? 0, tone: "bad" as const },
    { label: "Food", value: toPercent(economicAverages.food_price_pressure, "ratio") ?? 0, tone: "warn" as const },
    { label: "Labor", value: toPercent(economicAverages.labor_stress_score, "ratio") ?? 0, tone: "good" as const },
  ];

  const operationalTimeline = operationalAlerts.slice(0, 8).map((alert, index) => {
    const severity = String(alert.severity ?? "unknown").toLowerCase();
    return {
      key: `${String(alert.source ?? "alert")}-${index}`,
      severity,
      tone: severity === "high" || severity === "critical" ? "bad" : severity === "medium" ? "warn" : severity === "low" ? "good" : "neutral",
      source: String(alert.source_label ?? alert.source ?? "source"),
      message: String(alert.message ?? ""),
      category: String(alert.category ?? ""),
    };
  });

  const globalMoodConfidencePct = toPercent(trustConfidence.global_mood_confidence, "ratio") ?? 0;
  const forecastConfidencePct = toPercent(trustConfidence.forecast_confidence, "ratio") ?? 0;
  const globalMoodUncertaintyPct = toPercent(trustConfidence.global_mood_uncertainty, "ratio")
    ?? toPercent(trustConfidence.global_mood_uncertainty, "percent")
    ?? 0;
  const confidenceQualityBars = [
    { label: "Confidence strength", value: globalMoodConfidencePct, tone: "good" as const },
    { label: "Forecast confidence", value: forecastConfidencePct, tone: "warn" as const },
    { label: "Uncertainty pressure", value: Math.max(0, 100 - globalMoodUncertaintyPct), tone: "bad" as const },
  ];

  const payloadSummaryChips = [
    { label: "Server", value: displayValue(serverStatus.status) },
    { label: "API ready", value: displayValue(readyHealth.status) },
    { label: "Pipeline", value: displayValue(dataPipeline.status) },
    { label: "Alerts", value: formatNumber(operationalAlerts.length, 0) },
    { label: "Country coverage", value: displayValue(economicSnapshot.country_count) },
    { label: "Uptime", value: displayValue(uptimeStats.uptime_human) },
  ];

  return (
    <main className="wp-shell proposal-runtime-shell">
      <ConsoleNavigation
        title={<>SYSTEM <span>MONITORING</span></>}
        subtitle="Admin-only operational visibility for server health, API readiness, pipeline flow, and uptime stats."
      />

      {error ? <div className="proposal-auth-error">{error}</div> : null}

      <section className="proposal-runtime-intro">
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">Server status</span>
          <div className={`system-status-hero system-tone-${serverStatusTone}`}>
            <h2>{displayValue(serverStatus.status)}</h2>
            <span className="system-status-dot" />
          </div>
          <div className="system-kpi-grid">
            <div className="system-kpi-card">
              <span>Process ID</span>
              <strong>{displayValue(serverStatus.process_id)}</strong>
            </div>
            <div className="system-kpi-card">
              <span>Hostname</span>
              <strong>{displayValue(serverStatus.hostname)}</strong>
            </div>
            <div className="system-kpi-card">
              <span>Started</span>
              <strong>{formatTimestamp(serverStatus.started_at)}</strong>
            </div>
            <div className="system-kpi-card">
              <span>Python</span>
              <strong>{displayValue(serverStatus.python_version)}</strong>
            </div>
          </div>
        </article>
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">API health</span>
          <div className="system-health-grid">
            <div className={`system-health-tile system-tone-${apiLiveTone}`}>
              <span>Live</span>
              <strong>{displayValue((apiHealth.live as Record<string, unknown>)?.status)}</strong>
            </div>
            <div className={`system-health-tile system-tone-${apiReadyTone}`}>
              <span>Ready</span>
              <strong>{displayValue(readyHealth.status)}</strong>
            </div>
            <div className={`system-health-tile system-tone-${dbTone}`}>
              <span>Database</span>
              <strong>{displayValue(readyHealth.database)}</strong>
            </div>
            <div className={`system-health-tile system-tone-${modelTone}`}>
              <span>Model loaded</span>
              <strong>{displayValue(readyHealth.model_loaded)}</strong>
            </div>
          </div>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Data pipeline status</span>
          {loading ? <p>Loading pipeline status...</p> : null}
          {!loading ? (
            <>
              <div className={`system-status-hero system-tone-${toneFromStatus(dataPipeline.status)}`}>
                <h2>{displayValue(dataPipeline.status)}</h2>
                <span className="system-status-dot" />
              </div>
              <div className="system-dep-grid">
                {dependencyRows.length ? (
                  dependencyRows.map((row) => (
                    <div key={row.name} className="system-dep-row">
                      <span>{row.name}</span>
                      <div className="system-dep-track">
                        <div
                          className={`system-dep-fill system-tone-${row.tone}`}
                          style={{ width: `${row.tone === "good" ? 100 : row.tone === "warn" ? 58 : row.tone === "bad" ? 24 : 40}%` }}
                        />
                      </div>
                      <strong>{row.status}</strong>
                    </div>
                  ))
                ) : (
                  <p>No dependency snapshot available.</p>
                )}
              </div>
              <details className="system-raw">
                <summary>Show pipeline raw payload</summary>
                <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(dataPipeline.dependencies)}</pre>
              </details>
            </>
          ) : null}
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Uptime statistics</span>
          {loading ? <p>Loading uptime metrics...</p> : null}
          {!loading ? (
            <>
              <div className="system-uptime-top">
                <CircleMeter
                  label="Error rate"
                  value={errorRatePct}
                  subtitle={`${formatNumber(totalErrors, 0)} errors`}
                  variant={errorRatePct > 6 ? "bad" : errorRatePct > 2 ? "warn" : "good"}
                />
                <div className="system-uptime-kpis">
                  <div className="system-kpi-card">
                    <span>Uptime</span>
                    <strong>{displayValue(uptimeStats.uptime_human)}</strong>
                  </div>
                  <div className="system-kpi-card">
                    <span>Total requests</span>
                    <strong>{formatNumber(totalRequests, 0)}</strong>
                  </div>
                  <div className="system-kpi-card">
                    <span>Req / min</span>
                    <strong>{formatNumber(requestsPerMin, 3)}</strong>
                  </div>
                  <div className="system-kpi-card">
                    <span>Predictions</span>
                    <strong>{formatNumber(predictions, 0)}</strong>
                  </div>
                </div>
              </div>
              <div className="system-dep-grid">
                {throughputBars.map((row) => {
                  const width = (row.value / throughputMax) * 100;
                  return (
                    <div key={row.label} className="system-dep-row">
                      <span>{row.label}</span>
                      <div className="system-dep-track">
                        <div className="system-dep-fill system-tone-good" style={{ width: `${width}%` }} />
                      </div>
                      <strong>{formatNumber(row.value, 2)}</strong>
                    </div>
                  );
                })}
              </div>
              <p className="system-uptime-footnote">Runtime seconds: <strong>{formatNumber(uptimeSeconds, 0)}</strong></p>
            </>
          ) : null}
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Latest ingestion timestamps</span>
          <div className="system-ingestion-top">
            <CircleMeter
              label="Fresh in 24h"
              value={ingestionFreshPct}
              subtitle={`${ingestionFreshCount}/${knownIngestionRows.length || 0} sources`}
              variant={ingestionFreshPct !== null && ingestionFreshPct >= 60 ? "good" : ingestionFreshPct !== null && ingestionFreshPct >= 35 ? "warn" : "bad"}
            />
            <div className="system-ingestion-grid">
              {ingestionRows.length ? (
                ingestionRows.map((row) => (
                  <div key={row.source} className="system-ingestion-row">
                    <span>{row.source}</span>
                    <div className="system-dep-track">
                      <div
                        className={`system-dep-fill system-tone-${row.tone}`}
                        style={{
                          width: `${row.ageHours === null ? 100 : Math.max(8, Math.min(100, 100 - (row.ageHours / 168) * 100))}%`,
                        }}
                      />
                    </div>
                    <strong>{row.ageHours === null ? "missing" : `${formatNumber(row.ageHours, 1)}h ago`}</strong>
                  </div>
                ))
              ) : (
                <p>No ingestion timestamps available.</p>
              )}
            </div>
          </div>
          <details className="system-raw">
            <summary>Show timestamp raw payload</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>
              {compactJson((dataPipeline.latest_ingestion ?? {}) as Record<string, unknown>)}
            </pre>
          </details>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Trust reliability snapshot</span>
          <div className="system-trust-top">
            <CircleMeter
              label="Freshness ratio"
              value={trustFreshPct}
              subtitle={`Fresh ${formatNumber(trustFreshCount, 0)} | Stale ${formatNumber(trustStaleCount, 0)}`}
              variant={trustFreshPct !== null && trustFreshPct >= 60 ? "good" : trustFreshPct !== null && trustFreshPct >= 35 ? "warn" : "bad"}
            />
            <div className="system-trust-kpis">
              <div className={`system-health-tile system-tone-${trustOverallTone}`}>
                <span>Overall freshness</span>
                <strong>{displayValue(trustFreshness.overall_status)}</strong>
              </div>
              <div className="system-health-tile">
                <span>Country backtest Brier</span>
                <strong>{formatNumber(countryBacktest.weighted_brier_score, 4)}</strong>
              </div>
              <div className="system-health-tile">
                <span>Global backtest MAE</span>
                <strong>{formatNumber(globalBacktest.weighted_mae, 4)}</strong>
              </div>
            </div>
          </div>
          <div className="system-dep-grid">
            {trustBars.map((bar) => (
              <div key={bar.label} className="system-dep-row">
                <span>{bar.label}</span>
                <div className="system-dep-track">
                  <div className={`system-dep-fill system-tone-${bar.tone}`} style={{ width: `${Math.max(6, Math.min(100, bar.value))}%` }} />
                </div>
                <strong>{formatNumber(bar.value, 1)}%</strong>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Mobility trust</span>
          <div className={`system-status-hero system-tone-${toneFromStatus(mobilitySnapshot.status)}`}>
            <h2>{displayValue(mobilitySnapshot.status)}</h2>
            <span className="system-status-dot" />
          </div>
          <div className="system-mobility-meters">
            <CircleMeter
              label="Overlap ratio"
              value={overlapRatioPct}
              subtitle={formatNumber(mobilitySnapshot.crosscheck_overlap_ratio, 3)}
              variant={overlapRatioPct >= 50 ? "good" : overlapRatioPct >= 20 ? "warn" : "bad"}
            />
            <div className="system-mobility-bars">
              {mobilityCoverageBars.map((row) => {
                const width = (row.value / mobilityCoverageMax) * 100;
                return (
                  <div key={row.label} className="system-dep-row">
                    <span>{row.label} coverage</span>
                    <div className="system-dep-track">
                      <div className={`system-dep-fill system-tone-${row.tone}`} style={{ width: `${Math.max(6, width)}%` }} />
                    </div>
                    <strong>{formatNumber(row.value, 0)}</strong>
                  </div>
                );
              })}
            </div>
          </div>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Mobility coverage trend</span>
          <div className="system-trend-kpis">
            <div className={`system-kpi-card system-tone-${toNumber(mobilityTrend.combined_delta) === null ? "neutral" : (toNumber(mobilityTrend.combined_delta) ?? 0) < 0 ? "bad" : "good"}`}>
              <span>Combined delta</span>
              <strong>{displayValue(mobilityTrend.combined_delta)}</strong>
            </div>
            <div className={`system-kpi-card system-tone-${(toNumber(mobilityTrend.displacement_delta) ?? 0) < 0 ? "bad" : "good"}`}>
              <span>Displacement delta</span>
              <strong>{displayValue(mobilityTrend.displacement_delta)}</strong>
            </div>
            <div className={`system-kpi-card system-tone-${(toNumber(mobilityTrend.aviation_delta) ?? 0) < 0 ? "bad" : "good"}`}>
              <span>Aviation delta</span>
              <strong>{displayValue(mobilityTrend.aviation_delta)}</strong>
            </div>
          </div>
          <div className="system-line-chart-wrap">
            {trendPoints.length >= 2 ? (
              <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} preserveAspectRatio="none">
                <polyline className="system-line-chart-line" points={trendPolyline} />
                {trendPoints.map((point, index) => {
                  const x = trendPoints.length <= 1 ? chartWidth / 2 : (index / (trendPoints.length - 1)) * chartWidth;
                  const y = chartHeight - ((point.value - trendMin) / trendSpan) * chartHeight;
                  return <circle key={`${point.period}-${index}`} cx={x} cy={y} r="2.8" className="system-line-chart-dot" />;
                })}
              </svg>
            ) : (
              <p>Not enough trend points yet.</p>
            )}
          </div>
          {trendPoints.length ? (
            <div className="system-line-labels">
              {trendPoints.map((point) => (
                <span key={point.period}>{point.period}</span>
              ))}
            </div>
          ) : null}
          <details className="system-raw">
            <summary>Show trend raw payload</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(combinedDaily.slice(-8))}</pre>
          </details>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Economic source health</span>
          {economicHealthChartRows.length ? (
            <div className="system-econ-health-grid">
              {economicHealthChartRows.map((row) => (
                <div key={row.label} className="system-econ-health-row">
                  <span>{row.label}</span>
                  <div className="system-dep-track">
                    <div
                      className={`system-dep-fill system-tone-${row.tone}`}
                      style={{ width: `${Math.max(8, (row.records / economicHealthMax) * 100)}%` }}
                    />
                  </div>
                  <strong>{row.status} ({formatNumber(row.records, 0)})</strong>
                </div>
              ))}
            </div>
          ) : (
            <p>No economic source-health rows available yet.</p>
          )}
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Alert summary</span>
          {operationalAlerts.length ? (
            <>
              <div className="system-alert-distribution">
                {alertSeverityChart.map((row) => {
                  const pct = alertSeverityTotal ? (row.count / alertSeverityTotal) * 100 : 0;
                  return (
                    <div key={row.severity} className="system-alert-distribution-row">
                      <span>{row.severity}</span>
                      <div className="system-dep-track">
                        <div className={`system-dep-fill system-tone-${row.tone}`} style={{ width: `${Math.max(8, pct)}%` }} />
                      </div>
                      <strong>{row.count}</strong>
                    </div>
                  );
                })}
              </div>
              <div className="system-alert-chip-grid">
                {operationalAlerts.slice(0, 6).map((alert, index) => (
                  <div key={`${String(alert.source ?? "alert")}-${index}`} className={`system-alert-chip system-tone-${toneFromStatus(alert.severity)}`}>
                    <b>{displayValue(alert.severity)}:</b> {displayValue(alert.source_label ?? alert.source)}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p>No active mobility or economic alerts.</p>
          )}
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Economic observability</span>
          <div className={`system-status-hero system-tone-${toneFromStatus(economicSnapshot.status)}`}>
            <h2>{displayValue(economicSnapshot.status)}</h2>
            <span className="system-status-dot" />
          </div>
          <div className="system-trend-kpis">
            <div className="system-kpi-card">
              <span>Country coverage</span>
              <strong>{displayValue(economicSnapshot.country_count)}</strong>
            </div>
            <div className={`system-kpi-card system-tone-${(toNumber(economicTrend.coverage_delta) ?? 0) < 0 ? "bad" : "good"}`}>
              <span>Coverage delta</span>
              <strong>{displayValue(economicTrend.coverage_delta)}</strong>
            </div>
          </div>
          <div className="system-econ-stress-grid">
            {economicStressRows.map((row) => (
              <CircleMeter
                key={row.label}
                label={row.label}
                value={row.value}
                subtitle={`${formatNumber(row.value, 1)}%`}
                variant={row.tone}
              />
            ))}
          </div>
          <details className="system-raw">
            <summary>Show top country raw payload</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(economicTopCountries.slice(0, 5))}</pre>
          </details>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Operational alerts</span>
          {operationalTimeline.length ? (
            <div className="system-operational-timeline">
              {operationalTimeline.map((row, index) => (
                <div key={row.key} className="system-operational-item">
                  <span className={`system-operational-dot system-tone-${row.tone}`} />
                  <div className="system-operational-content">
                    <p>
                      <b>{index + 1}. {row.source}</b> ({row.severity})
                    </p>
                    <small>{row.category || "general"}: {row.message || "-"}</small>
                  </div>
                </div>
              ))}
              <details className="system-raw">
                <summary>Show full operational payload</summary>
                <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(operationalAlerts)}</pre>
              </details>
            </div>
          ) : (
            <p>No active mobility or economic alerts.</p>
          )}
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Confidence + uncertainty</span>
          <div className="system-confidence-meters">
            <CircleMeter
              label="Global confidence"
              value={globalMoodConfidencePct}
              subtitle={formatNumber(trustConfidence.global_mood_confidence, 4)}
              variant={globalMoodConfidencePct >= 60 ? "good" : globalMoodConfidencePct >= 35 ? "warn" : "bad"}
            />
            <CircleMeter
              label="Uncertainty"
              value={globalMoodUncertaintyPct}
              subtitle={formatNumber(trustConfidence.global_mood_uncertainty, 4)}
              variant={globalMoodUncertaintyPct <= 30 ? "good" : globalMoodUncertaintyPct <= 55 ? "warn" : "bad"}
            />
            <CircleMeter
              label="Forecast confidence"
              value={forecastConfidencePct}
              subtitle={formatNumber(trustConfidence.forecast_confidence, 4)}
              variant={forecastConfidencePct >= 60 ? "good" : forecastConfidencePct >= 35 ? "warn" : "bad"}
            />
          </div>
          <div className="system-dep-grid">
            {confidenceQualityBars.map((bar) => (
              <div key={bar.label} className="system-dep-row">
                <span>{bar.label}</span>
                <div className="system-dep-track">
                  <div className={`system-dep-fill system-tone-${bar.tone}`} style={{ width: `${Math.max(6, bar.value)}%` }} />
                </div>
                <strong>{formatNumber(bar.value, 1)}%</strong>
              </div>
            ))}
          </div>
          <details className="system-raw">
            <summary>Show confidence validation payload</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(trustValidation)}</pre>
          </details>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Raw monitoring payload</span>
          <div className="system-payload-chips">
            {payloadSummaryChips.map((chip) => (
              <div key={chip.label} className="system-payload-chip">
                <span>{chip.label}</span>
                <strong>{chip.value}</strong>
              </div>
            ))}
          </div>
          <details className="system-raw" open>
            <summary>Show full payload JSON</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(data)}</pre>
          </details>
          <div className="proposal-form-actions">
            <button className="proposal-button proposal-button-primary" onClick={loadData} disabled={loading}>
              {loading ? "Refreshing..." : "Refresh monitoring"}
            </button>
          </div>
        </article>
      </section>
    </main>
  );
}
