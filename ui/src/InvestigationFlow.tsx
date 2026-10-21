import { useEffect, useRef, useState, type CSSProperties } from 'react'

const agentProfiles: Record<string, { name: string, image: string }> = {
  triage: { name: 'Marshal', image: '/agents/triage.png' },
  logs: { name: 'Echo', image: '/agents/logs.png' },
  metrics: { name: 'Pulse', image: '/agents/metrics.png' },
  dependency: { name: 'Tether', image: '/agents/dependency.jpg' },
  deploy: { name: 'Ledger', image: '/agents/deploy.png' },
  hypothesis: { name: 'Sage', image: '/agents/hypothesis.jpg' },
}

const stages = [
  { label: 'Alert', title: 'Scope the incident.', agents: ['triage'], working: 'Marshal is scoping the alert', done: 'Scoped', snapshot: ['checkout-api', 'latency & timeouts', '14:00–14:15 UTC'] },
  { label: 'Investigate', title: 'Follow the evidence.', agents: ['logs', 'metrics', 'dependency', 'deploy'], working: 'Echo, Pulse, Tether & Ledger are gathering evidence', done: '3 findings linked', snapshot: ['E01 upstream timeouts', 'E02 retries climb', 'E03 new release'] },
  { label: 'Reason', title: 'Challenge the explanation.', agents: ['hypothesis'], working: 'Sage is testing explanations', done: 'Lead found', snapshot: ['Lead: upstream timeouts', 'Ruled down: the deploy'] },
  { label: 'Review', title: 'Know what to check next.', agents: ['hypothesis'], working: 'Sage is writing the next checks', done: 'Ready for you', snapshot: ['Confidence: medium', 'Next: upstream latency'] },
]

type Phase = 'travel' | 'working' | 'done'
const TRAVEL_MS = 350
const WORKING_MS = 1800
const HOLD_MS = 700
const LOOP_PAUSE_MS = 1400
const segments = stages.length - 1

/** One ECG-style beat across a segment: flat, a small P bump, a sharp QRS spike, then flat. */
const beatPath = (i: number) => {
  const x = (f: number) => (i + f) * 100
  return `M ${x(0)} 30 L ${x(.38)} 30 Q ${x(.43)} 22 ${x(.48)} 30 L ${x(.54)} 30 L ${x(.57)} 36 L ${x(.61)} 4 L ${x(.65)} 56 L ${x(.68)} 30 L ${x(1)} 30`
}

/** Loops the journey stage by stage once it scrolls into view; click a stage to jump there. */
export default function InvestigationFlow() {
  const root = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(0)
  const [phase, setPhase] = useState<Phase>('working')
  const [playing, setPlaying] = useState(false)
  const finished = active === segments && phase === 'done'

  useEffect(() => {
    const node = root.current
    if (!node) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setActive(segments); setPhase('done'); return }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry?.isIntersecting) { setPlaying(true); observer.disconnect() }
    }, { threshold: .2 })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!playing) return
    const timer = window.setTimeout(() => {
      if (phase === 'travel') setPhase('working')
      else if (phase === 'working') setPhase('done')
      else if (active < segments) { setActive(active + 1); setPhase('travel') }
      else { setActive(0); setPhase('working') }
    }, phase === 'travel' ? TRAVEL_MS : phase === 'working' ? WORKING_MS : finished ? LOOP_PAUSE_MS : HOLD_MS)
    return () => window.clearTimeout(timer)
  }, [active, phase, playing, finished])

  const jump = (index: number) => { setActive(index); setPhase('working') }
  const stateOf = (index: number) => index < active || (index === active && phase === 'done') ? 'is-done' : index === active && phase === 'working' ? 'is-working' : index === active ? 'is-next' : ''
  const status = finished ? 'Alert to next check — starting over…' : phase === 'travel' ? `Handing off to ${stages[active]!.label}…` : phase === 'working' ? `${stages[active]!.working}…` : stages[active]!.done

  return (
    <section id="how" className="how" aria-labelledby="how-title">
      <div className="section-heading">
        <div><p className="eyebrow">How it works</p><h2 id="how-title">From an alert to<br />an explanation you can inspect.</h2></div>
        <p>Built for the engineer on call. Tracehound connects the signals, considers alternatives, and makes the reasoning visible.</p>
      </div>
      <div ref={root} className={`journey ${playing ? 'is-playing' : ''}`} style={{ '--travel-ms': `${TRAVEL_MS}ms`, '--progress': active / segments } as CSSProperties}>
        <svg className="journey-pulse" viewBox={`0 0 ${segments * 100} 60`} preserveAspectRatio="none" aria-hidden="true">
          <path className="pulse-track" d={`M 0 30 L ${segments * 100} 30`} vectorEffect="non-scaling-stroke" />
          {active > 1 && <path className="pulse-line" d={`M 0 30 L ${(active - 1) * 100} 30`} vectorEffect="non-scaling-stroke" />}
          {active > 0 && <g key={active} className={`pulse-beat is-${phase}`}>
            <path className="pulse-glow" d={beatPath(active - 1)} pathLength="1" vectorEffect="non-scaling-stroke" />
            <path className="pulse-line" d={beatPath(active - 1)} pathLength="1" vectorEffect="non-scaling-stroke" />
          </g>}
        </svg>
        <div className="journey-rail" aria-hidden="true"><span /></div>
        <ol className="journey-stages">
          {stages.map((stage, index) => <li key={stage.label} className={stateOf(index)}>
            <button type="button" className="journey-stop" aria-current={index === active ? 'step' : undefined} onClick={() => jump(index)}>
              <span className="journey-node"><span>{stateOf(index) === 'is-done' ? '✓' : `0${index + 1}`}</span></span>
              <span className="journey-label">{stage.label}</span>
              <span className="journey-title">{stage.title}</span>
            </button>
            <div className="journey-souls">
              {stage.agents.map((id, i) => <figure key={id} className="agent-soul" style={{ '--agent-color': `var(--agent-${id})`, '--soul-delay': `${i * 140}ms` } as CSSProperties}>
                <span className="soul-frame"><img src={agentProfiles[id]!.image} alt="" loading="lazy" decoding="async" /></span>
                <figcaption>{agentProfiles[id]!.name}</figcaption>
              </figure>)}
            </div>
            <p className="journey-status">{stateOf(index) === 'is-done' ? <><span className="status-check" aria-hidden="true">✓</span>{stage.done}</> : <>{stage.working}<span className="status-dots" aria-hidden="true"><span /><span /><span /></span></>}</p>
            <ul className="journey-snapshot">{stage.snapshot.map((line, i) => <li key={line} style={{ '--soul-delay': `${i * 120}ms` } as CSSProperties}>{line}</li>)}</ul>
          </li>)}
        </ol>
        <div className="journey-footer">
          <span aria-live="polite">{status}</span>
          {playing && <span className="journey-loop" aria-hidden="true">Live · looping</span>}
        </div>
      </div>
      <div className="principles"><div><span>01</span><h3>Evidence before assertions.</h3><p>Follow findings back to their source, time, and identifier.</p></div><div><span>02</span><h3>Uncertainty stays visible.</h3><p>See what supports an explanation—and what still needs checking.</p></div><div><span>03</span><h3>Read-only by design.</h3><p>Investigate your telemetry. Keep production changes under human control.</p></div></div>
    </section>
  )
}
