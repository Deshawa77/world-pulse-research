import { startTransition, useEffect, useEffectEvent, useState } from "react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import {
  getPlanetaryBehaviorOperatorSurface,
  getPlanetaryBehaviorReplay,
  type PlanetaryBehaviorOperatorSurfaceResponse,
  type PlanetaryBehaviorReplayFrame,
  type PlanetaryCountrySnapshot,
  type PlanetaryNormalizedSignal,
} from "../services/api";
import "./Dashboard.css";
import "./BehaviorIntelligence.css";

function safeNumber(value: number | undefined | null, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeRatio(value: number | undefined | null): number {
  const numeric = safeNumber(value, 0);
  if (numeric > 1) {
    return Math.max(0, Math.min(1, numeric / 100));
  }
  return Math.max(0, Math.min(1, numeric));
}

function formatPercent(value: number | undefined | null, digits = 0): string {
  return `${(normalizeRatio(value) * 100).toFixed(digits)}%`;
}

function formatNumber(value: number | undefined | null, digits = 1): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatRelativeTime(value: string | undefined | null): string {
  if (!value) return "--";
  const stamp = new Date(value);
  if (!Number.isFinite(stamp.getTime())) return value;
  const deltaSec = Math.max(0, Math.round((Date.now() - stamp.getTime()) / 1000));
  if (deltaSec < 60) return `${deltaSec}s ago`;
  if (deltaSec < 3600) return `${Math.round(deltaSec / 60)}m ago`;
  if (deltaSec < 86400) return `${Math.round(deltaSec / 3600)}h ago`;
  return `${Math.round(deltaSec / 86400)}d ago`;
}

function titleCase(value: string | undefined | null): string {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .trim();
}

function toneClass(value: number | undefined | null): string {
  const ratio = normalizeRatio(value);
  if (ratio >= 0.75) return "is-critical";
  if (ratio >= 0.55) return "is-elevated";
  if (ratio >= 0.35) return "is-guarded";
  return "is-stable";
}

function buildReplayPath(frames: PlanetaryBehaviorReplayFrame[], width = 320, height = 110): string {
  if (!frames.length) return "";
  const step = frames.length > 1 ? width / (frames.length - 1) : width;
  return frames
    .map((item, index) => {
      const x = index * step;
      const y = height - (normalizeRatio(item.severity_score) * height);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export default function BehaviorIntelligence() {
  const [surface, setSurface] = useState<PlanetaryBehaviorOperatorSurfaceResponse | null>(null);
  const [replay, setReplay] = useState<PlanetaryBehaviorReplayFrame[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSurface = useEffectEvent(async (refresh = false) => {
    if (refresh || surface) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const [nextSurface, nextReplay] = await Promise.all([
        getPlanetaryBehaviorOperatorSurface(refresh),
        getPlanetaryBehaviorReplay(refresh),
      ]);
      startTransition(() => {
        setSurface(nextSurface);
        setReplay(nextReplay.replay_frames || []);
      });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load behavior intelligence.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  });

  useEffect(() => {
    void loadSurface(false);
    const intervalId = window.setInterval(() => {
      void loadSurface(false);
    }, 90000);
    return () => window.clearInterval(intervalId);
  }, [loadSurface]);

  const snapshot = surface?.global_behavior_snapshot;
  const topCountries = surface?.top_countries || [];
  const narrativeWatch = surface?.narrative_watch || [];
  const regionalHeat = surface?.regional_heat || [];
  const sourceHealth = surface?.source_health || {};
  const replayPath = buildReplayPath(replay);
  const replayAverageSeverity = replay.length
    ? replay.reduce((sum, item) => sum + normalizeRatio(item.severity_score), 0) / replay.length
    : 0;
  const replayAverageConfidence = replay.length
    ? replay.reduce((sum, item) => sum + normalizeRatio(item.confidence_ratio), 0) / replay.length
    : 0;
  const replayPeak = replay.reduce<PlanetaryBehaviorReplayFrame | null>((best, item) => {
    if (!best) return item;
    return normalizeRatio(item.severity_score) > normalizeRatio(best.severity_score) ? item : best;
  }, null);
  const replayCountryMix = Array.from(new Set(replay.map((item) => item.country))).slice(0, 6);
  const replaySourceMix = replay.reduce<Record<string, number>>((acc, item) => {
    for (const [key, value] of Object.entries(item.source_families || {})) {
      acc[key] = (acc[key] || 0) + Number(value || 0);
    }
    return acc;
  }, {});
  const replaySourceHighlights = Object.entries(replaySourceMix)
    .sort((left, right) => right[1] - left[1])
    .slice(0, 4);

  return (
    <div className="wp-page behavior-console">
      <ConsoleNavigation
        title={<>Human Behavior Intelligence</>}
        subtitle="A dedicated operator surface for world stress, narrative acceleration, disruption pressure, and replayable behavior shifts."
        rightSlot={
          <div className="behavior-console__header-actions">
            <span className="behavior-console__stamp">Updated {formatRelativeTime(surface?.generated_at)}</span>
            <button type="button" className="behavior-console__refresh" onClick={() => void loadSurface(true)} disabled={refreshing}>
              {refreshing ? "Refreshing..." : "Refresh behavior view"}
            </button>
          </div>
        }
        sectionTabs={[
          { label: "Global", targetId: "behavior-global", badge: String(topCountries.length || 0) },
          { label: "Countries", targetId: "behavior-countries", badge: String(topCountries.length || 0) },
          { label: "Signals", targetId: "behavior-signals", badge: String(narrativeWatch.length || 0) },
          { label: "Replay", targetId: "behavior-replay", badge: String(replay.length || 0) },
        ]}
      />

      <main className="behavior-console__main">
        {error ? (
          <section className="behavior-console__error">
            <strong>Behavior surface degraded.</strong>
            <span>{error}</span>
          </section>
        ) : null}

        {!surface && loading ? (
          <section className="behavior-console__loading">
            <strong>Building behavior operator surface...</strong>
            <p>Collecting country stress, narrative watch, and replayable behavior signals.</p>
          </section>
        ) : null}

        {surface ? (
          <>
            <section id="behavior-global" className="behavior-console__hero">
              <article className="behavior-console__hero-copy">
                <span className="behavior-console__eyebrow">Global pulse</span>
                <h2>Monitor narrative acceleration, social strain, and disruption pressure in one behavior-first deck.</h2>
                <p>Confidence {formatPercent(snapshot?.confidence_ratio, 0)} with freshness {formatNumber(snapshot?.freshness_sec, 0)}s.</p>
              </article>
              <div className="behavior-console__hero-metrics">
                {[
                  { label: "Global Stress", value: snapshot?.global_stress_level },
                  { label: "Behavior Index", value: snapshot?.global_behavior_index },
                  { label: "Attention", value: snapshot?.global_attention_index },
                  { label: "Disruption", value: snapshot?.global_disruption_index },
                  { label: "Economic", value: snapshot?.global_economic_stress_index },
                  { label: "Migration", value: snapshot?.migration_pressure_index },
                ].map((item) => (
                  <article key={item.label} className={`behavior-console__metric ${toneClass(item.value)}`}>
                    <span>{item.label}</span>
                    <strong>{formatPercent(item.value, 0)}</strong>
                  </article>
                ))}
              </div>
            </section>

            <section id="behavior-countries" className="behavior-console__two-column">
              <article className="behavior-console__panel behavior-console__panel--span-two">
                <div className="behavior-console__panel-header">
                  <div>
                    <span className="behavior-console__eyebrow">Country ladder</span>
                    <h3>Top stressed countries</h3>
                  </div>
                  <span className="behavior-console__badge">{topCountries.length} tracked</span>
                </div>
                <div className="behavior-console__country-grid">
                  {topCountries.map((item: PlanetaryCountrySnapshot) => (
                    <article key={item.country} className={`behavior-console__country-card ${toneClass(item.display_risk ?? item.raw_risk_score)}`}>
                      <div className="behavior-console__country-topline">
                        <strong>{item.country}</strong>
                        <span>{item.risk_band || "unknown"}</span>
                      </div>
                      <div className="behavior-console__country-score">{formatNumber(item.display_risk ?? item.raw_risk_score, 1)}</div>
                      <p>{item.advisory || "Review fast-moving behavior and context drivers."}</p>
                      <div className="behavior-console__country-meta">
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        <span>Behavior {formatPercent(item.signal_scores?.direct_behavior_score, 0)}</span>
                        <span>Context {formatPercent(item.signal_scores?.contextual_pressure_score, 0)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>

              <article className="behavior-console__panel">
                <div className="behavior-console__panel-header">
                  <div>
                    <span className="behavior-console__eyebrow">Regional heat</span>
                    <h3>Signal geography</h3>
                  </div>
                </div>
                <div className="behavior-console__list">
                  {regionalHeat.slice(0, 10).map((item) => (
                    <article key={item.country} className={`behavior-console__list-card ${toneClass(item.avg_severity)}`}>
                      <div className="behavior-console__list-topline">
                        <strong>{item.country}</strong>
                        <span>{item.signal_count} signals</span>
                      </div>
                      <div className="behavior-console__list-meta">
                        <span>Severity {formatPercent(item.avg_severity, 0)}</span>
                        <span>Confidence {formatPercent(item.avg_confidence, 0)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>
            </section>

            <section id="behavior-signals" className="behavior-console__two-column">
              <article className="behavior-console__panel">
                <div className="behavior-console__panel-header">
                  <div>
                    <span className="behavior-console__eyebrow">Narrative watch</span>
                    <h3>Top behavior signals</h3>
                  </div>
                </div>
                <div className="behavior-console__list">
                  {narrativeWatch.slice(0, 10).map((item: PlanetaryNormalizedSignal) => (
                    <article key={item.signal_id} className={`behavior-console__list-card ${toneClass(item.severity_score)}`}>
                      <div className="behavior-console__list-topline">
                        <strong>{titleCase(item.signal_type)}</strong>
                        <span>{String(item.geography?.country || item.geography?.scope || "GLOBAL")}</span>
                      </div>
                      <p>{titleCase(item.metric_name)} via {titleCase(item.source_family)}</p>
                      <div className="behavior-console__list-meta">
                        <span>Severity {formatPercent(item.severity_score, 0)}</span>
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        <span>{formatRelativeTime(item.timestamp)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>

              <article className="behavior-console__panel">
                <div className="behavior-console__panel-header">
                  <div>
                    <span className="behavior-console__eyebrow">Source posture</span>
                    <h3>Behavior signal health</h3>
                  </div>
                </div>
                <div className="behavior-console__pill-grid">
                  {Object.entries(sourceHealth.normalized_signal_families || {}).map(([key, value]) => (
                    <div key={`signal:${key}`} className="behavior-console__pill">
                      <span>{titleCase(key)}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                  {Object.entries(sourceHealth.source_event_families || {}).map(([key, value]) => (
                    <div key={`event:${key}`} className="behavior-console__pill">
                      <span>{titleCase(key)} events</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
              </article>
            </section>

            <section id="behavior-replay" className="behavior-console__panel">
              <div className="behavior-console__panel-header">
                <div>
                  <span className="behavior-console__eyebrow">Replay strip</span>
                  <h3>Behavior timeline frames</h3>
                </div>
                <span className="behavior-console__badge">{replay.length} frames</span>
              </div>
              <div className="behavior-console__replay-layout">
                <article className="behavior-console__replay-chart-panel">
                  <div className="behavior-console__replay-chart-head">
                    <div>
                      <strong>Severity trend</strong>
                      <span>Replayable behavior pressure over the latest persisted frames.</span>
                    </div>
                    <div className="behavior-console__replay-insight-pill">
                      <span>Avg severity</span>
                      <strong>{formatPercent(replayAverageSeverity, 0)}</strong>
                    </div>
                  </div>
                  <div className="behavior-console__replay-chart-shell">
                    <svg viewBox="0 0 320 110" preserveAspectRatio="none" className="behavior-console__replay-chart">
                      <defs>
                        <linearGradient id="behaviorReplayStroke" x1="0%" y1="0%" x2="100%" y2="0%">
                          <stop offset="0%" stopColor="#38bdf8" />
                          <stop offset="55%" stopColor="#7dd3fc" />
                          <stop offset="100%" stopColor="#f59e0b" />
                        </linearGradient>
                      </defs>
                      <path d="M 0 104 L 320 104" className="behavior-console__replay-gridline" />
                      <path d="M 0 60 L 320 60" className="behavior-console__replay-gridline is-mid" />
                      {replayPath ? <path d={replayPath} className="behavior-console__replay-line" /> : null}
                    </svg>
                    <div className="behavior-console__replay-axis">
                      <span>{replay[0] ? formatRelativeTime(replay[0].frame_timestamp) : "--"}</span>
                      <span>{replay[Math.max(0, replay.length - 1)] ? formatRelativeTime(replay[Math.max(0, replay.length - 1)].frame_timestamp) : "--"}</span>
                    </div>
                  </div>
                  <div className="behavior-console__replay-metrics">
                    <div className="behavior-console__replay-insight-pill">
                      <span>Avg confidence</span>
                      <strong>{formatPercent(replayAverageConfidence, 0)}</strong>
                    </div>
                    <div className="behavior-console__replay-insight-pill">
                      <span>Peak country</span>
                      <strong>{replayPeak?.country || "--"}</strong>
                    </div>
                    <div className="behavior-console__replay-insight-pill">
                      <span>Peak severity</span>
                      <strong>{formatPercent(replayPeak?.severity_score, 0)}</strong>
                    </div>
                  </div>
                </article>

                <article className="behavior-console__replay-insights">
                  <div className="behavior-console__panel-header">
                    <div>
                      <span className="behavior-console__eyebrow">Replay context</span>
                      <h3>Operator cues</h3>
                    </div>
                  </div>
                  <div className="behavior-console__pill-grid behavior-console__pill-grid--compact">
                    <div className="behavior-console__pill">
                      <span>Tracked countries</span>
                      <strong>{replayCountryMix.length}</strong>
                    </div>
                    <div className="behavior-console__pill">
                      <span>Frames with evidence</span>
                      <strong>{replay.filter((item) => item.signal_count > 0).length}</strong>
                    </div>
                  </div>
                  <div className="behavior-console__chip-cloud">
                    {replayCountryMix.map((item) => (
                      <span key={item} className="behavior-console__chip">{item}</span>
                    ))}
                  </div>
                  <div className="behavior-console__chip-cloud">
                    {replaySourceHighlights.map(([key, value]) => (
                      <span key={key} className="behavior-console__chip is-guarded">
                        {titleCase(key)} {value}
                      </span>
                    ))}
                  </div>
                </article>
              </div>
              <div className="behavior-console__replay-grid">
                {replay.map((item) => (
                  <article key={item.frame_id} className={`behavior-console__replay-card ${toneClass(item.severity_score)}`}>
                    <div className="behavior-console__list-topline">
                      <strong>{item.country}</strong>
                      <span>{formatRelativeTime(item.frame_timestamp)}</span>
                    </div>
                    <div className="behavior-console__replay-score">{formatPercent(item.severity_score, 0)}</div>
                    <div className="behavior-console__list-meta">
                      <span>{item.signal_count} signals</span>
                      <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}
