import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'

const baseUrl = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

const nav = [
  { group: 'Getting started', items: [{ id: 'introduction', label: 'Introduction' }, { id: 'quickstart', label: 'Quickstart' }, { id: 'authentication', label: 'Authentication' }] },
  { group: 'Investigations', items: [{ id: 'create-investigation', label: 'Start an investigation', method: 'POST' }] },
  { group: 'Reference', items: [{ id: 'errors', label: 'Errors' }] },
]

type Param = { name: string, type: string, required: boolean, description: ReactNode }

const bodyParams: Param[] = [
  { name: 'service_id', type: 'string', required: true, description: <>The service that is misbehaving, as it is labelled in your logs. 1–128 characters: letters, digits, <code>.</code> <code>_</code> <code>-</code>.</> },
  { name: 'symptom', type: 'string', required: true, description: 'What you are seeing, in plain words. Up to 2,000 characters. The alert title and summary work well.' },
  { name: 'window_start', type: 'datetime', required: true, description: <>Start of the time range to investigate, in ISO 8601 with a timezone, e.g. <code>2026-10-29T14:00:00Z</code>.</> },
  { name: 'window_end', type: 'datetime', required: true, description: <>End of the range. Must be after <code>window_start</code>.</> },
  { name: 'severity', type: 'enum', required: true, description: <>One of <code>low</code>, <code>medium</code>, <code>high</code> or <code>critical</code>.</> },
  { name: 'trace_id', type: 'string', required: false, description: 'A trace ID from the failing request, if you have one. Up to 128 characters.' },
]

const responseFields: Param[] = [
  { name: 'incident_id', type: 'uuid', required: true, description: 'The case that was opened.' },
  { name: 'run_id', type: 'uuid', required: true, description: 'The investigation run working on it. Every run appears on the dashboard.' },
  { name: 'status_url', type: 'string', required: true, description: 'Path to the incident, relative to the API base URL.' },
]

const errors = [
  { code: '401', title: 'Unauthorized', description: 'The API key is missing, malformed or revoked.' },
  { code: '422', title: 'Unprocessable', description: <>The body failed validation. <code>detail</code> lists each field that is wrong.</> },
  { code: '500', title: 'Server error', description: 'Tracehound could not store the incident. Retry with backoff.' },
]

const examplePayload = {
  service_id: 'checkout-api',
  symptom: 'p99 latency above 2s and 5xx rate at 4% since 14:05',
  window_start: '2026-10-29T14:00:00Z',
  window_end: '2026-10-29T14:30:00Z',
  severity: 'high',
}
const json = JSON.stringify(examplePayload, null, 2)
const indented = (text: string, pad: string) => text.split('\n').map((line, index) => index === 0 ? line : pad + line).join('\n')

const samples = {
  cURL: `curl -X POST ${baseUrl}/v1/incidents \\
  -H "Authorization: Bearer $TRACEHOUND_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '${indented(json, '  ')}'`,
  Python: `import os
import requests

response = requests.post(
    "${baseUrl}/v1/incidents",
    headers={"Authorization": f"Bearer {os.environ['TRACEHOUND_API_KEY']}"},
    json=${indented(json, '    ')},
    timeout=10,
)
response.raise_for_status()
print(response.json()["run_id"])`,
  JavaScript: `const response = await fetch("${baseUrl}/v1/incidents", {
  method: "POST",
  headers: {
    Authorization: \`Bearer \${process.env.TRACEHOUND_API_KEY}\`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify(${indented(json, '  ')}),
})
if (!response.ok) throw new Error(\`Tracehound: \${response.status}\`)
const { run_id } = await response.json()`,
}
type Language = keyof typeof samples

const responses = {
  '202': `{
  "incident_id": "7d1c2f0e-5b8a-4c39-9e0d-2a6f1b3c4d5e",
  "run_id": "b4e9a1c7-3f62-4d18-8a5b-9c0e7f2d1a36",
  "status_url": "/v1/incidents/7d1c2f0e-5b8a-4c39-9e0d-2a6f1b3c4d5e"
}`,
  '401': `{
  "detail": "Missing or invalid access token."
}`,
  '422': `{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body"],
      "msg": "Value error, window_end must be after window_start"
    }
  ]
}`,
}
type Status = keyof typeof responses

