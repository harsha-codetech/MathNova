// Thin fetch wrapper. All calls go through the Vite proxy to Flask on :5000.

const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  let body = null
  const text = await res.text()
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = { error: text }
    }
  }

  if (!res.ok) {
    const message = (body && (body.error || body.message)) || `HTTP ${res.status}`
    const err = new Error(message)
    err.status = res.status
    err.body = body
    throw err
  }
  return body
}

const get = (path) => request(path)
const post = (path, payload) =>
  request(path, { method: 'POST', body: JSON.stringify(payload ?? {}) })

const qs = (params) =>
  Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&')

export const api = {
  health: () => get('/health'),
  listPatients: () => get('/patients'),
  vault: (patientId) => get(`/patients/${patientId}/vault`),
  addRecord: (patientId, payload) => post(`/patients/${patientId}/records`, payload),

  accessFields: () => get('/access-fields'),

  listRequests: (params) => get(`/access-requests?${qs(params)}`),
  createRequest: (payload) => post('/access-requests', payload),
  approveRequest: (id, payload) => post(`/access-requests/${id}/approve`, payload),
  denyRequest: (id, payload) => post(`/access-requests/${id}/deny`, payload),

  listGrants: (patientId) => get(`/access-grants?${qs({ patient_id: patientId })}`),
  revokeGrant: (id, payload) => post(`/access-grants/${id}/revoke`, payload),
  fetchRecords: (params) => get(`/records?${qs(params)}`),

  listDelegates: (patientId) => get(`/patients/${patientId}/delegates`),
  addDelegate: (patientId, payload) => post(`/patients/${patientId}/delegates`, payload),
  revokeDelegate: (id, payload) => post(`/delegates/${id}/revoke`, payload),

  auditLog: (patientId) => get(`/patients/${patientId}/audit-log`),
  flags: (patientId) => get(`/patients/${patientId}/flags`),
  disclosureDashboard: (patientId) => get(`/patients/${patientId}/disclosure-dashboard`),

  // Demo stand-in for a client-side wallet. See backend/routes/wallet.py.
  sign: (payload) => post('/wallet/sign', payload),
}

export default api
