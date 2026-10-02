import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'proj4'
import 'proj4leaflet'
import { buildCoastline, buildLandFill } from '../coastline'
import { arrowPlacements, lineStringsOf } from '../routeArrows'

// Latitude at which Web Mercator ends; clamping land to it leaves no gap at the edge of the map
const MERCATOR_MAX_LAT = 85.0511
// Shown for tiles GIBS has no data for (instead of a broken image)
const BLANK_TILE = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=='

// Distance between direction arrows along a route, in screen pixels
const ARROW_SPACING = 90
const POLAR_EXTENT = 4194304
const polarCrs = (code, def) =>
  new L.Proj.CRS(code, def, {
    origin: [-POLAR_EXTENT, POLAR_EXTENT],
    bounds: L.bounds([-POLAR_EXTENT, -POLAR_EXTENT], [POLAR_EXTENT, POLAR_EXTENT]),
    resolutions: Array.from({ length: 10 }, (_, z) => 16384 / 2 ** z),
  })

const CRS_BY_PROJECTION = {
  mercator: L.CRS.EPSG3857,
  epsg3031: polarCrs('EPSG:3031', '+proj=stere +lat_0=-90 +lat_ts=-71 +lon_0=0 +k=1 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs'),
  epsg3413: polarCrs('EPSG:3413', '+proj=stere +lat_0=90 +lat_ts=70 +lon_0=-45 +k=1 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs'),
}

const VIEW_BY_PROJECTION = {
  mercator: { center: [-65.0, -60.0], zoom: 4 },
  epsg3031: { center: [-90.0, 0.0], zoom: 1 },
  epsg3413: { center: [90.0, -45.0], zoom: 1 },
}

// Bigger pins for touch screens so they are easy to grab and drag
const pinIcon = (letter, colour) => {
  const size = window.matchMedia?.('(pointer: coarse)').matches ? 36 : 24
  return L.divIcon({
    className: 'custom-pin',
    html: `<div style="background:${colour};color:white;border-radius:50%;width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:${Math.round(size / 2)}px;border:2px solid white;box-shadow:0 2px 4px rgba(0,0,0,0.3);">${letter}</div>`,
    iconSize: [size, size],
  })
}

