import { useEffect, useRef, useState, type ChangeEvent, type CSSProperties, type FormEvent, type RefObject } from 'react'
import { Link } from 'react-router'
import { ApiError, getCatalog, putCatalog, type CatalogEdge, type CatalogEntity, type CatalogSummary } from '../lib/api'
import Dialog from '../Dialog'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'

const MAX_BYTES = 1_048_576
const formatDateTime = (iso: string) => new Date(iso).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
const message = (err: unknown, fallback: string) => err instanceof Error ? err.message : fallback

const EXAMPLE = `apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: checkout-api
  annotations:
    github.com/project-slug: acme/checkout
spec:
  type: service
  owner: group:team-checkout
  dependsOn:
    - resource:orders-db
---
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: orders-db
  annotations:
    tracehound.dev/kind: postgres
spec:
  type: database
  owner: group:team-platform
`

type Load = { status: 'loading' } | { status: 'empty' } | { status: 'ready', catalog: CatalogSummary } | { status: 'error', message: string }

const fetchCatalog = (): Promise<Load> => getCatalog().then(
  (catalog) => ({ status: 'ready', catalog }),
  (err: unknown) => err instanceof ApiError && err.status === 404 ? { status: 'empty' } : { status: 'error', message: message(err, 'Could not load the catalog.') },
)

/** The user's Backstage catalog-info.yaml: which services exist, who owns them and what each depends on. */
export default function Catalog() {
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const [editing, setEditing] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    let active = true
    fetchCatalog().then((next) => { if (active) setLoad(next) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!status) return
    const timer = setTimeout(() => setStatus(null), 4000)
    return () => clearTimeout(timer)
  }, [status])

  const retry = () => { setLoad({ status: 'loading' }); void fetchCatalog().then(setLoad) }
  const catalog = load.status === 'ready' ? load.catalog : null

  const onSaved = (saved: CatalogSummary) => {
    setLoad({ status: 'ready', catalog: saved })
    setEditing(false)
    setStatus(`Catalog saved: ${saved.entities.length} ${saved.entities.length === 1 ? 'entity' : 'entities'}`)
  }

  return (
    <>
      <div className="auth-page" inert={editing}>
        <SignedInHeader />

        <main className="workspace">
          <Link className="back-link" to="/app"><span aria-hidden="true">←</span> Home</Link>
          <div className="workspace-heading">
            <div><p className="eyebrow"><span /> Topology</p><h1 ref={heading} tabIndex={-1}>Service catalog</h1><p className="heading-note">Your Backstage <code>catalog-info.yaml</code>. Triage reads it to know which services call which, and who owns each one.</p></div>
            {catalog && <button type="button" className="button-primary" onClick={() => setEditing(true)}>Replace catalog</button>}
          </div>

          <section className="catalog" aria-labelledby="catalog-title" aria-busy={load.status === 'loading'}>
            <h2 id="catalog-title" className="sr-only">Catalog</h2>
            {load.status === 'loading' && <><p className="sr-only" role="status">Loading the catalog</p><div className="skeleton catalog-skeleton" aria-hidden="true" /></>}
            {load.status === 'error' && <div className="notice" role="status">
              <div><p className="notice-title">Couldn’t load your catalog</p><p>{load.message}</p></div>
              <button type="button" className="button-quiet" onClick={retry}>Retry</button>
            </div>}
            {load.status === 'empty' && <EmptyCatalog onStart={() => setEditing(true)} />}
            {catalog && <CatalogView catalog={catalog} />}
          </section>
        </main>
      </div>

      <div className="toast-region" role="status" aria-live="polite">{status && <p className="toast">{status}</p>}</div>

      {editing && <CatalogDialog current={catalog?.source} fallbackFocus={heading} onSaved={onSaved} onClose={() => setEditing(false)} />}
    </>
  )
}

function EmptyCatalog({ onStart }: { onStart: () => void }) {
  return (
    <div className="catalog-empty">
      <p className="notice-title">No catalog yet</p>
      <p>Upload the <code>catalog-info.yaml</code> you keep for Backstage, or paste one in. Each service is a <code>Component</code>, each database or queue a <code>Resource</code>, and <code>spec.dependsOn</code> says what calls what.</p>
      <button type="button" className="button-primary" onClick={onStart}>Add catalog <span aria-hidden="true">+</span></button>
    </div>
  )
}

