import type { CSSProperties } from 'react'
import { exampleLineup as lineup, modelProviders, providerLogo as logo } from './lib/providers'
import './ModelProviders.css'

const mask = (url: string) => ({ maskImage: `url(${url})`, WebkitMaskImage: `url(${url})` }) as CSSProperties

/** The landing-page case for configurable models: any provider, chosen per agent. */
export default function ModelProviders() {
  return (
    <section id="models" className="models" aria-labelledby="models-title">
      <div className="section-heading">
        <div><p className="eyebrow">Configurable models</p><h2 id="models-title">Bring your own model.<br />Per agent.</h2></div>
        <p>Every specialist runs on the model you pick. Keep everything on your servers with a local model, or give the hardest reasoning to a hosted one with your own key.</p>
      </div>

      <ul className="models-providers">
        {modelProviders.map((provider) => <li key={provider.id} className="models-provider">
          <span className="provider-logo provider-logo-large" style={mask(provider.logo)} aria-hidden="true" />
          <div>
            <h3>{provider.name}</h3>
            <p>{provider.hosting}</p>
          </div>
          <span className={`models-tag${provider.available ? ' is-live' : ''}`}>{provider.available ? 'Available now' : 'Coming soon'}</span>
        </li>)}
      </ul>

      <div className="models-lineup" aria-label="Example: a different model for each agent">
        <p className="models-lineup-title">One team, many models</p>
        <ol>
          {lineup.map((item) => <li key={item.agent} style={{ '--agent-color': item.color } as CSSProperties}>
            <span className="models-agent"><span className="agent-dot" aria-hidden="true" />{item.agent}<small>{item.specialty}</small></span>
            <span className="models-pick"><span className="provider-logo" style={mask(logo(item.provider))} aria-hidden="true" />{item.model}</span>
          </li>)}
        </ol>
      </div>

      <p className="supported-note">Logos are trademarks of their respective owners.</p>
    </section>
  )
}
