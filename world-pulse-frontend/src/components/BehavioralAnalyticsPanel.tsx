import type { RiskMapPoint } from "../services/api";

type Snapshot = {
  timestamp: string;
  riskScore: number;
  moodScore: number;
  moodConfidence: number;
  moodUncertainty: number;
  moodVerifiedCountries: number;
  moodEligibleCountries: number;
  moodUsedCountries: number;
  moodExcludedCountries: number;
  forecastRiskScore: number | null;
  forecastRiskDelta: number;
  forecastConfidence: number;
  forecastHorizonHours: number;
  features: Record<string, number>;
  topics: string[];
};

type Props = {
  history: Snapshot[];
  rows: RiskMapPoint[];
  telemetryDrivers: string[];
  topTopic: string;
  riskDelta: number;
  globalRiskScore: number;
  globalMoodScore: number;
  forecastRiskDelta: number;
  incidentCount: number;
  coveragePct: number;
};

const REGION_GROUPS: Array<{ label: string; countries: string[] }> = [
  { label: "USA", countries: ["USA", "CAN", "MEX"] },
  { label: "Europe", countries: ["GBR", "FRA", "DEU", "ESP", "ITA", "POL", "NLD", "SWE", "NOR", "FIN", "UKR"] },
  { label: "Asia", countries: ["CHN", "IND", "JPN", "KOR", "IDN", "PAK", "BGD", "THA", "VNM", "PHL"] },
  { label: "Africa", countries: ["ZAF", "NGA", "EGY", "KEN", "ETH", "GHA", "MAR", "TUN", "DZA"] },
  { label: "Oceania", countries: ["AUS", "NZL"] },
];

function deriveStabilityLabel(riskDelta: number, incidentCount: number, coveragePct: number) {
  if (Math.abs(riskDelta) >= 4 || incidentCount >= 8) return "Regime shift";
  if (Math.abs(riskDelta) >= 2 || coveragePct < 60) return "Volatile";
  if (Math.abs(riskDelta) >= 0.75) return "Guarded";
  return "Stable";
}

export default function BehavioralAnalyticsPanel({
  history,
  rows,
  telemetryDrivers,
  topTopic,
  riskDelta,
  globalRiskScore,
  globalMoodScore,
  forecastRiskDelta,
  incidentCount,
  coveragePct,
}: Props) {
  const verifiedRows = rows.filter((row): row is RiskMapPoint & { risk: number } => typeof row.risk === "number");
  const stableCount = verifiedRows.filter((row) => row.risk < 35).length;
  const guardedCount = verifiedRows.filter((row) => row.risk >= 35 && row.risk < 60).length;
  const elevatedCount = verifiedRows.filter((row) => row.risk >= 60).length;
  const totalSignals = Math.max(1, stableCount + guardedCount + elevatedCount);
  const stablePct = Math.round((stableCount / totalSignals) * 100);
  const guardedPct = Math.round((guardedCount / totalSignals) * 100);
  const elevatedPct = Math.max(0, 100 - stablePct - guardedPct);
  const donutStyle = {
    background: `conic-gradient(#1ec88b 0 ${stablePct}%, #ef4444 ${stablePct}% ${stablePct + elevatedPct}%, #94a3b8 ${stablePct + elevatedPct}% 100%)`,
  };

  const regionImpact = REGION_GROUPS.map((region) => {
    const members = verifiedRows.filter((row) => region.countries.includes(row.country));
    const averageRisk = members.length
      ? members.reduce((sum, row) => sum + row.risk, 0) / members.length
      : 0;
    return { label: region.label, score: Math.round(averageRisk) };
  });

  const recent = history.slice(-6);
  const averageRisk = recent.length
    ? recent.reduce((sum, item) => sum + item.riskScore, 0) / recent.length
    : globalRiskScore;
  const momentumLabel = forecastRiskDelta >= 1.5 ? "Accelerating" : forecastRiskDelta <= -1.5 ? "Cooling" : "Balanced";
  const stabilityLabel = deriveStabilityLabel(riskDelta, incidentCount, coveragePct);

  return (
    <article className="wp-card panel-frame operational-panel analytics-hero-panel">
      <div className="panel-head analytics-panel-head analytics-panel-head-wide">
        <div>
          <div className="analytics-kicker">Global Analytics</div>
          <h3>Behavior Intelligence Overview</h3>
        </div>
        <span className="analytics-pill">Last 24 hours</span>
      </div>
      <div className="panel-content operational-panel-content">
        <div className="analytics-hero-grid">
          <section className="analytics-visual-card">
            <div className="analytics-card-title">Sentiment Distribution</div>
            <div className="analytics-donut-stage">
              <div className="analytics-donut" style={donutStyle}>
                <div className="analytics-donut-core">
                  <strong>{globalMoodScore.toFixed(0)}</strong>
                  <span>Mood</span>
                </div>
              </div>
              <div className="analytics-donut-legend">
                <span><i className="tone-positive" />Stable {stablePct}%</span>
                <span><i className="tone-negative" />Elevated {elevatedPct}%</span>
                <span><i className="tone-neutral" />Guarded {guardedPct}%</span>
              </div>
            </div>
          </section>

          <section className="analytics-visual-card">
            <div className="analytics-card-title">Target Region Impact</div>
            <div className="analytics-bar-chart">
              {regionImpact.map((region) => (
                <div key={region.label} className="analytics-bar-group">
                  <div className="analytics-bar-track">
                    <div className="analytics-bar-fill" style={{ height: `${Math.max(region.score, 6)}%` }} />
                  </div>
                  <strong>{region.label}</strong>
                  <span>{region.score}</span>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="analytics-summary-strip">
          <div className="analytics-summary-item">
            <span>Top Narrative</span>
            <strong>{topTopic}</strong>
          </div>
          <div className="analytics-summary-item">
            <span>Trend Stability</span>
            <strong>{stabilityLabel}</strong>
          </div>
          <div className="analytics-summary-item">
            <span>Forward Momentum</span>
            <strong>{momentumLabel}</strong>
          </div>
          <div className="analytics-summary-item">
            <span>Average Load</span>
            <strong>{averageRisk.toFixed(1)} / 100</strong>
          </div>
        </div>

        <div className="analytics-driver-strip">
          <span>Driver Attribution</span>
          <div className="brain-telemetry-chip-list">
            {telemetryDrivers.map((driver) => (
              <span key={driver} className="brain-telemetry-chip">{driver}</span>
            ))}
          </div>
        </div>
      </div>
    </article>
  );
}
