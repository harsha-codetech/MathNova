import { useState } from 'react'
import api from '../api.js'
import Modal from './Modal.jsx'
import SignatureReceipt, { SignerPicker, signerParam } from './SignatureReceipt.jsx'
import { Banner } from './ui.jsx'

// Mid-grant revocation: consent already given is withdrawn *before* it expires,
// and the withdrawal is itself a signed act.
export default function RevokeGrantModal({ grant, patient, delegates, onClose, onRevoked }) {
  const [signer, setSigner] = useState('patient')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  async function signAndRevoke() {
    setBusy(true)
    setError('')
    try {
      const signed = await api.sign({
        patient_id: grant.patient_id,
        signer: signerParam(signer),
        intent: 'revoke_grant',
        params: { grant_id: grant.id },
      })
      const revoked = await api.revokeGrant(grant.id, {
        signature: signed.signature,
        signer: signerParam(signer),
      })
      setResult(revoked.verification)
      onRevoked?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={`Revoke access for ${grant.requester_name || `grant #${grant.id}`}`}
      sub={`grant #${grant.id} · ${(grant.scope || []).join(', ')}`}
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
            <button className="danger" disabled={busy} onClick={signAndRevoke}>
              {busy ? 'Signing…' : 'Sign & revoke'}
            </button>
          </>
        )
      }
    >
      {!result && (
        <>
          <Banner tone="info">
            This grant is still valid until {new Date(grant.expires_at).toLocaleString()}.
            Revoking now cuts it off immediately — the next read attempt is refused, not
            merely hidden.
          </Banner>

          <SignerPicker
            patient={patient}
            delegates={delegates}
            value={signer}
            onChange={setSigner}
          />

          <div>
            <div className="section-title">Message to be signed</div>
            <div className="codebox accent">
              {JSON.stringify({ action: 'revoke', grant_id: grant.id })}
            </div>
          </div>
        </>
      )}

      {error && <Banner tone="error">{error}</Banner>}

      {result && (
        <>
          <Banner tone="ok">
            Revocation signature verified ✓ — grant #{grant.id} is now inactive.
          </Banner>
          <SignatureReceipt receipt={result} />
        </>
      )}
    </Modal>
  )
}
