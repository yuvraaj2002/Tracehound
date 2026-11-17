import { createContext, useContext } from 'react'
import type { Session, User } from '@supabase/supabase-js'

export type Provider = 'google' | 'github'

export type AuthState = {
  session: Session | null
  user: User | null
  /** True until the stored session has been restored on first load. */
  loading: boolean
  signInWith: (provider: Provider) => Promise<void>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth() {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside <AuthProvider>')
  return auth
}

// The OAuth round trip leaves the app, so the page a visitor was heading to
// survives in sessionStorage rather than router state.
const nextKey = 'tracehound:next'

export function rememberNext(path: string) {
  try { sessionStorage.setItem(nextKey, path) } catch { /* storage blocked: fall back to /app */ }
}

export function takeNext() {
  let path: string | null = null
  try {
    path = sessionStorage.getItem(nextKey)
    sessionStorage.removeItem(nextKey)
  } catch { /* storage blocked */ }
  // Only same-origin app paths; never '//host' or the auth pages themselves.
  return path && path.startsWith('/') && !path.startsWith('//') && !path.startsWith('/signin') && !path.startsWith('/auth/') ? path : '/app'
}

/** The page RequireAuth stored in router state, if it is a safe in-app path. */
export function fromState(state: unknown) {
  const from = (state as { from?: unknown } | null)?.from
  return typeof from === 'string' && from.startsWith('/') && !from.startsWith('//') ? from : '/app'
}
