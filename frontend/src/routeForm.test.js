import { describe, expect, it } from 'vitest'
import {
  applySavedLocation,
  findSavedLocation,
  formatCoordinate,
  initialRouteForm,
  parseRouteForm,
  pointFromForm,
  withStaleNameCleared,
  wrapLongitude,
} from './routeForm'

describe('parseRouteForm', () => {
  it('converts the default form into a numeric API payload', () => {
    const { payload, errors, isValid } = parseRouteForm(initialRouteForm)
    expect(isValid).toBe(true)
    expect(errors).toEqual({})
    expect(payload).toMatchObject({
      start_lat: -67.57,
      start_lon: -68.12,
      end_lat: -53.15,
      end_lon: -70.91,
      mesh_id: null,
      force_new_route: false,
      tags: ['archive', 'SD056'],
    })
  })

  it('reports out of range and non-numeric coordinates by field', () => {
    const { errors, isValid } = parseRouteForm({ ...initialRouteForm, start_lat: '-95', end_lon: '', start_lon: '181', end_lat: 'abc' })
    expect(isValid).toBe(false)
    expect(Object.keys(errors).sort()).toEqual(['end_lat', 'end_lon', 'start_lat', 'start_lon'])
  })

  it('accepts an empty mesh id and rejects invalid ones', () => {
    expect(parseRouteForm({ ...initialRouteForm, mesh_id: '' }).payload.mesh_id).toBeNull()
    expect(parseRouteForm({ ...initialRouteForm, mesh_id: '12' }).payload.mesh_id).toBe(12)
    expect(parseRouteForm({ ...initialRouteForm, mesh_id: '1.5' }).errors.mesh_id).toBeDefined()
    expect(parseRouteForm({ ...initialRouteForm, mesh_id: '0' }).errors.mesh_id).toBeDefined()
  })

  it('sends blank point names as null', () => {
    const { payload } = parseRouteForm({ ...initialRouteForm, start_name: '  ', end_name: ' Punta Arenas ' })
    expect(payload.start_name).toBeNull()
    expect(payload.end_name).toBe('Punta Arenas')
  })

  it('drops empty tags', () => {
    expect(parseRouteForm({ ...initialRouteForm, tags: ' a, ,b ,' }).payload.tags).toEqual(['a', 'b'])
  })
})

describe('coordinate helpers', () => {
  it('formats coordinates to at most 6 decimal places', () => {
    expect(formatCoordinate(-67.123456789)).toBe('-67.123457')
    expect(formatCoordinate(10)).toBe('10')
  })

  it('wraps longitudes into [-180, 180)', () => {
    expect(wrapLongitude(190)).toBe(-170)
    expect(wrapLongitude(-190)).toBe(170)
    expect(wrapLongitude(45)).toBe(45)
  })

  it('reads a point from the form, giving NaN for blank fields', () => {
    expect(pointFromForm({ start_lat: '1.5', start_lon: '' }, 'start')).toEqual({ lat: 1.5, lon: NaN })
  })
})

describe('saved locations', () => {
  const locations = [
    { id: 1, name: 'Rothera Research Station', lat: -67.57, lon: -68.12 },
    { id: 2, name: 'Punta Arenas', lat: -53.15, lon: -70.91 },
  ]

  it('finds a saved location by name, ignoring case and whitespace', () => {
    expect(findSavedLocation(locations, ' punta arenas ')?.id).toBe(2)
    expect(findSavedLocation(locations, 'Nowhere')).toBeUndefined()
    expect(findSavedLocation(locations, '')).toBeUndefined()
  })

  it('applies name and coordinates together', () => {
    const form = applySavedLocation(initialRouteForm, 'end', locations[0])
    expect(form).toMatchObject({ end_name: 'Rothera Research Station', end_lat: '-67.57', end_lon: '-68.12' })
  })

  it('clears a saved name once the point has moved away from that location', () => {
    const moved = { ...initialRouteForm, start_lat: '-60' }
    expect(withStaleNameCleared(moved, 'start', locations).start_name).toBe('')
  })

  it('keeps a saved name while the coordinates still match, and keeps custom names', () => {
    expect(withStaleNameCleared(initialRouteForm, 'start', locations)).toBe(initialRouteForm)
    const custom = { ...initialRouteForm, start_name: 'My camp', start_lat: '-60' }
    expect(withStaleNameCleared(custom, 'start', locations)).toBe(custom)
  })
})
