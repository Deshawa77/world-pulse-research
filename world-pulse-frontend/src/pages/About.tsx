import { Link } from "react-router-dom";
import { 
  Activity, 
  Target, 
  Lightbulb, 
  Users, 
  Code2, 
  Database, 
  Brain, 
  Globe,
  ArrowRight,
  GraduationCap,
  BookOpen
} from "lucide-react";

const teamMembers = [
  { name: "E D Ethugala", id: "10965366", role: "Project Lead" },
  { name: "K D Attanayake", id: "10965100", role: "Backend Developer" },
  { name: "C T Weckasinghe", id: "10965637", role: "Data Engineer" },
  { name: "R D Rajapaksha", id: "10965292", role: "ML Engineer" },
  { name: "L V Randeniya", id: "10965520", role: "Frontend Developer" },
  { name: "P G N Theekshana", id: "10965309", role: "NLP Specialist" },
  { name: "M H C Mudunkothge", id: "10965120", role: "Security Engineer" },
  { name: "Y M V Gimhani", id: "10965223", role: "UI/UX Designer" },
  { name: "R D A A Ranathunga", id: "10965512", role: "DevOps Engineer" }
];

const techStack = [
  { name: "Python", category: "Backend", description: "Data processing, ML, and API development" },
  { name: "React + TypeScript", category: "Frontend", description: "Interactive dashboard and UI components" },
  { name: "Apache Kafka", category: "Data Streaming", description: "Real-time data pipeline processing" },
  { name: "MongoDB", category: "Database", description: "Scalable document storage for analytics" },
  { name: "TensorFlow/PyTorch", category: "ML/NLP", description: "Sentiment analysis and predictive models" },
  { name: "FastAPI", category: "Backend", description: "High-performance API framework" },
  { name: "Plotly/D3.js", category: "Visualization", description: "Interactive charts and maps" },
  { name: "Docker", category: "DevOps", description: "Containerization and deployment" }
];

