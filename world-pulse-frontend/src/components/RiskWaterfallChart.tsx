type Item = {
  feature: string;
  delta: number;
};

type Props = {
  prevRisk: number;
  currentRisk: number;
  items: Item[];
  confidence: { lower: number; upper: number };
};

export default function RiskWaterfallChart({ prevRisk, currentRisk, items, confidence }: Props) {
  const bars = items.slice(0, 8);
  return (
    <div className="risk-waterfall">
      <div className="risk-waterfall-head">
        <span>Previous: {prevRisk.toFixed(2)}</span>
        <span>Current: {currentRisk.toFixed(2)}</span>
        <span>
          CI [{confidence.lower.toFixed(1)}, {confidence.upper.toFixed(1)}]
        </span>
      </div>
      <div className="risk-waterfall-ribbon">
        <div
          className="risk-waterfall-ribbon-fill"
          style={{
            left: `${Math.max(0, Math.min(100, confidence.lower))}%`,
            width: `${Math.max(2, Math.min(100, confidence.upper - confidence.lower))}%`,
          }}
        />
      </div>
      <div className="risk-waterfall-bars">
        {bars.map((x) => (
          <div key={x.feature} className="risk-waterfall-row">
            <span>{x.feature}</span>
            <div className="risk-waterfall-track">
              <div
                className={x.delta >= 0 ? "risk-waterfall-pos" : "risk-waterfall-neg"}
                style={{ width: `${Math.max(4, Math.min(100, Math.abs(x.delta) * 180))}%` }}
              />
            </div>
            <strong>{x.delta >= 0 ? "+" : ""}{x.delta.toFixed(3)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}
