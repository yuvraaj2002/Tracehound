import { Link } from 'react-router'
import { useAuth } from './auth/context'
import { useGetStarted } from './auth/useGetStarted'
import './Footer.css'

const year = new Date().getFullYear()

const product = [
  { href: '#agents', label: 'Agents' },
  { href: '#how', label: 'How it works' },
  { href: '#integrations', label: 'Integrations' },
  { href: '#pricing', label: 'Pricing' },
]

/** Site footer for the landing page: brand, where to go next, and who built it. */
export default function Footer() {
  const { session } = useAuth()
  const getStarted = useGetStarted()

  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div className="site-footer-brand">
          <a className="brand" href="#" aria-label="Tracehound home"><img className="brand-symbol" src="/tracehound-mark.svg" alt="" width="32" height="32" /><span>Tracehound</span></a>
          <p>Six AI specialists turn scattered telemetry into likely causes, cited evidence, and clear next checks.</p>
        </div>

        <nav className="site-footer-column" aria-labelledby="footer-product">
          <h2 id="footer-product">Product</h2>
          <ul>{product.map((item) => <li key={item.href}><a href={item.href}>{item.label}</a></li>)}</ul>
        </nav>

        <nav className="site-footer-column" aria-labelledby="footer-developers">
          <h2 id="footer-developers">Developers</h2>
          <ul>
            <li><Link to={getStarted.to} onClick={getStarted.start}>{session ? 'Open your workspace' : 'Get started'}</Link></li>
            <li><Link to="/app/docs">API reference</Link></li>
          </ul>
        </nav>

        <nav className="site-footer-column" aria-labelledby="footer-connect">
          <h2 id="footer-connect">Connect</h2>
          <ul>
            <li><a href="https://www.linkedin.com/in/yuvraaj-singh/" target="_blank" rel="noopener noreferrer">Meet the developer <span aria-hidden="true">↗</span><span className="sr-only"> (opens in a new tab)</span></a></li>
          </ul>
        </nav>
      </div>

      <div className="site-footer-base">
        <p>© {year} Tracehound. Follow the evidence.</p>
        <a href="#">Back to top <span aria-hidden="true">↑</span></a>
      </div>
    </footer>
  )
}
