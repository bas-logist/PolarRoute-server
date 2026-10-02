import { useId, useState } from 'react'
import { COLOUR_SCALE_GRADIENT, EXTENT_ICE_COLOUR, LAYER_KINDS, formatDay, formatShortDay } from '../seaIce'

const StatusNote = ({ children }) => (
  <>
    {' '}
    <span className="sea-ice-status">{children}</span>
  </>
)

function LayerRow({ layer, date, onToggle }) {
  const unavailable = !layer.loading && !layer.current
  const otherDay = layer.enabled && layer.shownDate && layer.shownDate !== date
  return (
    <label className={unavailable ? 'sea-ice-layer sea-ice-layer--off' : 'sea-ice-layer'}>
      <input type="checkbox" checked={layer.enabled} disabled={unavailable} onChange={() => onToggle(layer.id)} />
      <span>
        {layer.name} <span className="sea-ice-detail">({layer.detail})</span>
        {layer.loading && <StatusNote>checking…</StatusNote>}
        {unavailable && <StatusNote>no recent data</StatusNote>}
        {otherDay && <StatusNote>showing {formatShortDay(layer.shownDate)}</StatusNote>}
        {layer.enabled && layer.current && !layer.shownDate && <StatusNote>no data for this day</StatusNote>}
      </span>
    </label>
  )
}

// Map overlay panel for the sea ice layers (concentration and extent). It can be minimised to just its title bar.
export default function SeaIceControl({ seaIce, startMinimised = false }) {
  const [minimised, setMinimised] = useState(startMinimised)
  const bodyId = useId()
  const { layers, dates, date, latest, olderDate, newerDate, opacity, loading, failed } = seaIce

  const showing = (kind) => layers.some((l) => l.kind === kind && l.enabled && l.shownDate)

  return (
    <section className="sea-ice-control" aria-label="Sea ice">
      <button type="button" className="sea-ice-toggle" aria-expanded={!minimised} aria-controls={bodyId} onClick={() => setMinimised((m) => !m)}>
        <span>
          <i className="fa-solid fa-snowflake fa-fw" aria-hidden="true"></i> Sea ice
        </span>
        <i className={`fa-solid ${minimised ? 'fa-chevron-down' : 'fa-chevron-up'}`} aria-hidden="true"></i>
        <span className="sr-only">{minimised ? 'Show controls' : 'Minimise controls'}</span>
      </button>

      {!minimised && (
        <div id={bodyId} className="sea-ice-body">
          {!seaIce.available ? (
            <p className="sea-ice-note">NASA GIBS has no sea ice layers that are current to today in this projection.</p>
          ) : (
            <>
              {LAYER_KINDS.map((kind) => {
                const group = layers.filter((l) => l.kind === kind.id)
                if (group.length === 0) return null
                return (
                  <fieldset key={kind.id} className="sea-ice-layers">
                    <legend>{kind.title}</legend>
                    {group.map((layer) => (
                      <LayerRow key={layer.id} layer={layer} date={date} onToggle={seaIce.toggleLayer} />
                    ))}
                  </fieldset>
                )
              })}

              {failed && (
                <p role="alert" className="sea-ice-note sea-ice-note--error">
                  Could not check which days are available.
                </p>
              )}

              {dates.length > 0 && (
                <div className="sea-ice-day">
                  <label htmlFor={`${bodyId}-date`}>Day</label>
                  <div className="sea-ice-day-controls">
                    <button type="button" className="bsk-btn bsk-btn-default bsk-btn-xs" disabled={!olderDate} onClick={() => seaIce.setDate(olderDate)} aria-label="Previous day">
                      <i className="fa-solid fa-chevron-left" aria-hidden="true"></i>
                    </button>
                    <select id={`${bodyId}-date`} value={date || ''} onChange={(e) => seaIce.setDate(e.target.value)}>
                      {dates.map((d) => (
                        <option key={d} value={d}>
                          {formatDay(d)}
                          {d === latest ? ' (latest)' : ''}
                        </option>
                      ))}
                    </select>
                    <button type="button" className="bsk-btn bsk-btn-default bsk-btn-xs" disabled={!newerDate} onClick={() => seaIce.setDate(newerDate)} aria-label="Next day">
                      <i className="fa-solid fa-chevron-right" aria-hidden="true"></i>
                    </button>
                  </div>
                </div>
              )}
              {loading && dates.length === 0 && <p className="sea-ice-note">Checking available days…</p>}

              <div className="sea-ice-opacity">
                <label htmlFor={`${bodyId}-opacity`}>Opacity</label>
                <input
                  id={`${bodyId}-opacity`}
                  type="range"
                  min="10"
                  max="100"
                  step="5"
                  value={Math.round(opacity * 100)}
                  onChange={(e) => seaIce.setOpacity(Number(e.target.value) / 100)}
                />
                <output htmlFor={`${bodyId}-opacity`}>{Math.round(opacity * 100)}%</output>
              </div>

              {showing('concentration') && (
                <div className="sea-ice-scale">
                  <div className="sea-ice-scale-bar" style={{ background: COLOUR_SCALE_GRADIENT }} role="img" aria-label="Colour scale from 0 to 100 percent sea ice concentration" />
                  <div className="sea-ice-scale-labels" aria-hidden="true">
                    <span>0%</span>
                    <span>50%</span>
                    <span>100%</span>
                  </div>
                  <p className="sea-ice-caption">Concentration</p>
                </div>
              )}
              {showing('extent') && (
                <p className="sea-ice-key">
                  <span className="sea-ice-key-swatch" style={{ background: EXTENT_ICE_COLOUR }} aria-hidden="true"></span>
                  Sea ice detected. Gaps are open water, or no cloud-free daylight view.
                </p>
              )}
              <p className="sea-ice-credit">Imagery: NASA GIBS (GHRSST L4; MODIS and VIIRS sea ice extent).</p>
            </>
          )}
        </div>
      )}
    </section>
  )
}
