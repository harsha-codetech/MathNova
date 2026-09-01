import { useState } from 'react'
import api from '../api.js'
import Modal from './Modal.jsx'
import SignatureReceipt from './SignatureReceipt.jsx'
import { Badge, Banner, Empty, Field, Panel, formatWhen, statusTone } from './ui.jsx'

function AddDelegateModal({ patient, onClose, onAdded }) {
  const [name, setName] = useState('')
  const [relationship, setRelationship] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  async function signAndAdd() {
    setBusy(true)
    setError('')
    try {
      const signed = await api.sign({
        patient_id: patient.id,
        signer: 'patient',
        intent: 'add_delegate',
        params: {
          patient_id: patient.id,
          delegate_name: name.trim(),
          relationship: relationship.trim(),
        },
      })
      const created = await api.addDelegate(patient.id, {
        delegate_name: name.trim(),
        relationship: relationship.trim(),
        signature: signed.signature,
      })
      setResult({ ...created.verification, delegate: created.delegate })
      onAdded?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Authorise a delegate"
      sub="Only the data owner can appoint someone to consent on their behalf"
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
              disabled={busy || !name.trim() || !relationship.trim()}
              onClick={signAndAdd}
            >
              {busy ? 'Signing…' : 'Sign & authorise'}
            </button>
          </>
        )
      }
    >
      {!result && (
        <>
          <Banner tone="info">
            The delegate gets their own Ed25519 keypair. Anything they approve verifies
            against <em>their</em> key and is logged as{' '}
            <span className="mono">approved_by_delegate</span> — never mistakable for{' '}
            {patient?.name}&apos;s own signature.
          </Banner>

          <Field label="Delegate name">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Kavita Deshmukh"
            />
          </Field>
          <Field label="Relationship">
            <input
              value={relationship}
              onChange={(e) => setRelationship(e.target.value)}
              placeholder="e.g. Spouse, Daughter, Primary caregiver"
            />
          </Field>

          <div>
            <div className="section-title">Message {patient?.name} will sign</div>
            <div className="codebox accent">
              {JSON.stringify({
                action: 'add_delegate',
                delegate_name: name.trim(),
                patient_id: patient?.id,
                relationship: relationship.trim(),
              })}
            </div>
          </div>
        </>
      )}

      {error && <Banner tone="error">{error}</Banner>}

      {result && (
        <>
          <Banner tone="ok">
            Signature verified ✓ — {result.delegate.delegate_name} is now an active delegate.
          </Banner>
          <SignatureReceipt receipt={result} />
        </>
      )}
    </Modal>
  )
}

function RevokeDelegateModal({ delegate, patient, onClose, onRevoked }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  async function signAndRevoke() {
    setBusy(true)
    setError('')
    try {
      const signed = await api.sign({
        patient_id: patient.id,
        signer: 'patient',
        intent: 'revoke_delegate',
        params: { delegate_id: delegate.id },
      })
      const revoked = await api.revokeDelegate(delegate.id, {
        signature: signed.signature,
        signer: 'patient',
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
      title={`Revoke ${delegate.delegate_name}'s authority`}
      sub={`${delegate.relationship} · delegate #${delegate.id}`}
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
            After revocation the backend refuses any signature from this key — existing
            grants they already signed stay valid until you revoke those separately.
          </Banner>
          <div>
            <div className="section-title">Message to be signed</div>
            <div className="codebox accent">
              {JSON.stringify({ action: 'revoke', delegate_id: delegate.id })}
            </div>
          </div>
        </>
      )}

      {error && <Banner tone="error">{error}</Banner>}

      {result && (
        <>
          <Banner tone="ok">
            Verified ✓ — {delegate.delegate_name} can no longer sign on{' '}
            {patient?.name}&apos;s behalf.
          </Banner>
          <SignatureReceipt receipt={result} />
        </>
      )}
    </Modal>
  )
}

export default function DelegatePanel({ patient, delegates, onRefresh }) {
  const [adding, setAdding] = useState(false)
  const [revoking, setRevoking] = useState(null)

  const activeCount = (delegates || []).filter((d) => d.status === 'active').length

  return (
    <>
      <Panel
        title="Delegates"
        sub="Proxy consent for when the patient cannot sign themselves"
        actions={
          <>
            <Badge tone={activeCount ? 'violet' : 'neutral'}>{activeCount} active</Badge>
            <button onClick={() => setAdding(true)}>Add delegate</button>
          </>
        }
      >
        {(delegates || []).length === 0 ? (
          <Empty>No delegates authorised.</Empty>
        ) : (
          delegates.map((d) => (
            <article className="card" key={d.id}>
              <div className="spread">
                <div className="row wrap">
                  <strong>{d.delegate_name}</strong>
                  <span className="small faint">{d.relationship}</span>
                  <Badge tone={statusTone(d.status)}>{d.status}</Badge>
                </div>
                {d.status === 'active' && (
                  <button className="danger" onClick={() => setRevoking(d)}>
                    Revoke
                  </button>
                )}
              </div>
              <div className="hash" style={{ marginTop: 8 }}>
                pubkey {d.delegate_public_key?.slice(0, 32)}…
              </div>
              <div className="small faint" style={{ marginTop: 4 }}>
                authorised {formatWhen(d.created_at)}
              </div>
            </article>
          ))
        )}
      </Panel>

      {adding && (
        <AddDelegateModal
          patient={patient}
          onClose={() => {
            setAdding(false)
            onRefresh()
          }}
          onAdded={onRefresh}
        />
      )}

      {revoking && (
        <RevokeDelegateModal
          delegate={revoking}
          patient={patient}
          onClose={() => {
            setRevoking(null)
            onRefresh()
          }}
          onRevoked={onRefresh}
        />
      )}
    </>
  )
}
