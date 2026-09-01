import { useState } from 'react'
import api from '../api.js'
import FlagList from './Flags.jsx'
import { RecordCard } from './VaultPanel.jsx'
import { Badge, Banner, Empty, Field, Panel, formatWhen, statusTone } from './ui.jsx'

export default function RequesterPortal({
  requester,
  patients,
  fields: allFields,
  requests,
  onRefresh,
}) {
  const [targetPatient, setTargetPatient] = useState(patients[0]?.id ?? null)
  const [selected, setSelected] = useState(['prescriptions'])
  const [purpose, setPurpose] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  // Fraud heuristics also run on the consent side, so a requester sees when
  // their own request pattern has been flagged to the patient.
  const [submitFlags, setSubmitFlags] = useState([])

  // Fetched payloads keyed by grant id, plus per-grant errors when the consent
  // engine refuses (revoked / expired / out of scope).
  const [fetched, setFetched] = useState({})
  const [fetchErrors, setFetchErrors] = useState({})

  const toggle = (field) =>
    setSelected((current) =>
      current.includes(field) ? current.filter((f) => f !== field) : [...current, field],
    )

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const created = await api.createRequest({
        requester_name: requester.name,
        requester_type: requester.type,
        patient_id: targetPatient,
        requested_fields: selected,
        purpose,
      })
      setNotice(
        `Request #${created.access_request.id} submitted. Nothing is readable until the patient signs.`,
      )
      setSubmitFlags(created.fraud_flags || [])
      setPurpose('')
      await onRefresh()
    } catch (e2) {
      setError(e2.message)
    } finally {
      setBusy(false)
    }
  }

  async function fetchData(grant, request) {
    setFetchErrors((prev) => ({ ...prev, [grant.id]: null }))
    try {
      const data = await api.fetchRecords({
        patient_id: request.patient_id,
        access_grant_id: grant.id,
      })
      setFetched((prev) => ({ ...prev, [grant.id]: data }))
      // The read just wrote a `data_accessed` entry to the patient's chain --
      // refresh so flipping back to the patient view shows it immediately.
      onRefresh()
    } catch (e) {
      setFetched((prev) => ({ ...prev, [grant.id]: null }))
      setFetchErrors((prev) => ({ ...prev, [grant.id]: e.message }))
    }
  }

  const patientName = (id) => patients.find((p) => p.id === id)?.name || `patient #${id}`

  return (
    <div className="grid-side">
      <div className="stack">
        <Panel title="Request access" sub={`Acting as ${requester.name} (${requester.type})`}>
          <form className="stack" style={{ gap: 16 }} onSubmit={submit}>
            <Field label="Patient">
              <select
                value={targetPatient ?? ''}
                onChange={(e) => setTargetPatient(Number(e.target.value))}
              >
                {patients.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Fields requested">
              <div className="chip-list">
                {allFields.map((f) => (
                  <span
                    key={f}
                    className={`chip selectable ${selected.includes(f) ? 'on' : ''}`}
                    onClick={() => toggle(f)}
                  >
                    {selected.includes(f) ? '✓ ' : ''}
                    {f}
                  </span>
                ))}
              </div>
            </Field>

            <Field label="Purpose (shown to the patient verbatim)">
              <textarea
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                placeholder="e.g. Verify current anticoagulant therapy before a dental extraction."
              />
            </Field>

            {error && <Banner tone="error">{error}</Banner>}
            {notice && <Banner tone="ok">{notice}</Banner>}
            {submitFlags.length > 0 && (
              <div>
                <Banner tone="error">
                  This request tripped {submitFlags.length} fraud heuristic
                  {submitFlags.length > 1 ? 's' : ''} and the patient will see the
                  explanation alongside it.
                </Banner>
                <FlagList fraud={submitFlags} />
              </div>
            )}

            <div>
              <button
                className="primary"
                type="submit"
                disabled={busy || !purpose.trim() || selected.length === 0}
              >
                {busy ? 'Submitting…' : 'Submit access request'}
              </button>
            </div>
          </form>
        </Panel>
      </div>

      <Panel
        title="My requests & granted data"
        sub="Data only appears once a patient has signed"
        actions={<Badge tone="neutral">{requests.length} total</Badge>}
      >
        {requests.length === 0 ? (
          <Empty>No requests submitted yet.</Empty>
        ) : (
          requests.map((request) => {
            const grants = request.grants || []
            return (
              <article className="card" key={request.id}>
                <div className="spread">
                  <div className="row wrap">
                    <strong>{patientName(request.patient_id)}</strong>
                    <Badge tone={statusTone(request.status)}>{request.status}</Badge>
                  </div>
                  <span className="faint mono">#{request.id}</span>
                </div>

                <p className="small dim" style={{ marginTop: 6 }}>
                  {request.purpose}
                </p>
                <div className="row wrap" style={{ marginTop: 8 }}>
                  {(request.requested_fields || []).map((f) => (
                    <span key={f} className="chip">
                      {f}
                    </span>
                  ))}
                </div>
                <div className="small faint" style={{ marginTop: 8 }}>
                  {formatWhen(request.created_at)}
                </div>

                {grants.map((grant) => (
                  <div key={grant.id} style={{ marginTop: 12 }}>
                    <div className="divider" />
                    <div className="spread" style={{ marginTop: 10 }}>
                      <div className="row wrap">
                        <span className="small faint mono">grant #{grant.id}</span>
                        <Badge tone={statusTone(grant.status)}>{grant.status}</Badge>
                        {(grant.scope || []).map((f) => (
                          <span key={f} className="chip on">
                            {f}
                          </span>
                        ))}
                      </div>
                      <button onClick={() => fetchData(grant, request)}>Fetch data</button>
                    </div>

                    {fetchErrors[grant.id] && (
                      <div style={{ marginTop: 10 }}>
                        <Banner tone="error">Access denied — {fetchErrors[grant.id]}</Banner>
                      </div>
                    )}

                    {fetched[grant.id] && (
                      <div style={{ marginTop: 10 }}>
                        <Banner tone="ok">
                          {fetched[grant.id].records.length} records released for{' '}
                          {fetched[grant.id].fields.join(', ')} — logged to the patient&apos;s
                          audit chain.
                        </Banner>
                        <div style={{ marginTop: 10 }}>
                          {fetched[grant.id].records.map((record) => (
                            <RecordCard key={record.id} record={record} />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </article>
            )
          })
        )}
      </Panel>
    </div>
  )
}
