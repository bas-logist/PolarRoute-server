import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ViewSwitch from './ViewSwitch'
import MapPickBanner from './MapPickBanner'

describe('ViewSwitch', () => {
  it('marks the current view as pressed and reports changes', async () => {
    const onChange = vi.fn()
    render(<ViewSwitch view="panel" onChange={onChange} />)
    expect(screen.getByRole('button', { name: /planner/i })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /map/i })).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(screen.getByRole('button', { name: /map/i }))
    expect(onChange).toHaveBeenCalledWith('map')
  })
})

describe('MapPickBanner', () => {
  it('renders nothing when not picking', () => {
    const { container } = render(<MapPickBanner mode={null} onCancel={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('names the point being placed and can be cancelled', async () => {
    const onCancel = vi.fn()
    render(<MapPickBanner mode="end" onCancel={onCancel} />)
    expect(screen.getByRole('status')).toHaveTextContent(/place the end point/i)
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalled()
  })
})
