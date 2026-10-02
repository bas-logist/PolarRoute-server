import Card from './Card'
import QueryState from './QueryState'
import StatusBadge from './StatusBadge'
import { useRecentRoutes } from '../api/queries'
import { recentRouteView } from '../routes'

export default function RecentTab({ onLoadRoute }) {
  const query = useRecentRoutes()
  const routes = (query.data?.routes || []).map(recentRouteView)

  return (
    <Card title="Recent Route History">
      <QueryState
        query={query}
        isEmpty={routes.length === 0}
        loadingText="Loading recent routes..."
        emptyText="No recent routes found."
        errorText="Failed to load recent routes."
      >
        {routes.map((r) => (
          <div key={r.id} className="list-item">
            <div className="list-item-header">
              <span className="list-item-title">{r.name}</span>
              <StatusBadge status={r.status} />
            </div>
            <div className="list-item-meta list-item-meta--spaced">Requested: {r.requested ? new Date(r.requested).toLocaleString() : 'unknown'}</div>
            {r.meshName && <div className="list-item-meta">Mesh: {r.meshName}</div>}
            {r.tags.length > 0 && <div className="list-item-meta">Tags: {r.tags.join(', ')}</div>}
            {r.status === 'SUCCESS' && (
              <div className="list-item-actions">
                <button type="button" className="bsk-btn bsk-btn-default bsk-btn-xs" onClick={() => onLoadRoute(r.id)}>
                  Load Route on Map
                </button>
              </div>
            )}
          </div>
        ))}
      </QueryState>
    </Card>
  )
}
