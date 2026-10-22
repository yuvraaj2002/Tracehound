import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { supabase } from '../lib/supabase'
import { takeNext, useAuth } from '../auth/context'
import { AuthLoading } from '../auth/guards'
import '../auth.css'

// A code is single-use. StrictMode runs effects twice in development, so share
// one exchange per code instead of spending it twice.
const exchanges = new Map<string, Promise<string | null>>()
const exchange = (code: string) => {
  if (!exchanges.has(code)) exchanges.set(code, supabase.auth.exchangeCodeForSession(code).then(({ error }) => error?.message ?? null))
  return exchanges.get(code)!
}

/** Finishes the OAuth redirect: the provider error, or ?code= traded for a session. */
export default function AuthCallback() {
  const { session, loading } = useAuth()
  const navigate = useNavigate()
  const [params] = useState(() => new URLSearchParams(location.search))
  const [error, setError] = useState<string | null>(() => params.get('error_description') ?? params.get('error'))
  const code = params.get('code')

  useEffect(() => {
    if (!code || error) return
    let active = true
    exchange(code).then((message) => { if (active && message) setError(message) })
    return () => { active = false }
  }, [code, error])

  // Navigate once the session has reached the auth context, so /app never sees a stale signed-out state.
  useEffect(() => {
    if (error || loading) return
    if (session) navigate(takeNext(), { replace: true })
    else if (!code) navigate('/signin', { replace: true })
  }, [session, loading, code, error, navigate])

  if (!error) return <AuthLoading label="Signing you in" />
  return (
    <div className="auth-page">
      <main className="signin signin-error">
        <div className="signin-copy">
          <p className="eyebrow"><span /> Sign-in failed</p>
          <h1>We couldn’t sign you in.</h1>
          <p className="form-error" role="alert">{error}</p>
          <Link className="text-link" to="/signin" replace>Try again <span aria-hidden="true">→</span></Link>
        </div>
      </main>
    </div>
  )
}
