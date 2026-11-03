import type { CSSProperties } from 'react'
import { modelProviders, providerLogo } from './lib/providers'

/** A provider's logo, or its first letter when it has none. */
export default function ProviderMark({ id, large }: { id: string, large?: boolean }) {
  const logo = providerLogo(id)
  const className = `provider-logo${large ? ' provider-logo-large' : ''}`
  if (logo) return <span className={className} style={{ maskImage: `url(${logo})`, WebkitMaskImage: `url(${logo})` } as CSSProperties} aria-hidden="true" />
  const name = modelProviders.find((p) => p.id === id)?.name ?? id
  return <span className={`${className} provider-monogram`} aria-hidden="true">{name[0]}</span>
}
