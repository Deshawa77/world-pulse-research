import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getActionPlan,
  getCausalExplanations,
  runCounterfactual,
  runPolicyReplay,
  type ActionPlanResponse,
  type CausalExplanationResponse,
  type CounterfactualResponse,
  type PolicyReplayResponse,
} from "../services/api";

interface CausalRiskNavigatorProps {
  className?: string;
  selectedCountry?: string | null;
  refreshInterval?: number;
}

const DEFAULT_SCENARIO: Record<string, number> = {
  news_sentiment: -0.1,
  crypto_volatility: -0.12,
  weather_anomaly: -0.08,
};

const DEFAULT_INTERVENTIONS = ["communications", "market_stabilization", "climate_prepositioning"];

export default function CausalRiskNavigator({
  className = "",
  selectedCountry = null,
  refreshInterval = 30000,
}: CausalRiskNavigatorProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<CausalExplanationResponse | null>(null);
  const [actionPlan, setActionPlan] = useState<ActionPlanResponse | null>(null);
  const [counterfactual, setCounterfactual] = useState<CounterfactualResponse | null>(null);
  const [policyReplay, setPolicyReplay] = useState<PolicyReplayResponse | null>(null);
  const [scenario, setScenario] = useState<Record<string, number>>(DEFAULT_SCENARIO);
  const [runningCounterfactual, setRunningCounterfactual] = useState(false);
  const [runningReplay, setRunningReplay] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const scopeLabel = selectedCountry ? `Country Focus: ${selectedCountry}` : "Global Scope";

  const fetchBase = useCallback(async () => {
    try {
      const [explainRes, actionRes] = await Promise.all([
        getCausalExplanations(selectedCountry ?? null),
        getActionPlan(selectedCountry ?? null, "online", 4),
      ]);
      setExplanation(explainRes);
      setActionPlan(actionRes);
      setError(null);
    } catch {
      setError("Failed to load causal navigator data");
    } finally {
      setLoading(false);
    }
  }, [selectedCountry]);

  useEffect(() => {
    setLoading(true);
    void fetchBase();

    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      void fetchBase();
    }, refreshInterval);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchBase, refreshInterval]);

  const topDrivers = explanation?.drivers ?? [];

  const runScenario = async () => {
    setRunningCounterfactual(true);
    try {
      const result = await runCounterfactual(scenario, selectedCountry ?? null);
      setCounterfactual(result);
      setError(null);
    } catch {
      setError("Failed to run counterfactual simulation");
    } finally {
      setRunningCounterfactual(false);
    }
  };

  const runReplay = async () => {
    setRunningReplay(true);
    try {
      const result = await runPolicyReplay(DEFAULT_INTERVENTIONS, selectedCountry ?? null, 30);
      setPolicyReplay(result);
      setError(null);
    } catch {
      setError("Failed to run policy replay");
    } finally {
      setRunningReplay(false);
    }
  };

  const scenarioEntries = useMemo(() => Object.entries(scenario), [scenario]);

  if (loading) {
    return (
      <div className={`causal-risk-navigator ${className}`} style={containerStyle}>
        <div style={headerStyle}>
          <span style={titleStyle}>Causal Risk Navigator</span>
          <span style={scopePillStyle}>{scopeLabel}</span>
        </div>
        <div style={loadingStyle}>Loading causal intelligence...</div>
      </div>
    );
  }

  return (
    <div className={`causal-risk-navigator ${className}`} style={containerStyle}>
      <div style={headerStyle}>
        <span style={titleStyle}>Causal Risk Navigator</span>
        <span style={scopePillStyle}>{scopeLabel}</span>
      </div>

      {error ? <div style={errorStyle}>{error}</div> : null}

      <div style={summaryGridStyle}>
        <div style={summaryCardStyle}>
          <span style={summaryLabelStyle}>Risk Score</span>
          <strong style={summaryValueStyle}>{explanation?.risk_score.toFixed(1) ?? "n/a"}</strong>
        </div>
        <div style={summaryCardStyle}>
          <span style={summaryLabelStyle}>Threat</span>
          <strong style={summaryValueStyle}>{explanation?.threat_level ?? "n/a"}</strong>
        </div>
        <div style={summaryCardStyle}>
          <span style={summaryLabelStyle}>Freshness</span>
          <strong style={summaryValueStyle}>
            {explanation?.data_freshness_minutes === null || explanation?.data_freshness_minutes === undefined
              ? "n/a"
              : `${explanation.data_freshness_minutes}m`}
          </strong>
        </div>
      </div>

      <div style={sectionStyle}>
        <div style={sectionTitleStyle}>Root Cause Drivers</div>
        <div style={driverListStyle}>
          {topDrivers.length === 0 ? <div style={mutedStyle}>No drivers available</div> : null}
          {topDrivers.slice(0, 5).map((driver) => (
            <div key={driver.feature} style={driverRowStyle}>
              <span style={driverNameStyle}>{driver.label}</span>
              <span style={driverMetaStyle}>impact {driver.impact.toFixed(3)}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={sectionStyle}>
        <div style={sectionTitleStyle}>Counterfactual Simulation</div>
        <div style={scenarioGridStyle}>
          {scenarioEntries.map(([feature, value]) => (
            <label key={feature} style={scenarioFieldStyle}>
              <span style={fieldLabelStyle}>{feature}</span>
              <input
                style={inputStyle}
                type="number"
                step="0.01"
                value={value}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setScenario((prev) => ({ ...prev, [feature]: Number.isFinite(next) ? next : 0 }));
                }}
              />
            </label>
          ))}
        </div>
        <button style={buttonStyle} onClick={runScenario} disabled={runningCounterfactual}>
          {runningCounterfactual ? "Running..." : "Run Counterfactual"}
        </button>
        {counterfactual ? (
          <div style={resultStyle}>
            Projected Risk {counterfactual.projected_risk_score.toFixed(1)} ({counterfactual.projected_risk_delta >= 0 ? "+" : ""}
            {counterfactual.projected_risk_delta.toFixed(2)})
          </div>
        ) : null}
      </div>

      <div style={sectionStyle}>
        <div style={sectionTitleStyle}>Action Recommender</div>
        <div style={driverListStyle}>
          {(actionPlan?.recommendations ?? []).slice(0, 4).map((item) => (
            <div key={`${item.feature}-${item.title}`} style={actionCardStyle}>
              <div style={driverNameStyle}>{item.title}</div>
              <div style={mutedStyle}>{item.action}</div>
              <div style={driverMetaStyle}>Expected reduction: {item.expected_risk_reduction.toFixed(2)}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={sectionStyle}>
        <div style={sectionTitleStyle}>Policy Replay</div>
        <button style={buttonStyle} onClick={runReplay} disabled={runningReplay}>
          {runningReplay ? "Running..." : "Run Policy Replay"}
        </button>
        {policyReplay ? (
          <div style={resultStyle}>
            Final Risk Delta {policyReplay.projected_delta >= 0 ? "+" : ""}
            {policyReplay.projected_delta.toFixed(2)}
          </div>
        ) : null}
      </div>
    </div>
  );
}

const containerStyle: React.CSSProperties = {
  background: "rgba(11, 18, 32, 0.74)",
  border: "1px solid rgba(14, 165, 233, 0.24)",
  borderRadius: "12px",
  padding: "14px",
  height: "100%",
  display: "flex",
  flexDirection: "column",
  gap: "10px",
  overflow: "auto",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "10px",
  paddingBottom: "10px",
  borderBottom: "1px solid rgba(14, 165, 233, 0.2)",
};

const titleStyle: React.CSSProperties = {
  color: "#dbeafe",
  fontSize: "14px",
  fontWeight: 700,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

const scopePillStyle: React.CSSProperties = {
  fontSize: "10px",
  color: "#7dd3fc",
  border: "1px solid rgba(125, 211, 252, 0.35)",
  borderRadius: "999px",
  padding: "4px 10px",
};

const loadingStyle: React.CSSProperties = {
  color: "#93c5fd",
  fontSize: "12px",
  padding: "18px 0",
};

const errorStyle: React.CSSProperties = {
  color: "#fda4af",
  fontSize: "11px",
};

const summaryGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
  gap: "8px",
};

const summaryCardStyle: React.CSSProperties = {
  border: "1px solid rgba(148, 163, 184, 0.2)",
  borderRadius: "8px",
  padding: "8px",
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const summaryLabelStyle: React.CSSProperties = {
  color: "rgba(191, 219, 254, 0.74)",
  fontSize: "10px",
  textTransform: "uppercase",
};

const summaryValueStyle: React.CSSProperties = {
  color: "#f8fafc",
  fontSize: "18px",
};

const sectionStyle: React.CSSProperties = {
  border: "1px solid rgba(148, 163, 184, 0.15)",
  borderRadius: "10px",
  padding: "10px",
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const sectionTitleStyle: React.CSSProperties = {
  color: "#e0f2fe",
  fontSize: "11px",
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  fontWeight: 700,
};

const driverListStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
};

const driverRowStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: "8px",
  padding: "6px 8px",
  borderRadius: "7px",
  background: "rgba(30, 41, 59, 0.45)",
};

const driverNameStyle: React.CSSProperties = {
  color: "#dbeafe",
  fontSize: "12px",
  fontWeight: 600,
};

const driverMetaStyle: React.CSSProperties = {
  color: "#7dd3fc",
  fontSize: "11px",
};

const mutedStyle: React.CSSProperties = {
  color: "rgba(191, 219, 254, 0.7)",
  fontSize: "11px",
};

const scenarioGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
  gap: "8px",
};

const scenarioFieldStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const fieldLabelStyle: React.CSSProperties = {
  fontSize: "10px",
  color: "rgba(186, 230, 253, 0.75)",
};

const inputStyle: React.CSSProperties = {
  minHeight: "30px",
  background: "rgba(15, 23, 42, 0.9)",
  border: "1px solid rgba(56, 189, 248, 0.28)",
  borderRadius: "6px",
  color: "#f8fafc",
  padding: "0 8px",
  fontSize: "11px",
};

const buttonStyle: React.CSSProperties = {
  minHeight: "32px",
  padding: "0 12px",
  borderRadius: "8px",
  border: "1px solid rgba(56, 189, 248, 0.35)",
  background: "rgba(12, 74, 110, 0.56)",
  color: "#dbeafe",
  fontSize: "11px",
  fontWeight: 700,
  cursor: "pointer",
  alignSelf: "flex-start",
};

const resultStyle: React.CSSProperties = {
  color: "#86efac",
  fontSize: "12px",
  fontWeight: 600,
};

const actionCardStyle: React.CSSProperties = {
  border: "1px solid rgba(148, 163, 184, 0.16)",
  borderRadius: "8px",
  padding: "8px",
  display: "flex",
  flexDirection: "column",
  gap: "6px",
};
