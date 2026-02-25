import TimeSeriesChart from "./TimeSeriesChart";
import type { GovernanceData } from "../services/api";

type Props = {
  data: GovernanceData;
};

export default function ModelGovernance({ data }: Props) {
  return (
    <section className="model-governance">
      <h3>Model Governance</h3>
      <div className="gov-grid">
        <div>
          <h4>Per-model latency and calibration</h4>
          {data.models.map((m) => (
            <div key={m.name} className="gov-row">
              <span>{m.name}</span>
              <span>{m.latencyMs}ms</span>
              <span>Cal {m.calibration.toFixed(2)}</span>
              <span>{m.driftHint}</span>
            </div>
          ))}
        </div>
        <div>
          <h4>Disagreement matrix</h4>
          {data.disagreement.map((d) => (
            <div key={`${d.left}-${d.right}`} className="gov-row">
              <span>{d.left}</span>
              <span>{d.right}</span>
              <span>{d.value.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </div>
      <TimeSeriesChart
        title="Calibration trend"
        series={[
          {
            name: "Calibration",
            points: data.calibrationTrend.map((x) => ({ timestamp: x.timestamp, value: x.value * 100 })),
            color: "#a3e635",
          },
        ]}
        thresholdBand={{ low: 75, high: 95 }}
      />
    </section>
  );
}
