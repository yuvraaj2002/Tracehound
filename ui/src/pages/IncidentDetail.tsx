import { createContext, useContext, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError, getIncident, type AgentName, type AgentRun, type Evidence, type EvidenceSource, type Finding, type Hypothesis, type IncidentDetail as Detail, type InvestigationResult, type InvestigationScope, type Severity, type Specialist, type SpecialistTask } from '../lib/api'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'
import '../IncidentDetail.css'

const POLL_MS = 3000
const specialists: Specialist[] = ['logs', 'metrics', 'deploy', 'dependency']
const agentColor: Record<AgentName, string> = { triage: 'var(--agent-triage)', logs: 'var(--agent-logs)', metrics: 'var(--agent-metrics)', deploy: 'var(--agent-deploy)', dependency: 'var(--agent-dependency)', hypothesis: 'var(--agent-hypothesis)' }
const agentLabel: Record<AgentName, string> = { triage: 'Triage', logs: 'Logs', metrics: 'Metrics', deploy: 'Deploy', dependency: 'Dependency', hypothesis: 'Hypothesis' }
const severityColor: Record<Severity, string> = { critical: 'var(--severity-critical)', high: 'var(--severity-high)', medium: 'var(--severity-medium)', low: 'var(--severity-low)' }
const sourceLabel: Record<EvidenceSource, string> = { log: 'Logs', metric: 'Metrics', trace: 'Traces', deploy: 'Deploys' }
const confidenceLevel = { low: 1, medium: 2, high: 3 } as const
const STATUS_WORDS = new Set(['proposed', 'supported', 'refuted', 'inconclusive'])

type Load = { status: 'loading' } | { status: 'error', message: string, notFound: boolean } | { status: 'ready', data: Detail }

const stamp = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
const clock = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
const formatStamp = (iso: string) => `${stamp.format(new Date(iso))} UTC`
const formatClock = (iso: string) => clock.format(new Date(iso))
/** The incident's own service, so evidence only names its service when it comes from elsewhere. */
const HomeService = createContext('')
const isActive = (state: string) => state === 'CREATED' || state === 'RUNNING'
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

function span(from: string | null | undefined, to: string | null | undefined, now: number) {
  if (!from) return null
  const end = to ? new Date(to).getTime() : now
  const seconds = Math.max(0, (end - new Date(from).getTime()) / 1000)
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

/** A hypothesis's statement is sometimes just its status word; fall back to the mechanism then. */
function headline(h: Hypothesis) {
  const bare = STATUS_WORDS.has(h.statement.trim().toLowerCase()) || h.statement.trim().length < 12
  return bare ? { title: h.mechanism, detail: null } : { title: h.statement, detail: h.mechanism }
}

const levelOf = (e: Evidence) => typeof e.metadata.level === 'string' ? e.metadata.level.toUpperCase() : null

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

function useNow(live: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!live) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [live])
  return now
}

