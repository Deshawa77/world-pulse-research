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

  const metrics = [
    { label: "Coverage", value: `${coverage.coverage_pct.toFixed(1)}%`, detail: `${coverage.verified} verified / ${coverage.total || 233}` },
    { label: "Freshness", value: `${(freshnessRatio * 100).toFixed(0)}%`, detail: `${freshSources} fresh / ${staleSources} stale` },
    { label: "Validation", value: validationStatus, detail: `Heartbeat ${heartbeatSec.toFixed(1)}s` },
    { label: "Model Drift", value: modelDrift.toFixed(2), detail: connectionState },
    { label: "Mood Confidence", value: `${(moodConfidence * 100).toFixed(0)}%`, detail: `Uncertainty +/- ${moodUncertainty.toFixed(1)}` },
    { label: "Forecast", value: `${(forecastConfidence * 100).toFixed(0)}%`, detail: reliabilityStatus },
  ];

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
        <div className="integrity-metric-grid">
          {metrics.map((metric) => (
            <div key={metric.label} className="integrity-metric-card">
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <small>{metric.detail}</small>
            </div>
          ))}
        </div>
        <div className="integrity-footnote">
          <span>No-data {coverage.no_data}</span>
          <span>Stale {coverage.stale}</span>
          <span>Fresh feeds {safeNumber(freshness.fresh_count, freshSources)}</span>
        </div>
      </div>
    </article>
  );
}
