import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode, type RefObject } from 'react'

// The fallback ref is read when focus moves back, not when the dialog opened.
const restoreFocus = (opener: HTMLElement | null, fallback: RefObject<HTMLElement | null>) => (opener?.isConnected && opener !== document.body ? opener : fallback.current)?.focus()

/** A modal dialog: focus stays inside, and Esc or a backdrop click call onDismiss
 *  when it is set. Pass null to require an explicit button instead. */
export default function Dialog({ labelledBy, describedBy, onDismiss, fallbackFocus, wide = false, children }: { labelledBy: string, describedBy?: string, onDismiss: (() => void) | null, fallbackFocus: RefObject<HTMLElement | null>, wide?: boolean, children: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null)
  // Read during the first render: by the time effects run, autoFocus has already moved focus inside.
  const [opener] = useState(() => document.activeElement as HTMLElement | null)

  // Lock page scroll while open; on close, return focus to whatever opened the
  // dialog, or to the fallback when that element has gone (a removed row).
  useEffect(() => {
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    if (!panel.current?.contains(document.activeElement)) panel.current?.focus()
    return () => {
      document.body.style.overflow = overflow
      // Decide after the page re-renders: the removed row is gone, the empty state's button may be new.
      requestAnimationFrame(() => restoreFocus(opener, fallbackFocus))
    }
  }, [opener, fallbackFocus])

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      onDismiss?.()
      return
    }
    if (event.key !== 'Tab' || !panel.current) return
    const focusable = [...panel.current.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [href], [tabindex]:not([tabindex="-1"])')]
    if (!focusable.length) return
    const first = focusable[0]!
    const last = focusable.at(-1)!
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }

  return (
    <div className="dialog-backdrop" onPointerDown={(event) => {
      if (event.target !== event.currentTarget) return
      // Keep focus inside the dialog, so Esc still reaches it after a backdrop click.
      event.preventDefault()
      onDismiss?.()
    }}>
      <div ref={panel} className={wide ? 'dialog dialog-wide' : 'dialog'} role="dialog" aria-modal="true" aria-labelledby={labelledBy} aria-describedby={describedBy} tabIndex={-1} onKeyDown={onKeyDown}>
        {children}
      </div>
    </div>
  )
}
