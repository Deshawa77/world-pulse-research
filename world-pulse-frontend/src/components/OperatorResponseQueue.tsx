import type { OperatorEvent } from "./EventLog";

type Props = {
  events: OperatorEvent[];
  incidents: string[];
  selectedCountry: string | null;
  onSelectCountry: (country: string | null) => void;
  onAction: (action: "acknowledge" | "snooze" | "assign", comment: string, owner?: string) => void;
  stale: boolean;
};

type StreamRow = {
  id: string;
  label: string;
  detail: string;
  status: string;
};

export default function OperatorResponseQueue({
  events,
  incidents,
  selectedCountry,
  onSelectCountry,
  onAction,
  stale,
}: Props) {
  const streamRows: StreamRow[] = [
    ...incidents.slice(0, 5).map((incident, index) => ({
      id: `incident-${index}`,
      label: `Signal Packet #${1000 + index}`,
      detail: incident,
      status: "Pending",
    })),
    ...events.slice(0, 5).map((event) => ({
      id: event.id,
      label: `Operator ${event.action}`,
      detail: event.comment ?? `Action by ${event.actor}`,
      status: event.action === "assign" ? "Assigned" : "Processed",
    })),
  ].slice(0, 8);

  const counts = {
    acknowledge: events.filter((event) => event.action === "acknowledge").length,
    snooze: events.filter((event) => event.action === "snooze").length,
    assign: events.filter((event) => event.action === "assign").length,
  };

  return (
    <article className="wp-card panel-frame operator-response-panel stream-panel">
      <div className="panel-head analytics-panel-head analytics-panel-head-wide">
        <div>
          <div className="analytics-kicker">Operations</div>
          <h3>Raw Data Stream</h3>
        </div>
        <div className="stream-panel-actions">
          <span className={`analytics-pill ${stale ? "is-warning" : ""}`}>{stale ? "Stale" : "Processed live"}</span>
          {selectedCountry ? (
            <button type="button" className="operator-clear-focus" onClick={() => onSelectCountry(null)}>Clear {selectedCountry}</button>
          ) : null}
        </div>
      </div>
      <div className="panel-content operational-panel-content">
        <div className="stream-toolbar">
          <div className="operator-response-metrics">
            <span>Incidents {incidents.length}</span>
            <span>Ack {counts.acknowledge}</span>
            <span>Snoozed {counts.snooze}</span>
            <span>Assigned {counts.assign}</span>
          </div>
          <div className="operator-actions-row">
            <button type="button" onClick={() => onAction("acknowledge", "stream acknowledge")}>Acknowledge</button>
            <button type="button" onClick={() => onAction("snooze", "stream snooze")}>Snooze</button>
            <button type="button" onClick={() => onAction("assign", "stream assign", "analyst-1")}>Assign</button>
          </div>
        </div>
        <div className="stream-list">
          {streamRows.length ? streamRows.map((row) => (
            <div key={row.id} className="stream-row">
              <div className="stream-row-copy">
                <strong>{row.label}</strong>
                <span>{row.detail}</span>
              </div>
              <span className={`stream-status ${row.status === "Pending" ? "is-pending" : "is-processed"}`}>{row.status}</span>
            </div>
          )) : <div className="watchlist-empty">No live stream packets available yet.</div>}
        </div>
      </div>
    </article>
  );
}
