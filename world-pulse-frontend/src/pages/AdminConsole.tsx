import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
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
import "./AdminConsole.css";
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

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function toPercent(value: unknown, scale: "ratio" | "percent" = "ratio"): number | null {
  const numeric = toNumber(value);
  if (numeric === null) return null;
  if (scale === "percent") return Math.max(0, Math.min(100, numeric));
  return Math.max(0, Math.min(100, numeric * 100));
}

function formatNumber(value: unknown, fallback: string = "-"): string {
  const numeric = toNumber(value);
  if (numeric === null) return fallback;
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(numeric);
}

function formatPercent(value: unknown, scale: "ratio" | "percent" = "ratio", fallback: string = "-"): string {
  const pct = toPercent(value, scale);
  if (pct === null) return fallback;
  return `${pct.toFixed(1)}%`;
}

function statusTone(status: unknown): "good" | "warn" | "bad" | "neutral" {
  const text = String(status || "").trim().toLowerCase();
  if (!text) return "neutral";
  if (["ok", "ready", "healthy", "passed", "success", "active", "up"].includes(text)) return "good";
  if (["failed", "error", "down", "critical"].includes(text)) return "bad";
  if (["degraded", "warning", "stale", "monitoring", "unknown"].includes(text)) return "warn";
  return "neutral";
}

function formatStatus(status: unknown): string {
  const text = String(status || "").trim();
  if (!text) return "-";
  return text.replace(/_/g, " ");
}

function initialsFromIdentity(name?: string | null, email?: string | null): string {
  const source = String(name || email || "U").trim();
  if (!source) return "U";
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
}

function avatarStorageKey(email?: string | null): string | null {
  const normalized = String(email || "").trim().toLowerCase();
  if (!normalized) return null;
  return `wp_admin_avatar_${normalized}`;
}

