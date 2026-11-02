/** Model providers shown on the landing page. Logos are Simple Icons (CC0), tinted with CSS. */
export const modelProviders = [
  { id: 'ollama', name: 'Ollama', logo: '/providers/ollama.svg', hosting: 'Runs on your own servers', available: true },
  { id: 'anthropic', name: 'Anthropic', logo: '/providers/anthropic.svg', hosting: 'Claude, with your API key', available: false },
  { id: 'openai', name: 'OpenAI', logo: '/providers/openai.svg', hosting: 'GPT models, with your API key', available: false },
  { id: 'google', name: 'Google Gemini', logo: '/providers/googlegemini.svg', hosting: 'Gemini, with your API key', available: false },
] as const

export type ModelProvider = (typeof modelProviders)[number]

/** An example mix for the landing page's lineup: each specialist on a model that suits its job. */
export const exampleLineup = [
  { agent: 'Marshal', specialty: 'Triage', color: 'var(--agent-triage)', provider: 'anthropic', model: 'Claude Sonnet' },
  { agent: 'Echo', specialty: 'Logs', color: 'var(--agent-logs)', provider: 'ollama', model: 'Llama 3.1 8B' },
  { agent: 'Pulse', specialty: 'Metrics', color: 'var(--agent-metrics)', provider: 'ollama', model: 'Qwen3 8B' },
  { agent: 'Tether', specialty: 'Dependency', color: 'var(--agent-dependency)', provider: 'google', model: 'Gemini' },
  { agent: 'Ledger', specialty: 'Deploy', color: 'var(--agent-deploy)', provider: 'openai', model: 'GPT' },
  { agent: 'Sage', specialty: 'Hypothesis', color: 'var(--agent-hypothesis)', provider: 'anthropic', model: 'Claude Opus' },
] as const

export const providerLogo = (id: string) => modelProviders.find((p) => p.id === id)!.logo
