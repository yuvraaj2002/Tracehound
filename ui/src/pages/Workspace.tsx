import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { getIncidentStats, listIncidents, type Incident, type IncidentPage, type IncidentStats, type Severity } from '../lib/api'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'

const severities: Severity[] = ['critical', 'high', 'medium', 'low']
const severityColor: Record<Severity, string> = { critical: 'var(--severity-critical)', high: 'var(--severity-high)', medium: 'var(--severity-medium)', low: 'var(--severity-low)' }

const ranges = [
  { key: '24h', label: '24h', days: 1 },
  { key: '7d', label: '7 days', days: 7 },
  { key: '30d', label: '30 days', days: 30 },
  { key: '90d', label: '90 days', days: 90 },
] as const
type RangeKey = typeof ranges[number]['key']
type Period = { key: RangeKey, from: string, to: string }

/** The range ends now; it is fixed when chosen so paging stays stable while new runs arrive. */
const periodFor = (key: RangeKey): Period => {
  const to = new Date()
  const days = ranges.find((range) => range.key === key)!.days
  return { key, from: new Date(to.getTime() - days * 86_400_000).toISOString(), to: to.toISOString() }
}

const errorText = (err: unknown, fallback: string) => err instanceof Error ? err.message : fallback
const formatTime = (iso: string) => new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
const formatDay = (day: string) => new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
const formatPercent = (value: number) => `${Math.round(value * 100)}%`

function formatDuration(seconds: number) {
  if (seconds < 60) return `${Math.round(seconds)}s`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return minutes % 60 ? `${hours}h ${minutes % 60}m` : `${hours}h`
}

type Load<T> = { status: 'loading' } | { status: 'ready', data: T } | { status: 'error', message: string }

/** The dashboard: headline figures for a time range, then that range's runs, newest first. */
export default function Workspace() {
  const [period, setPeriod] = useState<Period>(() => periodFor('7d'))

  return (
    <div className="auth-page">
      <SignedInHeader />

      <main className="workspace">
        <Link className="back-link" to="/app"><span aria-hidden="true">←</span> Home</Link>
        <div className="workspace-heading">
          <div><p className="eyebrow"><span /> Runs</p><h1>Dashboard</h1></div>
          <div className="range-picker" role="radiogroup" aria-label="Time range">
            {ranges.map((range) => <button key={range.key} type="button" role="radio" aria-checked={period.key === range.key} className={period.key === range.key ? 'is-selected' : undefined} onClick={() => setPeriod(periodFor(range.key))}>{range.label}</button>)}
          </div>
        </div>

        {/* Keyed on the period so each range starts from a clean loading state. */}
        <Stats key={`stats-${period.from}`} period={period} />
        <Runs key={`runs-${period.from}`} period={period} />
      </main>
    </div>
  )
}

function Stats({ period }: { period: Period }) {
  const [load, setLoad] = useState<Load<IncidentStats>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    getIncidentStats(period.from, period.to).then(
      (data) => { if (active) setLoad({ status: 'ready', data }) },
      (err: unknown) => { if (active) setLoad({ status: 'error', message: errorText(err, 'Could not load the figures.') }) },
    )
    return () => { active = false }
  }, [period, attempt])

  if (load.status === 'error') return <div className="list-state" role="alert"><p className="form-error">{load.message}</p><button type="button" className="button-quiet" onClick={() => { setLoad({ status: 'loading' }); setAttempt((n) => n + 1) }}>Retry</button></div>
  const stats = load.status === 'ready' ? load.data : null

  return (
    <section className="dashboard-stats" aria-label="Figures for the selected range" aria-busy={!stats}>
      <ul className="stat-cards">
        <StatCard label="Incidents" value={stats?.total} note={stats && <Change current={stats.total} previous={stats.previous_total} />} />
        <StatCard label="Critical and high" value={stats && stats.by_severity.critical + stats.by_severity.high} note={stats && (stats.total ? `${formatPercent((stats.by_severity.critical + stats.by_severity.high) / stats.total)} of all incidents` : 'None in this range')} />
        <StatCard label="Avg incident period" value={stats && (stats.avg_window_seconds === null ? '—' : formatDuration(stats.avg_window_seconds))} note="How long a problem ran before it was reported" />
        <StatCard label="Trace coverage" value={stats && (stats.trace_coverage === null ? '—' : formatPercent(stats.trace_coverage))} note="Incidents that arrived with a trace ID" />
      </ul>

      <div className="dashboard-charts">
        <div className="chart-panel chart-wide">
          <div className="chart-head"><h2>Incidents per day</h2><Legend /></div>
          {stats ? <DailyChart stats={stats} /> : <div className="skeleton chart-skeleton" />}
        </div>
        <div className="chart-panel">
          <div className="chart-head"><h2>By severity</h2></div>
          {stats ? <BarList total={stats.total} rows={severities.map((severity) => ({ key: severity, label: severity, count: stats.by_severity[severity], color: severityColor[severity] }))} empty="No incidents in this range." /> : <div className="skeleton chart-skeleton" />}
        </div>
        <div className="chart-panel">
          <div className="chart-head"><h2>Top services</h2></div>
          {stats ? <BarList total={stats.total} rows={stats.top_services.map((service) => ({ key: service.service_id, label: service.service_id, count: service.count, color: 'var(--color-primary)' }))} empty="No services reported yet." /> : <div className="skeleton chart-skeleton" />}
        </div>
      </div>
    </section>
  )
}

function StatCard({ label, value, note }: { label: string, value: ReactNode, note: ReactNode }) {
  const loading = value === null || value === undefined
  return (
    <li className="stat-card">
      <p className="stat-label">{label}</p>
      {loading ? <div className="skeleton stat-skeleton" /> : <p className="stat-value">{value}</p>}
      <p className="stat-note">{loading ? ' ' : note}</p>
    </li>
  )
}

