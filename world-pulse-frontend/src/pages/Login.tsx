import { useState } from "react";
import { Link } from "react-router-dom";
import { login } from "../services/authService";
import { ProposalAuthLayout } from "../components/ProposalShell";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await login(email, password);
      if (!res.access_token) throw new Error("No access token received from server");
      localStorage.setItem("token", res.access_token);
      localStorage.setItem("role", res.role || "user");
      window.location.href = "/dashboard";
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Login failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ProposalAuthLayout
      eyebrow="Secure access"
      title="Enter the operations console."
      subtitle="Sign in to the platform that monitors global human behavior across social, news, financial, and environmental signals."
      bullets={[
        "Role-based access supports researchers, policymakers, students, and administrators.",
        "The dashboard is designed for live monitoring, historical evidence, and predictive interpretation.",
        "Authentication protects operational analytics, alert workflows, and system governance views.",
      ]}
      metrics={[{ label: "Latency target", value: "5-10s" }, { label: "Sources", value: "Cross-domain" }, { label: "Mode", value: "Live intelligence" }]}
    >
      <h2>Sign in</h2>
      <p>Use your registered account to access live dashboards, predictive intelligence, and scenario tools.</p>
      {error ? <div className="proposal-auth-error">{error}</div> : null}
      <form className="proposal-contact-form" onSubmit={handleSubmit}>
        <label>Email address<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Enter your email" required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password" required /></label>
        <div className="proposal-form-actions"><button type="submit" className="proposal-button proposal-button-primary" disabled={loading}>{loading ? "Authenticating" : "Enter dashboard"}</button></div>
      </form>
      <div className="proposal-auth-links"><Link to="/register">Create account</Link><Link to="/forgot-password">Forgot password?</Link></div>
    </ProposalAuthLayout>
  );
}
