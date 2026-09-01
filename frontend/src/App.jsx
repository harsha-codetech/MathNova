import { useCallback, useEffect, useState } from 'react'
import api from './api.js'
import { Banner } from './components/ui.jsx'
import VaultPanel from './components/VaultPanel.jsx'

// There is no authentication anywhere in this app -- by design. The role
// switcher below IS the identity model for the demo: pick which mock patient
// you are, or flip to the requester side of the table.

export default function App() {
  const [health, setHealth] = useState(null)
  const [patients, setPatients] = useState([])
  const [patientId, setPatientId] = useState(null)
  const [role, setRole] = useState('patient') // patient | requester
  const [vault, setVault] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function boot() {
      try {
        const [h, ps] = await Promise.all([api.health(), api.listPatients()])
        if (cancelled) return
        setHealth(h)
        setPatients(ps)
        if (ps.length) setPatientId(ps[0].id)
      } catch (e) {
        if (!cancelled) setError(`Cannot reach the backend: ${e.message}`)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    boot()
    return () => {
      cancelled = true
    }
  }, [])

  const loadVault = useCallback(async (id) => {
    if (!id) return
    try {
      setVault(await api.vault(id))
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    loadVault(patientId)
  }, [patientId, loadVault])

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
            <button className={role === 'requester' ? 'on' : ''} onClick={() => setRole('requester')}>
              Requester
            </button>
          </div>

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

          <span className="row small faint" title={health ? 'API reachable' : 'API unreachable'}>
            <span className={`status-dot ${health ? 'up' : 'down'}`} />
            {health ? 'API up' : 'API down'}
          </span>
        </div>
      </header>

      <main className="page stack">
        {error && <Banner tone="error">{error}</Banner>}

        {loading ? (
          <div className="loading">Loading demo world…</div>
        ) : role === 'patient' ? (
          <>
            <Banner tone="info">
              Logged in as <strong>{patient?.name}</strong>. Everything below belongs to this
              patient — the only read path that needs no cryptographic grant.
            </Banner>
            <VaultPanel vault={vault} />
          </>
        ) : (
          <Banner tone="info">
            Requester portal arrives in phase 3, once the signature-backed access-control API
            exists.
          </Banner>
        )}
      </main>
    </div>
  )
}
