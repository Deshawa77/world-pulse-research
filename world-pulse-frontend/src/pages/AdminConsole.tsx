import { useEffect, useMemo, useState } from "react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import {
  getAdminUsers,
  getCountryRiskBacktestSummary,
  getCountryRiskValidationHistory,
  getCountryRiskValidationSummary,
  getCurrentUser,
  getGlobalMoodBacktestSummary,
  getGlobalMoodValidationHistory,
  getGlobalMoodValidationSummary,
  getHealthDependencies,
  getHealthLive,
  getHealthReady,
  getObservabilityMetrics,
  getObservabilityModel,
  getObservabilityStreaming,
  runObservabilityBacktests,
  updateAdminUserAccess,
  updateAdminUserStatus,
  type BacktestSummary,
  type HealthDependenciesResponse,
  type HealthStatus,
  type ObservabilityMetrics,
  type ObservabilityModelSummary,
  type ObservabilityStreamingSummary,
  type UserProfile,
  type UserRole,
  type UserType,
  type ValidationSummary,
} from "../services/api";
import "./Dashboard.css";
import "../components/futuristic-dashboard.css";

type AccessDraft = {
  role: UserRole;
  user_type: UserType;
};

function toDisplayTimestamp(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "-";
  return date.toLocaleString();
}

function compactJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

