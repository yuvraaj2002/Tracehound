import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import './ModelSelect.css'

type Option = { id: string, label: string, hint?: string }

/** A Notion-style dropdown: a quiet field that opens a soft menu with the current choice ticked. */
export default function ModelSelect({ label, value, options, onChange }: { label: string, value: string, options: Option[], onChange: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const id = useId()
  const selected = options.findIndex((option) => option.id === value)

  useEffect(() => {
    if (!open) return
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [open])

  const show = () => { setCursor(Math.max(selected, 0)); setOpen(true) }
  const pick = (index: number) => { onChange(options[index]!.id); setOpen(false) }
  const onKey = (event: KeyboardEvent) => {
    if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); setOpen(false); return }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) return show()
      setCursor((current) => (current + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length)
    }
    if ((event.key === 'Enter' || event.key === ' ') && open) { event.preventDefault(); pick(cursor) }
  }

  return (
    <div className="nsel" ref={root} onKeyDown={onKey}>
      <button type="button" className="nsel-field" role="combobox" aria-label={label} aria-expanded={open} aria-haspopup="listbox" aria-controls={`${id}-list`}
        aria-activedescendant={open ? `${id}-${cursor}` : undefined} onClick={() => open ? setOpen(false) : show()}>
        <span>{options[selected]?.label ?? 'Select a model'}</span>
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      {open && <ul className="nsel-menu" id={`${id}-list`} role="listbox" aria-label={label}>
        {options.map((option, index) => <li key={option.id} id={`${id}-${index}`} role="option" aria-selected={index === selected} data-active={index === cursor || undefined}
          onPointerEnter={() => setCursor(index)} onClick={() => pick(index)}>
          <span className="nsel-label">{option.label}{option.hint && <small>{option.hint}</small>}</span>
          {index === selected && <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="m2.5 6.5 2.5 2.5 4.5-5.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>}
        </li>)}
      </ul>}
    </div>
  )
}
