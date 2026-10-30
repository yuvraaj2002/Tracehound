import { useEffect, useRef, useState, type CSSProperties, type FormEvent, type RefObject } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ApiError, createIntegration, deleteIntegration, listIntegrations, updateIntegration, type IntegrationAuth, type IntegrationKind, type IntegrationStatus, type IntegrationSummary, type IntegrationUpdate } from '../lib/api'
import Dialog from '../Dialog'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'

const formatDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
const message = (err: unknown, fallback: string) => err instanceof Error ? err.message : fallback

/** One slot per specialist data source. Only Loki is connectable today; the rest say so plainly. */
type Source = { signal: string, agent: string, name: string, face: string, product: string, description: string, color: string, kind: IntegrationKind | null }
const sources: Source[] = [
  { signal: 'Logs', name: 'Echo', face: '/agents/faces/logs.jpg', agent: 'Logs agent', product: 'Grafana Loki', description: 'Reads error bursts, stack traces and new messages from your services during the incident window.', color: 'var(--agent-logs)', kind: 'loki' },
  { signal: 'Metrics', name: 'Pulse', face: '/agents/faces/metrics.jpg', agent: 'Metrics agent', product: 'Prometheus', description: 'Compares latency, error rate and saturation against the baseline before the incident.', color: 'var(--agent-metrics)', kind: null },
  { signal: 'Traces', name: 'Tether', face: '/agents/faces/dependency.jpg', agent: 'Dependency agent', product: 'Grafana Tempo', description: 'Follows slow and failing spans across service boundaries to find where trouble starts.', color: 'var(--agent-dependency)', kind: null },
  { signal: 'Deploys', name: 'Ledger', face: '/agents/faces/deploy.jpg', agent: 'Deploy agent', product: 'GitHub', description: 'Lines up releases and configuration changes with the moment the incident began.', color: 'var(--agent-deploy)', kind: null },
]

const statusLabel: Record<IntegrationStatus, string> = { untested: 'Not tested yet', active: 'Connected', failing: 'Failing' }
const authLabel = (config: IntegrationSummary['config']) => config.auth_type === 'basic' ? `Basic · ${config.username}` : config.auth_type === 'bearer' ? 'Bearer token' : 'None'

/** Dev-only sample rows (`?preview=all`) showing every source connected, one per status.
 *  Only Loki is a real kind today, so these never touch the API. */
const previewAt = '2026-10-21T09:30:00Z'
const preview: Record<string, IntegrationSummary> = {
  Logs: { id: 'preview-logs', kind: 'loki', config: { url: 'https://logs-prod-012.grafana.net', service_label: 'service_name', org_id: null, auth_type: 'basic', username: '987654' }, has_secret: true, status: 'active', last_tested_at: previewAt, created_at: previewAt },
  Metrics: { id: 'preview-metrics', kind: 'loki', config: { url: 'https://prometheus-prod-24.grafana.net/api/prom', service_label: 'job', org_id: null, auth_type: 'basic', username: '1234567' }, has_secret: true, status: 'active', last_tested_at: previewAt, created_at: previewAt },
  Traces: { id: 'preview-traces', kind: 'loki', config: { url: 'https://tempo.internal.acme.com', service_label: 'service_name', org_id: 'acme-prod', auth_type: 'bearer' }, has_secret: true, status: 'untested', last_tested_at: null, created_at: '2026-10-28T16:05:00Z' },
  Deploys: { id: 'preview-deploys', kind: 'loki', config: { url: 'https://api.github.com/repos/acme/checkout', service_label: 'repository', org_id: 'acme', auth_type: 'bearer' }, has_secret: true, status: 'failing', last_tested_at: previewAt, created_at: '2026-10-14T11:20:00Z' },
}

type Load = { status: 'loading' } | { status: 'ready', items: IntegrationSummary[] } | { status: 'error', message: string }

const fetchAll = (): Promise<Load> => listIntegrations().then(
  (page) => ({ status: 'ready', items: page.items }),
  (err: unknown) => ({ status: 'error', message: message(err, 'Could not load integrations.') }),
)

