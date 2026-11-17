import { useState, type MouseEvent } from 'react'
import { useNavigate } from 'react-router'
import { ApiError, getMe } from '../lib/api'
import { useAuth } from './context'

/** "Get started" for links into /app: confirms the session with GET /v1/me before entering.
 *  A browser session can outlive its token on the server (revoked, user deleted), so a local
 *  session alone isn't trusted here. */
export function useGetStarted() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const [checking, setChecking] = useState(false)

  const start = async (event: MouseEvent<HTMLAnchorElement>) => {
    // Let new-tab clicks through; RequireAuth still guards the page they open.
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return
    event.preventDefault()
    if (!session) { navigate('/signin', { state: { from: '/app' } }); return }
    setChecking(true)
    try {
      await getMe()
      navigate('/app')
    } catch (err) {
      // 401: apiFetch has already cleared the local session. Any other failure (API down)
      // isn't proof the user is signed out, so let them in; the app pages report the error.
      navigate(err instanceof ApiError && err.status === 401 ? '/signin' : '/app', { state: { from: '/app' } })
    } finally {
      setChecking(false)
    }
  }

  return { to: session ? '/app' : '/signin', start, checking }
}
