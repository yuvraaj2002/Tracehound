import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type RefObject } from 'react'
import { Link } from 'react-router'
import { ApiError, getCatalog, getCatalogSample, putCatalog, validateCatalog, type CatalogEdge, type CatalogEntity, type CatalogGraphData, type CatalogSample, type CatalogSummary } from '../lib/api'
import CatalogGraph from '../CatalogGraph'
import Dialog from '../Dialog'
import SetupTabs from '../SetupTabs'
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
  const [sampleOpen, setSampleOpen] = useState(false)
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
      <div className="auth-page" inert={sampleOpen}>
        <SignedInHeader />

        <main className="workspace">
          <Link className="back-link" to="/app"><span aria-hidden="true">←</span> Home</Link>
          <SetupTabs />
          <div className="workspace-heading catalog-heading">
            <h1 ref={heading} tabIndex={-1}>Service catalog</h1>
            <div className="catalog-heading-actions">
              {catalog && !editing && <button type="button" className="button-quiet" onClick={() => setEditing(true)}>Edit</button>}
              <button type="button" className="button-quiet" onClick={() => setSampleOpen(true)}>View sample</button>
            </div>
          </div>

          <section className="catalog" aria-labelledby="catalog-title" aria-busy={load.status === 'loading'}>
            <div className="catalog-section-head">
              <h2 id="catalog-title">Your catalog</h2>
            </div>
            {load.status === 'loading' && <><p className="sr-only" role="status">Loading the catalog</p><div className="skeleton catalog-skeleton" aria-hidden="true" /></>}
            {load.status === 'error' && <div className="notice" role="status">
              <div><p className="notice-title">Couldn’t load your catalog</p><p>{load.message}</p></div>
              <button type="button" className="button-quiet" onClick={retry}>Retry</button>
            </div>}
            {load.status === 'empty' && !editing && <EmptyCatalog onStart={() => setEditing(true)} />}
            {editing ? <CatalogEditor current={catalog?.source} onSaved={onSaved} onClose={() => setEditing(false)} /> : catalog && <CatalogView catalog={catalog} />}
          </section>
        </main>
      </div>

      <div className="toast-region" role="status" aria-live="polite">{status && <p className="toast">{status}</p>}</div>

      {sampleOpen && <SampleDialog fallbackFocus={heading} onClose={() => setSampleOpen(false)} />}
    </>
  )
}

type SampleLoad = { status: 'loading' } | { status: 'ready', sample: CatalogSample } | { status: 'error', message: string }