export default function Integrations() {
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const [connecting, setConnecting] = useState<{ source: Source, integration?: IntegrationSummary } | null>(null)
  const [disconnecting, setDisconnecting] = useState<{ source: Source, integration: IntegrationSummary } | null>(null)
  const [highlight, setHighlight] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const [params] = useSearchParams()
  const previewing = import.meta.env.DEV && params.get('preview') === 'all'

  useEffect(() => {
    let active = true
    fetchAll().then((next) => { if (active) setLoad(next) })
    return () => { active = false }
  }, [])

  // The status message and the new-row highlight both fade on their own.
  useEffect(() => {
    if (!status) return
    const timer = setTimeout(() => setStatus(null), 4000)
    return () => clearTimeout(timer)
  }, [status])
  useEffect(() => {
    if (!highlight) return
    const timer = setTimeout(() => setHighlight(null), 2400)
    return () => clearTimeout(timer)
  }, [highlight])

  const retry = () => { setLoad({ status: 'loading' }); void fetchAll().then(setLoad) }

  const onSaved = (source: Source, integration: IntegrationSummary, edited: boolean) => {
    // An edit keeps the row in place; a new connection goes after the existing ones.
    setLoad((current) => current.status !== 'ready' ? current : { status: 'ready', items: edited ? current.items.map((item) => item.id === integration.id ? integration : item) : [...current.items.filter((item) => item.kind !== integration.kind), integration] })
    setConnecting(null)
    setHighlight(integration.id)
    setStatus(`${source.product} ${edited ? 'updated' : 'connected'}`)
  }

  const onDeleted = (source: Source, integration: IntegrationSummary) => {
    setLoad((current) => current.status === 'ready' ? { status: 'ready', items: current.items.filter((item) => item.id !== integration.id) } : current)
    setDisconnecting(null)
    setStatus(`${source.product} disconnected`)
  }

  const connected = previewing ? sources.length : load.status === 'ready' ? load.items.length : 0

  return (
    <>
      <div className="auth-page" inert={connecting !== null || disconnecting !== null}>
        <SignedInHeader />

        <main className="workspace">
          <Link className="back-link" to="/app"><span aria-hidden="true">←</span> Home</Link>
          <div className="workspace-heading">
            <div><p className="eyebrow"><span /> Data sources</p><h1 ref={heading} tabIndex={-1}>Integrations</h1><p className="heading-note">Connect the backends your services already report to. Each specialist reads its evidence from here, with read-only access.</p></div>
            {(previewing || load.status === 'ready') && <p className="source-count"><strong>{connected}</strong> of {sources.length} connected</p>}
          </div>

          <section className="source-list" aria-labelledby="source-list-title" aria-busy={load.status === 'loading'}>
            <h2 id="source-list-title" className="sr-only">Data sources</h2>
            {previewing && <div className="notice">
              <div><p className="notice-title">Preview with sample data</p><p>Every source is shown connected, one per status. Nothing here is saved, and the actions are switched off.</p></div>
              <Link className="button-quiet preview-exit" to="/app/integrations">Exit preview</Link>
            </div>}
            {!previewing && load.status === 'error' && <div className="notice" role="status">
              <div><p className="notice-title">Couldn’t load your integrations</p><p>{load.message}</p></div>
              <button type="button" className="button-quiet" onClick={retry}>Retry</button>
            </div>}
            {load.status === 'loading' && <p className="sr-only" role="status">Loading integrations</p>}
            <ul>
              {sources.map((source) => {
                const integration = previewing ? preview[source.signal] : load.status === 'ready' ? load.items.find((item) => item.kind === source.kind) : undefined
                return <SourceRow key={source.signal} source={source} integration={integration} previewing={previewing} loading={!previewing && load.status === 'loading'} unavailable={load.status === 'error'} isNew={integration?.id === highlight} onConnect={() => setConnecting({ source })} onEdit={(item) => setConnecting({ source, integration: item })} onDisconnect={(item) => setDisconnecting({ source, integration: item })} />
              })}
            </ul>
          </section>
        </main>
      </div>

      <div className="toast-region" role="status" aria-live="polite">{status && <p className="toast">{status}</p>}</div>

      {disconnecting && <DisconnectDialog source={disconnecting.source} integration={disconnecting.integration} fallbackFocus={heading} onDeleted={() => onDeleted(disconnecting.source, disconnecting.integration)} onClose={() => setDisconnecting(null)} />}
      {connecting && <ConnectLokiDialog source={connecting.source} integration={connecting.integration} fallbackFocus={heading} onSaved={(integration) => onSaved(connecting.source, integration, connecting.integration !== undefined)} onClose={() => setConnecting(null)} />}
    </>
  )
}

/** The agent who reads this source. Decorative: the eyebrow already names the agent. */
function AgentFace({ source }: { source: Source }) {
  return <span className="agent-face" aria-hidden="true"><img src={source.face} alt="" width="96" height="96" loading="lazy" decoding="async" /></span>
}

