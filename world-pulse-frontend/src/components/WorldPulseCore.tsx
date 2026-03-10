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
    "world-pulse-brain-core",
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

  const cortexBands = Array.from({ length: 6 }, (_, index) => ({
    key: index,
    style: {
      "--cortex-offset": `${-6 + index * 2.6}%`,
      animationDelay: `${index * 0.15}s`,
    } as CSSProperties,
  }));

  const neuralLinks = [
    { key: "frontal-left", style: { "--link-left": "18%", "--link-top": "30%", "--link-width": "22%", "--link-rotate": "16deg", animationDelay: "0.08s" } as CSSProperties },
    { key: "temporal-left", style: { "--link-left": "22%", "--link-top": "49%", "--link-width": "18%", "--link-rotate": "-10deg", animationDelay: "0.24s" } as CSSProperties },
    { key: "bridge-upper", style: { "--link-left": "36%", "--link-top": "26%", "--link-width": "28%", "--link-rotate": "6deg", animationDelay: "0.14s" } as CSSProperties },
    { key: "bridge-center", style: { "--link-left": "34%", "--link-top": "43%", "--link-width": "32%", "--link-rotate": "-3deg", animationDelay: "0.18s" } as CSSProperties },
    { key: "bridge-lower", style: { "--link-left": "37%", "--link-top": "57%", "--link-width": "24%", "--link-rotate": "11deg", animationDelay: "0.34s" } as CSSProperties },
    { key: "frontal-right", style: { "--link-left": "60%", "--link-top": "31%", "--link-width": "19%", "--link-rotate": "-14deg", animationDelay: "0.26s" } as CSSProperties },
    { key: "temporal-right", style: { "--link-left": "58%", "--link-top": "51%", "--link-width": "18%", "--link-rotate": "12deg", animationDelay: "0.42s" } as CSSProperties },
  ];

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

      <div className="world-pulse-brain-stage">
        <div className="world-pulse-brain-halo world-pulse-brain-halo-outer" />
        <div className="world-pulse-brain-halo world-pulse-brain-halo-inner" />

        <div className="world-pulse-brain-shell">
          <div className="world-pulse-brain-hemisphere world-pulse-brain-hemisphere-left">
            {cortexBands.map((band) => (
              <span key={`left-${band.key}`} className="world-pulse-cortex-band" style={band.style} />
            ))}
          </div>

          <div className="world-pulse-brain-hemisphere world-pulse-brain-hemisphere-right">
            {cortexBands.map((band) => (
              <span key={`right-${band.key}`} className="world-pulse-cortex-band" style={band.style} />
            ))}
          </div>

          <div className="world-pulse-brain-midline" />
          <div className="world-pulse-brain-stem" />

          <div className="world-pulse-neural-links">
            {neuralLinks.map((link) => (
              <span key={link.key} className="world-pulse-neural-link" style={link.style} />
            ))}
          </div>

          <div className="world-pulse-network-cluster world-pulse-network-cluster-brain">
            {networkPoints.map((point) => (
              <span key={point.key} className={`world-pulse-network-point point-${point.key + 1}`} style={point.style} />
            ))}
          </div>

          <div className="world-pulse-brain-core-node">
            <div className="world-pulse-brain-core-ring" />
            <div className="world-pulse-brain-impulse" />
          </div>

          <div className="world-pulse-center-readout">
            <span className="world-pulse-center-label">Risk Score</span>
            <strong>{riskScore.toFixed(0)}</strong>
            <span className="world-pulse-center-trend">{trendLabel}</span>
          </div>
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
        <span>NEURAL HOLOGRAM</span>
        <strong>{threatLevel.toUpperCase()}</strong>
      </div>
    </div>
  );
}
