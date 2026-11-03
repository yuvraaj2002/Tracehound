import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import ProviderMark from './ProviderMark'
import { describeModel, modelProviders } from './lib/providers'
import './ModelProviders.css'

const AUTO_MS = 1500

/** The landing-page case for configurable models: a tour of the providers and the models each offers. */
export default function ModelProviders() {
  const [active, setActive] = useState(0)
  const tabs = useRef<(HTMLButtonElement | null)[]>([])
  const provider = modelProviders[active]!

  // Keep touring the providers, restarting the countdown on every click.
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const timer = setTimeout(() => setActive((current) => (current + 1) % modelProviders.length), AUTO_MS)
    return () => clearTimeout(timer)
  }, [active])

  const choose = (index: number) => setActive(index)
  const onKey = (event: KeyboardEvent) => {
    const step = event.key === 'ArrowDown' || event.key === 'ArrowRight' ? 1 : event.key === 'ArrowUp' || event.key === 'ArrowLeft' ? -1 : 0
    if (!step) return
    event.preventDefault()
    const next = (active + step + modelProviders.length) % modelProviders.length
    choose(next)
    tabs.current[next]?.focus()
  }

  return (
    <section id="models" className="models" aria-labelledby="models-title">
      <div className="section-heading">
        <div><p className="eyebrow">Configurable models</p><h2 id="models-title">A model for each agent.</h2></div>
        <p>Every specialist runs on the model you pick, from a curated set of providers and models.</p>
      </div>

      <div className="models-explorer">
        <div className="models-rail" role="tablist" aria-label="Model providers" aria-orientation="vertical" onKeyDown={onKey}>
          {modelProviders.map((item, index) => <button key={item.id} ref={(node) => { tabs.current[index] = node }} type="button" role="tab" id={`provider-tab-${item.id}`}
            aria-selected={index === active} aria-controls="provider-panel" tabIndex={index === active ? 0 : -1} className="models-tab" onClick={() => choose(index)}>
            <ProviderMark id={item.id} />
            <span className="models-tab-name">{item.name}</span>
            <span className="models-tab-count">{item.models.length}</span>
            {index === active && <span className="models-tab-timer" key={`${active}-timer`} aria-hidden="true" />}
          </button>)}
        </div>

        <div id="provider-panel" className="models-stage" role="tabpanel" aria-labelledby={`provider-tab-${provider.id}`} key={provider.id}>
          <header className="models-stage-head">
            <ProviderMark id={provider.id} large />
            <div><h3>{provider.name}</h3><p>{provider.models.length} {provider.models.length === 1 ? 'model' : 'models'} available</p></div>
          </header>
          <ul className="models-cards">
            {provider.models.map((key, index) => {
              const model = describeModel(key)
              return <li key={key} style={{ '--i': index } as CSSProperties}>
                <div className="model-chip">
                  <strong>{model.name}</strong>
                  <span className="model-tags">{model.tags.map((tag) => <span key={tag}>{tag}</span>)}</span>
                </div>
              </li>
            })}
          </ul>
        </div>
      </div>

      <p className="supported-note">Logos are trademarks of their respective owners.</p>
    </section>
  )
}
