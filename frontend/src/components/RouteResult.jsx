import Card from './Card'
import { baseRouteName, routeNotes, routeTypeLabel, routesOf, summariseRoute } from '../routes'

// Result of a route request: the travel-time and fuel optimised routes side by side.
export default function RouteResult({ response }) {
  if (!response) return null

  const routes = routesOf(response)
  if (routes.length === 0) {
    return (
      <Card title="No route available" icon="fa-circle-exclamation" variant="danger" className="route-result">
        <p>{response.error || 'The server returned no route for this request.'}</p>
      </Card>
    )
  }

  const summaries = routes.map(summariseRoute)
  const rows = [
    ['Distance', 'distance'],
    ['Travel time', 'duration'],
    ['Fuel', 'fuel'],
  ]
  const mesh = summaries.find((s) => s.mesh)?.mesh
  const notes = routes.flatMap((route) => routeNotes(route).map((note) => ({ ...note, type: route.type })))

  return (
    <Card title="Route Calculation Results" icon="fa-circle-check" variant="success" className="route-result">
      <p className="route-result-name">{baseRouteName(routes)}</p>
      <table className="route-result-table">
        <thead>
          <tr>
            <td></td>
            {routes.map((route) => (
              <th key={route.type} scope="col">
                <svg className={`route-legend-swatch route-legend-swatch--${route.type}`} viewBox="0 0 40 12" aria-hidden="true">
                  <line className="route-legend-line" x1="1" y1="6" x2="39" y2="6" />
                </svg>
                {routeTypeLabel(route.type)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, key]) => (
            <tr key={key}>
              <th scope="row">{label}</th>
              {summaries.map((summary, i) => (
                <td key={routes[i].type}>{summary[key] ?? 'N/A'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {mesh && <p className="route-result-note">Mesh: {mesh}</p>}
      {notes.map((note) => (
        <p key={note.type + note.kind + note.text} className="route-result-note">
          <i className="fa-solid fa-circle-info fa-fw" aria-hidden="true"></i> {routeTypeLabel(note.type)}: {note.text}
        </p>
      ))}
    </Card>
  )
}
