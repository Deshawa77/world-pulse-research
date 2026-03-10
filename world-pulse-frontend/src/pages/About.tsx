import { BookOpen, BriefcaseBusiness, Shield, Sparkles, Target } from "lucide-react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import { ProposalPublicLayout, ProposalStatBoard } from "../components/ProposalShell";

const teamMembers = [
  ["E D Ethugala", "10965366", "Project lead / integration"],
  ["K D Attanayake", "10965100", "Backend engineering"],
  ["C T Weckasinghe", "10965637", "Data engineering"],
  ["R D Rajapaksha", "10965292", "Machine learning"],
  ["L V Randeniya", "10965520", "Frontend development"],
  ["P G N Theekshana", "10965309", "NLP and sentiment analysis"],
  ["M H C Mudunkothge", "10965120", "Security engineering"],
  ["Y M V Gimhani", "10965223", "UI and UX design"],
  ["R D A A Ranathunga", "10965512", "DevOps and deployment"],
] as const;

const scope = [
  { title: "Included", points: ["Live public data ingestion from social, news, financial, and weather sources", "NLP-based sentiment and trend analysis", "Interactive visual dashboard for global behavior patterns", "Predictive analytics for possible reaction and market shifts", "Secure and scalable data handling"] },
  { title: "Excluded", points: ["Manual paperwork or manual data entry workflows", "Private medical or personal user data processing", "Narrow geopolitical consultancy systems", "High-frequency trading systems outside the proposal scope"] },
];

const gaps = [
  ["Knowledge gap", "Most current work stays inside one stream such as sentiment, markets, or environmental monitoring instead of examining combined human behavior."],
  ["Technology gap", "There is no accessible cross-domain system in this project context that ingests live APIs, forecasts trends, and visualizes them for operational use."],
  ["Methodological gap", "Static datasets miss fast-changing emotional and behavioral shifts around live world events."],
  ["Contextual gap", "The project explicitly aims to make advanced real-time analytics more accessible to Sri Lankan students, analysts, and institutions."],
] as const;

export default function About() {
  return (
    <>
      <ConsoleNavigation
        title={<>PROJECT <span>ABOUT</span></>}
        subtitle="Project rationale, scope, and academic framing for The World's Pulse."
      />
      <ProposalPublicLayout
        eyebrow="Module and rationale"
        title="Why this project exists and what it promises to deliver."
        subtitle="This proposal is framed as PUSL2021 coursework: The World's Pulse - Real-Time Global Human Behavior Intelligence. It combines data engineering, machine learning, visualization, and cybersecurity into one operational system."
        aside={<ProposalStatBoard />}
      >
        <section className="proposal-section">
        <div className="proposal-section-head">
          <div>
            <span className="proposal-eyebrow">Coursework context</span>
            <h2>Academic brief translated into a usable platform concept.</h2>
          </div>
          <p>The proposal centers on a real-time system that can observe the global reaction to major events, reduce data fragmentation, and provide actionable intelligence through live dashboards and forecasts.</p>
        </div>
        <div className="proposal-grid-2">
          <article className="proposal-card"><span className="proposal-card-kicker"><BookOpen size={14} /> Module</span><h3>PUSL2021 Computing Group Project</h3><p>Coursework title: The World's Pulse: Real-Time Global Human Behavior Intelligence.</p></article>
          <article className="proposal-card"><span className="proposal-card-kicker"><BriefcaseBusiness size={14} /> Intended outcomes</span><h3>Decision support for public-good use cases</h3><p>The system is aimed at researchers, analysts, policymakers, NGOs, students, and administrators who need timely, evidence-backed visibility into global sentiment and reaction patterns.</p></article>
        </div>
        </section>

        <section className="proposal-section">
        <div className="proposal-section-head">
          <div><span className="proposal-eyebrow">Project objectives</span><h2>Five commitments that shape the platform.</h2></div>
          <p>These objectives anchor the product direction: integrated ingestion, live processing, visualization, predictive insights, and secure scale.</p>
        </div>
        <div className="proposal-grid-3">
          <article className="proposal-card"><span className="proposal-card-kicker"><Target size={14} /> Objective 01</span><h3>Combine multi-source data</h3><p>Bring social media, news, finance, and environmental APIs into one coherent analytics pipeline.</p></article>
          <article className="proposal-card"><span className="proposal-card-kicker"><Sparkles size={14} /> Objective 02</span><h3>Run real-time processing</h3><p>Filter noise, analyze sentiment, detect trends, and update dashboards fast enough to matter operationally.</p></article>
          <article className="proposal-card"><span className="proposal-card-kicker"><Shield size={14} /> Objective 03</span><h3>Forecast and secure</h3><p>Use predictive models, secure data paths, and scalable storage without drifting outside public-data scope.</p></article>
        </div>
        </section>

        <section className="proposal-section">
        <div className="proposal-section-head">
          <div><span className="proposal-eyebrow">Research gap</span><h2>The proposal is justified by what current systems fail to integrate.</h2></div>
          <p>The platform concept is strongest when it is explicit about its gap: current tools fragment behavior, context, and predictive understanding.</p>
        </div>
        <div className="proposal-gap-grid">
          {gaps.map(([title, text]) => (
            <article key={title} className="proposal-card"><span className="proposal-card-kicker">Gap</span><h3>{title}</h3><p>{text}</p></article>
          ))}
        </div>
        </section>

        <section className="proposal-section">
        <div className="proposal-section-head">
          <div><span className="proposal-eyebrow">Scope</span><h2>Clear boundaries keep the project academically coherent.</h2></div>
          <p>The proposal is broad, but it is not unlimited. Included and excluded scope need to stay visible throughout design and implementation.</p>
        </div>
        <div className="proposal-scope-grid">
          {scope.map((area) => (
            <article key={area.title} className="proposal-card">
              <span className="proposal-card-kicker">{area.title}</span>
              <h3>{area.title === "Included" ? "Within delivery scope" : "Outside delivery scope"}</h3>
              <ul className="proposal-list">{area.points.map((point) => <li key={point}>{point}</li>)}</ul>
            </article>
          ))}
        </div>
        </section>

        <section className="proposal-section">
        <div className="proposal-section-head">
          <div><span className="proposal-eyebrow">Team</span><h2>Nine members, one interdisciplinary build.</h2></div>
          <p>The group structure reflects the proposal itself: software engineering, data engineering, machine learning, frontend delivery, security, and operations all have visible ownership.</p>
        </div>
        <div className="proposal-people-grid">
          {teamMembers.map(([name, id, role]) => (
            <article key={id} className="proposal-card proposal-team-card"><span className="proposal-card-kicker">Student {id}</span><h3>{name}</h3><p>{role}</p></article>
          ))}
        </div>
        </section>
      </ProposalPublicLayout>
    </>
  );
}
