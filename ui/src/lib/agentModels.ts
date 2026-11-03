/** The agent configuration page's data: the catalog of models and each agent's choice, from the Tracehound API. */

import { apiFetch } from './api'
import type { ModelDetails } from './modelDetails'
import { modelName } from './providers'

export type AgentId = 'triage' | 'logs' | 'metrics' | 'dependency' | 'deploy' | 'hypothesis'

export type ModelOption = { id: string, label: string, details: ModelDetails }

export type Provider = { id: string, label: string, models: ModelOption[] }

export type AgentModelConfig = { provider: string, model: string }

export type AgentModels = {
  providers: Provider[]
  /** What each agent runs on: the user's choice, or the default if they have not chosen. */
  agents: Record<AgentId, AgentModelConfig>
  defaults: Record<AgentId, AgentModelConfig>
  /** Agents the user has saved a choice for. */
  customized: AgentId[]
  /** False until a choice is saved for at least one agent; investigations cannot start before that. */
  configured: boolean
}

type ApiCatalog = { providers: { id: string, label: string, models: ModelDetails[] }[] }
export type ApiPreferences = { agents: Record<AgentId, AgentModelConfig>, defaults: Record<AgentId, AgentModelConfig>, customized: AgentId[], configured: boolean, message: string | null }

const toProviders = (api: ApiCatalog): Provider[] => api.providers.map((provider) => ({
  id: provider.id, label: provider.label,
  // A model offered with and without a `:free` suffix is listed once, under its first id.
  models: provider.models.filter((m, i, all) => all.findIndex((other) => modelName(other.id) === modelName(m.id)) === i)
    .map((details) => ({ id: details.id, label: details.listed ? details.name : modelName(details.id), details })),
}))

export const getAgentModels = async (): Promise<AgentModels> => {
  const [catalog, preferences] = await Promise.all([
    apiFetch<ApiCatalog>('/v1/agent-models/catalog'),
    apiFetch<ApiPreferences>('/v1/agent-models/preferences'),
  ])
  return { providers: toProviders(catalog), agents: preferences.agents, defaults: preferences.defaults, customized: preferences.customized, configured: preferences.configured }
}

/** Saves one agent's choice and returns everyone's, so the page stays in step with the server. */
export const saveAgentModel = (agent: AgentId, config: AgentModelConfig) =>
  apiFetch<ApiPreferences>(`/v1/agent-models/preferences/${agent}`, { method: 'PUT', body: JSON.stringify(config) })

/** Just the user's settings, for screens that only need to know whether models are configured. */
export const getModelPreferences = () => apiFetch<ApiPreferences>('/v1/agent-models/preferences')
