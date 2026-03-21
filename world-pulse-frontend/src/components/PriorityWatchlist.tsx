import { useMemo } from "react";
import type { CountryDrilldownData, IntelligenceFeedItem, RiskMapPoint } from "../services/api";

type Props = {
  rows: RiskMapPoint[];
  incidents: string[];
  feedItems: IntelligenceFeedItem[];
  selectedCountry: string | null;
  onSelectCountry: (country: string) => void;
  countryData?: CountryDrilldownData | null;
};

type SignalChip = {
  label: string;
  value: number;
};

type MetricBlock = {
  label: string;
  value: number;
};

type SpilloverLink = {
  country: string;
  label: string;
  risk: number;
  relationship: string;
};

type WatchRow = {
  country: string;
  label: string;
  risk: number;
  status: string;
  confidence: string;
  confidenceScore: number;
  freshnessScore: number;
  driver: string;
  incidentFlag: boolean;
  incidentText: string;
  rankingScore: number;
  momentum: number;
  evidenceCount: number;
  quality: string;
  watchReason: string;
  signalChips: SignalChip[];
  sourceCount: number;
  directBehavior: number;
  contextualPressure: number;
  warFlags: string[];
  operationalStress: MetricBlock[];
  posture: string;
  analystAction: "Monitor" | "Verify" | "Escalate";
  riskDelta24h: number;
  riskDelta7d: number;
  trendDirection: string;
  scoreChangeContributors: Array<{ feature: string; value: number; delta?: number; contribution?: number }>;
  spilloverLinks: SpilloverLink[];
};

