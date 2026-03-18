import type { CountryDrilldownData, IntelligenceFeedItem } from "../services/api";
import AlertControls from "./AlertControls";
import EventLog, { type OperatorEvent } from "./EventLog";
import type { CountryWeatherSnapshot } from "../services/weather";
import RiskWaterfallChart from "./RiskWaterfallChart";
import TimeSeriesChart from "./TimeSeriesChart";

type Props = {
  open: boolean;
  loading: boolean;
  data: CountryDrilldownData | null;
  events?: OperatorEvent[];
  countryNews: IntelligenceFeedItem[];
  liveIncidents: string[];
  threatLabel: string;
  trendLabel: string;
  riskDelta: number;
  topDrivers: string[];
  forecast: {
    score: number;
    delta: number;
    confidence: number;
    horizonHours: number;
  };
  reliability: {
    status: string;
    freshSources: number;
    staleSources: number;
    confidence: number;
    uncertainty: number;
    coverage: string;
  };
  weather: CountryWeatherSnapshot | null;
  weatherLoading: boolean;
  weatherError: string;
  onClose: () => void;
  onAcknowledge?: (comment: string) => void;
  onSnooze?: (comment: string) => void;
  onAssign?: (owner: string, comment: string) => void;
  workflowEnabled?: boolean;
};

function trendTone(value: number): "up" | "down" | "stable" {
  if (value >= 0.35) return "up";
  if (value <= -0.35) return "down";
  return "stable";
}

function riskBand(score: number): string {
  if (score >= 75) return "high";
  if (score >= 50) return "elevated";
  if (score >= 25) return "guarded";
  return "low";
}

function cleanDriverLabel(label: string): string {
  return label.replace(/_/g, " ").replace(/\w/g, (char) => char.toUpperCase());
}

function driverReason(feature: string, contribution: number): string {
  const direction = contribution >= 0 ? "increasing pressure" : "reducing pressure";
  const key = feature.toLowerCase();
  if (key.includes("sentiment")) return `Narrative tone is ${direction}.`;
  if (key.includes("volatility")) return `Instability signals are ${direction}.`;
  if (key.includes("return")) return `Market movement is ${direction}.`;
  if (key.includes("weather")) return `Weather-linked anomalies are ${direction}.`;
  return `This factor is ${direction}.`;
}

function cleanIncident(value: string): string {
  const compact = String(value || "").trim();
  if (!compact) return "";
  return compact
    .replace(/^topic pressure\s*:?/i, "Signal detected:")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ");
}

