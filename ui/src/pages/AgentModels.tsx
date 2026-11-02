import { useEffect, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { Link } from 'react-router'
import { agentRoster } from '../lib/agents'
import { getAgentModels, saveAgentModel, type AgentId, type AgentModelConfig, type AgentModels as Catalog } from '../lib/modelsStub'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'

const count = agentRoster.length
const without = <T extends object>(record: T, key: keyof T): T => { const next = { ...record }; delete next[key]; return next }
const same = (a: AgentModelConfig, b: AgentModelConfig) => a.provider === b.provider && a.model === b.model && a.temperature === b.temperature
const formatTokens = (n: number) => n >= 1000 ? `${Math.round(n / 1000)}K` : String(n)
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
    const stored = await saveAgentModel(id, config)
    setLoad((current) => current.status === 'ready' ? { status: 'ready', catalog: { ...current.catalog, agents: { ...current.catalog.agents, [id]: stored } } } : current)
    setDrafts((current) => without(current, id))
    setSaving(false)
    setStatus(`Saved ${agentRoster.find((a) => a.id === id)?.name}’s model`)
  }

  return (
    <>
      <div className="auth-page">
        <SignedInHeader />
        <main className="workspace">
          <Link className="back-link" to="/app"><span aria-hidden="true">←</span> Home</Link>
          <div className="workspace-heading">
            <div><p className="eyebrow"><span /> Agents</p><h1>AI models</h1><p className="heading-note">Pick the model each investigator thinks with. A small local model keeps data on your servers; a hosted one reasons more deeply.</p></div>
          </div>
          <p className="billing-preview" role="note"><span aria-hidden="true">●</span> Preview: sample providers and choices until model settings go live. Saves last until you reload.</p>

          <div className={`models-layout${open ? ' is-open' : ''}`}>
            <section className="roster" aria-roledescription="carousel" aria-label="Agents" onKeyDown={onBeltKey}>
              <div className="roster-stage">
                {agentRoster.map((item, index) => {
                  const offset = offsetFrom(index, active)
                  const hidden = Math.abs(offset) > 2
                  const custom = load.status === 'ready' && !same(drafts[item.id] ?? load.catalog.agents[item.id], load.catalog.defaults)
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
  const dirty = !same(config, saved)
  const isDefault = same(config, catalog.defaults)

  const pickProvider = (id: string) => {
    const next = catalog.providers.find((p) => p.id === id)
    if (next?.connected) onChange({ ...config, provider: id, model: next.models[0].id })
  }

  return (
    <aside id="model-card" className="model-card" aria-labelledby="model-card-title" style={{ '--agent': agent.color } as CSSProperties}>
      <header className="model-card-head">
        <img src={agent.image} alt="" />
        <div>
          <p className="eyebrow"><span /> {agent.specialty} agent</p>
          <h2 id="model-card-title">{agent.name}</h2>
          <p className="model-card-job">{agent.job}</p>
        </div>
        <button type="button" className="model-card-close" onClick={onClose} aria-label="Close model settings">×</button>
      </header>

      <dl className="model-current">
        <div><dt>Provider</dt><dd>{provider.label}</dd></div>
        <div><dt>Model</dt><dd><code>{model.id}</code></dd></div>
        <div><dt>Context</dt><dd>{formatTokens(model.context_tokens)} tokens</dd></div>
      </dl>

      <fieldset className="model-field">
        <legend>Provider</legend>
        <div className="provider-grid">
          {catalog.providers.map((p) => <label key={p.id} className="provider-option" data-disabled={!p.connected || undefined}>
            <input type="radio" name={`provider-${agent.id}`} value={p.id} checked={p.id === provider.id} disabled={!p.connected} onChange={() => pickProvider(p.id)} />
            <span><strong>{p.label}</strong><small>{p.connected ? p.hosting : 'Add an API key to use (coming soon)'}</small></span>
          </label>)}
        </div>
      </fieldset>

      <div className="model-field">
        <label htmlFor={`model-${agent.id}`}>Model</label>
        <select id={`model-${agent.id}`} value={model.id} onChange={(event) => onChange({ ...config, model: event.target.value })}>
          {provider.models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
        <p className="field-hint"><span>{model.note}</span></p>
      </div>

      <div className="model-field">
        <label htmlFor={`temp-${agent.id}`}>Temperature <output htmlFor={`temp-${agent.id}`}>{config.temperature.toFixed(1)}</output></label>
        <input id={`temp-${agent.id}`} type="range" min={0} max={1} step={0.1} value={config.temperature} onChange={(event) => onChange({ ...config, temperature: Number(event.target.value) })} />
        <p className="field-hint"><span>Lower is steadier and repeatable. Investigations work best at 0.0 to 0.3.</span></p>
      </div>

      <div className="model-actions">
        <button type="button" className="button-quiet" disabled={isDefault || saving} onClick={() => onChange({ ...catalog.defaults })}>Reset to default</button>
        <span className="model-actions-end">
          {dirty && <button type="button" className="button-quiet" disabled={saving} onClick={onDiscard}>Discard</button>}
          <button type="button" className="button-primary" disabled={!dirty || saving} onClick={() => onSave(config)}>{saving ? 'Saving…' : 'Save'}</button>
        </span>
      </div>
    </aside>
  )
}