function SourceRow({ source, integration, previewing, loading, unavailable, isNew, onConnect, onEdit, onDisconnect }: { source: Source, integration?: IntegrationSummary, previewing: boolean, loading: boolean, unavailable: boolean, isNew: boolean, onConnect: () => void, onEdit: (integration: IntegrationSummary) => void, onDisconnect: (integration: IntegrationSummary) => void }) {
  const titleId = `source-${source.signal.toLowerCase()}`
  const action = () => {
    if (!source.kind && !previewing) return <span className="source-soon">Coming soon</span>
    if (loading) return <span className="skeleton source-skeleton" aria-hidden="true" />
    if (integration) return <>
      <span className={`source-status is-${integration.status}`}><span aria-hidden="true" />{statusLabel[integration.status]}</span>
      <button type="button" className="button-quiet" onClick={() => onEdit(integration)} disabled={previewing} aria-label={`Edit ${source.product}`}>Edit</button>
      <button type="button" className="button-quiet button-danger" onClick={() => onDisconnect(integration)} disabled={previewing} aria-label={`Disconnect ${source.product}`}>Disconnect</button>
    </>
    return <button type="button" className="button-primary" onClick={onConnect} disabled={unavailable} aria-describedby={titleId}>Connect <span aria-hidden="true">+</span></button>
  }

  return (
    <li className={['source', source.kind || previewing ? null : 'is-planned', isNew ? 'is-new' : null].filter(Boolean).join(' ')} style={{ '--source-color': source.color } as CSSProperties} aria-labelledby={titleId}>
      <div className="source-head">
        <AgentFace source={source} />
        <div className="source-identity">
          <p className="eyebrow"><span /> {source.signal} · {source.name}, {source.agent}</p>
          <h3 id={titleId}>{source.product}</h3>
          <p className="source-description">{source.description}</p>
        </div>
        <div className="source-action">{action()}</div>
      </div>
      {integration && <dl className="source-details">
        <div className="source-detail-wide"><dt>Endpoint</dt><dd><code title={integration.config.url}>{integration.config.url}</code></dd></div>
        <div><dt>Authentication</dt><dd>{authLabel(integration.config)}{integration.has_secret && <span className="source-secret"><svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><rect x="3.5" y="7" width="9" height="6.5" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>Encrypted</span>}</dd></div>
        <div><dt>Service label</dt><dd><code>{integration.config.service_label}</code></dd></div>
        <div><dt>Tenant</dt><dd>{integration.config.org_id ? <code>{integration.config.org_id}</code> : 'Default'}</dd></div>
        <div><dt>Connected</dt><dd>{formatDate(integration.created_at)}</dd></div>
      </dl>}
    </li>
  )
}

function DisconnectDialog({ source, integration, fallbackFocus, onDeleted, onClose }: { source: Source, integration: IntegrationSummary, fallbackFocus: RefObject<HTMLElement | null>, onDeleted: () => void, onClose: () => void }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const disconnect = async () => {
    setPending(true)
    setError(null)
    try {
      await deleteIntegration(integration.id)
      onDeleted()
    } catch (err) {
      // Already gone on the server: the outcome the user asked for.
      if (err instanceof ApiError && err.status === 404) onDeleted()
      else { setError(message(err, 'Could not disconnect the integration.')); setPending(false) }
    }
  }

  return (
    <Dialog labelledBy="disconnect-dialog-title" describedBy="disconnect-dialog-body" onDismiss={pending ? null : onClose} fallbackFocus={fallbackFocus}>
      <h2 id="disconnect-dialog-title">Disconnect {source.product}?</h2>
      <div id="disconnect-dialog-body">
        <p className="dialog-key"><code>{integration.config.url}</code></p>
        <p>{source.name}, the {source.agent.toLowerCase()}, will stop reading evidence from this backend. The URL and the stored {integration.has_secret ? 'token are' : 'settings are'} deleted for good; to use it again, connect it from scratch.</p>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="dialog-actions">
        <button type="button" className="button-quiet" onClick={onClose} disabled={pending} autoFocus>Cancel</button>
        <button type="button" className="button-primary button-danger-solid" onClick={() => void disconnect()} disabled={pending}>{pending ? 'Disconnecting…' : 'Disconnect'}</button>
      </div>
    </Dialog>
  )
}