/** An example catalog-info.yaml and the graph Tracehound draws from it. Read-only: nothing here is saved. */
function SampleDialog({ fallbackFocus, onClose }: { fallbackFocus: RefObject<HTMLElement | null>, onClose: () => void }) {
  const [load, setLoad] = useState<SampleLoad>({ status: 'loading' })

  const fetchSample = () => getCatalogSample().then(
    (sample): SampleLoad => ({ status: 'ready', sample }),
    (err: unknown): SampleLoad => ({ status: 'error', message: message(err, 'Could not load the sample.') }),
  )
  useEffect(() => {
    let active = true
    void fetchSample().then((next) => { if (active) setLoad(next) })
    return () => { active = false }
  }, [])

  const retry = () => { setLoad({ status: 'loading' }); void fetchSample().then(setLoad) }

  return (
    <Dialog labelledBy="catalog-sample-title" describedBy="catalog-sample-intro" onDismiss={onClose} fallbackFocus={fallbackFocus} wide>
      <div className="sample-dialog" aria-busy={load.status === 'loading'}>
        <h2 id="catalog-sample-title">Sample catalog</h2>
        <p id="catalog-sample-intro">A small checkout platform, to show the format and the map Tracehound builds from it. Nothing here is saved to your account.</p>
        {load.status === 'loading' && <><p className="sr-only" role="status">Loading the sample</p><div className="skeleton catalog-skeleton" aria-hidden="true" /></>}
        {load.status === 'error' && <div className="notice" role="status">
          <div><p className="notice-title">Couldn’t load the sample</p><p>{load.message}</p></div>
          <button type="button" className="button-quiet" onClick={retry}>Retry</button>
        </div>}
        {load.status === 'ready' && <CatalogViews entities={load.sample.entities} edges={load.sample.edges} source={load.sample.source} label="Sample" />}
        <div className="dialog-actions"><button type="button" className="button-primary" onClick={onClose} autoFocus>Close</button></div>
      </div>
    </Dialog>
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

/** The graph and the file, one at a time. Shared by the user's catalog and the sample. */
function CatalogViews({ entities, edges, source, label, meta }: { entities: CatalogEntity[], edges: CatalogEdge[], source: string, label: string, meta?: string }) {
  const [view, setView] = useState<'graph' | 'yaml'>('graph')
  const [copied, setCopied] = useState<'done' | 'failed' | null>(null)

  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(null), 2000)
    return () => clearTimeout(timer)
  }, [copied])

  const copy = async () => {
    try { await navigator.clipboard.writeText(source); setCopied('done') } catch { setCopied('failed') }
  }

  return (
    <>
      <div className="catalog-views-bar">
        <div className="catalog-sample-tabs" role="group" aria-label={`${label} view`}>
          <button type="button" className="button-quiet" aria-pressed={view === 'graph'} onClick={() => setView('graph')}>Graph</button>
          <button type="button" className="button-quiet" aria-pressed={view === 'yaml'} onClick={() => setView('yaml')}>catalog-info.yaml</button>
        </div>
        {meta && <p className="catalog-views-meta">{meta}</p>}
        {view === 'yaml' && <button type="button" className="editor-link" onClick={() => void copy()}>{copied === 'done' ? 'Copied' : copied === 'failed' ? 'Press ⌘C to copy' : 'Copy'}</button>}
        <span className="sr-only" role="status">{copied === 'done' ? 'Copied to clipboard' : ''}</span>
      </div>
      {view === 'graph' ? <CatalogGraph entities={entities} edges={edges} /> : <pre className="catalog-sample-source" tabIndex={0}><code>{source}</code></pre>}
    </>
  )
}

function CatalogView({ catalog }: { catalog: CatalogSummary }) {
  const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
  const services = catalog.entities.filter((entity) => entity.entity_kind === 'Component').length
  const meta = [count(services, 'service', 'services'), count(catalog.entities.length - services, 'resource', 'resources'), count(catalog.edges.length, 'dependency', 'dependencies'), `Updated ${formatDateTime(catalog.updated_at)}`].join(' · ')
  return <CatalogViews entities={catalog.entities} edges={catalog.edges} source={catalog.source} label="Your catalog" meta={meta} />
}

const PREVIEW_DELAY_MS = 400

type Preview = { status: 'idle' | 'checking' } | { status: 'valid' } | { status: 'invalid', problems: string[] } | { status: 'failed', message: string }

/**
 * Inline on the page: write or paste a catalog-info.yaml on the left and see the graph it describes on the right.
 * The server checks the text as you type; Save sends it to PUT and is only offered once it is valid.
 */
