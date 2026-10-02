// BAS Style Kit card: https://style-kit.web.bas.ac.uk/0.7.4/components/card.html
export default function Card({ title, icon, variant, children, className = '' }) {
  const colour = variant ? `bsk-card-${variant}` : 'bg-gray-200'
  return (
    <section className={`bsk-card ${colour} rounded py-2 px-4 ${className}`.trim()}>
      {title && (
        <header className="card-header">
          {icon && <i className={`fa-solid ${icon} fa-fw`} aria-hidden="true"></i>} {title}
        </header>
      )}
      {children}
    </section>
  )
}
