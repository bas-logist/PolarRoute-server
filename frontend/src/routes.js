// Adapters between the API's route payloads and what the UI shows.
//
// GET /api/recent_routes   -> { routes: [{ id, status, job_id, requested, start_name, end_name, tags, mesh, ... }] }
// GET /api/route/<id>      -> { routes: [{ type, name, path, optimisation: { metrics }, mesh, info, ... }], error?, tags }

export const ROUTE_TYPE_LABELS = { traveltime: 'Travel time', fuel: 'Fuel' }

export const routeTypeLabel = (type) => ROUTE_TYPE_LABELS[type] || type

// Same wording as the server uses for route names
export const routeLabel = (startName, endName) => `${startName || 'Start'} to ${endName || 'End'}`

// One entry of /api/recent_routes, shaped for the Recent and Jobs lists.
export function recentRouteView(route) {
  return {
    id: route.id,
    name: routeLabel(route.start_name, route.end_name),
    status: route.status || 'UNKNOWN',
    jobId: route.job_id || null,
    requested: route.requested || null,
    tags: route.tags || [],
    meshName: route.mesh?.name || null,
  }
}

export const routesOf = (response) => response?.routes || []

// Name shared by all routes of one request, e.g. "Rothera to Punta Arenas" from "Rothera to Punta Arenas (fuel)"
export function baseRouteName(routes) {
  const name = routes[0]?.name
  return name ? name.replace(/\s*\((traveltime|fuel)\)$/, '') : null
}

export function formatDuration(days) {
  const value = Number(days)
  if (!Number.isFinite(value)) return null
  return `${value.toFixed(1)} days (${Math.round(value * 24)} hrs)`
}

// Server-side notes about a route (info is an object such as { warning }, { info } or { error }, or a string)
export function routeNotes(route) {
  const info = route?.info
  if (!info) return []
  if (typeof info === 'string') return [{ kind: 'info', text: info }]
  return Object.entries(info).map(([kind, text]) => ({ kind, text: String(text) }))
}

// Display values for the results card; null where the API gave no figure.
export function summariseRoute(route) {
  const metrics = route?.optimisation?.metrics || {}
  const distance = metrics.distance
  const fuel = metrics.fuelConsumption

  let distanceText = null
  if (distance && Number.isFinite(Number(distance.value))) {
    distanceText =
      distance.units === 'meters' ? `${(Number(distance.value) / 1000).toFixed(2)} km` : `${Number(distance.value).toFixed(2)} ${distance.units || ''}`.trim()
  }

  return {
    type: route?.type || null,
    distance: distanceText,
    duration: metrics.time ? formatDuration(metrics.time.duration) : null,
    fuel: fuel && Number.isFinite(Number(fuel.value)) ? `${Number(fuel.value).toFixed(2)} ${fuel.units || ''}`.trim() : null,
    mesh: route?.mesh?.name || null,
  }
}
