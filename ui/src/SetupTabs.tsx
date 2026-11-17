import { NavLink } from 'react-router'

/** Integrations and the service catalog are one area on Home; these tabs move between them. */
export default function SetupTabs() {
  return (
    <nav className="setup-tabs" aria-label="Integrations and catalog">
      <NavLink to="/app/integrations" end>Integrations</NavLink>
      <NavLink to="/app/catalog" end>Service catalog</NavLink>
    </nav>
  )
}
