import config from '../../../src/tracehound/resources/config.json'

/** The backend's model config (src/tracehound/resources/config.json) is the single source of truth. */
export type ConfigProvider = { id: string, label: string, models: string[] }

/** Logos are Simple Icons (CC0), tinted with CSS. Providers without one show a monogram. */
const logos: Record<string, string> = { nvidia: '/providers/nvidia.svg', google: '/providers/google.svg' }

export const gateway = config.gateway
export const defaultChoice = config.default
export const configProviders: ConfigProvider[] = config.providers

/** A model id without its provider prefix and `:free` suffix, e.g. "nemotron-3.5-lightning". */
export const modelName = (id: string) => id.split('/').slice(1).join('/').replace(/:free$/, '')

export const modelProviders = configProviders.map((provider) => ({
  id: provider.id,
  name: provider.label,
  logo: logos[provider.id] ?? null,
  /** Distinct display names: a model offered with and without a `:free` suffix is shown once. */
  models: [...new Set(provider.models.map(modelName))],
  hosting: provider.models.map(modelName).filter((name, i, all) => all.indexOf(name) === i).join(' · '),
}))

export type ModelProvider = (typeof modelProviders)[number]

/** An example mix for the landing page's lineup, using models from the config. */
export const exampleLineup = [
  { agent: 'Marshal', specialty: 'Triage', color: 'var(--agent-triage)', provider: 'nvidia', model: 'Nemotron 3 Ultra 550B' },
  { agent: 'Echo', specialty: 'Logs', color: 'var(--agent-logs)', provider: 'liquid', model: 'LFM 2.5 2.6B' },
  { agent: 'Pulse', specialty: 'Metrics', color: 'var(--agent-metrics)', provider: 'nvidia', model: 'Nemotron 3.5 Lightning' },
  { agent: 'Tether', specialty: 'Dependency', color: 'var(--agent-dependency)', provider: 'google', model: 'Gemma 4 26B' },
  { agent: 'Ledger', specialty: 'Deploy', color: 'var(--agent-deploy)', provider: 'cohere', model: 'North Mini Code' },
  { agent: 'Sage', specialty: 'Hypothesis', color: 'var(--agent-hypothesis)', provider: 'thinkingmachines', model: 'Inkling' },
] as const

export const providerLogo = (id: string) => logos[id] ?? null
