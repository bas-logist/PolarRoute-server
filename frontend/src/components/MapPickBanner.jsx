// Shown over the map while the user is placing a start or end point
export default function MapPickBanner({ mode, onCancel }) {
  if (!mode) return null
  return (
    <div className="map-pick-banner" role="status">
      <span>Click or tap the map to place the {mode === 'start' ? 'start' : 'end'} point.</span>
      <button type="button" className="bsk-btn bsk-btn-default bsk-btn-xs" onClick={onCancel}>
        Cancel
      </button>
    </div>
  )
}
