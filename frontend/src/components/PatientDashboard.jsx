import { useState } from 'react'
import api from '../api.js'
import AddPrescriptionModal from './AddPrescriptionModal.jsx'
import ApprovalModal from './ApprovalModal.jsx'
import DelegatePanel from './DelegatePanel.jsx'
import FlagList, { indexFlags } from './Flags.jsx'
import RevokeGrantModal from './RevokeGrantModal.jsx'
import VaultPanel from './VaultPanel.jsx'
import { Badge, Banner, Empty, Panel, formatWhen, statusTone } from './ui.jsx'

function RequestCard({ request, onApprove, onDeny, busy, flags }) {
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

      {flags && <FlagList safety={flags.safety} fraud={flags.fraud} />}

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

function GrantCard({ grant, onRevoke }) {
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
          <span key={f} className={grant.status === 'active' ? 'chip on' : 'chip'}>
            {f}
          </span>
        ))}
      </div>

      <div className="spread" style={{ marginTop: 10 }}>
        <div>
          <div className="small faint">
            Signed by {grant.granted_by} · expires {formatWhen(grant.expires_at)}
          </div>
          <div className="hash" style={{ marginTop: 4 }}>
            sig {grant.signature?.slice(0, 32)}…
          </div>
        </div>
        {grant.status === 'active' && (
          <button className="danger" onClick={() => onRevoke(grant)}>
            Revoke
          </button>
        )}
      </div>
    </article>
  )
}

export default function PatientDashboard({
  patient,
  vault,
  requests,
  grants,
  delegates,
  flags,
  onRefresh,
}) {
  const [approving, setApproving] = useState(null)
  const [revoking, setRevoking] = useState(null)
  const [prescribing, setPrescribing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const { byRecord, byRequest } = indexFlags(flags)
  const allSafety = flags?.safety_flags || []
  const allFraud = flags?.fraud_flags || []
  const highCount = [...allSafety, ...allFraud].filter((f) => f.severity === 'high').length

  const pending = requests.filter((r) => r.status === 'pending')
  const settled = requests.filter((r) => r.status !== 'pending')
  const activeGrants = grants.filter((g) => g.status === 'active')
  const pastGrants = grants.filter((g) => g.status !== 'active')

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
          title="Clinical & fraud alerts"
          sub="Every new prescription is reviewed for interactions, allergy conflicts and diversion patterns"
          actions={
            <Badge tone={highCount ? 'danger' : allSafety.length + allFraud.length ? 'warn' : 'ok'}>
              {allSafety.length + allFraud.length} open
              {highCount ? ` · ${highCount} high` : ''}
            </Badge>
          }
        >
          {allSafety.length + allFraud.length === 0 ? (
            <Empty>No safety or fraud concerns on this vault.</Empty>
          ) : (
            <FlagList safety={allSafety} fraud={allFraud} dedupe />
          )}
        </Panel>

        <Panel
          title="Pending access requests"
          sub="Nothing is released until someone with authority signs"
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
                flags={byRequest[r.id]}
                onApprove={setApproving}
                onDeny={deny}
              />
            ))
          )}
        </Panel>

        <Panel
          title="Active access grants"
          sub="Revoke any of these at any time — it takes effect on the next read"
          actions={<Badge tone={activeGrants.length ? 'ok' : 'neutral'}>{activeGrants.length} active</Badge>}
        >
          {activeGrants.length === 0 ? (
            <Empty>No one currently holds access to this vault.</Empty>
          ) : (
            activeGrants.map((g) => <GrantCard key={g.id} grant={g} onRevoke={setRevoking} />)
          )}
        </Panel>

        <DelegatePanel patient={patient} delegates={delegates} onRefresh={onRefresh} />

        {pastGrants.length > 0 && (
          <Panel title="Revoked & expired grants" sub="Kept for the record, useless for access">
            {pastGrants.map((g) => (
              <GrantCard key={g.id} grant={g} onRevoke={() => {}} />
            ))}
          </Panel>
        )}

        {settled.length > 0 && (
          <Panel title="Settled requests" sub="Approved or denied">
            {settled.map((r) => (
              <RequestCard key={r.id} request={r} busy={busy} onApprove={() => {}} onDeny={() => {}} />
            ))}
          </Panel>
        )}
      </div>

      <VaultPanel
        vault={vault}
        actions={<button onClick={() => setPrescribing(true)}>+ New prescription</button>}
        renderRecordExtra={(record) =>
          byRecord[record.id] ? (
            <FlagList safety={byRecord[record.id].safety} fraud={byRecord[record.id].fraud} />
          ) : null
        }
      />

      {approving && (
        <ApprovalModal
          request={approving}
          patient={patient}
          delegates={delegates}
          onClose={() => {
            setApproving(null)
            onRefresh()
          }}
          onApproved={onRefresh}
        />
      )}

      {prescribing && (
        <AddPrescriptionModal
          patient={patient}
          onClose={() => {
            setPrescribing(false)
            onRefresh()
          }}
          onAdded={onRefresh}
        />
      )}

      {revoking && (
        <RevokeGrantModal
          grant={revoking}
          patient={patient}
          delegates={delegates}
          onClose={() => {
            setRevoking(null)
            onRefresh()
          }}
          onRevoked={onRefresh}
        />
      )}
    </div>
  )
}
