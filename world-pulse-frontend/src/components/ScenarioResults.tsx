import TimeSeriesChart from "./TimeSeriesChart";
import type { ScenarioResult } from "../services/api";

type Props = {
  result: ScenarioResult | null;
};

export default function ScenarioResults({ result }: Props) {
  if (!result) {
    return (
      <section className="wp-card">
        <h3>Scenario Results</h3>
        <p>Run a scenario to see side-by-side projected paths.</p>
      </section>
    );
  }

  return (
    <section className="wp-card">
      <h3>Scenario Results</h3>
      <TimeSeriesChart
        title="Baseline vs Scenario"
        series={[
          {
            name: "Baseline",
            points: result.timestamps.map((t, i) => ({ timestamp: t, value: result.baseline[i] ?? 0 })),
            color: "#56d6ff",
          },
          {
            name: "Scenario",
            points: result.timestamps.map((t, i) => ({ timestamp: t, value: result.scenario[i] ?? 0 })),
            color: "#f97316",
          },
        ]}
        thresholdBand={{ low: 35, high: 75 }}
      />
    </section>
  );
}
