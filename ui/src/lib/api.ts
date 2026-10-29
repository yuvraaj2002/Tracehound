import { supabase } from './supabase'

export type Severity = 'low' | 'medium' | 'high' | 'critical'

export type Incident = {
  id: string
  run_id: string
  service_id: string
  symptom: string
  severity: Severity
  window_start: string
  window_end: string
  trace_id: string | null
  state: string
  created_at: string
  updated_at: string
}

export type IncidentCreate = {
  service_id: string
  symptom: string
  /** ISO-8601 with a timezone, e.g. 2026-10-17T14:00:00Z. */
  window_start: string
  window_end: string
  severity: Severity
  trace_id?: string
}

export type IncidentAccepted = { incident_id: string, run_id: string, status_url: string }

export type ApiKeySummary = {
  id: string
  name: string
  prefix: string
  suffix: string
  created_at: string
  last_used_at: string | null
}

/** Pass `next_cursor` back as `cursor` for the next page; null on the last page. */
export type ApiKeyPage = { items: ApiKeySummary[], next_cursor: string | null }

/** `key` is the raw secret. The API returns it once, here, and never again. */
export type ApiKeyCreated = Omit<ApiKeySummary, 'last_used_at'> & { key: string }

export type IntegrationKind = 'loki'
export type IntegrationStatus = 'untested' | 'active' | 'failing'
export type IntegrationAuth =
  | { type: 'none' }
  | { type: 'basic', username: string, password: string }
  | { type: 'bearer', token: string }

/** Non-secret Loki settings. `org_id` is sent as X-Scope-OrgID to multi-tenant Loki. */
export type LokiConfig = { url: string, service_label?: string, org_id?: string | null }

export type IntegrationCreate = { kind: IntegrationKind, config: LokiConfig, auth: IntegrationAuth }

/** Omitted fields keep their value; `org_id: null` clears it. Without `auth` the stored
 *  credential is kept; with it, the whole credential is replaced. */
export type IntegrationUpdate = { config?: Partial<LokiConfig>, auth?: IntegrationAuth }

/** The credential is never returned; `has_secret` says whether one is stored. */
export type IntegrationSummary = {
  id: string
  kind: IntegrationKind
  config: Required<LokiConfig> & { auth_type: IntegrationAuth['type'], username?: string }
  has_secret: boolean
  status: IntegrationStatus
  last_tested_at: string | null
  created_at: string
}

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Calls the Tracehound API with the current Supabase access token.
 *  getSession() refreshes an expiring token first, so each request carries a valid one. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const base = import.meta.env.VITE_API_URL?.replace(/\/+$/, '')
  if (!base) throw new Error('Missing VITE_API_URL in ui/.env.local (see ui/.env.example).')
  const { data } = await supabase.auth.getSession()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body !== undefined) headers.set('Content-Type', 'application/json')
  if (data.session) headers.set('Authorization', `Bearer ${data.session.access_token}`)

  let response: Response
  try {
    response = await fetch(`${base}${path}`, { ...init, headers })
  } catch (err) {
    // fetch rejects with a TypeError when the request never reaches the server
    // ("Failed to fetch" / "Load failed"): API down, wrong URL or CORS.
    if (err instanceof TypeError) throw new ApiError(0, 'Can’t reach the Tracehound API. Check that the backend is running.')
    throw err
  }
  if (response.status === 401) {
    // The API rejected the token. Clearing the local session fires SIGNED_OUT,
    // and RequireAuth sends the user to /signin, remembering where they were.
    await supabase.auth.signOut({ scope: 'local' })
    throw new ApiError(401, 'Your session has expired. Please sign in again.')
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response))
  // 204 No Content (e.g. a revoke) has no body to parse.
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function errorMessage(response: Response) {
  try {
    const body = await response.json() as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    // FastAPI validation errors: [{ loc, msg }, ...]
    if (Array.isArray(body.detail)) return body.detail.map((item: { loc?: unknown[], msg?: string }) => `${item.loc?.at(-1) ?? 'request'}: ${item.msg?.replace(/^Value error, /, '')}`).join('; ')
  } catch { /* not JSON */ }
  return `Request failed (${response.status})`
}

export const listIncidents = () => apiFetch<Incident[]>('/v1/incidents')

export const createIncident = (incident: IncidentCreate) => apiFetch<IncidentAccepted>('/v1/incidents', { method: 'POST', body: JSON.stringify(incident) })

export const listApiKeys = (cursor?: string | null) => apiFetch<ApiKeyPage>(`/v1/api-keys${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`)

export const createApiKey = (name: string) => apiFetch<ApiKeyCreated>('/v1/api-keys', { method: 'POST', body: JSON.stringify({ name }) })

export const revokeApiKey = (id: string) => apiFetch<void>(`/v1/api-keys/${encodeURIComponent(id)}`, { method: 'DELETE' })

export const listIntegrations = () => apiFetch<{ items: IntegrationSummary[] }>('/v1/integrations')

export const createIntegration = (integration: IntegrationCreate) => apiFetch<IntegrationSummary>('/v1/integrations', { method: 'POST', body: JSON.stringify(integration) })

export const deleteIntegration = (id: string) => apiFetch<void>(`/v1/integrations/${encodeURIComponent(id)}`, { method: 'DELETE' })

export const updateIntegration = (id: string, changes: IntegrationUpdate) => apiFetch<IntegrationSummary>(`/v1/integrations/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(changes) })