function CircularGauge({
  label,
  valuePercent,
  subtitle,
  variant = "primary",
}: {
  label: string;
  valuePercent: number | null;
  subtitle: string;
  variant?: "primary" | "warning";
}) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, valuePercent ?? 0));
  const dash = (clamped / 100) * circumference;

  return (
    <div className={`admin-gauge-card admin-gauge-${variant}`}>
      <span className="admin-gauge-label">{label}</span>
      <div className="admin-gauge-ring">
        <svg viewBox="0 0 100 100" aria-hidden="true">
          <circle className="admin-gauge-track" cx="50" cy="50" r={radius} />
          <circle
            className="admin-gauge-progress"
            cx="50"
            cy="50"
            r={radius}
            strokeDasharray={`${dash} ${circumference - dash}`}
          />
        </svg>
        <strong>{valuePercent === null ? "-" : `${clamped.toFixed(0)}%`}</strong>
      </div>
      <p>{subtitle}</p>
    </div>
  );
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
  const [operatorAvatar, setOperatorAvatar] = useState("");
  const [avatarUrlDraft, setAvatarUrlDraft] = useState("");
  const avatarInputRef = useRef<HTMLInputElement | null>(null);

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

  const runtimeStats = useMemo(() => {
    const runtime = (metrics?.runtime ?? {}) as Record<string, unknown>;
    const model = (modelSummary ?? {}) as Record<string, unknown>;
    const stream = (streamingSummary ?? {}) as Record<string, unknown>;

    const totalRequests = toNumber(runtime.total_requests) ?? 0;
    const totalErrors = toNumber(runtime.total_errors) ?? 0;
    const totalPredictions = toNumber(runtime.total_predictions) ?? 0;
    const startedAt = typeof runtime.started_at === "string" ? runtime.started_at : null;

    let requestsPerMinute: number | null = null;
    if (startedAt) {
      const startedDate = new Date(startedAt);
      if (Number.isFinite(startedDate.getTime())) {
        const minutes = (Date.now() - startedDate.getTime()) / 60000;
        if (minutes > 0) {
          requestsPerMinute = totalRequests / minutes;
        }
      }
    }

    const modelSamples = toNumber(model.samples);
    const avgProbabilityPct = toPercent(model.avg_probability, "ratio");
    const avgDriftPct = toPercent(model.avg_drift_score, "ratio");
    const driftAlert = Boolean(model.drift_alert);

    const errorRatePct = totalRequests > 0 ? (totalErrors / totalRequests) * 100 : 0;

    const throughputBars = [
      { label: "Requests", value: totalRequests },
      { label: "Predictions", value: totalPredictions },
      { label: "Errors", value: totalErrors },
      { label: "Model samples", value: modelSamples ?? 0 },
    ];
    const throughputMax = Math.max(1, ...throughputBars.map((item) => item.value));

    const streamNumericBars = Object.entries(stream)
      .filter(([, value]) => toNumber(value) !== null)
      .slice(0, 5)
      .map(([key, value]) => ({
        label: key.replace(/_/g, " "),
        value: toNumber(value) ?? 0,
      }));
    const streamMax = Math.max(1, ...streamNumericBars.map((item) => item.value), 1);

    return {
      totalRequests,
      totalErrors,
      totalPredictions,
      requestsPerMinute,
      modelSamples,
      avgProbabilityPct,
      avgDriftPct,
      driftAlert,
      errorRatePct,
      throughputBars,
      throughputMax,
      streamNumericBars,
      streamMax,
    };
  }, [metrics, modelSummary, streamingSummary]);

  const securityView = useMemo(() => {
    const security = (metrics?.security ?? {}) as Record<string, unknown>;
    const requireHttps = security.require_https === true;
    const allowInsecureLocalhost = security.allow_insecure_localhost === true;
    const userKeys = toNumber(security.user_keys_configured) ?? 0;
    const adminKeys = toNumber(security.admin_keys_configured) ?? 0;
    const statusItems = [
      { label: "HTTPS enforcement", value: requireHttps ? "Enabled" : "Disabled", tone: requireHttps ? "good" : "bad" },
      { label: "Localhost insecure", value: allowInsecureLocalhost ? "Allowed" : "Blocked", tone: allowInsecureLocalhost ? "warn" : "good" },
      { label: "User keys", value: formatNumber(userKeys), tone: userKeys > 0 ? "good" : "warn" },
      { label: "Admin keys", value: formatNumber(adminKeys), tone: adminKeys > 0 ? "good" : "bad" },
    ] as Array<{ label: string; value: string; tone: "good" | "warn" | "bad" }>;

    const securityRiskScore =
      (requireHttps ? 0 : 45)
      + (allowInsecureLocalhost ? 20 : 0)
      + (adminKeys === 0 ? 25 : 0)
      + Math.min(20, securityAlerts.length * 5);

    const postureBars = [
      { label: "TLS posture", value: requireHttps ? 100 : 15 },
      { label: "Key coverage", value: Math.min(100, (adminKeys + userKeys) * 25) },
      { label: "Alert pressure", value: Math.max(0, 100 - Math.min(100, securityAlerts.length * 20)) },
    ];
    const alertCount = securityAlerts.length;

    return {
      statusItems,
      securityRiskScore: Math.min(100, securityRiskScore),
      postureBars,
      alertCount,
      security,
    };
  }, [metrics, securityAlerts]);

  const integrityView = useMemo(() => {
    const country = (countryValidation ?? {}) as Record<string, unknown>;
    const global = (globalValidation ?? {}) as Record<string, unknown>;
    const countryMetrics = ((country.metrics ?? {}) as Record<string, unknown>);
    const globalMetrics = ((global.metrics ?? {}) as Record<string, unknown>);
    const countryBt = (countryBacktest ?? {}) as Record<string, unknown>;
    const globalBt = (globalBacktest ?? {}) as Record<string, unknown>;
    const countryBtMetrics = ((countryBt.metrics ?? {}) as Record<string, unknown>);
    const globalBtMetrics = ((globalBt.metrics ?? {}) as Record<string, unknown>);

    const cards = [
      {
        label: "Country validation",
        status: formatStatus(country.status),
        tone: statusTone(country.status),
        timestamp: toDisplayTimestamp(country.timestamp as string | undefined),
        metricLabel: "Brier score",
        metricValue: formatNumber(countryMetrics.brier_score),
      },
      {
        label: "Global validation",
        status: formatStatus(global.status),
        tone: statusTone(global.status),
        timestamp: toDisplayTimestamp(global.timestamp as string | undefined),
        metricLabel: "Confidence avg",
        metricValue: formatNumber(globalMetrics.confidence_avg),
      },
      {
        label: "Country backtest",
        status: formatStatus(countryBt.status),
        tone: statusTone(countryBt.status),
        timestamp: toDisplayTimestamp(countryBt.timestamp as string | undefined),
        metricLabel: "Weighted brier",
        metricValue: formatNumber(countryBtMetrics.weighted_brier_score),
      },
      {
        label: "Global backtest",
        status: formatStatus(globalBt.status),
        tone: statusTone(globalBt.status),
        timestamp: toDisplayTimestamp(globalBt.timestamp as string | undefined),
        metricLabel: "Weighted MAE",
        metricValue: formatNumber(globalBtMetrics.weighted_mae),
      },
    ];

    const bars = [
      { label: "Country sample count", value: toNumber(country.sample_count) ?? 0 },
      { label: "Global sample count", value: toNumber(global.sample_count) ?? 0 },
      { label: "Country matched days", value: toNumber(countryBt.matched_days) ?? 0 },
      { label: "Global matched days", value: toNumber(globalBt.matched_days) ?? 0 },
    ];
    const maxBar = Math.max(1, ...bars.map((item) => item.value));

    const qualityScore = Math.max(
      0,
      Math.min(
        100,
        100
          - ((toNumber(countryMetrics.brier_score) ?? 0) * 100 * 0.4)
          - ((toNumber(countryBtMetrics.weighted_brier_score) ?? 0) * 100 * 0.3)
          - ((toNumber(globalBtMetrics.weighted_mae) ?? 0) * 100 * 0.2)
          + ((toNumber(globalMetrics.confidence_avg) ?? 0) * 100 * 0.1),
      ),
    );

    return {
      cards,
      bars,
      maxBar,
      qualityScore,
    };
  }, [countryValidation, globalValidation, countryBacktest, globalBacktest]);

  const historyView = useMemo(() => {
    const countryRecent = countryValidationHistory.slice(0, 10);
    const globalRecent = globalValidationHistory.slice(0, 10);

    const toTimeline = (rows: ValidationSummary[]) =>
      rows.map((row, index) => {
        const item = row as Record<string, unknown>;
        const status = String(item.status || "unknown");
        const sampleCount = toNumber(item.sample_count) ?? 0;
        const timestamp = toDisplayTimestamp((item.timestamp as string | undefined) ?? null);
        return {
          id: `${status}-${timestamp}-${index}`,
          status,
          tone: statusTone(status),
          sampleCount,
          timestamp,
        };
      });

    const countryTimeline = toTimeline(countryRecent);
    const globalTimeline = toTimeline(globalRecent);

    const summarize = (rows: Array<{ tone: "good" | "warn" | "bad" | "neutral" }>) => ({
      good: rows.filter((item) => item.tone === "good").length,
      warn: rows.filter((item) => item.tone === "warn").length,
      bad: rows.filter((item) => item.tone === "bad").length,
      neutral: rows.filter((item) => item.tone === "neutral").length,
      total: rows.length,
    });

    const countrySummary = summarize(countryTimeline);
    const globalSummary = summarize(globalTimeline);

    return {
      countryTimeline,
      globalTimeline,
      countrySummary,
      globalSummary,
    };
  }, [countryValidationHistory, globalValidationHistory]);

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

  useEffect(() => {
    const key = avatarStorageKey(me?.email);
    if (!key || typeof window === "undefined") {
      setOperatorAvatar("");
      setAvatarUrlDraft("");
      return;
    }
    const stored = String(window.localStorage.getItem(key) || "");
    setOperatorAvatar(stored);
    setAvatarUrlDraft(stored);
  }, [me?.email]);

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

  const saveAvatar = (nextUrl: string) => {
    const key = avatarStorageKey(me?.email);
    if (!key || typeof window === "undefined") return;
    const cleaned = String(nextUrl || "").trim();
    if (cleaned) {
      window.localStorage.setItem(key, cleaned);
    } else {
      window.localStorage.removeItem(key);
    }
    setOperatorAvatar(cleaned);
    setAvatarUrlDraft(cleaned);
  };

  const handleAvatarFileUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      if (result) saveAvatar(result);
    };
    reader.readAsDataURL(file);
    event.target.value = "";
  };

  return (
    <main className="wp-shell proposal-runtime-shell">
      <ConsoleNavigation
        title={<>ADMIN <span>DASHBOARD</span></>}
        subtitle="Monitor system health, security posture, data integrity, and user lifecycle controls."
      />

      <section className="proposal-runtime-intro">
        <article className="proposal-runtime-panel current-operator-panel">
          <span className="proposal-eyebrow">Current operator</span>
          <div className="current-operator-layout">
            <div className="current-operator-avatar-wrap">
              {operatorAvatar ? (
                <img
                  src={operatorAvatar}
                  alt={`${me?.name || me?.email || "Operator"} profile`}
                  className="current-operator-avatar"
                />
              ) : (
                <div className="current-operator-avatar-fallback">
                  {initialsFromIdentity(me?.name, me?.email)}
                </div>
              )}
            </div>

            <div className="current-operator-info">
              <h2>{me?.name || me?.email || "Loading profile..."}</h2>
              <p>Role: <strong>{me?.role || "-"}</strong> | User type: <strong>{me?.user_type || "-"}</strong></p>
              <p>Admins: {adminCount} | Active users: {activeCount}/{users.length}</p>
            </div>
          </div>

          <div className="current-operator-avatar-controls">
            <label className="current-operator-avatar-label" htmlFor="operator-avatar-url">
              Profile image URL
            </label>
            <div className="current-operator-avatar-actions">
              <input
                id="operator-avatar-url"
                type="text"
                value={avatarUrlDraft}
                onChange={(event) => setAvatarUrlDraft(event.target.value)}
                placeholder="https://example.com/avatar.jpg"
              />
              <button
                type="button"
                className="proposal-button proposal-button-primary"
                onClick={() => saveAvatar(avatarUrlDraft)}
              >
                Save photo
              </button>
              <button
                type="button"
                className="proposal-button"
                onClick={() => avatarInputRef.current?.click()}
              >
                Upload file
              </button>
              <button
                type="button"
                className="proposal-button"
                onClick={() => saveAvatar("")}
              >
                Remove
              </button>
              <input
                ref={avatarInputRef}
                type="file"
                accept="image/*"
                style={{ display: "none" }}
                onChange={handleAvatarFileUpload}
              />
            </div>
          </div>
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
              <div className="admin-monitoring-kpi-grid">
                <div className="admin-monitoring-kpi">
                  <span>Total requests</span>
                  <strong>{formatNumber(runtimeStats.totalRequests)}</strong>
                </div>
                <div className="admin-monitoring-kpi">
                  <span>Requests / min</span>
                  <strong>{runtimeStats.requestsPerMinute === null ? "-" : formatNumber(runtimeStats.requestsPerMinute)}</strong>
                </div>
                <div className="admin-monitoring-kpi">
                  <span>Total predictions</span>
                  <strong>{formatNumber(runtimeStats.totalPredictions)}</strong>
                </div>
                <div className="admin-monitoring-kpi">
                  <span>Model samples</span>
                  <strong>{formatNumber(runtimeStats.modelSamples)}</strong>
                </div>
              </div>

              <div className="admin-monitoring-visuals">
                <CircularGauge
                  label="Error rate"
                  valuePercent={runtimeStats.errorRatePct}
                  subtitle={`${formatNumber(runtimeStats.totalErrors)} errors`}
                  variant="warning"
                />
                <CircularGauge
                  label="Avg drift"
                  valuePercent={runtimeStats.avgDriftPct}
                  subtitle={runtimeStats.driftAlert ? "Drift alert active" : "Drift stable"}
                  variant={runtimeStats.driftAlert ? "warning" : "primary"}
                />
                <CircularGauge
                  label="Avg probability"
                  valuePercent={runtimeStats.avgProbabilityPct}
                  subtitle={formatPercent((modelSummary as Record<string, unknown> | null)?.avg_probability, "ratio")}
                />
              </div>

              <div className="admin-monitoring-bars">
                <h3>Runtime throughput</h3>
                {runtimeStats.throughputBars.map((item) => {
                  const widthPct = (item.value / runtimeStats.throughputMax) * 100;
                  return (
                    <div key={item.label} className="admin-monitoring-bar-row">
                      <span>{item.label}</span>
                      <div className="admin-monitoring-bar-track">
                        <div className="admin-monitoring-bar-fill" style={{ width: `${widthPct}%` }} />
                      </div>
                      <strong>{formatNumber(item.value)}</strong>
                    </div>
                  );
                })}
              </div>

              {runtimeStats.streamNumericBars.length ? (
                <div className="admin-monitoring-bars">
                  <h3>Streaming service activity</h3>
                  {runtimeStats.streamNumericBars.map((item) => {
                    const widthPct = (item.value / runtimeStats.streamMax) * 100;
                    return (
                      <div key={item.label} className="admin-monitoring-bar-row">
                        <span>{item.label}</span>
                        <div className="admin-monitoring-bar-track">
                          <div className="admin-monitoring-bar-fill admin-monitoring-bar-fill-alt" style={{ width: `${widthPct}%` }} />
                        </div>
                        <strong>{formatNumber(item.value)}</strong>
                      </div>
                    );
                  })}
                </div>
              ) : null}

              <details className="admin-monitoring-raw">
                <summary>Show raw payload</summary>
                <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(metrics?.runtime)}</pre>
                <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(modelSummary)}</pre>
                <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(streamingSummary)}</pre>
              </details>
            </>
          ) : null}
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Security alerts</span>
          <div className="admin-security-top">
            <div className="admin-security-risk">
              <CircularGauge
                label="Risk index"
                valuePercent={securityView.securityRiskScore}
                subtitle={`${securityView.alertCount} active alerts`}
                variant={securityView.securityRiskScore >= 55 ? "warning" : "primary"}
              />
            </div>
            <div className="admin-security-posture">
              {securityView.statusItems.map((item) => (
                <div key={item.label} className={`admin-status-tile admin-status-${item.tone}`}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </div>

          <div className="admin-security-bars">
            {securityView.postureBars.map((item) => (
              <div key={item.label} className="admin-security-bar-row">
                <span>{item.label}</span>
                <div className="admin-security-bar-track">
                  <div className="admin-security-bar-fill" style={{ width: `${item.value}%` }} />
                </div>
                <strong>{item.value.toFixed(0)}%</strong>
              </div>
            ))}
          </div>

          <div className="admin-security-alert-list">
            {securityAlerts.length ? (
              securityAlerts.map((alert) => (
                <p key={alert} className="admin-alert-pill">{alert}</p>
              ))
            ) : (
              <p className="admin-alert-pill admin-alert-pill-ok">No active security alerts from configured checks.</p>
            )}
          </div>

          <details className="admin-monitoring-raw">
            <summary>Show raw security payload</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(securityView.security)}</pre>
          </details>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Data integrity logs</span>
          <div className="admin-integrity-score-wrap">
            <CircularGauge
              label="Integrity score"
              valuePercent={integrityView.qualityScore}
              subtitle={integrityView.qualityScore >= 70 ? "Healthy confidence posture" : "Needs quality improvements"}
              variant={integrityView.qualityScore >= 70 ? "primary" : "warning"}
            />
          </div>

          <div className="admin-integrity-cards">
            {integrityView.cards.map((item) => (
              <article key={item.label} className={`admin-integrity-card admin-status-${item.tone}`}>
                <span>{item.label}</span>
                <strong>{item.status}</strong>
                <p>{item.metricLabel}: <b>{item.metricValue}</b></p>
                <p>Updated: {item.timestamp}</p>
              </article>
            ))}
          </div>

          <div className="admin-integrity-bars">
            {integrityView.bars.map((item) => {
              const widthPct = (item.value / integrityView.maxBar) * 100;
              return (
                <div key={item.label} className="admin-security-bar-row">
                  <span>{item.label}</span>
                  <div className="admin-security-bar-track">
                    <div className="admin-security-bar-fill admin-integrity-bar-fill" style={{ width: `${widthPct}%` }} />
                  </div>
                  <strong>{formatNumber(item.value)}</strong>
                </div>
              );
            })}
          </div>

          <details className="admin-monitoring-raw">
            <summary>Show raw integrity payload</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(countryValidation)}</pre>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(globalValidation)}</pre>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(countryBacktest)}</pre>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(globalBacktest)}</pre>
          </details>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Validation + backtest history</span>
          <div className="admin-history-summary-grid">
            <article className="admin-history-summary-card">
              <span>Country validations</span>
              <strong>{countryValidationHistory.length}</strong>
              <p>Good {historyView.countrySummary.good} | Warn {historyView.countrySummary.warn} | Bad {historyView.countrySummary.bad}</p>
            </article>
            <article className="admin-history-summary-card">
              <span>Global validations</span>
              <strong>{globalValidationHistory.length}</strong>
              <p>Good {historyView.globalSummary.good} | Warn {historyView.globalSummary.warn} | Bad {historyView.globalSummary.bad}</p>
            </article>
          </div>

          <div className="admin-history-timelines">
            <div className="admin-history-column">
              <h3>Country timeline</h3>
              {historyView.countryTimeline.length ? (
                historyView.countryTimeline.map((item) => (
                  <div key={item.id} className="admin-history-row">
                    <span className={`admin-history-dot admin-status-${item.tone}`} />
                    <div className="admin-history-content">
                      <p>{formatStatus(item.status)}</p>
                      <small>{item.timestamp}</small>
                    </div>
                    <div className="admin-history-mini-track">
                      <div
                        className={`admin-history-mini-fill admin-status-${item.tone}`}
                        style={{ width: `${Math.min(100, Math.max(12, item.sampleCount))}%` }}
                      />
                    </div>
                  </div>
                ))
              ) : (
                <p>No country validation history yet.</p>
              )}
            </div>

            <div className="admin-history-column">
              <h3>Global timeline</h3>
              {historyView.globalTimeline.length ? (
                historyView.globalTimeline.map((item) => (
                  <div key={item.id} className="admin-history-row">
                    <span className={`admin-history-dot admin-status-${item.tone}`} />
                    <div className="admin-history-content">
                      <p>{formatStatus(item.status)}</p>
                      <small>{item.timestamp}</small>
                    </div>
                    <div className="admin-history-mini-track">
                      <div
                        className={`admin-history-mini-fill admin-status-${item.tone}`}
                        style={{ width: `${Math.min(100, Math.max(12, item.sampleCount))}%` }}
                      />
                    </div>
                  </div>
                ))
              ) : (
                <p>No global validation history yet.</p>
              )}
            </div>
          </div>

          <div className="proposal-form-actions">
            <button className="proposal-button proposal-button-primary" onClick={loadData} disabled={loading || runningBacktests}>
              {loading ? "Refreshing..." : "Refresh dashboard"}
            </button>
            <button className="proposal-button" onClick={runBacktestsNow} disabled={loading || runningBacktests}>
              {runningBacktests ? "Running backtests..." : "Run 60d backtests"}
            </button>
          </div>
          <details className="admin-monitoring-raw">
            <summary>Show raw history payload</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(countryValidationHistory.slice(0, 10))}</pre>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(globalValidationHistory.slice(0, 10))}</pre>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.78rem" }}>{compactJson(healthDependencies?.dependencies)}</pre>
          </details>
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







