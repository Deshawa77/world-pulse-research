import { useEffect, useState } from "react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import {
  changeCurrentUserPassword,
  getCurrentUser,
  updateCurrentUserProfile,
  type UserProfile,
} from "../services/api";
import "./Dashboard.css";
import "../components/futuristic-dashboard.css";

export default function Profile() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [name, setName] = useState("");
  const [organization, setOrganization] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadProfile = async () => {
    setLoading(true);
    setError("");
    try {
      const me = await getCurrentUser();
      setProfile(me);
      setName(me.name || "");
      setOrganization(me.organization || "");
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load profile.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
  }, []);

  const saveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    setSavingProfile(true);
    setError("");
    setNotice("");

    try {
      const updated = await updateCurrentUserProfile({
        name,
        organization: organization.trim() || null,
      });
      setProfile(updated);
      setNotice("Profile updated successfully.");
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to update profile.");
    } finally {
      setSavingProfile(false);
    }
  };

  const savePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setNotice("");

    if (!currentPassword || !newPassword || !confirmPassword) {
      setError("Please fill all password fields.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("New password and confirmation do not match.");
      return;
    }

    setChangingPassword(true);
    try {
      const result = await changeCurrentUserPassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setNotice(result.message || "Password updated successfully.");
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to change password.");
    } finally {
      setChangingPassword(false);
    }
  };

  return (
    <main className="wp-shell proposal-runtime-shell">
      <ConsoleNavigation
        title={<>USER <span>PROFILE</span></>}
        subtitle="Manage your account profile, credentials, and role visibility."
      />

      <section className="proposal-runtime-intro">
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">Access identity</span>
          <h2>{profile?.name || profile?.email || "Loading profile..."}</h2>
          <p>Role: <strong>{profile?.role || "-"}</strong></p>
          <p>User type: <strong>{profile?.user_type || "-"}</strong></p>
          <p>Status: <strong>{profile?.active === false ? "Deactivated" : "Active"}</strong></p>
        </article>
        <article className="proposal-runtime-panel">
          <span className="proposal-eyebrow">Account scope</span>
          <p>
            Role determines authorization. User type is profile metadata used for interface personalization and reporting.
          </p>
          <p>Only admins can change role and account activation status.</p>
        </article>
      </section>

      <section className="proposal-runtime-grid">
        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Edit profile</span>
          {loading ? <p>Loading profile...</p> : null}
          {error ? <div className="proposal-auth-error">{error}</div> : null}
          {notice ? <div className="proposal-auth-success">{notice}</div> : null}

          <form className="proposal-contact-form" onSubmit={saveProfile}>
            <label>
              Full name
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Your full name"
                required
              />
            </label>
            <label>
              Organization
              <input
                value={organization}
                onChange={(event) => setOrganization(event.target.value)}
                placeholder="University, NGO, agency..."
              />
            </label>
            <div className="proposal-form-actions">
              <button
                type="submit"
                className="proposal-button proposal-button-primary"
                disabled={savingProfile || loading}
              >
                {savingProfile ? "Saving..." : "Save profile"}
              </button>
            </div>
          </form>
        </article>

        <article className="wp-card proposal-runtime-panel">
          <span className="proposal-eyebrow">Change password</span>
          <form className="proposal-contact-form" onSubmit={savePassword}>
            <label>
              Current password
              <input
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                placeholder="Enter current password"
                required
              />
            </label>
            <label>
              New password
              <input
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                placeholder="Enter new password"
                required
              />
            </label>
            <label>
              Confirm new password
              <input
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder="Re-enter new password"
                required
              />
            </label>
            <div className="proposal-form-actions">
              <button
                type="submit"
                className="proposal-button proposal-button-primary"
                disabled={changingPassword || loading}
              >
                {changingPassword ? "Updating..." : "Update password"}
              </button>
            </div>
          </form>
        </article>
      </section>
    </main>
  );
}
