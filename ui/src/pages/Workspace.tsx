import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../auth/context'
import { createIncident, listIncidents, type Incident, type Severity } from '../lib/api'
import '../auth.css'

const severities: Severity[] = ['low', 'medium', 'high', 'critical']
const severityColor: Record<Severity, string> = { low: 'var(--agent-metrics)', medium: 'var(--color-tertiary)', high: 'var(--agent-logs)', critical: 'var(--agent-logs)' }

// <input type="datetime-local"> speaks local wall-clock time without a zone.
const toLocalInput = (date: Date) => new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
const formatTime = (iso: string) => new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

type Load = { status: 'loading' } | { status: 'ready', incidents: Incident[] } | { status: 'error', message: string }

const fetchIncidents = (): Promise<Load> => listIncidents().then(
  (incidents) => ({ status: 'ready', incidents }),
  (err: unknown) => ({ status: 'error', message: err instanceof Error ? err.message : 'Could not load incidents.' }),
)

export default function Workspace() {
  const { user, signOut } = useAuth()
  const meta = (user?.user_metadata ?? {}) as { avatar_url?: string, picture?: string, full_name?: string, name?: string, user_name?: string }
  const name = meta.full_name ?? meta.name ?? meta.user_name ?? user?.email ?? 'Signed in'
  const avatar = meta.avatar_url ?? meta.picture

  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const refresh = useCallback(() => fetchIncidents().then(setLoad), [])
  useEffect(() => {
    let active = true
    fetchIncidents().then((next) => { if (active) setLoad(next) })
    return () => { active = false }
  }, [])

  return (
    <div className="auth-page">
      <header className="nav">
        <Link className="brand" to="/" aria-label="Tracehound home"><img className="brand-symbol" src="/tracehound-mark.svg" alt="" width="40" height="40" /><span>Tracehound</span></Link>
        <div className="account">
          {avatar ? <img className="account-avatar" src={avatar} alt="" width="36" height="36" referrerPolicy="no-referrer" /> : <span className="account-avatar" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>}
          <div className="account-name"><strong>{name}</strong>{user?.email && user.email !== name && <span>{user.email}</span>}</div>
          <button type="button" className="button-quiet" onClick={() => void signOut()}>Sign out</button>
        </div>
      </header>

      <main className="workspace">
        <div className="workspace-heading">
          <div><p className="eyebrow"><span /> Case board</p><h1>Incidents</h1></div>
          <p>Every case the team has opened, newest first.</p>
        </div>

        <div className="workspace-grid">
          <section className="incident-list" aria-labelledby="incident-list-title" aria-busy={load.status === 'loading'}>
            <h2 id="incident-list-title" className="sr-only">Incident list</h2>
            {load.status === 'loading' && <p className="list-state" role="status">Loading incidents<span className="status-dots" aria-hidden="true"><span /><span /><span /></span></p>}
            {load.status === 'error' && <div className="list-state" role="alert"><p className="form-error">{load.message}</p><button type="button" className="button-quiet" onClick={() => { setLoad({ status: 'loading' }); void refresh() }}>Retry</button></div>}
            {load.status === 'ready' && load.incidents.length === 0 && <p className="list-state">No incidents yet. Open the first case with the form.</p>}
            {load.status === 'ready' && load.incidents.length > 0 && <ul>
              {load.incidents.map((incident) => <li key={incident.id} className="incident">
                <div className="incident-top">
                  <span className="incident-service">{incident.service_id}</span>
                  <span className="incident-severity" style={{ color: severityColor[incident.severity] }}><span className="agent-dot" style={{ background: severityColor[incident.severity] }} />{incident.severity}</span>
                </div>
                <p className="incident-symptom">{incident.symptom}</p>
                <p className="incident-meta"><span>{incident.state}</span><span>{formatTime(incident.window_start)} → {formatTime(incident.window_end)}</span>{incident.trace_id && <span>trace {incident.trace_id}</span>}</p>
              </li>)}
            </ul>}
          </section>

          <IncidentForm onCreated={refresh} />
        </div>
      </main>
    </div>
  )
}

function IncidentForm({ onCreated }: { onCreated: () => Promise<void> }) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [defaults] = useState(() => { const end = new Date(); return { start: toLocalInput(new Date(end.getTime() - 3_600_000)), end: toLocalInput(end) } })

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    const field = (key: string) => String(data.get(key) ?? '').trim()
    const start = new Date(field('window_start'))
    const end = new Date(field('window_end'))
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) {
      setError('The window must end after it starts.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await createIncident({
        service_id: field('service_id'),
        symptom: field('symptom'),
        severity: field('severity') as Severity,
        window_start: start.toISOString(),
        window_end: end.toISOString(),
        ...(field('trace_id') && { trace_id: field('trace_id') }),
      })
      form.reset()
      await onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open the case.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="incident-form" onSubmit={submit} aria-labelledby="incident-form-title">
      <h2 id="incident-form-title">Open a case</h2>
      <label>Service<input name="service_id" required maxLength={128} pattern="[A-Za-z0-9._\-]+" placeholder="checkout-api" autoComplete="off" /></label>
      <label>Symptom<textarea name="symptom" required maxLength={2000} rows={3} placeholder="p95 latency jumped from 200ms to 3s" /></label>
      <div className="form-row">
        <label>From<input name="window_start" type="datetime-local" required defaultValue={defaults.start} /></label>
        <label>To<input name="window_end" type="datetime-local" required defaultValue={defaults.end} /></label>
      </div>
      <div className="form-row">
        <label>Severity<select name="severity" defaultValue="high">{severities.map((severity) => <option key={severity} value={severity}>{severity}</option>)}</select></label>
        <label>Trace ID <span className="optional">optional</span><input name="trace_id" maxLength={128} autoComplete="off" /></label>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button type="submit" className="button-primary" disabled={submitting}>{submitting ? 'Opening…' : 'Open case'} <span aria-hidden="true">→</span></button>
    </form>
  )
}
