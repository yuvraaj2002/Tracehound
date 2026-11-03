import { useState } from 'react'
import { tokens, type ModelDetails } from './lib/modelDetails'
import './ModelDetailsPanel.css'

const modality: Record<string, string> = { text: 'Text', image: 'Images', audio: 'Audio', video: 'Video', file: 'Files' }
const date = (iso: string) => new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })

const Check = ({ on }: { on: boolean }) => <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
  {on ? <><circle cx="8" cy="8" r="7" fill="currentColor" opacity=".14" /><path d="m5 8.2 2 2 4-4.4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></>
    : <circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" strokeWidth="1.2" strokeDasharray="2 2.4" />}
</svg>

/** A spec sheet for the selected model: what it is, how much it holds, what it reads and can do. */
export default function ModelDetailsPanel({ model }: { model: ModelDetails }) {
  const [more, setMore] = useState(false)
  if (!model.listed) return <p className="mdp mdp-note">No further details are published for this model yet.</p>

  const abilities = [
    { label: 'Tool use', hint: 'Calls tools and APIs', on: model.supports_tools },
    { label: 'Reasoning', hint: 'Thinks before answering', on: model.supports_reasoning },
    { label: 'Structured output', hint: 'Returns valid JSON', on: model.supports_structured_output },
    { label: 'Adjustable creativity', hint: 'Responds to temperature', on: model.supports_temperature },
  ]
  const meta = [model.released_at && `Released ${date(model.released_at)}`, model.knowledge_cutoff && `Knowledge to ${date(model.knowledge_cutoff)}`].filter(Boolean)
  const long = (model.description?.length ?? 0) > 170

  return (
    <article className="mdp" aria-label={`${model.name} details`}>
      <header className="mdp-head">
        <h3>{model.name}</h3>
        <span>{model.provider_label}</span>
      </header>

      {model.retires_at && <p className="mdp-warning" role="note">Scheduled to retire on {date(model.retires_at)}. Pick another model before then.</p>}
      {model.description && <p className={`mdp-description${more ? ' is-open' : ''}`}>{model.description}</p>}
      {long && <button type="button" className="mdp-more" onClick={() => setMore(!more)} aria-expanded={more}>{more ? 'Show less' : 'Show more'}</button>}

      <div className="mdp-stats">
        {model.context_length && <div><strong>{tokens(model.context_length)}</strong><span>Context window</span></div>}
        {model.max_output_tokens && <div><strong>{tokens(model.max_output_tokens)}</strong><span>Max output</span></div>}
        <div><strong>{model.input_modalities.length}</strong><span>Input {model.input_modalities.length === 1 ? 'type' : 'types'}</span></div>
      </div>

      <section className="mdp-section" aria-label="What it reads">
        <h4>Reads</h4>
        <ul className="mdp-chips">{model.input_modalities.map((m) => <li key={m}>{modality[m] ?? m}</li>)}</ul>
      </section>

      <section className="mdp-section" aria-label="What it can do">
        <h4>Can do</h4>
        <ul className="mdp-abilities">{abilities.map((a) => <li key={a.label} data-off={!a.on || undefined}>
          <Check on={a.on} /><span><b>{a.label}</b><small>{a.hint}</small></span>
          {!a.on && <span className="sr-only">Not supported</span>}
        </li>)}</ul>
      </section>

      {!model.supports_tools && <p className="mdp-warning" role="note">This model can’t call tools, which investigation agents may rely on.</p>}
      {meta.length > 0 && <p className="mdp-meta">{meta.join(' · ')}</p>}
    </article>
  )
}
