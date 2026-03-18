import type { RiskMapPoint } from "../services/api";

type Props = {
  rows: RiskMapPoint[];
  incidents: string[];
  selectedCountry: string | null;
  onSelectCountry: (country: string) => void;
};

type WatchRow = {
  country: string;
  risk: number;
  status: string;
  confidence: string;
  driver: string;
  incidentFlag: boolean;
};

function safeNumber(value: unknown, fallback = 0): number {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function deriveDriver(row: RiskMapPoint): string {
  const candidates = [
    { label: "Social unrest", value: safeNumber(row.social_unrest_score) },
    { label: "Narrative pressure", value: safeNumber(row.google_trends_pressure) },
    { label: "Weather stress", value: safeNumber(row.weather_stress) },
    { label: "Signal freshness", value: safeNumber(row.external_signal_freshness) },
  ].sort((left, right) => right.value - left.value);

  return candidates[0]?.value > 0 ? candidates[0].label : "Composite risk";
}

function deriveStatus(risk: number): string {
  if (risk >= 75) return "Escalating";
  if (risk >= 55) return "Elevated";
  if (risk >= 35) return "Guarded";
  return "Stable";
}

function deriveConfidence(row: RiskMapPoint): string {
  if (row.validated_today) return "Verified";
  if (row.data_quality === "synthetic") return "Synthetic";
  if (row.data_quality === "stale") return "Stale";
  return "Partial";
}

function toneClass(risk: number): string {
  if (risk >= 75) return "tone-critical";
  if (risk >= 55) return "tone-elevated";
  if (risk >= 35) return "tone-guarded";
  return "tone-stable";
}

export default function PriorityWatchlist({ rows, incidents, selectedCountry, onSelectCountry }: Props) {
  const incidentCountries = new Set(
    incidents
      .map((item) => item.match(/\b[A-Z]{3}\b/)?.[0] ?? "")
      .filter(Boolean)
  );

  const rankedRows: WatchRow[] = rows
    .filter((row): row is RiskMapPoint & { risk: number } => typeof row.risk === "number")
    .map((row) => {
      const incidentFlag = incidentCountries.has(row.country);
      const risk = safeNumber(row.risk);
      const momentum =
        safeNumber(row.social_unrest_score) * 18 +
        safeNumber(row.google_trends_pressure) * 14 +
        safeNumber(row.weather_stress) * 10;
      const rankingScore = risk + momentum + (incidentFlag ? 12 : 0) + (row.validated_today ? 5 : 0);
      return {
        country: row.country,
        risk,
        status: deriveStatus(risk),
        confidence: deriveConfidence(row),
        driver: deriveDriver(row),
        incidentFlag,
        rankingScore,
      };
    })
    .sort((left, right) => right.rankingScore - left.rankingScore)
    .slice(0, 7)
    .map(({ rankingScore: _rankingScore, ...row }) => row);

  return (
    <article className="wp-card panel-frame operational-panel watchlist-panel">
      <div className="panel-head analytics-panel-head">
        <h3>Priority Watchlist</h3>
        <span className="analytics-pill">Live triage</span>
      </div>
      <div className="panel-content operational-panel-content">
        <div className="operational-panel-intro">
          Highest-pressure countries shown as ranked escalation bars for faster analyst scanning.
        </div>
        <div className="watchlist-chart" role="list" aria-label="Priority watchlist chart">
          {rankedRows.map((row) => (
            <button
              key={row.country}
              type="button"
              className={`watchlist-chart-row ${selectedCountry === row.country ? "is-selected" : ""}`}
              onClick={() => onSelectCountry(row.country)}
            >
              <div className="watchlist-chart-head">
                <div className="watchlist-country-block">
                  <strong>{row.country}</strong>
                  <span>{row.driver}</span>
                </div>
                <div className="watchlist-chart-meta">
                  <span className={`watchlist-status-pill ${toneClass(row.risk)}`}>{row.status}</span>
                  <strong>{row.risk.toFixed(1)}</strong>
                </div>
              </div>
              <div className="watchlist-bar-track">
                <div className={`watchlist-bar-fill ${toneClass(row.risk)}`} style={{ width: `${Math.min(100, Math.max(8, row.risk))}%` }} />
              </div>
              <div className="watchlist-chart-foot">
                <span>{row.confidence}</span>
                <span>{row.incidentFlag ? "Live incident" : "No active incident"}</span>
              </div>
            </button>
          ))}
          {!rankedRows.length ? <div className="watchlist-empty">Watchlist will populate when verified country signals arrive.</div> : null}
        </div>
      </div>
    </article>
  );
}
