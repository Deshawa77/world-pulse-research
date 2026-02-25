import { useState } from "react";
import type { ScenarioStep } from "../services/api";

type Props = {
  onRun: (steps: ScenarioStep[]) => void;
  loading: boolean;
};

const BLANK: ScenarioStep = { label: "New step", marketShock: 0, sentimentShock: 0, weatherShock: 0 };

export default function ScenarioEditor({ onRun, loading }: Props) {
  const [steps, setSteps] = useState<ScenarioStep[]>([
    { label: "Market crash", marketShock: 20, sentimentShock: -10, weatherShock: 0 },
    { label: "Sentiment rebound", marketShock: -5, sentimentShock: 15, weatherShock: 0 },
  ]);

  const updateStep = (idx: number, patch: Partial<ScenarioStep>) => {
    setSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };

  return (
    <section className="wp-card">
      <h3>Scenario Editor</h3>
      {steps.map((s, i) => (
        <div key={`${s.label}-${i}`} className="scenario-row">
          <input value={s.label} onChange={(e) => updateStep(i, { label: e.target.value })} />
          <input type="number" value={s.marketShock} onChange={(e) => updateStep(i, { marketShock: Number(e.target.value) || 0 })} />
          <input type="number" value={s.sentimentShock} onChange={(e) => updateStep(i, { sentimentShock: Number(e.target.value) || 0 })} />
          <input type="number" value={s.weatherShock} onChange={(e) => updateStep(i, { weatherShock: Number(e.target.value) || 0 })} />
          <button onClick={() => setSteps((prev) => prev.filter((_, x) => x !== i))}>Delete</button>
        </div>
      ))}
      <div className="scenario-actions">
        <button onClick={() => setSteps((prev) => [...prev, BLANK])}>Add Step</button>
        <button onClick={() => onRun(steps)} disabled={loading}>
          {loading ? "Running..." : "Run Simulation"}
        </button>
      </div>
    </section>
  );
}
