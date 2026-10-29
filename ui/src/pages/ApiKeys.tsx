import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type ReactNode, type RefObject } from 'react'
import { Link } from 'react-router'
import { ApiError, createApiKey, listApiKeys, revokeApiKey, type ApiKeyCreated, type ApiKeySummary } from '../lib/api'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'

const nameLimit = 100
const formatDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
const formatTime = (iso: string) => new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
const message = (err: unknown, fallback: string) => err instanceof Error ? err.message : fallback
const masked = (key: Pick<ApiKeySummary, 'prefix' | 'suffix'>) => `${key.prefix}…${key.suffix}`

type Load = { status: 'loading' } | { status: 'ready', keys: ApiKeySummary[], next: string | null } | { status: 'error', message: string }

const fetchFirstPage = (): Promise<Load> => listApiKeys().then(
  (page) => ({ status: 'ready', keys: page.items, next: page.next_cursor }),
  (err: unknown) => ({ status: 'error', message: message(err, 'Could not load API keys.') }),
)

export default function ApiKeys() {
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [revoking, setRevoking] = useState<ApiKeySummary | null>(null)
  const [highlight, setHighlight] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const createButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    let active = true
    fetchFirstPage().then((next) => { if (active) setLoad(next) })
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

  const retry = () => { setLoad({ status: 'loading' }); void fetchFirstPage().then(setLoad) }

  const loadMore = async () => {
    if (load.status !== 'ready' || !load.next) return
    setLoadingMore(true)
    setMoreError(null)
    try {
      const page = await listApiKeys(load.next)
      // A key created on this page may also arrive in a later page; keep one copy.
      setLoad((current) => current.status !== 'ready' ? current : { status: 'ready', keys: [...current.keys, ...page.items.filter((item) => !current.keys.some((key) => key.id === item.id))], next: page.next_cursor })
    } catch (err) {
      setMoreError(message(err, 'Could not load more keys.'))
    } finally {
      setLoadingMore(false)
    }
  }

  const onCreated = (key: ApiKeySummary) => setLoad((current) => current.status === 'ready' ? { ...current, keys: [key, ...current.keys] } : current)

  const onRevoked = (key: ApiKeySummary) => {
    setLoad((current) => current.status === 'ready' ? { ...current, keys: current.keys.filter((item) => item.id !== key.id) } : current)
    setRevoking(null)
    setStatus(`Revoked “${key.name}”`)
  }

  const dialogOpen = creating || revoking !== null
  const createAction = <button ref={createButton} type="button" className="button-primary" onClick={() => setCreating(true)}>Create API key <span aria-hidden="true">+</span></button>

  return (
    <>
      {/* While a dialog is open the page behind it is inert: no clicks, no focus. */}
      <div className="auth-page" inert={dialogOpen}>
        <SignedInHeader />

        <main className="workspace">
          <Link className="back-link" to="/app"><span aria-hidden="true">←</span> Home</Link>
          <div className="workspace-heading">
            <div><p className="eyebrow"><span /> Access</p><h1>API keys</h1><p className="heading-note">Keys let scripts, CI jobs and alerting tools call the Tracehound API as you.</p></div>
            {load.status === 'ready' && load.keys.length === 0 ? null : createAction}
          </div>

          <section className="key-list" aria-labelledby="key-list-title" aria-busy={load.status === 'loading'}>
            <h2 id="key-list-title" className="sr-only">Your API keys</h2>
            {load.status === 'error' && <div className="notice" role="status">
              <div><p className="notice-title">Couldn’t load your API keys</p><p>{load.message}</p></div>
              <button type="button" className="button-quiet" onClick={retry}>Retry</button>
            </div>}
            {load.status === 'ready' && load.keys.length === 0 && <div className="key-empty">
              <p className="notice-title">No API keys yet</p>
              <p>Create a key to let a script or integration open cases without signing in. You’ll see the full key once, right after you create it.</p>
              {createAction}
            </div>}
            {(load.status === 'loading' || (load.status === 'ready' && load.keys.length > 0)) && <table className="key-table">
              <thead><tr><th scope="col">Name</th><th scope="col">Key</th><th scope="col">Created</th><th scope="col">Last used</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {load.status === 'loading' && [0, 1, 2].map((row) => <tr key={row} className="key-skeleton" aria-hidden="true">
                  {[0, 1, 2, 3, 4].map((cell) => <td key={cell}><span className="skeleton" /></td>)}
                </tr>)}
                {load.status === 'ready' && load.keys.map((key) => <tr key={key.id} className={key.id === highlight ? 'is-new' : undefined}>
                  <td data-label="Name" className="key-name">{key.name}</td>
                  <td data-label="Key"><code>{masked(key)}</code></td>
                  <td data-label="Created">{formatDate(key.created_at)}</td>
                  <td data-label="Last used">{key.last_used_at ? formatTime(key.last_used_at) : 'Never'}</td>
                  <td className="key-action"><button type="button" className="button-quiet button-danger" onClick={() => setRevoking(key)} aria-label={`Revoke ${key.name}`}>Revoke</button></td>
                </tr>)}
              </tbody>
            </table>}
            {load.status === 'loading' && <p className="sr-only" role="status">Loading API keys</p>}
            {load.status === 'ready' && load.next && <div className="list-state">
              <button type="button" className="button-quiet" onClick={() => void loadMore()} disabled={loadingMore}>{loadingMore ? 'Loading…' : 'Load more'}</button>
              {moreError && <p className="form-error" role="alert">{moreError}</p>}
            </div>}
          </section>
        </main>
      </div>

      <div className="toast-region" role="status" aria-live="polite">{status && <p className="toast">{status}</p>}</div>

      {creating && <CreateKeyDialog fallbackFocus={createButton} onCreated={onCreated} onClose={(key) => {
        setCreating(false)
        if (key) { setHighlight(key.id); setStatus(`Created “${key.name}”`) }
      }} />}
      {revoking && <RevokeKeyDialog apiKey={revoking} fallbackFocus={createButton} onRevoked={onRevoked} onClose={() => setRevoking(null)} />}
    </>
  )
}