function DetailBody({ detail }: { detail: Detail }) {
  const { incident, result } = detail
  const live = isActive(incident.state)
  const now = useNow(live)
  const [openEvidence, setOpenEvidence] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>({ source: null, service: null })
  const [cursor, setCursor] = useState<number | null>(null)
  const evidenceById = useMemo(() => new Map((result?.evidence ?? []).map((e) => [e.id, e])), [result])
  const citedBy = useMemo(() => citations(result), [result])

  const showEvidence = (id: string) => {
    setFilter({ source: null, service: null })
    setOpenEvidence(id)
    // Wait a frame so a filtered-out row is back in the DOM.
    requestAnimationFrame(() => document.getElementById(`evidence-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  }
  const [top, ...others] = result?.hypotheses ?? []
  const ran = (s: Specialist) => !!result?.agent_runs[s] || !!result?.scope?.tasks.some((t) => t.specialist === s)
  const gantt = <RunGantt runs={result?.agent_runs ?? {}} scope={result?.scope ?? null} started={result?.started_at ?? null} live={live} now={now} />
  const failedAgents = (Object.entries(result?.agent_runs ?? {}) as [AgentName, AgentRun][]).filter(([, run]) => run.status === 'failed')

  return (
    <HomeService.Provider value={incident.service_id}>
      <header className="inc-head">
        <p className="inc-badges">
          <span className={`state-badge state-${incident.state.toLowerCase()}`}>{live && <span className="inc-live" aria-hidden="true" />}{incident.state}</span>
          <span className="inc-severity" style={{ '--sev': severityColor[incident.severity] } as CSSProperties}><span aria-hidden="true" />{incident.severity} severity</span>
        </p>
        <h1>{incident.service_id}</h1>
        <p className="inc-symptom">{incident.symptom}</p>
        <dl className="inc-facts">
          <div><dt>Opened</dt><dd>{formatStamp(incident.created_at)}</dd></div>
          <div><dt>Symptom window</dt><dd>{formatClock(incident.window_start)} → {formatClock(incident.window_end)} <span>{span(incident.window_start, incident.window_end, now)}</span></dd></div>
          <div><dt>Investigation</dt><dd>{span(result?.started_at, result?.finished_at, now) ?? '—'}{live && <span> running</span>}</dd></div>
          {incident.trace_id && <div><dt>Trace</dt><dd><code>{incident.trace_id}</code></dd></div>}
        </dl>
      </header>

      {live && gantt}

      {incident.state === 'FAILED' && <section className="inc-failure" role="alert">
        <h2>Investigation failed</h2>
        {(!failedAgents.length || !failedAgents.some(([, run]) => run.error && result?.error?.includes(run.error))) && <p>{result?.error ?? 'The run failed before storing a reason.'}</p>}
        {failedAgents.length > 0 && <ul>
          {failedAgents.map(([agent, run]) => <li key={agent}><strong style={{ color: agentColor[agent] }}>{agentLabel[agent]}</strong><span>{run.error ?? 'Failed.'}</span></li>)}
        </ul>}
        {result && <p className="inc-quiet">Anything stored before the failure is shown below.</p>}
      </section>}

      {!result && <p className="list-state">{live ? 'The investigation is starting. Results appear here as agents finish.' : 'No investigation has been stored for this incident yet.'}</p>}

      {result && <div className="inc-layout">
        <div className="inc-main">
          <Section title="Most likely cause" color={agentColor.hypothesis}>
            {top ? <HypothesisCard hypothesis={top} primary evidence={evidenceById} onEvidence={showEvidence} /> : <p className="inc-empty">{live ? 'The hypothesis agent hasn’t run yet.' : 'No hypotheses were produced.'}</p>}
            {others.length > 0 && <div className="inc-others">
              <h3>Other hypotheses <span>{others.length}</span></h3>
              {others.map((h) => <HypothesisCard key={h.id} hypothesis={h} evidence={evidenceById} onEvidence={showEvidence} />)}
            </div>}
          </Section>

          {result.evidence.length > 0 && <EventTimeline evidence={result.evidence} windowStart={incident.window_start} windowEnd={incident.window_end} cursor={cursor} onCursor={setCursor} onEvidence={showEvidence} citedBy={citedBy} />}

          {specialists.filter(ran).map((s) => <AgentSection key={s} specialist={s} task={result.scope?.tasks.find((t) => t.specialist === s)} findings={result.findings.filter((f) => f.specialist === s)} run={result.agent_runs[s]} evidence={evidenceById} onEvidence={showEvidence} live={live} now={now} />)}
          {specialists.some((s) => !ran(s)) && <p className="inc-skipped">Not dispatched for this incident: {specialists.filter((s) => !ran(s)).map((s) => agentLabel[s]).join(', ')}.</p>}

          <Section title="All evidence" count={result.evidence.length}>
            <Timeline cursor={cursor} evidence={result.evidence} open={openEvidence} onOpen={setOpenEvidence} filter={filter} onFilter={setFilter} citedBy={citedBy} />
          </Section>

          {!live && <details className="inc-process"><summary>How the investigation ran <span>{span(result.started_at, result.finished_at, now)}</span></summary>{gantt}</details>}
        </div>

        <aside className="inc-aside" aria-label="Investigation context">
          {result.scope ? <ScopeCard scope={result.scope} /> : <p className="inc-empty">Triage hasn’t produced a scope yet.</p>}
        </aside>
      </div>}
    </HomeService.Provider>
  )
}

function Section({ title, color, count, children }: { title: string, color?: string, count?: number, children: ReactNode }) {
  return (
    <section className="inc-section">
      <h2>{color && <span className="inc-dot" style={{ background: color }} aria-hidden="true" />}{title}{count !== undefined && <span className="inc-count">{count}</span>}</h2>
      {children}
    </section>
  )
}

/** Who relies on each piece of evidence: hypotheses (for/against) and agent findings. */
function citations(result: InvestigationResult | null) {
  const map = new Map<string, string[]>()
  const add = (id: string, label: string) => map.set(id, [...(map.get(id) ?? []), label])
  result?.hypotheses.forEach((h, i) => {
    h.supporting_evidence_ids.forEach((id) => add(id, `H${i + 1} supports`))
    h.contradicting_evidence_ids.forEach((id) => add(id, `H${i + 1} contradicts`))
  })
  result?.findings.forEach((f) => f.evidence_ids.forEach((id) => add(id, agentLabel[f.specialist])))
  return map
}

const agentOrder: AgentName[] = ['triage', 'logs', 'metrics', 'deploy', 'dependency', 'hypothesis']

/** One bar per agent, placed by when it really ran, so parallel specialists overlap. */
function RunGantt({ runs, scope, started, live, now }: { runs: Partial<Record<AgentName, AgentRun>>, scope: InvestigationScope | null, started: string | null, live: boolean, now: number }) {
  const times = Object.values(runs).flatMap((r) => [r.started_at, r.finished_at]).filter((t): t is string => !!t).map((t) => Date.parse(t))
  const t0 = Math.min(...times, started ? Date.parse(started) : Infinity)
  const t1 = Math.max(...times, live ? now : 0)
  const total = Math.max(t1 - t0, 1000)
  const ticks = [0, 0.25, 0.5, 0.75, 1]
  return (
    <section className="inc-gantt" aria-label="Agent progress" aria-live={live ? 'polite' : undefined}>
      {live && <h2 className="inc-gantt-title">Investigation run <span>{span(new Date(t0).toISOString(), new Date(t1).toISOString(), now) ?? ''}</span></h2>}
      <div className="inc-gantt-rows">
        {agentOrder.map((agent) => {
          const run = runs[agent]
          const dispatched = agent === 'triage' || agent === 'hypothesis' || (scope?.tasks.some((t) => t.specialist === agent) ?? false)
          if (!run && !dispatched) return null // never dispatched: nothing happened, so no row
          const status = run?.status ?? 'pending'
          const left = run?.started_at ? ((Date.parse(run.started_at) - t0) / total) * 100 : 0
          const end = run?.finished_at ? Date.parse(run.finished_at) : now
          const width = run?.started_at ? Math.max(((end - Date.parse(run.started_at)) / total) * 100, 1.2) : 0
          return (
            <div key={agent} className={`inc-gantt-row is-${status}`} style={{ '--agent-color': agentColor[agent] } as CSSProperties} title={run?.error ?? undefined}>
              <span className="inc-gantt-label"><span className="inc-dot" aria-hidden="true" />{agentLabel[agent]}</span>
              <span className="inc-gantt-track">
                {run?.started_at ? <span className="inc-gantt-bar" style={{ left: `${left}%`, width: `${width}%` }} /> : null}
                <span className="inc-gantt-note" style={run?.started_at ? (left + width > 86 ? { left: 'auto', right: `${100 - left - width}%`, marginRight: 8, color: 'var(--color-bg)' } : { left: `${left + width}%` }) : undefined}>{run?.started_at ? `${status === 'completed' ? '' : `${status} · `}${span(run.started_at, run.finished_at, now)}` : status}</span>
              </span>
            </div>
          )
        })}
      </div>
      <div className="inc-gantt-axis" aria-hidden="true"><span className="inc-gantt-label" />
        <span className="inc-gantt-track">{ticks.map((t) => <span key={t} style={{ left: `${t * 100}%` }}>{t === 0 ? '0s' : `${((total * t) / 1000).toFixed(total < 10000 ? 1 : 0)}s`}</span>)}</span>
      </div>
    </section>
  )
}

const tickClock = (ms: number, spanMs: number) => `${clock.format(new Date(ms))}${spanMs < 20000 ? `.${String(Math.floor(ms % 1000)).padStart(3, '0')}` : ''}`

/** Every piece of evidence on a time axis, one lane per service, with a scrubber to travel through it. */
function EventTimeline({ evidence, windowStart, windowEnd, cursor, onCursor, onEvidence, citedBy }: { evidence: Evidence[], windowStart: string, windowEnd: string, cursor: number | null, onCursor: (t: number | null) => void, onEvidence: (id: string) => void, citedBy: Map<string, string[]> }) {
  const [zoom, setZoom] = useState<boolean | null>(null)
  const [playing, setPlaying] = useState(false)
  const times = evidence.map((e) => Date.parse(e.event_time))
  const winS = Date.parse(windowStart)
  const winE = Date.parse(windowEnd)
  const fullS = Math.min(winS, ...times)
  const fullE = Math.max(winE, ...times)
  const evS = Math.min(...times)
  const evE = Math.max(...times)
  const pad = Math.max((evE - evS) * 0.15, 1000)
  const clustered = (evE - evS) / (fullE - fullS) < 0.25
  const zoomed = zoom ?? clustered
  const [d0, d1] = zoomed ? [evS - pad, evE + pad] : [fullS - (fullE - fullS) * 0.02, fullE + (fullE - fullS) * 0.02]
  const range = d1 - d0
  const pct = (t: number) => Math.min(100, Math.max(0, ((t - d0) / range) * 100))
  const services = [...new Set(evidence.map((e) => e.service))].sort()
  const firstError = evidence.find((e) => levelOf(e) === 'ERROR')

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => {
      const next = (cursor === null || cursor >= d1 ? d0 : cursor) + range / 120
      if (next >= d1) setPlaying(false)
      onCursor(Math.min(next, d1))
    }, 60)
    return () => clearInterval(id)
  }, [playing, cursor, d0, d1, range, onCursor])

  const at = cursor ?? d1
  const seen = times.filter((t) => t <= at).length
  const bandL = pct(winS)
  const bandR = pct(winE)
  return (
    <section className="inc-events" aria-label="Incident timeline">
      <header>
        <h2>Incident timeline <span className="inc-count">{evidence.length}</span></h2>
        <div className="inc-events-tools">
          <button type="button" className="inc-chip" aria-pressed={playing} onClick={() => { if (playing) setPlaying(false); else { if (cursor === null || cursor >= d1) onCursor(d0); setPlaying(true) } }}>{playing ? 'Pause' : 'Play'}</button>
          <button type="button" className="inc-chip" aria-pressed={zoomed} onClick={() => { setZoom(!zoomed); onCursor(null); setPlaying(false) }}>{zoomed ? 'Zoom: evidence' : 'Zoom: full window'}</button>
          {cursor !== null && <button type="button" className="inc-chip" onClick={() => { onCursor(null); setPlaying(false) }}>Show all</button>}
        </div>
      </header>
      <div className="inc-events-plot">
        {services.map((service) => (
          <div key={service} className="inc-lane">
            <span className="inc-gantt-label">{service}</span>
            <span className="inc-lane-track">
              {evidence.filter((e) => e.service === service).map((e) => {
                const t = Date.parse(e.event_time)
                const level = levelOf(e)
                return <button key={e.id} type="button" className={`inc-mark${level ? ` is-${level.toLowerCase()}` : ''}${citedBy.has(e.id) ? ' is-cited' : ''}${t > at ? ' is-future' : ''}`} style={{ left: `${pct(t)}%` }} onClick={() => onEvidence(e.id)} title={`${tickClock(t, range)} · ${level ?? e.source_type} · ${e.excerpt.slice(0, 90)}`} aria-label={`${e.service} ${level ?? e.source_type} at ${tickClock(t, range)}`} />
              })}
            </span>
          </div>
        ))}
        <div className="inc-overlay" aria-hidden="true"><span className="inc-gantt-label" />
          <span className="inc-lane-track">
            {bandR > bandL && <span className="inc-band" style={{ left: `${bandL}%`, width: `${bandR - bandL}%` }}><em>symptom window</em></span>}
            {firstError && <span className="inc-first" style={{ left: `${pct(Date.parse(firstError.event_time))}%` }}><em>first error</em></span>}
            {cursor !== null && <span className="inc-playhead" style={{ left: `${pct(cursor)}%` }}><em>{tickClock(cursor, range)}</em></span>}
          </span>
        </div>
        <div className="inc-gantt-axis" aria-hidden="true"><span className="inc-gantt-label" />
          <span className="inc-gantt-track">{[0, 0.25, 0.5, 0.75, 1].map((f) => <span key={f} style={{ left: `${f * 100}%` }}>{tickClock(d0 + range * f, range)}</span>)}</span>
        </div>
      </div>
      <label className="inc-scrub">
        <span>{cursor === null ? 'Drag to travel through the incident' : `${seen} of ${evidence.length} events up to ${tickClock(cursor, range)}`}</span>
        <input type="range" min={d0} max={d1} step={range / 400} value={at} onChange={(e) => { setPlaying(false); onCursor(Number(e.target.value)) }} aria-label="Time cursor" />
      </label>
    </section>
  )
}

function HypothesisCard({ hypothesis: h, primary, evidence, onEvidence }: { hypothesis: Hypothesis, primary?: boolean, evidence: Map<string, Evidence>, onEvidence: (id: string) => void }) {
  const { title, detail } = headline(h)
  const body = (
    <>
      {detail && <p className="inc-mechanism">{detail}</p>}
      <p className="inc-rationale"><strong>Why this confidence:</strong> {h.confidence_rationale}</p>
      <EvidenceList label="Supporting evidence" ids={h.supporting_evidence_ids} evidence={evidence} onEvidence={onEvidence} />
      <EvidenceList label="Contradicting evidence" ids={h.contradicting_evidence_ids} evidence={evidence} onEvidence={onEvidence} against />
      {h.verification_steps.length > 0 && <div className="inc-verify">
        <h4>How to verify</h4>
        <ol>{h.verification_steps.map((v, i) => <li key={i}><span>{v.check}</span><em>Expect: {v.expected_if_true}</em></li>)}</ol>
      </div>}
    </>
  )
  const head = (
    <>
      <span className="inc-meter" role="img" aria-label={`${h.confidence} confidence`} data-level={confidenceLevel[h.confidence]}><i /><i /><i /></span>
      <span className="inc-hyp-tags"><span className={`inc-confidence is-${h.confidence}`}>{h.confidence} confidence</span><span className={`inc-status is-${h.status}`}>{h.status}</span></span>
      {primary ? <h3>{title}</h3> : <span className="inc-hyp-title">{title}</span>}
    </>
  )
  if (primary) return <article className="inc-hyp is-primary">{head}{body}</article>
  return <details className="inc-hyp"><summary>{head}</summary>{body}</details>
}

function EvidenceList({ label, ids, evidence, onEvidence, against }: { label: string, ids: string[], evidence: Map<string, Evidence>, onEvidence: (id: string) => void, against?: boolean }) {
  if (ids.length === 0) return null
  return (
    <div className={`inc-cites${against ? ' is-against' : ''}`}>
      <h4>{label} <span>{ids.length}</span></h4>
      <QuoteList ids={ids} evidence={evidence} onEvidence={onEvidence} />
    </div>
  )
}

/** Cited lines as one-liners. Routine repeats fold into one row with a count; errors never fold. */
function QuoteList({ ids, evidence, onEvidence }: { ids: string[], evidence: Map<string, Evidence>, onEvidence: (id: string) => void }) {
  const rows: { e?: Evidence, id: string, count: number }[] = []
  const seen = new Map<string, number>()
  for (const id of ids) {
    const e = evidence.get(id)
    const loud = e ? ['ERROR', 'WARN'].includes(levelOf(e) ?? '') : true
    const key = e && !loud ? `${e.service}|${template(e.excerpt)}` : id
    const at = seen.get(key)
    if (at === undefined) { seen.set(key, rows.length); rows.push({ e, id, count: 1 }) } else rows[at].count += 1
  }
  return <ul className="inc-quotes">{rows.map((r) => <li key={r.id}><EvidenceQuote id={r.id} evidence={r.e} count={r.count} onEvidence={onEvidence} /></li>)}</ul>
}

function EvidenceQuote({ id, evidence: e, count, onEvidence }: { id: string, evidence?: Evidence, count: number, onEvidence: (id: string) => void }) {
  const home = useContext(HomeService)
  if (!e) return <span className="inc-quote is-missing"><code>{id}</code> isn’t in the stored evidence.</span>
  const level = levelOf(e)
  const loud = level === 'ERROR' || level === 'WARN'
  return (
    <button type="button" className={`inc-quote${loud ? ` is-${level.toLowerCase()}` : ''}`} onClick={() => onEvidence(id)} title={`${e.excerpt}\n\nShow in the evidence log`}>
      <time dateTime={e.event_time}>{formatClock(e.event_time)}</time>
      {loud ? <span className={`inc-level is-${level.toLowerCase()}`}>{level}</span> : <span />}
      <span className="inc-quote-text">{e.service !== home && <b>{e.service} </b>}{e.excerpt}</span>
      {count > 1 && <span className="inc-fold">×{count}</span>}
    </button>
  )
}

/** A specialist's own section: what it was asked, how its run went, and what it found. */
function AgentSection({ specialist, task, findings, run, evidence, onEvidence, live, now }: { specialist: Specialist, task?: SpecialistTask, findings: Finding[], run?: AgentRun, evidence: Map<string, Evidence>, onEvidence: (id: string) => void, live: boolean, now: number }) {
  const dispatched = !!task || !!run
  const status = run?.status ?? (dispatched && live ? 'pending' : 'skipped')
  const cited = new Set(findings.flatMap((f) => f.evidence_ids)).size
  let note = ''
  if (status === 'running' || status === 'pending') note = 'Investigating…'
  else if (!dispatched) note = 'Triage didn’t dispatch this agent for this incident.'
  else if (findings.length === 0 && status !== 'failed') note = 'Ran, but found nothing to report.'
  return (
    <section id={`agent-${specialist}`} className={`inc-agent${dispatched ? '' : ' is-quiet'}`} style={{ '--agent-color': agentColor[specialist] } as CSSProperties} aria-labelledby={`agent-${specialist}-title`}>
      <header>
        <h2 id={`agent-${specialist}-title`}><span className="inc-dot" aria-hidden="true" />{agentLabel[specialist]}</h2>
        <span className={`inc-run is-${status}`}>{status === 'skipped' ? 'not dispatched' : status}{run?.started_at && ` · ${span(run.started_at, run.finished_at, now)}`}</span>
        {cited > 0 && <span className="inc-run-meta">{plural(cited, 'cited line')}</span>}
      </header>
      {task && <p className="inc-ask"><span>Asked</span>{task.question}<em>{task.services.join(', ')}</em></p>}
      {run?.status === 'failed' && <p className="inc-agent-error">{run.error ?? 'This agent failed.'}</p>}
      {note && <p className="inc-quiet">{note}</p>}
      {findings.length > 0 && <ol className="inc-claims">
        {findings.map((f, i) => <li key={i}>
          <p>{f.claim}</p>
          <QuoteList ids={f.evidence_ids} evidence={evidence} onEvidence={onEvidence} />
        </li>)}
      </ol>}
    </section>
  )
}

type Filter = { source: EvidenceSource | null, service: string | null }

/** Lines that differ only by ids and numbers share a template, so routine repeats can fold together. */
const template = (text: string) => text.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}|\d+/gi, '·')
const hypothesisTags = (labels: string[] | undefined) => [...new Set(labels ?? [])].filter((l) => /^H\d/.test(l)).map((l) => l.replace(' supports', ' ✓').replace(' contradicts', ' ✗'))

type Group = { key: string, lines: Evidence[] }

function Timeline({ cursor, evidence, open, onOpen, filter, onFilter, citedBy }: { cursor: number | null, evidence: Evidence[], open: string | null, onOpen: (id: string | null) => void, filter: Filter, onFilter: (f: Filter) => void, citedBy: Map<string, string[]> }) {
  const [importantOnly, setImportantOnly] = useState(false)
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set())
  if (evidence.length === 0) return <p className="inc-empty">No evidence was collected.</p>
  const sources = [...new Set(evidence.map((e) => e.source_type))]
  const services = [...new Set(evidence.map((e) => e.service))].sort()
  const important = (e: Evidence) => ['ERROR', 'WARN'].includes(levelOf(e) ?? '') || citedBy.has(e.id)
  const shown = evidence.filter((e) => (!filter.source || e.source_type === filter.source) && (!filter.service || e.service === filter.service) && (!importantOnly || important(e)))
  // Errors and warnings always stand alone; routine lines with the same template fold into one row.
  const groups: Group[] = []
  const byKey = new Map<string, Group>()
  for (const e of shown) {
    const loud = ['ERROR', 'WARN'].includes(levelOf(e) ?? '')
    const key = loud ? e.id : `${e.service}|${levelOf(e)}|${template(e.excerpt)}`
    const group = byKey.get(key)
    if (group) group.lines.push(e)
    else { const g = { key, lines: [e] }; byKey.set(key, g); groups.push(g) }
  }
  const folded = shown.length - groups.length
  const toggleGroup = (key: string) => setOpenGroups((prev) => { const next = new Set(prev); if (!next.delete(key)) next.add(key); return next })
  const showChips = sources.length > 1 || services.length > 1
  return (
    <>
      <div className="inc-filters" role="group" aria-label="Filter evidence">
        <button type="button" className="inc-chip" aria-pressed={importantOnly} onClick={() => setImportantOnly(!importantOnly)}>Errors &amp; cited only</button>
        {showChips && <span className="inc-chip-sep" aria-hidden="true" />}
        {sources.length > 1 && sources.map((s) => <button key={s} type="button" className="inc-chip" aria-pressed={filter.source === s} onClick={() => onFilter({ ...filter, source: filter.source === s ? null : s })}>{sourceLabel[s]}</button>)}
        {services.length > 1 && services.map((s) => <button key={s} type="button" className="inc-chip" aria-pressed={filter.service === s} onClick={() => onFilter({ ...filter, service: filter.service === s ? null : s })}>{s}</button>)}
        {services.length === 1 && <span className="inc-filters-note">All from <strong>{services[0]}</strong>{sources.length === 1 && ` · ${sourceLabel[sources[0]].toLowerCase()}`}</span>}
        {folded > 0 && <span className="inc-filters-note is-right">{folded} repeated line{folded === 1 ? '' : 's'} folded</span>}
      </div>
      {groups.length === 0 ? <p className="inc-empty">Nothing matches these filters.</p> : <ol className="inc-timeline">
        {groups.map((g) => {
          const future = cursor !== null && g.lines.every((e) => Date.parse(e.event_time) > cursor)
          return g.lines.length === 1
            ? <TimelineRow key={g.key} future={future} evidence={g.lines[0]} showService={services.length > 1} open={open === g.lines[0].id} onToggle={() => onOpen(open === g.lines[0].id ? null : g.lines[0].id)} tags={hypothesisTags(citedBy.get(g.lines[0].id))} />
            : <GroupRow key={g.key} future={future} lines={g.lines} showService={services.length > 1} open={openGroups.has(g.key) || g.lines.some((e) => e.id === open)} onToggle={() => toggleGroup(g.key)} citedBy={citedBy} />
        })}
      </ol>}
    </>
  )
}

function Tags({ tags }: { tags: string[] }) {
  return tags.length ? <span className="inc-cited">{tags.map((t) => <span key={t} className={t.endsWith('✗') ? 'is-against' : undefined}>{t}</span>)}</span> : null
}

function GroupRow({ future, lines, showService, open, onToggle, citedBy }: { future: boolean, lines: Evidence[], showService: boolean, open: boolean, onToggle: () => void, citedBy: Map<string, string[]> }) {
  const first = lines[0]
  const level = levelOf(first)
  const tags = [...new Set(lines.flatMap((e) => hypothesisTags(citedBy.get(e.id))))]
  return (
    <li className={`inc-row is-group${future ? ' is-future' : ''}${open ? ' is-open' : ''}`}>
      <button type="button" className="inc-row-head" aria-expanded={open} onClick={onToggle}>
        <time dateTime={first.event_time}>{formatClock(first.event_time)}</time>
        <span className={`inc-level is-${(level ?? '').toLowerCase()}`}>{level ?? first.source_type}</span>
        <span className="inc-row-text">{showService && <b>{first.service}</b>}{template(first.excerpt).replace(/·/g, '…')}</span>
        <span className="inc-fold">×{lines.length}</span>
        <Tags tags={tags} />
      </button>
      {open && <ul className="inc-group-lines">
        {lines.map((e) => <li key={e.id} id={`evidence-${e.id}`}><time dateTime={e.event_time}>{formatClock(e.event_time)}</time><code>{e.excerpt}</code><Tags tags={hypothesisTags(citedBy.get(e.id))} /></li>)}
      </ul>}
    </li>
  )
}

function TimelineRow({ future, evidence: e, showService, open, onToggle, tags }: { future: boolean, evidence: Evidence, showService: boolean, open: boolean, onToggle: () => void, tags: string[] }) {
  const level = levelOf(e)
  const extra = Object.entries(e.metadata).filter(([k, v]) => k !== 'level' && v !== null && v !== '')
  return (
    <li id={`evidence-${e.id}`} className={`inc-row${future ? ' is-future' : ''}${open ? ' is-open' : ''}${level ? ` lvl-${level.toLowerCase()}` : ''}`}>
      <button type="button" className="inc-row-head" aria-expanded={open} onClick={onToggle}>
        <time dateTime={e.event_time}>{formatClock(e.event_time)}</time>
        {level ? <span className={`inc-level is-${level.toLowerCase()}`}>{level}</span> : <span className="inc-source">{e.source_type}</span>}
        <span className="inc-row-text">{showService && <b>{e.service}</b>}{e.excerpt}</span>
        <span />
        <Tags tags={tags} />
      </button>
      {open && <div className="inc-row-body">
        <pre>{e.excerpt}</pre>
        <p className="inc-row-meta"><span>{formatStamp(e.event_time)}</span><code>{e.source_locator}</code>{extra.map(([k, v]) => <span key={k}>{k} <code>{String(v)}</code></span>)}</p>
      </div>}
    </li>
  )
}

function ScopeCard({ scope }: { scope: InvestigationScope }) {
  return (
    <section className="inc-card">
      <h2><span className="inc-dot" style={{ background: agentColor.triage }} aria-hidden="true" />Triage scope</h2>
      <p className="inc-rationale">{scope.rationale}</p>
      <h4>Services in scope</h4>
      <p className="inc-tags">{scope.services.map((s) => <span key={s} className={s === scope.alert_service ? 'is-alert' : undefined}>{s}</span>)}</p>
      <h4>Windows</h4>
      <dl className="inc-windows">
        <div><dt>Changes since</dt><dd>{formatStamp(scope.change_window_start)}</dd></div>
        <div><dt>Symptom</dt><dd>{formatClock(scope.symptom_window_start)} → {formatClock(scope.symptom_window_end)}</dd></div>
      </dl>
      <h4>Questions asked</h4>
      <ul className="inc-tasks">
        {scope.tasks.map((t) => <li key={t.specialist} style={{ '--agent-color': agentColor[t.specialist] } as CSSProperties}><strong>{agentLabel[t.specialist]}</strong><span>{t.question}</span></li>)}
      </ul>
    </section>
  )
}
