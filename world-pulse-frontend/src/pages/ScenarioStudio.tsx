import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ScenarioEditor from "../components/ScenarioEditor";
import ScenarioResults from "../components/ScenarioResults";
import { runScenarioSimulation, type ScenarioResult, type ScenarioStep } from "../services/api";

export default function ScenarioStudio() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ScenarioResult | null>(null);

  const onRun = async (steps: ScenarioStep[]) => {
    setLoading(true);
    const out = await runScenarioSimulation(steps);
    setResult(out);
    setLoading(false);
  };

  return (
    <main className="wp-shell">
      <header className="wp-top">
        <div className="wp-burger"><span /><span /><span /></div>
        <div>
          <h1>SCENARIO <span>STUDIO</span></h1>
          <p>Multi-step what-if simulation</p>
        </div>
        <div className="wp-actions-inline">
          <button onClick={() => navigate("/dashboard")}>Back to Dashboard</button>
        </div>
      </header>
      <section className="wp-grid">
        <ScenarioEditor onRun={onRun} loading={loading} />
        <ScenarioResults result={result} />
      </section>
    </main>
  );
}