function CatalogView({ catalog }: { catalog: CatalogSummary }) {
  const services = catalog.entities.filter((entity) => entity.entity_kind === 'Component')
  const resources = catalog.entities.filter((entity) => entity.entity_kind === 'Resource')
  const ignored = Object.entries(catalog.ignored)

  return (
    <>
      <p className="catalog-meta">
        <span><strong>{services.length}</strong> {services.length === 1 ? 'service' : 'services'}</span>
        <span><strong>{resources.length}</strong> {resources.length === 1 ? 'resource' : 'resources'}</span>
        <span><strong>{catalog.edges.length}</strong> {catalog.edges.length === 1 ? 'dependency' : 'dependencies'}</span>
        <span>Updated {formatDateTime(catalog.updated_at)}</span>
      </p>
      {ignored.length > 0 && <p className="catalog-ignored">Also read, but not part of the graph: {ignored.map(([kind, count]) => `${count} ${kind}`).join(', ')}.</p>}

      <EntityGroup title="Services" entities={services} edges={catalog.edges} all={catalog.entities} />
      <EntityGroup title="Resources" entities={resources} edges={catalog.edges} all={catalog.entities} />

      <details className="catalog-source">
        <summary>View <code>catalog-info.yaml</code></summary>
        <pre><code>{catalog.source}</code></pre>
      </details>
    </>
  )
}

function EntityGroup({ title, entities, edges, all }: { title: string, entities: CatalogEntity[], edges: CatalogEdge[], all: CatalogEntity[] }) {
  if (!entities.length) return null
  const id = `catalog-${title.toLowerCase()}`
  return (
    <section className="catalog-group" aria-labelledby={id}>
      <h3 id={id} className="catalog-group-title">{title}</h3>
      <ul>
        {entities.map((entity) => <EntityCard key={entity.name} entity={entity} calls={edges.filter((edge) => edge.source === entity.name)} calledBy={edges.filter((edge) => edge.target === entity.name)} all={all} />)}
      </ul>
    </section>
  )
}

function EntityCard({ entity, calls, calledBy, all }: { entity: CatalogEntity, calls: CatalogEdge[], calledBy: CatalogEdge[], all: CatalogEntity[] }) {
  const isService = entity.entity_kind === 'Component'
  const color = isService ? 'var(--color-primary)' : 'var(--agent-dependency)'
  const kindOf = (name: string) => all.find((item) => item.name === name)?.entity_kind === 'Resource' ? 'is-resource' : 'is-service'
  return (
    <li className="source catalog-entity" style={{ '--source-color': color } as CSSProperties} aria-labelledby={`entity-${entity.name}`}>
      <div className="source-identity">
        <p className="eyebrow"><span /> {isService ? 'Service' : 'Resource'} · {entity.kind}</p>
        <h3 id={`entity-${entity.name}`}><code>{entity.name}</code>{entity.title && <span className="catalog-title-alt">{entity.title}</span>}</h3>
        {entity.description && <p className="source-description">{entity.description}</p>}
      </div>

      {(calls.length > 0 || calledBy.length > 0) && <div className="catalog-links">
        {calls.length > 0 && <div><span className="catalog-links-label">Depends on</span><ul>{calls.map((edge) => <li key={edge.target} className={`catalog-chip ${kindOf(edge.target)}`}><span aria-hidden="true">→</span> <code>{edge.target}</code> <span className="catalog-protocol">{edge.protocol}</span></li>)}</ul></div>}
        {calledBy.length > 0 && <div><span className="catalog-links-label">Used by</span><ul>{calledBy.map((edge) => <li key={edge.source} className={`catalog-chip ${kindOf(edge.source)}`}><span aria-hidden="true">←</span> <code>{edge.source}</code></li>)}</ul></div>}
      </div>}

      <dl className="source-details catalog-details">
        <div><dt>Owner</dt><dd><code>{entity.owner}</code></dd></div>
        <div><dt>Type</dt><dd>{entity.type}</dd></div>
        <div><dt>System</dt><dd>{entity.system ? <code>{entity.system}</code> : '—'}</dd></div>
        <div><dt>Lifecycle</dt><dd>{entity.lifecycle ?? '—'}</dd></div>
        {isService && <div><dt>Repository</dt><dd>{entity.repository ? <code>{entity.repository}</code> : '—'}</dd></div>}
      </dl>
    </li>
  )
}

