import { useState, type ReactElement } from 'react'
import { Link, useLocation } from 'react-router'
import { fromState, rememberNext, useAuth, type Provider } from '../auth/context'
import '../auth.css'

const providers: { id: Provider, label: string, logo: ReactElement }[] = [
  {
    id: 'google',
    label: 'Continue with Google',
    logo: <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="#4285F4" d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.46a5.52 5.52 0 0 1-2.4 3.62v3h3.88c2.27-2.09 3.58-5.17 3.58-8.81Z" /><path fill="#34A853" d="M12 24c3.24 0 5.96-1.07 7.94-2.9l-3.88-3.02c-1.07.72-2.45 1.15-4.06 1.15-3.12 0-5.77-2.11-6.71-4.95H1.28v3.11A12 12 0 0 0 12 24Z" /><path fill="#FBBC05" d="M5.29 14.28A7.2 7.2 0 0 1 4.91 12c0-.79.14-1.56.38-2.28V6.61H1.28a12 12 0 0 0 0 10.78l4.01-3.11Z" /><path fill="#EA4335" d="M12 4.77c1.76 0 3.34.6 4.58 1.8l3.44-3.44A11.5 11.5 0 0 0 12 0 12 12 0 0 0 1.28 6.61l4.01 3.11C6.23 6.88 8.88 4.77 12 4.77Z" /></svg>,
  },
  {
    id: 'github',
    label: 'Continue with GitHub',
    logo: <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M12 .3a12 12 0 0 0-3.8 23.38c.6.12.83-.26.83-.57L9 21.07c-3.34.72-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.08-.74.09-.73.09-.73 1.2.09 1.83 1.24 1.83 1.24 1.07 1.83 2.81 1.3 3.5 1 .1-.78.42-1.31.76-1.61-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.14-.3-.54-1.52.1-3.18 0 0 1-.32 3.3 1.23a11.5 11.5 0 0 1 6 0c2.28-1.55 3.29-1.23 3.29-1.23.64 1.66.24 2.88.12 3.18a4.65 4.65 0 0 1 1.23 3.22c0 4.61-2.8 5.63-5.48 5.92.42.36.81 1.1.81 2.22l-.01 3.29c0 .31.21.69.82.57A12 12 0 0 0 12 .3Z" /></svg>,
  },
]

export default function SignIn() {
  const { signInWith } = useAuth()
  const location = useLocation()
  const [pending, setPending] = useState<Provider | null>(null)
  const [error, setError] = useState<string | null>(null)

  const start = async (provider: Provider) => {
    setPending(provider)
    setError(null)
    rememberNext(fromState(location.state))
    try {
      // On success the browser leaves for the provider, so pending stays set.
      await signInWith(provider)
    } catch (err) {
      setPending(null)
      setError(err instanceof Error ? err.message : 'Could not start sign-in.')
    }
  }

  return (
    <div className="auth-page">
      <header className="nav">
        <Link className="brand" to="/" aria-label="Tracehound home"><img className="brand-symbol" src="/tracehound-mark.svg" alt="" width="40" height="40" /><span>Tracehound</span></Link>
        <nav aria-label="Main navigation"><Link to="/">Back to home</Link></nav>
      </header>

      <main className="signin">
        <div className="signin-copy">
          <p className="eyebrow"><span /> Sign in</p>
          <h1>Open your first case.<br /><span>The team is standing by.</span></h1>
          <p>Sign in to hand an incident to Marshal and the specialists, and follow the evidence as it comes back.</p>
        </div>

        <div className="signin-panel">
          <p className="signin-label">CONTINUE WITH</p>
          <div className="signin-providers">
            {providers.map((provider) => <button key={provider.id} type="button" className="provider-button" onClick={() => start(provider.id)} disabled={pending !== null} aria-busy={pending === provider.id}>
              {provider.logo}<span>{pending === provider.id ? 'Redirecting…' : provider.label}</span>
            </button>)}
          </div>
          {error && <p className="form-error" role="alert">{error}</p>}
          <p className="signin-note">We only use your name, email and avatar to identify you in Tracehound.</p>
        </div>
      </main>
    </div>
  )
}
