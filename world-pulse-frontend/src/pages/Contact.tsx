import { useState } from "react";
import { Link } from "react-router-dom";
import { 
  Activity, 
  Mail, 
  User, 
  MessageSquare, 
  Send, 
  GraduationCap,
  MapPin,
  ArrowRight,
  CheckCircle,
  AlertCircle
} from "lucide-react";


export default function Contact() {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    subject: "",
    message: "",
    feedbackType: "general"
  });
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    
    // Basic validation
    if (!formData.name || !formData.email || !formData.message) {
      setError("Please fill in all required fields.");
      return;
    }

    if (!formData.email.includes("@")) {
      setError("Please enter a valid email address.");
      return;
    }

    // Simulate form submission
    setSubmitted(true);
    setTimeout(() => {
      setFormData({
        name: "",
        email: "",
        subject: "",
        message: "",
        feedbackType: "general"
      });
      setSubmitted(false);
    }, 5000);
  };

  return (
    <div className="wp-landing-page">
      {/* Navigation */}
      <nav className="wp-landing-nav">
        <div className="wp-landing-nav-content">
          <Link to="/" className="wp-landing-logo">
            <Activity className="wp-landing-logo-icon" />
            <span>THE WORLD'S <span className="wp-landing-logo-accent">PULSE</span></span>
          </Link>
          <div className="wp-landing-nav-links">
            <Link to="/" className="wp-landing-nav-link">Home</Link>
            <Link to="/about" className="wp-landing-nav-link">About</Link>
            <Link to="/login" className="wp-landing-nav-link wp-landing-nav-link-primary">Login</Link>
            <Link to="/register" className="wp-landing-nav-link wp-landing-nav-link-highlight">Get Started</Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="wp-landing-hero wp-contact-hero">
        <div className="wp-landing-hero-bg">
          <div className="wp-landing-hero-grid"></div>
          <div className="wp-landing-hero-glow"></div>
        </div>
        <div className="wp-landing-hero-content">
          <div className="wp-landing-hero-badge">
            <Mail className="wp-landing-hero-badge-icon" />
            <span>Get In Touch</span>
          </div>
          <h1 className="wp-landing-hero-title">
            Contact <span className="wp-landing-hero-title-accent">Us</span>
          </h1>
          <p className="wp-landing-hero-subtitle">
            Have questions about The World's Pulse? Want to provide feedback or collaborate? 
            We'd love to hear from you.
          </p>
        </div>
      </section>

      {/* Contact Section */}
      <section className="wp-landing-section">
        <div className="wp-landing-section-content">
          <div className="wp-contact-container">
            {/* Contact Form */}
            <div className="wp-contact-form-wrapper">
              <div className="wp-contact-form-card">
                <h2 className="wp-contact-form-title">Send us a Message</h2>
                
                {submitted ? (
                  <div className="wp-contact-success">
                    <CheckCircle className="wp-contact-success-icon" />
                    <h3>Message Sent!</h3>
                    <p>Thank you for reaching out. We'll get back to you soon.</p>
                  </div>
                ) : (
                  <form onSubmit={handleSubmit} className="wp-contact-form">
                    {error && (
                      <div className="wp-contact-error">
                        <AlertCircle className="wp-contact-error-icon" />
                        <span>{error}</span>
                      </div>
                    )}

                    <div className="wp-contact-field">
                      <label htmlFor="name">
                        <User className="wp-contact-field-icon" />
                        Full Name *
                      </label>
                      <input
                        type="text"
                        id="name"
                        name="name"
                        value={formData.name}
                        onChange={handleChange}
                        placeholder="Enter your full name"
                        required
                      />
                    </div>

                    <div className="wp-contact-field">
                      <label htmlFor="email">
                        <Mail className="wp-contact-field-icon" />
                        Email Address *
                      </label>
                      <input
                        type="email"
                        id="email"
                        name="email"
                        value={formData.email}
                        onChange={handleChange}
                        placeholder="Enter your email address"
                        required
                      />
                    </div>

                    <div className="wp-contact-field">
                      <label htmlFor="feedbackType">
                        <MessageSquare className="wp-contact-field-icon" />
                        Feedback Type
                      </label>
                      <select
                        id="feedbackType"
                        name="feedbackType"
                        value={formData.feedbackType}
                        onChange={handleChange}
                      >
                        <option value="general">General Inquiry</option>
                        <option value="feedback">Feedback</option>
                        <option value="bug">Bug Report</option>
                        <option value="feature">Feature Request</option>
                        <option value="collaboration">Collaboration</option>
                        <option value="academic">Academic Inquiry</option>
                      </select>
                    </div>

                    <div className="wp-contact-field">
                      <label htmlFor="subject">
                        Subject
                      </label>
                      <input
                        type="text"
                        id="subject"
                        name="subject"
                        value={formData.subject}
                        onChange={handleChange}
                        placeholder="What is this about?"
                      />
                    </div>

                    <div className="wp-contact-field">
                      <label htmlFor="message">
                        <MessageSquare className="wp-contact-field-icon" />
                        Message *
                      </label>
                      <textarea
                        id="message"
                        name="message"
                        value={formData.message}
                        onChange={handleChange}
                        placeholder="Tell us more about your inquiry..."
                        rows={5}
                        required
                      />
                    </div>

                    <button type="submit" className="wp-contact-submit-btn">
                      <Send className="wp-contact-submit-icon" />
                      Send Message
                    </button>
                  </form>
                )}
              </div>
            </div>

            {/* Contact Info */}
            <div className="wp-contact-info-wrapper">
              <div className="wp-contact-info-card">
                <h3 className="wp-contact-info-title">Supervisor Information</h3>
                <div className="wp-contact-info-item">
                  <GraduationCap className="wp-contact-info-icon" />
                  <div className="wp-contact-info-content">
                    <span className="wp-contact-info-label">Academic Supervisor</span>
                    <span className="wp-contact-info-value">Plymouth University Faculty</span>
                    <span className="wp-contact-info-sublabel">Computing Group Project (PUSL2021)</span>
                  </div>
                </div>
              </div>

              <div className="wp-contact-info-card">
                <h3 className="wp-contact-info-title">Project Details</h3>
                <div className="wp-contact-info-item">
                  <MapPin className="wp-contact-info-icon" />
                  <div className="wp-contact-info-content">
                    <span className="wp-contact-info-label">Institution</span>
                    <span className="wp-contact-info-value">Plymouth University</span>
                    <span className="wp-contact-info-sublabel">United Kingdom</span>
                  </div>
                </div>
                <div className="wp-contact-info-item">
                  <GraduationCap className="wp-contact-info-icon" />
                  <div className="wp-contact-info-content">
                    <span className="wp-contact-info-label">Module</span>
                    <span className="wp-contact-info-value">PUSL2021</span>
                    <span className="wp-contact-info-sublabel">Computing Group Project</span>
                  </div>
                </div>
              </div>

              <div className="wp-contact-info-card wp-contact-info-card-highlight">
                <h3 className="wp-contact-info-title">Quick Links</h3>
                <div className="wp-contact-quick-links">
                  <Link to="/" className="wp-contact-quick-link">
                    <ArrowRight className="wp-contact-quick-link-icon" />
                    Back to Home
                  </Link>
                  <Link to="/about" className="wp-contact-quick-link">
                    <ArrowRight className="wp-contact-quick-link-icon" />
                    About the Project
                  </Link>
                  <Link to="/login" className="wp-contact-quick-link">
                    <ArrowRight className="wp-contact-quick-link-icon" />
                    Access Dashboard
                  </Link>
                </div>
              </div>

              <div className="wp-contact-info-card wp-contact-feedback-card">
                <h3 className="wp-contact-info-title">Feedback Options</h3>
                <div className="wp-contact-feedback-types">
                  <div className="wp-contact-feedback-type">
                    <span className="wp-contact-feedback-type-label">General Inquiry</span>
                    <span className="wp-contact-feedback-type-desc">Questions about the platform</span>
                  </div>
                  <div className="wp-contact-feedback-type">
                    <span className="wp-contact-feedback-type-label">Bug Report</span>
                    <span className="wp-contact-feedback-type-desc">Report technical issues</span>
                  </div>
                  <div className="wp-contact-feedback-type">
                    <span className="wp-contact-feedback-type-label">Feature Request</span>
                    <span className="wp-contact-feedback-type-desc">Suggest new capabilities</span>
                  </div>
                  <div className="wp-contact-feedback-type">
                    <span className="wp-contact-feedback-type-label">Academic Inquiry</span>
                    <span className="wp-contact-feedback-type-desc">Research collaboration</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="wp-landing-section wp-landing-cta">
        <div className="wp-landing-section-content">
          <div className="wp-landing-cta-container">
            <h2 className="wp-landing-cta-title">Ready to Explore?</h2>
            <p className="wp-landing-cta-text">
              Access the live dashboard and experience real-time global human behavior intelligence.
            </p>
            <div className="wp-landing-cta-buttons">
              <Link to="/login" className="wp-landing-cta-btn wp-landing-cta-btn-primary">
                Access Dashboard
                <ArrowRight className="wp-landing-cta-btn-icon" />
              </Link>
              <Link to="/register" className="wp-landing-cta-btn wp-landing-cta-btn-secondary">
                Create Account
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="wp-landing-footer">
        <div className="wp-landing-footer-content">
          <div className="wp-landing-footer-main">
            <div className="wp-landing-footer-brand">
              <Activity className="wp-landing-footer-brand-icon" />
              <span>THE WORLD'S <span className="wp-landing-footer-brand-accent">PULSE</span></span>
            </div>
            <p className="wp-landing-footer-tagline">
              Real-Time Global Human Behavior Intelligence
            </p>
          </div>
          <div className="wp-landing-footer-links">
            <div className="wp-landing-footer-links-group">
              <h4 className="wp-landing-footer-links-title">Platform</h4>
              <Link to="/" className="wp-landing-footer-link">Home</Link>
              <Link to="/about" className="wp-landing-footer-link">About</Link>
              <Link to="/login" className="wp-landing-footer-link">Login</Link>
            </div>
            <div className="wp-landing-footer-links-group">
              <h4 className="wp-landing-footer-links-title">Legal</h4>
              <span className="wp-landing-footer-link">Privacy Policy</span>
              <span className="wp-landing-footer-link">Terms of Service</span>
            </div>
          </div>
        </div>
        <div className="wp-landing-footer-bottom">
          <p className="wp-landing-footer-copyright">
            © 2025 World's Pulse. PUSL2021 Computing Group Project. Plymouth University.
          </p>
        </div>
      </footer>
    </div>
  );
}
