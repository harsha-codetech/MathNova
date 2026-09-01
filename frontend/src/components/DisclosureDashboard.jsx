import { Badge, Empty, Panel, formatWhen, shortHash } from './ui.jsx'

const ACTION_LABEL = {
  request_created: 'requested access',
  approved_by_patient: 'granted by patient',
  approved_by_delegate: 'granted by delegate',
  denied: 'denied',
  data_accessed: 'read data',
  grant_revoked: 'access revoked',
}

const ACTION_TONE = {
  request_created: 'info',
  approved_by_patient: 'ok',
  approved_by_delegate: 'violet',
  denied: 'danger',
  data_accessed: 'neutral',
  grant_revoked: 'danger',
}

function Stat({ n, label, tone }) {
  return (
    <div className="card stat">
      <span className="n" style={tone ? { color: tone } : undefined}>
        {n}
      </span>
      <span className="l">{label}</span>
    </div>
  )
}

export default function DisclosureDashboard({ data, patient }) {
  if (!data) return <div className="loading">Loading disclosure history…</div>

  const t = data.totals || {}
  const requesters = data.requesters || []
  const timeline = data.timeline || []

  return (
    <div className="stack">
      <Panel
        title="Disclosure dashboard"
        sub={`Every organisation that has touched ${patient?.name ? `${patient.name}'s` : 'this'} vault, what they saw and why`}
        actions={
          data.chain?.valid ? (
            <Badge tone="ok">reconstructed from an intact hash chain</Badge>
          ) : (
            <Badge tone="danger">audit chain broken at #{data.chain?.broken_at}</Badge>
          )
        }
      >
        <div className="grid-3" style={{ gap: 12 }}>
          <Stat n={t.requesters ?? 0} label="Organisations" />
          <Stat n={t.requests ?? 0} label="Access requests" />
          <Stat n={t.active_grants ?? 0} label="Currently hold access" tone={t.active_grants ? '#6ee7b7' : null} />
          <Stat n={t.reads_allowed ?? 0} label="Reads allowed" />
          <Stat n={t.reads_blocked ?? 0} label="Reads blocked" tone={t.reads_blocked ? '#fca5a5' : null} />
          <Stat n={t.revocations ?? 0} label="Grants revoked" tone={t.revocations ? '#fcd34d' : null} />
        </div>
      </Panel>

      <Panel title="By requester" sub="Grouped access counts, purposes and recency" tight>
        {requesters.length === 0 ? (
          <div style={{ padding: 16 }}>
            <Empty>No one has ever requested this vault.</Empty>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Requester</th>
                <th style={{ width: 90 }}>Type</th>
                <th style={{ width: 78 }}>Requests</th>
                <th style={{ width: 66 }}>Reads</th>
                <th style={{ width: 190 }}>Fields seen</th>
                <th>Stated purposes</th>
                <th style={{ width: 170 }}>Last activity</th>
                <th style={{ width: 110 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {requesters.map((r) => (
                <tr key={r.requester_name}>
                  <td>
                    <strong>{r.requester_name}</strong>
                  </td>
                  <td>
                    <Badge tone="info">{r.requester_type}</Badge>
                  </td>
                  <td className="mono">
                    {r.requests}
                    {r.denials > 0 && <span className="faint"> ({r.denials} denied)</span>}
                  </td>
                  <td className="mono">
                    {r.reads_allowed}
                    {r.reads_blocked > 0 && (
                      <span style={{ color: '#fca5a5' }}> +{r.reads_blocked} blocked</span>
                    )}
                  </td>
                  <td>
                    <div className="chip-list">
                      {r.fields_seen.length === 0 ? (
                        <span className="faint small">nothing released</span>
                      ) : (
                        r.fields_seen.map((f) => (
                          <span key={f} className="chip on">
                            {f}
                          </span>
                        ))
                      )}
                    </div>
                  </td>
                  <td className="small dim">
                    {r.purposes.map((p, i) => (
                      <div key={i}>{p}</div>
                    ))}
                  </td>
                  <td className="small dim">{formatWhen(r.last_seen)}</td>
                  <td>
                    {r.active_grants > 0 ? (
                      <Badge tone="ok">holds access</Badge>
                    ) : r.revocations > 0 ? (
                      <Badge tone="danger">revoked</Badge>
                    ) : (
                      <Badge tone="neutral">no access</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel
        title="Disclosure timeline"
        sub="Newest first — each row is an entry in the tamper-evident chain"
        tight
      >
        {timeline.length === 0 ? (
          <div style={{ padding: 16 }}>
            <Empty>Nothing has been disclosed yet.</Empty>
          </div>
        ) : (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 170 }}>When</th>
                  <th style={{ width: 220 }}>Requester</th>
                  <th style={{ width: 170 }}>What happened</th>
                  <th style={{ width: 210 }}>Fields</th>
                  <th>Why</th>
                  <th style={{ width: 130 }}>Chain hash</th>
                </tr>
              </thead>
              <tbody>
                {timeline.map((row) => (
                  <tr key={row.entry_id}>
                    <td className="small dim">{formatWhen(row.timestamp)}</td>
                    <td className="small">
                      <strong>{row.requester_name}</strong>
                      <div className="faint">{row.requester_type}</div>
                    </td>
                    <td>
                      <Badge tone={ACTION_TONE[row.action] || 'neutral'}>
                        {ACTION_LABEL[row.action] || row.action.replace(/_/g, ' ')}
                      </Badge>
                      {row.outcome === 'DENIED' && (
                        <div style={{ marginTop: 4 }}>
                          <Badge tone="danger">blocked</Badge>
                        </div>
                      )}
                    </td>
                    <td>
                      <div className="chip-list">
                        {(row.fields || []).map((f) => (
                          <span key={f} className="chip">
                            {f}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="small dim">{row.purpose}</td>
                    <td className="hash">{shortHash(row.entry_hash, 6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
