import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'
import { getIncidentStats, listIncidents, type Incident, type IncidentPage, type IncidentStats, type IncidentFilters, type IncidentState, type Severity } from '../lib/api'
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

const states: IncidentState[] = ['CREATED', 'RUNNING', 'COMPLETED', 'FAILED']

function Runs({ period }: { period: Period }) {
  const [severity, setSeverity] = useState<Severity[]>([])
  const [state, setState] = useState<IncidentState[]>([])
  const [service, setService] = useState('')
  const [serviceQuery, setServiceQuery] = useState('')
  // Wait for a pause in typing before asking for a service, instead of one request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setServiceQuery(service.trim()), 300)
    return () => clearTimeout(timer)
  }, [service])
  const filters = useMemo<IncidentFilters>(() => ({ ...(severity.length && { severity }), ...(state.length && { state }), ...(serviceQuery && { service_id: serviceQuery }) }), [severity, state, serviceQuery])
  const active = Boolean(severity.length || state.length || service.trim())

  return (
    <section className="incident-list" aria-labelledby="incident-list-title">
      <div className="runs-head">
        <h2 id="incident-list-title">Incident runs</h2>
        <p>Newest first</p>
      </div>
      <div className="run-filters" role="group" aria-label="Filter incidents">
        <OptionFilter label="Severity" options={severities} selected={severity} onChange={setSeverity} />
        <OptionFilter label="State" options={states} selected={state} onChange={setState} />
        <TextFilter label="Service" value={service} placeholder="Service name, e.g. checkout-api" onChange={setService} />
        {active && <button type="button" className="filter-reset" onClick={() => { setSeverity([]); setState([]); setService('') }}>Reset</button>}
      </div>
      {/* Keyed on the filters so a change starts again from page 1. */}
      <RunsTable key={JSON.stringify(filters)} period={period} filters={filters} filtered={active} />
    </section>
  )
}

const optionLabel = (value: string) => value.charAt(0).toUpperCase() + value.slice(1).toLowerCase()

/** Open/close state for a filter popover: closes on an outside click or Escape. */
function usePopover() {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onPointer = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpen(false); root.current?.querySelector<HTMLButtonElement>('.filter-chip')?.focus() } }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('pointerdown', onPointer); document.removeEventListener('keydown', onKey) }
  }, [open])
  return { open, setOpen, root }
}

function FilterChip({ label, summary, open, onToggle, onClear }: { label: string, summary: string, open: boolean, onToggle: () => void, onClear: () => void }) {
  const set = summary !== ''
  return (
    <span className={set ? 'filter-chip-group is-set' : 'filter-chip-group'}>
      <button type="button" className="filter-chip" aria-haspopup="true" aria-expanded={open} onClick={onToggle}>
        <span className="filter-chip-label">{label}</span>{set && <>: <span className="filter-chip-value">{summary}</span></>}
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      {set && <button type="button" className="filter-chip-clear" aria-label={`Clear ${label.toLowerCase()} filter`} onClick={onClear}>×</button>}
    </span>
  )
}

function OptionFilter<T extends string>({ label, options, selected, onChange }: { label: string, options: T[], selected: T[], onChange: (next: T[]) => void }) {
  const { open, setOpen, root } = usePopover()
  const toggle = (value: T) => onChange(selected.includes(value) ? selected.filter((item) => item !== value) : options.filter((item) => item === value || selected.includes(item)))
  return (
    <div className="filter" ref={root}>
      <FilterChip label={label} summary={selected.map(optionLabel).join(', ')} open={open} onToggle={() => setOpen((value) => !value)} onClear={() => onChange([])} />
      {open && <div className="filter-menu" role="group" aria-label={label}>
        {options.map((value) => <label key={value} className="filter-option">
          <input type="checkbox" checked={selected.includes(value)} onChange={() => toggle(value)} />
          <span className="filter-check" aria-hidden="true" />
          {optionLabel(value)}
        </label>)}
      </div>}
    </div>
  )
}

