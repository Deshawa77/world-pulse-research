import { useEffect, useState } from "react";
import axios from "axios";

const API_URL = "http://127.0.0.1:8000"; // make sure this matches your FastAPI port

interface HealthResponse {
  status: string;
  database: string;
  model_loaded: boolean;
}

interface RiskResponse {
  risk_score: number;
}

interface SummaryResponse {
  summary: string;
}

interface GlobalFeatures {
  version: number;
  timestamp: string;
  [key: string]: any;
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [risk, setRisk] = useState<RiskResponse | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [globalFeatures, setGlobalFeatures] = useState<GlobalFeatures | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchData = async () => {
    setLoading(true);
    setError(null);

    try {
      const headers = { "x-api-key": "super_secure_api_key" };

      const [healthRes, riskRes, summaryRes, featuresRes] = await Promise.all([
        axios.get(`${API_URL}/health`, { headers }),
        axios.get(`${API_URL}/risk_score`, { headers }),
        axios.get(`${API_URL}/summary`, { headers }),
        axios.get(`${API_URL}/features/global/latest`, { headers }),
      ]);

      setHealth(healthRes.data);
      setRisk(riskRes.data);
      setSummary(summaryRes.data);
      setGlobalFeatures(featuresRes.data);
    } catch (err: any) {
      console.error("API call failed:", err);
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) return <p>Loading dashboard data...</p>;
  if (error) return <p style={{ color: "red" }}>Error: {error}</p>;

  return (
    <div>
      <h1>World Pulse Dashboard</h1>

      <section>
        <h2>System Status</h2>
        <pre>{JSON.stringify(health, null, 2)}</pre>
      </section>

      <section>
        <h2>Global Risk Score</h2>
        <pre>{JSON.stringify(risk, null, 2)}</pre>
      </section>

      <section>
        <h2>Summary</h2>
        <pre>{JSON.stringify(summary, null, 2)}</pre>
      </section>

      <section>
        <h2>Latest Global Features</h2>
        <pre>{JSON.stringify(globalFeatures, null, 2)}</pre>
      </section>

      <button onClick={fetchData} style={{ marginTop: "20px" }}>
        Refresh
      </button>
    </div>
  );
}