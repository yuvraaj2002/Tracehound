import { useEffect, useState, type CSSProperties } from 'react'
import { providerLogo } from './lib/providers'

/** One-word model names the hero cycles through. As many as agents, so all six always differ. */
const models = [
  { name: 'Claude', provider: 'anthropic' },
  { name: 'Llama', provider: 'ollama' },
  { name: 'Qwen', provider: 'ollama' },
  { name: 'Gemini', provider: 'google' },
  { name: 'GPT', provider: 'openai' },
  { name: 'DeepSeek', provider: 'ollama' },
]

/**
 * Where each label rises from (the middle of the character) and where it rests (just above the
 * head), as percentages of the hero image, left to right. Marshal's head touches the top edge,
 * so his label rests beside his hair instead (`side`).
 */
const souls = [
  { agent: 'Echo', color: 'var(--agent-logs)', from: [10.6, 65], to: [9.3, 31.3] },
  { agent: 'Pulse', color: 'var(--agent-metrics)', from: [26.4, 63], to: [25.6, 31.9] },
  { agent: 'Marshal', color: 'var(--agent-triage)', from: [47.6, 54], to: [56, 9], side: true },
  { agent: 'Tether', color: 'var(--agent-dependency)', from: [61.7, 66], to: [61.7, 32] },
  { agent: 'Sage', color: 'var(--agent-hypothesis)', from: [75.4, 65], to: [75.7, 31.2] },
  { agent: 'Ledger', color: 'var(--agent-deploy)', from: [90.8, 65], to: [91.7, 30.7] },
]

/** Matches the 3s rise-hold-fade animation plus the left-to-right stagger. */
const CYCLE_MS = 3600
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * Model names that rise out of each agent like a soul, rest above its head, then drift away as
 * the next one rises. Each agent shows a different model at any moment, to show that every
 * agent's model is configurable.
 */
export default function HeroModels() {
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (reducedMotion()) return
    const timer = setInterval(() => setTick((current) => current + 1), CYCLE_MS)
    return () => clearInterval(timer)
  }, [])

  return (
    <ul className="hero-souls" aria-label="Each agent runs on a model you choose, such as Claude, Llama, Qwen, Gemini, GPT or DeepSeek">
      {souls.map((soul, index) => {
        const model = models[(index + tick) % models.length]!
        const logo = providerLogo(model.provider)
        // A new key each cycle restarts the rise; the first cycle waits for the hero image to land.
        const delay = (tick === 0 ? 0.9 : 0) + index * 0.1
        return (
          <li key={`${soul.agent}-${tick}`} className="hero-soul" data-side={soul.side || undefined} aria-hidden="true"
            style={{
              '--from-x': `${soul.from[0]}%`, '--from-y': `${soul.from[1]}%`,
              '--to-x': `${soul.to[0]}%`, '--to-y': `${soul.to[1]}%`,
              '--agent-color': soul.color, '--delay': `${delay}s`,
            } as CSSProperties}>
            <span className="provider-logo" style={{ maskImage: `url(${logo})`, WebkitMaskImage: `url(${logo})` }} />
            {model.name}
          </li>
        )
      })}
    </ul>
  )
}
