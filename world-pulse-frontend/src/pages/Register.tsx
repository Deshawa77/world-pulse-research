import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { register } from "../services/authService";

const ROLES = [
  { value: "researcher", label: "Researcher" },
  { value: "policy", label: "Policy Maker" },
  { value: "student", label: "Student" },
  { value: "admin", label: "Admin" },
];

export default function Register() {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
    role: "researcher",
    organization: "",
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      await register(formData.name, formData.email, formData.password, formData.role, formData.organization);

      setSuccess("Account created successfully! Redirecting to login...");
      setTimeout(() => navigate("/login"), 2000);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="wp-auth-page">
      <div className="wp-auth-card">
        <h1>THE WORLD'S <span>PULSE</span></h1>
        <p className="wp-auth-subtitle">Create Your Account</p>

        {error && <div className="wp-auth-error">{error}</div>}
        {success && <div className="wp-auth-success">{success}</div>}

        <form onSubmit={handleSubmit} className="wp-auth-form">
          <div className="wp-auth-field">
            <label>Full Name</label>
            <input
              type="text"
              name="name"
              placeholder="Enter your full name"
              value={formData.name}
              onChange={handleChange}
              required
            />
          </div>

          <div className="wp-auth-field">
            <label>Email Address</label>
            <input
              type="email"
              name="email"
              placeholder="Enter your email"
              value={formData.email}
              onChange={handleChange}
              required
            />
          </div>

          <div className="wp-auth-field">
            <label>Password</label>
            <input
              type="password"
              name="password"
              placeholder="Create a password"
              value={formData.password}
              onChange={handleChange}
              required
            />
          </div>

          <div className="wp-auth-field">
            <label>Select Role</label>
            <select name="role" value={formData.role} onChange={handleChange} required>
              {ROLES.map((role) => (
                <option key={role.value} value={role.value}>
                  {role.label}
                </option>
              ))}
            </select>
          </div>

          <div className="wp-auth-field">
            <label>Organization (Optional)</label>
            <input
              type="text"
              name="organization"
              placeholder="Your organization"
              value={formData.organization}
              onChange={handleChange}
            />
          </div>

          <button type="submit" className="wp-auth-btn" disabled={loading}>
            {loading ? "Creating Account..." : "Register"}
          </button>
        </form>

        <div className="wp-auth-links">
          <Link to="/login">Already have an account? Login</Link>
        </div>
      </div>
    </div>
  );
}
