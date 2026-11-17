import { createContext, useContext } from 'react'

export type Theme = 'light' | 'black'

export const THEME_STORAGE_KEY = 'tracehound-theme'

export function storedTheme(): Theme {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) === 'black' ? 'black' : 'light'
  } catch {
    return 'light'
  }
}

export const ThemeContext = createContext<{ theme: Theme, toggle: () => void }>({ theme: 'light', toggle: () => {} })

/** The viewer's chosen theme, remembered in this browser. Light until they pick black. */
export function useTheme() {
  return useContext(ThemeContext)
}
