export default function Modal({ title, sub, onClose, children, footer, wide = false }) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.()
      }}
    >
      <div className={wide ? 'modal wide' : 'modal'}>
        <header className="modal-head">
          <div>
            <h2>{title}</h2>
            {sub && <div className="small faint" style={{ marginTop: 4 }}>{sub}</div>}
          </div>
          <button className="close-x" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  )
}
