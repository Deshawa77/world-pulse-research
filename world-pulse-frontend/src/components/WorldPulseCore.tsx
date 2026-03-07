import type { CSSProperties } from "react";

interface WorldPulseCoreProps {
  isSpeaking?: boolean;
  isProcessing?: boolean;
  threatLevel?: "stable" | "guarded" | "elevated" | "critical";
  className?: string;
  riskScore?: number;
  riskTrend?: "increasing" | "decreasing" | "stable";
  signalCount?: number;
}

const THREAT_CLASS: Record<NonNullable<WorldPulseCoreProps["threatLevel"]>, string> = {
  stable: "is-stable",
  guarded: "is-guarded",
  elevated: "is-elevated",
  critical: "is-critical",
};

const DOMAIN_NODES = [
  { label: "News", className: "domain-news", style: { "--domain-x": "19%", "--domain-y": "24%" } as CSSProperties },
  { label: "Social", className: "domain-social", style: { "--domain-x": "79%", "--domain-y": "31%" } as CSSProperties },
  { label: "Markets", className: "domain-markets", style: { "--domain-x": "23%", "--domain-y": "77%" } as CSSProperties },
  { label: "Weather", className: "domain-weather", style: { "--domain-x": "76%", "--domain-y": "73%" } as CSSProperties },
];

export default function WorldPulseCore({
  isSpeaking = false,
  isProcessing = false,
  threatLevel = "stable",
  className = "",
  riskScore = 0,
  riskTrend = "stable",
  signalCount = 0,
}: WorldPulseCoreProps) {
  const rootClass = [
    "world-pulse-core",
    THREAT_CLASS[threatLevel],
    isSpeaking ? "is-speaking" : "",
    isProcessing ? "is-processing" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const signalBars = Array.from({ length: 10 }, (_, index) => ({
    key: index,
    style: {
      "--bar-index": index,
      "--bar-rotate": `${index * 36}deg`,
    } as CSSProperties,
  }));

  const networkPoints = Array.from({ length: 9 }, (_, index) => ({
    key: index,
    style: {
      "--point-delay": `${index * 0.16}s`,
    } as CSSProperties,
  }));

  const trendLabel =
    riskTrend === "increasing" ? "Rising" : riskTrend === "decreasing" ? "Cooling" : "Stable";

  return (
    <div className={rootClass}>
      <div className="world-pulse-grid" />
      <div className="world-pulse-radar-sweep" />
      <div className="world-pulse-orbit world-pulse-orbit-outer" />
      <div className="world-pulse-orbit world-pulse-orbit-mid" />
      <div className="world-pulse-orbit world-pulse-orbit-inner" />

      <div className="world-pulse-signal-ring">
        {signalBars.map((bar) => (
          <span key={bar.key} className="world-pulse-bar" style={bar.style} />
        ))}
      </div>

      <div className="world-pulse-connection-layer">
        <span className="world-pulse-connector connector-news" />
        <span className="world-pulse-connector connector-social" />
        <span className="world-pulse-connector connector-markets" />
        <span className="world-pulse-connector connector-weather" />
      </div>

      <div className="world-pulse-core-sphere">
        <div className="world-pulse-core-glow" />
        <div className="world-pulse-core-shield" />
        <div className="world-pulse-core-meridian world-pulse-core-meridian-a" />
        <div className="world-pulse-core-meridian world-pulse-core-meridian-b" />
        <div className="world-pulse-core-latitude world-pulse-core-latitude-a" />
        <div className="world-pulse-core-latitude world-pulse-core-latitude-b" />
        <div className="world-pulse-network-cluster">
          {networkPoints.map((point) => (
            <span key={point.key} className={`world-pulse-network-point point-${point.key + 1}`} style={point.style} />
          ))}
        </div>
        <div className="world-pulse-core-heartbeat" />
        <div className="world-pulse-center-readout">
          <span className="world-pulse-center-label">Risk Score</span>
          <strong>{riskScore.toFixed(0)}</strong>
          <span className="world-pulse-center-trend">{trendLabel}</span>
        </div>
      </div>

      <div className="world-pulse-domains">
        {DOMAIN_NODES.map((node) => (
          <div key={node.label} className={`world-pulse-domain-wrap ${node.className}`} style={node.style}>
            <span className="world-pulse-domain-dot" />
            <span className="world-pulse-domain">{node.label}</span>
          </div>
        ))}
      </div>

      <div className="world-pulse-metric-chip world-pulse-metric-chip-left">
        <span>Signals</span>
        <strong>{signalCount}</strong>
      </div>

      <div className="world-pulse-metric-chip world-pulse-metric-chip-right">
        <span>Trend</span>
        <strong>{trendLabel}</strong>
      </div>

      <div className="world-pulse-status-readout">
        <span>GLOBAL SIGNAL CORE</span>
        <strong>{threatLevel.toUpperCase()}</strong>
      </div>
    </div>
  );
}