type AuthType = IntegrationAuth['type']
const authOptions: { value: AuthType, label: string, hint: string }[] = [
  { value: 'basic', label: 'Basic', hint: 'Grafana Cloud: your Loki user ID and an access policy token with logs:read.' },
  { value: 'bearer', label: 'Bearer token', hint: 'For Loki behind a proxy or gateway that expects an Authorization: Bearer header.' },
  { value: 'none', label: 'None', hint: 'Only for Loki on a private network that needs no credentials.' },
]

/** Connects Loki, or edits an existing connection when `integration` is given. The stored token
 *  is never sent back to the browser, so an edit leaves it alone unless a new one is typed. */
function ConnectLokiDialog({ source, integration, fallbackFocus, onSaved, onClose }: { source: Source, integration?: IntegrationSummary, fallbackFocus: RefObject<HTMLElement | null>, onSaved: (integration: IntegrationSummary) => void, onClose: () => void }) {
  const stored = integration?.config
  const [url, setUrl] = useState(stored?.url ?? '')
  const [authType, setAuthType] = useState<AuthType>(stored?.auth_type ?? 'basic')
  const [username, setUsername] = useState(stored?.username ?? '')
  // The credential lives only in this state and is sent once, over the API, to be encrypted.
  const [secret, setSecret] = useState('')
  const [showSecret, setShowSecret] = useState(false)
  const [serviceLabel, setServiceLabel] = useState(stored?.service_label ?? 'service_name')
  const [orgId, setOrgId] = useState(stored?.org_id ?? '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const trimmedUrl = url.trim()
  const label = serviceLabel.trim() || 'service_name'
  const org = orgId.trim() || null
  const urlProblem = trimmedUrl && !/^https?:\/\/[^\s/?#]+/i.test(trimmedUrl) ? 'Enter a full URL, starting with https://' : null
  const labelProblem = serviceLabel.trim() && !/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(serviceLabel.trim()) ? 'Letters, digits and underscores; it can’t start with a digit.' : null

  // Editing: the stored secret can be kept only while the auth type and user ID stay the same.
  const editing = stored !== undefined
  const sameAuth = editing && authType === stored.auth_type && (authType !== 'basic' || username.trim() === (stored.username ?? ''))
  const canKeepSecret = sameAuth && authType !== 'none' && Boolean(integration?.has_secret)
  const needsSecret = authType !== 'none' && !canKeepSecret
  const authComplete = authType === 'none' || ((authType === 'bearer' || username.trim()) && (secret || !needsSecret))

  const changes: IntegrationUpdate = {}
  if (editing) {
    const config: IntegrationUpdate['config'] = {}
    if (trimmedUrl.replace(/\/+$/, '') !== stored.url) config.url = trimmedUrl
    if (label !== stored.service_label) config.service_label = label
    if (org !== stored.org_id) config.org_id = org
    if (Object.keys(config).length) changes.config = config
  }
  const auth: IntegrationAuth = authType === 'basic' ? { type: 'basic', username: username.trim(), password: secret } : authType === 'bearer' ? { type: 'bearer', token: secret } : { type: 'none' }
  if (editing && (!sameAuth || secret)) changes.auth = auth
  const unchanged = editing && !changes.config && !changes.auth
  const complete = Boolean(trimmedUrl) && !urlProblem && !labelProblem && Boolean(authComplete) && !unchanged

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!complete || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      onSaved(integration
        ? await updateIntegration(integration.id, changes)
        : await createIntegration({ kind: 'loki', config: { url: trimmedUrl, service_label: label, org_id: org }, auth }))
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? 'You already have a Loki connection. Reload the page to see it.'
        : err instanceof ApiError && err.status === 404 ? 'This connection no longer exists. Reload the page to see your integrations.'
        : message(err, 'Could not save the connection.'))
      setSubmitting(false)
    }
  }

  const option = authOptions.find((item) => item.value === authType)!

  return (
    <Dialog labelledBy="connect-dialog-title" describedBy="connect-dialog-intro" onDismiss={submitting ? null : onClose} fallbackFocus={fallbackFocus} wide>
      <form className="dialog-form connect-form" onSubmit={submit} noValidate style={{ '--source-color': source.color } as CSSProperties}>
        <div className="connect-header">
          <div className="connect-title">
            <AgentFace source={source} />
            <div>
              <p className="eyebrow"><span /> {source.signal} · {source.name}, {source.agent}</p>
              <h2 id="connect-dialog-title">{editing ? 'Edit' : 'Connect'} {source.product}</h2>
            </div>
          </div>
          <p id="connect-dialog-intro">{editing ? 'Saving changes marks the connection as not tested, since the old result no longer applies.' : 'Tracehound runs read-only LogQL queries against this Loki when it investigates an incident.'}</p>
        </div>

        <div className="connect-field">
          <label htmlFor="loki-url">Loki URL</label>
          <input id="loki-url" type="url" inputMode="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://logs-prod-012.grafana.net" autoComplete="off" spellCheck={false} aria-describedby="loki-url-hint" aria-invalid={urlProblem ? true : undefined} autoFocus />
          <p id="loki-url-hint" className={urlProblem ? 'field-hint is-error' : 'field-hint'}>{urlProblem ?? 'The base URL, without /loki/api/v1. In Grafana Cloud it’s on your stack’s Loki details page.'}</p>
        </div>

        <fieldset className="connect-field">
          <legend>Authentication</legend>
          <div className="segmented" role="radiogroup" aria-describedby="auth-hint">
            {authOptions.map((item) => <label key={item.value} className={item.value === authType ? 'is-selected' : undefined}>
              <input type="radio" name="auth-type" value={item.value} checked={item.value === authType} onChange={() => { setAuthType(item.value); setSecret(''); setShowSecret(false) }} />
              {item.label}
            </label>)}
          </div>
          <p id="auth-hint" className="field-hint">{option.hint}</p>
        </fieldset>

        {authType !== 'none' && <div className={authType === 'basic' ? 'connect-row' : undefined}>
          {authType === 'basic' && <div className="connect-field">
            <label htmlFor="loki-username">User ID</label>
            <input id="loki-username" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="123456" autoComplete="off" spellCheck={false} />
          </div>}
          <div className="connect-field">
            <label htmlFor="loki-secret">{authType === 'basic' ? 'Token or password' : 'Token'}</label>
            <div className="secret-input">
              <input id="loki-secret" type={showSecret ? 'text' : 'password'} value={secret} onChange={(event) => setSecret(event.target.value)} placeholder={authType === 'basic' ? 'glc_…' : 'eyJ…'} autoComplete="new-password" spellCheck={false} aria-describedby={canKeepSecret ? 'loki-secret-hint' : undefined} />
              <button type="button" onClick={() => setShowSecret((value) => !value)} aria-pressed={showSecret} aria-label={showSecret ? 'Hide token' : 'Show token'}>{showSecret ? 'Hide' : 'Show'}</button>
            </div>
            {canKeepSecret && <p id="loki-secret-hint" className="field-hint">Leave blank to keep the current token.</p>}
            {editing && !canKeepSecret && stored.auth_type !== 'none' && <p className="field-hint">{authType === stored.auth_type ? 'A new user ID needs its token too.' : 'Enter the token for the new method.'}</p>}
          </div>
        </div>}

        <details className="connect-advanced">
          <summary>Advanced settings</summary>
          <div className="connect-row">
            <div className="connect-field">
              <label htmlFor="loki-label">Service label</label>
              <input id="loki-label" value={serviceLabel} onChange={(event) => setServiceLabel(event.target.value)} autoComplete="off" spellCheck={false} aria-describedby="loki-label-hint" aria-invalid={labelProblem ? true : undefined} />
              <p id="loki-label-hint" className={labelProblem ? 'field-hint is-error' : 'field-hint'}>{labelProblem ?? 'The stream label that names each service.'}</p>
            </div>
            <div className="connect-field">
              <label htmlFor="loki-org">Tenant ID <span className="optional">optional</span></label>
              <input id="loki-org" value={orgId} onChange={(event) => setOrgId(event.target.value)} placeholder="acme-prod" autoComplete="off" spellCheck={false} aria-describedby="loki-org-hint" />
              <p id="loki-org-hint" className="field-hint">Sent as X-Scope-OrgID to multi-tenant Loki.</p>
            </div>
          </div>
        </details>

        {authType !== 'none' && <div className="connect-callout">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><rect x="3.5" y="7" width="9" height="6.5" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
          <p>{canKeepSecret ? 'The current token stays encrypted and is never shown. A new one replaces it for good.' : 'Your token is encrypted before it’s stored and is never shown again. Use a read-only token, so Tracehound can query logs but never change them.'}</p>
        </div>}

        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="dialog-actions">
          <button type="button" className="button-quiet" onClick={onClose} disabled={submitting}>Cancel</button>
          <button type="submit" className="button-primary" disabled={!complete || submitting}>{submitting ? 'Saving…' : editing ? (unchanged ? 'No changes' : 'Save changes') : 'Save connection'}</button>
        </div>
      </form>
    </Dialog>
  )
}
