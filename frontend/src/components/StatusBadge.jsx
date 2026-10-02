import { statusTone } from '../status'

export default function StatusBadge({ status }) {
  return <span className={`bsk-label bsk-label-${statusTone(status)}`}>{status}</span>
}