// The fallback ref is read when focus moves back, not when the dialog opened.
const restoreFocus = (opener: HTMLElement | null, fallback: RefObject<HTMLElement | null>) => (opener?.isConnected && opener !== document.body ? opener : fallback.current)?.focus()

/** A modal dialog: focus stays inside, and Esc or a backdrop click call onDismiss
 *  when it is set. Pass null to require an explicit button instead. */
function Dialog({ labelledBy, describedBy, onDismiss, fallbackFocus, wide = false, children }: { labelledBy: string, describedBy?: string, onDismiss: (() => void) | null, fallbackFocus: RefObject<HTMLElement | null>, wide?: boolean, children: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null)
  // Read during the first render: by the time effects run, autoFocus has already moved focus inside.
  const [opener] = useState(() => document.activeElement as HTMLElement | null)

  // Lock page scroll while open; on close, return focus to whatever opened the
  // dialog, or to the fallback when that element has gone (a revoked row).
  useEffect(() => {
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    if (!panel.current?.contains(document.activeElement)) panel.current?.focus()
    return () => {
      document.body.style.overflow = overflow
      // Decide after the page re-renders: the revoked row is gone, the empty state's button may be new.
      requestAnimationFrame(() => restoreFocus(opener, fallbackFocus))
    }
  }, [opener, fallbackFocus])

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      onDismiss?.()
      return
    }
    if (event.key !== 'Tab' || !panel.current) return
    const focusable = [...panel.current.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), [href], [tabindex]:not([tabindex="-1"])')]
    if (!focusable.length) return
    const first = focusable[0]!
    const last = focusable.at(-1)!
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }

  return (
    <div className="dialog-backdrop" onPointerDown={(event) => {
      if (event.target !== event.currentTarget) return
      // Keep focus inside the dialog, so Esc still reaches it after a backdrop click.
      event.preventDefault()
      onDismiss?.()
    }}>
      <div ref={panel} className={wide ? 'dialog dialog-wide' : 'dialog'} role="dialog" aria-modal="true" aria-labelledby={labelledBy} aria-describedby={describedBy} tabIndex={-1} onKeyDown={onKeyDown}>
        {children}
      </div>
    </div>
  )
}

