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

  const response = await fetch(`${base}${path}`, { ...init, headers })
  if (response.status === 401) {
    // The API rejected the token. Clearing the local session fires SIGNED_OUT,
    // and RequireAuth sends the user to /signin, remembering where they were.
    await supabase.auth.signOut({ scope: 'local' })
    throw new ApiError(401, 'Your session has expired. Please sign in again.')
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response))
  return response.json() as Promise<T>
}

async function errorMessage(response: Response) {
  try {
    const body = await response.json() as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    // FastAPI validation errors: [{ loc, msg }, ...]
    if (Array.isArray(body.detail)) return body.detail.map((item: { loc?: unknown[], msg?: string }) => `${item.loc?.at(-1) ?? 'request'}: ${item.msg}`).join('; ')
  } catch { /* not JSON */ }
  return `Request failed (${response.status})`
}

export const listIncidents = () => apiFetch<Incident[]>('/v1/incidents')

export const createIncident = (incident: IncidentCreate) => apiFetch<IncidentAccepted>('/v1/incidents', { method: 'POST', body: JSON.stringify(incident) })
