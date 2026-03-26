import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  Globe2,
  Radar,
  ShieldCheck,
} from "lucide-react";

type PublicLayoutProps = {
  eyebrow: string;
  title: string;
  subtitle: string;
  children: ReactNode;
  aside?: ReactNode;
  cta?: ReactNode;
};

type AuthLayoutProps = {
  eyebrow: string;
  title: string;
  subtitle: string;
  children: ReactNode;
  bullets: string[];
  metrics?: Array<{ label: string; value: string }>;
};

const publicLinks = [
  { to: "/", label: "Home" },
  { to: "/about", label: "About" },
  { to: "/contact", label: "Contact" },
];

function ProposalBrand() {
  return (
    <Link to="/" className="proposal-brand">
      <div className="proposal-brand-icon-wrap">
        <Activity className="proposal-brand-icon" />
      </div>
      <div>
        <span className="proposal-brand-kicker">AI-Powered Global Intelligence Platform</span>
        <strong>The World's Pulse</strong>
      </div>
    </Link>
  );
}

function PublicNav() {
  return (
    <header className="proposal-nav">
      <div className="proposal-nav-inner">
        <ProposalBrand />
        <nav className="proposal-nav-links" aria-label="Primary">
          {publicLinks.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `proposal-nav-link${isActive ? " active" : ""}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="proposal-nav-actions">
          <Link to="/login" className="proposal-button proposal-button-ghost">
            Login
          </Link>
          <Link to="/register" className="proposal-button proposal-button-primary">
            Launch Console
          </Link>
        </div>
      </div>
    </header>
  );
}

export function ProposalFooter() {
  return (
    <footer className="proposal-footer">
      <div className="proposal-footer-inner">
        <div>
          <p className="proposal-footer-kicker">Real-Time Global Human Behavior Intelligence</p>
          <h2>One operating picture for social, news, finance, weather, and predictive signals.</h2>
        </div>
        <div className="proposal-footer-meta">
          <span>Role-based Access</span>
          <span>Live Decision Support</span>
        </div>
      </div>
    </footer>
  );
}

export function ProposalPublicLayout({
  eyebrow,
  title,
  subtitle,
  children,
  aside,
  cta,
}: PublicLayoutProps) {
  return (
    <div className="proposal-site-shell">
      <PublicNav />
      <main className="proposal-site-main">
        <section className="proposal-hero-frame">
          <div className="proposal-hero-copy">
            <span className="proposal-eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p>{subtitle}</p>
            {cta ? <div className="proposal-hero-actions">{cta}</div> : null}
          </div>
          {aside ? <aside className="proposal-hero-aside">{aside}</aside> : null}
        </section>
        <div className="proposal-site-content">{children}</div>
      </main>
      <ProposalFooter />
    </div>
  );
}

export function ProposalAuthLayout({
  eyebrow,
  title,
  subtitle,
  children,
  bullets,
  metrics = [],
}: AuthLayoutProps) {
  return (
    <div className="proposal-site-shell proposal-auth-shell">
      <PublicNav />
      <main className="proposal-auth-main">
        <section className="proposal-auth-grid">
          <article className="proposal-auth-brief">
            <span className="proposal-eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p>{subtitle}</p>
            <div className="proposal-auth-signal-row">
              <div className="proposal-auth-signal">
                <Radar size={18} />
                <span>Live cross-domain monitoring</span>
              </div>
              <div className="proposal-auth-signal">
                <BrainCircuit size={18} />
                <span>Predictive intelligence for operational decisions</span>
              </div>
              <div className="proposal-auth-signal">
                <ShieldCheck size={18} />
                <span>Secure, role-based access to operational analytics</span>
              </div>
            </div>
            {metrics.length > 0 ? (
              <div className="proposal-auth-metrics">
                {metrics.map((metric) => (
                  <div key={metric.label} className="proposal-auth-metric">
                    <span>{metric.label}</span>
                    <strong>{metric.value}</strong>
                  </div>
                ))}
              </div>
            ) : null}
            <div className="proposal-auth-list-card">
              <h2>Platform value</h2>
              <ul>
                {bullets.map((bullet) => (
                  <li key={bullet}>{bullet}</li>
                ))}
              </ul>
            </div>
          </article>
          <section className="proposal-auth-card">{children}</section>
        </section>
      </main>
    </div>
  );
}

export function ProposalStatBoard() {
  return (
    <div className="proposal-stat-board">
      <div className="proposal-stat-board-head">
        <span className="proposal-eyebrow">System framing</span>
        <h2>Platform operating model</h2>
      </div>
      <div className="proposal-stat-grid">
        <div className="proposal-stat-card">
          <span>Sources</span>
          <strong>Social, news, finance, weather</strong>
        </div>
        <div className="proposal-stat-card">
          <span>Latency target</span>
          <strong>5-10 second live updates</strong>
        </div>
        <div className="proposal-stat-card">
          <span>Primary outputs</span>
          <strong>Risk map, sentiment, forecasts, alerts</strong>
        </div>
        <div className="proposal-stat-card">
          <span>Stakeholders</span>
          <strong>Researchers, policy, students, admins</strong>
        </div>
      </div>
      <div className="proposal-brief-points">
        <div>
          <Globe2 size={16} />
          <span>Centralized global behavior visibility</span>
        </div>
        <div>
          <BrainCircuit size={16} />
          <span>Predictive modeling on top of live analytics</span>
        </div>
        <div>
          <ArrowRight size={16} />
          <span>Actionable support for crisis response and research</span>
        </div>
      </div>
    </div>
  );
}
