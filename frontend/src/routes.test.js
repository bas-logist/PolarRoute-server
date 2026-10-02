import { describe, expect, it } from 'vitest'
import { baseRouteName, formatDuration, recentRouteView, routeNotes, routesOf, summariseRoute } from './routes'

// Shapes taken from the server's own tests (tests/test_views.py, tests/test_serializers.py)
const line = (objective) => ({
  type: 'FeatureCollection',
  features: [{ type: 'Feature', properties: { objective_function: objective }, geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] } }],
})

const routeResponse = {
  routes: [
    {
      type: 'traveltime',
      id: '7',
      name: 'KEP to Halley (traveltime)',
      path: line('traveltime'),
      optimisation: { metrics: { time: { duration: '24.0' }, distance: { value: 1234567, units: 'meters' } } },
      mesh: { id: 1, name: 'Test Mesh' },
    },
    {
      type: 'fuel',
      id: '7',
      name: 'KEP to Halley (fuel)',
      path: line('fuel'),
      optimisation: { metrics: { fuelConsumption: { value: 100.5, units: 'kg' } } },
      info: { warning: 'Smoothing failed for fuel-optimisation, returning unsmoothed route.' },
    },
  ],
  tags: [],
  'polarrouteserver-version': '1.0.0',
}

const recentRoute = {
  id: 7,
  start_lat: -54.3,
  start_lon: -36.5,
  end_lat: -75.1,
  end_lon: -26.7,
  start_name: 'KEP',
  end_name: 'Halley',
  requested: '2026-10-02T09:00:00Z',
  calculated: '2026-10-02T09:05:00Z',
  status: 'SUCCESS',
  route_url: 'http://testserver/api/route/7',
  job_id: 'c0ffee00-0000-4000-8000-000000000001',
  job_status_url: 'http://testserver/api/job/c0ffee00-0000-4000-8000-000000000001',
  tags: ['archive'],
  mesh: { id: 1, name: 'Test Mesh' },
}

describe('recentRouteView', () => {
  it('reads status, job id and created time from the flat recent_routes item', () => {
    expect(recentRouteView(recentRoute)).toEqual({
      id: 7,
      name: 'KEP to Halley',
      status: 'SUCCESS',
      jobId: 'c0ffee00-0000-4000-8000-000000000001',
      requested: '2026-10-02T09:00:00Z',
      tags: ['archive'],
      meshName: 'Test Mesh',
    })
  })

  it('copes with unnamed points and routes without a job or mesh', () => {
    const view = recentRouteView({ id: 8, start_name: null, end_name: null, status: 'PENDING', requested: '2026-10-02T09:00:00Z' })
    expect(view).toMatchObject({ name: 'Start to End', status: 'PENDING', jobId: null, meshName: null, tags: [] })
  })

  it('only reports UNKNOWN when the API gives no status at all', () => {
    expect(recentRouteView({ id: 9 }).status).toBe('UNKNOWN')
  })
})

describe('route detail response', () => {
  it('lists the routes of every optimisation type', () => {
    expect(routesOf(routeResponse)).toHaveLength(2)
    expect(routesOf(null)).toEqual([])
    expect(routesOf({ routes: [], error: 'No routes available for any optimisation type.' })).toEqual([])
  })

  it('exposes the GeoJSON path of each route for the map', () => {
    expect(routesOf(routeResponse).map((route) => route.path.features[0].geometry.type)).toEqual(['LineString', 'LineString'])
  })

  it('names the request after the points, without the optimisation type', () => {
    expect(baseRouteName(routeResponse.routes)).toBe('KEP to Halley')
    expect(baseRouteName([])).toBeNull()
  })

  it('summarises distance, duration and fuel from the metrics', () => {
    expect(summariseRoute(routeResponse.routes[0])).toMatchObject({ distance: '1234.57 km', duration: '24.0 days (576 hrs)', fuel: null, mesh: 'Test Mesh', type: 'traveltime' })
    expect(summariseRoute(routeResponse.routes[1])).toMatchObject({ distance: null, duration: null, fuel: '100.50 kg' })
  })

  it('returns server notes for display', () => {
    expect(routeNotes(routeResponse.routes[1])).toEqual([{ kind: 'warning', text: 'Smoothing failed for fuel-optimisation, returning unsmoothed route.' }])
    expect(routeNotes(routeResponse.routes[0])).toEqual([])
    expect(routeNotes({ info: 'plain text' })).toEqual([{ kind: 'info', text: 'plain text' }])
  })
})

describe('formatDuration', () => {
  it('formats decimal days and ignores non-numeric values', () => {
    expect(formatDuration('2.5')).toBe('2.5 days (60 hrs)')
    expect(formatDuration('n/a')).toBeNull()
  })
})
