// Helpers for drawing a route and its direction of travel on the map.

// LineString coordinates of a route's GeoJSON path as [[lat, lon], ...] lists (GeoJSON itself is [lon, lat]).
export function lineStringsOf(geojson) {
  if (!geojson) return []
  const geometries =
    geojson.type === 'FeatureCollection' ? geojson.features.map((f) => f.geometry) : geojson.type === 'Feature' ? [geojson.geometry] : [geojson]

  return geometries
    .filter(Boolean)
    .flatMap((g) => (g.type === 'LineString' ? [g.coordinates] : g.type === 'MultiLineString' ? g.coordinates : []))
    .map((line) => line.map(([lon, lat]) => [lat, lon]))
    .filter((line) => line.length > 1)
}

// Points at regular distances along a polyline given in screen coordinates, each with the direction (degrees,
// 0 = pointing right, clockwise on screen) of the segment it sits on. The first arrow is `offset` along the line.
export function arrowPlacements(points, spacing, offset = spacing / 2) {
  if (!(spacing > 0)) return []
  const placements = []
  let next = offset
  let travelled = 0

  for (let i = 1; i < points.length; i++) {
    const dx = points[i].x - points[i - 1].x
    const dy = points[i].y - points[i - 1].y
    const length = Math.hypot(dx, dy)
    if (length === 0) continue
    const angle = (Math.atan2(dy, dx) * 180) / Math.PI
    while (next <= travelled + length) {
      const t = (next - travelled) / length
      placements.push({ x: points[i - 1].x + dx * t, y: points[i - 1].y + dy * t, angle })
      next += spacing
    }
    travelled += length
  }
  return placements
}
