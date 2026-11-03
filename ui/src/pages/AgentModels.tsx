import { useEffect, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { Link } from 'react-router'
import { agentRoster } from '../lib/agents'
import { getAgentModels, saveAgentModel, type AgentId, type AgentModelConfig, type AgentModels as Catalog } from '../lib/agentModels'
import ModelDetailsPanel from '../ModelDetailsPanel'
import ModelSelect from '../ModelSelect'
import { tokens } from '../lib/modelDetails'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'

const count = agentRoster.length
const without = <T extends object>(record: T, key: keyof T): T => { const next = { ...record }; delete next[key]; return next }
const same = (a: AgentModelConfig, b: AgentModelConfig) => a.provider === b.provider && a.model === b.model
/** Shortest signed distance from the active slot, so the belt wraps around: -3..2 for six agents. */
const offsetFrom = (index: number, active: number) => ((index - active + count + Math.floor(count / 2)) % count) - Math.floor(count / 2)

type Load = { status: 'loading' } | { status: 'ready', catalog: Catalog }

export default function AgentModels() {
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const [active, setActive] = useState(0)
  // The model card stays closed until an agent is picked from the belt.
  const [open, setOpen] = useState(false)
  // Unsaved edits per agent; an agent without an entry shows what's saved.
  const [drafts, setDrafts] = useState<Partial<Record<AgentId, AgentModelConfig>>>({})
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    void getAgentModels().then((catalog) => { if (live) setLoad({ status: 'ready', catalog }) })
    return () => { live = false }
  }, [])
  useEffect(() => {
    if (!status) return
    const timer = setTimeout(() => setStatus(null), 4000)
    return () => clearTimeout(timer)
  }, [status])

  const agent = agentRoster[active]
  const step = (by: number) => setActive((current) => (current + by + count) % count)
  const onBeltKey = (event: KeyboardEvent) => {
    if (event.key === 'ArrowRight') { event.preventDefault(); step(1) }
    if (event.key === 'ArrowLeft') { event.preventDefault(); step(-1) }
    if (event.key === 'Escape' && open) setOpen(false)
  }

  const save = async (id: AgentId, config: AgentModelConfig) => {
    setSaving(true)
    try {
      const stored = await saveAgentModel(id, config)
      setLoad((current) => current.status === 'ready' ? { status: 'ready', catalog: { ...current.catalog, agents: stored.agents, defaults: stored.defaults, customized: stored.customized, configured: stored.configured } } : current)
      setDrafts((current) => without(current, id))
      setStatus(`Saved ${agentRoster.find((a) => a.id === id)?.name}’s model`)
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Could not save the model. Try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="auth-page">
        <SignedInHeader />
        <main className="workspace">
          <Link className="back-link" to="/app"><span aria-hidden="true">←</span> Home</Link>
          <div className="workspace-heading">
            <div><p className="eyebrow"><span /> Agents</p><h1>Agent configuration</h1><p className="heading-note">Pick the model each investigator thinks with. Investigations need your choice saved here before they can start.</p></div>
          </div>

          {load.status === 'ready' && !load.catalog.configured && <div className="notice models-setup" role="status">
            <div>
              <p className="notice-title">Your agents aren’t configured yet</p>
              <p>Investigations can’t start until you choose a model. Pick an agent below, choose its provider and model, and save. You can start with the suggested defaults.</p>
            </div>
          </div>}

          <div className={`models-layout${open ? ' is-open' : ''}`}>
            <section className="roster" aria-roledescription="carousel" aria-label="Agents" onKeyDown={onBeltKey}>
              <div className="roster-stage">
                {agentRoster.map((item, index) => {
                  const offset = offsetFrom(index, active)
                  const hidden = Math.abs(offset) > 2
                  const custom = load.status === 'ready' && load.catalog.customized.includes(item.id)
                  return (
                    <button key={item.id} type="button" className="roster-card" data-offset={offset} aria-hidden={hidden || undefined} tabIndex={offset === 0 ? 0 : -1}
                      aria-label={offset === 0 ? `Configure ${item.name}, ${item.specialty} agent` : `${item.name}, ${item.specialty} agent`} aria-current={offset === 0 || undefined}
                      aria-expanded={offset === 0 ? open : undefined} aria-controls={offset === 0 && open ? 'model-card' : undefined}
                      onClick={() => offset === 0 ? setOpen(true) : setActive(index)}
                      style={{ '--offset': offset, '--abs': Math.abs(offset), '--agent': item.color } as CSSProperties}>
                      <img src={item.image} alt="" draggable={false} />
                      <span className="roster-name"><strong>{item.name}</strong>{item.specialty}</span>
                      {custom && <span className="roster-badge">Custom</span>}
                      {offset === 0 && !open && <span className="roster-cta">Configure model →</span>}
                    </button>
                  )
                })}
              </div>
              <div className="roster-controls">
                <button type="button" className="roster-arrow" onClick={() => step(-1)} aria-label="Previous agent">←</button>
                <ol className="roster-belt" aria-label="Choose an agent">
                  {agentRoster.map((item, index) => <li key={item.id}>
                    <button type="button" className="roster-dot" aria-current={index === active || undefined} onClick={() => setActive(index)} style={{ '--agent': item.color } as CSSProperties}>
                      <span className="sr-only">{item.name}, {item.specialty}</span>
                      <span aria-hidden="true">{item.specialty}</span>
                    </button>
                  </li>)}
                </ol>
                <button type="button" className="roster-arrow" onClick={() => step(1)} aria-label="Next agent">→</button>
              </div>
              <p className="roster-hint">{open ? 'Rotate to switch agents. Esc closes the card.' : 'Rotate with ← and →, then click the agent in front to choose its model.'}</p>
            </section>

            {!open ? null : load.status === 'loading'
              ? <aside className="model-card" aria-busy="true"><p className="sr-only" role="status">Loading models</p><span className="skeleton" /><span className="skeleton" /><span className="skeleton" /></aside>
              : <ModelCard key={agent.id} agent={agent} catalog={load.catalog} draft={drafts[agent.id]} saving={saving}
                onChange={(config) => setDrafts((current) => ({ ...current, [agent.id]: config }))}
                onDiscard={() => setDrafts((current) => without(current, agent.id))}
                onSave={(config) => void save(agent.id, config)} onClose={() => setOpen(false)} />}
          </div>
        </main>
      </div>
      <div className="toast-region" role="status" aria-live="polite">{status && <p className="toast">{status}</p>}</div>
    </>
  )
}

