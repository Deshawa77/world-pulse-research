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
      localStorage.setItem("user_type", res.user_type || "researcher");
      if (res.name) localStorage.setItem("name", res.name);
      if (res.email) localStorage.setItem("email", res.email);
      window.location.href = "/dashboard";
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Login failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ProposalAuthLayout
      eyebrow="Secure Access"
      title="Sign in to your intelligence workspace."
      subtitle="Access live dashboards, forecasting modules, and operational monitoring from one secure console."
      bullets={[
        "Role-based authentication controls access to sensitive analytics and administration workflows.",
        "Session-based access keeps monitoring, prediction, and alerting tools within trusted user boundaries.",
        "Designed for fast entry into live operational views without compromising security.",
      ]}
      metrics={[
        { label: "Access Model", value: "Role-based" },
        { label: "Data Mode", value: "Live + Historical" },
        { label: "Workspace", value: "Operational" },
      ]}
    >
      <h2>Sign in</h2>
      <p>Use your registered credentials to enter the platform.</p>
      {error ? <div className="proposal-auth-error">{error}</div> : null}
      <form className="proposal-contact-form" onSubmit={handleSubmit}>
        <label>Email address<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Enter your email" required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password" required /></label>
        <div className="proposal-form-actions"><button type="submit" className="proposal-button proposal-button-primary" disabled={loading}>{loading ? "Authenticating" : "Sign in"}</button></div>
      </form>
      <div className="proposal-auth-links"><Link to="/register">Create account</Link><Link to="/forgot-password">Forgot password?</Link></div>
    </ProposalAuthLayout>
  );
}


