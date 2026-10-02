import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'polarroute-theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'

const systemTheme = () => (window.matchMedia?.(DARK_QUERY).matches ? 'dark' : 'light')

function storedTheme() {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme
}

// Applies the saved theme (or the system preference) before the first render to avoid a flash.
export const initTheme = () => applyTheme(storedTheme() ?? systemTheme())

// Follows the operating system setting until the user picks a theme with the toggle.
export function useTheme() {
  const [explicit, setExplicit] = useState(storedTheme)
  const [system, setSystem] = useState(systemTheme)
  const theme = explicit ?? system

  useEffect(() => {
    const query = window.matchMedia?.(DARK_QUERY)
    if (!query) return undefined
    const onChange = () => setSystem(query.matches ? 'dark' : 'light')
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  useEffect(() => applyTheme(theme), [theme])

  const toggleTheme = useCallback(() => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setExplicit(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Storage unavailable: the choice still applies for this session
    }
  }, [theme])

  return { theme, toggleTheme }
}
