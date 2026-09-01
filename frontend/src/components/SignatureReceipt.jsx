import { Badge } from './ui.jsx'

// The evidence panel shown after any signed action. Phase 6 wraps this in the
// step-by-step crypto visualisation; the raw material is the same.
export default function SignatureReceipt({ receipt }) {
  if (!receipt) return null
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div>
        <div className="section-title">Canonical message that was signed</div>
        <div className="codebox accent">{receipt.canonical_message}</div>
      </div>
      <div>
        <div className="section-title">SHA-256 of message</div>
        <div className="codebox">{receipt.message_sha256}</div>
      </div>
      <div>
        <div className="section-title">Ed25519 signature</div>
        <div className="codebox">{receipt.signature}</div>
      </div>
      <div>
        <div className="section-title">Verified against public key</div>
        <div className="codebox">{receipt.public_key}</div>
      </div>
      <div className="row">
        <Badge tone="ok">verified</Badge>
        <span className="small dim">signed by {receipt.signed_by}</span>
      </div>
    </div>
  )
}

// Shared signer picker: the patient, or any of their currently-active delegates.
export function SignerPicker({ patient, delegates, value, onChange }) {
  const active = (delegates || []).filter((d) => d.status === 'active')
  return (
    <div>
      <label>Signing as</label>
      <div className="chip-list">
        <span
          className={`chip selectable ${value === 'patient' ? 'on' : ''}`}
          onClick={() => onChange('patient')}
        >
          {patient?.name} (data owner)
        </span>
        {active.map((d) => (
          <span
            key={d.id}
            className={`chip selectable ${value === `delegate:${d.id}` ? 'on' : ''}`}
            onClick={() => onChange(`delegate:${d.id}`)}
          >
            {d.delegate_name} ({d.relationship})
          </span>
        ))}
      </div>
      {active.length === 0 && (
        <p className="small faint" style={{ marginTop: 6 }}>
          No active delegates. Only {patient?.name} can sign.
        </p>
      )}
    </div>
  )
}

// The wire format the backend expects for a signer.
export const signerParam = (value) =>
  value === 'patient' ? 'patient' : { type: 'delegate', id: Number(value.split(':')[1]) }
