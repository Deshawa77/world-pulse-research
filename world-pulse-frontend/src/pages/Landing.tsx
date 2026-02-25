import { Link } from "react-router-dom";
import { 
  Activity, 
  Globe, 
  Brain, 
  Shield, 
  Zap, 
  TrendingUp, 
  Database, 
  Lock,
  ArrowRight,
  PlayCircle,
  BarChart3,
  Users,
  Clock
} from "lucide-react";


export default function Landing() {
  return (
    <div className="wp-landing-page">
      {/* Navigation */}
      <nav className="wp-landing-nav">
        <div className="wp-landing-nav-content">
          <div className="wp-landing-logo">
            <Activity className="wp-landing-logo-icon" />
            <span>THE WORLD'S <span className="wp-landing-logo-accent">PULSE</span></span>
          </div>
          <div className="wp-landing-nav-links">
            <Link to="/about" className="wp-landing-nav-link">About</Link>
            <Link to="/contact" className="wp-landing-nav-link">Contact</Link>
            <Link to="/login" className="wp-landing-nav-link wp-landing-nav-link-primary">Login</Link>
            <Link to="/register" className="wp-landing-nav-link wp-landing-nav-link-highlight">Get Started</Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="wp-landing-hero">
        <div className="wp-landing-hero-bg">
          <div className="wp-landing-hero-grid"></div>
          <div className="wp-landing-hero-glow"></div>
        </div>
        <div className="wp-landing-hero-content">
          <div className="wp-landing-hero-badge">
            <Zap className="wp-landing-hero-badge-icon" />
            <span>Real-Time Global Intelligence</span>
          </div>
          <h1 className="wp-landing-hero-title">
            Experience the <span className="wp-landing-hero-title-accent">Pulse</span> of Humanity
          </h1>
          <p className="wp-landing-hero-subtitle">
            The World's Pulse is an intelligent analytics platform that captures and visualizes 
            global human behavior in real-time. Monitor emotions, trends, and reactions across 
            social media, financial markets, and news streams—all in one unified dashboard.
          </p>
          <div className="wp-landing-hero-cta">
            <Link to="/register" className="wp-landing-hero-btn wp-landing-hero-btn-primary">
              Start Exploring
              <ArrowRight className="wp-landing-hero-btn-icon" />
            </Link>
            <Link to="/login" className="wp-landing-hero-btn wp-landing-hero-btn-secondary">
              <PlayCircle className="wp-landing-hero-btn-icon" />
              Live Demo
            </Link>
          </div>
          <div className="wp-landing-hero-stats">
            <div className="wp-landing-hero-stat">
              <span className="wp-landing-hero-stat-value">50+</span>
              <span className="wp-landing-hero-stat-label">Data Sources</span>
            </div>
            <div className="wp-landing-hero-stat">
              <span className="wp-landing-hero-stat-value">{"<5s"}</span>
              <span className="wp-landing-hero-stat-label">Real-time Updates</span>
            </div>

            <div className="wp-landing-hero-stat">
              <span className="wp-landing-hero-stat-value">195</span>
              <span className="wp-landing-hero-stat-label">Countries Monitored</span>
            </div>
            <div className="wp-landing-hero-stat">
              <span className="wp-landing-hero-stat-value">99.9%</span>
              <span className="wp-landing-hero-stat-label">Uptime</span>
            </div>
          </div>
        </div>
      </section>

      {/* What is World's Pulse Section */}
      <section className="wp-landing-section wp-landing-about">
        <div className="wp-landing-section-content">
          <div className="wp-landing-section-header">
            <h2 className="wp-landing-section-title">What is <span className="wp-landing-section-title-accent">World's Pulse</span>?</h2>
            <p className="wp-landing-section-subtitle">
              A revolutionary platform that transforms fragmented global data into actionable intelligence
            </p>
          </div>
          <div className="wp-landing-about-grid">
            <div className="wp-landing-about-card">
              <div className="wp-landing-about-card-icon">
                <Globe className="wp-landing-about-card-icon-svg" />
              </div>
              <h3 className="wp-landing-about-card-title">Global Reach</h3>
              <p className="wp-landing-about-card-text">
                Monitor human behavior across 195 countries in real-time. From Tokyo to New York, 
                capture the collective emotional response to world events as they unfold.
              </p>
            </div>
            <div className="wp-landing-about-card">
              <div className="wp-landing-about-card-icon">
                <Brain className="wp-landing-about-card-icon-svg" />
              </div>
              <h3 className="wp-landing-about-card-title">AI-Powered Insights</h3>
              <p className="wp-landing-about-card-text">
                Advanced NLP and machine learning models analyze sentiment, detect trends, 
                and predict behavioral shifts before they become mainstream news.
              </p>
            </div>
            <div className="wp-landing-about-card">
              <div className="wp-landing-about-card-icon">
                <Database className="wp-landing-about-card-icon-svg" />
              </div>
              <h3 className="wp-landing-about-card-title">Multi-Source Fusion</h3>
              <p className="wp-landing-about-card-text">
                Integrate social media, financial markets, news feeds, and environmental data 
                into a single coherent view of global human behavior.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Key Features Section */}
      <section className="wp-landing-section wp-landing-features">
        <div className="wp-landing-section-content">
          <div className="wp-landing-section-header">
            <h2 className="wp-landing-section-title">Key <span className="wp-landing-section-title-accent">Features</span></h2>
            <p className="wp-landing-section-subtitle">
              Everything you need to understand the global human condition
            </p>
          </div>
          <div className="wp-landing-features-grid">
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <Clock className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Real-Time Analytics</h3>
              <p className="wp-landing-feature-text">
                Live dashboards update every 5-10 seconds with fresh data from across the globe. 
                Watch events unfold in real-time as humanity reacts.
              </p>
            </div>
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <BarChart3 className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Sentiment Analysis</h3>
              <p className="wp-landing-feature-text">
                Natural Language Processing models analyze emotions across millions of data points, 
                tracking fear, optimism, sadness, and more.
              </p>
            </div>
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <TrendingUp className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Predictive Intelligence</h3>
              <p className="wp-landing-feature-text">
                Machine learning models forecast trends and predict behavioral shifts, 
                giving you advance warning of significant global events.
              </p>
            </div>
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <Shield className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Secure & Scalable</h3>
              <p className="wp-landing-feature-text">
                Enterprise-grade security with encrypted API keys, HTTPS/SSL communication, 
                and role-based access control. Built to scale.
              </p>
            </div>
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <Users className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Crisis Detection</h3>
              <p className="wp-landing-feature-text">
                Automated alerts for natural disasters, economic shocks, pandemics, and political 
                events with impact assessment across regions.
              </p>
            </div>
            <div className="wp-landing-feature">
              <div className="wp-landing-feature-icon">
                <Lock className="wp-landing-feature-icon-svg" />
              </div>
              <h3 className="wp-landing-feature-title">Privacy First</h3>
              <p className="wp-landing-feature-text">
                We only process publicly available data streams. No private user data is collected 
                or stored, ensuring ethical analytics.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Live Demo Preview Section */}
      <section className="wp-landing-section wp-landing-demo">
        <div className="wp-landing-section-content">
          <div className="wp-landing-demo-container">
            <div className="wp-landing-demo-content">
              <h2 className="wp-landing-demo-title">
                See the <span className="wp-landing-demo-title-accent">World's Pulse</span> in Action
              </h2>
              <p className="wp-landing-demo-text">
                Experience our interactive dashboard with real-time visualizations, 
                global sentiment maps, and predictive analytics. Monitor how humanity 
                responds to major events as they happen.
              </p>
              <ul className="wp-landing-demo-list">
                <li className="wp-landing-demo-list-item">
                  <Activity className="wp-landing-demo-list-icon" />
                  <span>Live global sentiment tracking</span>
                </li>
                <li className="wp-landing-demo-list-item">
                  <Activity className="wp-landing-demo-list-icon" />
                  <span>Interactive world heat maps</span>
                </li>
                <li className="wp-landing-demo-list-item">
                  <Activity className="wp-landing-demo-list-icon" />
                  <span>Real-time event detection</span>
                </li>
                <li className="wp-landing-demo-list-item">
                  <Activity className="wp-landing-demo-list-icon" />
                  <span>Predictive trend forecasting</span>
                </li>
              </ul>
              <Link to="/login" className="wp-landing-demo-btn">
                Access Live Dashboard
                <ArrowRight className="wp-landing-demo-btn-icon" />
              </Link>
            </div>
            <div className="wp-landing-demo-preview">
              <div className="wp-landing-demo-preview-frame">
                <div className="wp-landing-demo-preview-header">
                  <div className="wp-landing-demo-preview-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <span className="wp-landing-demo-preview-title">World's Pulse Dashboard</span>
                </div>
                <div className="wp-landing-demo-preview-content">
                  <div className="wp-landing-demo-preview-grid">
                    <div className="wp-landing-demo-preview-panel wp-landing-demo-preview-panel-large">
                      <div className="wp-landing-demo-preview-panel-header">Global Sentiment</div>
                      <div className="wp-landing-demo-preview-chart">
                        <div className="wp-landing-demo-preview-bars">
                          <span style={{ height: "60%" }}></span>
                          <span style={{ height: "80%" }}></span>
                          <span style={{ height: "45%" }}></span>
                          <span style={{ height: "90%" }}></span>
                          <span style={{ height: "70%" }}></span>
                          <span style={{ height: "55%" }}></span>
                        </div>
                      </div>
                    </div>
                    <div className="wp-landing-demo-preview-panel">
                      <div className="wp-landing-demo-preview-panel-header">Risk Level</div>
                      <div className="wp-landing-demo-preview-gauge">
                        <div className="wp-landing-demo-preview-gauge-value">42</div>
                      </div>
                    </div>
                    <div className="wp-landing-demo-preview-panel">
                      <div className="wp-landing-demo-preview-panel-header">Active Events</div>
                      <div className="wp-landing-demo-preview-number">12</div>
                    </div>
                    <div className="wp-landing-demo-preview-panel wp-landing-demo-preview-panel-wide">
                      <div className="wp-landing-demo-preview-panel-header">Trending Topics</div>
                      <div className="wp-landing-demo-preview-tags">
                        <span>#Climate</span>
                        <span>#Economy</span>
                        <span>#Elections</span>
                        <span>#Technology</span>
                      </div>
                    </div>
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
            <h2 className="wp-landing-cta-title">Ready to Feel the Pulse?</h2>
            <p className="wp-landing-cta-text">
              Join researchers, policymakers, and analysts worldwide who use World's Pulse 
              to understand global human behavior in real-time.
            </p>
            <div className="wp-landing-cta-buttons">
              <Link to="/register" className="wp-landing-cta-btn wp-landing-cta-btn-primary">
                Create Free Account
              </Link>
              <Link to="/login" className="wp-landing-cta-btn wp-landing-cta-btn-secondary">
                Sign In
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
              <Link to="/about" className="wp-landing-footer-link">About</Link>
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
