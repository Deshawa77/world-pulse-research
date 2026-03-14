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
