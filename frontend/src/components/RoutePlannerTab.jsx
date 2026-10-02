import { cloneElement, useMemo, useState } from 'react'
import Card from './Card'
import LocationCombobox from './LocationCombobox'
import RouteResult from './RouteResult'
import { useLocations } from '../api/queries'
import { applySavedLocation, parseRouteForm, withStaleNameCleared } from '../routeForm'

// Form markup follows the Style Kit forms guidance (fieldset, bold label, help/validation text linked
// with aria-describedby, aria-invalid on invalid controls): https://style-kit.web.bas.ac.uk/0.7.4/core/forms.html
function Field({ label, name, error, showError, children }) {
  const hasError = showError && Boolean(error)
  const errorId = `${name}-error`
  return (
    <fieldset className={`bsk-form-group ${hasError ? 'bsk-has-error' : ''}`.trim()}>
      <b>
        <label htmlFor={name}>{label}</label>
      </b>
      {cloneElement(children, { 'aria-invalid': hasError || undefined, 'aria-describedby': hasError ? errorId : undefined })}
      {hasError && (
        <p id={errorId} role="alert" className="field-error">
          <i className="fa-solid fa-circle-exclamation fa-fw" aria-hidden="true"></i> {error}
        </p>
      )}
    </fieldset>
  )
}

function PointCard({ prefix, title, icon, placeholder, form, errors, showErrors, onChange, locations, onSelectLocation, picking, onTogglePicking }) {
  const input = (suffix, props) => (
    <input id={`${prefix}_${suffix}`} name={`${prefix}_${suffix}`} className="form-input" value={form[`${prefix}_${suffix}`]} onChange={onChange} {...props} />
  )
  const fieldProps = (suffix) => ({ name: `${prefix}_${suffix}`, error: errors[`${prefix}_${suffix}`], showError: showErrors })
  const pointLabel = prefix === 'start' ? 'start point' : 'end point'

  return (
    <Card title={title} icon={icon}>
      <fieldset className="bsk-form-group">
        <b>
          <label htmlFor={`${prefix}_name`}>Location Name</label>
        </b>
        <LocationCombobox
          id={`${prefix}_name`}
          name={`${prefix}_name`}
          value={form[`${prefix}_name`]}
          onChange={(text) => onChange({ target: { name: `${prefix}_name`, value: text, type: 'text' } })}
          onSelect={onSelectLocation}
          options={locations}
          placeholder={placeholder}
          aria-describedby={`${prefix}_name-help`}
        />
        <p id={`${prefix}_name-help`} className="field-help">
          Type a name for this point, or choose a saved location from the list.
        </p>
      </fieldset>
      <div className="coordinate-inputs">
        <Field label="Latitude" {...fieldProps('lat')}>
          {input('lat', { type: 'number', step: 'any' })}
        </Field>
        <Field label="Longitude" {...fieldProps('lon')}>
          {input('lon', { type: 'number', step: 'any' })}
        </Field>
      </div>
      <button
        type="button"
        className={`bsk-btn bsk-btn-default bsk-btn-xs ${picking ? 'bsk-active' : ''}`.trim()}
        aria-pressed={picking}
        onClick={onTogglePicking}
      >
        <i className="fa-solid fa-location-crosshairs fa-fw" aria-hidden="true"></i> {picking ? 'Cancel' : 'Set on map'}
      </button>
      {picking && (
        <p role="status" className="field-help">
          Click the map to place the {pointLabel}. Press Escape to cancel.
        </p>
      )}
    </Card>
  )
}

export default function RoutePlannerTab({
  routeForm,
  setRouteForm,
  onCalculate,
  routeResponse,
  mapPickMode,
  onMapPickModeChange,
}) {
  const [submitted, setSubmitted] = useState(false)
  const { payload, errors, isValid } = useMemo(() => parseRouteForm(routeForm), [routeForm])

  const locations = useLocations().data || []

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setRouteForm((prev) => {
      const next = { ...prev, [name]: type === 'checkbox' ? checked : value }
      const coordinate = name.match(/^(start|end)_(lat|lon)$/)
      return coordinate ? withStaleNameCleared(next, coordinate[1], locations) : next
    })
  }

  const selectLocation = (prefix) => (location) => setRouteForm((prev) => applySavedLocation(prev, prefix, location))
  const togglePicking = (prefix) => () => onMapPickModeChange(mapPickMode === prefix ? null : prefix)

  const handleSubmit = (e) => {
    e.preventDefault()
    setSubmitted(true)
    if (isValid) onCalculate(payload)
  }

  const pointProps = { form: routeForm, errors, showErrors: submitted, onChange: handleChange, locations }

  return (
    <div>
      <form onSubmit={handleSubmit} noValidate>
        <PointCard
          prefix="start"
          title="Start Point"
          icon="fa-location-dot"
          placeholder="e.g. Rothera"
          onSelectLocation={selectLocation('start')}
          picking={mapPickMode === 'start'}
          onTogglePicking={togglePicking('start')}
          {...pointProps}
        />
        <PointCard
          prefix="end"
          title="End Point"
          icon="fa-flag-checkered"
          placeholder="e.g. Punta Arenas"
          onSelectLocation={selectLocation('end')}
          picking={mapPickMode === 'end'}
          onTogglePicking={togglePicking('end')}
          {...pointProps}
        />

        <Card title="Advanced Options" icon="fa-sliders">
          <Field label="Mesh ID (Optional)" name="mesh_id" error={errors.mesh_id} showError={submitted}>
            <input
              id="mesh_id"
              type="number"
              name="mesh_id"
              className="form-input"
              value={routeForm.mesh_id}
              onChange={handleChange}
              placeholder="e.g. 1"
            />
          </Field>
          <fieldset className="bsk-form-group">
            <label>
              <input type="checkbox" name="force_new_route" checked={routeForm.force_new_route} onChange={handleChange} /> Force new route
              recalculation
            </label>
          </fieldset>
          <Field label="Tags (comma separated)" name="tags">
            <input id="tags" type="text" name="tags" className="form-input" value={routeForm.tags} onChange={handleChange} />
          </Field>
        </Card>

        <button type="submit" className="bsk-btn bsk-btn-primary w-full">
          <i className="fa-solid fa-calculator" aria-hidden="true"></i> Calculate Optimal Route
        </button>
      </form>

      <RouteResult response={routeResponse} />
    </div>
  )
}
