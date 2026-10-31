import { useEffect, useState, type CSSProperties } from 'react'
import { Link } from 'react-router'
import './App.css'
import InvestigationFlow from './InvestigationFlow'
import AgentThread from './AgentThread'
import Pricing from './Pricing'
import SupportedIntegrations from './SupportedIntegrations'
import { useSmoothScroll } from './useSmoothScroll'
import { useGetStarted } from './auth/useGetStarted'

const agents = [
  { id: 'triage', name: 'Marshal', specialty: 'Triage', image: '/agents/triage.png', alt: 'Blue investigator coordinating scope and priorities', role: 'One alert. A coordinated team.', description: 'Sizes up the incident and directs the right specialists toward the evidence. Keeps the investigation focused as new findings arrive.', color: 'var(--agent-triage)', signal: 'Incoming alerts & context', output: 'A focused investigation plan' },
  { id: 'logs', name: 'Echo', specialty: 'Logs', image: '/agents/logs.png', alt: 'Red investigator examining a terminal and error traces', role: 'Reads between the lines.', description: 'Scans log streams for errors, stack traces, and the first sign of trouble. Turns noisy output into evidence worth following.', color: 'var(--agent-logs)', signal: 'Log streams & stack traces', output: 'The first sign of failure' },
  { id: 'metrics', name: 'Pulse', specialty: 'Metrics', image: '/agents/metrics.png', alt: 'Green investigator inspecting a performance dashboard', role: 'Keeps an eye on the vitals.', description: 'Looks for latency spikes, saturation, and error-rate shifts. Establishes what changed, when it changed, and how far it reached.', color: 'var(--agent-metrics)', signal: 'Latency, traffic & error rates', output: 'A timeline of anomalies' },
  { id: 'dependency', name: 'Tether', specialty: 'Dependency', image: '/agents/dependency.jpg', alt: 'Teal investigator studying connected systems', role: 'Follows the chain reaction.', description: 'Traces connections between services to understand where a failure started and how it spread. Makes the blast radius visible.', color: 'var(--agent-dependency)', signal: 'Service calls & dependencies', output: 'The path of the failure' },
  { id: 'deploy', name: 'Ledger', specialty: 'Deploy', image: '/agents/deploy.png', alt: 'Yellow investigator inspecting infrastructure and changes', role: 'Remembers what changed.', description: 'Lines up releases and configuration changes with the incident timeline. Helps the team test whether a recent change explains the failure.', color: 'var(--agent-deploy)', signal: 'Releases & configuration changes', output: 'Changes worth investigating' },
  { id: 'hypothesis', name: 'Sage', specialty: 'Hypothesis', image: '/agents/hypothesis.jpg', alt: 'Purple investigator piecing together possible explanations', role: 'Connects evidence to answers.', description: 'Weighs competing explanations against the findings. Ranks likely root causes with supporting evidence and uncertainty made explicit.', color: 'var(--agent-hypothesis)', signal: 'Findings from every specialist', output: 'Ranked, evidence-backed hypotheses' },
]

const year = new Date().getFullYear()

