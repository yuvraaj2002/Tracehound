import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import type { CatalogEdge, CatalogEntity } from './lib/api'
import './CatalogGraph.css'

const NODE_W = 176
const NODE_H = 52
const COL_GAP = 96
const ROW_GAP = 22
const PAD = 24
const DRAG_THRESHOLD = 4

type Point = { x: number, y: number }
type Box = { x: number, y: number, w: number, h: number }

const MIN_ZOOM = 0.25  // how far in, as a share of the fitted width
const MAX_ZOOM = 4
const ZOOM_STEP = 1.25

/** Callers on the left, what they depend on to the right: a node's column is its longest path from a root. */
function layout(entities: CatalogEntity[], edges: CatalogEdge[]): Record<string, Point> {
  const names = new Set(entities.map((entity) => entity.name))
  const out = new Map<string, string[]>()
  const into = new Map<string, string[]>()
  for (const edge of edges) {
    if (!names.has(edge.source) || !names.has(edge.target)) continue
    out.set(edge.source, [...(out.get(edge.source) ?? []), edge.target])
    into.set(edge.target, [...(into.get(edge.target) ?? []), edge.source])
  }

  const depth = new Map<string, number>()
  const visiting = new Set<string>()
  const depthOf = (name: string): number => {
    const known = depth.get(name)
    if (known !== undefined) return known
    if (visiting.has(name)) return 0  // a dependency cycle: stop descending
    visiting.add(name)
    const value = Math.max(-1, ...(into.get(name) ?? []).map(depthOf)) + 1
    visiting.delete(name)
    depth.set(name, value)
    return value
  }
  entities.forEach((entity) => depthOf(entity.name))

  const columns: string[][] = []
  for (const entity of entities) (columns[depth.get(entity.name) ?? 0] ??= []).push(entity.name)

  // Order each column by the average row of its callers, so wires cross less.
  const row = new Map<string, number>()
  columns.forEach((column, index) => {
    if (index > 0) {
      const score = (name: string) => {
        const callers = (into.get(name) ?? []).filter((caller) => row.has(caller))
        return callers.length ? callers.reduce((sum, caller) => sum + (row.get(caller) ?? 0), 0) / callers.length : Infinity
      }
      column.sort((a, b) => score(a) - score(b) || a.localeCompare(b))
    } else column.sort()
    column.forEach((name, position) => row.set(name, position))
  })

  const tallest = Math.max(...columns.map((column) => column.length))
  const height = tallest * NODE_H + (tallest - 1) * ROW_GAP
  const positions: Record<string, Point> = {}
  columns.forEach((column, index) => {
    const used = column.length * NODE_H + (column.length - 1) * ROW_GAP
    column.forEach((name, position) => {
      positions[name] = { x: PAD + index * (NODE_W + COL_GAP), y: PAD + (height - used) / 2 + position * (NODE_H + ROW_GAP) }
    })
  })
  return positions
}

/** Everything reachable from `start` along `next`, not including `start`. */
function reach(start: string, next: Map<string, string[]>): Set<string> {
  const seen = new Set<string>()
  const queue = [start]
  while (queue.length) {
    for (const name of next.get(queue.shift() as string) ?? []) if (!seen.has(name)) { seen.add(name); queue.push(name) }
  }
  return seen
}

const wire = (from: Point, to: Point) => {
  const x1 = from.x + NODE_W, y1 = from.y + NODE_H / 2, x2 = to.x, y2 = to.y + NODE_H / 2
  const bend = Math.max(40, Math.abs(x2 - x1) / 2)
  return `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`
}

const clip = (text: string, max: number) => text.length > max ? `${text.slice(0, max - 1)}…` : text

/**
 * The dependency graph of a catalog. Hover or focus a node to trace what it calls (and what calls it),
 * click to pin it and read its details, drag to rearrange.
 */
