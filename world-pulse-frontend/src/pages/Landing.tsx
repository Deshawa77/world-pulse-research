import { Link } from "react-router-dom";
import { ArrowRight, BrainCircuit, Globe2, ShieldCheck, TimerReset, Users } from "lucide-react";
import { ProposalPublicLayout, ProposalStatBoard } from "../components/ProposalShell";

const objectives = [
  { title: "Combine multi-source data", text: "Fuse social, news, financial, and environmental streams into one operational picture instead of isolated dashboards.", icon: Globe2 },
  { title: "Process live behavior signals", text: "Apply NLP, sentiment analysis, filtering, and trend extraction on incoming data within a practical monitoring window.", icon: TimerReset },
  { title: "Deliver predictive intelligence", text: "Turn raw behavior signals into forecasts, alerts, and decision support for crisis response and long-range monitoring.", icon: BrainCircuit },
  { title: "Keep it secure and usable", text: "Support researchers, policy teams, students, and administrators with scalable, secure, role-aware access.", icon: ShieldCheck },
];

const stakeholders = ["Researchers / Analysts", "Policy Makers / NGO", "Students / Educators", "Developers / Admin"];
const timeline = [
  { phase: "January", focus: "Requirements, literature review, architecture, dashboard planning" },
  { phase: "February", focus: "Backend pipelines, preprocessing, NLP, predictive models, security, dashboard integration" },
  { phase: "March", focus: "Testing, feedback, documentation, presentation, and final submission" },
];

export default function Landing() {
  return (
    <ProposalPublicLayout
      eyebrow="Proposal concept"
      title="Real-time global human behavior intelligence."
      subtitle="The World's Pulse is a cross-domain analytics platform designed to capture how societies, markets, media, and environmental systems react to major global events in one live operating picture."
      aside={<ProposalStatBoard />}
      cta={
        <>
          <Link to="/register" className="proposal-button proposal-button-primary">Open the platform <ArrowRight size={16} /></Link>
          <Link to="/about" className="proposal-button proposal-button-ghost">Read the proposal</Link>
        </>
      }
    >
      <section className="proposal-section">
        <div className="proposal-section-head">
          <div>
            <span className="proposal-eyebrow">Problem statement</span>
            <h2>Fragmented signals hide the real human response.</h2>
          </div>
          <p>Existing tools usually monitor one domain at a time. Social sentiment, market reactions, search behavior, headlines, and weather alerts stay disconnected even when the same event drives them all.</p>
        </div>
        <div className="proposal-grid-2">
          <article className="proposal-card">
            <span className="proposal-card-kicker">Current gap</span>
            <h3>No unified behavioral intelligence layer</h3>
            <p>When disasters, pandemics, political instability, or economic shocks occur, organizations often need to piece together multiple dashboards manually before they can understand the global mood and likely consequences.</p>
          </article>
          <article className="proposal-card">
            <span className="proposal-card-kicker">World's Pulse answer</span>
            <h3>One dashboard, many streams, faster interpretation</h3>
            <p>The platform turns fragmented public signals into live dashboards, predictive models, and historical evidence that can support researchers, humanitarian actors, and policy teams.</p>
          </article>
        </div>
      </section>

      <section className="proposal-section">
        <div className="proposal-section-head">
          <div>
            <span className="proposal-eyebrow">Core objectives</span>
            <h2>Built directly from the proposal requirements.</h2>
          </div>
          <p>The design is not generic product marketing. Each area maps to the project scope, expected outcomes, and non-functional targets described in the coursework proposal.</p>
        </div>
        <div className="proposal-grid-2">
          {objectives.map(({ title, text, icon: Icon }) => (
            <article key={title} className="proposal-card">
              <span className="proposal-card-kicker"><Icon size={14} /> Objective</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="proposal-section">
        <div className="proposal-section-head">
          <div>
            <span className="proposal-eyebrow">Primary users</span>
            <h2>Made for evidence-based action, not passive charts.</h2>
          </div>
          <p>The interface has to support both technical and non-technical users who need clarity, not just visual spectacle.</p>
        </div>
        <div className="proposal-audience-row">
          {stakeholders.map((stakeholder) => (
            <span key={stakeholder} className="proposal-audience-pill"><Users size={14} /> {stakeholder}</span>
          ))}
        </div>
      </section>

      <section className="proposal-section">
        <div className="proposal-section-head">
          <div>
            <span className="proposal-eyebrow">Delivery rhythm</span>
            <h2>Requirements in January, systems in February, validation in March.</h2>
          </div>
          <p>The page structure reflects the proposal timeline: analysis first, then architecture and implementation, then testing, documentation, and submission.</p>
        </div>
        <div className="proposal-grid-3">
          {timeline.map((item) => (
            <article key={item.phase} className="proposal-card">
              <span className="proposal-card-kicker">{item.phase}</span>
              <h3>{item.focus}</h3>
            </article>
          ))}
        </div>
      </section>
    </ProposalPublicLayout>
  );
}
