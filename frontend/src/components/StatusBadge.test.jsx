import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusBadge from './StatusBadge'

describe('StatusBadge', () => {
  it.each([
    ['SUCCESS', 'success'],
    ['STARTED', 'info'],
    ['FAILURE', 'danger'],
    ['UNKNOWN', 'default'],
  ])('renders %s as a %s Style Kit label', (status, tone) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(status)).toHaveClass('bsk-label', `bsk-label-${tone}`)
  })
})
