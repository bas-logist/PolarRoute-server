import Card from './Card'
import QueryState from './QueryState'
import StatusBadge from './StatusBadge'
import { useCancelJob, useRecentRoutes } from '../api/queries'
import { recentRouteView } from '../routes'
import { isActiveStatus, statusTone } from '../status'

const JOBS_POLL_INTERVAL_MS = 3000

export default function JobsTab({ onLoadRoute }) {
  // Only mounted while the tab is visible, so polling stops when the user leaves it.
  const query = useRecentRoutes({ refetchInterval: JOBS_POLL_INTERVAL_MS })
  const cancelJob = useCancelJob()
  const jobs = (query.data?.routes || []).map(recentRouteView)

  const handleCancelJob = (jobId) => {
    cancelJob.mutate(jobId, {
      onSuccess: () => alert('Job cancellation requested.'),
      onError: () => alert('Failed to cancel job.'),
    })
  }

  return (
    <Card title="Active & Pending Jobs" icon="fa-tasks">
      <p className="card-hint">Monitor long-running route optimization tasks and background job statuses.</p>
      <QueryState
        query={query}
        isEmpty={jobs.length === 0}
        loadingText="Loading jobs..."
        emptyText="No jobs found."
        errorText="Failed to load jobs."
      >
        {jobs.map((r) => {
          const status = r.status

          return (
            <div key={r.id} className={`list-item list-item--${statusTone(status)}`}>
              <div className="list-item-header">
                <span className="list-item-title">{r.name}</span>
                <StatusBadge status={status} />
              </div>
              <div className="list-item-meta list-item-meta--spaced">
                Job ID: <code>{r.jobId || 'none'}</code>
              </div>
              <div className="list-item-meta">Requested: {r.requested ? new Date(r.requested).toLocaleString() : 'unknown'}</div>
              <div className="list-item-actions">
                {status === 'SUCCESS' && (
                  <button type="button" className="bsk-btn bsk-btn-default bsk-btn-xs" onClick={() => onLoadRoute(r.id)}>
                    View Result on Map
                  </button>
                )}
                {isActiveStatus(status) && r.jobId && (
                  <button
                    type="button"
                    className="bsk-btn bsk-btn-danger bsk-btn-xs"
                    disabled={cancelJob.isPending}
                    onClick={() => handleCancelJob(r.jobId)}
                  >
                    Cancel Job
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </QueryState>
    </Card>
  )
}
