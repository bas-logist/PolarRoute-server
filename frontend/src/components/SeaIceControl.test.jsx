import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SeaIceControl from './SeaIceControl'

const baseSeaIce = (overrides = {}) => ({
  available: true,
  loading: false,
  failed: false,
  layers: [
    { id: 'a', kind: 'concentration', name: 'MUR', detail: 'high resolution', enabled: true, loading: false, current: true, shownDate: '2026-10-01' },
    { id: 'b', kind: 'concentration', name: 'MUR25', detail: '0.25° grid', enabled: false, loading: false, current: true, shownDate: '2026-09-30' },
    { id: 'c', kind: 'extent', name: 'MODIS Terra', detail: 'daily', enabled: false, loading: false, current: true, shownDate: '2026-10-01' },
  ],
  dates: ['2026-10-01', '2026-09-30', '2026-09-29'],
  date: '2026-10-01',
  latest: '2026-10-01',
  olderDate: '2026-09-30',
  newerDate: null,
  opacity: 0.7,
  toggleLayer: vi.fn(),
  setDate: vi.fn(),
  setOpacity: vi.fn(),
  ...overrides,
})

describe('SeaIceControl', () => {
  it('shows the latest day selected and lets the user step to previous days', async () => {
    const seaIce = baseSeaIce()
    render(<SeaIceControl seaIce={seaIce} />)
    const select = screen.getByRole('combobox', { name: 'Day' })
    expect(select).toHaveValue('2026-10-01')
    expect(screen.getByRole('option', { name: /\(latest\)/ })).toHaveValue('2026-10-01')
    expect(screen.getByRole('button', { name: 'Next day' })).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Previous day' }))
    expect(seaIce.setDate).toHaveBeenCalledWith('2026-09-30')
    await userEvent.selectOptions(select, '2026-09-29')
    expect(seaIce.setDate).toHaveBeenCalledWith('2026-09-29')
  })

  it('toggles layers and changes opacity', async () => {
    const seaIce = baseSeaIce()
    render(<SeaIceControl seaIce={seaIce} />)
    expect(screen.getByRole('checkbox', { name: /^MUR \(/ })).toBeChecked()
    await userEvent.click(screen.getByRole('checkbox', { name: /^MUR25/ }))
    expect(seaIce.toggleLayer).toHaveBeenCalledWith('b')
    expect(screen.getByRole('slider', { name: 'Opacity' })).toHaveValue('70')
    expect(screen.getByText('70%')).toBeInTheDocument()
  })

  it('can be minimised and restored', async () => {
    render(<SeaIceControl seaIce={baseSeaIce()} />)
    const toggle = screen.getByRole('button', { name: /sea ice/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('combobox', { name: 'Day' })).not.toBeInTheDocument()
    await userEvent.click(toggle)
    expect(screen.getByRole('combobox', { name: 'Day' })).toBeInTheDocument()
  })

  it('can start minimised', () => {
    render(<SeaIceControl seaIce={baseSeaIce()} startMinimised />)
    expect(screen.getByRole('button', { name: /sea ice/i })).toHaveAttribute('aria-expanded', 'false')
  })

  it('explains when a projection has no current layer', () => {
    render(<SeaIceControl seaIce={baseSeaIce({ available: false, layers: [], dates: [], date: null })} />)
    expect(screen.getByText(/no sea ice layers that are current/i)).toBeInTheDocument()
  })

  it('flags layers with no recent data and a failed availability check', () => {
    const seaIce = baseSeaIce({ failed: true, layers: [{ id: 'a', kind: 'concentration', name: 'MUR', detail: 'x', enabled: false, loading: false, current: false, shownDate: null }] })
    render(<SeaIceControl seaIce={seaIce} />)
    expect(screen.getByRole('checkbox', { name: /no recent data/i })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent(/could not check/i)
  })

  it('groups layers into concentration and extent', () => {
    render(<SeaIceControl seaIce={baseSeaIce()} />)
    expect(screen.getByRole('group', { name: 'Concentration' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Extent' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /MODIS Terra/ })).toBeInTheDocument()
  })

  it('says which day a layer is actually showing when it differs from the selected one', () => {
    const seaIce = baseSeaIce({ date: '2026-10-02', dates: ['2026-10-02', '2026-10-01'], latest: '2026-10-02' })
    render(<SeaIceControl seaIce={seaIce} />)
    expect(screen.getByRole('checkbox', { name: /MUR \(high resolution\) showing (1 Oct|Oct 1)/ })).toBeInTheDocument()
  })

  it('shows the key for the kinds of layer that are on', () => {
    const seaIce = baseSeaIce()
    seaIce.layers[2].enabled = true
    render(<SeaIceControl seaIce={seaIce} />)
    expect(screen.getByRole('img', { name: /colour scale/i })).toBeInTheDocument()
    expect(screen.getByText(/sea ice detected/i)).toBeInTheDocument()
  })
})