function TextFilter({ label, value, placeholder, onChange }: { label: string, value: string, placeholder: string, onChange: (next: string) => void }) {
  const { open, setOpen, root } = usePopover()
  return (
    <div className="filter" ref={root}>
      <FilterChip label={label} summary={value.trim()} open={open} onToggle={() => setOpen((current) => !current)} onClear={() => onChange('')} />
      {open && <div className="filter-menu">
        <input className="filter-input" type="search" aria-label={label} value={value} placeholder={placeholder} spellCheck={false} autoFocus onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') setOpen(false) }} />
      </div>}
    </div>
  )
}

function RunsTable({ period, filters, filtered }: { period: Period, filters: IncidentFilters, filtered: boolean }) {
  // cursors[i] fetches page i; page 0 has no cursor.
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [page, setPage] = useState(0)
  const [load, setLoad] = useState<Load<IncidentPage>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    listIncidents(period.from, period.to, cursors[page], 10, filters).then(
      (data) => { if (active) setLoad({ status: 'ready', data }) },
      (err: unknown) => { if (active) setLoad({ status: 'error', message: errorText(err, 'Could not load incidents.') }) },
    )
    return () => { active = false }
  }, [period, filters, cursors, page, attempt])

  const go = (next: number) => { setLoad({ status: 'loading' }); setPage(next) }
  const nextCursor = load.status === 'ready' ? load.data.next_cursor : null

  return (
    <div aria-busy={load.status === 'loading'}>
      {page > 0 && <p className="runs-page">Page {page + 1}</p>}
      {load.status === 'loading' && <p className="list-state" role="status">Loading incidents<span className="status-dots" aria-hidden="true"><span /><span /><span /></span></p>}
      {load.status === 'error' && <div className="list-state" role="alert"><p className="form-error">{load.message}</p><button type="button" className="button-quiet" onClick={() => { setLoad({ status: 'loading' }); setAttempt((n) => n + 1) }}>Retry</button></div>}
      {load.status === 'ready' && load.data.items.length === 0 && <p className="list-state">{filtered ? 'No incidents match these filters in this range.' : 'No incidents in this range. Runs your tools open will show up here.'}</p>}
      {load.status === 'ready' && load.data.items.length > 0 && <div className="incident-table-wrap"><table className="incident-table">
        <thead><tr><th scope="col">Service</th><th scope="col">Symptom</th><th scope="col">Severity</th><th scope="col">State</th><th scope="col">Opened</th><th scope="col">Window</th></tr></thead>
        <tbody>{load.data.items.map((incident) => <IncidentRow key={incident.id} incident={incident} />)}</tbody>
      </table></div>}
      {(page > 0 || nextCursor) && <nav className="pager" aria-label="Incident pages">
        <button type="button" className="button-quiet" disabled={page === 0 || load.status === 'loading'} onClick={() => go(page - 1)}><span aria-hidden="true">←</span> Newer</button>
        <button type="button" className="button-quiet" disabled={!nextCursor || load.status === 'loading'} onClick={() => { if (!nextCursor) return; setCursors((list) => [...list.slice(0, page + 1), nextCursor]); go(page + 1) }}>Older <span aria-hidden="true">→</span></button>
      </nav>}
    </div>
  )
}

function IncidentRow({ incident }: { incident: Incident }) {
  const navigate = useNavigate()
  const href = `/app/incidents/${incident.id}`
  const seconds = (Date.parse(incident.window_end) - Date.parse(incident.window_start)) / 1000
  // The whole row opens the incident; the service cell holds the real link for keyboard and screen readers.
  return (
    <tr className="incident-row" onClick={(event) => { if (!(event.target as Element).closest('a')) navigate(href) }}>
      <td className="incident-service"><Link to={href}>{incident.service_id}</Link></td>
      <td className="incident-symptom">{incident.symptom}</td>
      <td><span className="incident-severity" style={{ color: severityColor[incident.severity] }}><span className="agent-dot" style={{ background: severityColor[incident.severity] }} />{incident.severity}</span></td>
      <td><span className={`state-pill is-${incident.state.toLowerCase()}`}>{incident.state.toLowerCase()}</span></td>
      <td className="incident-time">{formatTime(incident.created_at)}</td>
      <td className="incident-time" title={`${formatTime(incident.window_start)} → ${formatTime(incident.window_end)}`}>{formatDuration(seconds)}</td>
    </tr>
  )
}
