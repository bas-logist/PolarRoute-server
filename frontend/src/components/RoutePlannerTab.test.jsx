import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import RoutePlannerTab from './RoutePlannerTab'
import { initialRouteForm } from '../routeForm'
import * as api from '../api/client'

vi.mock('../api/client')

const locations = [
  { id: 1, name: 'Rothera Research Station', lat: -67.57, lon: -68.12 },
  { id: 2, name: 'Punta Arenas', lat: -53.15, lon: -70.91 },
  { id: 3, name: 'Halley VI', lat: -75.58, lon: -26.66 },
]

function Harness({ onCalculate = () => {}, initial = initialRouteForm, onMapPickModeChange = () => {}, mapPickMode = null }) {
  const [form, setForm] = useState(initial)
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }))
  return (
    <QueryClientProvider client={client}>
      <RoutePlannerTab
        routeForm={form}
        setRouteForm={setForm}
        onCalculate={onCalculate}
        routeResponse={null}
        mapPickMode={mapPickMode}
        onMapPickModeChange={onMapPickModeChange}
      />
    </QueryClientProvider>
  )
}

const getCard = (title) => screen.getAllByText(title).find((el) => el.closest('section'))?.closest('section')

beforeEach(() => {
  api.getLocations.mockResolvedValue(locations)
})

describe('RoutePlannerTab', () => {
  it('submits a numeric payload when the form is valid', async () => {
    const onCalculate = vi.fn()
    render(<Harness onCalculate={onCalculate} />)
    await userEvent.click(screen.getByRole('button', { name: /calculate optimal route/i }))
    expect(onCalculate).toHaveBeenCalledTimes(1)
    expect(onCalculate.mock.calls[0][0]).toMatchObject({ start_lat: -67.57, end_lon: -70.91, tags: ['archive', 'SD056'] })
  })

  it('blocks submission and shows field errors for invalid input', async () => {
    const onCalculate = vi.fn()
    render(<Harness onCalculate={onCalculate} initial={{ ...initialRouteForm, start_lat: '123' }} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /calculate optimal route/i }))
    expect(onCalculate).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Latitude must be between -90 and 90')
  })

  it('sets name and coordinates from the saved locations dropdown of the end point', async () => {
    render(<Harness />)
    const endCard = within(getCard('End Point'))
    await userEvent.click(endCard.getByRole('button', { name: /show saved locations/i }))
    await userEvent.click(await screen.findByRole('option', { name: /halley vi/i }))
    expect(endCard.getByRole('combobox')).toHaveValue('Halley VI')
    expect(endCard.getByLabelText('Latitude')).toHaveValue(-75.58)
    expect(endCard.getByLabelText('Longitude')).toHaveValue(-26.66)
    expect(within(getCard('Start Point')).getByRole('combobox')).toHaveValue('Rothera Research Station')
  })

  it('lets a point be named freely and filters the dropdown while typing', async () => {
    render(<Harness />)
    const startName = within(getCard('Start Point')).getByRole('combobox')
    await userEvent.clear(startName)
    await userEvent.type(startName, 'hal')
    expect(await screen.findAllByRole('option')).toHaveLength(1)
    await userEvent.type(startName, 'x')
    expect(screen.queryAllByRole('option')).toHaveLength(0)
    expect(startName).toHaveValue('halx')
  })

  it('selects a location from the keyboard', async () => {
    render(<Harness />)
    const startName = within(getCard('Start Point')).getByRole('combobox')
    await userEvent.click(startName)
    await userEvent.keyboard('{ArrowDown}{ArrowDown}{Enter}')
    expect(startName).toHaveValue('Punta Arenas')
  })

  it('clears a saved name when its coordinates are edited, but keeps custom names', async () => {
    render(<Harness />)
    const start = within(getCard('Start Point'))
    await userEvent.type(start.getByLabelText('Latitude'), '1')
    expect(start.getByRole('combobox')).toHaveValue('')
  })

  it('toggles map picking for each point', async () => {
    const onMapPickModeChange = vi.fn()
    const { rerender } = render(<Harness onMapPickModeChange={onMapPickModeChange} />)
    await userEvent.click(within(getCard('End Point')).getByRole('button', { name: /set on map/i }))
    expect(onMapPickModeChange).toHaveBeenLastCalledWith('end')
    rerender(<Harness onMapPickModeChange={onMapPickModeChange} mapPickMode="end" />)
    const cancel = within(getCard('End Point')).getByRole('button', { name: /cancel/i })
    expect(cancel).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('status')).toHaveTextContent(/place the end point/i)
    await userEvent.click(cancel)
    expect(onMapPickModeChange).toHaveBeenLastCalledWith(null)
  })
})
