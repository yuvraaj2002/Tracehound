import { tokens, type ModelDetails } from './lib/modelDetails'
import './ModelDetailsPanel.css'

const date = (iso: string) => new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })

/** What someone choosing a model needs: what it is, how much it can take in, and how much it can answer. */
export default function ModelDetailsPanel({ model }: { model: ModelDetails }) {
  if (!model.listed) return <p className="mdp mdp-note">No further details are published for this model yet.</p>

  return (
    <article className="mdp" aria-label={`${model.name} details`}>
      <header className="mdp-head">
        <h3>{model.name}</h3>
        <span>{model.provider_label}</span>
      </header>

      {model.retires_at && <p className="mdp-warning" role="note">Scheduled to retire on {date(model.retires_at)}. Pick another model before then.</p>}
      {model.description && <p className="mdp-description">{model.description}</p>}

      {(model.context_length || model.max_output_tokens) && <div className="mdp-stats">
        {model.context_length && <div><strong>{tokens(model.context_length)}</strong><span>Context window</span></div>}
        {model.max_output_tokens && <div><strong>{tokens(model.max_output_tokens)}</strong><span>Max output</span></div>}
      </div>}

      {!model.supports_tools && <p className="mdp-warning" role="note">This model can’t call tools, which investigation agents may rely on.</p>}
      {model.released_at && <p className="mdp-meta">Released {date(model.released_at)}</p>}
    </article>
  )
}
