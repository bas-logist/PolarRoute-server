// Sea ice overlays from NASA GIBS (https://nasa-gibs.github.io/gibs-api-docs/).
//
// Only layers whose time range runs up to the present day are listed (checked against the "best" WMTS
// capabilities of each projection):
//  - concentration: the GHRSST L4 analyses, served in Web Mercator only. The AMSR2 and SSMIS concentration
//    layers stopped in 2025 and 2021, so the polar projections have no current concentration layer.
//  - extent: the MODIS (Aqua, Terra) and VIIRS (NOAA-20, Suomi NPP) sea ice layers, in all three projections.
//    They only draw where sea ice is detected (cloud-free daylight scenes); everything else is transparent.
// Availability is still checked at runtime (see findAvailableDates), so a layer that stops being updated is
// disabled automatically.

export const GIBS_WMTS_URL = 'https://gibs.earthdata.nasa.gov/wmts'

// Tile layouts per GIBS projection. Polar tiles are 512 px and start at GIBS level 0 = 8192 m/px, which is
// zoom 1 of the polar CRSs in MapView, hence zoomOffset -1.
const MERCATOR_L7 = { tileMatrixSet: 'GoogleMapsCompatible_Level7', maxNativeZoom: 7 }
const MERCATOR_L6 = { tileMatrixSet: 'GoogleMapsCompatible_Level6', maxNativeZoom: 6 }
const POLAR_1KM = { tileMatrixSet: '1km', maxNativeZoom: 4, tileSize: 512, zoomOffset: -1, minZoom: 1 }
const EXTENT_SPECS = { epsg3857: MERCATOR_L7, epsg3031: POLAR_1KM, epsg3413: POLAR_1KM }

export const LAYER_KINDS = [
  { id: 'concentration', title: 'Concentration' },
  { id: 'extent', title: 'Extent' },
]

export const SEA_ICE_LAYERS = [
  {
    id: 'GHRSST_L4_MUR_Sea_Ice_Concentration',
    kind: 'concentration',
    name: 'MUR',
    detail: 'GHRSST L4, high resolution',
    specs: { epsg3857: MERCATOR_L7 },
  },
  {
    id: 'GHRSST_L4_MUR25_Sea_Ice_Concentration',
    kind: 'concentration',
    name: 'MUR25',
    detail: 'GHRSST L4, 0.25° grid',
    specs: { epsg3857: MERCATOR_L6 },
  },
  { id: 'MODIS_Terra_Sea_Ice', kind: 'extent', name: 'MODIS Terra', detail: 'daily, 1 km', specs: EXTENT_SPECS },
  { id: 'MODIS_Aqua_Sea_Ice', kind: 'extent', name: 'MODIS Aqua', detail: 'daily, 1 km', specs: EXTENT_SPECS },
  { id: 'VIIRS_NOAA20_Sea_Ice', kind: 'extent', name: 'VIIRS NOAA-20', detail: 'daily', specs: EXTENT_SPECS },
  { id: 'VIIRS_SNPP_Sea_Ice', kind: 'extent', name: 'VIIRS Suomi NPP', detail: 'daily', specs: EXTENT_SPECS },
]

// Layers on the first time the map is shown in each projection: concentration where there is one, otherwise extent
export const DEFAULT_ENABLED_LAYERS = {
  mercator: ['GHRSST_L4_MUR_Sea_Ice_Concentration'],
  epsg3031: ['MODIS_Terra_Sea_Ice'],
  epsg3413: ['MODIS_Terra_Sea_Ice'],
}

// How many days (today included) to offer, newest first
export const DAYS_TO_OFFER = 14

// The app's projection ids -> GIBS projection ids
const GIBS_PROJECTION = { mercator: 'epsg3857', epsg3031: 'epsg3031', epsg3413: 'epsg3413' }

// The layers GIBS serves in an app projection, with that projection's tile layout merged in
export function layersForProjection(projection) {
  const gibsProjection = GIBS_PROJECTION[projection]
  return SEA_ICE_LAYERS.filter((layer) => layer.specs[gibsProjection]).map((layer) => ({ ...layer, projection: gibsProjection, ...layer.specs[gibsProjection] }))
}

const tilePath = (layer, date) => `${GIBS_WMTS_URL}/${layer.projection}/best/${layer.id}/default/${date}/${layer.tileMatrixSet}`

// Leaflet tile URL template for one layer on one day
export const tileUrlTemplate = (layer, date) => `${tilePath(layer, date)}/{z}/{y}/{x}.png`

// The single world tile, used to ask GIBS whether a day exists (days without data return 404)
export const probeUrl = (layer, date) => `${tilePath(layer, date)}/0/0/0.png`

export const toIsoDate = (date) => date.toISOString().slice(0, 10)

// ['2026-10-02', '2026-10-01', ...] counting back from `today` (UTC, like GIBS)
export function recentDates(today, count = DAYS_TO_OFFER) {
  return Array.from({ length: count }, (_, i) => toIsoDate(new Date(today.getTime() - i * 86_400_000)))
}

// The subset of `dates` that GIBS has imagery for, newest first.
export async function findAvailableDates(layer, dates, fetchFn = fetch) {
  const checks = await Promise.all(
    dates.map(async (date) => {
      try {
        const response = await fetchFn(probeUrl(layer, date), { method: 'HEAD' })
        return response.ok ? date : null
      } catch {
        return null
      }
    }),
  )
  return checks.filter(Boolean)
}

export function formatDay(isoDate, locale) {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString(locale, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
}

export function formatShortDay(isoDate, locale) {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString(locale, { day: 'numeric', month: 'short', timeZone: 'UTC' })
}

// Colour scale of GIBS' GHRSST_Sea_Ice_Concentration colormap, sampled every 10 %
const COLOUR_SCALE = [
  [0, '17,17,17'],
  [10, '163,0,163'],
  [20, '177,0,255'],
  [30, '7,0,255'],
  [40, '0,189,255'],
  [50, '0,217,142'],
  [60, '30,180,0'],
  [70, '210,240,0'],
  [80, '255,127,0'],
  [90, '255,51,51'],
  [100, '255,255,255'],
]

export const COLOUR_SCALE_GRADIENT = `linear-gradient(to right, ${COLOUR_SCALE.map(([pct, rgb]) => `rgb(${rgb}) ${pct}%`).join(', ')})`

// Colour GIBS draws sea ice in for the extent layers (MODIS_L2_Sea_Ice colormap)
export const EXTENT_ICE_COLOUR = 'rgb(255,100,100)'

// The day of imagery to show for a selected day: the newest one the layer has on or before it
export const shownDateFor = (layerDates, selected) => (selected ? layerDates.find((d) => d <= selected) || null : null)