type CardProps = {
  agent: (typeof agentRoster)[number]
  catalog: Catalog
  draft: AgentModelConfig | undefined
  saving: boolean
  onChange: (config: AgentModelConfig) => void
  onDiscard: () => void
  onSave: (config: AgentModelConfig) => void
  onClose: () => void
}

function ModelCard({ agent, catalog, draft, saving, onChange, onDiscard, onSave, onClose }: CardProps) {
  const saved = catalog.agents[agent.id]
  const config = draft ?? saved
  const provider = catalog.providers.find((p) => p.id === config.provider) ?? catalog.providers[0]
  const model = provider.models.find((m) => m.id === config.model) ?? provider.models[0]
  const options = provider.models.map((m) => ({ id: m.id, label: m.label, hint: m.details.context_length ? `${tokens(m.details.context_length)} context` : undefined }))
  const dirty = !same(config, saved)
  const isDefault = same(config, catalog.defaults[agent.id])
  // Until a choice is saved the agent only shows its default, so saving it once is allowed unchanged.
  const unsaved = !catalog.customized.includes(agent.id)

  const pickProvider = (id: string) => {
    const next = catalog.providers.find((p) => p.id === id)
    if (next) onChange({ ...config, provider: id, model: next.models[0].id })
  }

  return (
    <aside id="model-card" className="model-card" aria-labelledby="model-card-title" style={{ '--agent': agent.color } as CSSProperties}>
      <h2 id="model-card-title" className="sr-only">{agent.name}, {agent.specialty} agent: model settings</h2>

      <div className="model-field">
        <div className="model-field-top">
          <span className="model-field-label">Provider</span>
          <button type="button" className="model-card-close" onClick={onClose} aria-label="Close model settings">×</button>
        </div>
        <ModelSelect label={`Provider for ${agent.name}`} value={provider.id} options={catalog.providers} onChange={pickProvider} />
      </div>

      <div className="model-field">
        <span className="model-field-label">Model</span>
        <ModelSelect label={`Model for ${agent.name}`} value={model.id} options={options} onChange={(id) => onChange({ ...config, model: id })} />
        <ModelDetailsPanel model={model.details} />
      </div>

      <div className="model-actions">
        <button type="button" className="button-quiet" disabled={isDefault || saving} onClick={() => onChange({ ...catalog.defaults[agent.id] })}>Reset to default</button>
        <span className="model-actions-end">
          {dirty && <button type="button" className="button-quiet" disabled={saving} onClick={onDiscard}>Discard</button>}
          <button type="button" className="button-primary" disabled={(!dirty && !unsaved) || saving} onClick={() => onSave(config)}>{saving ? 'Saving…' : 'Save'}</button>
        </span>
      </div>
    </aside>
  )
}
