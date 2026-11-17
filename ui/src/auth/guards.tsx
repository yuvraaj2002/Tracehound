import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { fromState, useAuth } from './context'

export function AuthLoading({ label = 'Restoring your session' }: { label?: string }) {
  return (
    <div className="auth-loading" role="status" aria-live="polite">
      <img className="brand-symbol" src="/tracehound-mark.svg" alt="" width="40" height="40" />
      <p>{label}<span className="status-dots" aria-hidden="true"><span /><span /><span /></span></p>
    </div>
  )
}

/** Signed-out visitors go to /signin, carrying the page they wanted. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()
  const location = useLocation()
  if (loading) return <AuthLoading />
  if (!session) return <Navigate to="/signin" replace state={{ from: location.pathname + location.search + location.hash }} />
  return children
}

/** Signed-in visitors skip the sign-in page. */
export function RedirectIfSignedIn({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()
  const location = useLocation()
  if (loading) return <AuthLoading />
  if (session) return <Navigate to={fromState(location.state)} replace />
  return children
}
