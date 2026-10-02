import { useEffect, useRef, useState } from 'react'
import { roundel32 as logo, roundel64 as logo2x } from 'virtual:bas-style-kit-assets'

// Links required by the Style Kit standard header pattern:
// https://style-kit.web.bas.ac.uk/0.7.4/patterns/standard-header.html
const BAS_LINKS = [
  { label: 'BAS Home', href: 'https://www.bas.ac.uk' },
  { label: 'Discover BAS Data', href: 'https://data.bas.ac.uk' },
]

function PartOfBasMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    const onKeyDown = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div className="bas-menu" ref={ref}>
      <button type="button" className="bas-menu-toggle" aria-expanded={open} aria-controls="bas-menu-list" onClick={() => setOpen((o) => !o)}>
        Part of the British Antarctic Survey
        <svg className={`bas-menu-caret ${open ? 'bas-menu-caret--open' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div id="bas-menu-list" className="bas-menu-list bsk-bg-blue">
          {BAS_LINKS.map((link) => (
            <a key={link.href} href={link.href}>
              {link.label}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Header({ vessels, selectedVessel, onSelectVessel, projection, onSelectProjection, theme, onToggleTheme }) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header className="app-header bsk-bg-blue text-neutral-50">
      <div className="app-header-inner">
        <div className="app-header-brand">
          <a href="/" className="app-header-logo">
            <img src={logo} srcSet={`${logo} 1x, ${logo2x} 2x`} height="32" alt="British Antarctic Survey" />
          </a>
          <a href="/" className="app-header-name">
            PolarRoute
          </a>
        </div>
        <button
          type="button"
          className="header-menu-toggle"
          aria-expanded={menuOpen}
          aria-controls="header-controls"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <i className={`fa-solid ${menuOpen ? 'fa-xmark' : 'fa-bars'} fa-fw`} aria-hidden="true"></i> Menu
        </button>
        <div id="header-controls" className={`app-header-controls ${menuOpen ? 'app-header-controls--open' : ''}`.trim()}>
          <div className="header-field">
            <label htmlFor="projection-select">Projection:</label>
            <select id="projection-select" className="header-select" value={projection} onChange={(e) => onSelectProjection(e.target.value)}>
              <option value="mercator">Web Mercator</option>
              <option value="epsg3031">Antarctic Polar (EPSG:3031)</option>
              <option value="epsg3413">Arctic Polar (EPSG:3413)</option>
            </select>
          </div>
          <div className="header-field">
            <label htmlFor="vehicle-select">Vessel:</label>
            <select id="vehicle-select" className="header-select" value={selectedVessel} onChange={(e) => onSelectVessel(e.target.value)}>
              {vessels.length === 0 ? (
                <option value="">Loading vessels...</option>
              ) : (
                vessels.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))
              )}
            </select>
          </div>
          <div className="header-status">
            <span id="api-status-dot" className="status-dot" aria-hidden="true"></span>
            API Connected
          </div>
          <button type="button" className="theme-toggle" aria-pressed={theme === 'dark'} onClick={onToggleTheme}>
            <i className="fa-solid fa-moon fa-fw" aria-hidden="true"></i> Dark mode
          </button>
          <PartOfBasMenu />
        </div>
      </div>
    </header>
  )
}
