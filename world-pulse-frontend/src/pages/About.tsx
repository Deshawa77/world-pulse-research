import { BookOpen, BriefcaseBusiness, Shield, Sparkles, Target } from "lucide-react";
import { ProposalPublicLayout, ProposalStatBoard } from "../components/ProposalShell";

const creators = [
  ["E D Ethugala", "Co-creator", "Platform architecture, system integration, and delivery leadership"],
  ["Y M V Gimhani", "Co-creator", "Product design, UX strategy, and interface direction"],
] as const;

const scope = [
  {
    title: "Included",
    points: [
      "Live public data ingestion from social, news, financial, and weather sources",
      "NLP-driven sentiment and trend analysis",
      "Interactive dashboards for global behavioral and risk intelligence",
      "Predictive analytics for short-term scenario forecasting",
      "Role-based access and secure system operations",
    ],
  },
  {
    title: "Excluded",
    points: [
      "Private personal data processing",
      "Manual data-entry workflows",
      "Domain-specific advisory platforms outside global intelligence scope",
      "Unregulated high-frequency trading automation",
    ],
  },
];

const differentiators = [
  [
    "Cross-domain fusion",
    "Most tools specialize in one stream. The World's Pulse combines behavioral, informational, market, and environmental signals in one model.",
  ],
  [
    "Operational latency",
    "The platform is optimized for timely interpretation with live ingestion and fast visualization loops.",
  ],
  [
    "Decision-centered design",
    "Outputs focus on actionable insights, not only charts, so teams can move from signal detection to response quickly.",
  ],
  [
    "Secure collaboration",
    "Built-in role segmentation helps technical and non-technical users work from one trusted intelligence layer.",
  ],
] as const;

export default function About() {
  return (
    <ProposalPublicLayout
      eyebrow="About The Platform"
      title="A focused intelligence system for real-time global awareness."
      subtitle="The World's Pulse is designed as a production-style platform that unifies live data, analytics, and forecasting for operational teams."
      aside={<ProposalStatBoard />}
    >
      <section className="proposal-section">
        <div className="proposal-section-head">
          <div>
            <span className="proposal-eyebrow">Platform profile</span>
            <h2>From fragmented feeds to one operating picture.</h2>
          </div>
          <p>
            The system turns scattered public signals into a coherent intelligence workflow that supports monitoring, forecasting,
            and evidence-based response planning.
          </p>
        </div>
        <div className="proposal-grid-2">
          <article className="proposal-card">
            <span className="proposal-card-kicker"><BookOpen size={14} /> Product focus</span>
            <h3>Live global intelligence workflow</h3>
            <p>Continuously track sentiment, topic movement, volatility, and environmental pressure through a unified analytics surface.</p>
          </article>
          <article className="proposal-card">
            <span className="proposal-card-kicker"><BriefcaseBusiness size={14} /> Business value</span>
            <h3>Faster decisions with stronger context</h3>
            <p>Support analysts, planners, and operations teams with timely, explainable insights across multiple signal domains.</p>
          </article>
        </div>
      </section>

      <section className="proposal-section">
        <div className="proposal-section-head">
          <div><span className="proposal-eyebrow">Core commitments</span><h2>What the platform is built to deliver.</h2></div>
          <p>These design commitments define product quality, reliability, and operational usefulness.</p>
        </div>
        <div className="proposal-grid-3">
          <article className="proposal-card"><span className="proposal-card-kicker"><Target size={14} /> Commitment 01</span><h3>Integrate critical data streams</h3><p>Bring social, news, market, and weather signals into one consistent intelligence model.</p></article>
          <article className="proposal-card"><span className="proposal-card-kicker"><Sparkles size={14} /> Commitment 02</span><h3>Deliver low-latency analytics</h3><p>Provide near real-time processing and interpretation for fast-changing events.</p></article>
          <article className="proposal-card"><span className="proposal-card-kicker"><Shield size={14} /> Commitment 03</span><h3>Secure and scale responsibly</h3><p>Protect operational usage with role controls, governance visibility, and scalable architecture.</p></article>
        </div>
      </section>

      <section className="proposal-section">
        <div className="proposal-section-head">
          <div><span className="proposal-eyebrow">Differentiation</span><h2>Why this platform is different.</h2></div>
          <p>The value comes from integration, speed, and practical decision support rather than isolated visual analytics.</p>
        </div>
        <div className="proposal-gap-grid">
          {differentiators.map(([title, text]) => (
            <article key={title} className="proposal-card"><span className="proposal-card-kicker">Advantage</span><h3>{title}</h3><p>{text}</p></article>
          ))}
        </div>
      </section>

      <section className="proposal-section">
        <div className="proposal-section-head">
          <div><span className="proposal-eyebrow">Scope</span><h2>Clear boundaries for disciplined delivery.</h2></div>
          <p>Scope clarity keeps the platform useful, maintainable, and aligned with real operational outcomes.</p>
        </div>
        <div className="proposal-scope-grid">
          {scope.map((area) => (
            <article key={area.title} className="proposal-card">
              <span className="proposal-card-kicker">{area.title}</span>
              <h3>{area.title === "Included" ? "Within product scope" : "Outside product scope"}</h3>
              <ul className="proposal-list">{area.points.map((point) => <li key={point}>{point}</li>)}</ul>
            </article>
          ))}
        </div>
      </section>

      <section className="proposal-section">
        <div className="proposal-section-head">
          <div><span className="proposal-eyebrow">Creators</span><h2>Built by a focused founding team.</h2></div>
          <p>The platform was created by two contributors with complementary technical and product strengths.</p>
        </div>
        <div className="proposal-people-grid">
          {creators.map(([name, title, role]) => (
            <article key={name} className="proposal-card proposal-team-card"><span className="proposal-card-kicker">{title}</span><h3>{name}</h3><p>{role}</p></article>
          ))}
        </div>
      </section>
    </ProposalPublicLayout>
  );
}
