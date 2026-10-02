import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import RouteResult from './RouteResult'

const feature = (objective) => ({ type: 'FeatureCollection', features: [{ type: 'Feature', properties: { objective_function: objective }, geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] } }] })
const traveltime = { type: 'traveltime', name: 'KEP to Halley (traveltime)', path: feature('traveltime'), optimisation: { metrics: { time: { duration: '24.0' }, distance: { value: 2500000, units: 'meters' } } }, mesh: { id: 1, name: 'Test Mesh' } }
const fuel = { type: 'fuel', name: 'KEP to Halley (fuel)', path: feature('fuel'), optimisation: { metrics: { fuelConsumption: { value: 100.5, units: 'kg' }, distance: { value: 2700000, units: 'meters' } } }, info: { warning: 'Smoothing failed for fuel-optimisation, returning unsmoothed route.' } }

describe('RouteResult', () => {
  it('compares the travel-time and fuel optimised routes side by side', () => {
    render(<RouteResult response={{ routes: [traveltime, fuel] }} />)
    expect(screen.getByText('KEP to Halley')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByRole('columnheader', { name: /travel time/i })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: /fuel/i })).toBeInTheDocument()

    const distance = within(table).getByRole('row', { name: /distance/i })
    expect(within(distance).getByText('2500.00 km')).toBeInTheDocument()
    expect(within(distance).getByText('2700.00 km')).toBeInTheDocument()

    expect(within(within(table).getByRole('row', { name: /^travel time 24/i })).getByText('24.0 days (576 hrs)')).toBeInTheDocument()
    expect(within(within(table).getByRole('row', { name: /^fuel .*100/i })).getByText('100.50 kg')).toBeInTheDocument()
    expect(screen.getAllByText('N/A')).toHaveLength(2)
  })

  it('shows the mesh once and labels server warnings with their route', () => {
    render(<RouteResult response={{ routes: [traveltime, fuel] }} />)
    expect(screen.getByText('Mesh: Test Mesh')).toBeInTheDocument()
    expect(screen.getByText(/Fuel: Smoothing failed/)).toBeInTheDocument()
  })

  it('copes with only one optimisation type being available', () => {
    render(<RouteResult response={{ routes: [traveltime] }} />)
    expect(screen.getAllByRole('columnheader')).toHaveLength(1)
    expect(screen.queryByRole('columnheader', { name: /^fuel/i })).not.toBeInTheDocument()
  })

  it('explains when the server returned no route', () => {
    render(<RouteResult response={{ routes: [], error: 'No routes available for any optimisation type.' }} />)
    expect(screen.getByText('No routes available for any optimisation type.')).toBeInTheDocument()
  })

  it('renders nothing before a route is loaded', () => {
    const { container } = render(<RouteResult response={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
