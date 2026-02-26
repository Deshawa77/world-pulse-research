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
        <div className="cc-heartbeat-mini">
          <svg viewBox="0 0 60 20" className="heartbeat-svg-mini">
            <path

              className="heartbeat-path-mini"
              d="M0,10 L15,10 L20,5 L25,15 L30,10 L35,10 L40,5 L45,15 L50,10 L60,10"
              fill="none"
              stroke="#00e0ff"
              strokeWidth="1.5"
            />
          </svg>
        </div>
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
