import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register } from "../services/authService";
import { ProposalAuthLayout } from "../components/ProposalShell";

const roles = [
  { value: "researcher", label: "Researcher" },
  { value: "policy", label: "Policy maker" },
  { value: "student", label: "Student" },
  { value: "admin", label: "Admin" },
];

export default function Register() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({ name: "", email: "", password: "", role: "researcher", organization: "" });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData((current) => ({ ...current, [e.target.name]: e.target.value }));
  };

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);
    try {
      await register(formData.name, formData.email, formData.password, formData.role, formData.organization);
      setSuccess("Account created successfully. Redirecting to login...");
      setTimeout(() => navigate("/login"), 1500);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ProposalAuthLayout
      eyebrow="Onboarding"
      title="Register for the intelligence workspace."
      subtitle="Choose the role that best matches how you will use the system: research, policy, education, or administration."
      bullets={[
        "Researchers and analysts need filtering, evidence, and historical visibility.",
        "Policy and NGO users need rapid clarity after major events and crises.",
        "Students and educators need a simplified but credible global behavior view.",
      ]}
      metrics={[{ label: "User roles", value: "4" }, { label: "Scope", value: "Public data" }, { label: "Architecture", value: "Secure + scalable" }]}
    >
      <h2>Create account</h2>
      <p>Provision access for the live dashboard, prediction workspace, historical analysis, and scenario simulation.</p>
      {error ? <div className="proposal-auth-error">{error}</div> : null}
      {success ? <div className="proposal-auth-success">{success}</div> : null}
      <form className="proposal-contact-form" onSubmit={handleSubmit}>
        <label>Full name<input name="name" value={formData.name} onChange={handleChange} placeholder="Enter your full name" required /></label>
        <div className="proposal-field-grid">
          <label>Email address<input name="email" type="email" value={formData.email} onChange={handleChange} placeholder="Enter your email" required /></label>
          <label>Organization<input name="organization" value={formData.organization} onChange={handleChange} placeholder="University, NGO, agency..." /></label>
        </div>
        <div className="proposal-field-grid">
          <label>Password<input name="password" type="password" value={formData.password} onChange={handleChange} placeholder="Create a password" required /></label>
          <label>Role<select name="role" value={formData.role} onChange={handleChange} required>{roles.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}</select></label>
        </div>
        <div className="proposal-form-actions"><button type="submit" className="proposal-button proposal-button-primary" disabled={loading}>{loading ? "Creating account" : "Create account"}</button></div>
      </form>
      <div className="proposal-auth-links"><Link to="/login">Already have an account?</Link></div>
    </ProposalAuthLayout>
  );
}
