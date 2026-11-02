import './ServiceCatalog.css'

const SNIPPET = `apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: checkout-api
spec:
  type: service
  owner: group:team-checkout
  dependsOn:
    - component:orders
    - resource:orders-db`

const points = [
  { title: 'Backstage format, as is', body: 'Upload the catalog-info.yaml you already keep. No new schema to learn or convert to.' },
  { title: 'Upload it, or PUT it from CI', body: 'Paste it in the app, or send it to PUT /v1/catalog on every merge so the map stays current.' },
  { title: 'Triage knows the blast radius', body: 'Dependencies and owners tell triage which neighbours to investigate and whose service it is.' },
]

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

        <figure className="catalog-intro-map" aria-label="checkout-api depends on orders and orders-db">
          <figcaption>What triage reads</figcaption>
          <div className="catalog-intro-graph" aria-hidden="true">
            <span className="catalog-node is-service"><code>checkout-api</code><small>team-checkout</small></span>
            <span className="catalog-wires"><span>http</span><span>postgres</span></span>
            <span className="catalog-targets">
              <span className="catalog-node is-service"><code>orders</code><small>service</small></span>
              <span className="catalog-node is-resource"><code>orders-db</code><small>postgres</small></span>
            </span>
          </div>
          <ul className="catalog-intro-points">
            {points.map((point) => <li key={point.title}><h3>{point.title}</h3><p>{point.body}</p></li>)}
          </ul>
        </figure>
      </div>
    </section>
  )
}
