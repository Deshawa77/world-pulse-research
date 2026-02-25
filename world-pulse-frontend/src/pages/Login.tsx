import { useState } from "react";
import { Link } from "react-router-dom";
import { login } from "../services/authService";


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
      console.log("Login response:", res);

      if (!res.access_token) {
        throw new Error("No access token received from server");
      }

      localStorage.setItem("token", res.access_token);
      localStorage.setItem("role", res.role || "user");
      
      console.log("Token stored, redirecting to dashboard...");
      
      // Use window.location for reliable redirect
      window.location.href = "/dashboard";
    } catch (err: any) {
      console.error("Login error:", err);
      setError(err.response?.data?.detail || err.message || "Login failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  }


  return (
    <div className="wp-auth-page">
      <div className="wp-auth-card">
        <h1>THE WORLD'S <span>PULSE</span></h1>
        <p className="wp-auth-subtitle">Secure Access Portal</p>

        {error && <div className="wp-auth-error">{error}</div>}

        <form onSubmit={handleSubmit} className="wp-auth-form">
          <div className="wp-auth-field">
            <label>Email Address</label>
            <input
              type="email"
              placeholder="Enter your email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="wp-auth-field">
            <label>Password</label>
            <input
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button type="submit" className="wp-auth-btn" disabled={loading}>
            {loading ? "Authenticating..." : "Login"}
          </button>
        </form>

        <div className="wp-auth-links">
          <Link to="/register">Create Account</Link>
          <Link to="/forgot-password">Forgot Password?</Link>
        </div>
      </div>
    </div>
  );
}
