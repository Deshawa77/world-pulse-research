import { useState } from "react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import ScenarioEditor from "../components/ScenarioEditor";
import ScenarioResults from "../components/ScenarioResults";
import { runScenarioSimulation, type ScenarioResult, type ScenarioStep } from "../services/api";

export default function ScenarioStudio() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ScenarioResult | null>(null);

  const onRun = async (steps: ScenarioStep[]) => {
    setLoading(true);
    const output = await runScenarioSimulation(steps);
    setResult(output);
    setLoading(false);
  };

  return (
    <main className="wp-shell proposal-runtime-shell">
      <ConsoleNavigation
        title={<>SCENARIO <span>STUDIO</span></>}
        subtitle="What-if modeling for cross-domain human behavior and risk response."
      />

      <section className="proposal-runtime-intro">
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">Simulation purpose</span>
          <h2>Test how global behavior might shift before the event happens.</h2>
          <p>
            The proposal is not only about passive observation. Scenario Studio lets the team model sequence-based events and inspect how risk,
            sentiment, and operational interpretation could move.
          </p>
        </article>
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">Operator guidance</span>
          <div className="proposal-grid-2">
            <div className="proposal-mini-panel"><span>Inputs</span><strong>Multi-step triggers</strong></div>
            <div className="proposal-mini-panel"><span>Outputs</span><strong>Behavior and risk impact</strong></div>
          </div>
          <p>Use this page to test combined humanitarian, media, environmental, or market shocks without changing live production state.</p>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Scenario editor</span>
          <ScenarioEditor onRun={onRun} loading={loading} />
        </article>
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Scenario results</span>
          {result ? (
            <ScenarioResults result={result} />
          ) : (
            <div className="proposal-mini-panel">
              <span>Status</span>
              <strong>No simulation executed yet</strong>
              <p>Build a multi-step scenario on the left and run it to inspect predicted system behavior.</p>
            </div>
          )}
        </article>
      </section>
    </main>
  );
}