function App() {
  useSmoothScroll()
  const getStarted = useGetStarted()
  const [selected, setSelected] = useState(0)

  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting)
      if (visible.length) setSelected(Number((visible[0]!.target as HTMLElement).dataset.index))
    }, { rootMargin: '-30% 0px -30% 0px', threshold: 0 })
    document.querySelectorAll('.team-member').forEach((member) => observer.observe(member))
    return () => observer.disconnect()
  }, [])

  return (
    <>
      <header className="nav">
        <a className="brand" href="#" aria-label="Tracehound home"><img className="brand-symbol" src="/tracehound-mark.svg" alt="" width="40" height="40" /><span>Tracehound</span></a>
        <nav aria-label="Main navigation">
          <a href="#agents">Agents</a>
          <a href="#how">How it works</a>
          <a href="#pricing">Pricing</a>
          <a className="nav-developer" href="https://www.linkedin.com/in/yuvraaj-singh/" target="_blank" rel="noopener noreferrer">Meet the developer <span aria-hidden="true">↗</span><span className="sr-only"> (opens in a new tab)</span></a>
          <Link className="nav-cta" to={getStarted.to} onClick={getStarted.start} aria-busy={getStarted.checking || undefined}>Get started <span aria-hidden="true">→</span></Link>
        </nav>
      </header>

      <main>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-intro">
            <div><p className="eyebrow"><span /> AI-powered incident investigation</p><h1 id="hero-title">Your next incident.<br /><span>Their next case.</span></h1></div>
            <div className="hero-summary"><p>Six AI specialists turn scattered telemetry into likely causes, cited evidence, and clear next checks.</p></div>
          </div>

          <div className="agent-stage">
            <div className="stage-caption"><span>THE INVESTIGATION UNIT</span><span>06 SPECIALISTS / ONE SHARED MISSION</span></div>
            <div className="stage-word" aria-hidden="true">ON THE CASE.</div>
            <img className="hero-image" src="/agents-hero-hd.png" alt="The Tracehound team: six colorful, fuzzy AI investigators with tools for logs, metrics, triage, dependencies, hypotheses, and deploys" fetchPriority="high" width="1680" height="936" />
          </div>

          <a className="team-scroll" href="#agents"><span>Six specialists. Meet them one by one.</span><span aria-hidden="true">Scroll to explore ↓</span></a>
        </section>

        <section id="agents" className="team" aria-labelledby="team-title">
          <div className="team-header"><div><p className="eyebrow">Six agents. One investigation.</p><h2 id="team-title">Every lead has its specialist.</h2></div><p>Meet the team following your incident<br />from the first signal to a clearer answer.</p></div>
          <nav className="team-index" aria-label="Team members">
            {agents.map((item, index) => <a key={item.id} href={`#${item.id}`} aria-current={selected === index ? 'location' : undefined} className={`agent-tab ${selected === index ? 'selected' : ''}`} style={{ '--agent-color': item.color } as CSSProperties}><span className="agent-index">0{index + 1}</span><span className="agent-dot" /><span>{item.name}</span></a>)}
          </nav>
          <div className="team-members">
            <AgentThread />
            {agents.map((item, index) => <article key={item.id} id={item.id} data-index={index} className={`team-member ${selected === index ? 'is-current' : ''}`} aria-labelledby={`${item.id}-title`} style={{ '--agent-color': item.color } as CSSProperties}>
              <div className="member-art">
                <span className="member-watermark" aria-hidden="true">{item.name}</span>
                <img src={item.image} alt={item.alt} width={item.image.endsWith('.jpg') ? 1024 : 1375} height={item.image.endsWith('.jpg') ? 572 : 768} loading="lazy" decoding="async" />
                <div className="member-caption"><span className="agent-dot" /> TRACEHOUND / {item.name.toUpperCase()} · {item.specialty.toUpperCase()}<span>0{index + 1}</span></div>
              </div>
              <div className="member-copy">
                <p className="eyebrow">Meet {item.name} <span className="member-count">/ {item.specialty} specialist</span></p>
                <h3 id={`${item.id}-title`}>{item.role}</h3>
                <p className="profile-description">{item.description}</p>
                <dl className="profile-facts"><div><dt>FOLLOWS</dt><dd>{item.signal}</dd></div><div><dt>BRINGS BACK</dt><dd>{item.output}</dd></div></dl>
                <a className="member-next text-link" href={index < agents.length - 1 ? `#${agents[index + 1]!.id}` : '#how'}>{index < agents.length - 1 ? `Up next: ${agents[index + 1]!.name}` : 'See how they work together'}<span aria-hidden="true">↓</span></a>
              </div>
            </article>)}
          </div>
        </section>

        <InvestigationFlow />
        <SupportedIntegrations />
        <Pricing />
      </main>
      <footer className="footer"><a className="brand" href="#" aria-label="Tracehound home"><img className="brand-symbol" src="/tracehound-mark.svg" alt="" width="32" height="32" /><span>Tracehound</span></a><p>Follow the evidence.</p><div className="footer-links"><a href="https://www.linkedin.com/in/yuvraaj-singh/" target="_blank" rel="noopener noreferrer">Meet the developer <span aria-hidden="true">↗</span><span className="sr-only"> (opens in a new tab)</span></a><span>© {year} Tracehound</span></div></footer>
    </>
  )
}

export default App
