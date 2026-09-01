import { Badge, formatWhen, severityTone } from './ui.jsx'

const LABEL = {
  interaction: 'Drug interaction',
  allergy_conflict: 'Allergy conflict',
  dosage: 'Dosage concern',
  early_refill: 'Early refill',
  high_quantity: 'Unusual quantity',
  prescriber_shopping: 'Prescriber shopping',
  request_velocity: 'Request velocity',
  over_collection: 'Over-collection',
}

// Flags are shown as loud coloured cards with the full explanation text --
// never a bare icon, and never only in a log file.
export function FlagCard({ flag, kind, occurrences = 1 }) {
  return (
    <div className={`flag ${flag.severity}`}>
      <div className="flag-head">
        <Badge tone={kind === 'fraud' ? 'danger' : 'warn'}>
          {kind === 'fraud' ? 'fraud' : 'safety'}
        </Badge>
        <Badge tone={severityTone(flag.severity)}>{flag.severity}</Badge>
        <strong className="small">{LABEL[flag.flag_type] || flag.flag_type}</strong>
        {occurrences > 1 && (
          <span className="chip">raised on {occurrences} prescriptions</span>
        )}
        <span className="faint small" style={{ marginLeft: 'auto' }}>
          {flag.source === 'claude' ? 'Claude' : 'offline analyser'} · {formatWhen(flag.created_at)}
        </span>
      </div>
      <p className="flag-text">{flag.explanation}</p>
      {flag.triggered_rule && (
        <p className="small faint mono" style={{ marginTop: 6 }}>
          rule: {flag.triggered_rule}
        </p>
      )}
    </div>
  )
}

// The same warning can legitimately fire on several prescriptions (three
// tramadol scripts all clash with the same SSRI). Per-record we show each one;
// in the roll-up summary we collapse identical text into a single card with a
// count, so the panel stays readable on a projector.
function collapse(flags) {
  const groups = new Map()
  for (const f of flags) {
    const key = `${f.flag_type}|${f.explanation}`
    const existing = groups.get(key)
    if (existing) existing.occurrences += 1
    else groups.set(key, { flag: f, occurrences: 1 })
  }
  return [...groups.values()]
}

export default function FlagList({ safety = [], fraud = [], dedupe = false }) {
  if (safety.length === 0 && fraud.length === 0) return null
  const safetyItems = dedupe ? collapse(safety) : safety.map((f) => ({ flag: f, occurrences: 1 }))
  const fraudItems = dedupe ? collapse(fraud) : fraud.map((f) => ({ flag: f, occurrences: 1 }))
  return (
    <>
      {safetyItems.map(({ flag, occurrences }) => (
        <FlagCard key={`s${flag.id}`} flag={flag} kind="safety" occurrences={occurrences} />
      ))}
      {fraudItems.map(({ flag, occurrences }) => (
        <FlagCard key={`f${flag.id}`} flag={flag} kind="fraud" occurrences={occurrences} />
      ))}
    </>
  )
}

// Index flags by the record / request they belong to, so a card can render its
// own alerts without the parent knowing anything about flag shapes.
export function indexFlags(flags) {
  const byRecord = {}
  const byRequest = {}
  for (const f of flags?.safety_flags || []) {
    if (f.record_id) (byRecord[f.record_id] ||= { safety: [], fraud: [] }).safety.push(f)
  }
  for (const f of flags?.fraud_flags || []) {
    if (f.record_id) (byRecord[f.record_id] ||= { safety: [], fraud: [] }).fraud.push(f)
    if (f.access_request_id)
      (byRequest[f.access_request_id] ||= { safety: [], fraud: [] }).fraud.push(f)
  }
  return { byRecord, byRequest }
}
