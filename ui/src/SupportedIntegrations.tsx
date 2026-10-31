import type { CSSProperties } from 'react'
import './SupportedIntegrations.css'

const integrations = [
  { name: 'Grafana Loki', signal: 'Logs', logo: '/integrations/loki.svg', agent: 'Echo', color: 'var(--agent-logs)', description: 'Reads the log streams your services already ship, so Echo can cite the first errors and stack traces.' },
  { name: 'Prometheus', signal: 'Metrics', logo: '/integrations/prometheus.svg', agent: 'Pulse', color: 'var(--agent-metrics)', description: 'Compares latency, error rate and saturation against the baseline before the incident.' },
  { name: 'Grafana Tempo', signal: 'Traces', logo: '/integrations/tempo.svg', agent: 'Tether', color: 'var(--agent-dependency)', description: 'Follows slow and failing spans across service boundaries to find where trouble starts.' },
  { name: 'GitHub Deployments', signal: 'Deploys', logo: '/integrations/github.svg', agent: 'Ledger', color: 'var(--agent-deploy)', description: 'Lines up releases with the moment the incident began, so a recent change is never overlooked.' },
]

/** Copies of the list that make the belt loop seamlessly. Only the first is read by assistive tech. */
const COPIES = 3

/** The telemetry sources the specialists read, each owned by one agent, on a slow conveyor belt that never stops. */
export default function SupportedIntegrations() {
  return (
    <section id="integrations" className="supported" aria-labelledby="integrations-title">
      <div className="supported-inset">
        <div className="section-heading">
          <div><p className="eyebrow">Integrations</p><h2 id="integrations-title">Works with the tools<br />you already run.</h2></div>
          <p>Connect your own telemetry. Each source feeds one specialist, so every finding traces back to your real data.</p>
        </div>
      </div>

      <div className="supported-belt">
        <div className="supported-track">
          {Array.from({ length: COPIES }, (_, copy) => <ul key={copy} className="supported-set" aria-hidden={copy > 0 || undefined}>
            {integrations.map((item) => <li key={item.name} className="supported-card" style={{ '--source-color': item.color } as CSSProperties}>
              <img src={item.logo} alt="" width="44" height="40" />
              <p className="supported-signal"><span aria-hidden="true" /> {item.signal} · {item.agent}</p>
              <h3>{item.name}</h3>
              <p className="supported-description">{item.description}</p>
            </li>)}
          </ul>)}
        </div>
      </div>

      <div className="supported-inset supported-foot">
        <p className="supported-note">Logos are trademarks of their respective owners.</p>
      </div>
    </section>
  )
}
