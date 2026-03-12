import type { CountryDrilldownData } from "../services/api";
import AlertControls from "./AlertControls";
import EventLog, { type OperatorEvent } from "./EventLog";
import RiskWaterfallChart from "./RiskWaterfallChart";
import TimeSeriesChart from "./TimeSeriesChart";

type Props = {
  open: boolean;
  loading: boolean;
  data: CountryDrilldownData | null;
  events: OperatorEvent[];
  onClose: () => void;
  onAcknowledge: (comment: string) => void;
  onSnooze: (comment: string) => void;
  onAssign: (owner: string, comment: string) => void;
};

export default function CountryDrilldown({
  open,
  loading,
  data,
  events,
  onClose,
  onAcknowledge,
  onSnooze,
  onAssign,
}: Props) {
  if (!open) return null;

  const trend = Array.isArray(data?.trend) ? data.trend : [];
  const countryEvents = Array.isArray(data?.events) ? data.events : [];
  const drivers = Array.isArray(data?.drivers) ? data.drivers : [];

  const anomalies = countryEvents.slice(0, 3).map((event, index) => ({
    timestamp: event.timestamp,
    value: trend[Math.min(index, Math.max(0, trend.length - 1))]?.value ?? 50,
  }));

  const riskValue = Number(data?.risk);
  const risk = Number.isFinite(riskValue) ? riskValue : 0;

  const confidenceLowerValue = Number(data?.confidenceInterval?.lower);
  const confidenceUpperValue = Number(data?.confidenceInterval?.upper);
  const confidenceLower = Number.isFinite(confidenceLowerValue) ? confidenceLowerValue : 0;
  const confidenceUpper = Number.isFinite(confidenceUpperValue) ? confidenceUpperValue : 0;

  return (
    <aside className="country-drilldown">
      <header>
        <h3>Country Drilldown: {data?.country ?? "n/a"}</h3>
        <button onClick={onClose}>Close</button>
      </header>
      {loading ? <p>Loading country intelligence...</p> : null}
      {data ? (
        <>
          <div className="country-kpis">
            <span>Risk {risk.toFixed(2)}</span>
            <span>
              CI {confidenceLower.toFixed(1)} - {confidenceUpper.toFixed(1)}
            </span>
          </div>

          <TimeSeriesChart
            title={`${data.country} risk stream`}
            series={[{ name: "Risk", points: trend }]}
            anomalies={anomalies}
            thresholdBand={{ low: 35, high: 75 }}
          />

          <RiskWaterfallChart
            prevRisk={Math.max(0, risk - 1.8)}
            currentRisk={risk}
            items={drivers.map((driver) => ({ feature: driver.feature, delta: driver.contribution }))}
            confidence={{ lower: confidenceLower, upper: confidenceUpper }}
          />

          <h4>Recent events</h4>
          <div className="event-log">
            {countryEvents.map((event) => (
              <div key={event.id} className="event-log-row">
                <span>{new Date(event.timestamp).toLocaleTimeString()}</span>
                <strong>{event.title}</strong>
                <span>{event.severity}</span>
              </div>
            ))}
          </div>

          <AlertControls onAcknowledge={onAcknowledge} onSnooze={onSnooze} onAssign={onAssign} />
          <EventLog events={events} />
        </>
      ) : null}
    </aside>
  );
}
