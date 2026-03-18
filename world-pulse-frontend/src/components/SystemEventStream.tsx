import type { CSSProperties } from "react";

type SystemEventPacket = {
  id: string;
  timestamp: string;
  category: string;
  source: string;
  detail: string;
  status: string;
};

type Props = {
  packets: SystemEventPacket[];
  stale: boolean;
  style?: CSSProperties;
};

function formatStamp(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Unknown time";
  return date.toLocaleTimeString();
}

export default function SystemEventStream({ packets, stale, style }: Props) {
  return (
    <article className="wp-card panel-frame operator-response-panel stream-panel" style={style}>
      <div className="panel-head analytics-panel-head analytics-panel-head-wide">
        <div>
          <div className="analytics-kicker">Telemetry</div>
          <h3>System Event Stream</h3>
        </div>
        <span className={`analytics-pill ${stale ? "is-warning" : ""}`}>{stale ? "Lag detected" : "Live feed"}</span>
      </div>
      <div className="panel-content operational-panel-content">
        <div className="operational-panel-intro">
          Ingestion events, source refreshes, websocket country updates, validation checkpoints, model refreshes, and pipeline status packets.
        </div>
        <div className="stream-list">
          {packets.length ? packets.map((packet) => (
            <div key={packet.id} className="stream-row">
              <div className="stream-row-copy">
                <strong>{packet.category}</strong>
                <span>{packet.detail}</span>
                <small>{packet.source} • {formatStamp(packet.timestamp)}</small>
              </div>
              <span className={`stream-status ${String(packet.status).toLowerCase().includes("degrad") || String(packet.status).toLowerCase().includes("stale") ? "is-pending" : "is-processed"}`}>{packet.status}</span>
            </div>
          )) : <div className="watchlist-empty">No telemetry packets available yet.</div>}
        </div>
      </div>
    </article>
  );
}
