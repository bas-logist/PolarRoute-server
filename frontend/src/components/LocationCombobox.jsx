import { useEffect, useId, useRef, useState } from 'react'

// Text box that doubles as a dropdown of saved locations (ARIA 1.2 combobox with a list popup).
// Typing names the point; picking an option reports the whole location through onSelect.
export default function LocationCombobox({ id, value, onChange, onSelect, options, placeholder, ...inputProps }) {
  const listId = useId()
  const rootRef = useRef(null)
  const listRef = useRef(null)
  const [open, setOpen] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [active, setActive] = useState(-1)

  const query = value.trim().toLowerCase()
  const visible = showAll || !query ? options : options.filter((loc) => loc.name.toLowerCase().includes(query))
  const optionId = (index) => `${listId}-option-${index}`

  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  useEffect(() => {
    listRef.current?.children[active]?.scrollIntoView?.({ block: 'nearest' })
  }, [active])

  const openList = (all) => {
    setShowAll(all)
    setActive(-1)
    setOpen(true)
  }

  const choose = (location) => {
    onSelect(location)
    setOpen(false)
    setActive(-1)
  }

  const handleChange = (e) => {
    onChange(e.target.value)
    if (options.length > 0) openList(false)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!open) {
        openList(true)
        setActive(0)
      } else if (visible.length > 0) {
        setActive((i) => (i + 1) % visible.length)
      }
    } else if (e.key === 'ArrowUp' && open && visible.length > 0) {
      e.preventDefault()
      setActive((i) => (i <= 0 ? visible.length - 1 : i - 1))
    } else if (e.key === 'Enter' && open && active >= 0 && visible[active]) {
      e.preventDefault()
      choose(visible[active])
    } else if (e.key === 'Escape' && open) {
      e.stopPropagation()
      setOpen(false)
    } else if (e.key === 'Tab') {
      setOpen(false)
    }
  }

  return (
    <div className="combobox" ref={rootRef}>
      <input
        {...inputProps}
        id={id}
        type="text"
        role="combobox"
        className="form-input combobox-input"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 ? optionId(active) : undefined}
        autoComplete="off"
        placeholder={placeholder}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
      />
      <button
        type="button"
        className="combobox-toggle"
        tabIndex={-1}
        aria-label="Show saved locations"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => (open ? setOpen(false) : openList(true))}
      >
        <i className={`fa-solid ${open ? 'fa-chevron-up' : 'fa-chevron-down'}`} aria-hidden="true"></i>
      </button>
      {open && (
        <ul id={listId} ref={listRef} role="listbox" aria-label="Saved locations" className="combobox-list">
          {visible.length === 0 ? (
            <li role="presentation" className="combobox-empty">
              {options.length === 0 ? 'No saved locations' : 'No matching saved locations'}
            </li>
          ) : (
            visible.map((loc, index) => (
              <li
                key={loc.id}
                id={optionId(index)}
                role="option"
                aria-selected={index === active}
                className={`combobox-option ${index === active ? 'combobox-option--active' : ''}`.trim()}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(loc)}
                onMouseMove={() => setActive(index)}
              >
                <span>{loc.name}</span>
                <span className="combobox-option-meta">
                  {loc.lat}, {loc.lon}
                </span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}
