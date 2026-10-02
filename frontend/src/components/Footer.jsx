export default function Footer() {
  return (
    <footer className="app-footer bg-black text-white">
      <div className="app-footer-inner">
        <span>PolarRoute Server v0.0.1</span>
        <span>
          The{' '}
          <a href="https://www.bas.ac.uk" className="underline">
            British Antarctic Survey
          </a>{' '}
          (BAS) is part of{' '}
          <a href="https://www.ukri.org" className="underline">
            UK Research and Innovation
          </a>{' '}
          (UKRI)
        </span>
        <span>© {new Date().getFullYear()} British Antarctic Survey</span>
      </div>
    </footer>
  )
}