function CatalogEditor({ current, onSaved, onClose }: { current?: string, onSaved: (catalog: CatalogSummary) => void, onClose: () => void }) {
  const [text, setText] = useState(current ?? '')
  const [fileName, setFileName] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveProblems, setSaveProblems] = useState<string[]>([])
  const [graph, setGraph] = useState<CatalogGraphData | null>(null)
  const [preview, setPreview] = useState<Preview>({ status: 'idle' })
  const fileInput = useRef<HTMLInputElement>(null)

  const size = new Blob([text]).size
  const tooLarge = size > MAX_BYTES
  const unchanged = current !== undefined && text === current
  const blank = text.trim().length === 0

  // Check the text shortly after typing stops. A newer edit makes an older answer stale.
  useEffect(() => {
    if (blank || tooLarge) return
    let active = true
    const timer = setTimeout(() => {
      setPreview({ status: 'checking' })
      validateCatalog(text).then(
        (result) => { if (active) { setGraph(result); setPreview({ status: 'valid' }) } },
        (err: unknown) => {
          if (!active) return
          setPreview(err instanceof ApiError && err.status === 422 && err.problems.length ? { status: 'invalid', problems: err.problems } : { status: 'failed', message: message(err, 'Could not check the catalog.') })
        },
      )
    }, PREVIEW_DELAY_MS)
    return () => { active = false; clearTimeout(timer) }
  }, [text, blank, tooLarge])

  const edit = (next: string, name: string | null = null) => {
    setText(next)
    setFileName(name)
    setSaveError(null)
    setSaveProblems([])
    setPreview(next.trim() ? { status: 'checking' } : { status: 'idle' })
  }

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''  // picking the same file again still fires change
    if (!file) return
    if (file.size > MAX_BYTES) { setSaveError(`${file.name} is over 1 MB.`); return }
    edit(await file.text(), file.name)
  }

  const valid = preview.status === 'valid' && !blank && !tooLarge
  const canSave = valid && !unchanged && !submitting

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!canSave) return
    setSubmitting(true)
    setSaveError(null)
    setSaveProblems([])
    try {
      onSaved(await putCatalog(text))
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.problems.length) {
        setSaveError(err.problems.length === 1 ? 'The catalog has a problem:' : `The catalog has ${err.problems.length} problems:`)
        setSaveProblems(err.problems)
      } else setSaveError(message(err, 'Could not save the catalog.'))
      setSubmitting(false)
    }
  }

  const problems = preview.status === 'invalid' ? preview.problems : []
  const stale = preview.status === 'invalid' || preview.status === 'failed'
  const summary = graph && `${graph.entities.length} ${graph.entities.length === 1 ? 'entity' : 'entities'}, ${graph.edges.length} ${graph.edges.length === 1 ? 'dependency' : 'dependencies'}`

  return (
    <form className="editor-inline" onSubmit={submit} noValidate aria-label={current === undefined ? 'Add your catalog' : 'Edit your catalog'}>
      <div className="editor-split">
        <div className="editor-pane">
          <div className="editor-bar">
            <input ref={fileInput} type="file" accept=".yaml,.yml,application/yaml,text/yaml" onChange={(event) => void onFile(event)} hidden />
            <button type="button" className="button-quiet" onClick={() => fileInput.current?.click()}>{fileName ?? 'Upload file'}</button>
            {blank && <button type="button" className="button-quiet" onClick={() => edit(EXAMPLE)}>Use example</button>}
          </div>
          <textarea id="catalog-yaml" className="catalog-editor" aria-label="catalog-info.yaml" value={text} onChange={(event) => edit(event.target.value)} spellCheck={false} autoComplete="off" autoCapitalize="off" placeholder="Paste your catalog-info.yaml" aria-invalid={problems.length || tooLarge ? true : undefined} autoFocus />
          {saveError && <div className="form-error" role="alert">
            <p>{saveError}</p>
            {saveProblems.length > 0 && <ul className="catalog-problems">{saveProblems.map((problem) => <li key={problem}>{problem}</li>)}</ul>}
          </div>}
          <div className="editor-actions">
            <button type="button" className="button-quiet" onClick={onClose} disabled={submitting}>Cancel</button>
            <button type="submit" className="button-primary" disabled={!canSave}>{submitting ? 'Saving…' : 'Save'}</button>
          </div>
        </div>

        <div className="editor-pane editor-preview">
          <div className="editor-bar">
            <p className={`editor-status is-${preview.status}`} aria-live="polite">
              {preview.status === 'checking' && 'Checking…'}
              {preview.status === 'valid' && `Valid${summary ? ` · ${summary}` : ''}`}
              {preview.status === 'invalid' && `${problems.length} ${problems.length === 1 ? 'problem' : 'problems'}`}
              {preview.status === 'failed' && preview.message}
              {tooLarge && 'Over the 1 MB limit'}
            </p>
          </div>
          {graph && !blank ? <div className={stale ? 'editor-graph is-stale' : 'editor-graph'}><CatalogGraph entities={graph.entities} edges={graph.edges} /></div> : <div className="editor-empty">{blank ? 'The graph appears here' : ''}</div>}
          {problems.length > 0 && <ul className="catalog-problems form-error">{problems.map((problem) => <li key={problem}>{problem}</li>)}</ul>}
        </div>
      </div>
    </form>
  )
}
