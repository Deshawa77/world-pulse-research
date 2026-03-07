import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { resetPassword } from "../services/authService";
import { ProposalAuthLayout } from "../components/ProposalShell";

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [token, setToken] = useState(searchParams.get("token") || "");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (newPassword !== confirmPassword) return setError("Passwords do not match.");
    if (newPassword.length < 6) return setError("Password must be at least 6 characters.");
    setLoading(true);
    try {
      await resetPassword(token, newPassword);
      setSuccess(true);
      setTimeout(() => navigate("/login"), 1800);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to reset password. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ProposalAuthLayout
      eyebrow="Credential reset"
      title="Set a new password and return to the live system."
      subtitle="This step restores access to real-time dashboards, historical analysis, and predictive operations without breaking the security boundary."
      bullets={[
        "Reset flows should stay understandable for students and operational users alike.",
        "Security and usability have to coexist on every page, including recovery.",
        "Reliable access matters because the platform is designed for continuous monitoring.",
      ]}
      metrics={[{ label: "Access", value: "Recovered" }, { label: "Mode", value: "Secure reset" }, { label: "Return path", value: "Dashboard" }]}
    >
      <h2>Reset password</h2>
      <p>Provide the reset token and a new password for your account.</p>
      {error ? <div className="proposal-auth-error">{error}</div> : null}
      {success ? (
        <><div className="proposal-auth-success">Password reset complete. Redirecting to login...</div><div className="proposal-auth-links"><Link to="/login">Go to login</Link></div></>
      ) : (
        <form className="proposal-contact-form" onSubmit={handleSubmit}>
          <label>Reset token<input value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste reset token" required /></label>
          <div className="proposal-field-grid">
            <label>New password<input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Enter new password" required /></label>
            <label>Confirm password<input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Confirm new password" required /></label>
          </div>
          <div className="proposal-form-actions"><button type="submit" className="proposal-button proposal-button-primary" disabled={loading}>{loading ? "Resetting" : "Reset password"}</button></div>
        </form>
      )}
      <div className="proposal-auth-links"><Link to="/login">Back to login</Link></div>
    </ProposalAuthLayout>
  );
}
