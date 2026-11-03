import type { CSSProperties } from 'react'
import ProviderMark from './ProviderMark'
import { exampleLineup as lineup, modelProviders } from './lib/providers'
import './ModelProviders.css'

/** The landing-page case for configurable models: any provider, chosen per agent. */
export default function ModelProviders() {
  return (
    <section id="models" className="models" aria-labelledby="models-title">
      <div className="section-heading">
        <div><p className="eyebrow">Configurable models</p><h2 id="models-title">A model for each agent.</h2></div>
        <p>Every specialist runs on the model you pick, from a curated set of models served through OpenRouter.</p>
      </div>

      <ul className="models-providers">
        {modelProviders.map((provider) => <li key={provider.id} className="models-provider">
          <ProviderMark id={provider.id} large />
          <div>
            <h3>{provider.name}</h3>
            <p>{provider.hosting}</p>
          </div>
          <span className="models-tag is-live">{provider.models.length} {provider.models.length === 1 ? 'model' : 'models'}</span>
        </li>)}
      </ul>

      <div className="models-lineup" aria-label="Example: a different model for each agent">
        <p className="models-lineup-title">One team, many models</p>
        <ol>
          {lineup.map((item) => <li key={item.agent} style={{ '--agent-color': item.color } as CSSProperties}>
            <span className="models-agent"><span className="agent-dot" aria-hidden="true" />{item.agent}<small>{item.specialty}</small></span>
            <span className="models-pick"><ProviderMark id={item.provider} />{item.model}</span>
          </li>)}
        </ol>
      </div>

      <p className="supported-note">Logos are trademarks of their respective owners.</p>
    </section>
  )
}
