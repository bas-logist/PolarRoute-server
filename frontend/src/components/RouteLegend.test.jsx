import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import RouteLegend from './RouteLegend'

describe('RouteLegend', () => {
  it('lists each route type and explains the arrows', () => {
    render(<RouteLegend routes={[{ type: 'traveltime' }, { type: 'fuel' }]} />)
    expect(screen.getByText('Travel time route')).toBeInTheDocument()
    expect(screen.getByText('Fuel route')).toBeInTheDocument()
    expect(screen.getByText(/direction of travel/i)).toBeInTheDocument()
  })

  it('renders nothing without routes', () => {
    const { container } = render(<RouteLegend routes={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
