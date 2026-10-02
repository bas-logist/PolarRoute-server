import { describe, expect, it } from 'vitest'
import { arrowPlacements, lineStringsOf } from './routeArrows'

describe('lineStringsOf', () => {
  const line = { type: 'LineString', coordinates: [[-68, -67], [-60, -60]] }

  it('swaps GeoJSON [lon, lat] into [lat, lon]', () => {
    expect(lineStringsOf({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: line }] })).toEqual([
      [[-67, -68], [-60, -60]],
    ])
  })

  it('handles features, bare geometries and multi-line geometries', () => {
    expect(lineStringsOf({ type: 'Feature', geometry: line })).toHaveLength(1)
    expect(lineStringsOf(line)).toHaveLength(1)
    expect(lineStringsOf({ type: 'MultiLineString', coordinates: [line.coordinates, line.coordinates] })).toHaveLength(2)
  })

  it('ignores points, empty paths and missing geometry', () => {
    expect(lineStringsOf(null)).toEqual([])
    expect(lineStringsOf({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] } }, { type: 'Feature', geometry: null }] })).toEqual([])
  })
})

describe('arrowPlacements', () => {
  it('places arrows at regular distances in the direction of travel', () => {
    const arrows = arrowPlacements([{ x: 0, y: 0 }, { x: 100, y: 0 }], 40, 20)
    expect(arrows.map((a) => a.x)).toEqual([20, 60, 100])
    expect(arrows.every((a) => a.y === 0 && a.angle === 0)).toBe(true)
  })

  it('points the arrow along each segment, including across corners', () => {
    const arrows = arrowPlacements([{ x: 0, y: 0 }, { x: 50, y: 0 }, { x: 50, y: 50 }], 50, 25)
    expect(arrows).toHaveLength(2)
    expect(arrows[0]).toMatchObject({ x: 25, y: 0, angle: 0 })
    expect(arrows[1].x).toBeCloseTo(50)
    expect(arrows[1].y).toBeCloseTo(25)
    expect(arrows[1].angle).toBeCloseTo(90)
  })

  it('reverses the angle when the route runs the other way', () => {
    const [arrow] = arrowPlacements([{ x: 100, y: 0 }, { x: 0, y: 0 }], 80, 40)
    expect(Math.abs(arrow.angle)).toBeCloseTo(180)
  })

  it('skips repeated points and refuses a non-positive spacing', () => {
    expect(arrowPlacements([{ x: 0, y: 0 }, { x: 0, y: 0 }], 10)).toEqual([])
    expect(arrowPlacements([{ x: 0, y: 0 }, { x: 10, y: 0 }], 0)).toEqual([])
  })
})
