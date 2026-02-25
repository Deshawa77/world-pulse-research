import { useEffect, useMemo, useState } from "react";

type Props = {
  incidents: string[];
  ingestionHeartbeatSec: number;
  modelDrift: number;
  connectionState: "connecting" | "connected" | "reconnecting" | "disconnected";
  lastUpdated: string;
};

function utcTimeString(now: Date): string {
  return now.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

export default function CommandCenterHeader({
  incidents,
  ingestionHeartbeatSec,
  modelDrift,
  connectionState,
  lastUpdated,
}: Props) {
  const [now, setNow] = useState(() => new Date());
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    const t = window.setInterval(() => {
      setIdx((v) => (incidents.length ? (v + 1) % incidents.length : 0));
    }, 2800);
    return () => window.clearInterval(t);
  }, [incidents.length]);

  const driftTone = useMemo(() => {
    if (modelDrift >= 0.65) return "high";
    if (modelDrift >= 0.35) return "medium";
    return "low";
  }, [modelDrift]);

  return (
    <section className="cc-header">
      <div className="cc-ticker">
        <strong>LIVE INCIDENTS</strong>
        <span>{incidents[idx] ?? "No active incidents"}</span>
      </div>
      <div className="cc-metrics">
        <span>{utcTimeString(now)}</span>
        <span>Heartbeat {ingestionHeartbeatSec.toFixed(1)}s</span>
        <span className={`cc-drift cc-drift-${driftTone}`}>Drift {modelDrift.toFixed(2)}</span>
        <span>Feed {connectionState}</span>
        <span>Updated {new Date(lastUpdated).toLocaleTimeString()}</span>
      </div>
    </section>
  );
}
