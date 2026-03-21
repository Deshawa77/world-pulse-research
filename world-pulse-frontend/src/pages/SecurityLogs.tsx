import { useEffect, useState } from "react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import {
  getAdminSecurityLogs,
  type SecurityLogEvent,
  type SecurityLogsResponse,
} from "../services/api";
import "./Dashboard.css";
import "./SecurityLogs.css";
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

function toNumber(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function CircleStat({
  label,
  value,
  detail,
  tone = "good",
}: {
  label: string;
  value: number;
  detail: string;
  tone?: "good" | "warn" | "bad";
}) {
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(100, value));
  const dash = (pct / 100) * circumference;
  return (
    <div className={`security-circle security-circle-${tone}`}>
      <span>{label}</span>
      <div className="security-circle-svg-wrap">
        <svg viewBox="0 0 100 100" aria-hidden="true">
          <circle className="security-circle-track" cx="50" cy="50" r={radius} />
          <circle className="security-circle-fill" cx="50" cy="50" r={radius} strokeDasharray={`${dash} ${circumference - dash}`} />
        </svg>
        <strong>{pct.toFixed(0)}%</strong>
      </div>
      <p>{detail}</p>
    </div>
  );
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

  const loginTotal = toNumber(loginAttempts.total);
  const loginSuccess = toNumber(loginAttempts.success);
  const loginFailed = toNumber(loginAttempts.failed);
  const loginBlocked = toNumber(loginAttempts.blocked);
  const loginSuccessRate = loginTotal > 0 ? (loginSuccess / loginTotal) * 100 : 0;
  const loginMax = Math.max(1, loginSuccess, loginFailed, loginBlocked);

  const suspiciousTotal = toNumber(suspicious.total);
  const suspiciousTone: "good" | "warn" | "bad" = suspiciousTotal === 0 ? "good" : suspiciousTotal < 5 ? "warn" : "bad";
  const suspiciousRisk = Math.min(100, suspiciousTotal * 15);

  const jwtIssued = toNumber(jwtMonitoring.jwt_issued);
  const jwtValidatedSuccess = toNumber(jwtMonitoring.jwt_validated_success);
  const jwtValidatedFailed = toNumber(jwtMonitoring.jwt_validated_failed);
  const jwtRecentFailed = toNumber(jwtMonitoring.recent_failed_validations);
  const jwtValidationTotal = jwtValidatedSuccess + jwtValidatedFailed;
  const jwtSuccessRate = jwtValidationTotal > 0 ? (jwtValidatedSuccess / jwtValidationTotal) * 100 : 100;
  const jwtMax = Math.max(1, jwtIssued, jwtValidatedSuccess, jwtValidatedFailed, jwtRecentFailed);
  const windowPct = Math.min(100, (minutes / 10080) * 100);
  const limitPct = Math.min(100, (limit / 500) * 100);

  const jwtSnapshotRows = [
    { label: "Login success", value: toNumber(jwtMonitoring.login_success), tone: "good" as const },
    { label: "Login failed", value: toNumber(jwtMonitoring.login_failed), tone: "bad" as const },
    { label: "Login blocked", value: toNumber(jwtMonitoring.login_blocked), tone: "warn" as const },
    { label: "JWT issued", value: jwtIssued, tone: "good" as const },
    { label: "JWT validated success", value: jwtValidatedSuccess, tone: "good" as const },
    { label: "JWT validated failed", value: jwtValidatedFailed, tone: "bad" as const },
    { label: "Recent failed validations", value: jwtRecentFailed, tone: "warn" as const },
  ];
  const jwtSnapshotMax = Math.max(1, ...jwtSnapshotRows.map((row) => row.value));

  const statusCounts = events.reduce<Record<string, number>>((acc, event) => {
    const key = String(event.status || "unknown").toLowerCase();
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  const statusRows = Object.entries(statusCounts).map(([label, value]) => ({
    label,
    value,
    tone: label === "success" ? "good" : label === "failed" || label === "blocked" ? "bad" : "warn",
  })) as Array<{ label: string; value: number; tone: "good" | "warn" | "bad" }>;
  const statusTotal = statusRows.reduce((sum, row) => sum + row.value, 0);

  const typeCounts = events.reduce<Record<string, number>>((acc, event) => {
    const key = String(event.event_type || "unknown").toLowerCase();
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  const typeRows = Object.entries(typeCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([label, value]) => ({ label, value }));
  const typeMax = Math.max(1, ...typeRows.map((row) => row.value), 1);

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
          <div className="security-top-chart">
            <CircleStat
              label="Success rate"
              value={loginSuccessRate}
              detail={`${loginSuccess}/${Math.max(1, loginTotal)} successful`}
              tone={loginSuccessRate >= 85 ? "good" : loginSuccessRate >= 65 ? "warn" : "bad"}
            />
            <div className="security-bars">
              {[
                { label: "Success", value: loginSuccess, tone: "good" as const },
                { label: "Failed", value: loginFailed, tone: "bad" as const },
                { label: "Blocked", value: loginBlocked, tone: "warn" as const },
              ].map((item) => (
                <div key={item.label} className="security-bar-row">
                  <span>{item.label}</span>
                  <div className="security-bar-track">
                    <div className={`security-bar-fill security-tone-${item.tone}`} style={{ width: `${Math.max(8, (item.value / loginMax) * 100)}%` }} />
                  </div>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </div>
          <p>Total attempts: <strong>{metricValue(loginAttempts, "total")}</strong></p>
        </article>
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">Suspicious activity</span>
          <div className="security-top-chart">
            <CircleStat
              label="Risk pressure"
              value={suspiciousRisk}
              detail={`${suspiciousTotal} suspicious events`}
              tone={suspiciousTone}
            />
            <div className="security-kpi-stack">
              <div className={`security-kpi-card security-tone-${suspiciousTone}`}>
                <span>Total suspicious</span>
                <strong>{metricValue(suspicious, "total")}</strong>
              </div>
              <div className="security-kpi-card">
                <span>Window (minutes)</span>
                <strong>{String(data?.window_minutes ?? "-")}</strong>
              </div>
              <div className="security-kpi-card">
                <span>Generated at</span>
                <strong>{toDisplayTimestamp(data?.generated_at)}</strong>
              </div>
            </div>
          </div>
        </article>
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">JWT token monitoring</span>
          <div className="security-top-chart">
            <CircleStat
              label="JWT success"
              value={jwtSuccessRate}
              detail={`${jwtValidatedSuccess}/${Math.max(1, jwtValidationTotal)} validations`}
              tone={jwtSuccessRate >= 95 ? "good" : jwtSuccessRate >= 85 ? "warn" : "bad"}
            />
            <div className="security-bars">
              {[
                { label: "Issued", value: jwtIssued, tone: "good" as const },
                { label: "Validated success", value: jwtValidatedSuccess, tone: "good" as const },
                { label: "Validated failed", value: jwtValidatedFailed, tone: "bad" as const },
                { label: "Recent failed", value: jwtRecentFailed, tone: "warn" as const },
              ].map((item) => (
                <div key={item.label} className="security-bar-row">
                  <span>{item.label}</span>
                  <div className="security-bar-track">
                    <div className={`security-bar-fill security-tone-${item.tone}`} style={{ width: `${Math.max(8, (item.value / jwtMax) * 100)}%` }} />
                  </div>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </div>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Filters</span>
          <div className="security-filter-visuals">
            <CircleStat
              label="Window span"
              value={windowPct}
              detail={`${minutes} minutes`}
              tone={minutes <= 360 ? "good" : minutes <= 1440 ? "warn" : "bad"}
            />
            <CircleStat
              label="Row cap"
              value={limitPct}
              detail={`${limit} rows`}
              tone={limit <= 100 ? "good" : limit <= 250 ? "warn" : "bad"}
            />
          </div>
          <div className="proposal-field-grid security-filter-grid">
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
          <div className="security-bars">
            {jwtSnapshotRows.map((item) => (
              <div key={item.label} className="security-bar-row">
                <span>{item.label}</span>
                <div className="security-bar-track">
                  <div className={`security-bar-fill security-tone-${item.tone}`} style={{ width: `${Math.max(8, (item.value / jwtSnapshotMax) * 100)}%` }} />
                </div>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
          <details className="security-raw">
            <summary>Show JWT raw payload</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(jwtMonitoring)}</pre>
          </details>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Recent security events</span>
          {loading ? <p>Loading security events...</p> : null}
          {!loading ? (
            <>
              <div className="security-event-charts">
                <div className="security-event-chart-card">
                  <h3>Status distribution</h3>
                  {statusRows.length ? (
                    statusRows.map((row) => {
                      const pct = statusTotal ? (row.value / statusTotal) * 100 : 0;
                      return (
                        <div key={row.label} className="security-bar-row">
                          <span>{row.label}</span>
                          <div className="security-bar-track">
                            <div className={`security-bar-fill security-tone-${row.tone}`} style={{ width: `${Math.max(8, pct)}%` }} />
                          </div>
                          <strong>{row.value}</strong>
                        </div>
                      );
                    })
                  ) : (
                    <p>No status data.</p>
                  )}
                </div>

                <div className="security-event-chart-card">
                  <h3>Top event types</h3>
                  {typeRows.length ? (
                    typeRows.map((row) => (
                      <div key={row.label} className="security-bar-row">
                        <span>{row.label.replace(/_/g, " ")}</span>
                        <div className="security-bar-track">
                          <div className="security-bar-fill" style={{ width: `${Math.max(8, (row.value / typeMax) * 100)}%` }} />
                        </div>
                        <strong>{row.value}</strong>
                      </div>
                    ))
                  ) : (
                    <p>No type data.</p>
                  )}
                </div>
              </div>

              <div className="security-event-timeline">
                {events.slice(0, 20).map((event, index) => {
                  const status = String(event.status || "").toLowerCase();
                  const tone = status === "success" ? "good" : status === "failed" || status === "blocked" ? "bad" : "warn";
                  return (
                    <div key={event._id || `${event.timestamp}-${index}`} className="security-event-item">
                      <span className={`security-event-dot security-tone-${tone}`} />
                      <div className="security-event-content">
                        <p>
                          <b>{(event.event_type || "-").replace(/_/g, " ")}</b> • {event.status || "-"}
                        </p>
                        <small>{toDisplayTimestamp(event.timestamp)} | {event.email || "-"} | {event.client_ip || "-"} | {event.detail || "-"}</small>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          ) : null}
        </article>
      </section>
    </main>
  );
}
