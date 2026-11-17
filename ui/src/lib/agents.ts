import type { AgentId } from './agentModels'

/** The six investigators, in the order the landing page introduces them. */
export const agentRoster: { id: AgentId, name: string, specialty: string, image: string, color: string, job: string }[] = [
  { id: 'triage', name: 'Marshal', specialty: 'Triage', image: '/agents/triage.png', color: 'var(--agent-triage)', job: 'Scopes the incident and directs the specialists.' },
  { id: 'logs', name: 'Echo', specialty: 'Logs', image: '/agents/logs.png', color: 'var(--agent-logs)', job: 'Reads log streams for errors and the first sign of trouble.' },
  { id: 'metrics', name: 'Pulse', specialty: 'Metrics', image: '/agents/metrics.png', color: 'var(--agent-metrics)', job: 'Finds latency spikes, saturation and error-rate shifts.' },
  { id: 'dependency', name: 'Tether', specialty: 'Dependency', image: '/agents/dependency.jpg', color: 'var(--agent-dependency)', job: 'Traces calls between services to find where a failure spread.' },
  { id: 'deploy', name: 'Ledger', specialty: 'Deploy', image: '/agents/deploy.png', color: 'var(--agent-deploy)', job: 'Lines up releases and config changes with the timeline.' },
  { id: 'hypothesis', name: 'Sage', specialty: 'Hypothesis', image: '/agents/hypothesis.jpg', color: 'var(--agent-hypothesis)', job: 'Weighs the evidence and ranks likely root causes.' },
]