function CreateKeyDialog({ fallbackFocus, onCreated, onClose }: { fallbackFocus: RefObject<HTMLElement | null>, onCreated: (key: ApiKeySummary) => void, onClose: (created: ApiKeyCreated | null) => void }) {
  const [name, setName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The raw key lives only in this state: never stored, gone once the dialog closes.
  const [created, setCreated] = useState<ApiKeyCreated | null>(null)
  const [copied, setCopied] = useState<'idle' | 'copied' | 'failed'>('idle')
  const [stored, setStored] = useState(false)

  useEffect(() => {
    if (copied !== 'copied') return
    const timer = setTimeout(() => setCopied('idle'), 2000)
    return () => clearTimeout(timer)
  }, [copied])

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const key = await createApiKey(trimmed)
      onCreated({ id: key.id, name: key.name, prefix: key.prefix, suffix: key.suffix, created_at: key.created_at, last_used_at: null })
      setCreated(key)
    } catch (err) {
      setError(message(err, 'Could not create the key.'))
    } finally {
      setSubmitting(false)
    }
  }

  const copy = async () => {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.key)
      setCopied('copied')
    } catch {
      setCopied('failed')
    }
  }

  // Step 2 closes only through "Done": losing the key by a stray Esc is not recoverable.
  if (created) return (
    <Dialog labelledBy="key-dialog-title" describedBy="key-dialog-warning" onDismiss={null} fallbackFocus={fallbackFocus} wide>
      <div className="reveal-header">
        <span className="reveal-badge" aria-hidden="true"><svg viewBox="0 0 20 20" width="20" height="20"><path d="M5.5 10.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
        <div>
          <h2 id="key-dialog-title">API key created</h2>
          <p className="reveal-meta"><span className="key-chip">{created.name}</span><span>Created {formatTime(created.created_at)}</span></p>
        </div>
      </div>

      <div className="reveal-field">
        {/* One line; a click selects the whole key, and Copy always copies all of it. */}
        <code title={created.key}>{created.key}</code>
        <button type="button" className="reveal-copy" onClick={() => void copy()} autoFocus>
          {copied === 'copied'
            ? <><svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>Copied</>
            : <><svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="5.5" y="5.5" width="8" height="8" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M10.5 3.5v-.5a1.5 1.5 0 0 0-1.5-1.5H4a1.5 1.5 0 0 0-1.5 1.5v5A1.5 1.5 0 0 0 4 9.5h.5" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>Copy</>}
        </button>
      </div>
      <p className="sr-only" role="status">{copied === 'copied' ? 'Key copied to the clipboard.' : ''}</p>
      {copied === 'failed' && <p className="form-error" role="alert">Could not reach the clipboard. Click the key to select it, then copy it manually.</p>}

      <div id="key-dialog-warning" className="reveal-callout">
        <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M8 1.75l6.5 11.5h-13z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /><path d="M8 6.25v3M8 11.25v.01" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
        <div>
          <p>You won’t be able to see this key again. Store it in a password manager or secret store.</p>
          <p className="reveal-callout-note">Lost it? Revoke it and create another.</p>
        </div>
      </div>

      <div className="reveal-footer">
        <label className="reveal-check"><input type="checkbox" checked={stored} onChange={(event) => setStored(event.target.checked)} />I’ve stored this key somewhere safe</label>
        <button type="button" className="button-primary" onClick={() => onClose(created)} disabled={!stored}>Done, I’ve saved it</button>
      </div>
    </Dialog>
  )

  return (
    <Dialog labelledBy="key-dialog-title" onDismiss={submitting ? null : () => onClose(null)} fallbackFocus={fallbackFocus}>
      <form className="dialog-form" onSubmit={submit}>
        <h2 id="key-dialog-title">Create API key</h2>
        <label htmlFor="key-name">Name</label>
        <input id="key-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={nameLimit} placeholder="CI pipeline" autoComplete="off" aria-describedby="key-name-hint" aria-invalid={error ? true : undefined} autoFocus />
        <p id="key-name-hint" className="field-hint"><span>e.g. CI pipeline. Name it after where the key will be used.</span><span className="field-count">{name.length}/{nameLimit}</span></p>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="dialog-actions">
          <button type="button" className="button-quiet" onClick={() => onClose(null)} disabled={submitting}>Cancel</button>
          <button type="submit" className="button-primary" disabled={!name.trim() || submitting}>{submitting ? 'Creating…' : 'Create key'}</button>
        </div>
      </form>
    </Dialog>
  )
}

function RevokeKeyDialog({ apiKey, fallbackFocus, onRevoked, onClose }: { apiKey: ApiKeySummary, fallbackFocus: RefObject<HTMLElement | null>, onRevoked: (key: ApiKeySummary) => void, onClose: () => void }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const revoke = async () => {
    setPending(true)
    setError(null)
    try {
      await revokeApiKey(apiKey.id)
      onRevoked(apiKey)
    } catch (err) {
      // Already gone on the server: the outcome the user asked for.
      if (err instanceof ApiError && err.status === 404) onRevoked(apiKey)
      else { setError(message(err, 'Could not revoke the key.')); setPending(false) }
    }
  }

  return (
    <Dialog labelledBy="revoke-dialog-title" describedBy="revoke-dialog-body" onDismiss={pending ? null : onClose} fallbackFocus={fallbackFocus}>
      <h2 id="revoke-dialog-title">Revoke “{apiKey.name}”?</h2>
      <div id="revoke-dialog-body">
        <p className="dialog-key"><code>{masked(apiKey)}</code></p>
        <p>Apps and scripts using this key will stop working immediately. This can’t be undone.</p>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="dialog-actions">
        <button type="button" className="button-quiet" onClick={onClose} disabled={pending} autoFocus>Cancel</button>
        <button type="button" className="button-primary button-danger-solid" onClick={() => void revoke()} disabled={pending}>{pending ? 'Revoking…' : 'Revoke key'}</button>
      </div>
    </Dialog>
  )
}