export default function MapView({ startPoint, endPoint, onMapClick, onMarkerDragEnd, routes, overlays, overlayOpacity, mapPickMode, projection }) {
  const mapRef = useRef(null)
  const mapInstanceRef = useRef(null)
  const startMarkerRef = useRef(null)
  const endMarkerRef = useRef(null)
  const handlersRef = useRef({})
  handlersRef.current = { onMapClick, onMarkerDragEnd, mapPickMode }
  const [mapVersion, setMapVersion] = useState(0)

  // Approximate WGS84 to Polar Stereographic conversion for tooltip display
  const formatCoordinates = (lat, lon, proj) => {
    const rad = Math.PI / 180
    if (proj === 'epsg3031') {
      const easting = (6378137 * Math.tan(Math.PI/4 - (lat * rad)/2) * Math.sin(lon * rad)).toFixed(0)
      const northing = (-6378137 * Math.tan(Math.PI/4 - (lat * rad)/2) * Math.cos(lon * rad)).toFixed(0)
      return `EPSG:3031 (X: ${easting}m, Y: ${northing}m)<br/>Lat/Lon: ${lat.toFixed(4)}°, ${lon.toFixed(4)}°`
    } else if (proj === 'epsg3413') {
      const easting = (6378137 * Math.tan(Math.PI/4 + (lat * rad)/2) * Math.sin(lon * rad)).toFixed(0)
      const northing = (-6378137 * Math.tan(Math.PI/4 + (lat * rad)/2) * Math.cos(lon * rad)).toFixed(0)
      return `EPSG:3413 (X: ${easting}m, Y: ${northing}m)<br/>Lat/Lon: ${lat.toFixed(4)}°, ${lon.toFixed(4)}°`
    } else {
      return `EPSG:4326 (WGS84)<br/>Lat: ${lat.toFixed(4)}°, Lon: ${lon.toFixed(4)}°`
    }
  }

  // The CRS cannot change on an existing Leaflet map, so rebuild it per projection
  useEffect(() => {
    const crs = CRS_BY_PROJECTION[projection] || L.CRS.EPSG3857
    const view = VIEW_BY_PROJECTION[projection] || VIEW_BY_PROJECTION.mercator
    const map = L.map(mapRef.current, { crs, minZoom: 0, attributionControl: false }).setView(view.center, view.zoom)
    mapInstanceRef.current = map

    const polar = projection === 'epsg3031' || projection === 'epsg3413'
    const [minLat, maxLat] = projection === 'epsg3031' ? [-90, 0] : projection === 'epsg3413' ? [0, 90] : [-MERCATOR_MAX_LAT, MERCATOR_MAX_LAT]
    // Colours come from CSS (.map-land, .map-coast) so they follow the light/dark theme without rebuilding the map
    L.geoJSON(buildLandFill(minLat, maxLat, { splitAtAntimeridian: !polar }), {
      style: { className: 'map-land', weight: 0.5 },
      interactive: false,
    }).addTo(map)
    L.geoJSON(buildCoastline(minLat, maxLat, { splitAtAntimeridian: !polar }), {
      style: { className: 'map-coast', weight: polar ? 1.2 : 1, fill: false },
      interactive: false,
    }).addTo(map)

    map.on('click', (e) => {
      const { onMapClick: handleClick, mapPickMode: pickMode } = handlersRef.current
      if (pickMode) {
        handleClick(pickMode, e.latlng.lat, e.latlng.wrap().lng)
      }
    })

    // The map container changes size when the layout switches (mobile views, rotation, menus)
    const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => map.invalidateSize())
    resizeObserver?.observe(mapRef.current)

    setMapVersion((v) => v + 1)

    return () => {
      resizeObserver?.disconnect()
      map.remove()
      mapInstanceRef.current = null
      startMarkerRef.current = null
      endMarkerRef.current = null
    }
  }, [projection])

  // Update Start/End markers and tooltips, keeping latitude and longitude invariant across projection changes
  useEffect(() => {
    const map = mapInstanceRef.current
    if (!map) return

    if (startMarkerRef.current) map.removeLayer(startMarkerRef.current)
    if (!isNaN(startPoint.lat) && !isNaN(startPoint.lon)) {
      const coordText = formatCoordinates(startPoint.lat, startPoint.lon, projection)
      const marker = L.marker([startPoint.lat, startPoint.lon], {
        draggable: true,
        icon: pinIcon('S', '#008236'),
      }).addTo(map)

      marker.bindTooltip(`<strong>Start Point (Drag to Move)</strong><br/>${coordText}`, { permanent: false, direction: 'top' })

      marker.on('dragend', (e) => {
        const pos = e.target.getLatLng()
        handlersRef.current.onMarkerDragEnd?.('start', pos.lat, pos.wrap().lng)
      })

      startMarkerRef.current = marker
    }

    if (endMarkerRef.current) map.removeLayer(endMarkerRef.current)
    if (!isNaN(endPoint.lat) && !isNaN(endPoint.lon)) {
      const coordText = formatCoordinates(endPoint.lat, endPoint.lon, projection)
      const marker = L.marker([endPoint.lat, endPoint.lon], {
        draggable: true,
        icon: pinIcon('E', '#c10007'),
      }).addTo(map)

      marker.bindTooltip(`<strong>End Point (Drag to Move)</strong><br/>${coordText}`, { permanent: false, direction: 'top' })

      marker.on('dragend', (e) => {
        const pos = e.target.getLatLng()
        handlersRef.current.onMarkerDragEnd?.('end', pos.lat, pos.wrap().lng)
      })

      endMarkerRef.current = marker
    }
  }, [startPoint.lat, startPoint.lon, endPoint.lat, endPoint.lon, projection, mapVersion])

  // Sea ice (and any other GIBS) tile overlays. They sit in the tile pane, under the land fill and coastline.
  const overlayLayersRef = useRef([])
  const overlayOpacityRef = useRef(overlayOpacity)
  overlayOpacityRef.current = overlayOpacity
  useEffect(() => {
    const map = mapInstanceRef.current
    if (!map || !overlays || overlays.length === 0) return undefined

    const layers = overlays.map((overlay) =>
      L.tileLayer(overlay.url, {
        maxNativeZoom: overlay.maxNativeZoom,
        minZoom: overlay.minZoom,
        tileSize: overlay.tileSize,
        zoomOffset: overlay.zoomOffset,
        opacity: overlayOpacityRef.current,
        noWrap: true,
        errorTileUrl: BLANK_TILE,
      }).addTo(map),
    )
    overlayLayersRef.current = layers

    return () => {
      overlayLayersRef.current = []
      layers.forEach((layer) => {
        if (map.hasLayer(layer)) map.removeLayer(layer)
      })
    }
  }, [overlays, mapVersion])

  useEffect(() => {
    overlayLayersRef.current.forEach((layer) => layer.setOpacity(overlayOpacity))
  }, [overlayOpacity])

  // Draw every route (one per optimisation type) with arrows showing the direction of travel
  useEffect(() => {
    const map = mapInstanceRef.current
    if (!map || !routes || routes.length === 0) return undefined

    const lines = L.featureGroup().addTo(map)
    const arrows = L.layerGroup().addTo(map)
    const drawn = routes.map((route, index) => ({
      type: route.type,
      index,
      latlngs: lineStringsOf(route.path),
    }))

    drawn.forEach(({ type, latlngs }) => {
      latlngs.forEach((line) => L.polyline(line, { className: `map-route map-route--${type}`, weight: 4, interactive: false }).addTo(lines))
    })

    // Arrows are spaced in screen pixels and turned to follow the line as drawn, so they work in every projection
    const drawArrows = () => {
      arrows.clearLayers()
      const margin = 100
      const topLeft = map.containerPointToLayerPoint([-margin, -margin])
      const bottomRight = map.containerPointToLayerPoint(map.getSize().add([margin, margin]))
      const visible = L.bounds(topLeft, bottomRight)

      drawn.forEach(({ type, index, latlngs }) => {
        latlngs.forEach((line) => {
          const points = line.map((ll) => map.latLngToLayerPoint(ll))
          arrowPlacements(points, ARROW_SPACING, ARROW_SPACING / 2 + index * (ARROW_SPACING / 3))
            .filter((p) => visible.contains(L.point(p.x, p.y)))
            .forEach((p) => {
              L.marker(map.layerPointToLatLng([p.x, p.y]), {
                interactive: false,
                keyboard: false,
                icon: L.divIcon({
                  className: 'route-arrow-icon',
                  html: `<svg class="route-arrow route-arrow--${type}" style="transform: rotate(${p.angle.toFixed(1)}deg)" viewBox="0 0 12 12" aria-hidden="true"><path d="M1 1 L11 6 L1 11 L4 6 Z" /></svg>`,
                  iconSize: [18, 18],
                  iconAnchor: [9, 9],
                }),
              }).addTo(arrows)
            })
        })
      })
    }

    drawArrows()
    map.on('moveend zoomend resize', drawArrows)

    try {
      map.invalidateSize()
      const bounds = lines.getBounds()
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [50, 50] })
    } catch (e) {
      console.error(e)
    }

    return () => {
      map.off('moveend zoomend resize', drawArrows)
      if (map.hasLayer(lines)) map.removeLayer(lines)
      if (map.hasLayer(arrows)) map.removeLayer(arrows)
    }
  }, [routes, mapVersion])

  return (
    <div className={`map-container ${mapPickMode ? 'map-container--picking' : ''}`.trim()} style={{ position: 'relative' }}>
      <div ref={mapRef} style={{ width: '100%', height: '100%', zIndex: 1 }} />
    </div>
  )
}
