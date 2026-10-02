export const initialRouteForm = {
  start_lat: '-67.57',
  start_lon: '-68.12',
  start_name: 'Rothera Research Station',
  end_lat: '-53.15',
  end_lon: '-70.91',
  end_name: 'Punta Arenas',
  mesh_id: '',
  force_new_route: false,
  tags: 'archive, SD056',
}

// Form fields hold strings (as typed); map and saved-location updates go through this
// so every coordinate in the form state has the same representation.
export const formatCoordinate = (value) => String(Number(Number(value).toFixed(6)))

export const wrapLongitude = (lon) => ((((lon + 180) % 360) + 360) % 360) - 180

export function pointFromForm(form, prefix) {
  return { lat: parseFloat(form[`${prefix}_lat`]), lon: parseFloat(form[`${prefix}_lon`]) }
}

const sameName = (a, b) => String(a ?? '').trim().toLowerCase() === String(b ?? '').trim().toLowerCase()

export function findSavedLocation(locations, name) {
  const text = String(name ?? '').trim()
  return text ? locations.find((loc) => sameName(loc.name, text)) : undefined
}

// Fills a point from a saved location (name and coordinates together).
export function applySavedLocation(form, prefix, location) {
  return {
    ...form,
    [`${prefix}_name`]: location.name,
    [`${prefix}_lat`]: formatCoordinate(location.lat),
    [`${prefix}_lon`]: formatCoordinate(location.lon),
  }
}

// Once a point has been moved away from a saved location its name no longer describes it, so clear it
// and let the user name the new position. Custom names are left alone.
export function withStaleNameCleared(form, prefix, locations) {
  const saved = findSavedLocation(locations, form[`${prefix}_name`])
  if (!saved) return form
  const { lat, lon } = pointFromForm(form, prefix)
  const moved = !(Math.abs(lat - saved.lat) < 1e-6 && Math.abs(lon - saved.lon) < 1e-6)
  return moved ? { ...form, [`${prefix}_name`]: '' } : form
}

function parseCoordinate(raw, label, min, max, errors, key) {
  const text = String(raw ?? '').trim()
  const value = Number(text)
  if (text === '' || Number.isNaN(value)) {
    errors[key] = `${label} must be a number`
  } else if (value < min || value > max) {
    errors[key] = `${label} must be between ${min} and ${max}`
  }
  return value
}

// Converts the string-valued form into the API request payload, collecting validation errors by field.
export function parseRouteForm(form) {
  const errors = {}
  const start_lat = parseCoordinate(form.start_lat, 'Latitude', -90, 90, errors, 'start_lat')
  const start_lon = parseCoordinate(form.start_lon, 'Longitude', -180, 180, errors, 'start_lon')
  const end_lat = parseCoordinate(form.end_lat, 'Latitude', -90, 90, errors, 'end_lat')
  const end_lon = parseCoordinate(form.end_lon, 'Longitude', -180, 180, errors, 'end_lon')

  let mesh_id = null
  const meshText = String(form.mesh_id ?? '').trim()
  if (meshText !== '') {
    mesh_id = Number(meshText)
    if (!Number.isInteger(mesh_id) || mesh_id < 1) {
      errors.mesh_id = 'Mesh ID must be a positive whole number'
    }
  }

  const payload = {
    start_lat,
    start_lon,
    end_lat,
    end_lon,
    start_name: String(form.start_name ?? '').trim() || null,
    end_name: String(form.end_name ?? '').trim() || null,
    mesh_id,
    force_new_route: Boolean(form.force_new_route),
    tags: String(form.tags ?? '')
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean),
  }

  return { payload, errors, isValid: Object.keys(errors).length === 0 }
}
