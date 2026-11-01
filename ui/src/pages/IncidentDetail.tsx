import { useEffect, useState, type CSSProperties } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError, getIncident, type AgentName, type AgentRun, type Evidence, type Finding, type Hypothesis, type IncidentDetail as Detail, type InvestigationScope, type Severity, type Specialist } from '../lib/api'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'

const POLL_MS = 3000
const specialists: Specialist[] = ['logs', 'metrics', 'deploy', 'dependency']
const agentColor: Record<AgentName, string> = { triage: 'var(--agent-triage)', logs: 'var(--agent-logs)', metrics: 'var(--agent-metrics)', deploy: 'var(--agent-deploy)', dependency: 'var(--agent-dependency)', hypothesis: 'var(--agent-hypothesis)' }
const agentLabel: Record<AgentName, string> = { triage: 'Triage', logs: 'Logs', metrics: 'Metrics', deploy: 'Deploy', dependency: 'Dependency', hypothesis: 'Hypothesis' }
const severityColor: Record<Severity, string> = { critical: 'var(--severity-critical)', high: 'var(--severity-high)', medium: 'var(--severity-medium)', low: 'var(--severity-low)' }

type Load = { status: 'loading' } | { status: 'error', message: string, notFound: boolean } | { status: 'ready', data: Detail }

const formatTime = (iso: string) => new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
const isActive = (state: string) => state === 'CREATED' || state === 'RUNNING'

function duration(run: AgentRun | undefined, now: number) {
  if (!run?.started_at) return null
  const end = run.finished_at ? new Date(run.finished_at).getTime() : now
  const seconds = Math.max(0, (end - new Date(run.started_at).getTime()) / 1000)
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

/** One incident and its stored investigation, polled while the run is still going. */
export default function IncidentDetail() {
  const { incidentId = '' } = useParams()
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const fetchOnce = () => getIncident(incidentId).then(
      (data) => {
        if (!active) return
        setLoad({ status: 'ready', data })
        if (isActive(data.incident.state)) timer = setTimeout(fetchOnce, POLL_MS)
      },
      (err: unknown) => {
        if (!active) return
        const notFound = err instanceof ApiError && err.status === 404
        setLoad({ status: 'error', notFound, message: notFound ? 'This incident doesn’t exist, or it belongs to another account.' : err instanceof Error ? err.message : 'Could not load the incident.' })
      },
    )
    fetchOnce()
    return () => { active = false; clearTimeout(timer) }
  }, [incidentId, attempt])

  return (
    <div className="auth-page">
      <SignedInHeader />
      <main className="workspace incident-detail">
        <Link className="back-link" to="/app/incidents"><span aria-hidden="true">←</span> Dashboard</Link>
        {load.status === 'loading' && <p className="list-state" role="status">Loading incident<span className="status-dots" aria-hidden="true"><span /><span /><span /></span></p>}
        {load.status === 'error' && <div className="list-state" role="alert">
          <p className="form-error">{load.message}</p>
          {!load.notFound && <button type="button" className="button-quiet" onClick={() => { setLoad({ status: 'loading' }); setAttempt((n) => n + 1) }}>Retry</button>}
        </div>}
        {load.status === 'ready' && <DetailBody detail={load.data} />}
      </main>
    </div>
  )
}

