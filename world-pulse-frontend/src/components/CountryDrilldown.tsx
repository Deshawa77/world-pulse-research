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

  const trend = data?.trend ?? [];
  const anomalies = data?.events.slice(0, 3).map((e, i) => ({
    timestamp: e.timestamp,
    value: trend[Math.min(i, Math.max(0, trend.length - 1))]?.value ?? 50,
  })) ?? [];

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
            <span>Risk {data.risk.toFixed(2)}</span>
            <span>
              CI {data.confidenceInterval.lower.toFixed(1)} - {data.confidenceInterval.upper.toFixed(1)}
            </span>
          </div>

          <TimeSeriesChart
            title={`${data.country} risk stream`}
            series={[{ name: "Risk", points: trend }]}
            anomalies={anomalies}
            thresholdBand={{ low: 35, high: 75 }}
          />

          <RiskWaterfallChart
            prevRisk={Math.max(0, data.risk - 1.8)}
            currentRisk={data.risk}
            items={data.drivers.map((d) => ({ feature: d.feature, delta: d.contribution }))}
            confidence={data.confidenceInterval}
          />

          <h4>Recent events</h4>
          <div className="event-log">
            {data.events.map((evt) => (
              <div key={evt.id} className="event-log-row">
                <span>{new Date(evt.timestamp).toLocaleTimeString()}</span>
                <strong>{evt.title}</strong>
                <span>{evt.severity}</span>
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
