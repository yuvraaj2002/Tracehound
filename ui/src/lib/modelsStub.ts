/**
 * Stub data for the AI models page, until the model-settings API exists.
 *
 * Shapes mirror what the page expects from a future `GET /v1/agent-models` (the catalog of
 * providers plus each agent's choice) and `PUT /v1/agent-models/{agent}`. To switch to the real
 * API, replace the two functions at the bottom with `apiFetch` calls.
 */

export type AgentId = 'triage' | 'logs' | 'metrics' | 'dependency' | 'deploy' | 'hypothesis'

export type ModelOption = { id: string, label: string, context_tokens: number, note: string }

export type Provider = {
  id: string
  label: string
  /** Where the model runs, shown under the provider name. */
  hosting: string
  /** False until the user adds an API key for this provider (bring-your-own-key). */
  connected: boolean
  models: ModelOption[]
}

/**
 * How freely the agent reasons. Not every model takes a temperature (Claude 5 models don't), so
 * the backend maps this level to whatever the chosen model supports: a temperature for Ollama,
 * and the model's own defaults or reasoning settings elsewhere.
 */
export type Creativity = 'precise' | 'balanced' | 'creative'

export type AgentModelConfig = { provider: string, model: string, creativity: Creativity }

export type AgentModels = { providers: Provider[], defaults: AgentModelConfig, agents: Record<AgentId, AgentModelConfig> }

const providers: Provider[] = [
  {
    id: 'ollama', label: 'Ollama', hosting: 'Self-hosted, runs on your server', connected: true,
    models: [
      { id: 'LiquidAI/lfm2.5-1.2b-instruct', label: 'LFM 2.5 1.2B Instruct', context_tokens: 16384, note: 'Small and fast. The current default.' },
      { id: 'qwen3:8b', label: 'Qwen3 8B', context_tokens: 32768, note: 'Stronger reasoning, needs a GPU.' },
      { id: 'llama3.1:8b', label: 'Llama 3.1 8B', context_tokens: 131072, note: 'Long context for large log windows.' },
    ],
  },
  {
    id: 'anthropic', label: 'Anthropic', hosting: 'Hosted API, your key', connected: true,
    models: [
      { id: 'claude-opus-5-5', label: 'Claude Opus 5.5', context_tokens: 200000, note: 'Most capable. Best for weighing hypotheses.' },
      { id: 'claude-sonnet-5-5', label: 'Claude Sonnet 5.5', context_tokens: 200000, note: 'Balanced speed and depth.' },
      { id: 'claude-haiku-5-5', label: 'Claude Haiku 5.5', context_tokens: 200000, note: 'Fastest and cheapest.' },
    ],
  },
  { id: 'openai', label: 'OpenAI', hosting: 'Hosted API, your key', connected: false, models: [] },
  { id: 'google', label: 'Google Gemini', hosting: 'Hosted API, your key', connected: false, models: [] },
]

const defaults: AgentModelConfig = { provider: 'ollama', model: 'LiquidAI/lfm2.5-1.2b-instruct', creativity: 'precise' }

let saved: Record<AgentId, AgentModelConfig> = {
  triage: { ...defaults },
  logs: { ...defaults },
  metrics: { ...defaults },
  dependency: { ...defaults },
  deploy: { ...defaults },
  hypothesis: { provider: 'anthropic', model: 'claude-sonnet-5-5', creativity: 'balanced' },
}

const delay = <T,>(value: T, ms = 350) => new Promise<T>((resolve) => setTimeout(() => resolve(value), ms))

export const getAgentModels = (): Promise<AgentModels> =>
  delay({ providers, defaults, agents: structuredClone(saved) })

/** Kept in memory only: a reload brings back the stub's starting choices. */
export const saveAgentModel = (agent: AgentId, config: AgentModelConfig): Promise<AgentModelConfig> => {
  saved = { ...saved, [agent]: { ...config } }
  return delay({ ...config }, 500)
}
