import BrainModelViewer from "./BrainModelViewer";
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
  return label.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
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

  return (
    <aside className="country-drilldown country-drilldown-v2">
      <header className="country-drilldown-header">
        <h3>Country Drilldown: {data?.country ?? "n/a"}</h3>
        <button onClick={onClose}>Close</button>
      </header>

      {loading ? <p>Loading country intelligence...</p> : null}

      {data ? (
        <>
          <section className="drilldown-brain-section">
            <div className="drilldown-brain-view">
              <BrainModelViewer className="dashboard-brain-model" />
            </div>
            <div className="drilldown-country-telemetry">
              <article className="drilldown-telemetry-card">
                <span>Risk Score</span>
                <strong>{risk.toFixed(1)} / 100</strong>
              </article>
              <article className="drilldown-telemetry-card">
                <span>Threat Level</span>
                <strong>{threatLabel}</strong>
              </article>
              <article className={`drilldown-telemetry-card tone-${trendMode}`}>
                <span>Trend</span>
                <strong>{trendLabel} ({riskDelta >= 0 ? "+" : ""}{riskDelta.toFixed(2)})</strong>
              </article>
              <article className="drilldown-telemetry-card drilldown-drivers-card">
                <span>Main Drivers</span>
                <div className="drilldown-driver-chips">
                  {driverLabels.map((driver) => (
                    <span key={driver} className="drilldown-driver-chip">{driver}</span>
                  ))}
                </div>
              </article>
            </div>
          </section>

          <article className="drilldown-section-card drilldown-plain-summary">
            <h4>Quick Read (Plain English)</h4>
            <p>{quickRead}</p>
            <div className="drilldown-list">
              {implications.map((line) => (
                <div key={line.label} className="drilldown-list-row">
                  <strong>{line.label}</strong>
                  <span>{line.text}</span>
                </div>
              ))}
            </div>
          </article>

          <section className="drilldown-section-grid">
            <article className="drilldown-section-card">
              <h4>What Is Happening Right Now</h4>
              {topHeadline ? (
                <div className="drilldown-list-row">
                  <strong>Top headline now: {topHeadline.headline}</strong>
                  <span>{topHeadline.source} - {new Date(topHeadline.timestamp).toLocaleTimeString()}</span>
                </div>
              ) : null}
              <div className="drilldown-list">
                {remainingUpdates.map((item) => (
                  <div key={item.key} className="drilldown-list-row">
                    <strong>{item.label}</strong>
                    <span>{item.meta}</span>
                  </div>
                ))}
              </div>
            </article>

            <article className="drilldown-section-card">
              <h4>Live Weather (Latest)</h4>
              <div className="drilldown-list">
                <div className="drilldown-list-row">
                  <strong>Status</strong>
                  <span>{weatherError || (weather ? "Live" : "Live weather temporarily unavailable")}</span>
                </div>
                <div className="drilldown-list-row">
                  <strong>Current conditions</strong>
                  <span>{weather ? weather.conditionLabel : "Unavailable"}</span>
                </div>
                <div className="drilldown-list-row">
                  <strong>Temperature / feels like</strong>
                  <span>{weather ? `${weather.temperatureC.toFixed(1)}C / ${weather.feelsLikeC.toFixed(1)}C` : "n/a"}</span>
                </div>
                <div className="drilldown-list-row">
                  <strong>Wind / gusts</strong>
                  <span>{weather ? `${weather.windSpeedKmh.toFixed(1)} km/h / ${weather.windGustKmh.toFixed(1)} km/h` : "n/a"}</span>
                </div>
                <div className="drilldown-list-row">
                  <strong>Rain / precipitation</strong>
                  <span>{weather ? `${weather.rainMm.toFixed(2)} mm / ${weather.precipitationMm.toFixed(2)} mm` : "n/a"}</span>
                </div>
                <div className="drilldown-list-row">
                  <strong>Humidity / wind direction</strong>
                  <span>{weather ? `${weather.humidityPct.toFixed(0)}% / ${weather.windDirectionDeg.toFixed(0)} degrees` : "n/a"}</span>
                </div>
                <div className="drilldown-list-row">
                  <strong>Provider / observed at</strong>
                  <span>{weather ? `${weather.provider} / ${weatherObserved}` : weatherObserved}</span>
                </div>
                <div className="drilldown-list-row">
                  <strong>Refresh state</strong>
                  <span>{weatherLoading ? "Updating now..." : "Auto-refresh every 90s"}</span>
                </div>
              </div>
            </article>

            <article className="drilldown-section-card">
              <h4>Why The Risk Is Moving</h4>
              <RiskWaterfallChart
                prevRisk={Math.max(0, risk - 1.8)}
                currentRisk={risk}
                items={sortedDrivers
                  .slice(0, 8)
                  .map((driver) => ({ feature: cleanDriverLabel(driver.feature), delta: driver.contribution }))}
                confidence={{ lower: confidenceLower, upper: confidenceUpper }}
              />
              <div className="drilldown-list">
                {sortedDrivers.slice(0, 4).map((driver) => (
                  <div key={driver.feature} className="drilldown-list-row">
                    <strong>{cleanDriverLabel(driver.feature)}</strong>
                    <span>
                      {driver.contribution >= 0 ? "Pushing risk up" : "Pulling risk down"} by {Math.abs(driver.contribution).toFixed(3)}. {driverReason(driver.feature, driver.contribution)}
                    </span>
                  </div>
                ))}
              </div>
            </article>
          </section>

          <section className="drilldown-section-grid">
            <article className="drilldown-section-card">
              <h4>What May Happen Next (24-72h)</h4>
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
              </div>
            </article>

            <article className="drilldown-section-card">
              <h4>How Much You Can Trust This</h4>
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
              </div>
            </article>
          </section>

          <section className="drilldown-section-grid">
            <article className="drilldown-section-card">
              <h4>What To Watch</h4>
              <div className="drilldown-list">
                <div className="drilldown-list-row trigger-medium">
                  <strong>Escalation trigger</strong>
                  <span>Two new high-severity events in less than 6 hours.</span>
                </div>
                <div className="drilldown-list-row trigger-medium">
                  <strong>Data trust trigger</strong>
                  <span>Stale sources exceed fresh sources for this country.</span>
                </div>
                <div className="drilldown-list-row trigger-low">
                  <strong>Stabilization trigger</strong>
                  <span>Top risk drivers turn negative for multiple consecutive updates.</span>
                </div>
              </div>
            </article>

            <article className="drilldown-section-card">
              <h4>Risk Timeline (Last 24h)</h4>
              <TimeSeriesChart
                title={`${data.country} risk stream`}
                series={[{ name: "Risk", points: trend }]}
                anomalies={anomalies}
                thresholdBand={{ low: 35, high: 75 }}
              />
            </article>
          </section>

          <section className="drilldown-section-card">
            {workflowEnabled ? (<>
              <h4>Operator Actions</h4>
              <AlertControls
                onAcknowledge={onAcknowledge ?? (() => {})}
                onSnooze={onSnooze ?? (() => {})}
                onAssign={onAssign ?? (() => {})}
              />
              <EventLog events={safeEvents} />
            </>) : (<>
              <h4>Response Workflow</h4>
              <p>This drilldown is analytics-only on the dashboard. Use the Response Console for acknowledgements, assignments, and action tracking.</p>
            </>)}
          </section>
        </>
      ) : null}
    </aside>
  );
}












