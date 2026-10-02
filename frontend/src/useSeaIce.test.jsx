import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useSeaIce } from './useSeaIce'

const TODAY = '2026-10-02'
// Extent layers have imagery up to today, concentration layers up to yesterday, MUR25 only up to two days ago
const latestFor = (url) => (url.includes('MUR25') ? '2026-09-30' : url.includes('Concentration') ? '2026-10-01' : '2026-10-02')
const available = (url) => url.match(/default\/(\d{4}-\d{2}-\d{2})\//)[1] <= latestFor(url)

const wrapper = ({ children }) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const MUR = 'GHRSST_L4_MUR_Sea_Ice_Concentration'
const MUR25 = 'GHRSST_L4_MUR25_Sea_Ice_Concentration'
const TERRA = 'MODIS_Terra_Sea_Ice'

beforeEach(() => {
  vi.setSystemTime(new Date(`${TODAY}T10:00:00Z`))
  vi.stubGlobal('fetch', vi.fn(async (url) => ({ ok: available(url) })))
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useSeaIce', () => {
  it('selects the most recent day with data, and each layer shows its newest imagery up to it', async () => {
    const { result } = renderHook(() => useSeaIce('mercator'), { wrapper })
    await waitFor(() => expect(result.current.date).toBe('2026-10-02'))
    expect(result.current.latest).toBe('2026-10-02')
    expect(result.current.newerDate).toBeNull()
    // default layer is MUR, which has nothing for today yet and so shows yesterday
    expect(result.current.overlays).toHaveLength(1)
    expect(result.current.overlays[0].url).toContain(`${MUR}/default/2026-10-01/`)
    expect(result.current.layers.find((l) => l.id === MUR).shownDate).toBe('2026-10-01')
  })

  it('steps back through previous days and updates the overlays', async () => {
    const { result } = renderHook(() => useSeaIce('mercator'), { wrapper })
    await waitFor(() => expect(result.current.date).toBe('2026-10-02'))
    act(() => result.current.setDate('2026-09-29'))
    expect(result.current.overlays[0].url).toContain('/2026-09-29/')
    expect(result.current.newerDate).toBe('2026-09-30')
    expect(result.current.olderDate).toBe('2026-09-28')
  })

  it('toggles layers, with MUR25 showing its own newest day', async () => {
    const { result } = renderHook(() => useSeaIce('mercator'), { wrapper })
    await waitFor(() => expect(result.current.date).toBe('2026-10-02'))
    act(() => result.current.toggleLayer(MUR25))
    expect(result.current.overlays.find((o) => o.id === MUR25).url).toContain('/2026-09-30/')
    act(() => result.current.toggleLayer(MUR))
    expect(result.current.overlays.map((o) => o.id)).toEqual([MUR25])
  })

  it('offers the extent layers in the polar projections, with Terra on by default and 512 px tiles', async () => {
    const { result } = renderHook(() => useSeaIce('epsg3031'), { wrapper })
    await waitFor(() => expect(result.current.date).toBe('2026-10-02'))
    expect(result.current.available).toBe(true)
    expect(result.current.layers.every((l) => l.kind === 'extent')).toBe(true)
    expect(result.current.overlays).toHaveLength(1)
    expect(result.current.overlays[0]).toMatchObject({ id: TERRA, tileSize: 512, zoomOffset: -1, minZoom: 1, maxNativeZoom: 4 })
    expect(result.current.overlays[0].url).toContain('/epsg3031/best/MODIS_Terra_Sea_Ice/default/2026-10-02/1km/')
  })

  it('remembers the layer choice separately for each projection', async () => {
    const { result, rerender } = renderHook(({ projection }) => useSeaIce(projection), { wrapper, initialProps: { projection: 'mercator' } })
    await waitFor(() => expect(result.current.date).toBe('2026-10-02'))
    act(() => result.current.toggleLayer(TERRA))
    expect(result.current.overlays.map((o) => o.id).sort()).toEqual([MUR, TERRA].sort())
    rerender({ projection: 'epsg3413' })
    await waitFor(() => expect(result.current.date).toBe('2026-10-02'))
    expect(result.current.overlays.map((o) => o.id)).toEqual([TERRA])
    rerender({ projection: 'mercator' })
    expect(result.current.overlays.map((o) => o.id).sort()).toEqual([MUR, TERRA].sort())
  })

  it('keeps the overlay objects stable when nothing changed', async () => {
    const { result, rerender } = renderHook(() => useSeaIce('mercator'), { wrapper })
    await waitFor(() => expect(result.current.overlays).toHaveLength(1))
    const before = result.current.overlays
    act(() => result.current.setOpacity(0.4))
    rerender()
    expect(result.current.overlays).toBe(before)
  })

  it('disables layers with no recent data', async () => {
    fetch.mockImplementation(async (url) => ({ ok: !url.includes('MUR25') && available(url) }))
    const { result } = renderHook(() => useSeaIce('mercator'), { wrapper })
    await waitFor(() => expect(result.current.layers.every((l) => !l.loading)).toBe(true))
    expect(result.current.layers.find((l) => l.id === MUR25).current).toBe(false)
  })
})