export default function AdminConsole() {
  const [me, setMe] = useState<UserProfile | null>(null);
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [drafts, setDrafts] = useState<Record<string, AccessDraft>>({});
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [healthLive, setHealthLive] = useState<HealthStatus | null>(null);
  const [healthReady, setHealthReady] = useState<HealthStatus | null>(null);
  const [healthDependencies, setHealthDependencies] = useState<HealthDependenciesResponse | null>(null);
  const [metrics, setMetrics] = useState<ObservabilityMetrics | null>(null);
  const [modelSummary, setModelSummary] = useState<ObservabilityModelSummary | null>(null);
  const [streamingSummary, setStreamingSummary] = useState<ObservabilityStreamingSummary | null>(null);
  const [countryValidation, setCountryValidation] = useState<ValidationSummary | null>(null);
  const [globalValidation, setGlobalValidation] = useState<ValidationSummary | null>(null);
  const [countryValidationHistory, setCountryValidationHistory] = useState<ValidationSummary[]>([]);
  const [globalValidationHistory, setGlobalValidationHistory] = useState<ValidationSummary[]>([]);
  const [countryBacktest, setCountryBacktest] = useState<BacktestSummary | null>(null);
  const [globalBacktest, setGlobalBacktest] = useState<BacktestSummary | null>(null);
  const [runningBacktests, setRunningBacktests] = useState(false);

  const adminCount = useMemo(() => users.filter((user) => user.role === "admin").length, [users]);
  const activeCount = useMemo(() => users.filter((user) => user.active).length, [users]);

  const securityAlerts = useMemo(() => {
    const alerts: string[] = [];
    const security = (metrics?.security ?? {}) as Record<string, unknown>;
    const requireHttps = security.require_https;
    if (requireHttps === false) {
      alerts.push("HTTPS enforcement is disabled.");
    }

    const dependencies = (healthDependencies?.dependencies ?? {}) as Record<string, unknown>;
    if (Object.keys(dependencies).length === 0) {
      alerts.push("Dependency status data is unavailable.");
    }

    const countryStatus = (countryValidation ?? {}) as Record<string, unknown>;
    const globalStatus = (globalValidation ?? {}) as Record<string, unknown>;
    if (String(countryStatus.status || "").toLowerCase() === "failed") {
      alerts.push("Country risk validation reported a failed status.");
    }
    if (String(globalStatus.status || "").toLowerCase() === "failed") {
      alerts.push("Global mood validation reported a failed status.");
    }

    return alerts;
  }, [metrics, healthDependencies, countryValidation, globalValidation]);

  const loadData = async () => {
    setLoading(true);
    setError("");

    try {
      const [
        profile,
        allUsers,
        live,
        ready,
        dependencies,
        observabilityMetrics,
        observabilityModel,
        observabilityStreaming,
        countryRiskValidation,
        globalMoodValidation,
        countryRiskValidationHistory,
        globalMoodValidationHistory,
        latestCountryBacktest,
        latestGlobalBacktest,
      ] = await Promise.all([
        getCurrentUser(),
        getAdminUsers(),
        getHealthLive(),
        getHealthReady(),
        getHealthDependencies("online"),
        getObservabilityMetrics(),
        getObservabilityModel(200),
        getObservabilityStreaming(),
        getCountryRiskValidationSummary(),
        getGlobalMoodValidationSummary(),
        getCountryRiskValidationHistory(30),
        getGlobalMoodValidationHistory(30),
        getCountryRiskBacktestSummary(),
        getGlobalMoodBacktestSummary(),
      ]);

      setMe(profile);
      setUsers(allUsers);
      setHealthLive(live);
      setHealthReady(ready);
      setHealthDependencies(dependencies);
      setMetrics(observabilityMetrics);
      setModelSummary(observabilityModel);
      setStreamingSummary(observabilityStreaming);
      setCountryValidation(countryRiskValidation);
      setGlobalValidation(globalMoodValidation);
      setCountryValidationHistory(countryRiskValidationHistory.rows || []);
      setGlobalValidationHistory(globalMoodValidationHistory.rows || []);
      setCountryBacktest(latestCountryBacktest);
      setGlobalBacktest(latestGlobalBacktest);

      const nextDrafts = allUsers.reduce<Record<string, AccessDraft>>((acc, user) => {
        acc[user.email] = { role: user.role, user_type: user.user_type };
        return acc;
      }, {});
      setDrafts(nextDrafts);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load admin console data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const setDraftValue = (email: string, key: keyof AccessDraft, value: AccessDraft[keyof AccessDraft]) => {
    setDrafts((current) => ({
      ...current,
      [email]: {
        role: current[email]?.role || "user",
        user_type: current[email]?.user_type || "researcher",
        [key]: value,
      },
    }));
  };

  const saveAccess = async (email: string) => {
    const draft = drafts[email];
    if (!draft) return;

    setSavingKey(`access:${email}`);
    setError("");
    setNotice("");

    try {
      const updated = await updateAdminUserAccess(email, {
        role: draft.role,
        user_type: draft.user_type,
      });

      setUsers((current) => current.map((user) => (user.email === email ? updated : user)));
      setNotice(`Updated access for ${email}.`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || `Failed to update access for ${email}.`);
    } finally {
      setSavingKey(null);
    }
  };

  const toggleUserActive = async (user: UserProfile) => {
    setSavingKey(`status:${user.email}`);
    setError("");
    setNotice("");

    try {
      const updated = await updateAdminUserStatus(user.email, !user.active);
      setUsers((current) => current.map((row) => (row.email === user.email ? updated : row)));
      setNotice(`${updated.email} is now ${updated.active ? "active" : "deactivated"}.`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || `Failed to update status for ${user.email}.`);
    } finally {
      setSavingKey(null);
    }
  };


  const runBacktestsNow = async () => {
    setRunningBacktests(true);
    setError("");
    setNotice("");

    try {
      await runObservabilityBacktests(60);
      setNotice("Historical backtests started and latest snapshots refreshed.");
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to run historical backtests.");
    } finally {
      setRunningBacktests(false);
    }
  };
  return (
    <main className="wp-shell proposal-runtime-shell">
      <ConsoleNavigation
        title={<>ADMIN <span>DASHBOARD</span></>}
        subtitle="Monitor system health, security posture, data integrity, and user lifecycle controls."
      />

      <section className="proposal-runtime-intro">
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">Current operator</span>
          <h2>{me?.name || me?.email || "Loading profile..."}</h2>
          <p>Role: <strong>{me?.role || "-"}</strong> | User type: <strong>{me?.user_type || "-"}</strong></p>
          <p>Admins: {adminCount} | Active users: {activeCount}/{users.length}</p>
        </article>
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">API status</span>
          <p>Live: <strong>{healthLive?.status || "-"}</strong></p>
          <p>Ready: <strong>{healthReady?.status || "-"}</strong></p>
          <p>Dependencies: <strong>{healthDependencies?.status || "-"}</strong></p>
        </article>
      </section>

      {error ? <div className="proposal-auth-error">{error}</div> : null}
      {notice ? <div className="proposal-auth-success">{notice}</div> : null}

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">System performance monitoring</span>
          {loading ? <p>Loading monitoring data...</p> : null}
          {!loading ? (
            <>
              <p>Runtime metrics and model performance summary are shown below.</p>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(metrics?.runtime)}</pre>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(modelSummary)}</pre>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(streamingSummary)}</pre>
            </>
          ) : null}
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Security alerts</span>
          {securityAlerts.length ? (
            <ul>
              {securityAlerts.map((alert) => (
                <li key={alert}>{alert}</li>
              ))}
            </ul>
          ) : (
            <p>No active security alerts from configured health and validation checks.</p>
          )}
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(metrics?.security)}</pre>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Data integrity logs</span>
          <p>Country and global validation snapshots:</p>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(countryValidation)}</pre>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(globalValidation)}</pre>
          <p>Latest historical backtests:</p>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(countryBacktest)}</pre>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(globalBacktest)}</pre>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Validation + backtest history</span>
          <p>Recent country validations: <strong>{countryValidationHistory.length}</strong></p>
          <p>Recent global validations: <strong>{globalValidationHistory.length}</strong></p>
          <p>Latest country status: <strong>{String((countryValidationHistory[0] as Record<string, unknown> | undefined)?.status || "-")}</strong></p>
          <p>Latest global status: <strong>{String((globalValidationHistory[0] as Record<string, unknown> | undefined)?.status || "-")}</strong></p>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(countryValidationHistory.slice(0, 5))}</pre>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(globalValidationHistory.slice(0, 5))}</pre>
          <div className="proposal-form-actions">
            <button className="proposal-button proposal-button-primary" onClick={loadData} disabled={loading || runningBacktests}>
              {loading ? "Refreshing..." : "Refresh dashboard"}
            </button>
            <button className="proposal-button" onClick={runBacktestsNow} disabled={loading || runningBacktests}>
              {runningBacktests ? "Running backtests..." : "Run 60d backtests"}
            </button>
          </div>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(healthDependencies?.dependencies)}</pre>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel" style={{ overflowX: "auto" }}>
          <span className="proposal-eyebrow">Manage users (activate/deactivate)</span>
          {!loading ? (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "8px" }}>Email</th>
                  <th style={{ textAlign: "left", padding: "8px" }}>Name</th>
                  <th style={{ textAlign: "left", padding: "8px" }}>Role</th>
                  <th style={{ textAlign: "left", padding: "8px" }}>User Type</th>
                  <th style={{ textAlign: "left", padding: "8px" }}>Status</th>
                  <th style={{ textAlign: "left", padding: "8px" }}>Updated</th>
                  <th style={{ textAlign: "left", padding: "8px" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => {
                  const draft = drafts[user.email] || { role: user.role, user_type: user.user_type };
                  const accessSaving = savingKey === `access:${user.email}`;
                  const statusSaving = savingKey === `status:${user.email}`;

                  return (
                    <tr key={user.email}>
                      <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>{user.email}</td>
                      <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>{user.name || "-"}</td>
                      <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                        <select
                          value={draft.role}
                          onChange={(event) => setDraftValue(user.email, "role", event.target.value as UserRole)}
                          disabled={accessSaving || statusSaving}
                        >
                          <option value="user">user</option>
                          <option value="admin">admin</option>
                        </select>
                      </td>
                      <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                        <select
                          value={draft.user_type}
                          onChange={(event) => setDraftValue(user.email, "user_type", event.target.value as UserType)}
                          disabled={accessSaving || statusSaving}
                        >
                          <option value="researcher">researcher</option>
                          <option value="policy">policy</option>
                          <option value="student">student</option>
                          <option value="developer">developer</option>
                        </select>
                      </td>
                      <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                        {user.active ? "active" : "deactivated"}
                        {!user.active ? (
                          <div style={{ fontSize: "0.75rem", opacity: 0.8 }}>
                            {toDisplayTimestamp(user.deactivated_at)} by {user.deactivated_by || "-"}
                          </div>
                        ) : null}
                      </td>
                      <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                        {toDisplayTimestamp(user.updated_at || user.created_at)}
                      </td>
                      <td style={{ padding: "8px", borderTop: "1px solid rgba(255,255,255,0.1)", display: "flex", gap: "8px" }}>
                        <button
                          className="proposal-button proposal-button-primary"
                          onClick={() => saveAccess(user.email)}
                          disabled={accessSaving || statusSaving}
                        >
                          {accessSaving ? "Saving..." : "Save access"}
                        </button>
                        <button
                          className="proposal-button"
                          onClick={() => toggleUserActive(user)}
                          disabled={accessSaving || statusSaving}
                        >
                          {statusSaving ? "Updating..." : user.active ? "Deactivate" : "Activate"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p>Loading users...</p>
          )}
        </article>
      </section>
    </main>
  );
}