export default function About() {
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
            <Link to="/contact" className="wp-landing-nav-link">Contact</Link>
            <Link to="/login" className="wp-landing-nav-link wp-landing-nav-link-primary">Login</Link>
            <Link to="/register" className="wp-landing-nav-link wp-landing-nav-link-highlight">Get Started</Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="wp-landing-hero wp-about-hero">
        <div className="wp-landing-hero-bg">
          <div className="wp-landing-hero-grid"></div>
          <div className="wp-landing-hero-glow"></div>
        </div>
        <div className="wp-landing-hero-content">
          <div className="wp-landing-hero-badge">
            <BookOpen className="wp-landing-hero-badge-icon" />
            <span>About The Project</span>
          </div>
          <h1 className="wp-landing-hero-title">
            Understanding <span className="wp-landing-hero-title-accent">Humanity</span> Through Data
          </h1>
          <p className="wp-landing-hero-subtitle">
            An academic research project exploring the intersection of artificial intelligence, 
            big data analytics, and global human behavior patterns.
          </p>
        </div>
      </section>

      {/* Project Background */}
      <section className="wp-landing-section">
        <div className="wp-landing-section-content">
          <div className="wp-landing-section-header">
            <h2 className="wp-landing-section-title">Project <span className="wp-landing-section-title-accent">Background</span></h2>
          </div>
          <div className="wp-about-content">
            <div className="wp-about-text-block">
              <p>
                In the modern digital world, millions of digital interactions occur every second across 
                social media platforms, news media, and financial networks. These data streams represent 
                a collection of emotions, responses, and behaviors of humanity—yet no single system exists 
                to capture, process, and present global human behavior in real-time.
              </p>
              <p>
                Currently, organizations use isolated tools: social media analytics for sentiment, market 
                data for economic trends, or weather feeds for environmental monitoring. These single-domain 
                systems provide only narrow glimpses of human activity, preventing a holistic understanding 
                of how populations and markets react to major world developments.
              </p>
              <p>
                <strong>The World's Pulse</strong> addresses this critical gap by creating a unified, 
                real-time analytics platform that combines social, financial, environmental, and news data 
                streams to visualize how humanity responds to significant global events.
              </p>
            </div>
            <div className="wp-about-stats-highlight">
              <div className="wp-about-stat-item">
                <Globe className="wp-about-stat-icon" />
                <span className="wp-about-stat-value">195</span>
                <span className="wp-about-stat-label">Countries Monitored</span>
              </div>
              <div className="wp-about-stat-item">
                <Database className="wp-about-stat-icon" />
                <span className="wp-about-stat-value">50+</span>
                <span className="wp-about-stat-label">Data Sources</span>
              </div>
              <div className="wp-about-stat-item">
                <Brain className="wp-about-stat-icon" />
                <span className="wp-about-stat-value">Real-Time</span>
                <span className="wp-about-stat-label">AI Processing</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Objectives */}
      <section className="wp-landing-section wp-landing-features">
        <div className="wp-landing-section-content">
          <div className="wp-landing-section-header">
            <h2 className="wp-landing-section-title">Project <span className="wp-landing-section-title-accent">Objectives</span></h2>
            <p className="wp-landing-section-subtitle">
              Specific goals driving our research and development
            </p>
          </div>
          <div className="wp-landing-features-grid">
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <Database className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Combine Multi-Source Data</h3>
              <p className="wp-landing-feature-text">
                Fetch information from social media, news feeds, financial markets, and environmental 
                systems via APIs and automated pipelines for comprehensive analysis.
              </p>
            </div>
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <Brain className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Real-Time Processing</h3>
              <p className="wp-landing-feature-text">
                Use sentiment analysis and NLP to analyze emotions and tendencies in large, 
                unstructured data streams as they arrive.
              </p>
            </div>
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <Globe className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Visualize Global Behavior</h3>
              <p className="wp-landing-feature-text">
                Develop an interactive web-based dashboard presenting real-time visualizations 
                like world sentiment, event-impact maps, and behavioral trends.
              </p>
            </div>
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <Lightbulb className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Predictive Insights</h3>
              <p className="wp-landing-feature-text">
                Introduce machine learning models to predict emotional and market trends 
                in response to emerging global events.
              </p>
            </div>
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <Target className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Crisis Detection</h3>
              <p className="wp-landing-feature-text">
                Automatically detect and alert on natural disasters, economic shocks, pandemics, 
                and political events with regional impact assessment.
              </p>
            </div>
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <Code2 className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Secure & Scalable</h3>
              <p className="wp-landing-feature-text">
                Create a secure architecture capable of handling large data volumes without 
                compromising integrity, privacy, or performance.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Technology Stack */}
      <section className="wp-landing-section">
        <div className="wp-landing-section-content">
          <div className="wp-landing-section-header">
            <h2 className="wp-landing-section-title">Technology <span className="wp-landing-section-title-accent">Stack</span></h2>
            <p className="wp-landing-section-subtitle">
              Modern technologies powering the platform
            </p>
          </div>
          <div className="wp-tech-stack-grid">
            {techStack.map((tech, index) => (
              <div key={index} className="wp-tech-card">
                <div className="wp-tech-card-header">
                  <span className="wp-tech-card-category">{tech.category}</span>
                  <Code2 className="wp-tech-card-icon" />
                </div>
                <h3 className="wp-tech-card-name">{tech.name}</h3>
                <p className="wp-tech-card-description">{tech.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Team Members */}
      <section className="wp-landing-section wp-landing-features">
        <div className="wp-landing-section-content">
          <div className="wp-landing-section-header">
            <h2 className="wp-landing-section-title">Our <span className="wp-landing-section-title-accent">Team</span></h2>
            <p className="wp-landing-section-subtitle">
              Meet the minds behind The World's Pulse
            </p>
          </div>
          <div className="wp-team-grid">
            {teamMembers.map((member, index) => (
              <div key={index} className="wp-team-card">
                <div className="wp-team-card-avatar">
                  <Users className="wp-team-card-avatar-icon" />
                </div>
                <div className="wp-team-card-info">
                  <h3 className="wp-team-card-name">{member.name}</h3>
                  <span className="wp-team-card-role">{member.role}</span>
                  <span className="wp-team-card-id">ID: {member.id}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Academic Info */}
      <section className="wp-landing-section">
        <div className="wp-landing-section-content">
          <div className="wp-academic-info">
            <div className="wp-academic-card">
              <GraduationCap className="wp-academic-icon" />
              <div className="wp-academic-content">
                <h3>Academic Information</h3>
                <div className="wp-academic-details">
                  <div className="wp-academic-item">
                    <span className="wp-academic-label">Module Code:</span>
                    <span className="wp-academic-value">PUSL2021</span>
                  </div>
                  <div className="wp-academic-item">
                    <span className="wp-academic-label">Module Name:</span>
                    <span className="wp-academic-value">Computing Group Project</span>
                  </div>
                  <div className="wp-academic-item">
                    <span className="wp-academic-label">Institution:</span>
                    <span className="wp-academic-value">Plymouth University</span>
                  </div>
                  <div className="wp-academic-item">
                    <span className="wp-academic-label">Year:</span>
                    <span className="wp-academic-value">2025</span>
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
            <h2 className="wp-landing-cta-title">Want to Learn More?</h2>
            <p className="wp-landing-cta-text">
              Explore the platform or get in touch with our team for more information 
              about the project and its capabilities.
            </p>
            <div className="wp-landing-cta-buttons">
              <Link to="/" className="wp-landing-cta-btn wp-landing-cta-btn-primary">
                Back to Home
                <ArrowRight className="wp-landing-cta-btn-icon" />
              </Link>
              <Link to="/contact" className="wp-landing-cta-btn wp-landing-cta-btn-secondary">
                Contact Us
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
              <Link to="/contact" className="wp-landing-footer-link">Contact</Link>
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
