import { routeTypeLabel } from '../routes'

// Key for the routes drawn on the map: one entry per optimisation type, plus the meaning of the arrows
export default function RouteLegend({ routes }) {
  if (routes.length === 0) return null
  return (
    <div className="route-legend" aria-label="Map key">
      <ul>
        {routes.map((route) => (
          <li key={route.type}>
            <svg className={`route-legend-swatch route-legend-swatch--${route.type}`} viewBox="0 0 40 12" aria-hidden="true">
              <line className="route-legend-line" x1="1" y1="6" x2="39" y2="6" />
              <path className="route-legend-arrow" d="M20 1 L29 6 L20 11 L23 6 Z" />
            </svg>
            {routeTypeLabel(route.type)} route
          </li>
        ))}
      </ul>
      <p>Arrows show the direction of travel, from start to end.</p>
    </div>
  )
}
