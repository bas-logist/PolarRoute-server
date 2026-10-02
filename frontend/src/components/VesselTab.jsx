import Card from './Card'
import { useVehicle } from '../api/queries'

export default function VesselTab({ selectedVessel }) {
  const { data, isError } = useVehicle(selectedVessel)
  // GET /api/vehicle/<type>/ returns a list of vehicles with that type
  const details = (Array.isArray(data) ? data[0] : data) || null

  return (
    <Card title="Active Vessel Specification">
      <div className="vessel-details">
        {isError ? (
          <p className="state-message state-message--error" role="alert">
            Failed to load vessel details.
          </p>
        ) : !details ? (
          <p>Select a vessel from the top header dropdown to view technical parameters.</p>
        ) : (
          <ul>
            {Object.entries(details).map(([key, val]) => (
              <li key={key}>
                <strong>{key}:</strong> {val !== null ? String(val) : 'N/A'}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}
