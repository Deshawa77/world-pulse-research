import { useState } from "react";
import { Mail, MessageSquare, Send, Users } from "lucide-react";
import { ProposalPublicLayout } from "../components/ProposalShell";

export default function Contact() {
  const [formData, setFormData] = useState({ name: "", email: "", subject: "", message: "", feedbackType: "general" });
  const [status, setStatus] = useState<{ tone: "error" | "success" | "info"; message: string } | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setFormData((current) => ({ ...current, [e.target.name]: e.target.value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.email || !formData.message) {
      setStatus({ tone: "error", message: "Name, email, and message are required." });
      return;
    }
    if (!formData.email.includes("@")) {
      setStatus({ tone: "error", message: "Enter a valid email address." });
      return;
    }

    setStatus({ tone: "success", message: "Message submitted successfully. Our team will review and respond as soon as possible." });
    setFormData({ name: "", email: "", subject: "", message: "", feedbackType: "general" });
  };

  return (
    <ProposalPublicLayout
      eyebrow="Contact"
      title="Reach the World's Pulse team."
      subtitle="Use this channel for support requests, collaboration inquiries, product feedback, or implementation questions."
      aside={
        <div className="proposal-stat-board">
          <div className="proposal-stat-board-head">
            <span className="proposal-eyebrow">Best uses</span>
            <h2>How we can help</h2>
          </div>
          <div className="proposal-brief-points">
            <div><Mail size={16} /><span>Product and account support</span></div>
            <div><MessageSquare size={16} /><span>Platform feedback and enhancement requests</span></div>
            <div><Users size={16} /><span>Partnership, research, and deployment discussions</span></div>
          </div>
        </div>
      }
    >
      <section className="proposal-section">
        <div className="proposal-section-head">
          <div><span className="proposal-eyebrow">Support channel</span><h2>Send a structured request.</h2></div>
          <p>Clear messages with context, expected outcome, and urgency help us respond faster and more effectively.</p>
        </div>
        <div className="proposal-contact-grid">
          <article className="proposal-contact-card">
            <span>Message form</span>
            <h3>Contact support</h3>
            {status ? <div className={`proposal-contact-feedback ${status.tone}`}>{status.message}</div> : null}
            <form className="proposal-contact-form" onSubmit={handleSubmit}>
              <div className="proposal-field-grid">
                <label>Name<input name="name" value={formData.name} onChange={handleChange} placeholder="Your name" /></label>
                <label>Email<input name="email" type="email" value={formData.email} onChange={handleChange} placeholder="you@example.com" /></label>
              </div>
              <div className="proposal-field-grid">
                <label>Subject<input name="subject" value={formData.subject} onChange={handleChange} placeholder="Access, analytics, dashboard, integration..." /></label>
                <label>Request type<select name="feedbackType" value={formData.feedbackType} onChange={handleChange}><option value="general">General inquiry</option><option value="support">Support issue</option><option value="demo">Demo request</option><option value="partnership">Partnership</option></select></label>
              </div>
              <label>Message<textarea name="message" value={formData.message} onChange={handleChange} placeholder="Describe your request with enough detail for fast follow-up." /></label>
              <div className="proposal-form-actions"><button type="submit" className="proposal-button proposal-button-primary">Send message <Send size={16} /></button></div>
            </form>
          </article>

          <article className="proposal-contact-card">
            <span>Response quality</span>
            <h3>What to include</h3>
            <ul className="proposal-list">
              <li>What you are trying to achieve and where you are blocked.</li>
              <li>Relevant page, feature, or workflow name.</li>
              <li>Expected behavior versus observed behavior.</li>
              <li>Any urgency, impact, or timeline constraints.</li>
              <li>Best contact details for follow-up.</li>
            </ul>
          </article>
        </div>
      </section>
    </ProposalPublicLayout>
  );
}