function Change({ current, previous }: { current: number, previous: number }) {
  if (previous === 0) return <>{current ? 'None in the previous period' : 'No change from the previous period'}</>
  const change = (current - previous) / previous
  // For incidents, fewer is better: a drop reads as good news.
  const tone = change > 0 ? 'is-up' : change < 0 ? 'is-down' : ''
  return <><span className={`stat-change ${tone}`}>{change > 0 ? '+' : ''}{Math.round(change * 100)}%</span> vs previous period</>
}

function Legend() {
  return <ul className="chart-legend">{severities.map((severity) => <li key={severity}><span style={{ background: severityColor[severity] }} />{severity}</li>)}</ul>
}

function DailyChart({ stats }: { stats: IncidentStats }) {
  const peak = Math.max(1, ...stats.timeseries.map((point) => point.total))
  const labelEvery = Math.ceil(stats.timeseries.length / 8)
  return (
    <div className="daily-chart" role="img" aria-label={`Incidents per day, peaking at ${peak}`}>
      <div className="daily-bars">
        {stats.timeseries.map((point) => <div key={point.day} className="daily-bar" title={`${formatDay(point.day)}: ${point.total} incident${point.total === 1 ? '' : 's'}`}>
          <div className="daily-stack" style={{ height: `${(point.total / peak) * 100}%` }}>
            {severities.map((severity) => point[severity] > 0 && <span key={severity} style={{ flexGrow: point[severity], background: severityColor[severity] }} />)}
          </div>
        </div>)}
      </div>
      <div className="daily-axis" aria-hidden="true">
        {stats.timeseries.map((point, index) => <span key={point.day}>{index % labelEvery === 0 ? formatDay(point.day) : ''}</span>)}
      </div>
    </div>
  )
}

function BarList({ rows, total, empty }: { rows: { key: string, label: string, count: number, color: string }[], total: number, empty: string }) {
  if (total === 0 || rows.length === 0) return <p className="chart-empty">{empty}</p>
  const peak = Math.max(...rows.map((row) => row.count))
  return (
    <ul className="bar-list">
      {rows.map((row) => <li key={row.key}>
        <span className="bar-label">{row.label}</span>
        <span className="bar-count">{row.count}</span>
        <span className="bar-track"><span style={{ width: `${peak ? (row.count / peak) * 100 : 0}%`, background: row.color }} /></span>
      </li>)}
    </ul>
  )
}

function Runs({ period }: { period: Period }) {
  // cursors[i] fetches page i; page 0 has no cursor.
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [page, setPage] = useState(0)
  const [load, setLoad] = useState<Load<IncidentPage>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    listIncidents(period.from, period.to, cursors[page]).then(
      (data) => { if (active) setLoad({ status: 'ready', data }) },
      (err: unknown) => { if (active) setLoad({ status: 'error', message: errorText(err, 'Could not load incidents.') }) },
    )
    return () => { active = false }
  }, [period, cursors, page, attempt])

  const go = (next: number) => { setLoad({ status: 'loading' }); setPage(next) }
  const nextCursor = load.status === 'ready' ? load.data.next_cursor : null

  return (
    <section className="incident-list" aria-labelledby="incident-list-title" aria-busy={load.status === 'loading'}>
      <div className="runs-head">
        <h2 id="incident-list-title">Incident runs</h2>
        <p>Newest first{page > 0 && ` · page ${page + 1}`}</p>
      </div>
      {load.status === 'loading' && <p className="list-state" role="status">Loading incidents<span className="status-dots" aria-hidden="true"><span /><span /><span /></span></p>}
      {load.status === 'error' && <div className="list-state" role="alert"><p className="form-error">{load.message}</p><button type="button" className="button-quiet" onClick={() => { setLoad({ status: 'loading' }); setAttempt((n) => n + 1) }}>Retry</button></div>}
      {load.status === 'ready' && load.data.items.length === 0 && <p className="list-state">No incidents in this range. Runs your tools open will show up here.</p>}
      {load.status === 'ready' && load.data.items.length > 0 && <ul>{load.data.items.map((incident) => <IncidentRow key={incident.id} incident={incident} />)}</ul>}
      {(page > 0 || nextCursor) && <nav className="pager" aria-label="Incident pages">
        <button type="button" className="button-quiet" disabled={page === 0 || load.status === 'loading'} onClick={() => go(page - 1)}><span aria-hidden="true">←</span> Newer</button>
        <button type="button" className="button-quiet" disabled={!nextCursor || load.status === 'loading'} onClick={() => { if (!nextCursor) return; setCursors((list) => [...list.slice(0, page + 1), nextCursor]); go(page + 1) }}>Older <span aria-hidden="true">→</span></button>
      </nav>}
    </section>
  )
}

function IncidentRow({ incident }: { incident: Incident }) {
  return (
    <li className="incident">
      <div className="incident-top">
        <span className="incident-service">{incident.service_id}</span>
        <span className="incident-severity" style={{ color: severityColor[incident.severity] }}><span className="agent-dot" style={{ background: severityColor[incident.severity] }} />{incident.severity}</span>
      </div>
      <p className="incident-symptom">{incident.symptom}</p>
      <p className="incident-meta"><span>{incident.state}</span><span>Opened {formatTime(incident.created_at)}</span><span>Window {formatTime(incident.window_start)} → {formatTime(incident.window_end)}</span>{incident.trace_id && <span>trace {incident.trace_id}</span>}</p>
    </li>
  )
}
