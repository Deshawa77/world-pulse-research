import { useEffect, useState } from "react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import AlertControls from "../components/AlertControls";
import EventLog, { type OperatorEvent } from "../components/EventLog";
import "./Dashboard.css";

const EVENTS_KEY = "wp_v3_events";

function readStoredEvents(): OperatorEvent[] {
  try {
    const raw = localStorage.getItem(EVENTS_KEY);
    return raw ? (JSON.parse(raw) as OperatorEvent[]) : [];
  } catch {
    return [];
  }
}

export default function ResponseConsole() {
  const [events, setEvents] = useState<OperatorEvent[]>(() => readStoredEvents());

  useEffect(() => {
    localStorage.setItem(EVENTS_KEY, JSON.stringify(events.slice(0, 200)));
  }, [events]);

  const addEvent = (action: OperatorEvent["action"], comment?: string, owner = "ops-team") => {
    const evt: OperatorEvent = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      timestamp: new Date().toISOString(),
      actor: owner,
      action,
      comment,
    };
    setEvents((prev) => [evt, ...prev].slice(0, 200));
  };

  const counts = {
    acknowledge: events.filter((event) => event.action === "acknowledge").length,
    snooze: events.filter((event) => event.action === "snooze").length,
    assign: events.filter((event) => event.action === "assign").length,
  };

  return (
    <main className="wp-shell proposal-runtime-shell">
      <ConsoleNavigation
        title={<>RESPONSE <span>CONSOLE</span></>}
        subtitle="Secondary workflow surface for acknowledgements, assignment, and response tracking."
      />

      <section className="proposal-runtime-intro">
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">Workflow posture</span>
          <h2>Response operations separated from analytics</h2>
          <p>The main dashboard is now focused on live intelligence and telemetry. Workflow actions live here.</p>
        </article>
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">Action totals</span>
          <p>Acknowledged: <strong>{counts.acknowledge}</strong></p>
          <p>Snoozed: <strong>{counts.snooze}</strong></p>
          <p>Assigned: <strong>{counts.assign}</strong></p>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Dispatch controls</span>
          <AlertControls
            onAcknowledge={(comment) => addEvent("acknowledge", comment)}
            onSnooze={(comment) => addEvent("snooze", comment)}
            onAssign={(owner, comment) => addEvent("assign", comment, owner)}
          />
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Recent response activity</span>
          <EventLog events={events} />
        </article>
      </section>
    </main>
  );
}
