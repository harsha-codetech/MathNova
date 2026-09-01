import { Badge, Empty, Panel, formatWhen, shortHash } from './ui.jsx'

const ACTION_TONE = {
  request_created: 'info',
  approved_by_patient: 'ok',
  approved_by_delegate: 'violet',
  denied: 'danger',
  data_accessed: 'neutral',
  grant_revoked: 'danger',
  delegate_added: 'violet',
  delegate_revoked: 'danger',
  safety_flag: 'warn',
  fraud_flag: 'danger',
}

function summarise(entry) {
  const d = entry.details || {}
  switch (entry.action) {
    case 'request_created':
      return `asked for ${(d.requested_fields || []).join(', ')} — "${d.purpose}"`
    case 'approved_by_patient':
    case 'approved_by_delegate':
      return `granted ${(d.granted_fields || []).join(', ')} until ${formatWhen(d.expires_at)}`
    case 'denied':
      return d.reason || 'denied'
    case 'data_accessed':
      return d.outcome === 'ALLOWED'
        ? `read ${(d.fields || []).join(', ')} (${d.record_count} records)`
        : `BLOCKED — ${d.reason}`
    case 'grant_revoked':
      return `grant #${d.access_grant_id} revoked`
    case 'delegate_added':
      return `${d.delegate_name} authorised as ${d.relationship}`
    case 'delegate_revoked':
      return `${d.delegate_name} can no longer sign`
    case 'safety_flag':
      return `${d.flag_type} (${d.severity})`
    case 'fraud_flag':
      return `${d.flag_type} (${d.severity})`
    default:
      return JSON.stringify(d)
  }
}

export default function AuditLogPanel({ log }) {
  if (!log) return null
  const chain = log.chain || {}
  const entries = log.entries || []

  return (
    <Panel
      title="Hash-chained audit log"
      sub="entry_hash = SHA-256(entry fields + prev_entry_hash) — edit any row and every hash after it breaks"
      actions={
        chain.valid ? (
          <Badge tone="ok">chain intact · {chain.length} entries</Badge>
        ) : (
          <Badge tone="danger">chain broken at #{chain.broken_at}</Badge>
        )
      }
      tight
    >
      {!chain.valid && chain.reason && (
        <div className="banner error" style={{ margin: 16 }}>
          Tamper detected: {chain.reason}
        </div>
      )}

      {entries.length === 0 ? (
        <div style={{ padding: 16 }}>
          <Empty>Nothing has touched this vault yet.</Empty>
        </div>
      ) : (
        <div className="scroll-y">
          <table>
            <thead>
              <tr>
                <th style={{ width: 46 }}>#</th>
                <th style={{ width: 168 }}>When</th>
                <th style={{ width: 170 }}>Action</th>
                <th style={{ width: 210 }}>Actor</th>
                <th>Detail</th>
                <th style={{ width: 190 }}>hash ← prev</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <td className="faint mono">{entry.id}</td>
                  <td className="small dim">{formatWhen(entry.timestamp)}</td>
                  <td>
                    <Badge tone={ACTION_TONE[entry.action] || 'neutral'}>
                      {entry.action.replace(/_/g, ' ')}
                    </Badge>
                  </td>
                  <td className="small">{entry.actor}</td>
                  <td className="small dim">{summarise(entry)}</td>
                  <td className="hash">
                    {shortHash(entry.entry_hash, 6)}
                    <br />
                    <span className="faint">← {shortHash(entry.prev_entry_hash, 6)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}
