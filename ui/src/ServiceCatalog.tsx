import './ServiceCatalog.css'

const SNIPPET = `apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: checkout-api
spec:
  type: service
  owner: group:team-checkout
  dependsOn:
    - component:orders-api
    - component:payments-api
---
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: orders-db
  annotations:
    tracehound.dev/kind: postgres
spec:
  type: database
  owner: group:team-platform`

const points = [
  { title: 'Backstage format, as is', body: 'Upload the catalog-info.yaml you already keep. No new schema to learn or convert to.' },
  { title: 'See it before you save', body: 'Paste or write the file and watch the dependency graph build as you type. Save once it looks right.' },
  { title: 'Triage knows the blast radius', body: 'Dependencies and owners tell triage which neighbours to investigate and whose service it is.' },
]

// A small fixed map: node boxes are 124 x 40, laid out in four columns of callers to callees.
type MapNode = { id: string, kind: 'service' | 'resource', note: string, x: number, y: number }
const NODE_W = 124
const NODE_H = 40
const nodes: MapNode[] = [
  { id: 'checkout-web', kind: 'service', note: 'website', x: 0, y: 70 },
  { id: 'checkout-api', kind: 'service', note: 'service', x: 170, y: 70 },
  { id: 'orders-api', kind: 'service', note: 'service', x: 340, y: 20 },
  { id: 'payments-api', kind: 'service', note: 'service', x: 340, y: 120 },
  { id: 'orders-db', kind: 'resource', note: 'postgres', x: 510, y: 20 },
  { id: 'payments-db', kind: 'resource', note: 'postgres', x: 510, y: 120 },
]
const links: [string, string][] = [
  ['checkout-web', 'checkout-api'], ['checkout-api', 'orders-api'], ['checkout-api', 'payments-api'],
  ['orders-api', 'orders-db'], ['payments-api', 'payments-db'],
]
const at = (id: string) => nodes.find((node) => node.id === id) as MapNode
const wire = (from: string, to: string) => {
  const a = at(from), b = at(to)
  const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2, bend = (x2 - x1) / 2
  return `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`
}

/** The catalog-info.yaml a team uploads, and the dependency map Tracehound reads from it. */
export default function ServiceCatalog() {
  return (
    <section id="catalog" className="catalog-intro" aria-labelledby="catalog-intro-title">
      <div className="section-heading">
        <div><p className="eyebrow">Service catalog</p><h2 id="catalog-intro-title">Bring the map<br />you already keep.</h2></div>
        <p>Your Backstage catalog tells Tracehound which services call which, and who owns each one.</p>
      </div>

      <div className="catalog-intro-body">
        <figure className="catalog-intro-file">
          <figcaption><span aria-hidden="true" />catalog-info.yaml</figcaption>
          <pre><code>{SNIPPET}</code></pre>
        </figure>

        <figure className="catalog-intro-map" aria-label="checkout-web calls checkout-api, which calls orders-api and payments-api, each backed by a Postgres database">
          <figcaption>What triage reads</figcaption>
          <svg className="catalog-intro-graph" viewBox="0 0 634 180" aria-hidden="true">
            <defs><marker id="intro-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="currentColor" /></marker></defs>
            {links.map(([from, to]) => <path key={`${from}>${to}`} d={wire(from, to)} className="intro-wire" markerEnd="url(#intro-arrow)" />)}
            {nodes.map((node) => (
              <g key={node.id} className={`intro-node is-${node.kind}`} transform={`translate(${node.x} ${node.y})`}>
                <rect width={NODE_W} height={NODE_H} rx="8" />
                <text x="12" y="17" className="intro-node-name">{node.id}</text>
                <text x="12" y="31" className="intro-node-note">{node.note}</text>
              </g>
            ))}
          </svg>
          <ul className="catalog-intro-points">
            {points.map((point) => <li key={point.title}><h3>{point.title}</h3><p>{point.body}</p></li>)}
          </ul>
        </figure>
      </div>
    </section>
  )
}
