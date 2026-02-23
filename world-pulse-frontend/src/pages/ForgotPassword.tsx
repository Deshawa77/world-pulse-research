import { useState } from "react";
import { Link } from "react-router-dom";
import { forgotPassword } from "../services/authService";

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
    <div className="wp-auth-page">
      <div className="wp-auth-card">
        <h1>THE WORLD'S <span>PULSE</span></h1>
        <p className="wp-auth-subtitle">Password Recovery</p>

        {error && <div className="wp-auth-error">{error}</div>}

        {success ? (
          <div>
            <div className="wp-auth-success">
              Password reset initiated. Use the token below to reset your password.
            </div>
            <div className="wp-auth-field" style={{ marginTop: "16px" }}>
              <label>Reset Token (copy this)</label>
              <div className="wp-auth-token-box">{token}</div>
            </div>
            <div className="wp-auth-links">
              <Link to={`/reset-password?token=${token}`}>Proceed to Reset Password</Link>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="wp-auth-form">
            <div className="wp-auth-field">
              <label>Email Address</label>
              <input
                type="email"
                placeholder="Enter your registered email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <button type="submit" className="wp-auth-btn" disabled={loading}>
              {loading ? "Processing..." : "Send Reset Link"}
            </button>
          </form>
        )}

        <div className="wp-auth-links">
          <Link to="/login">Back to Login</Link>
        </div>
      </div>
    </div>
  );
}