function safeNumber(value: unknown, fallback = 0): number {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

const COUNTRY_NAMES: Record<string, string> = {
  USA: "United States",
  CAN: "Canada",
  MEX: "Mexico",
  BRA: "Brazil",
  ARG: "Argentina",
  GBR: "United Kingdom",
  FRA: "France",
  DEU: "Germany",
  ESP: "Spain",
  ITA: "Italy",
  RUS: "Russia",
  CHN: "China",
  IND: "India",
  JPN: "Japan",
  KOR: "South Korea",
  AUS: "Australia",
  ZAF: "South Africa",
  EGY: "Egypt",
  NGA: "Nigeria",
  TUR: "Turkey",
  SAU: "Saudi Arabia",
  IDN: "Indonesia",
  PAK: "Pakistan",
  UKR: "Ukraine",
  LKA: "Sri Lanka",
  DZA: "Algeria",
  IRN: "Iran",
  AFG: "Afghanistan",
  BGD: "Bangladesh",
  NPL: "Nepal",
  MMR: "Myanmar",
  THA: "Thailand",
  VNM: "Vietnam",
  MYS: "Malaysia",
  PHL: "Philippines",
  NZL: "New Zealand",
  NOR: "Norway",
  SWE: "Sweden",
  FIN: "Finland",
  POL: "Poland",
  NLD: "Netherlands",
  BEL: "Belgium",
  CHE: "Switzerland",
  AUT: "Austria",
  ISR: "Israel",
  IRQ: "Iraq",
  QAT: "Qatar",
  ARE: "United Arab Emirates",
  KWT: "Kuwait",
  KEN: "Kenya",
  ETH: "Ethiopia",
  GHA: "Ghana",
  MAR: "Morocco",
  TUN: "Tunisia",
  SGP: "Singapore",
  URY: "Uruguay",
  BOL: "Bolivia",
  CMR: "Cameroon",
  LBN: "Lebanon",
  JOR: "Jordan",
  SYR: "Syria",
  OMN: "Oman",
  AZE: "Azerbaijan",
  ARM: "Armenia",
  GEO: "Georgia",
};

function countryLabel(code: string): string {
  return COUNTRY_NAMES[code] ?? code;
}

function deriveStatus(risk: number, band?: string): string {
  const normalizedBand = String(band || "").trim().toLowerCase();
  if (normalizedBand === "critical") return "Critical";
  if (normalizedBand === "escalating") return "Escalating";
  if (normalizedBand === "elevated") return "Elevated";
  if (normalizedBand === "guarded") return "Guarded";
  if (risk >= 85) return "Critical";
  if (risk >= 70) return "Escalating";
  if (risk >= 55) return "Elevated";
  if (risk >= 35) return "Guarded";
  return "Stable";
}

function derivePosture(risk: number, momentum: number): string {
  if (risk >= 85 || momentum >= 72) return "Immediate analyst attention";
  if (risk >= 70 || momentum >= 56) return "Escalation building";
  if (risk >= 55 || momentum >= 42) return "Close monitoring required";
  return "Routine watch posture";
}

function deriveConfidence(row: RiskMapPoint): { label: string; score: number } {
  const canonicalScore = safeNumber(row.confidence_score, NaN);
  if (Number.isFinite(canonicalScore)) {
    if (row.gating_action === "suppress") return { label: "Withheld", score: canonicalScore };
    if (row.gating_action === "downgrade") return { label: "Downgraded", score: canonicalScore };
    if (row.source_status === "verified_live") return { label: "Verified", score: canonicalScore };
    if (row.source_status === "stale_observation") return { label: "Stale", score: canonicalScore };
    if (row.source_status === "derived_estimate") return { label: "Estimated", score: canonicalScore };
    return { label: "Partial", score: canonicalScore };
  }
  const evidence = safeNumber(row.evidence_quality_score, row.validated_today ? 78 : 48);
  const freshness = safeNumber(row.external_signal_freshness) * 100;
  const score = Math.max(8, Math.min(100, (evidence * 0.68) + (freshness * 0.32)));
  if (row.validated_today) return { label: "Verified", score };
  if (row.data_quality === "synthetic") return { label: "Synthetic", score };
  if (row.data_quality === "stale") return { label: "Stale", score };
  return { label: "Partial", score };
}

function toneClass(risk: number): string {
  if (risk >= 75) return "tone-critical";
  if (risk >= 55) return "tone-elevated";
  if (risk >= 35) return "tone-guarded";
  return "tone-stable";
}

function analystAction(row: RiskMapPoint, risk: number, momentum: number, confidenceScore: number, sourceCount: number, incidentFlag: boolean): WatchRow["analystAction"] {
  if ((row.war_state_rules ?? []).length || incidentFlag || risk >= 85 || momentum >= 70) return "Escalate";
  if (confidenceScore < 55 || sourceCount < 3 || safeNumber(row.external_signal_freshness) < 0.45 || row.data_quality === "stale") return "Verify";
  return "Monitor";
}

function collectSignals(row: RiskMapPoint): SignalChip[] {
  return [
    { label: "Social unrest", value: safeNumber(row.social_unrest_score) * 100 },
    { label: "Public attention", value: safeNumber(row.public_attention_score) * 100 },
    { label: "Narrative velocity", value: safeNumber(row.narrative_velocity_score) * 100 },
    { label: "Coordination risk", value: safeNumber(row.coordination_risk_score) * 100 },
    { label: "Mobility disruption", value: safeNumber(row.mobility_disruption_score) * 100 },
    { label: "Logistics stress", value: safeNumber(row.logistics_stress_score) * 100 },
    { label: "Household stress", value: safeNumber(row.household_stress_score) * 100 },
    { label: "Fuel pressure", value: safeNumber(row.fuel_price_pressure) * 100 },
    { label: "Food pressure", value: safeNumber(row.food_price_pressure) * 100 },
    { label: "Labor stress", value: safeNumber(row.labor_stress_score) * 100 },
    { label: "FX pressure", value: safeNumber(row.fx_pressure_score) * 100 },
    { label: "Remittance stress", value: safeNumber(row.remittance_stress_score) * 100 },
    { label: "Energy stress", value: safeNumber(row.energy_stress_score) * 100 },
    { label: "Weather stress", value: safeNumber(row.weather_stress) * 100 },
  ].sort((left, right) => right.value - left.value);
}

function operationalStressBlocks(row: RiskMapPoint): MetricBlock[] {
  return [
    { label: "Mobility", value: safeNumber(row.mobility_disruption_score) * 100 },
    { label: "Logistics", value: safeNumber(row.logistics_stress_score) * 100 },
    { label: "Household", value: safeNumber(row.household_stress_score) * 100 },
    { label: "Fuel", value: safeNumber(row.fuel_price_pressure) * 100 },
    { label: "Food", value: safeNumber(row.food_price_pressure) * 100 },
    { label: "Labor", value: safeNumber(row.labor_stress_score) * 100 },
    { label: "FX", value: safeNumber(row.fx_pressure_score) * 100 },
    { label: "Energy", value: safeNumber(row.energy_stress_score) * 100 },
  ].filter((item) => item.value > 0).sort((left, right) => right.value - left.value);
}

function generateIncidentHeadline(country: string, driver: string, status: string, incidentText?: string): string {
  if (incidentText?.trim()) return incidentText;
  const name = countryLabel(country);
  switch (driver) {
    case "Social unrest":
      return `Major unrest reported in ${name}`;
    case "Weather stress":
      return `Weather stress intensifies across ${name}`;
    case "Public attention":
      return `Public attention surging across ${name}`;
    case "Narrative velocity":
      return `Narrative activity is accelerating across ${name}`;
    case "Coordination risk":
      return `Coordinated messaging risk is rising in ${name}`;
    case "Mobility disruption":
      return `Population movement disruption intensifies across ${name}`;
    case "Household stress":
      return `Household stress is building across ${name}`;
    case "Fuel pressure":
      return `Fuel price pressure is climbing across ${name}`;
    case "Food pressure":
      return `Food price pressure is climbing across ${name}`;
    case "Labor stress":
      return `Labor stress is intensifying across ${name}`;
    case "Logistics stress":
      return `Logistics stress is intensifying across ${name}`;
    case "FX pressure":
      return `Currency stress is intensifying across ${name}`;
    default:
      return `${status} pressure building in ${name}`;
  }
}

function findIncidentHeadline(country: string, incidents: string[]): string | undefined {
  const name = countryLabel(country).toLowerCase();
  const code = country.toLowerCase();
  return incidents.find((item) => {
    const normalized = item.toLowerCase();
    return normalized.includes(name) || normalized.includes(code);
  });
}

function findFeedHeadline(country: string, feedItems: IntelligenceFeedItem[]): string | undefined {
  return feedItems.find((item) => item.country === country)?.headline;
}

function watchReason(row: RiskMapPoint, incidentFlag: boolean): string {
  if (typeof row.advisory === "string" && row.advisory.trim()) return row.advisory;
  if (incidentFlag) return "Live incident linkage detected";
  if ((row.war_state_rules ?? []).length) return "Conflict escalation rules are active in the scoring chain";
  if (safeNumber(row.mobility_disruption_score) >= 0.55) return "Movement disruption is crossing operational thresholds";
  if (safeNumber(row.narrative_velocity_score) >= 0.55) return "Narrative activity is accelerating unusually fast";
  if (safeNumber(row.household_stress_score) >= 0.55 || safeNumber(row.food_price_pressure) >= 0.55) return "Household and price stress are compounding";
  if (safeNumber(row.evidence_quality_score) >= 75) return "High-confidence multi-domain signal cluster";
  return "Composite escalation pressure building";
}

function formatSignalValue(value: number): string {
  return `${Math.round(value)}`;
}

function metricDisplay(value: number | null | undefined): string {
  if (!Number.isFinite(Number(value))) return "--";
  return `${Number(value).toFixed(1)}`;
}

function deltaDisplay(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "Awaiting history";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}`;
}

function deltaToneClass(value: number | null): string {
  if (value === null || Math.abs(value) < 0.75) return "is-flat";
  return value > 0 ? "is-up" : "is-down";
}

function deriveTrendDeltas(countryData?: CountryDrilldownData | null): { delta24h: number | null; delta7d: number | null } {
  const trend = countryData?.trend ?? [];
  if (!trend.length) return { delta24h: null, delta7d: null };
  const latest = safeNumber(trend[trend.length - 1]?.value, safeNumber(countryData?.risk, 0));
  const previous = trend.length > 1 ? safeNumber(trend[trend.length - 2]?.value, latest) : latest;
  const earliest = safeNumber(trend[0]?.value, latest);
  return {
    delta24h: Number((latest - previous).toFixed(1)),
    delta7d: Number((latest - earliest).toFixed(1)),
  };
}

function deriveActionList(focusRow: WatchRow, deltas: { delta24h: number | null; delta7d: number | null }): string[] {
  const actions: string[] = [];
  if (focusRow.analystAction === "Escalate") actions.push("Escalate to live operator review and keep the country pinned in the workbench.");
  if (focusRow.analystAction === "Verify") actions.push("Verify collection freshness, source count, and incident linkage before taking action.");
  if (focusRow.analystAction === "Monitor") actions.push("Monitor for further signal acceleration across the next refresh cycles.");
  if ((deltas.delta24h ?? 0) >= 3 || (deltas.delta7d ?? 0) >= 6) actions.push("Score acceleration is material. Compare new pressure drivers against the previous interval.");
  if (focusRow.warFlags.length) actions.push("Conflict escalation rules are active. Watch for regional spillover and transport disruption.");
  if (focusRow.confidenceScore < 55) actions.push("Confidence is weaker than production target. Prioritize evidence validation before escalating externally.");
  return actions.slice(0, 4);
}

function deriveContributorList(focusRow: WatchRow, countryData?: CountryDrilldownData | null): Array<{ label: string; detail: string }> {
  if (focusRow.scoreChangeContributors.length) {
    return focusRow.scoreChangeContributors.map((driver) => ({
      label: String(driver.feature || "driver").replace(/_/g, " "),
      detail: `${safeNumber(driver.delta).toFixed(1)} delta at value ${safeNumber(driver.value).toFixed(2)}`,
    }));
  }

  if (countryData?.country === focusRow.country && Array.isArray(countryData.drivers) && countryData.drivers.length) {
    return [...countryData.drivers]
      .sort((left, right) => Math.abs(safeNumber(right.contribution)) - Math.abs(safeNumber(left.contribution)))
      .slice(0, 4)
      .map((driver) => ({
        label: String(driver.feature || "driver").replace(/_/g, " "),
        detail: `${safeNumber(driver.contribution).toFixed(1)} contribution from value ${safeNumber(driver.value).toFixed(2)}`,
      }));
  }

  return focusRow.signalChips.slice(0, 4).map((signal) => ({
    label: signal.label,
    detail: `${formatSignalValue(signal.value)} intensity in the current escalation mix`,
  }));
}

function deriveSpillovers(focusRow: WatchRow): SpilloverLink[] {
  return focusRow.spilloverLinks.slice(0, 4);
}

export default function PriorityWatchlist({ rows, incidents, feedItems, selectedCountry, onSelectCountry, countryData = null }: Props) {
  const incidentCountries = useMemo(() => new Set(
    incidents
      .map((item) => item.match(/\b[A-Z]{3}\b/)?.[0] ?? "")
      .filter(Boolean),
  ), [incidents]);

  const rankedRows: WatchRow[] = useMemo(() => rows
    .filter((row): row is RiskMapPoint & { risk: number } => typeof row.risk === "number" && row.gating_action !== "suppress")
    .map((row) => {
      const matchedFeedHeadline = findFeedHeadline(row.country, feedItems);
      const matchedIncident = findIncidentHeadline(row.country, incidents);
      const incidentFlag = incidentCountries.has(row.country) || Boolean(matchedIncident) || Boolean(matchedFeedHeadline);
      const risk = safeNumber(row.risk);
      const statusLabel = deriveStatus(risk, row.risk_band);
      const momentum =
        safeNumber(row.social_unrest_score) * 18 +
        safeNumber(row.public_attention_score) * 16 +
        safeNumber(row.narrative_velocity_score) * 14 +
        safeNumber(row.coordination_risk_score) * 12 +
        safeNumber(row.mobility_disruption_score) * 18 +
        safeNumber(row.logistics_stress_score) * 11 +
        safeNumber(row.household_stress_score) * 15 +
        safeNumber(row.fuel_price_pressure) * 9 +
        safeNumber(row.food_price_pressure) * 9 +
        safeNumber(row.labor_stress_score) * 11 +
        safeNumber(row.fx_pressure_score) * 10 +
        safeNumber(row.google_trends_pressure) * 14 +
        safeNumber(row.weather_stress) * 10 +
        safeNumber(row.direct_behavior_score) * 0.08 +
        safeNumber(row.contextual_pressure_score) * 0.06;
      const confidence = deriveConfidence(row);
      const freshnessScore = safeNumber(row.external_signal_freshness) * 100;
      const signals = collectSignals(row);
      const driver = signals[0]?.label ?? "Composite risk";
      const evidenceCount = signals.filter((signal) => signal.value >= 35).length;
      const sourceCount = Math.max(0, Math.round(safeNumber(row.source_count)));
      const directBehavior = safeNumber(row.direct_behavior_score);
      const contextualPressure = safeNumber(row.contextual_pressure_score);
      const warFlags = row.war_state_rules ?? [];
      const posture = derivePosture(risk, momentum);
      const action = analystAction(row, risk, momentum, confidence.score, sourceCount, incidentFlag);
      const riskDelta24h = safeNumber(row.risk_delta_24h);
      const riskDelta7d = safeNumber(row.risk_delta_7d);
      const trendDirection = String(row.risk_trend_direction || "stable");
      const scoreChangeContributors = Array.isArray(row.score_change_contributors) ? row.score_change_contributors : [];
      const spilloverLinks = Array.isArray(row.spillover_links)
        ? row.spillover_links
            .map((item) => ({
              country: String(item.country || "").toUpperCase(),
              label: countryLabel(String(item.country || "").toUpperCase()),
              risk: safeNumber(item.risk),
              relationship: String(item.relationship || "Regional spillover"),
            }))
            .filter((item) => item.country)
        : [];
      const rankingScore =
        risk +
        momentum +
        (incidentFlag ? 12 : 0) +
        (row.validated_today ? 5 : 0) +
        (confidence.score * 0.08) +
        (warFlags.length ? 8 : 0) +
        (sourceCount * 0.35) -
        (row.gating_action === "downgrade" ? 10 : 0);
      return {
        country: row.country,
        label: countryLabel(row.country),
        risk,
        status: statusLabel,
        confidence: confidence.label,
        confidenceScore: confidence.score,
        freshnessScore,
        driver,
        incidentFlag,
        incidentText: matchedFeedHeadline ?? generateIncidentHeadline(row.country, driver, statusLabel, matchedIncident),
        rankingScore,
        momentum,
        evidenceCount,
        quality: row.data_quality ?? (row.validated_today ? "verified" : "unknown"),
        watchReason: watchReason(row, incidentFlag),
        signalChips: signals.slice(0, 5),
        sourceCount,
        directBehavior,
        contextualPressure,
        warFlags,
        operationalStress: operationalStressBlocks(row).slice(0, 8),
        posture,
        analystAction: action,
        riskDelta24h,
        riskDelta7d,
        trendDirection,
        scoreChangeContributors,
        spilloverLinks,
      };
    })
    .sort((left, right) => right.rankingScore - left.rankingScore)
    .slice(0, 8), [rows, feedItems, incidents, incidentCountries]);

  const focusRow = rankedRows.find((row) => row.country === selectedCountry) ?? rankedRows[0] ?? null;
  const focusCountryData = focusRow && countryData?.country === focusRow.country ? countryData : null;
  const trendDeltas = deriveTrendDeltas(focusCountryData);
  const contributorList = focusRow ? deriveContributorList(focusRow, focusCountryData) : [];
  const spilloverLinks = focusRow ? deriveSpillovers(focusRow) : [];
  const actionList = focusRow ? deriveActionList(focusRow, trendDeltas) : [];
  const escalatingCount = rankedRows.filter((row) => row.risk >= 75).length;
  const incidentLinkedCount = rankedRows.filter((row) => row.incidentFlag).length;
  const averageMomentum = rankedRows.length
    ? rankedRows.reduce((sum, row) => sum + row.momentum, 0) / rankedRows.length
    : 0;
  const verifiedShare = rankedRows.length
    ? (rankedRows.filter((row) => row.confidence === "Verified").length / rankedRows.length) * 100
    : 0;
  const conflictTaggedCount = rankedRows.filter((row) => row.warFlags.length > 0).length;
  const averageFreshness = rankedRows.length
    ? rankedRows.reduce((sum, row) => sum + row.freshnessScore, 0) / rankedRows.length
    : 0;
  const escalateActionCount = rankedRows.filter((row) => row.analystAction === "Escalate").length;

  return (
    <article className="wp-card panel-frame operational-panel watchlist-panel watchlist-panel-rich">
      <div className="panel-head analytics-panel-head watchlist-panel-head-rich">
        <div>
          <h3>Escalation Console</h3>
          <p>Production triage for countries with the strongest live escalation signature, operational stress, incident linkage, and confidence state.</p>
        </div>
        <span className="analytics-pill">Production triage</span>
      </div>
      <div className="panel-content operational-panel-content watchlist-panel-content-rich">
        <div className="watchlist-summary-grid watchlist-summary-grid-expanded">
          <div className="watchlist-summary-card">
            <span>Escalating</span>
            <strong>{escalatingCount}</strong>
            <small>Countries already in the highest escalation band.</small>
          </div>
          <div className="watchlist-summary-card">
            <span>Incident-linked</span>
            <strong>{incidentLinkedCount}</strong>
            <small>Rows tied to live incident or feed evidence.</small>
          </div>
          <div className="watchlist-summary-card">
            <span>Conflict-tagged</span>
            <strong>{conflictTaggedCount}</strong>
            <small>Countries carrying active conflict escalation rules.</small>
          </div>
          <div className="watchlist-summary-card">
            <span>Escalate state</span>
            <strong>{escalateActionCount}</strong>
            <small>Rows that should be escalated immediately.</small>
          </div>
          <div className="watchlist-summary-card">
            <span>Avg momentum</span>
            <strong>{averageMomentum.toFixed(1)}</strong>
            <small>Composite escalation velocity across the ranked set.</small>
          </div>
          <div className="watchlist-summary-card">
            <span>Avg freshness</span>
            <strong>{averageFreshness.toFixed(0)}%</strong>
            <small>External signal freshness across the ranked set.</small>
          </div>
          <div className="watchlist-summary-card">
            <span>Verified share</span>
            <strong>{verifiedShare.toFixed(0)}%</strong>
            <small>Escalation rows with same-day verified country data.</small>
          </div>
        </div>

        <div className="watchlist-rich-layout">
          <div className="watchlist-rich-list" role="list" aria-label="Escalation watchlist">
            {rankedRows.map((row, index) => (
              <button
                key={row.country}
                type="button"
                className={`watchlist-rich-row ${selectedCountry === row.country ? "is-selected" : ""}`}
                onClick={() => onSelectCountry(row.country)}
              >
                <div className="watchlist-rich-row-head">
                  <div className="watchlist-rich-rank">#{index + 1}</div>
                  <div className="watchlist-rich-country">
                    <strong>{row.country}</strong>
                    <span>{row.label}</span>
                  </div>
                  <div className="watchlist-rich-badges">
                    <span className={`watchlist-status-pill ${toneClass(row.risk)}`}>{row.status}</span>
                    <span className="watchlist-confidence-pill">{row.confidence}</span>
                    <span className={`watchlist-action-pill watchlist-action-pill--${row.analystAction.toLowerCase()}`}>{row.analystAction}</span>
                    {row.incidentFlag ? <span className="watchlist-incident-pill">Incident-linked</span> : null}
                    {row.warFlags.length ? <span className="watchlist-war-pill">Conflict-tagged</span> : null}
                  </div>
                  <div className="watchlist-rich-score">
                    <strong>{row.risk.toFixed(1)}</strong>
                    <span>Risk</span>
                  </div>
                </div>
                <div className="watchlist-rich-meta-grid watchlist-rich-meta-grid-expanded">
                  <div>
                    <span>Primary driver</span>
                    <strong>{row.driver}</strong>
                  </div>
                  <div>
                    <span>Momentum</span>
                    <strong>{row.momentum.toFixed(1)}</strong>
                  </div>
                  <div>
                    <span>Direct behavior</span>
                    <strong>{row.directBehavior.toFixed(1)}</strong>
                  </div>
                  <div>
                    <span>Context pressure</span>
                    <strong>{row.contextualPressure.toFixed(1)}</strong>
                  </div>
                  <div>
                    <span>24h delta</span>
                    <strong className={`watchlist-delta ${deltaToneClass(row.riskDelta24h)}`}>{deltaDisplay(row.riskDelta24h)}</strong>
                  </div>
                  <div>
                    <span>7d delta</span>
                    <strong className={`watchlist-delta ${deltaToneClass(row.riskDelta7d)}`}>{deltaDisplay(row.riskDelta7d)}</strong>
                  </div>
                  <div>
                    <span>Freshness</span>
                    <strong>{row.freshnessScore.toFixed(0)}%</strong>
                  </div>
                  <div>
                    <span>Sources</span>
                    <strong>{row.sourceCount}</strong>
                  </div>
                  <div>
                    <span>Confidence</span>
                    <strong>{row.confidenceScore.toFixed(0)}%</strong>
                  </div>
                  <div>
                    <span>Evidence cluster</span>
                    <strong>{row.evidenceCount} active</strong>
                  </div>
                  <div>
                    <span>Spillovers</span>
                    <strong>{row.spilloverLinks.length}</strong>
                  </div>
                </div>
                <div className="watchlist-bar-track watchlist-bar-track-rich">
                  <div className={`watchlist-bar-fill ${toneClass(row.risk)}`} style={{ width: `${Math.min(100, Math.max(10, row.risk))}%` }} />
                </div>
                <div className="watchlist-signal-chip-row">
                  {row.signalChips.map((signal) => (
                    <span key={`${row.country}-${signal.label}`} className="watchlist-signal-chip">
                      <em>{signal.label}</em>
                      <strong>{formatSignalValue(signal.value)}</strong>
                    </span>
                  ))}
                </div>
                <div className="watchlist-rich-foot">
                  <span>{row.watchReason}</span>
                  <span>{row.incidentText}</span>
                </div>
              </button>
            ))}
            {!rankedRows.length ? <div className="watchlist-empty">Escalation console will populate when verified country signals arrive.</div> : null}
          </div>

          <aside className="watchlist-focus-panel">
            <div className="watchlist-focus-head">
              <span>Focused Country</span>
              <strong>{focusRow ? `${focusRow.country} ${focusRow.risk.toFixed(1)} / 100` : "Awaiting selection"}</strong>
            </div>
            {focusRow ? (
              <>
                <div className="watchlist-focus-grid watchlist-focus-grid-expanded">
                  <div className="watchlist-focus-card">
                    <span>Status</span>
                    <strong>{focusRow.status}</strong>
                    <small>{focusRow.posture}</small>
                  </div>
                  <div className="watchlist-focus-card">
                    <span>Primary action</span>
                    <strong>{focusRow.analystAction}</strong>
                    <small>Current operator state</small>
                  </div>
                  <div className="watchlist-focus-card">
                    <span>Confidence</span>
                    <strong>{focusRow.confidenceScore.toFixed(0)}%</strong>
                    <small>{focusRow.confidence}</small>
                  </div>
                  <div className="watchlist-focus-card">
                    <span>Freshness</span>
                    <strong>{focusRow.freshnessScore.toFixed(0)}%</strong>
                    <small>External signal recency</small>
                  </div>
                  <div className="watchlist-focus-card">
                    <span>24h delta</span>
                    <strong className={`watchlist-delta ${deltaToneClass(trendDeltas.delta24h)}`}>{deltaDisplay(trendDeltas.delta24h)}</strong>
                    <small>From the selected country risk trend</small>
                  </div>
                  <div className="watchlist-focus-card">
                    <span>7d delta</span>
                    <strong className={`watchlist-delta ${deltaToneClass(trendDeltas.delta7d)}`}>{deltaDisplay(trendDeltas.delta7d)}</strong>
                    <small>Net change across available history</small>
                  </div>
                  <div className="watchlist-focus-card">
                    <span>Direct behavior</span>
                    <strong>{focusRow.directBehavior.toFixed(1)}</strong>
                    <small>Observed public and behavioral intensity</small>
                  </div>
                  <div className="watchlist-focus-card">
                    <span>Context pressure</span>
                    <strong>{focusRow.contextualPressure.toFixed(1)}</strong>
                    <small>Economic, mobility, and environmental drag</small>
                  </div>
                </div>
                <div className="watchlist-focus-story">
                  <span>Why This Country Is Here</span>
                  <strong>{focusRow.watchReason}</strong>
                  <p>{focusRow.incidentText}</p>
                </div>
                <div className="watchlist-focus-signals">
                  <span>Why Score Changed</span>
                  <div className="watchlist-contributor-list">
                    {contributorList.map((item) => (
                      <div key={`${item.label}-${item.detail}`} className="watchlist-contributor-item">
                        <strong>{item.label}</strong>
                        <small>{item.detail}</small>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="watchlist-focus-signals">
                  <span>Dominant Signal Cluster</span>
                  <div className="watchlist-focus-signal-list">
                    {focusRow.signalChips.map((signal) => (
                      <div key={`focus-${signal.label}`} className="watchlist-focus-signal-item">
                        <span>{signal.label}</span>
                        <strong>{formatSignalValue(signal.value)}</strong>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="watchlist-focus-signals watchlist-focus-stress-panel">
                  <span>Operational Stress Blocks</span>
                  <div className="watchlist-ops-grid">
                    {focusRow.operationalStress.length ? focusRow.operationalStress.map((signal) => (
                      <div key={`ops-${signal.label}`} className="watchlist-ops-item">
                        <div>
                          <span>{signal.label}</span>
                          <strong>{formatSignalValue(signal.value)}</strong>
                        </div>
                        <div className="watchlist-ops-bar-track">
                          <div className="watchlist-ops-bar-fill" style={{ width: `${Math.min(100, Math.max(6, signal.value))}%` }} />
                        </div>
                      </div>
                    )) : <div className="watchlist-empty">No additional operational stress signals are active for this country.</div>}
                  </div>
                </div>
                <div className="watchlist-focus-signals watchlist-focus-collection-panel">
                  <span>Spillover And Collection State</span>
                  <div className="watchlist-collection-grid">
                    <div className="watchlist-collection-card">
                      <strong>{focusRow.incidentFlag ? "Linked" : "Clear"}</strong>
                      <small>Incident relationship</small>
                    </div>
                    <div className="watchlist-collection-card">
                      <strong>{focusRow.evidenceCount}</strong>
                      <small>Signals above alert threshold</small>
                    </div>
                    <div className="watchlist-collection-card">
                      <strong>{focusRow.warFlags.length ? focusRow.warFlags.length : 0}</strong>
                      <small>Conflict escalation rules</small>
                    </div>
                    <div className="watchlist-collection-card">
                      <strong>{focusRow.sourceCount}</strong>
                      <small>Live contributing sources</small>
                    </div>
                  </div>
                  {spilloverLinks.length ? (
                    <div className="watchlist-spillover-links">
                      {spilloverLinks.map((item) => (
                        <button key={`${focusRow.country}-${item.country}`} type="button" className="watchlist-spillover-chip" onClick={() => onSelectCountry(item.country)}>
                          <strong>{item.country} {metricDisplay(item.risk)}</strong>
                          <span>{item.relationship}</span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="watchlist-empty">No mapped neighboring-country links are currently active for this focus.</div>
                  )}
                  {focusRow.warFlags.length ? (
                    <div className="watchlist-war-flags">
                      {focusRow.warFlags.map((flag) => (
                        <span key={flag} className="watchlist-war-flag-chip">{flag}</span>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="watchlist-focus-signals watchlist-focus-actions-panel">
                  <span>Analyst Actions</span>
                  <div className="watchlist-action-list">
                    {actionList.map((item) => (
                      <div key={item} className="watchlist-action-item">{item}</div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="watchlist-empty">Select a row to inspect its escalation context.</div>
            )}
          </aside>
        </div>
      </div>
    </article>
  );
}
