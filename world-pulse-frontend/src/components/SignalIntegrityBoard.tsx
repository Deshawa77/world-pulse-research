import type { RiskMapCoverage, TrustReliabilitySnapshot } from "../services/api";

type Props = {
  coverage: RiskMapCoverage;
  trustSnapshot: TrustReliabilitySnapshot | null;
  connectionState: string;
  heartbeatSec: number;
  modelDrift: number;
  validationStatus: string;
  moodConfidence: number;
  moodUncertainty: number;
  forecastConfidence: number;
  qualityGateMessage: string;
  reliabilityStatus: string;
  freshSources: number;
  staleSources: number;
};

function safeNumber(value: unknown, fallback = 0): number {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function toneClass(value: number): string {
  if (value >= 75) return "tone-stable";
  if (value >= 50) return "tone-guarded";
  if (value >= 30) return "tone-elevated";
  return "tone-critical";
}

export default function SignalIntegrityBoard({
  coverage,
  trustSnapshot,
  connectionState,
  heartbeatSec,
  modelDrift,
  validationStatus,
  moodConfidence,
  moodUncertainty,
  forecastConfidence,
  qualityGateMessage,
  reliabilityStatus,
  freshSources,
  staleSources,
}: Props) {
  const freshness = (trustSnapshot?.data_freshness ?? {}) as Record<string, unknown>;
  const qualityGate = (trustSnapshot?.quality_gate ?? {}) as Record<string, unknown>;
  const qualityGateMetrics = (qualityGate.metrics ?? {}) as Record<string, unknown>;
  const freshnessRatio = safeNumber(qualityGateMetrics.freshness_ratio, coverage.coverage_pct / 100);
  const latestIngestion = String((trustSnapshot?.latest_ingestion as Record<string, unknown> | undefined)?.latest_success ?? "Live");

  const radialMetrics = [
    {
      label: "Coverage",
      value: clampPercent(coverage.coverage_pct),
      display: `${coverage.coverage_pct.toFixed(1)}%`,
      detail: `${coverage.verified} verified / ${coverage.total || 233}`,
    },
    {
      label: "Freshness",
      value: clampPercent(freshnessRatio * 100),
      display: `${(freshnessRatio * 100).toFixed(0)}%`,
      detail: `${freshSources} fresh / ${staleSources} stale`,
    },
    {
      label: "Forecast",
      value: clampPercent(forecastConfidence * 100),
      display: `${(forecastConfidence * 100).toFixed(0)}%`,
      detail: reliabilityStatus,
    },
  ];

  const moodGauge = clampPercent(moodConfidence * 100);
  const driftGauge = clampPercent(100 - Math.min(100, modelDrift * 35));
  const driftOffset = clampPercent(modelDrift * 35);

  return (
    <article className="wp-card panel-frame operational-panel integrity-board-panel">
      <div className="panel-head analytics-panel-head">
        <h3>System Integrity</h3>
        <span className="analytics-pill">Trust layer</span>
      </div>
      <div className="panel-content operational-panel-content">
        <div className="operational-panel-intro">
          {qualityGateMessage} Latest ingestion checkpoint: {latestIngestion}.
        </div>

        <div className="integrity-radial-grid">
          {radialMetrics.map((metric) => (
            <div key={metric.label} className="integrity-radial-card">
              <div className={`integrity-radial-ring ${toneClass(metric.value)}`} style={{ background: `conic-gradient(currentColor 0 ${metric.value}%, rgba(30,41,59,0.96) ${metric.value}% 100%)` }}>
                <div className="integrity-radial-core">
                  <strong>{metric.display}</strong>
                  <span>{metric.label}</span>
                </div>
              </div>
              <small>{metric.detail}</small>
            </div>
          ))}
        </div>

        <div className="integrity-gauge-grid">
          <div className="integrity-gauge-card">
            <div className="integrity-gauge-head">
              <span>Model Drift</span>
              <strong>{modelDrift.toFixed(2)}</strong>
            </div>
            <div className="integrity-gauge-track">
              <div className={`integrity-gauge-fill ${toneClass(driftGauge)}`} style={{ width: `${driftGauge}%` }} />
              <div className="integrity-gauge-marker" style={{ left: `${driftOffset}%` }} />
            </div>
            <small>{connectionState}</small>
          </div>

          <div className="integrity-gauge-card">
            <div className="integrity-gauge-head">
              <span>Mood Confidence</span>
              <strong>{(moodConfidence * 100).toFixed(0)}%</strong>
            </div>
            <div className="integrity-gauge-track">
              <div className={`integrity-gauge-fill ${toneClass(moodGauge)}`} style={{ width: `${moodGauge}%` }} />
            </div>
            <small>Uncertainty +/- {moodUncertainty.toFixed(1)}</small>
          </div>
        </div>

        <div className="integrity-status-strip">
          <div className="integrity-status-chip">
            <span>Validation</span>
            <strong>{validationStatus}</strong>
            <small>Heartbeat {heartbeatSec.toFixed(1)}s</small>
          </div>
          <div className="integrity-status-chip">
            <span>Feeds</span>
            <strong>{safeNumber(freshness.fresh_count, freshSources)}</strong>
            <small>No-data {coverage.no_data} • Stale {coverage.stale}</small>
          </div>
          <div className="integrity-status-chip">
            <span>Reliability</span>
            <strong>{reliabilityStatus}</strong>
            <small>{latestIngestion}</small>
          </div>
        </div>
      </div>
    </article>
  );
}