export default function CatalogGraph({ entities, edges }: { entities: CatalogEntity[], edges: CatalogEdge[] }) {
  const base = useMemo(() => layout(entities, edges), [entities, edges])
  const [moved, setMoved] = useState<Record<string, Point>>({})
  const [pinned, setPinned] = useState<string | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)
  const svg = useRef<SVGSVGElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const [full, setFull] = useState(false)
  const [view, setView] = useState<Box | null>(null)  // null = fit everything
  const pan = useRef<{ x: number, y: number, box: Box, moved: boolean } | null>(null)
  const drag = useRef<{ name: string, start: Point, origin: Point, travelled: boolean } | null>(null)

  // Esc, or any other way out of full screen, comes through here too.
  useEffect(() => {
    const sync = () => setFull(document.fullscreenElement === stage.current)
    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])
  const toggleFull = () => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void stage.current?.requestFullscreen().catch(() => undefined)
  }

  const at = (name: string): Point => moved[name] ?? base[name]
  const byName = useMemo(() => new Map(entities.map((entity) => [entity.name, entity])), [entities])
  const downstream = useMemo(() => { const map = new Map<string, string[]>(); edges.forEach((edge) => map.set(edge.source, [...(map.get(edge.source) ?? []), edge.target])); return map }, [edges])
  const upstream = useMemo(() => { const map = new Map<string, string[]>(); edges.forEach((edge) => map.set(edge.target, [...(map.get(edge.target) ?? []), edge.source])); return map }, [edges])

  const focus = hovered ?? pinned
  const trace = useMemo(() => {
    if (!focus) return null
    const down = reach(focus, downstream)
    const up = reach(focus, upstream)
    return { down, up, lit: new Set([focus, ...down, ...up]) }
  }, [focus, downstream, upstream])
  const lit = trace?.lit ?? null
  // A wire is traced when it lies on a path leading away from, or into, the focused node.
  const traced = (edge: CatalogEdge) => !!trace && !!focus && (
    ((edge.source === focus || trace.down.has(edge.source)) && trace.down.has(edge.target)) ||
    ((edge.target === focus || trace.up.has(edge.target)) && trace.up.has(edge.source))
  )

  const positions = entities.map((entity) => at(entity.name))
  const width = Math.max(...positions.map((p) => p.x + NODE_W)) + PAD
  const height = Math.max(...positions.map((p) => p.y + NODE_H)) + PAD

  const box: Box = view ?? { x: 0, y: 0, w: width, h: height }

  // Screen to graph coordinates. The CTM accounts for the viewBox, the zoom and any letterboxing.
  const toSvg = (event: { clientX: number, clientY: number }): Point => {
    const element = svg.current
    const matrix = element?.getScreenCTM()
    if (!element || !matrix) return { x: event.clientX, y: event.clientY }
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    return { x: point.x, y: point.y }
  }

  /** Scale the view by `factor` (above 1 zooms out), keeping the graph point `around` where it is on screen. */
  const zoom = (factor: number, around?: Point) => {
    setView((prev) => {
      const current = prev ?? { x: 0, y: 0, w: width, h: height }
      const w = Math.min(width * MAX_ZOOM, Math.max(width * MIN_ZOOM, current.w * factor))
      const k = w / current.w
      const center = around ?? { x: current.x + current.w / 2, y: current.y + current.h / 2 }
      return { x: center.x - (center.x - current.x) * k, y: center.y - (center.y - current.y) * k, w, h: current.h * k }
    })
  }

  // Ctrl/⌘ + wheel (and trackpad pinch) zooms; in full screen a plain wheel does too. Otherwise the page scrolls.
  const wheel = useRef<(event: WheelEvent) => void>(() => undefined)
  useEffect(() => {
    wheel.current = (event) => {
      if (!(event.ctrlKey || event.metaKey || full)) return
      event.preventDefault()
      zoom(Math.exp(event.deltaY * (event.ctrlKey ? 0.01 : 0.0015)), toSvg(event))
    }
  })
  useEffect(() => {
    const element = svg.current
    if (!element) return
    const onWheel = (event: WheelEvent) => wheel.current(event)
    element.addEventListener('wheel', onWheel, { passive: false })  // React's own wheel handler is passive
    return () => element.removeEventListener('wheel', onWheel)
  }, [])

  // Dragging empty canvas pans.
  const onPanDown = (event: PointerEvent<SVGSVGElement>) => {
    if (event.target !== event.currentTarget) return
    event.currentTarget.setPointerCapture(event.pointerId)
    pan.current = { x: event.clientX, y: event.clientY, box, moved: false }
  }
  const onPanMove = (event: PointerEvent<SVGSVGElement>) => {
    const start = pan.current
    const element = svg.current
    if (!start || !element) return
    const dx = event.clientX - start.x, dy = event.clientY - start.y
    if (!start.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
    start.moved = true
    const rect = element.getBoundingClientRect()
    const scale = Math.max(start.box.w / rect.width, start.box.h / rect.height)  // graph units per pixel
    setView({ ...start.box, x: start.box.x - dx * scale, y: start.box.y - dy * scale })
  }
  const onPanUp = () => { window.setTimeout(() => { pan.current = null }, 0) }  // after the click that ends a drag

  const onDown = (name: string) => (event: PointerEvent<SVGGElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    drag.current = { name, start: toSvg(event), origin: at(name), travelled: false }
  }
  const onMove = (event: PointerEvent<SVGGElement>) => {
    const current = drag.current
    if (!current) return
    const now = toSvg(event)
    const dx = now.x - current.start.x, dy = now.y - current.start.y
    if (!current.travelled && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
    current.travelled = true
    setMoved((prev) => ({ ...prev, [current.name]: { x: Math.max(0, current.origin.x + dx), y: Math.max(0, current.origin.y + dy) } }))
  }
  const onUp = (name: string) => () => {
    const current = drag.current
    drag.current = null
    if (current && !current.travelled) setPinned((prev) => prev === name ? null : name)
  }
  const onKey = (name: string) => (event: KeyboardEvent) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setPinned((prev) => prev === name ? null : name) }
    if (event.key === 'Escape') setPinned(null)
  }

  const selected = pinned ? byName.get(pinned) : undefined
  const calls = selected ? edges.filter((edge) => edge.source === selected.name) : []
  const calledBy = selected ? edges.filter((edge) => edge.target === selected.name) : []

  return (
    <div className="graph">
      <div className="graph-stage" ref={stage}>
        <svg ref={svg} className="graph-canvas" viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`} role="group" aria-label={`Dependency graph: ${entities.length} entities, ${edges.length} dependencies`} onPointerDown={onPanDown} onPointerMove={onPanMove} onPointerUp={onPanUp} onPointerCancel={onPanUp} onClick={(event) => { if (event.target === event.currentTarget && !pan.current?.moved) setPinned(null) }}>
          <defs>
            <marker id="graph-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="context-stroke" /></marker>
          </defs>

          <g className="graph-edges">
            {edges.map((edge) => {
              if (!base[edge.source] || !base[edge.target]) return null
              const on = traced(edge)
              return <path key={`${edge.source}>${edge.target}`} d={wire(at(edge.source), at(edge.target))} className={`graph-edge${on ? ' is-lit' : ''}${lit && !on ? ' is-dim' : ''}`} markerEnd="url(#graph-arrow)" />
            })}
          </g>

          {entities.map((entity) => {
            const p = at(entity.name)
            const isService = entity.entity_kind === 'Component'
            const state = lit ? (lit.has(entity.name) ? ' is-lit' : ' is-dim') : ''
            return (
              <g key={entity.name} className={`graph-node ${isService ? 'is-service' : 'is-resource'}${state}${pinned === entity.name ? ' is-pinned' : ''}`} transform={`translate(${p.x} ${p.y})`} tabIndex={0} role="button" aria-pressed={pinned === entity.name} aria-label={`${entity.name}, ${isService ? 'service' : entity.kind}, owned by ${entity.owner}`}
                onPointerDown={onDown(entity.name)} onPointerMove={onMove} onPointerUp={onUp(entity.name)} onPointerCancel={() => { drag.current = null }}
                onPointerEnter={() => setHovered(entity.name)} onPointerLeave={() => setHovered(null)} onFocus={() => setHovered(entity.name)} onBlur={() => setHovered(null)} onKeyDown={onKey(entity.name)}>
                <rect width={NODE_W} height={NODE_H} rx="10" />
                <rect className="graph-node-bar" width="4" height={NODE_H} rx="2" />
                <text x="16" y="22" className="graph-node-name">{clip(entity.name, 20)}</text>
                <text x="16" y="39" className="graph-node-meta">{isService ? entity.type : entity.kind} · {clip(entity.owner.replace(/^team-/, ''), 12)}</text>
              </g>
            )
          })}
        </svg>

        {document.fullscreenEnabled && <button type="button" className="graph-full" onClick={toggleFull} aria-label={full ? 'Exit full screen' : 'View full screen'} title={full ? 'Exit full screen' : 'Full screen'}>
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{full ? <path d="M6 2v4H2M10 2v4h4M6 14v-4H2M10 14v-4h4" /> : <path d="M2 6V2h4M14 6V2h-4M2 10v4h4M14 10v4h-4" />}</svg>
        </button>}
        <div className="graph-zoom" role="group" aria-label="Zoom">
          <button type="button" onClick={() => zoom(1 / ZOOM_STEP)} aria-label="Zoom in" title="Zoom in">+</button>
          <button type="button" onClick={() => zoom(ZOOM_STEP)} aria-label="Zoom out" title="Zoom out">−</button>
          <button type="button" onClick={() => setView(null)} disabled={!view} aria-label="Fit to screen" title="Fit to screen">
            <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><circle cx="8" cy="8" r="2.5" /><path d="M8 1v3M8 12v3M1 8h3M12 8h3" /></svg>
          </button>
        </div>
        {Object.keys(moved).length > 0 && <button type="button" className="graph-reset" onClick={() => setMoved({})}>Reset layout</button>}

        {selected && <aside className="graph-detail" aria-live="polite">
          <button type="button" className="graph-detail-close" onClick={() => setPinned(null)} aria-label="Close details">×</button>
          <h3><code>{selected.name}</code></h3>
          <p className="graph-detail-kind">{selected.entity_kind === 'Component' ? 'Service' : 'Resource'} · {selected.kind}</p>
          {selected.description && <p className="graph-detail-note">{selected.description}</p>}
          <dl>
            <div><dt>Owner</dt><dd><code>{selected.owner}</code></dd></div>
            {selected.lifecycle && <div><dt>Lifecycle</dt><dd>{selected.lifecycle}</dd></div>}
            {selected.repository && <div><dt>Repository</dt><dd><code>{selected.repository}</code></dd></div>}
            {calls.length > 0 && <div><dt>Depends on</dt><dd>{calls.map((edge) => <code key={edge.target}>{edge.target}</code>)}</dd></div>}
            {calledBy.length > 0 && <div><dt>Used by</dt><dd>{calledBy.map((edge) => <code key={edge.source}>{edge.source}</code>)}</dd></div>}
          </dl>
        </aside>}
      </div>
    </div>
  )
}