export default function CountryDrilldown({
  open,
  loading,
  data,
  events,
  countryNews,
  liveIncidents,
  threatLabel,
  trendLabel,
  riskDelta,
  topDrivers,
  forecast,
  reliability,
  weather,
  weatherLoading,
  weatherError,
  onClose,
  onAcknowledge,
  onSnooze,
  onAssign,
  workflowEnabled = true,
}: Props) {
  if (!open) return null;

  const trend = Array.isArray(data?.trend) ? data.trend : [];
  const countryEvents = Array.isArray(data?.events) ? data.events : [];
  const drivers = Array.isArray(data?.drivers) ? data.drivers : [];
  const safeEvents = Array.isArray(events) ? events : [];

  const anomalies = countryEvents.slice(0, 3).map((event, index) => ({
    timestamp: event.timestamp,
    value: trend[Math.min(index, Math.max(0, trend.length - 1))]?.value ?? 50,
  }));

  const riskValue = Number(data?.risk);
  const risk = Number.isFinite(riskValue) ? riskValue : 0;

  const confidenceLowerValue = Number(data?.confidenceInterval?.lower);
  const confidenceUpperValue = Number(data?.confidenceInterval?.upper);
  const confidenceLower = Number.isFinite(confidenceLowerValue) ? confidenceLowerValue : Math.max(0, risk - 4);
  const confidenceUpper = Number.isFinite(confidenceUpperValue) ? confidenceUpperValue : Math.min(100, risk + 4);

  const sortedDrivers = [...drivers].sort((left, right) => Math.abs(right.contribution) - Math.abs(left.contribution));
  const driverLabels = topDrivers.length
    ? topDrivers.map(cleanDriverLabel)
    : sortedDrivers.map((driver) => cleanDriverLabel(driver.feature)).slice(0, 3);
  const trendMode = trendTone(riskDelta);

  const latestNews = countryNews.slice(0, 3);
  const latestEvents = countryEvents.slice(0, 3);
  const readableIncidents = liveIncidents
    .map(cleanIncident)
    .filter(Boolean)
    .slice(0, 3);

  const topHeadline = latestNews[0] ?? null;
  const remainingUpdates = [
    ...latestNews.slice(1).map((item) => ({
      key: `news-${item.id}`,
      label: item.headline,
      meta: `${item.source} - ${new Date(item.timestamp).toLocaleTimeString()}`,
    })),
    ...latestEvents.map((event) => ({
      key: `event-${event.id}`,
      label: event.title,
      meta: `${event.severity} severity - ${new Date(event.timestamp).toLocaleTimeString()}`,
    })),
    ...readableIncidents.map((incident) => ({
      key: `incident-${incident}`,
      label: incident,
      meta: "Live signal",
    })),
  ].slice(0, 6);

  const quickRead = `${data?.country ?? "This country"} is currently in a ${riskBand(risk)} risk band at ${risk.toFixed(1)} / 100, with a ${trendLabel.toLowerCase()} trend (${riskDelta >= 0 ? "+" : ""}${riskDelta.toFixed(2)}).`;
  const weatherObserved = weather?.observedAt ? new Date(weather.observedAt).toLocaleString() : "n/a";

  const implications = [
    {
      label: "Base case",
      text:
        forecast.delta >= 0.8
          ? "Risk may rise quickly in the next 24-48 hours if pressure compounds."
          : "Risk is likely to stay near current levels unless a new shock appears.",
    },
    {
      label: "Risk to watch",
      text:
        trendMode === "down"
          ? "Current signals suggest conditions are cooling, but continue monitoring headline events."
          : "Current signals suggest pressure is persistent, so watch for escalation triggers.",
    },
    {
      label: "Confidence note",
      text:
        reliability.status === "Degraded"
          ? "Confidence is lower due to stale inputs; verify critical decisions with fresh sources."
          : "Confidence is healthy with fresh data coverage.",
    },
  ];

  const summaryCards = [
    { label: "Risk Score", value: `${risk.toFixed(1)} / 100`, detail: threatLabel },
    { label: "Trend", value: `${trendLabel}`, detail: `${riskDelta >= 0 ? "+" : ""}${riskDelta.toFixed(2)} delta` },
    { label: "Forecast", value: `${forecast.score.toFixed(1)}`, detail: `${forecast.horizonHours}h outlook` },
    { label: "Trust", value: reliability.status, detail: `${(reliability.confidence * 100).toFixed(0)}% confidence` },
  ];

  return (
    <aside className="country-drilldown country-drilldown-analytics">
      <div className="country-drilldown-shell">
        <header className="country-drilldown-hero wp-card panel-frame analytics-hero-panel">
          <button type="button" className="country-drilldown-close country-drilldown-close-corner" onClick={onClose}>Close</button>
          <div className="analytics-panel-head analytics-panel-head-wide">
            <div>
              <span className="country-drilldown-eyebrow">Country Analytics</span>
              <h3>{data?.country ?? "Country Drilldown"}</h3>
            </div>
            <div className="country-drilldown-hero-actions">
              <span className="analytics-pill">Live focus</span>
            </div>
          </div>
          <div className="country-drilldown-subtitle">
            {loading ? "Refreshing country intelligence..." : quickRead}
          </div>
        </header>

        {data ? (
          <>
            <section className="country-drilldown-kpi-grid">
              {summaryCards.map((card) => (
                <article key={card.label} className="country-drilldown-kpi-card">
                  <span>{card.label}</span>
                  <strong>{card.value}</strong>
                  <small>{card.detail}</small>
                </article>
              ))}
            </section>

            <section className="country-drilldown-grid country-drilldown-grid-hero">
              <article className="country-analytics-card country-analytics-card-model">
                <div className="analytics-panel-head">
                  <h4>Country Signal Overview</h4>
                  <span className="analytics-pill">Live state</span>
                </div>
                <div className="country-drilldown-snapshot-grid">
                  <article className="country-drilldown-mini-card">
                    <span>Current Read</span>
                    <strong>{risk.toFixed(1)} / 100</strong>
                    <small>{quickRead}</small>
                  </article>
                  <article className={`country-drilldown-mini-card tone-${trendMode}`}>
                    <span>Live Trend</span>
                    <strong>{trendLabel}</strong>
                    <small>{riskDelta >= 0 ? "+" : ""}{riskDelta.toFixed(2)} delta with {threatLabel.toLowerCase()} pressure</small>
                  </article>
                  <article className="country-drilldown-mini-card">
                    <span>Latest Conditions</span>
                    <strong>{weather ? weather.conditionLabel : "Signal-only view"}</strong>
                    <small>{weather ? `${weather.temperatureC.toFixed(1)}C, humidity ${weather.humidityPct.toFixed(0)}%, wind ${weather.windSpeedKmh.toFixed(1)} km/h` : "Weather data temporarily unavailable."}</small>
                  </article>
                  <article className={`country-drilldown-mini-card tone-${trendMode}`}>
                    <span>Confidence Band</span>
                    <strong>{confidenceLower.toFixed(1)} - {confidenceUpper.toFixed(1)}</strong>
                    <small>{implications[2].text}</small>
                  </article>
                </div>
                <article className="country-drilldown-mini-card country-drilldown-headline-card">
                  <span>Headline Read</span>
                  <strong>{topHeadline?.headline ?? "No current headline in focus"}</strong>
                  <small>{topHeadline ? `${topHeadline.source} - ${new Date(topHeadline.timestamp).toLocaleTimeString()}` : "Awaiting latest country-specific signal"}</small>
                </article>
                <article className="country-drilldown-mini-card">
                  <span>Main Drivers</span>
                  <div className="drilldown-driver-chips">
                    {driverLabels.map((driver) => (
                      <span key={driver} className="drilldown-driver-chip">{driver}</span>
                    ))}
                  </div>
                </article>
              </article>

              <article className="country-analytics-card">
                <div className="analytics-panel-head">
                  <h4>Situation Overview</h4>
                  <span className="analytics-pill">Now</span>
                </div>
                <div className="drilldown-list">
                  {implications.map((line) => (
                    <div key={line.label} className="drilldown-list-row">
                      <strong>{line.label}</strong>
                      <span>{line.text}</span>
                    </div>
                  ))}
                  {remainingUpdates.map((item) => (
                    <div key={item.key} className="drilldown-list-row">
                      <strong>{item.label}</strong>
                      <span>{item.meta}</span>
                    </div>
                  ))}
                </div>
              </article>
            </section>

            <section className="country-drilldown-grid">
              <article className="country-analytics-card">
                <div className="analytics-panel-head">
                  <h4>Driver Attribution</h4>
                  <span className="analytics-pill">Why</span>
                </div>
                <RiskWaterfallChart
                  prevRisk={Math.max(0, risk - 1.8)}
                  currentRisk={risk}
                  items={sortedDrivers.slice(0, 8).map((driver) => ({ feature: cleanDriverLabel(driver.feature), delta: driver.contribution }))}
                  confidence={{ lower: confidenceLower, upper: confidenceUpper }}
                />
                <div className="drilldown-list">
                  {sortedDrivers.slice(0, 4).map((driver) => (
                    <div key={driver.feature} className="drilldown-list-row">
                      <strong>{cleanDriverLabel(driver.feature)}</strong>
                      <span>{driver.contribution >= 0 ? "Pushing risk up" : "Pulling risk down"} by {Math.abs(driver.contribution).toFixed(3)}. {driverReason(driver.feature, driver.contribution)}</span>
                    </div>
                  ))}
                </div>
              </article>

              <article className="country-analytics-card">
                <div className="analytics-panel-head">
                  <h4>Risk Timeline</h4>
                  <span className="analytics-pill">24h</span>
                </div>
                <TimeSeriesChart
                  title={`${data.country} risk stream`}
                  series={[{ name: "Risk", points: trend }]}
                  anomalies={anomalies}
                  thresholdBand={{ low: 35, high: 75 }}
                />
              </article>
            </section>

            <section className="country-drilldown-grid">
              <article className="country-analytics-card">
                <div className="analytics-panel-head">
                  <h4>Forward View</h4>
                  <span className="analytics-pill">24-72h</span>
                </div>
                <div className="country-kpis">
                  <span>Forecast {forecast.score.toFixed(1)} / 100</span>
                  <span>{forecast.horizonHours}h delta {forecast.delta >= 0 ? "+" : ""}{forecast.delta.toFixed(2)}</span>
                  <span>Confidence {(forecast.confidence * 100).toFixed(0)}%</span>
                </div>
                <div className="drilldown-list">
                  <div className="drilldown-list-row">
                    <strong>Most likely path</strong>
                    <span>{implications[0].text}</span>
                  </div>
                  <div className="drilldown-list-row">
                    <strong>Momentum read</strong>
                    <span>{implications[1].text}</span>
                  </div>
                  <div className="drilldown-list-row trigger-medium">
                    <strong>Escalation trigger</strong>
                    <span>Two new high-severity events in less than 6 hours.</span>
                  </div>
                  <div className="drilldown-list-row trigger-low">
                    <strong>Stabilization trigger</strong>
                    <span>Top risk drivers turn negative for multiple consecutive updates.</span>
                  </div>
                </div>
              </article>

              <article className="country-analytics-card">
                <div className="analytics-panel-head">
                  <h4>Trust And Conditions</h4>
                  <span className="analytics-pill">Coverage</span>
                </div>
                <div className="drilldown-list">
                  <div className="drilldown-list-row">
                    <strong>Data status</strong>
                    <span>{reliability.status}</span>
                  </div>
                  <div className="drilldown-list-row">
                    <strong>Fresh vs stale sources</strong>
                    <span>{reliability.freshSources} / {reliability.staleSources}</span>
                  </div>
                  <div className="drilldown-list-row">
                    <strong>Model confidence</strong>
                    <span>{(reliability.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="drilldown-list-row">
                    <strong>Uncertainty</strong>
                    <span>{reliability.uncertainty.toFixed(1)} points</span>
                  </div>
                  <div className="drilldown-list-row">
                    <strong>Weather status</strong>
                    <span>{weatherError || (weather ? weather.conditionLabel : "Weather temporarily unavailable")}</span>
                  </div>
                  <div className="drilldown-list-row">
                    <strong>Observed</strong>
                    <span>{weather ? `${weather.provider} - ${weatherObserved}` : weatherObserved}</span>
                  </div>
                  <div className="drilldown-list-row">
                    <strong>Conditions</strong>
                    <span>{weather ? `${weather.temperatureC.toFixed(1)}C, humidity ${weather.humidityPct.toFixed(0)}%, wind ${weather.windSpeedKmh.toFixed(1)} km/h` : "n/a"}</span>
                  </div>
                  <div className="drilldown-list-row">
                    <strong>Refresh state</strong>
                    <span>{weatherLoading ? "Updating now..." : "Auto-refresh every 90s"}</span>
                  </div>
                </div>
              </article>
            </section>

            <section className="country-analytics-card country-analytics-card-wide">
              <div className="analytics-panel-head">
                <h4>{workflowEnabled ? "Operator Actions" : "Response Workflow"}</h4>
                <span className="analytics-pill">Operations</span>
              </div>
              {workflowEnabled ? (
                <>
                  <AlertControls
                    onAcknowledge={onAcknowledge ?? (() => {})}
                    onSnooze={onSnooze ?? (() => {})}
                    onAssign={onAssign ?? (() => {})}
                  />
                  <EventLog events={safeEvents} />
                </>
              ) : (
                <p className="country-drilldown-ops-note">This drilldown is analytics-only on the dashboard. Use the Response Console for acknowledgements, assignments, and action tracking.</p>
              )}
            </section>
          </>
        ) : null}
      </div>
    </aside>
  );
}
