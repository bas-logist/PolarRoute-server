import { describe, expect, it, vi } from 'vitest'
import {
  COLOUR_SCALE_GRADIENT,
  DAYS_TO_OFFER,
  DEFAULT_ENABLED_LAYERS,
  SEA_ICE_LAYERS,
  findAvailableDates,
  formatDay,
  layersForProjection,
  probeUrl,
  recentDates,
  shownDateFor,
  tileUrlTemplate,
  toIsoDate,
} from './seaIce'

const mur = layersForProjection('mercator')[0]

describe('layer catalogue', () => {
  const ids = (projection) => layersForProjection(projection).map((l) => l.id)

  it('offers concentration and extent layers in Web Mercator', () => {
    expect(ids('mercator')).toContain('GHRSST_L4_MUR_Sea_Ice_Concentration')
    expect(ids('mercator')).toContain('MODIS_Terra_Sea_Ice')
    expect(layersForProjection('mercator').every((l) => l.projection === 'epsg3857')).toBe(true)
  })

  it('offers the extent layers, but no concentration layer, in the polar projections', () => {
    for (const projection of ['epsg3031', 'epsg3413']) {
      const layers = layersForProjection(projection)
      expect(layers.map((l) => l.kind)).toEqual(['extent', 'extent', 'extent', 'extent'])
      expect(layers.every((l) => l.projection === projection)).toBe(true)
    }
  })

  it('uses GIBS 512 px polar tiles that line up with zoom 1 of the polar CRSs', () => {
    const [layer] = layersForProjection('epsg3031')
    expect(layer).toMatchObject({ tileMatrixSet: '1km', tileSize: 512, zoomOffset: -1, minZoom: 1, maxNativeZoom: 4 })
  })

  it('excludes the sea ice layers whose data ended before today', () => {
    expect(SEA_ICE_LAYERS.map((l) => l.id).join(' ')).not.toMatch(/AMSR|SSMIS|_L3_/)
  })

  it('turns something on by default in every projection', () => {
    for (const projection of ['mercator', 'epsg3031', 'epsg3413']) {
      const defaults = DEFAULT_ENABLED_LAYERS[projection]
      expect(defaults.length).toBeGreaterThan(0)
      expect(defaults.every((id) => ids(projection).includes(id))).toBe(true)
    }
  })
})

describe('URLs', () => {
  it('builds polar tile URLs against the polar WMTS endpoint', () => {
    const [layer] = layersForProjection('epsg3413')
    expect(tileUrlTemplate(layer, '2026-10-02')).toBe('https://gibs.earthdata.nasa.gov/wmts/epsg3413/best/MODIS_Terra_Sea_Ice/default/2026-10-02/1km/{z}/{y}/{x}.png')
  })

  it('builds a Leaflet tile template for a layer and day', () => {
    expect(tileUrlTemplate(mur, '2026-10-01')).toBe(
      'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/GHRSST_L4_MUR_Sea_Ice_Concentration/default/2026-10-01/GoogleMapsCompatible_Level7/{z}/{y}/{x}.png',
    )
  })

  it('probes the single world tile', () => {
    expect(probeUrl(mur, '2026-10-01')).toMatch(/2026-10-01\/GoogleMapsCompatible_Level7\/0\/0\/0\.png$/)
  })
})

describe('dates', () => {
  it('lists the most recent days first, in UTC', () => {
    const days = recentDates(new Date('2026-10-02T23:30:00Z'), 4)
    expect(days).toEqual(['2026-10-02', '2026-10-01', '2026-09-30', '2026-09-29'])
    expect(recentDates(new Date('2026-10-02T00:00:00Z'))).toHaveLength(DAYS_TO_OFFER)
  })

  it('formats an ISO day without time zone shifts', () => {
    expect(toIsoDate(new Date('2026-10-02T23:59:59Z'))).toBe('2026-10-02')
    expect(formatDay('2026-10-01', 'en-GB')).toBe('Thu, 1 Oct 2026')
  })

  it('keeps only the days GIBS has imagery for', async () => {
    const fetchFn = vi.fn(async (url) => ({ ok: !url.includes('2026-10-02') && !url.includes('2026-09-29') }))
    const days = await findAvailableDates(mur, ['2026-10-02', '2026-10-01', '2026-09-30', '2026-09-29'], fetchFn)
    expect(days).toEqual(['2026-10-01', '2026-09-30'])
    expect(fetchFn).toHaveBeenCalledWith(expect.stringContaining('/0/0/0.png'), { method: 'HEAD' })
  })

  it('treats network failures as unavailable days', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error('offline'))
    await expect(findAvailableDates(mur, ['2026-10-01'], fetchFn)).resolves.toEqual([])
  })
})

describe('shownDateFor', () => {
  it('shows the newest day on or before the selected one', () => {
    const dates = ['2026-10-01', '2026-09-30', '2026-09-28']
    expect(shownDateFor(dates, '2026-10-02')).toBe('2026-10-01')
    expect(shownDateFor(dates, '2026-09-29')).toBe('2026-09-28')
    expect(shownDateFor(dates, '2026-09-01')).toBeNull()
    expect(shownDateFor(dates, null)).toBeNull()
  })
})

describe('colour scale', () => {
  it('is a gradient from 0 to 100 percent', () => {
    expect(COLOUR_SCALE_GRADIENT).toMatch(/^linear-gradient\(to right, rgb\(17,17,17\) 0%/)
    expect(COLOUR_SCALE_GRADIENT).toMatch(/rgb\(255,255,255\) 100%\)$/)
  })
})
