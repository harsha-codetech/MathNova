import { useState } from 'react'
import api from '../api.js'
import ApprovalModal from './ApprovalModal.jsx'
import VaultPanel from './VaultPanel.jsx'
import { Badge, Banner, Empty, Panel, formatWhen, statusTone } from './ui.jsx'

function RequestCard({ request, onApprove, onDeny, busy }) {
  return (
    <article className="card">
      <div className="spread">
        <div className="row wrap">
          <strong>{request.requester_name}</strong>
          <Badge tone="info">{request.requester_type}</Badge>
          <Badge tone={statusTone(request.status)}>{request.status}</Badge>
        </div>
        <span className="faint mono">#{request.id}</span>
      </div>

      <p className="small dim" style={{ marginTop: 8 }}>
        {request.purpose}
      </p>

      <div className="row wrap" style={{ marginTop: 10 }}>
        <span className="small faint">Wants:</span>
        {(request.requested_fields || []).map((f) => (
          <span key={f} className="chip">
            {f}
          </span>
        ))}
      </div>

      <div className="spread" style={{ marginTop: 12 }}>
        <span className="small faint">{formatWhen(request.created_at)}</span>
        {request.status === 'pending' && (
          <div className="row">
            <button className="danger" disabled={busy} onClick={() => onDeny(request)}>
              Deny
            </button>
            <button className="primary" disabled={busy} onClick={() => onApprove(request)}>
              Review &amp; approve
            </button>
          </div>
        )}
      </div>
    </article>
  )
}

function GrantCard({ grant }) {
  return (
    <article className="card">
      <div className="spread">
        <div className="row wrap">
          <strong>{grant.requester_name || `request #${grant.access_request_id}`}</strong>
          {grant.requester_type && <Badge tone="info">{grant.requester_type}</Badge>}
          <Badge tone={statusTone(grant.status)}>{grant.status}</Badge>
        </div>
        <span className="faint mono">grant #{grant.id}</span>
      </div>

      <div className="row wrap" style={{ marginTop: 10 }}>
        <span className="small faint">Scope:</span>
        {(grant.scope || []).map((f) => (
          <span key={f} className="chip on">
            {f}
          </span>
        ))}
      </div>

      <div className="small faint" style={{ marginTop: 10 }}>
        Signed by {grant.granted_by} · expires {formatWhen(grant.expires_at)}
      </div>
      <div className="hash" style={{ marginTop: 6 }}>
        sig {grant.signature?.slice(0, 32)}…
      </div>
    </article>
  )
}

export default function PatientDashboard({ patient, vault, requests, grants, onRefresh }) {
  const [approving, setApproving] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const pending = requests.filter((r) => r.status === 'pending')
  const settled = requests.filter((r) => r.status !== 'pending')

  async function deny(request) {
    setBusy(true)
    setError('')
    try {
      await api.denyRequest(request.id, { signer: 'patient' })
      await onRefresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid-side">
      <div className="stack">
        {error && <Banner tone="error">{error}</Banner>}

        <Panel
          title="Pending access requests"
          sub="Nothing is released until you sign"
          actions={<Badge tone={pending.length ? 'warn' : 'neutral'}>{pending.length} waiting</Badge>}
        >
          {pending.length === 0 ? (
            <Empty>No one is waiting on your consent right now.</Empty>
          ) : (
            pending.map((r) => (
              <RequestCard
                key={r.id}
                request={r}
                busy={busy}
                onApprove={setApproving}
                onDeny={deny}
              />
            ))
          )}
        </Panel>

        <Panel
          title="Access grants"
          sub="Every grant is backed by a signature you produced"
          actions={
            <Badge tone="ok">{grants.filter((g) => g.status === 'active').length} active</Badge>
          }
        >
          {grants.length === 0 ? (
            <Empty>No grants issued yet.</Empty>
          ) : (
            grants.map((g) => <GrantCard key={g.id} grant={g} />)
          )}
        </Panel>

        {settled.length > 0 && (
          <Panel title="Settled requests" sub="Approved or denied">
            {settled.map((r) => (
              <RequestCard key={r.id} request={r} busy={busy} onApprove={() => {}} onDeny={() => {}} />
            ))}
          </Panel>
        )}
      </div>

      <VaultPanel vault={vault} />

      {approving && (
        <ApprovalModal
          request={approving}
          patient={patient}
          onClose={() => {
            setApproving(null)
            onRefresh()
          }}
          onApproved={onRefresh}
        />
      )}
    </div>
  )
}