/** Developer docs for triggering an investigation from an alerting tool or script. */
export default function ApiDocs() {
  const active = useActiveSection(nav.flatMap((group) => group.items.map((item) => item.id)))
  const [language, setLanguage] = useState<Language>('cURL')

  return (
    <div className="auth-page">
      <SignedInHeader />

      <main className="workspace docs">
        <Link className="back-link" to="/app"><span aria-hidden="true">←</span> Home</Link>
        <div className="workspace-heading">
          <div><p className="eyebrow"><span /> Developers</p><h1>API reference</h1></div>
          <p>One request opens a case. Marshal and the specialists take it from there.</p>
        </div>

        <div className="docs-layout">
          <nav className="docs-nav" aria-label="API reference">
            {nav.map((group) => <div key={group.group}>
              <p className="docs-nav-group">{group.group}</p>
              <ul>
                {group.items.map((item) => <li key={item.id}>
                  <a href={`#${item.id}`} aria-current={active === item.id ? 'location' : undefined}>
                    {'method' in item && <span className="docs-method is-post">{item.method}</span>}{item.label}
                  </a>
                </li>)}
              </ul>
            </div>)}
          </nav>

          <div className="docs-content">
            <section id="introduction" className="docs-section">
              <h2>Introduction</h2>
              <p>The Tracehound API lets your alerting tool, on-call bot or deploy script start an investigation the moment something breaks. Send the service, the symptom and the time window. The specialists read your logs, test competing explanations and write up a cited report.</p>
              <dl className="docs-facts">
                <div><dt>Base URL</dt><dd><code>{baseUrl}</code></dd></div>
                <div><dt>Format</dt><dd>JSON over HTTPS</dd></div>
                <div><dt>Auth</dt><dd>Bearer API key</dd></div>
              </dl>
            </section>

            <section id="quickstart" className="docs-section">
              <h2>Quickstart</h2>
              <ol className="docs-steps">
                <li><span>01</span><div><h3>Connect your logs</h3><p>Point Tracehound at your Loki so the Logs agent has real evidence to read. <Link to="/app/integrations">Open integrations</Link></p></div></li>
                <li><span>02</span><div><h3>Create an API key</h3><p>Keys start with <code>th_</code> and are shown once. Store it as <code>TRACEHOUND_API_KEY</code> in your tool's secrets. <Link to="/app/api-keys">Create a key</Link></p></div></li>
                <li><span>03</span><div><h3>Send your first incident</h3><p>Call <a href="#create-investigation"><code>POST /v1/incidents</code></a> from your alert webhook. The run shows up on your <Link to="/app/incidents">dashboard</Link>.</p></div></li>
              </ol>
            </section>

            <section id="authentication" className="docs-section">
              <h2>Authentication</h2>
              <p>Send your API key in the <code>Authorization</code> header on every request. Keep keys on the server: anyone holding a key can open cases on your behalf. Revoke a leaked key on the <Link to="/app/api-keys">API keys</Link> page and it stops working immediately.</p>
              <CodeBlock label="Header" code="Authorization: Bearer th_your_api_key" />
            </section>

            <section id="create-investigation" className="docs-section docs-endpoint">
              <div className="docs-endpoint-copy">
                <h2>Start an investigation</h2>
                <p className="docs-route"><span className="docs-method is-post">POST</span><code>/v1/incidents</code></p>
                <p>Opens an incident and queues an investigation run. The request returns as soon as the case is stored, with <code>202 Accepted</code>; the investigation continues in the background.</p>

                <h3>Body</h3>
                <ParamList params={bodyParams} />

                <h3>Response <span className="docs-status is-ok">202</span></h3>
                <ParamList params={responseFields} />
              </div>

              <div className="docs-endpoint-code">
                <div className="code-panel">
                  <div className="code-panel-head">
                    <div role="tablist" aria-label="Request language">
                      {(Object.keys(samples) as Language[]).map((name) => <button key={name} type="button" role="tab" aria-selected={language === name} onClick={() => setLanguage(name)}>{name}</button>)}
                    </div>
                    <CopyButton text={samples[language]} />
                  </div>
                  <pre role="tabpanel" aria-label={`${language} request`}><code>{samples[language]}</code></pre>
                </div>
                <ResponsePanel />
              </div>
            </section>

            <section id="errors" className="docs-section">
              <h2>Errors</h2>
              <p>Tracehound uses standard HTTP status codes. Error bodies always carry a <code>detail</code> field you can log.</p>
              <ul className="docs-errors">
                {errors.map((error) => <li key={error.code}><span className="docs-status is-error">{error.code}</span><div><strong>{error.title}</strong><p>{error.description}</p></div></li>)}
              </ul>
            </section>
          </div>
        </div>
      </main>
    </div>
  )
}

function ParamList({ params }: { params: Param[] }) {
  return (
    <ul className="docs-params">
      {params.map((param) => <li key={param.name}>
        <div className="docs-param-head"><code>{param.name}</code><span className="docs-type">{param.type}</span>{param.required ? <span className="docs-required">required</span> : <span className="docs-optional">optional</span>}</div>
        <p>{param.description}</p>
      </li>)}
    </ul>
  )
}

function ResponsePanel() {
  const [status, setStatus] = useState<Status>('202')
  return (
    <div className="code-panel">
      <div className="code-panel-head">
        <div role="tablist" aria-label="Response status">
          {(Object.keys(responses) as Status[]).map((code) => <button key={code} type="button" role="tab" aria-selected={status === code} onClick={() => setStatus(code)}><span className={`docs-dot ${code === '202' ? 'is-ok' : 'is-error'}`} />{code}</button>)}
        </div>
        <CopyButton text={responses[status]} />
      </div>
      <pre role="tabpanel" aria-label={`${status} response`}><code>{responses[status]}</code></pre>
    </div>
  )
}

function CodeBlock({ label, code }: { label: string, code: string }) {
  return (
    <div className="code-panel">
      <div className="code-panel-head"><span className="code-panel-label">{label}</span><CopyButton text={code} /></div>
      <pre><code>{code}</code></pre>
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 1600)
    return () => clearTimeout(timer)
  }, [copied])
  const copy = () => { void navigator.clipboard.writeText(text).then(() => setCopied(true)) }
  return <button type="button" className="code-copy" onClick={copy} aria-live="polite">{copied ? 'Copied' : 'Copy'}</button>
}

/** The id of the section nearest the top of the viewport, for highlighting the side nav. */
function useActiveSection(ids: string[]) {
  const [active, setActive] = useState(ids[0])
  const key = ids.join(',')
  useEffect(() => {
    const sections = key.split(',').map((id) => document.getElementById(id)).filter((node): node is HTMLElement => node !== null)
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (visible[0]) setActive(visible[0].target.id)
    }, { rootMargin: '-80px 0px -65% 0px' })
    sections.forEach((section) => observer.observe(section))
    return () => observer.disconnect()
  }, [key])
  return active
}
