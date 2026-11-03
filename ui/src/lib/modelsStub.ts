/**
 * Stub data for the AI models page, until the model-settings API exists.
 *
 * Shapes mirror what the page expects from a future `GET /v1/agent-models` (the catalog of
 * providers plus each agent's choice) and `PUT /v1/agent-models/{agent}`. To switch to the real
 * API, replace the two functions at the bottom with `apiFetch` calls.
 */

import { apiFetch } from './api'
import type { ModelDetails } from './modelDetails'
import { defaultChoice, modelName } from './providers'

export type AgentId = 'triage' | 'logs' | 'metrics' | 'dependency' | 'deploy' | 'hypothesis'

export type ModelOption = { id: string, label: string, details: ModelDetails }

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
 * How freely the agent reasons. Not every model takes a temperature, so
 * the backend maps this level to whatever the chosen model supports.
 */
export type Creativity = 'precise' | 'balanced' | 'creative'

export type AgentModelConfig = { provider: string, model: string, creativity: Creativity }

export type AgentModels = { providers: Provider[], defaults: AgentModelConfig, agents: Record<AgentId, AgentModelConfig> }

type ApiCatalog = { providers: { id: string, label: string, models: ModelDetails[] }[], default: { provider: string, model: string } }

const toProviders = (api: ApiCatalog): Provider[] => api.providers.map((provider) => ({
  id: provider.id, label: provider.label, hosting: '', connected: true,
  // A model offered with and without a `:free` suffix is listed once, under its first id.
  models: provider.models.filter((m, i, all) => all.findIndex((other) => modelName(other.id) === modelName(m.id)) === i)
    .map((details) => ({ id: details.id, label: details.listed ? details.name : modelName(details.id), details })),
}))

const defaults: AgentModelConfig = { ...defaultChoice, creativity: 'precise' } // matches the API's default

let saved: Record<AgentId, AgentModelConfig> = {
  triage: { ...defaults },
  logs: { ...defaults },
  metrics: { ...defaults },
  dependency: { ...defaults },
  deploy: { ...defaults },
  hypothesis: { ...defaults },
}

const delay = <T,>(value: T, ms = 350) => new Promise<T>((resolve) => setTimeout(() => resolve(value), ms))

/** The providers and models come from the API; each agent's saved choice is still a stub. */
export const getAgentModels = async (): Promise<AgentModels> => {
  const catalog = await apiFetch<ApiCatalog>('/v1/agent-models/catalog')
  return { providers: toProviders(catalog), defaults, agents: structuredClone(saved) }
}

/** Kept in memory only: a reload brings back the stub's starting choices. */
export const saveAgentModel = (agent: AgentId, config: AgentModelConfig): Promise<AgentModelConfig> => {
  saved = { ...saved, [agent]: { ...config } }
  return delay({ ...config }, 500)
}
