import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from './auth/context'

/** The header every signed-in page shares: the wordmark and the avatar menu. */
export default function SignedInHeader() {
  const { user, signOut } = useAuth()
  const meta = (user?.user_metadata ?? {}) as { avatar_url?: string, picture?: string, full_name?: string, name?: string, user_name?: string }
  const name = meta.full_name ?? meta.name ?? meta.user_name ?? user?.email ?? 'Signed in'
  const avatar = meta.avatar_url ?? meta.picture

  return (
    <header className="nav">
      <Link className="brand" to="/" aria-label="Tracehound home"><img className="brand-symbol" src="/tracehound-mark.svg" alt="" width="40" height="40" /><span>Tracehound</span></Link>
      <AccountMenu name={name} email={user?.email} avatar={avatar} onSignOut={() => void signOut()} />
    </header>
  )
}

function AccountMenu({ name, email, avatar, onSignOut }: { name: string, email?: string, avatar?: string, onSignOut: () => void }) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)

  // Close on a click outside the menu, or on Escape (returning focus to the avatar).
  useEffect(() => {
    if (!open) return
    const onPointer = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpen(false); trigger.current?.focus() } }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('pointerdown', onPointer); document.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <div className="account" ref={root}>
      <button ref={trigger} type="button" className="account-trigger" aria-haspopup="true" aria-expanded={open} aria-controls="account-menu" aria-label={`Account: ${name}`} title={email && email !== name ? `${name}\n${email}` : name} onClick={() => setOpen((value) => !value)}>
        {avatar ? <img className="account-avatar" src={avatar} alt="" width="36" height="36" referrerPolicy="no-referrer" /> : <span className="account-avatar" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>}
      </button>
      {open && <div id="account-menu" className="account-menu">
        <div className="account-name"><strong>{name}</strong>{email && email !== name && <span>{email}</span>}</div>
        <button type="button" className="button-quiet" onClick={onSignOut}>Sign out</button>
      </div>}
    </div>
  )
}
