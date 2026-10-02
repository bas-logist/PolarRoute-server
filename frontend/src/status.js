// Celery task states reported by the job status API.
export const TERMINAL_STATUSES = ['SUCCESS', 'FAILURE', 'REVOKED']

export const isTerminalStatus = (status) => TERMINAL_STATUSES.includes(status)
export const isActiveStatus = (status) => status === 'PENDING' || status === 'STARTED'

// Style Kit contextual tone for a status: success / info (in progress) / danger / default (unknown).
// Drives the label and list-item accent colours; the status text is always shown as well.
export function statusTone(status) {
  if (status === 'SUCCESS') return 'success'
  if (isActiveStatus(status)) return 'info'
  if (status === 'FAILURE' || status === 'REVOKED') return 'danger'
  return 'default'
}
