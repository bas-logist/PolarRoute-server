import { useCallback, useMemo, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { DEFAULT_ENABLED_LAYERS, findAvailableDates, layersForProjection, recentDates, shownDateFor, tileUrlTemplate, toIsoDate } from './seaIce'

const DEFAULT_OPACITY = 0.7

// State for the sea ice overlays: which layers are on, which day is selected and the resulting map overlays.
// The newest day with data is selected until the user picks another. A layer without imagery for the selected
// day shows its newest earlier day instead (e.g. concentration lags the extent layers by a day).
export function useSeaIce(projection) {
  const layers = useMemo(() => layersForProjection(projection), [projection])
  const today = toIsoDate(new Date())

  const queries = useQueries({
    queries: layers.map((layer) => ({
      queryKey: ['seaIceDates', layer.projection, layer.id, today],
      queryFn: () => findAvailableDates(layer, recentDates(new Date(`${today}T00:00:00Z`))),
      staleTime: 30 * 60_000,
      retry: false,
    })),
  })

  // Each projection remembers its own layer choice
  const [enabledByProjection, setEnabledByProjection] = useState({})
  const enabled = enabledByProjection[projection] || DEFAULT_ENABLED_LAYERS[projection] || []
  const [chosenDate, setChosenDate] = useState(null)
  const [opacity, setOpacity] = useState(DEFAULT_OPACITY)

  const datesByLayer = queries.map((q) => q.data || [])
  const dates = [...new Set(datesByLayer.flat())].sort().reverse()
  const date = chosenDate && dates.includes(chosenDate) ? chosenDate : dates[0] || null

  const layerStates = layers.map((layer, i) => ({
    ...layer,
    enabled: enabled.includes(layer.id),
    loading: queries[i].isPending,
    failed: queries[i].isError,
    current: datesByLayer[i].length > 0,
    shownDate: shownDateFor(datesByLayer[i], date),
  }))

  // Serialised so the overlays keep the same identity (and the map keeps its tiles) until something really changes
  const overlayKey = JSON.stringify(
    layerStates
      .filter((layer) => layer.enabled && layer.shownDate)
      .map((layer) => ({
        id: layer.id,
        url: tileUrlTemplate(layer, layer.shownDate),
        maxNativeZoom: layer.maxNativeZoom,
        tileSize: layer.tileSize || 256,
        zoomOffset: layer.zoomOffset || 0,
        minZoom: layer.minZoom || 0,
      })),
  )
  const overlays = useMemo(() => JSON.parse(overlayKey), [overlayKey])

  const toggleLayer = useCallback(
    (id) =>
      setEnabledByProjection((prev) => {
        const current = prev[projection] || DEFAULT_ENABLED_LAYERS[projection] || []
        return { ...prev, [projection]: current.includes(id) ? current.filter((x) => x !== id) : [...current, id] }
      }),
    [projection],
  )

  const dateIndex = date ? dates.indexOf(date) : -1
  const olderDate = dateIndex >= 0 ? dates[dateIndex + 1] || null : null
  const newerDate = dateIndex > 0 ? dates[dateIndex - 1] : null

  return {
    available: layers.length > 0,
    layers: layerStates,
    loading: queries.some((q) => q.isPending),
    failed: queries.length > 0 && queries.every((q) => q.isError),
    dates,
    date,
    latest: dates[0] || null,
    setDate: setChosenDate,
    olderDate,
    newerDate,
    opacity,
    setOpacity,
    toggleLayer,
    overlays,
  }
}
