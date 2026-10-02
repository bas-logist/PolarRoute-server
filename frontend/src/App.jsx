import { useCallback, useEffect, useMemo, useState } from 'react'
import Header from './components/Header'
import Footer from './components/Footer'
import RoutePlannerTab from './components/RoutePlannerTab'
import RecentTab from './components/RecentTab'
import JobsTab from './components/JobsTab'
import VesselTab from './components/VesselTab'
import MapView from './components/MapView'
import MapPickBanner from './components/MapPickBanner'
import RouteLegend from './components/RouteLegend'
import SeaIceControl from './components/SeaIceControl'
import ViewSwitch from './components/ViewSwitch'
import { useJob, useLoadRoute, useLocations, useRequestRoute, useVesselTypes } from './api/queries'
import { useSeaIce } from './useSeaIce'
import { useTheme } from './theme'
import { MOBILE_QUERY, useMediaQuery } from './useMediaQuery'
import { routesOf } from './routes'
import { formatCoordinate, initialRouteForm, pointFromForm, withStaleNameCleared } from './routeForm'

const TABS = [
  { id: 'planner', label: 'Planner', icon: 'fa-route' },
  { id: 'recent', label: 'Recent', icon: 'fa-clock-rotate-left' },
  { id: 'jobs', label: 'Jobs', icon: 'fa-tasks' },
  { id: 'vehicles', label: 'Vessel', icon: 'fa-ship' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('planner')
  const [chosenVessel, setChosenVessel] = useState('')
  const [projection, setProjection] = useState('mercator')
  const [routeForm, setRouteForm] = useState(initialRouteForm)
  const [routeResponse, setRouteResponse] = useState(null)
  const [currentJobId, setCurrentJobId] = useState(null)
  const [mapPickMode, setMapPickMode] = useState(null)
  const [mobileView, setMobileView] = useState('panel')
  const isMobile = useMediaQuery(MOBILE_QUERY)
  const seaIce = useSeaIce(projection)
  const { theme, toggleTheme } = useTheme()

  const locations = useLocations().data || []
  const vesselTypes = useVesselTypes()
  const vessels = vesselTypes.data?.vessel_types?.length ? vesselTypes.data.vessel_types : vesselTypes.isPending ? [] : ['default']
  const selectedVessel = chosenVessel || vessels[0] || ''

  const requestRoute = useRequestRoute()
  const loadRoute = useLoadRoute()
  const job = useJob(currentJobId)
  const routes = useMemo(() => routesOf(routeResponse), [routeResponse])
  const isRouting = currentJobId !== null || requestRoute.isPending

  const { mutate: fetchRoute } = loadRoute
  const handleLoadRouteById = useCallback(
    (routeId) => {
      fetchRoute(routeId, {
        onSuccess: (response) => {
          setRouteResponse(response)
          setMobileView('map')
        },
        onError: () => alert('Failed to load route details.'),
      })
    },
    [fetchRoute],
  )

  // React to the polled job reaching a final state, or disappearing (e.g. cancelled from the Jobs tab).
  useEffect(() => {
    if (!currentJobId) return
    if (job.isError) {
      setCurrentJobId(null)
      return
    }
    const status = job.data?.status
    if (status === 'SUCCESS') {
      setCurrentJobId(null)
      if (job.data.route_id) handleLoadRouteById(job.data.route_id)
    } else if (status === 'FAILURE') {
      setCurrentJobId(null)
      alert('Route calculation failed: ' + (job.data.info?.error || 'Unknown error'))
    } else if (status === 'REVOKED') {
      setCurrentJobId(null)
    }
  }, [currentJobId, job.data, job.isError, handleLoadRouteById])

  // Moves a point; a name that belongs to a saved location is cleared, any custom name is kept
  const movePoint = (type, lat, lon) => {
    setRouteForm((prev) =>
      withStaleNameCleared({ ...prev, [`${type}_lat`]: formatCoordinate(lat), [`${type}_lon`]: formatCoordinate(lon) }, type, locations),
    )
  }

  // On small screens the map is hidden behind the planner, so picking a point switches to the map and
  // returns to the planner when the point is placed or picking is cancelled.
  const handlePickModeChange = useCallback(
    (mode) => {
      setMapPickMode(mode)
      if (isMobile) setMobileView(mode ? 'map' : 'panel')
    },
    [isMobile],
  )

  const handleMapClick = (type, lat, lon) => {
    movePoint(type, lat, lon)
    handlePickModeChange(null)
  }

  // Escape cancels picking a point on the map
  useEffect(() => {
    if (!mapPickMode) return undefined
    const onKeyDown = (e) => {
      if (e.key === 'Escape') handlePickModeChange(null)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [mapPickMode, handlePickModeChange])

  const handleCalculateRoute = (payload) => {
    setActiveTab('jobs')
    requestRoute.mutate(payload, {
      onSuccess: (data) => {
        if (data?.id) setCurrentJobId(data.id)
        else alert('Error: Failed to accept route request')
      },
      onError: (err) => alert('Error: ' + err.message),
    })
  }

  const renderTab = () => {
    switch (activeTab) {
      case 'planner':
        return <RoutePlannerTab routeForm={routeForm} setRouteForm={setRouteForm} onCalculate={handleCalculateRoute}
            routeResponse={routeResponse}
            mapPickMode={mapPickMode}
            onMapPickModeChange={handlePickModeChange}
          />
      case 'recent':
        return <RecentTab onLoadRoute={handleLoadRouteById} />
      case 'jobs':
        return <JobsTab onLoadRoute={handleLoadRouteById} />
      case 'vehicles':
        return <VesselTab selectedVessel={selectedVessel} />
      default:
        return null
    }
  }

  return (
    <div className="app-shell">
      <Header
        vessels={vessels}
        selectedVessel={selectedVessel}
        onSelectVessel={setChosenVessel}
        projection={projection}
        onSelectProjection={setProjection}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      <div className="main-container" data-mobile-view={mobileView}>
        <aside className="sidebar">
          <div className="bsk-tabs-nav">
            <nav className="bsk-tabs sidebar-tabs" role="tablist" aria-label="Sidebar sections">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  id={`tab-${tab.id}`}
                  type="button"
                  role="tab"
                  className="bsk-tab-btn"
                  aria-selected={activeTab === tab.id}
                  aria-controls="sidebar-panel"
                  onClick={() => setActiveTab(tab.id)}
                >
                  <i className={`fa-solid ${tab.icon} fa-fw`} aria-hidden="true"></i> {tab.label}
                  {tab.id === 'jobs' && isRouting && (
                    <>
                      <span className="tab-busy-dot" aria-hidden="true">
                        {' '}
                        ●
                      </span>
                      <span className="sr-only"> (route calculation in progress)</span>
                    </>
                  )}
                </button>
              ))}
            </nav>
          </div>

          <div id="sidebar-panel" role="tabpanel" aria-labelledby={`tab-${activeTab}`} className="sidebar-content">
            {renderTab()}
          </div>
        </aside>

        <main className="map-pane" aria-label="Map">
          <div className="map-overlays">
            <SeaIceControl key={projection} seaIce={seaIce} startMinimised={isMobile} />
            <RouteLegend routes={routes} />
          </div>
          <MapPickBanner mode={mapPickMode} onCancel={() => handlePickModeChange(null)} />
          <MapView
            startPoint={pointFromForm(routeForm, 'start')}
            endPoint={pointFromForm(routeForm, 'end')}
            onMapClick={handleMapClick}
            onMarkerDragEnd={movePoint}
            mapPickMode={mapPickMode}
            routes={routes}
            overlays={seaIce.overlays}
            overlayOpacity={seaIce.opacity}
            projection={projection}
          />
        </main>
      </div>

      <ViewSwitch view={mobileView} onChange={setMobileView} />

      <Footer />
    </div>
  )
}