function DetailBody({ detail }: { detail: Detail }) {
  const { incident, result } = detail
  const [openEvidence, setOpenEvidence] = useState<string | null>(null)
  const showEvidence = (id: string) => {
    setOpenEvidence(id)
    document.getElementById(`evidence-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  const failed = incident.state === 'FAILED'
  const [top, ...others] = result?.hypotheses ?? []

  return (
    <>
      <header className="workspace-heading detail-heading">
        <div>
          <p className="eyebrow"><span /> Incident</p>
          <h1>{incident.service_id}</h1>
          <p className="detail-symptom">{incident.symptom}</p>
          <p className="incident-meta">
            <span className={`state-badge state-${incident.state.toLowerCase()}`}>{incident.state}</span>
            <span className="incident-severity" style={{ color: severityColor[incident.severity] }}><span className="agent-dot" style={{ background: severityColor[incident.severity] }} />{incident.severity}</span>
            <span>Opened {formatTime(incident.created_at)}</span>
            <span>Window {formatTime(incident.window_start)} → {formatTime(incident.window_end)}</span>
            {incident.trace_id && <span>trace <code>{incident.trace_id}</code></span>}
          </p>
        </div>
      </header>

      {failed && <div className="detail-failure" role="alert">
        <p className="eyebrow">Investigation failed</p>
        <p>{result?.error ?? 'The run failed before storing a reason.'}</p>
        {result && <p className="detail-note">Partial results stored before the failure are shown below.</p>}
      </div>}

      {(isActive(incident.state) || result) && <AgentStrip runs={result?.agent_runs ?? {}} live={isActive(incident.state)} />}

      {!result && <p className="list-state">{isActive(incident.state) ? 'The investigation is starting. Results appear here as agents finish.' : 'No investigation has been stored for this incident yet.'}</p>}

      {result && <>
        <section className="detail-section" aria-labelledby="hyp-title">
          <h2 id="hyp-title" className="detail-title"><span className="agent-dot" style={{ background: agentColor.hypothesis }} />Hypotheses</h2>
          {top ? <HypothesisCard hypothesis={top} primary onEvidence={showEvidence} /> : <p className="list-state">No hypotheses yet.</p>}
          {others.length > 0 && <details className="detail-more">
            <summary>{others.length} other hypothes{others.length === 1 ? 'is' : 'es'}</summary>
            {others.map((h) => <HypothesisCard key={h.id} hypothesis={h} onEvidence={showEvidence} />)}
          </details>}
        </section>

        {result.scope && <Scope scope={result.scope} />}

        <section className="detail-section" aria-labelledby="findings-title">
          <h2 id="findings-title" className="detail-title">Specialist findings</h2>
          <div className="specialist-grid">
            {specialists.map((s) => <SpecialistCard key={s} specialist={s} findings={result.findings.filter((f) => f.specialist === s)} run={result.agent_runs[s]} onEvidence={showEvidence} />)}
          </div>
        </section>

        <section className="detail-section" aria-labelledby="evidence-title">
          <h2 id="evidence-title" className="detail-title">Evidence timeline</h2>
          {result.evidence.length === 0 ? <p className="list-state">No evidence collected.</p> : <ol className="evidence-timeline">
            {result.evidence.map((e) => <EvidenceItem key={e.id} evidence={e} open={openEvidence === e.id} onToggle={() => setOpenEvidence(openEvidence === e.id ? null : e.id)} />)}
          </ol>}
        </section>
      </>}
    </>
  )
}

function AgentStrip({ runs, live }: { runs: Partial<Record<AgentName, AgentRun>>, live: boolean }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!live) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [live])
  const step = (agent: AgentName) => {
    const run = runs[agent]
    const status = run?.status ?? 'pending'
    return (
      <li key={agent} className={`agent-step is-${status}`} style={{ '--agent-color': agentColor[agent] } as CSSProperties} title={run?.error ?? undefined}>
        <span className="agent-dot" />
        <strong>{agentLabel[agent]}</strong>
        <span>{status}{duration(run, now) && ` · ${duration(run, now)}`}</span>
      </li>
    )
  }
  return (
    <section className="agent-strip" aria-label="Agent progress" aria-live={live ? 'polite' : undefined}>
      <ol className="agent-stage">{step('triage')}</ol>
      <span className="agent-arrow" aria-hidden="true">→</span>
      <ol className="agent-stage is-parallel">{specialists.map(step)}</ol>
      <span className="agent-arrow" aria-hidden="true">→</span>
      <ol className="agent-stage">{step('hypothesis')}</ol>
    </section>
  )
}

function EvidenceChips({ ids, onEvidence, label }: { ids: string[], onEvidence: (id: string) => void, label?: string }) {
  if (ids.length === 0) return null
  return (
    <p className="evidence-chips">
      {label && <span className="chip-label">{label}</span>}
      {ids.map((id) => <button key={id} type="button" className="evidence-chip" onClick={() => onEvidence(id)}>{id}</button>)}
    </p>
  )
}

function HypothesisCard({ hypothesis: h, primary, onEvidence }: { hypothesis: Hypothesis, primary?: boolean, onEvidence: (id: string) => void }) {
  return (
    <article className={`detail-card hypothesis${primary ? ' is-primary' : ''}`}>
      <p className="hypothesis-tags"><span className={`band band-${h.confidence}`}>{h.confidence} confidence</span><span className="band">{h.status}</span></p>
      <h3>{h.statement}</h3>
      <p>{h.mechanism}</p>
      <p className="detail-note">{h.confidence_rationale}</p>
      {h.verification_steps.length > 0 && <>
        <p className="eyebrow detail-sub">Verify</p>
        <ul className="verify-list">
          {h.verification_steps.map((v, i) => <li key={i}><input type="checkbox" aria-label={`Mark checked: ${v.check}`} /><span>{v.check} <span className="verify-arrow">→</span> <em>{v.expected_if_true}</em></span></li>)}
        </ul>
      </>}
      <EvidenceChips ids={h.supporting_evidence_ids} label="Supports" onEvidence={onEvidence} />
      <EvidenceChips ids={h.contradicting_evidence_ids} label="Contradicts" onEvidence={onEvidence} />
    </article>
  )
}

function Scope({ scope }: { scope: InvestigationScope }) {
  return (
    <section className="detail-section" aria-labelledby="scope-title">
      <h2 id="scope-title" className="detail-title"><span className="agent-dot" style={{ background: agentColor.triage }} />Triage scope</h2>
      <div className="detail-card">
        <p>{scope.rationale}</p>
        <p className="incident-meta">
          <span>Services</span><span>{scope.services.join(', ')}</span>
        </p>
        <p className="incident-meta">
          <span>Changes since</span><span>{formatTime(scope.change_window_start)}</span>
          <span>Symptom</span><span>{formatTime(scope.symptom_window_start)} → {formatTime(scope.symptom_window_end)}</span>
        </p>
        <ul className="scope-tasks">
          {scope.tasks.map((t) => <li key={t.specialist} style={{ '--agent-color': agentColor[t.specialist] } as CSSProperties}>
            <strong>{agentLabel[t.specialist]}</strong> <span>{t.question}</span> <span className="detail-note">{t.services.join(', ')}</span>
          </li>)}
        </ul>
      </div>
    </section>
  )
}

function SpecialistCard({ specialist, findings, run, onEvidence }: { specialist: Specialist, findings: Finding[], run?: AgentRun, onEvidence: (id: string) => void }) {
  return (
    <article className="detail-card specialist-card" style={{ '--agent-color': agentColor[specialist] } as CSSProperties}>
      <p className="eyebrow"><span /> {agentLabel[specialist]}</p>
      {run?.status === 'failed' && <p className="form-error">{run.error ?? 'This agent failed.'}</p>}
      {findings.length === 0 ? <p className="detail-note">{run ? (run.status === 'running' ? 'Investigating…' : 'No findings.') : 'Not dispatched.'}</p> : <ul className="finding-list">
        {findings.map((f, i) => <li key={i}><p>{f.claim}</p><EvidenceChips ids={f.evidence_ids} onEvidence={onEvidence} /></li>)}
      </ul>}
    </article>
  )
}

function EvidenceItem({ evidence: e, open, onToggle }: { evidence: Evidence, open: boolean, onToggle: () => void }) {
  return (
    <li id={`evidence-${e.id}`} className={`evidence-item${open ? ' is-open' : ''}`}>
      <button type="button" className="evidence-head" aria-expanded={open} onClick={onToggle}>
        <time dateTime={e.event_time}>{formatTime(e.event_time)}</time>
        <span>{e.service}</span>
        <span className="band">{e.source_type}</span>
        <code className="evidence-id">{e.id}</code>
      </button>
      <pre className="evidence-excerpt">{e.excerpt}</pre>
      {open && <p className="detail-note evidence-locator"><code>{e.source_locator}</code></p>}
    </li>
  )
}
