import { useEffect } from 'react'
import Lenis from 'lenis'
import 'lenis/dist/lenis.css'

export function useSmoothScroll() {
  useEffect(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    let lenis: Lenis | undefined
    const configure = () => {
      lenis?.destroy()
      lenis = undefined
      if (!reducedMotion.matches) {
        lenis = new Lenis({ autoRaf: true, lerp: 0.085, smoothWheel: true, syncTouch: false })
      }
    }
    const navigate = (event: MouseEvent) => {
      if (!lenis || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('a[href]') : null
      if (!link || link.target || link.hasAttribute('download')) return
      const url = new URL(link.href)
      if (url.origin !== location.origin || url.pathname !== location.pathname || url.search !== location.search) return
      const rawHash = link.getAttribute('href')
      if (!url.hash && rawHash !== '#') return
      const target = url.hash ? document.getElementById(decodeURIComponent(url.hash.slice(1))) : document.querySelector<HTMLElement>('header')
      if (!target) return
      event.preventDefault()
      if (location.hash !== url.hash) history.pushState(null, '', url.hash || location.pathname + location.search)
      // Native keyboard/history scrolling can happen between animation frames.
      // Synchronize before measuring a new anchor to avoid stale-position offsets.
      lenis.scrollTo(window.scrollY, { immediate: true })
      lenis.scrollTo(url.hash ? target : 0, {
        onComplete: () => {
          // Move keyboard focus with the destination without a second jump.
          const hadTabIndex = target.hasAttribute('tabindex')
          if (!hadTabIndex) target.setAttribute('tabindex', '-1')
          target.focus({ preventScroll: true })
          if (!hadTabIndex) target.removeAttribute('tabindex')
        },
      })
    }
    configure()
    document.addEventListener('click', navigate)
    reducedMotion.addEventListener('change', configure)
    return () => {
      lenis?.destroy()
      document.removeEventListener('click', navigate)
      reducedMotion.removeEventListener('change', configure)
    }
  }, [])
}