/** Paste or upload a catalog-info.yaml. A file is read in the browser and sent as text. */
function CatalogDialog({ current, fallbackFocus, onSaved, onClose }: { current?: string, fallbackFocus: RefObject<HTMLElement | null>, onSaved: (catalog: CatalogSummary) => void, onClose: () => void }) {
  const [text, setText] = useState(current ?? '')
  const [fileName, setFileName] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const fileInput = useRef<HTMLInputElement>(null)

  const size = new Blob([text]).size
  const tooLarge = size > MAX_BYTES
  const unchanged = current !== undefined && text === current
  const complete = text.trim().length > 0 && !tooLarge && !unchanged

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''  // picking the same file again still fires change
    if (!file) return
    if (file.size > MAX_BYTES) { setError(`${file.name} is over 1 MB.`); return }
    setText(await file.text())
    setFileName(file.name)
    setError(null)
    setProblems([])
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!complete || submitting) return
    setSubmitting(true)
    setError(null)
    setProblems([])
    try {
      onSaved(await putCatalog(text))
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.problems.length) {
        setError(err.problems.length === 1 ? 'The catalog has a problem:' : `The catalog has ${err.problems.length} problems:`)
        setProblems(err.problems)
      } else setError(message(err, 'Could not save the catalog.'))
      setSubmitting(false)
    }
  }

  return (
    <Dialog labelledBy="catalog-dialog-title" describedBy="catalog-dialog-intro" onDismiss={submitting ? null : onClose} fallbackFocus={fallbackFocus} wide>
      <form className="dialog-form catalog-form" onSubmit={submit} noValidate>
        <h2 id="catalog-dialog-title">{current === undefined ? 'Add your catalog' : 'Replace your catalog'}</h2>
        <p id="catalog-dialog-intro">Upload or paste a Backstage <code>catalog-info.yaml</code>. Separate entities with <code>---</code>. Saving replaces the whole catalog.</p>

        <div className="catalog-file">
          <input ref={fileInput} type="file" accept=".yaml,.yml,application/yaml,text/yaml" onChange={(event) => void onFile(event)} hidden />
          <button type="button" className="button-quiet" onClick={() => fileInput.current?.click()}>Choose file…</button>
          <span className="field-hint">{fileName ? <>Loaded <code>{fileName}</code></> : 'or paste below'}</span>
          {!text && <button type="button" className="button-quiet catalog-example" onClick={() => setText(EXAMPLE)}>Start from an example</button>}
        </div>

        <div className="connect-field">
          <label htmlFor="catalog-yaml">catalog-info.yaml</label>
          <textarea id="catalog-yaml" className="catalog-editor" value={text} onChange={(event) => { setText(event.target.value); setFileName(null) }} spellCheck={false} autoComplete="off" autoCapitalize="off" rows={16} placeholder="apiVersion: backstage.io/v1alpha1" aria-describedby="catalog-yaml-hint" aria-invalid={problems.length || tooLarge ? true : undefined} autoFocus />
          <p id="catalog-yaml-hint" className={tooLarge ? 'field-hint is-error' : 'field-hint'}>{tooLarge ? 'Over the 1 MB limit.' : `${(size / 1024).toFixed(1)} KB of 1 MB`}</p>
        </div>

        {error && <div className="form-error" role="alert">
          <p>{error}</p>
          {problems.length > 0 && <ul className="catalog-problems">{problems.map((problem) => <li key={problem}>{problem}</li>)}</ul>}
        </div>}
        <div className="dialog-actions">
          <button type="button" className="button-quiet" onClick={onClose} disabled={submitting}>Cancel</button>
          <button type="submit" className="button-primary" disabled={!complete || submitting}>{submitting ? 'Saving…' : unchanged ? 'No changes' : 'Save catalog'}</button>
        </div>
      </form>
    </Dialog>
  )
}
