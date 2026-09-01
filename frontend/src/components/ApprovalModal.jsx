import { useMemo, useState } from 'react'
import api from '../api.js'
import Modal from './Modal.jsx'
import { Badge, Banner, Field } from './ui.jsx'

const DURATIONS = [
  { label: '24 hours', hours: 24 },
  { label: '7 days', hours: 24 * 7 },
  { label: '30 days', hours: 24 * 30 },
]

export default function ApprovalModal({ request, patient, onClose, onApproved }) {
  const requested = request.requested_fields || []
  const [fields, setFields] = useState(requested)
  const [hours, setHours] = useState(24 * 7)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const expiresAt = useMemo(
    () => new Date(Date.now() + hours * 3600 * 1000).toISOString(),
    [hours],
  )

  const toggle = (field) =>
    setFields((current) =>
      current.includes(field) ? current.filter((f) => f !== field) : [...current, field],
    )

  async function signAndApprove() {
    setBusy(true)
    setError('')
    try {
      // Step 1 -- the "wallet" builds the canonical consent message and signs it.
      const signed = await api.sign({
        patient_id: request.patient_id,
        signer: 'patient',
        intent: 'approve_request',
        params: {
          request_id: request.id,
          granted_fields: fields,
          expires_at: expiresAt,
        },
      })

      // Step 2 -- the server independently rebuilds that message and verifies
      // the signature against the stored public key. It holds no private key.
      const approved = await api.approveRequest(request.id, {
        signature: signed.signature,
        signer: 'patient',
        granted_fields: fields,
        expires_at: expiresAt,
      })

      setResult({ ...signed, ...approved.verification, grant: approved.access_grant })
      onApproved?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={`Approve access for ${request.requester_name}`}
      sub={`${request.requester_type} · request #${request.id}`}
      onClose={onClose}
      footer={
        result ? (
          <button className="primary" onClick={onClose}>
            Done
          </button>
        ) : (
          <>
            <button className="ghost" onClick={onClose}>
              Cancel
            </button>
            <button
              className="primary"
              disabled={busy || fields.length === 0}
              onClick={signAndApprove}
            >
              {busy ? 'Signing…' : 'Sign & approve'}
            </button>
          </>
        )
      }
    >
      <div className="card">
        <div className="section-title">Stated purpose</div>
        <p className="small">{request.purpose}</p>
      </div>

      {!result && (
        <>
          <Field label="Grant only these fields (you may narrow the request)">
            <div className="chip-list">
              {requested.map((field) => (
                <span
                  key={field}
                  className={`chip selectable ${fields.includes(field) ? 'on' : ''}`}
                  onClick={() => toggle(field)}
                >
                  {fields.includes(field) ? '✓ ' : ''}
                  {field}
                </span>
              ))}
            </div>
          </Field>

          <Field label="Access expires after">
            <div className="chip-list">
              {DURATIONS.map((d) => (
                <span
                  key={d.hours}
                  className={`chip selectable ${hours === d.hours ? 'on' : ''}`}
                  onClick={() => setHours(d.hours)}
                >
                  {d.label}
                </span>
              ))}
            </div>
          </Field>

          <div>
            <div className="section-title">This is the exact message you will sign</div>
            <div className="codebox accent">
              {JSON.stringify(
                {
                  request_id: request.id,
                  granted_fields: [...fields].sort(),
                  expires_at: expiresAt,
                },
                null,
                0,
              )}
            </div>
            <p className="small faint" style={{ marginTop: 6 }}>
              Signed with {patient?.name}&apos;s Ed25519 private key. The server rebuilds this
              string from its own data and verifies the signature — it never sees a private key.
            </p>
          </div>
        </>
      )}

      {error && <Banner tone="error">{error}</Banner>}

      {result && (
        <div className="stack" style={{ gap: 12 }}>
          <Banner tone="ok">
            Signature verified ✓ — access grant #{result.grant.id} created, scoped to{' '}
            {result.grant.scope.join(', ')}.
          </Banner>
          <div>
            <div className="section-title">Signed message</div>
            <div className="codebox">{result.canonical_message}</div>
          </div>
          <div>
            <div className="section-title">SHA-256 of message</div>
            <div className="codebox">{result.message_sha256}</div>
          </div>
          <div>
            <div className="section-title">Ed25519 signature</div>
            <div className="codebox">{result.signature}</div>
          </div>
          <div>
            <div className="section-title">Verified against public key</div>
            <div className="codebox">{result.public_key}</div>
          </div>
          <div className="row">
            <Badge tone="ok">verified</Badge>
            <span className="small dim">signed by {result.signed_by}</span>
          </div>
        </div>
      )}
    </Modal>
  )
}
