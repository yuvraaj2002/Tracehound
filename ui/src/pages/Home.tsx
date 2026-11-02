import type { CSSProperties } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../auth/context'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'

const cards = [
  { to: '/app/docs', eyebrow: 'Developers', title: 'API reference', description: 'Trigger an investigation from your alerting tool with one POST request. Copy-ready examples in cURL, Python and JavaScript.', action: 'Read the docs' },
  { to: '/app/integrations', eyebrow: 'Data sources', title: 'Integrations & catalog', description: 'Connect the telemetry your services already report to, and upload your Backstage catalog so triage knows which services call which.', action: 'Manage data sources' },
  { to: '/app/models', eyebrow: 'Agents', title: 'AI models', description: 'Choose the model behind each investigator, from a small local model to a hosted one, and tune how it reasons.', action: 'Configure models' },
  { to: '/app/api-keys', eyebrow: 'Access', title: 'API keys', description: 'Create keys for scripts and alerting tools that open cases on your behalf, and revoke the ones you no longer use.', action: 'Manage keys' },
  { to: '/app/incidents', eyebrow: 'Runs', title: 'Dashboard', description: 'Every investigation your tools have opened, with its service, severity, window and current state.', action: 'Open the dashboard' },
  { to: '/app/billing', eyebrow: 'Account', title: 'Billing & subscription', description: 'Your current plan, the credits left this period, days until renewal, and every payment and invoice.', action: 'View billing' },
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
          <p>Read the API, connect your telemetry, create a key, then watch the runs arrive.</p>
        </div>

        <ul className="home-cards">
          {cards.map((card, index) => <li key={card.to}>
            <Link className="home-card" to={card.to} style={{ '--card-color': 'var(--color-primary)' } as CSSProperties}>
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
