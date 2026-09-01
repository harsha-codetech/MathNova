import { useCallback, useEffect, useState } from 'react'
import api from './api.js'
import AuditLogPanel from './components/AuditLogPanel.jsx'
import PatientDashboard from './components/PatientDashboard.jsx'
import RequesterPortal from './components/RequesterPortal.jsx'
import { Banner } from './components/ui.jsx'

// There is no authentication anywhere in this app -- by design. The role
// switcher below IS the identity model for the demo: pick which mock patient
// you are, or step around the table and act as an organisation asking for data.

const REQUESTERS = [
  { name: 'Fortis Hospital, Mulund', type: 'hospital' },
  { name: 'Apollo Pharmacy, Indiranagar', type: 'pharmacy' },
  { name: 'SRL Diagnostics, T. Nagar', type: 'lab' },
  { name: 'MaxLife Insurance', type: 'insurer' },
]

const PATIENT_TABS = [
  { id: 'consent', label: 'Consent & Vault' },
  { id: 'audit', label: 'Audit Log' },
]

export default function App() {
  const [health, setHealth] = useState(null)
  const [patients, setPatients] = useState([])
  const [fields, setFields] = useState([])
  const [patientId, setPatientId] = useState(null)
  const [role, setRole] = useState('patient')
  const [requesterIndex, setRequesterIndex] = useState(0)
  const [tab, setTab] = useState('consent')

  const [vault, setVault] = useState(null)
  const [requests, setRequests] = useState([])
  const [grants, setGrants] = useState([])
  const [auditLog, setAuditLog] = useState(null)
  const [delegates, setDelegates] = useState([])
  const [flags, setFlags] = useState(null)
  const [requesterRequests, setRequesterRequests] = useState([])

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const requester = REQUESTERS[requesterIndex]

  useEffect(() => {
    let cancelled = false
    async function boot() {
      try {
        const [h, ps, f] = await Promise.all([
          api.health(),
          api.listPatients(),
          api.accessFields(),
        ])
        if (cancelled) return
        setHealth(h)
        setPatients(ps)
        setFields(f.fields || [])
        if (ps.length) setPatientId(ps[0].id)
      } catch (e) {
        if (!cancelled) setError(`Cannot reach the backend on :5000 — ${e.message}`)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    boot()
    return () => {
      cancelled = true
    }
  }, [])

  const refreshPatient = useCallback(async () => {
    if (!patientId) return
    try {
      const [v, rs, gs, ds, log, fl] = await Promise.all([
        api.vault(patientId),
        api.listRequests({ patient_id: patientId }),
        api.listGrants(patientId),
        api.listDelegates(patientId),
        api.auditLog(patientId),
        api.flags(patientId),
      ])
      setVault(v)
      setRequests(rs)
      setGrants(gs)
      setDelegates(ds)
      setAuditLog(log)
      setFlags(fl)
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [patientId])

  const refreshRequester = useCallback(async () => {
    try {
      setRequesterRequests(await api.listRequests({ requester_name: requester.name }))
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [requester.name])

  // Re-fetch on every role switch too: acting as a requester mutates the
  // patient's audit chain, so the patient view must not be stale when you flip
  // back to it mid-demo.
  useEffect(() => {
    if (role === 'patient') refreshPatient()
  }, [role, refreshPatient])

  useEffect(() => {
    if (role === 'requester') refreshRequester()
  }, [role, refreshRequester])

  // A patient action changes what a requester can read, and vice versa, so both
  // views are refreshed after either side acts.
  const refreshAll = useCallback(async () => {
    await Promise.all([refreshPatient(), refreshRequester()])
  }, [refreshPatient, refreshRequester])

  const patient = patients.find((p) => p.id === patientId) || null

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">MathNova</span>
          <span className="tagline">Patient-Sovereign Prescription Intelligence Network</span>
        </div>

        <div className="topbar-spacer" />

        <div className="role-switch">
          <div className="seg">
            <button className={role === 'patient' ? 'on' : ''} onClick={() => setRole('patient')}>
              Patient
            </button>
            <button
              className={role === 'requester' ? 'on' : ''}
              onClick={() => setRole('requester')}
            >
              Requester
            </button>
          </div>

          {role === 'patient' ? (
            <select
              value={patientId ?? ''}
              onChange={(e) => setPatientId(Number(e.target.value))}
              aria-label="Logged in as"
            >
              {patients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          ) : (
            <select
              value={requesterIndex}
              onChange={(e) => setRequesterIndex(Number(e.target.value))}
              aria-label="Acting as"
            >
              {REQUESTERS.map((r, i) => (
                <option key={r.name} value={i}>
                  {r.name} ({r.type})
                </option>
              ))}
            </select>
          )}

          <span className="row small faint">
            <span className={`status-dot ${health ? 'up' : 'down'}`} />
            {health ? 'API up' : 'API down'}
          </span>
        </div>
      </header>

      {role === 'patient' && (
        <nav className="tabs">
          {PATIENT_TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? 'on' : ''} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      )}

      <main className="page stack">
        {error && <Banner tone="error">{error}</Banner>}

        {loading ? (
          <div className="loading">Loading demo world…</div>
        ) : role === 'patient' ? (
          tab === 'consent' ? (
            <PatientDashboard
              patient={patient}
              vault={vault}
              requests={requests}
              grants={grants}
              delegates={delegates}
              flags={flags}
              onRefresh={refreshAll}
            />
          ) : (
            <AuditLogPanel log={auditLog} />
          )
        ) : (
          <RequesterPortal
            requester={requester}
            patients={patients}
            fields={fields}
            requests={requesterRequests}
            onRefresh={refreshAll}
          />
        )}
      </main>
    </div>
  )
}
