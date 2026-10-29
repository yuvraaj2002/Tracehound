import type { CSSProperties } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../auth/context'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'

const cards = [
  { to: '/app/incidents', eyebrow: 'Case board', title: 'Start an investigation', description: 'Describe the symptom and the window. Marshal and the specialists follow the evidence from there.', action: 'Open a case', color: 'var(--color-primary)' },
  { to: '/app/api-keys', eyebrow: 'Access', title: 'API keys', description: 'Create keys for scripts and alerting tools that open cases on your behalf, and revoke the ones you no longer use.', action: 'Manage keys', color: 'var(--color-secondary)' },
]

/** Where a signed-in user lands: one card per area of the product. */
export default function Home() {
  const { user } = useAuth()
  const meta = (user?.user_metadata ?? {}) as { full_name?: string, name?: string, user_name?: string }
  const firstName = (meta.full_name ?? meta.name ?? meta.user_name)?.split(' ')[0]

  return (
    <div className="auth-page">
      <SignedInHeader />

      <main className="workspace">
        <div className="workspace-heading">
          <div><p className="eyebrow"><span /> Home</p><h1>{firstName ? `Welcome, ${firstName}.` : 'Welcome.'}<br /><span>Where should we start?</span></h1></div>
          <p>Open a case, or set up access for your tools.</p>
        </div>

        <ul className="home-cards">
          {cards.map((card, index) => <li key={card.to}>
            <Link className="home-card" to={card.to} style={{ '--card-color': card.color } as CSSProperties}>
              <span className="home-card-index">0{index + 1}</span>
              <p className="eyebrow"><span /> {card.eyebrow}</p>
              <h2>{card.title}</h2>
              <p className="home-card-description">{card.description}</p>
              <span className="home-card-action">{card.action} <span aria-hidden="true">→</span></span>
            </Link>
          </li>)}
        </ul>
      </main>
    </div>
  )
}
