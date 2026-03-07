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
    setStatus({ tone: "success", message: "Message recorded. Use this page for project feedback, demo requests, and supervisor comments." });
    setFormData({ name: "", email: "", subject: "", message: "", feedbackType: "general" });
  };

  return (
    <ProposalPublicLayout
      eyebrow="Project communication"
      title="Contact the team with feedback that improves the actual system."
      subtitle="Use this page for supervisor comments, technical issues, usability feedback, collaboration requests, or questions about the proposal direction and implementation."
      aside={<div className="proposal-stat-board"><div className="proposal-stat-board-head"><span className="proposal-eyebrow">Best uses</span><h2>What this page is for</h2></div><div className="proposal-brief-points"><div><Mail size={16} /><span>Project and supervisor communication</span></div><div><MessageSquare size={16} /><span>Usability, dashboard, and reporting feedback</span></div><div><Users size={16} /><span>Requests from researchers, NGOs, educators, and technical reviewers</span></div></div></div>}
    >
      <section className="proposal-section">
        <div className="proposal-section-head">
          <div><span className="proposal-eyebrow">Feedback channel</span><h2>Keep comments tied to the proposal goals.</h2></div>
          <p>The most useful feedback connects directly to clarity, live data interpretation, predictive usefulness, security expectations, and how well the product serves its target users.</p>
        </div>
        <div className="proposal-contact-grid">
          <article className="proposal-contact-card">
            <span>Structured message</span>
            <h3>Send project feedback</h3>
            {status ? <div className={`proposal-contact-feedback ${status.tone}`}>{status.message}</div> : null}
            <form className="proposal-contact-form" onSubmit={handleSubmit}>
              <div className="proposal-field-grid">
                <label>Name<input name="name" value={formData.name} onChange={handleChange} placeholder="Your name" /></label>
                <label>Email<input name="email" type="email" value={formData.email} onChange={handleChange} placeholder="you@example.com" /></label>
              </div>
              <div className="proposal-field-grid">
                <label>Topic<input name="subject" value={formData.subject} onChange={handleChange} placeholder="Dashboard, data, UX, security..." /></label>
                <label>Feedback type<select name="feedbackType" value={formData.feedbackType} onChange={handleChange}><option value="general">General feedback</option><option value="demo">Demo request</option><option value="research">Research alignment</option><option value="technical">Technical issue</option></select></label>
              </div>
              <label>Message<textarea name="message" value={formData.message} onChange={handleChange} placeholder="State the issue, recommendation, or question clearly." /></label>
              <div className="proposal-form-actions"><button type="submit" className="proposal-button proposal-button-primary">Send feedback <Send size={16} /></button></div>
            </form>
          </article>
          <article className="proposal-contact-card">
            <span>Useful framing</span>
            <h3>Feedback that helps the project</h3>
            <ul className="proposal-list">
              <li>Does the dashboard explain cross-domain behavior clearly enough for researchers and policymakers?</li>
              <li>Are real-time alerts and predictive outputs actually actionable, or just visually impressive?</li>
              <li>Do page layouts reflect the proposal's academic goals rather than generic product UI?</li>
              <li>Is the system understandable for students and non-technical stakeholders?</li>
              <li>Are security, role access, and reliability concerns visible in the interface where appropriate?</li>
            </ul>
          </article>
        </div>
      </section>
    </ProposalPublicLayout>
  );
}
