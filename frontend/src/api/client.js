export class ApiError extends Error {
  constructor(message, { status, body } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  let data = null
  try {
    data = await res.json()
  } catch {
    // Empty or non-JSON body
  }

  if (!res.ok) {
    throw new ApiError(data?.error || `Request failed with status ${res.status}`, { status: res.status, body: data })
  }
  return data
}

export const getVesselTypes = () => request('/api/vehicle/available')
export const getVehicle = (vesselType) => request(`/api/vehicle/${encodeURIComponent(vesselType)}/`)
export const getLocations = () => request('/api/locations/')
export const getRecentRoutes = () => request('/api/recent_routes')
export const getRoute = (routeId) => request(`/api/route/${routeId}`)
export const requestRoute = (payload) => request('/api/route', { method: 'POST', body: payload })
export const getJob = (jobId) => request(`/api/job/${jobId}`)
export const cancelJob = (jobId) => request(`/api/job/${jobId}`, { method: 'DELETE' })
