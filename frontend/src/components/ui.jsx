// Small shared primitives. Deliberately unstyled-by-props: everything reads
// from styles.css so the visual language stays in one file.

export function Panel({ title, sub, actions, children, tight = false }) {
  return (
    <section className="panel">
      {(title || actions) && (
        <header className="panel-head">
          <div>
            {title && <h2>{title}</h2>}
            {sub && <div className="sub">{sub}</div>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      <div className={tight ? 'panel-body tight' : 'panel-body'}>{children}</div>
    </section>
  )
}

export function Badge({ tone = 'neutral', children }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>
}

export function Banner({ tone = 'info', children }) {
  if (!children) return null
  return <div className={`banner ${tone}`}>{children}</div>
}

export function Field({ label, children }) {
  return (
    <div>
      <label>{label}</label>
      {children}
    </div>
  )
}

export const severityTone = (severity) =>
  ({ high: 'danger', medium: 'warn', low: 'info' }[severity] || 'neutral')

export const statusTone = (status) =>
  ({
    active: 'ok',
    approved: 'ok',
    pending: 'warn',
    denied: 'danger',
    revoked: 'danger',
    expired: 'neutral',
  }[status] || 'neutral')

export function shortHash(hash, size = 10) {
  if (!hash) return '—'
  return hash.length <= size * 2 ? hash : `${hash.slice(0, size)}…${hash.slice(-size)}`
}

export function formatWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
