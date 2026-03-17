import { Link } from "react-router-dom";
import { ArrowRight, BrainCircuit, Globe2, ShieldCheck, TimerReset, Users } from "lucide-react";
import { ProposalPublicLayout, ProposalStatBoard } from "../components/ProposalShell";

const capabilities = [
  {
    title: "Unified signal intelligence",
    text: "Correlate social sentiment, news velocity, market movement, and weather pressure in one operating view.",
    icon: Globe2,
  },
  {
    title: "Live monitoring pipeline",
    text: "Process incoming streams with low-latency enrichment and trend detection for faster situational awareness.",
    icon: TimerReset,
  },
  {
    title: "Predictive risk analytics",
    text: "Use model-backed projections to anticipate short-term shifts and prepare response scenarios.",
    icon: BrainCircuit,
  },
  {
    title: "Secure access control",
    text: "Enable trusted usage with role-based permissions, governance visibility, and controlled administration.",
    icon: ShieldCheck,
  },
];

const audiences = [
  "Research & Intelligence Teams",
  "Operations & Risk Units",
  "Policy & Humanitarian Organizations",
  "Academic and Technical Users",
];

const valuePillars = [
  {
    title: "Detect",
    text: "Spot emerging disruptions and narrative shifts as they happen.",
  },
  {
    title: "Understand",
    text: "Analyze cross-domain signals with context-rich visual intelligence.",
  },
  {
    title: "Act",
    text: "Convert insights into rapid, evidence-backed operational decisions.",
  },
];

export default function Landing() {
  return (
    <ProposalPublicLayout
      eyebrow="Enterprise Intelligence"
      title="Professional-grade global signal intelligence."
      subtitle="The World's Pulse provides a real-time command surface for monitoring sentiment, risk, and macro behavior across critical public data streams."
      aside={<ProposalStatBoard />}
      cta={
        <>
          <Link to="/register" className="proposal-button proposal-button-primary">
            Get Started <ArrowRight size={16} />
          </Link>
          <Link to="/about" className="proposal-button proposal-button-ghost">Learn More</Link>
        </>
      }
    >
      <section className="proposal-section">
        <div className="proposal-section-head">
          <div>
            <span className="proposal-eyebrow">Strategic challenge</span>
            <h2>Critical signals are fragmented when speed matters most.</h2>
          </div>
          <p>
            Teams often jump between disconnected tools to understand fast-moving events. The World's Pulse centralizes those signals
            into one clear, operationally usable intelligence workspace.
          </p>
        </div>
      </section>

      <section className="proposal-section">
        <div className="proposal-section-head">
          <div>
            <span className="proposal-eyebrow">Core capabilities</span>
            <h2>Built for continuous monitoring and decision support.</h2>
          </div>
          <p>Each capability is designed to improve response quality, reduce blind spots, and accelerate analysis-to-action workflows.</p>
        </div>
        <div className="proposal-grid-2">
          {capabilities.map(({ title, text, icon: Icon }) => (
            <article key={title} className="proposal-card">
              <span className="proposal-card-kicker"><Icon size={14} /> Capability</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="proposal-section">
        <div className="proposal-section-head">
          <div>
            <span className="proposal-eyebrow">Designed for</span>
            <h2>Multi-disciplinary teams that need clarity under pressure.</h2>
          </div>
          <p>From analysts to operators, the platform aligns technical depth with clear decision-ready outputs.</p>
        </div>
        <div className="proposal-audience-row">
          {audiences.map((audience) => (
            <span key={audience} className="proposal-audience-pill"><Users size={14} /> {audience}</span>
          ))}
        </div>
      </section>

      <section className="proposal-section">
        <div className="proposal-section-head">
          <div>
            <span className="proposal-eyebrow">Value delivery</span>
            <h2>Detect. Understand. Act.</h2>
          </div>
          <p>A practical intelligence cycle that supports both live operations and long-horizon planning.</p>
        </div>
        <div className="proposal-grid-3">
          {valuePillars.map((pillar) => (
            <article key={pillar.title} className="proposal-card">
              <span className="proposal-card-kicker">{pillar.title}</span>
              <h3>{pillar.text}</h3>
            </article>
          ))}
        </div>
      </section>
    </ProposalPublicLayout>
  );
}
