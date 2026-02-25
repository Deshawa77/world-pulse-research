export type OperatorEvent = {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  comment?: string;
};

type Props = {
  events: OperatorEvent[];
};

export default function EventLog({ events }: Props) {
  return (
    <div className="event-log">
      {events.length === 0 ? <p>No operator actions yet.</p> : null}
      {events.slice(0, 30).map((evt) => (
        <div key={evt.id} className="event-log-row">
          <span>{new Date(evt.timestamp).toLocaleTimeString()}</span>
          <strong>{evt.action}</strong>
          <span>{evt.actor}</span>
          <span>{evt.comment ?? ""}</span>
        </div>
      ))}
    </div>
  );
}
