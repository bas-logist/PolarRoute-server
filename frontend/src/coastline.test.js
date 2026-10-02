import { describe, expect, it } from 'vitest'
import { buildCoastline, buildLandFill } from './coastline'

const allPoints = (feature) => feature.geometry.coordinates.flat(2)

describe('buildLandFill', () => {
  it('clamps latitudes to the requested range', () => {
    const lats = allPoints(buildLandFill(0, 90)).map((p) => p[1])
    expect(Math.min(...lats)).toBeGreaterThanOrEqual(0)
    expect(Math.max(...lats)).toBeLessThanOrEqual(90)
  })

  it('drops polygons wholly outside the range, so Antarctica is not drawn in the Arctic view', () => {
    const arctic = buildLandFill(0, 90).geometry.coordinates.length
    const antarctic = buildLandFill(-90, 0).geometry.coordinates.length
    const world = buildLandFill(-85, 85).geometry.coordinates.length
    expect(arctic).toBeLessThan(world)
    expect(antarctic).toBeLessThan(world)
    const arcticSouthernmostRings = buildLandFill(0, 90).geometry.coordinates.filter((poly) => poly[0].every((p) => p[1] === 0))
    expect(arcticSouthernmostRings).toHaveLength(0)
  })
})

describe('buildCoastline', () => {
  it('only contains points inside the latitude range', () => {
    const lats = buildCoastline(-90, 0).geometry.coordinates.flat().map((p) => p[1])
    expect(Math.max(...lats)).toBeLessThanOrEqual(0)
  })
})

describe('flat map (antimeridian) handling', () => {
  const MAX = 85.0511
  // Edges lying on the map's top/bottom border (Antarctica's closure through the pole) legitimately span the full width
  const onBorder = (p) => Math.abs(p[1]) === MAX
  const jumps = (rings) =>
    rings.flatMap((ring) => ring.slice(1).filter((p, i) => Math.abs(p[0] - ring[i][0]) > 180 && !(onBorder(p) && onBorder(ring[i]))))

  it('has no ring edges that span the whole world when splitting at the antimeridian', () => {
    const polygons = buildLandFill(-MAX, MAX, { splitAtAntimeridian: true }).geometry.coordinates
    expect(jumps(polygons.flat())).toEqual([])
  })

  it('keeps every longitude within [-180, 180] after splitting', () => {
    const lons = buildLandFill(-MAX, MAX, { splitAtAntimeridian: true }).geometry.coordinates.flat(2).map((p) => p[0])
    expect(Math.min(...lons)).toBeGreaterThanOrEqual(-180)
    expect(Math.max(...lons)).toBeLessThanOrEqual(180)
  })

  it('still contains world-spanning edges without the option (the data stores some polygons that way)', () => {
    const polygons = buildLandFill(-MAX, MAX).geometry.coordinates
    expect(jumps(polygons.flat()).length).toBeGreaterThan(0)
  })

  it('closes Antarctica through the pole instead of drawing a line across the map', () => {
    const polygons = buildLandFill(-MAX, MAX, { splitAtAntimeridian: true }).geometry.coordinates
    const antarctica = polygons.find((poly) => poly[0].some((p) => p[1] === -MAX))
    const lons = antarctica[0].map((p) => p[0])
    expect(Math.min(...lons)).toBeCloseTo(-180, 0)
    expect(Math.max(...lons)).toBeCloseTo(180, 0)
    expect(antarctica).toHaveLength(1)
  })

  it('does not draw coastline segments across the whole world', () => {
    const lines = buildCoastline(-MAX, MAX, { splitAtAntimeridian: true }).geometry.coordinates
    expect(jumps(lines)).toEqual([])
  })
})
