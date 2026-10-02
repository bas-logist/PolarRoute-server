import { describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useMediaQuery } from './useMediaQuery'

describe('useMediaQuery', () => {
  it('reports the current match and follows changes', () => {
    let listener
    const list = {
      matches: false,
      addEventListener: vi.fn((_, fn) => (listener = fn)),
      removeEventListener: vi.fn(),
    }
    window.matchMedia = vi.fn().mockReturnValue(list)

    const { result, unmount } = renderHook(() => useMediaQuery('(max-width: 767px)'))
    expect(result.current).toBe(false)

    list.matches = true
    act(() => listener())
    expect(result.current).toBe(true)

    unmount()
    expect(list.removeEventListener).toHaveBeenCalled()
  })

  it('is false when matchMedia is unavailable', () => {
    window.matchMedia = undefined
    const { result } = renderHook(() => useMediaQuery('(max-width: 767px)'))
    expect(result.current).toBe(false)
  })
})
