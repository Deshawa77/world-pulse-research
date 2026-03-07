import { useState } from "react";
import { Link } from "react-router-dom";
import { forgotPassword } from "../services/authService";
import { ProposalAuthLayout } from "../components/ProposalShell";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await forgotPassword(email);
      setToken(res.reset_token);
      setSuccess(true);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to process request. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ProposalAuthLayout
      eyebrow="Recovery"
      title="Restore access without losing operational continuity."
      subtitle="Password recovery is part of system reliability. Researchers and operators should be able to regain access quickly and securely."
      bullets={[
        "Recovery flows should be simple enough for non-technical users.",
        "Security still matters: reset access must stay tied to authenticated identity checks.",
        "The platform remains centered on reliability and continuity for monitoring work.",
      ]}
      metrics={[{ label: "Security", value: "Role aware" }, { label: "Goal", value: "Continuity" }, { label: "Data", value: "Protected" }]}
    >
      <h2>Password recovery</h2>
      <p>Request a reset token so you can return to the dashboard and analytics tools.</p>
      {error ? <div className="proposal-auth-error">{error}</div> : null}
      {success ? (
        <>
          <div className="proposal-auth-success">Reset initiated. Use the token below to set a new password.</div>
          <div className="proposal-note">{token}</div>
          <div className="proposal-auth-links"><Link to={`/reset-password?token=${token}`}>Proceed to reset password</Link><Link to="/login">Back to login</Link></div>
        </>
      ) : (
        <form className="proposal-contact-form" onSubmit={handleSubmit}>
          <label>Email address<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Enter your registered email" required /></label>
          <div className="proposal-form-actions"><button type="submit" className="proposal-button proposal-button-primary" disabled={loading}>{loading ? "Processing" : "Send reset token"}</button></div>
        </form>
      )}
    </ProposalAuthLayout>
  );
}
