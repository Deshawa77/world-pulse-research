import { useEffect, useState } from "react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import {
  getAdminSystemMonitoring,
  getTrustReliability,
  type SystemMonitoringResponse,
  type TrustReliabilitySnapshot,
} from "../services/api";
import "./Dashboard.css";
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
          <h2>{displayValue(serverStatus.status)}</h2>
          <p>Process ID: <strong>{displayValue(serverStatus.process_id)}</strong></p>
          <p>Host: <strong>{displayValue(serverStatus.hostname)}</strong></p>
          <p>Started: <strong>{displayValue(serverStatus.started_at)}</strong></p>
        </article>
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">API health</span>
          <p>Live: <strong>{displayValue((apiHealth.live as Record<string, unknown>)?.status)}</strong></p>
          <p>Ready: <strong>{displayValue(readyHealth.status)}</strong></p>
          <p>Database: <strong>{displayValue(readyHealth.database)}</strong></p>
          <p>Model loaded: <strong>{displayValue(readyHealth.model_loaded)}</strong></p>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Data pipeline status</span>
          {loading ? <p>Loading pipeline status...</p> : null}
          {!loading ? (
            <>
              <p>Pipeline status: <strong>{displayValue(dataPipeline.status)}</strong></p>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(dataPipeline.dependencies)}</pre>
            </>
          ) : null}
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Uptime statistics</span>
          {loading ? <p>Loading uptime metrics...</p> : null}
          {!loading ? (
            <>
              <p>Uptime: <strong>{displayValue(uptimeStats.uptime_human)}</strong></p>
              <p>Total requests: <strong>{displayValue(uptimeStats.total_requests)}</strong></p>
              <p>Error rate: <strong>{displayValue(uptimeStats.error_rate)}</strong></p>
              <p>Requests / min: <strong>{displayValue(uptimeStats.requests_per_minute)}</strong></p>
            </>
          ) : null}
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Latest ingestion timestamps</span>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>
            {compactJson((dataPipeline.latest_ingestion ?? {}) as Record<string, unknown>)}
          </pre>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Trust reliability snapshot</span>
          <p>Fresh sources: <strong>{displayValue(trustFreshness.fresh_count)}</strong></p>
          <p>Stale sources: <strong>{displayValue(trustFreshness.stale_count)}</strong></p>
          <p>Overall freshness: <strong>{displayValue(trustFreshness.overall_status)}</strong></p>
          <p>Country backtest Brier: <strong>{displayValue((trustValidation.country_backtest as Record<string, unknown> | undefined)?.weighted_brier_score)}</strong></p>
          <p>Global mood backtest MAE: <strong>{displayValue((trustValidation.global_backtest as Record<string, unknown> | undefined)?.weighted_mae)}</strong></p>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Mobility trust</span>
          <p>Status: <strong>{displayValue(mobilitySnapshot.status)}</strong></p>
          <p>Displacement coverage: <strong>{displayValue(mobilityDisplacement.country_count)}</strong></p>
          <p>Aviation coverage: <strong>{displayValue(mobilityAviation.country_count)}</strong></p>
          <p>Overlap ratio: <strong>{displayValue(mobilitySnapshot.crosscheck_overlap_ratio)}</strong></p>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Mobility coverage trend</span>
          <p>Combined delta: <strong>{displayValue(mobilityTrend.combined_delta)}</strong></p>
          <p>Displacement delta: <strong>{displayValue(mobilityTrend.displacement_delta)}</strong></p>
          <p>Aviation delta: <strong>{displayValue(mobilityTrend.aviation_delta)}</strong></p>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(combinedDaily.slice(-5))}</pre>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Economic source health</span>
          {economicHealthRows.length ? (
            <div>
              {economicHealthRows.map((row) => (
                <p key={String(row.source ?? row.source_label ?? Math.random())}>
                  {displayValue(row.source_label ?? row.source)}: <strong>{displayValue(row.status)}</strong>
                  {row.records !== undefined ? ` (${displayValue(row.records)} rows)` : ""}
                </p>
              ))}
            </div>
          ) : (
            <p>No economic source-health rows available yet.</p>
          )}
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Alert summary</span>
          {operationalAlerts.length ? (
            <div>
              {operationalAlerts.slice(0, 6).map((alert, index) => (
                <p key={`${String(alert.source ?? 'alert')}-${index}`}>
                  {displayValue(alert.severity)}: <strong>{displayValue(alert.source_label ?? alert.source)}</strong> - {displayValue(alert.message)}
                </p>
              ))}
            </div>
          ) : (
            <p>No active mobility or economic alerts.</p>
          )}
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Economic observability</span>
          <p>Status: <strong>{displayValue(economicSnapshot.status)}</strong></p>
          <p>Country coverage: <strong>{displayValue(economicSnapshot.country_count)}</strong></p>
          <p>Coverage delta: <strong>{displayValue(economicTrend.coverage_delta)}</strong></p>
          <p>Household avg: <strong>{displayValue(economicAverages.household_stress_score)}</strong></p>
          <p>Fuel avg: <strong>{displayValue(economicAverages.fuel_price_pressure)}</strong></p>
          <p>Food avg: <strong>{displayValue(economicAverages.food_price_pressure)}</strong></p>
          <p>Labor avg: <strong>{displayValue(economicAverages.labor_stress_score)}</strong></p>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(economicTopCountries.slice(0, 5))}</pre>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Operational alerts</span>
          {operationalAlerts.length ? (
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(operationalAlerts)}</pre>
          ) : (
            <p>No active mobility or economic alerts.</p>
          )}
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Confidence + uncertainty</span>
          <p>Global mood confidence: <strong>{displayValue(trustConfidence.global_mood_confidence)}</strong></p>
          <p>Global mood uncertainty: <strong>{displayValue(trustConfidence.global_mood_uncertainty)}</strong></p>
          <p>Forecast confidence: <strong>{displayValue(trustConfidence.forecast_confidence)}</strong></p>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(trustValidation)}</pre>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Raw monitoring payload</span>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(data)}</pre>
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
