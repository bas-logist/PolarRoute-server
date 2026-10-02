import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import JobsTab from './JobsTab'
import RecentTab from './RecentTab'
import VesselTab from './VesselTab'
import * as api from '../api/client'

vi.mock('../api/client')

// Shape of GET /api/recent_routes (see tests/test_views.py in the server)
const item = (overrides) => ({
  id: 1,
  start_lat: -54.3,
  start_lon: -36.5,
  end_lat: -75.1,
  end_lon: -26.7,
  start_name: 'KEP',
  end_name: 'Halley',
  requested: '2026-10-02T09:00:00Z',
  calculated: null,
  status: 'PENDING',
  route_url: 'http://testserver/api/route/1',
  job_id: 'job-1',
  job_status_url: 'http://testserver/api/job/job-1',
  tags: [],
  ...overrides,
})

const recent = {
  routes: [
    item({ id: 3, start_name: 'Rothera', end_name: 'Punta Arenas', status: 'SUCCESS', calculated: '2026-10-02T09:05:00Z', job_id: 'job-3', mesh: { id: 1, name: 'Test Mesh' }, tags: ['archive'] }),
    item({ id: 2, status: 'PENDING', job_id: 'job-2' }),
    item({ id: 1, start_name: null, end_name: null, status: 'FAILURE', job_id: 'job-1' }),
  ],
  'polarrouteserver-version': '1.0.0',
}

const renderWithClient = (ui) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.resetAllMocks()
  api.getRecentRoutes.mockResolvedValue(recent)
})

describe('JobsTab', () => {
  it('shows the real status of each job, not UNKNOWN', async () => {
    renderWithClient(<JobsTab onLoadRoute={() => {}} />)
    expect(await screen.findByText('Rothera to Punta Arenas')).toBeInTheDocument()
    expect(screen.getByText('SUCCESS')).toBeInTheDocument()
    expect(screen.getByText('PENDING')).toBeInTheDocument()
    expect(screen.getByText('FAILURE')).toBeInTheDocument()
    expect(screen.queryByText('UNKNOWN')).not.toBeInTheDocument()
    expect(screen.getByText('Start to End')).toBeInTheDocument()
  })

  it('offers to view finished routes and cancel pending ones', async () => {
    const onLoadRoute = vi.fn()
    api.cancelJob.mockResolvedValue({})
    vi.spyOn(window, 'alert').mockImplementation(() => {})
    renderWithClient(<JobsTab onLoadRoute={onLoadRoute} />)
    await screen.findByText('Rothera to Punta Arenas')

    expect(screen.getAllByRole('button', { name: /view result on map/i })).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: /view result on map/i }))
    expect(onLoadRoute).toHaveBeenCalledWith(3)

    expect(screen.getAllByRole('button', { name: /cancel job/i })).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: /cancel job/i }))
    await vi.waitFor(() => expect(api.cancelJob).toHaveBeenCalled())
    expect(api.cancelJob.mock.calls[0][0]).toBe('job-2')
  })
})

describe('RecentTab', () => {
  it('lists routes with their status, mesh and tags, and loads finished ones by route id', async () => {
    const onLoadRoute = vi.fn()
    renderWithClient(<RecentTab onLoadRoute={onLoadRoute} />)
    const finished = (await screen.findByText('Rothera to Punta Arenas')).closest('.list-item')
    expect(within(finished).getByText('SUCCESS')).toBeInTheDocument()
    expect(within(finished).getByText(/Mesh: Test Mesh/)).toBeInTheDocument()
    expect(within(finished).getByText(/Tags: archive/)).toBeInTheDocument()
    await userEvent.click(within(finished).getByRole('button', { name: /load route on map/i }))
    expect(onLoadRoute).toHaveBeenCalledWith(3)
    expect(screen.getAllByRole('button', { name: /load route on map/i })).toHaveLength(1)
  })
})

describe('VesselTab', () => {
  it('shows the fields of the vehicle returned as a list', async () => {
    api.getVehicle.mockResolvedValue([{ vessel_type: 'SDA', max_speed: 26.5, unit: 'km/h', max_ice_conc: 80 }])
    renderWithClient(<VesselTab selectedVessel="SDA" />)
    expect(await screen.findByText('max_speed:')).toBeInTheDocument()
    expect(screen.getByText(/26.5/)).toBeInTheDocument()
    expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument()
  })
})
