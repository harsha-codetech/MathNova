import { useMemo, useState } from 'react'
import api from '../api.js'
import { Code, CryptoSteps, Verified, useCryptoSteps } from './CryptoSteps.jsx'
import Modal from './Modal.jsx'
import { SignerPicker, signerParam } from './SignatureReceipt.jsx'
import { Banner, Field } from './ui.jsx'

const DURATIONS = [
  { label: '24 hours', hours: 24 },
  { label: '7 days', hours: 24 * 7 },
  { label: '30 days', hours: 24 * 30 },
]

// The six steps are the actual mechanism, in order. Nothing here is theatre:
// each one is filled in with the real value produced at that stage.
const STEP_DEFS = [
  { key: 'canonical', title: 'Build the canonical consent payload' },
  { key: 'digest', title: 'SHA-256 digest of the exact bytes to be signed' },
  { key: 'sign', title: 'Sign with the Ed25519 private key (the wallet step)' },
  { key: 'rebuild', title: 'Server independently rebuilds the message from its own records' },
  { key: 'verify', title: 'Server verifies the signature against the stored public key' },
  { key: 'commit', title: 'Grant issued and appended to the hash-chained audit log' },
]

export default function ApprovalModal({ request, patient, delegates, onClose, onApproved }) {
  const requested = request.requested_fields || []
  const [fields, setFields] = useState(requested)
  const [hours, setHours] = useState(24 * 7)
  const [signer, setSigner] = useState('patient')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [grant, setGrant] = useState(null)
  const [running, setRunning] = useState(false)

  const { steps, start, complete, fail } = useCryptoSteps(STEP_DEFS)

  const expiresAt = useMemo(
    () => new Date(Date.now() + hours * 3600 * 1000).toISOString(),
    [hours],
  )

  const preview = useMemo(
    () =>
      JSON.stringify({
        expires_at: expiresAt,
        granted_fields: [...fields].sort(),
        request_id: request.id,
      }),
    [expiresAt, fields, request.id],
  )

  const toggle = (field) =>
    setFields((current) =>
      current.includes(field) ? current.filter((f) => f !== field) : [...current, field],
    )

  async function signAndApprove() {
    setBusy(true)
    setRunning(true)
    setError('')
    // Tracked locally rather than read back from `steps`: the state in this
    // closure is the pre-run snapshot, so it cannot tell us where we failed.
    let current = null
    const begin = (key) => {
      current = key
      start(key)
    }
    try {
      begin('canonical')
      await complete('canonical', <Code accent>{preview}</Code>)

      // The wallet builds the same payload, hashes it and signs it. In a real
      // deployment this happens in the browser and the key never leaves it.
      begin('digest')
      const signed = await api.sign({
        patient_id: request.patient_id,
        signer: signerParam(signer),
        intent: 'approve_request',
        params: {
          request_id: request.id,
          granted_fields: fields,
          expires_at: expiresAt,
        },
      })
      await complete('digest', <Code>{signed.message_sha256}</Code>)

      begin('sign')
      await complete(
        'sign',
        <>
          <Code>{signed.signature}</Code>
          <div className="small faint" style={{ marginTop: 6 }}>
            signed by {signed.signer_label}
          </div>
        </>,
      )

      begin('rebuild')
      // The server is handed the signature and the claimed parameters -- never
      // the message itself. It reconstructs the message from its own row.
      const approved = await api.approveRequest(request.id, {
        signature: signed.signature,
        signer: signerParam(signer),
        granted_fields: fields,
        expires_at: expiresAt,
      })
      const v = approved.verification
      await complete(
        'rebuild',
        <>
          <Code>{v.canonical_message}</Code>
          <div className="small faint" style={{ marginTop: 6 }}>
            {v.canonical_message === signed.canonical_message
              ? 'byte-identical to what was signed ✓'
              : 'does not match what was signed'}
          </div>
        </>,
      )

      begin('verify')
      await complete(
        'verify',
        <>
          <Code>{v.public_key}</Code>
          <Verified>Ed25519 signature valid — signed by {v.signed_by}</Verified>
        </>,
      )

      begin('commit')
      await complete(
        'commit',
        <div className="small dim">
          Grant #{approved.access_grant.id} · scope{' '}
          {approved.access_grant.scope.join(', ')} · expires{' '}
          {new Date(approved.access_grant.expires_at).toLocaleString()}
        </div>,
        0,
      )

      setGrant(approved.access_grant)
      onApproved?.()
    } catch (e) {
      if (current) fail(current, <span className="small">{e.message}</span>)
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
      wide={running}
      footer={
        grant ? (
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

      {!running && (
        <>
          <SignerPicker
            patient={patient}
            delegates={delegates}
            value={signer}
            onChange={setSigner}
          />

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
            <Code accent>{preview}</Code>
            <p className="small faint" style={{ marginTop: 6 }}>
              The server rebuilds this string from its own data and verifies the signature
              against the stored public key — it never sees a private key.
            </p>
          </div>
        </>
      )}

      {running && (
        <div>
          <div className="section-title">What is actually happening</div>
          <CryptoSteps steps={steps} />
        </div>
      )}

      {error && <Banner tone="error">{error}</Banner>}

      {grant && (
        <Banner tone="ok">
          Signature verified ✓ — access grant #{grant.id} created, scoped to{' '}
          {grant.scope.join(', ')}. Revoke it at any time from the dashboard.
        </Banner>
      )}
    </Modal>
  )
}
