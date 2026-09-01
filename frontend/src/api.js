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

export const api = {
  health: () => get('/health'),
  listPatients: () => get('/patients'),
  vault: (patientId) => get(`/patients/${patientId}/vault`),
  addRecord: (patientId, payload) => post(`/patients/${patientId}/records`, payload),
}

export default api
