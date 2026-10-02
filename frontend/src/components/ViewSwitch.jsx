// Mobile-only switch between the sidebar panel and the map (shown one at a time on small screens)
export default function ViewSwitch({ view, onChange }) {
  const buttons = [
    { id: 'panel', label: 'Planner', icon: 'fa-sliders' },
    { id: 'map', label: 'Map', icon: 'fa-map' },
  ]
  return (
    <div className="view-switch" role="group" aria-label="Show planner or map">
      {buttons.map((b) => (
        <button key={b.id} type="button" className="bsk-btn bsk-btn-default" aria-pressed={view === b.id} onClick={() => onChange(b.id)}>
          <i className={`fa-solid ${b.icon} fa-fw`} aria-hidden="true"></i> {b.label}
        </button>
      ))}
    </div>
  )
}
