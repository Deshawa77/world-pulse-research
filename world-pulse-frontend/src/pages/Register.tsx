import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register } from "../services/authService";
import type { UserRole, UserType } from "../services/api";
import { ProposalAuthLayout } from "../components/ProposalShell";

const userTypes: Array<{ value: UserType; label: string }> = [
  { value: "researcher", label: "Researcher / Analyst" },
  { value: "policy", label: "Policy / NGO" },
  { value: "student", label: "Student / Educator" },
  { value: "developer", label: "Developer" },
];

const accessLevels: Array<{ value: UserRole; label: string }> = [
  { value: "user", label: "Standard User" },
  { value: "admin", label: "Admin (Invite Code)" },
];

export default function Register() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
    role: "user" as UserRole,
    user_type: "researcher" as UserType,
    admin_invite_code: "",
    organization: "",
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;

    if (name === "user_type") {
      setFormData((current) => ({ ...current, user_type: value as UserType }));
      return;
    }

    if (name === "role") {
      const nextRole = value as UserRole;
      setFormData((current) => ({
        ...current,
        role: nextRole,
        user_type: nextRole === "admin" ? "developer" : current.user_type,
        admin_invite_code: nextRole === "admin" ? current.admin_invite_code : "",
      }));
      return;
    }

    setFormData((current) => ({ ...current, [name]: value }));
  };

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (formData.role === "admin" && !formData.admin_invite_code.trim()) {
      setError("Admin invite code is required when registering as admin.");
      return;
    }

    setLoading(true);
    try {
      await register(
        formData.name,
        formData.email,
        formData.password,
        formData.user_type,
        formData.organization,
        formData.role,
        formData.admin_invite_code.trim() || undefined
      );
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
      eyebrow="Workspace Onboarding"
      title="Create your World's Pulse account."
      subtitle="Set up secure access to the intelligence platform with the role and profile that fits your responsibilities."
      bullets={[
        "Choose a profile aligned to your primary workflow, from research to operational monitoring.",
        "Use admin registration only with an authorized invite code.",
        "All accounts are provisioned for secure, role-aware access across platform features.",
      ]}
      metrics={[
        { label: "Access Tiers", value: "User + Admin" },
        { label: "Profile Types", value: "4" },
        { label: "Security", value: "Invite-controlled" },
      ]}
    >
      <h2>Create account</h2>
      <p>Complete the form below to activate your workspace access.</p>
      {error ? <div className="proposal-auth-error">{error}</div> : null}
      {success ? <div className="proposal-auth-success">{success}</div> : null}
      <form className="proposal-contact-form" onSubmit={handleSubmit}>
        <label>Full name<input name="name" value={formData.name} onChange={handleChange} placeholder="Enter your full name" required /></label>
        <div className="proposal-field-grid">
          <label>Email address<input name="email" type="email" value={formData.email} onChange={handleChange} placeholder="Enter your email" required /></label>
          <label>Organization<input name="organization" value={formData.organization} onChange={handleChange} placeholder="Company, university, NGO..." /></label>
        </div>
        <div className="proposal-field-grid">
          <label>Password<input name="password" type="password" value={formData.password} onChange={handleChange} placeholder="Create a password" required /></label>
          <label>User profile<select name="user_type" value={formData.user_type} onChange={handleChange} required disabled={formData.role === "admin"}>{userTypes.map((profile) => <option key={profile.value} value={profile.value}>{profile.label}</option>)}</select></label>
        </div>
        <div className="proposal-field-grid">
          <label>Access tier<select name="role" value={formData.role} onChange={handleChange} required>{accessLevels.map((level) => <option key={level.value} value={level.value}>{level.label}</option>)}</select></label>
          {formData.role === "admin" ? (
            <label>Admin invite code<input name="admin_invite_code" type="password" value={formData.admin_invite_code} onChange={handleChange} placeholder="Enter admin invite code" required /></label>
          ) : <div />}
        </div>
        <div className="proposal-form-actions"><button type="submit" className="proposal-button proposal-button-primary" disabled={loading}>{loading ? "Creating account" : "Create account"}</button></div>
      </form>
      <div className="proposal-auth-links"><Link to="/login">Already have an account?</Link></div>
    </ProposalAuthLayout>
  );
}
