import { useEffect, useState } from "react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import {
  getAdminSecurityLogs,
  type SecurityLogEvent,
  type SecurityLogsResponse,
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

function toDisplayTimestamp(value?: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return date.toLocaleString();
}

function metricValue(container: Record<string, unknown>, key: string): string {
  const value = container[key];
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "true" : "false";
  return "0";
}

export default function SecurityLogs() {
  const [data, setData] = useState<SecurityLogsResponse | null>(null);
  const [events, setEvents] = useState<SecurityLogEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [limit, setLimit] = useState(100);
  const [minutes, setMinutes] = useState(1440);

  const loadData = async (nextLimit: number = limit, nextMinutes: number = minutes) => {
    setLoading(true);
    setError("");

    try {
      const response = await getAdminSecurityLogs(nextLimit, nextMinutes);
      setData(response);
      setEvents(response.events || []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load security logs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const loginAttempts = (data?.login_attempts ?? {}) as Record<string, unknown>;
  const suspicious = (data?.suspicious_activity ?? {}) as Record<string, unknown>;
  const jwtMonitoring = (data?.jwt_token_monitoring ?? {}) as Record<string, unknown>;

  return (
    <main className="wp-shell proposal-runtime-shell">
      <ConsoleNavigation
        title={<>SECURITY <span>LOGS</span></>}
        subtitle="Admin-only login attempt tracking, suspicious activity visibility, and JWT monitoring."
      />

      {error ? <div className="proposal-auth-error">{error}</div> : null}

      <section className="proposal-runtime-intro">
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">Login attempts</span>
          <h2>{metricValue(loginAttempts, "total")}</h2>
          <p>Success: <strong>{metricValue(loginAttempts, "success")}</strong></p>
          <p>Failed: <strong>{metricValue(loginAttempts, "failed")}</strong></p>
          <p>Blocked: <strong>{metricValue(loginAttempts, "blocked")}</strong></p>
        </article>
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">Suspicious activity</span>
          <h2>{metricValue(suspicious, "total")}</h2>
          <p>Window (minutes): <strong>{String(data?.window_minutes ?? "-")}</strong></p>
          <p>Generated at: <strong>{toDisplayTimestamp(data?.generated_at)}</strong></p>
        </article>
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">JWT token monitoring</span>
          <p>Issued: <strong>{metricValue(jwtMonitoring, "jwt_issued")}</strong></p>
          <p>Validated success: <strong>{metricValue(jwtMonitoring, "jwt_validated_success")}</strong></p>
          <p>Validated failed: <strong>{metricValue(jwtMonitoring, "jwt_validated_failed")}</strong></p>
          <p>Recent failed validations: <strong>{metricValue(jwtMonitoring, "recent_failed_validations")}</strong></p>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Filters</span>
          <div className="proposal-field-grid">
            <label>
              Time window
              <select
                value={minutes}
                onChange={(event) => setMinutes(Number(event.target.value))}
                disabled={loading}
              >
                <option value={60}>Last 1 hour</option>
                <option value={360}>Last 6 hours</option>
                <option value={1440}>Last 24 hours</option>
                <option value={10080}>Last 7 days</option>
              </select>
            </label>
            <label>
              Max rows
              <select
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value))}
                disabled={loading}
              >
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={250}>250</option>
                <option value={500}>500</option>
              </select>
            </label>
          </div>
          <div className="proposal-form-actions">
            <button
              className="proposal-button proposal-button-primary"
              onClick={() => loadData(limit, minutes)}
              disabled={loading}
            >
              {loading ? "Refreshing..." : "Apply filters"}
            </button>
          </div>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">JWT monitoring snapshot</span>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(jwtMonitoring)}</pre>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel" style={{ overflowX: "auto" }}>
          <span className="proposal-eyebrow">Recent security events</span>
          {loading ? <p>Loading security events...</p> : null}
          {!loading ? (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "8px" }}>Timestamp</th>
                  <th style={{ textAlign: "left", padding: "8px" }}>Type</th>
                  <th style={{ textAlign: "left", padding: "8px" }}>Status</th>
                  <th style={{ textAlign: "left", padding: "8px" }}>Email</th>
                  <th style={{ textAlign: "left", padding: "8px" }}>IP</th>
                  <th style={{ textAlign: "left", padding: "8px" }}>Detail</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event, index) => (
                  <tr key={event._id || `${event.timestamp}-${index}`}>
                    <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                      {toDisplayTimestamp(event.timestamp)}
                    </td>
                    <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                      {event.event_type || "-"}
                    </td>
                    <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                      {event.status || "-"}
                    </td>
                    <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                      {event.email || "-"}
                    </td>
                    <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                      {event.client_ip || "-"}
                    </td>
                    <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                      {event.detail || "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </article>
      </section>
    </main>
  );
}