import { Badge, Empty, Panel } from './ui.jsx'

const TYPE_TONE = {
  prescription: 'info',
  allergy: 'danger',
  diagnostic: 'violet',
  report: 'neutral',
}

const TYPE_LABEL = {
  prescription: 'Prescriptions',
  allergy: 'Allergies',
  diagnostic: 'Diagnostics',
  report: 'Reports',
}

export function RecordCard({ record, extra }) {
  const p = record.payload || {}
  const title = p.drug_name || p.test_name || `${record.record_type} #${record.id}`
  const dose = [p.dosage, p.frequency, p.result && `Result: ${p.result}`]
    .filter(Boolean)
    .join(' · ')
  const meta = [p.prescriber_name, p.prescriber_id, p.date].filter(Boolean).join(' · ')
  return (
    <article className="card">
      <div className="spread">
        <div className="row">
          <strong>{title}</strong>
          <Badge tone={TYPE_TONE[record.record_type] || 'neutral'}>{record.record_type}</Badge>
        </div>
        <span className="faint mono">#{record.id}</span>
      </div>

      {dose && (
        <div className="small dim" style={{ marginTop: 6 }}>
          {dose}
        </div>
      )}

      {meta && (
        <div className="small faint mono" style={{ marginTop: 6 }}>
          {meta}
        </div>
      )}

      {p.notes && (
        <p className="small dim" style={{ marginTop: 8 }}>
          {p.notes}
        </p>
      )}

      {extra}
    </article>
  )
}

export default function VaultPanel({ vault, renderRecordExtra, actions }) {
  if (!vault) return null
  const byType = vault.by_type || {}
  const order = ['allergy', 'prescription', 'diagnostic', 'report']

  return (
    <Panel
      title="Health Vault"
      sub={`${vault.records?.length || 0} records — owned by ${vault.patient?.name}`}
      actions={actions}
    >
      <div className="stack">
        {order.map((type) => {
          const items = byType[type] || []
          return (
            <div key={type}>
              <div className="section-title">
                {TYPE_LABEL[type]} ({items.length})
              </div>
              {items.length === 0 ? (
                <Empty>No {type} records.</Empty>
              ) : (
                items.map((record) => (
                  <RecordCard
                    key={record.id}
                    record={record}
                    extra={renderRecordExtra ? renderRecordExtra(record) : null}
                  />
                ))
              )}
            </div>
          )
        })}
      </div>
    </Panel>
  )
}
