import { useState } from 'react'

const stages = [
  { title: 'Start with the alert.', label: 'Scope', description: 'Give Triage a service, symptom, and time window. It turns the alert into a focused investigation for the specialists.', agents: ['Triage'], heading: 'A clear starting point.', detail: 'The investigation stays anchored to the affected service and the period when the symptom appeared.' },
  { title: 'Follow the evidence.', label: 'Investigate', description: 'Logs, Metrics, Dependency, and Deploy examine the same incident from different angles, connecting findings to their sources.', agents: ['Logs', 'Metrics', 'Dependency', 'Deploy'], heading: 'Different signals. Shared context.', detail: 'Errors, latency shifts, service calls, and recent changes are considered together—not as isolated clues.' },
  { title: 'Challenge the explanation.', label: 'Reason', description: 'Hypothesis weighs possible causes against supporting and contradicting evidence, and explains what would confirm or rule them out.', agents: ['Hypothesis'], heading: 'A recent deploy is a lead. Not a verdict.', detail: 'A plausible explanation must fit the evidence. Timing alone does not establish the cause.' },
  { title: 'Know what to check next.', label: 'Review', description: 'Review likely causes, their evidence, and what remains uncertain. The next checks stay in your hands.', agents: ['Hypothesis'], heading: 'An answer you can interrogate.', detail: 'Confidence comes with a rationale. Missing evidence stays visible, alongside the next checks to make.' },
]

export default function InvestigationFlow() {
  const [active, setActive] = useState(0)
  const stage = stages[active]!
  return (
    <section id="how" className="how" aria-labelledby="how-title">
      <div className="section-heading">
        <div><p className="eyebrow">How it works</p><h2 id="how-title">From an alert to<br />an explanation you can inspect.</h2></div>
        <p>Built for the engineer on call. Tracehound connects the signals, considers alternatives, and makes the reasoning visible.</p>
      </div>
      <div className="investigation-flow">
        <div className="flow-controls" aria-label="Investigation stages">
          {stages.map((item, index) => <button key={item.label} type="button" className={`flow-step ${active === index ? 'is-active' : ''}`} aria-pressed={active === index} aria-controls="investigation-preview" onClick={() => setActive(index)}>
            <span className="flow-number">0{index + 1}</span>
            <span><span className="flow-title">{item.title}</span><span className="flow-description">{item.description}</span></span>
            <span className="flow-arrow" aria-hidden="true">↗</span>
          </button>)}
        </div>
        <div className="investigation-preview" id="investigation-preview" role="region" aria-label="Illustrative investigation" aria-live="polite" aria-atomic="true">
          <div className="preview-top"><span>INVESTIGATION BRIEF</span><span>Illustrative example</span></div>
          <div className="preview-intro"><span className="preview-stage">0{active + 1} / {stage.label}</span><h3>{stage.heading}</h3><p>{stage.detail}</p></div>
          <div className="preview-body">
            {active === 0 && <dl className="intake-fields"><div><dt>Service</dt><dd>checkout-api</dd></div><div><dt>Symptom</dt><dd>Elevated latency &amp; timeouts</dd></div><div><dt>Investigation window</dt><dd>14:00–14:15 UTC</dd></div><div><dt>Starting question</dt><dd>Where did the slowdown begin?</dd></div></dl>}
            {active === 1 && <ol className="evidence-list"><li><span className="evidence-time">14:02</span><div><strong>Upstream calls begin timing out</strong><span>Logs · checkout-api · E01</span></div></li><li><span className="evidence-time">14:03</span><div><strong>Retries and latency rise together</strong><span>Metrics · checkout-api · E02</span></div></li><li><span className="evidence-time">14:07</span><div><strong>A new release is deployed</strong><span>Deploy · checkout-api · E03</span></div></li></ol>}
            {active === 2 && <div className="hypothesis-comparison"><div><span className="finding-label">Leading explanation</span><h4>Upstream timeouts, amplified by retries.</h4><p>The timeouts precede the latency increase. Retry traffic rises alongside it. <span className="evidence-ref">E01 · E02</span></p></div><div><span className="finding-label alternative">Alternative considered</span><h4>The latest deployment.</h4><p>It happened after the first timeouts, weakening it as the initial trigger. <span className="evidence-ref">E01 · E03</span></p></div></div>}
            {active === 3 && <div className="review-findings"><div><span className="finding-label">Confidence · Medium</span><p>The timing supports the upstream explanation. Direct upstream telemetry is still missing.</p></div><div><span className="finding-label alternative">Next check</span><p>Inspect upstream latency and checkout retry settings. Check whether retries amplified an existing slowdown.</p></div><div className="human-decision">Investigation informs the decision.<br /><strong>You decide what changes.</strong></div></div>}
          </div>
          <div className="preview-agents"><span>On the case</span><div>{stage.agents.map(name => <span key={name} className="agent-chip"><span style={{ background: `var(--agent-${name.toLowerCase()})` }} />{name}</span>)}</div></div>
        </div>
      </div>
      <div className="principles"><div><span>01</span><h3>Evidence before assertions.</h3><p>Follow findings back to their source, time, and identifier.</p></div><div><span>02</span><h3>Uncertainty stays visible.</h3><p>See what supports an explanation—and what still needs checking.</p></div><div><span>03</span><h3>Read-only by design.</h3><p>Investigate your telemetry. Keep production changes under human control.</p></div></div>
    </section>
  )
}
