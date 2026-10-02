import { useEffect, useState } from 'react'

const matches = (query) => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : false)

// Tracks a CSS media query, e.g. useMediaQuery('(max-width: 767px)').
export function useMediaQuery(query) {
  const [value, setValue] = useState(() => matches(query))

  useEffect(() => {
    const list = window.matchMedia?.(query)
    if (!list) return undefined
    const onChange = () => setValue(list.matches)
    onChange()
    list.addEventListener('change', onChange)
    return () => list.removeEventListener('change', onChange)
  }, [query])

  return value
}

// Phones and small tablets in portrait: the sidebar and map are shown one at a time (keep in step with index.css)
export const MOBILE_QUERY = '(max-width: 767px)'
