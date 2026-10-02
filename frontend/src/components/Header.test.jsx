import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Header from './Header'

const renderHeader = (props = {}) =>
  render(
    <Header
      vessels={['default']}
      selectedVessel="default"
      onSelectVessel={() => {}}
      projection="mercator"
      onSelectProjection={() => {}}
      theme="light"
      onToggleTheme={() => {}}
      {...props}
    />,
  )

describe('Header', () => {
  it('shows the BAS logo and links the site name to the app home', () => {
    renderHeader()
    expect(screen.getByAltText('British Antarctic Survey')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'PolarRoute' })).toHaveAttribute('href', '/')
  })

  it('provides the Part of the British Antarctic Survey links', async () => {
    renderHeader()
    const toggle = screen.getByRole('button', { name: /part of the british antarctic survey/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('link', { name: 'BAS Home' })).not.toBeInTheDocument()

    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('link', { name: 'BAS Home' })).toHaveAttribute('href', 'https://www.bas.ac.uk')
    expect(screen.getByRole('link', { name: 'Discover BAS Data' })).toHaveAttribute('href', 'https://data.bas.ac.uk')

    await userEvent.keyboard('{Escape}')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('exposes the dark mode toggle state and calls back when pressed', async () => {
    const onToggleTheme = vi.fn()
    renderHeader({ theme: 'dark', onToggleTheme })
    const toggle = screen.getByRole('button', { name: /dark mode/i })
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(toggle)
    expect(onToggleTheme).toHaveBeenCalledTimes(1)
  })

  it('collapses the controls behind a Menu button that reports its state', async () => {
    renderHeader()
    const menu = screen.getByRole('button', { name: /menu/i })
    const controls = document.getElementById('header-controls')
    expect(menu).toHaveAttribute('aria-controls', 'header-controls')
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    expect(controls).not.toHaveClass('app-header-controls--open')
    await userEvent.click(menu)
    expect(menu).toHaveAttribute('aria-expanded', 'true')
    expect(controls).toHaveClass('app-header-controls--open')
  })
})
