import { feature } from 'topojson-client'
import land from 'world-atlas/land-50m.json'

const landGeoJson = feature(land, land.objects.land)

const isPolarEdge = (a, b) => Math.abs(a[1]) > 89.9 && Math.abs(b[1]) > 89.9
const isAntimeridianEdge = (a, b) => Math.abs(a[0]) > 179.99 && Math.abs(b[0]) > 179.99 && Math.sign(a[0]) === Math.sign(b[0])

const landPolygons = () => {
  const geoms = landGeoJson.type === 'FeatureCollection' ? landGeoJson.features.map((f) => f.geometry) : [landGeoJson.geometry]
  return geoms.flatMap((g) => (g.type === 'Polygon' ? [g.coordinates] : g.coordinates))
}

const isDegeneratePolarRing = (ring) => ring.every((p) => Math.abs(p[1]) > 89)

// Keeps the part of a polygon on one side of a vertical line (Sutherland-Hodgman).
function clipToLongitude(points, edge, keepGreater) {
  const inside = (p) => (keepGreater ? p[0] >= edge : p[0] <= edge)
  const cross = (a, b) => [edge, a[1] + ((edge - a[0]) / (b[0] - a[0])) * (b[1] - a[1])]
  const out = []
  points.forEach((cur, i) => {
    const prev = points[(i + points.length - 1) % points.length]
    if (inside(cur)) {
      if (!inside(prev)) out.push(cross(prev, cur))
      out.push(cur)
    } else if (inside(prev)) {
      out.push(cross(prev, cur))
    }
  })
  return out
}

// A flat map repeats longitudes at +/-180, so the few polygons that straddle the antimeridian are stored with
// a jump between +180 and -180 which would otherwise be drawn as a line (and fill) across the whole world.
// This rebuilds such a ring with continuous longitudes and cuts it into pieces that fit within [-180, 180].
// Rings that circle the globe (Antarctica) are closed through the pole.
function splitRing(ring) {
  const open = ring.slice(0, -1)
  const unwrapped = [open[0]]
  let offset = 0
  for (let i = 1; i < open.length; i++) {
    const delta = open[i][0] - open[i - 1][0]
    if (delta > 180) offset -= 360
    else if (delta < -180) offset += 360
    unwrapped.push([open[i][0] + offset, open[i][1]])
  }

  const first = unwrapped[0]
  const last = unwrapped[unwrapped.length - 1]
  const circlesGlobe = Math.abs(first[0] - last[0]) > 180
  if (circlesGlobe) {
    const meanLat = unwrapped.reduce((sum, p) => sum + p[1], 0) / unwrapped.length
    const poleLat = meanLat < 0 ? -90 : 90
    unwrapped.push([last[0], poleLat], [first[0], poleLat])
  }

  return [-360, 0, 360]
    .map((shift) => {
      const shifted = unwrapped.map(([lon, lat]) => [lon + shift, lat])
      return clipToLongitude(clipToLongitude(shifted, -180, true), 180, false)
    })
    .filter((piece) => piece.length >= 3)
    .map((piece) => [...piece, piece[0]])
}

const ringHasJump = (ring) => ring.some((p, i) => i > 0 && Math.abs(p[0] - ring[i - 1][0]) > 180)

// Builds a MultiPolygon of the land for shading. Polygons wholly outside the latitude range are dropped
// and latitudes of the rest are clamped to it, which approximates clipping and keeps points such as
// the opposite pole (infinite in a polar stereographic projection) out of the projection.
// Set splitAtAntimeridian for flat world maps (Mercator).
export function buildLandFill(minLat, maxLat, { splitAtAntimeridian = false } = {}) {
  const clamp = (lat) => Math.min(maxLat, Math.max(minLat, lat))
  const clampRing = (ring) => ring.map(([lon, lat]) => [lon, clamp(lat)])

  const polygons = landPolygons()
    .filter((poly) => poly[0].some((p) => p[1] >= minLat && p[1] <= maxLat))
    .flatMap((poly) => {
      if (!splitAtAntimeridian || !ringHasJump(poly[0])) return [poly.map(clampRing)]
      const holes = poly.slice(1).filter((ring) => !isDegeneratePolarRing(ring))
      const pieces = splitRing(poly[0])
      return pieces.map((piece) => [clampRing(piece), ...(pieces.length === 1 ? holes.map(clampRing) : [])])
    })

  return { type: 'Feature', properties: {}, geometry: { type: 'MultiPolygon', coordinates: polygons } }
}

// Builds a MultiLineString of the land outlines, dropping the artificial edges
// from clipping at the poles/antimeridian and any points outside the lat range.
export function buildCoastline(minLat, maxLat, { splitAtAntimeridian = false } = {}) {
  const lines = []
  const rings = []
  const geoms = landGeoJson.type === 'FeatureCollection' ? landGeoJson.features.map((f) => f.geometry) : [landGeoJson.geometry]
  geoms.forEach((g) => {
    const polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates
    polys.forEach((poly) => poly.forEach((ring) => rings.push(ring)))
  })

  const inRange = (p) => p[1] >= minLat && p[1] <= maxLat

  rings.forEach((ring) => {
    let current = []
    const flush = () => {
      if (current.length > 1) lines.push(current)
      current = []
    }
    for (let i = 0; i < ring.length; i++) {
      const p = ring[i]
      if (!inRange(p)) {
        flush()
        continue
      }
      if (current.length) {
        const prev = current[current.length - 1]
        if (isPolarEdge(prev, p) || isAntimeridianEdge(prev, p) || (splitAtAntimeridian && Math.abs(p[0] - prev[0]) > 180)) flush()
      }
      current.push(p)
    }
    flush()
  })

  return { type: 'Feature', properties: {}, geometry: { type: 'MultiLineString', coordinates: lines } }
}
