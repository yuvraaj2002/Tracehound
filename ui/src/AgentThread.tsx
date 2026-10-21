import { useEffect, useId, useRef } from 'react'

const agentNames = ['triage', 'logs', 'metrics', 'dependency', 'deploy', 'hypothesis']
const mix = (from: number[], to: number[], amount: number) => `rgb(${from.map((value, i) => Math.round(value + (to[i]! - value) * amount)).join(' ')})`

/** Decorative light follows actual scroll position, outside the reading area,
 *  then runs down into Marshal's first stage in How it works. */
export default function AgentThread() {
  const svg = useRef<SVGSVGElement>(null)
  const id = useId().replaceAll(':', '')
  useEffect(() => {
    const root = svg.current
    const container = root?.parentElement
    if (!root || !container) return
    const track = root.querySelector<SVGPathElement>('.thread-track')!
    const paths = [...root.querySelectorAll<SVGPathElement>('.thread-drawn')]
    const head = root.querySelector<SVGGElement>('.thread-head')!
    const particles = [...root.querySelectorAll<SVGCircleElement>('.thread-particle')]
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    let frame = 0, length = 0, firstY = 0, lastY = 1, mergeY = 1
    let colors: number[][] = []
    let centers: number[] = []
    const paint = () => {
      frame = 0
      const position = window.innerHeight * .52 - container.getBoundingClientRect().top
      const fraction = Math.min(1, Math.max(0, (position - firstY) / (lastY - firstY)))
      let low = 0, high = length
      for (let i = 0; i < 14; i++) {
        const mid = (low + high) / 2
        if (track.getPointAtLength(mid).y < position) low = mid
        else high = mid
      }
      const distance = fraction === 0 ? 0 : fraction === 1 ? length : (low + high) / 2
      for (const path of paths) path.style.strokeDashoffset = String(reduced.matches ? 0 : 1 - distance / (length || 1))
      const point = track.getPointAtLength(distance)
      let index = 0
      while (index < centers.length - 2 && position > centers[index + 1]!) index++
      const blend = Math.min(1, Math.max(0, (position - centers[index]!) / (centers[index + 1]! - centers[index]!)))
      const color = mix(colors[index]!, colors[index + 1]!, blend)
      const finish = Math.min(1, Math.max(0, (position - mergeY) / (lastY - mergeY)))
      head.setAttribute('transform', `translate(${point.x} ${point.y})`)
      head.style.color = color
      head.style.opacity = reduced.matches || fraction === 0 ? '0' : String(1 - finish)
      particles.forEach((particle, i) => {
        const angle = (i / particles.length) * Math.PI * 2
        particle.setAttribute('cx', String(point.x + Math.cos(angle) * finish * (24 + i * 3)))
        particle.setAttribute('cy', String(point.y + Math.sin(angle) * finish * 30))
        particle.style.fill = color
        particle.style.opacity = reduced.matches ? '0' : String(Math.sin(finish * Math.PI) * .65)
      })
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(paint) }
    const measure = () => {
      const bounds = container.getBoundingClientRect()
      const mobile = window.matchMedia('(max-width: 700px)').matches
      const members = [...container.querySelectorAll<HTMLElement>('.team-member')]
      const points = members.map((member, index) => {
        const box = member.getBoundingClientRect()
        const art = member.querySelector<HTMLElement>('.member-art')!.getBoundingClientRect()
        const copy = member.querySelector<HTMLElement>('.member-copy')!.getBoundingClientRect()
        const x = mobile ? 3 : index % 2 === 0 ? (art.right + copy.left) / 2 - bounds.left : (copy.right + art.left) / 2 - bounds.left
        const hex = getComputedStyle(member).getPropertyValue('--agent-color').trim()
        colors[index] = [1, 3, 5].map(start => parseInt(hex.slice(start, start + 2), 16))
        return { x, top: box.top - bounds.top + 24, bottom: box.bottom - bounds.top - 24 }
      })
      if (!points.length) return
      centers = points.map(point => (point.top + point.bottom) / 2)
      firstY = points[0]!.top
      const last = points.at(-1)!
      const finishY = last.bottom
      // The thread ends inside Marshal's node, routed around the How it works heading.
      const marshal = document.querySelector<HTMLElement>('.journey-stages > li:first-child')?.getBoundingClientRect()
      const heading = document.querySelector<HTMLElement>('.how .section-heading')
      let ending = ''
      if (marshal && heading) {
        const target = { x: marshal.left - bounds.left + 18.5, y: marshal.top - bounds.top + 18.5 }
        const box = heading.getBoundingClientRect()
        const top = box.top - bounds.top, bottom = box.bottom - bounds.top
        if (mobile) {
          const x = -10
          ending = ` C ${last.x} ${finishY + 60}, ${x} ${top - 70}, ${x} ${top - 20} L ${x} ${target.y - 28} C ${x} ${target.y}, ${x} ${target.y}, ${target.x - 18.5} ${target.y}`
        } else {
          const copy = heading.querySelector<HTMLElement>(':scope > p:last-child')!.getBoundingClientRect()
          const title = heading.querySelector<HTMLElement>(':scope > div')!.getBoundingClientRect()
          const x = (Math.min(title.right, copy.left - 32) + copy.left) / 2 - bounds.left
          const middle = (bottom + target.y - 18.5) / 2
          ending = ` C ${last.x} ${finishY + 90}, ${x} ${top - 90}, ${x} ${top - 20} L ${x} ${bottom + 4} C ${x} ${middle + 10}, ${target.x} ${middle - 10}, ${target.x} ${target.y - 30} L ${target.x} ${target.y}`
        }
        lastY = target.y
        centers.push(lastY)
        colors.push([0x28, 0x4b, 0x63])
      } else {
        lastY = bounds.height - 16
        ending = ` C ${last.x} ${finishY + 50}, ${bounds.width / 2} ${lastY - 50}, ${bounds.width / 2} ${lastY}`
      }
      colors.length = centers.length
      mergeY = lastY - 70
      const d = points.map((point, i) => {
        if (i === 0) return `M ${point.x} ${point.top} L ${point.x} ${point.bottom}`
        const previous = points[i - 1]!
        const middle = (previous.bottom + point.top) / 2
        return `C ${previous.x} ${middle}, ${point.x} ${middle}, ${point.x} ${point.top} L ${point.x} ${point.bottom}`
      }).join(' ') + ending
      root.setAttribute('viewBox', `0 0 ${bounds.width} ${bounds.height}`)
      track.setAttribute('d', d)
      for (const path of paths) path.setAttribute('d', d)
      root.querySelectorAll<SVGStopElement>('.thread-color').forEach((stop, index) => {
        stop.setAttribute('offset', String((centers[index]! - firstY) / (lastY - firstY)))
        stop.style.stopColor = `rgb(${colors[index]!.join(' ')})`
      })
      length = track.getTotalLength()
      paint()
    }
    const observer = new ResizeObserver(measure)
    observer.observe(container)
    const how = document.getElementById('how')
    if (how) observer.observe(how)
    // Fonts and lazy images move the How it works section after mount; re-route once they settle.
    let alive = true
    document.fonts?.ready.then(() => { if (alive) measure() })
    window.addEventListener('load', measure)
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', measure)
    reduced.addEventListener('change', schedule)
    measure()
    return () => {
      alive = false
      observer.disconnect()
      window.removeEventListener('load', measure)
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', measure)
      reduced.removeEventListener('change', schedule)
      cancelAnimationFrame(frame)
    }
  }, [])
  return <svg ref={svg} className="agent-thread" aria-hidden="true">
    <defs>
      <linearGradient id={`${id}-colors`} x1="0" y1="0" x2="0" y2="1">{[...agentNames, 'marshal'].map(name => <stop className="thread-color" key={name} />)}</linearGradient>
      <filter id={`${id}-glow`} x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="3" /></filter>
    </defs>
    <g>
      <path className="thread-track" />
      <path className="thread-drawn thread-aura" pathLength="1" stroke={`url(#${id}-colors)`} />
      <path className="thread-drawn thread-progress" pathLength="1" stroke={`url(#${id}-colors)`} />
    </g>
    <g className="thread-head"><circle r="11" fill="currentColor" opacity=".22" filter={`url(#${id}-glow)`} /><circle r="5" fill="currentColor" /><circle className="thread-marker" r="2" fill="white" /></g>
    {Array.from({ length: 7 }, (_, i) => <circle className="thread-particle" key={i} r={i % 2 ? 1.5 : 2} opacity="0" />)}
  </svg>
}
