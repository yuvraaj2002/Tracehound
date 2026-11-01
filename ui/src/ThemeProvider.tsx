import { useEffect, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router'
import { storedTheme, THEME_STORAGE_KEY, ThemeContext, type Theme } from './lib/theme'

/** Applies the chosen theme to <html> on every page except the marketing landing page, which stays light. */
export default function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(storedTheme)
  const { pathname } = useLocation()
  const applied = pathname === '/' ? 'light' : theme

  useEffect(() => {
    document.documentElement.dataset.theme = applied
  }, [applied])

  const toggle = () => setTheme((current) => {
    const next = current === 'black' ? 'light' : 'black'
    try { localStorage.setItem(THEME_STORAGE_KEY, next) } catch { /* storage blocked: keep it for this visit */ }
    return next
  })

  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>
}
