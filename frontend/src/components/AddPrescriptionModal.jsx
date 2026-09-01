import { useState } from 'react'
import api from '../api.js'
import FlagList from './Flags.jsx'
import Modal from './Modal.jsx'
import { Banner, Field } from './ui.jsx'

// The live demo moment: write a prescription into the vault and watch the two
// analysers run on it before the modal closes.
const PRESETS = [
  {
    label: 'Diclofenac (NSAID)',
    payload: {
      drug_name: 'Diclofenac',
      dosage: '50 mg',
      frequency: 'twice daily',
      prescriber_name: 'Dr. Sameer Joshi',
      prescriber_id: 'MCI-MH-55214',
      notes: 'Acute musculoskeletal pain.',
      quantity: 20,
      supply_days: 10,
    },
  },
  {
    label: 'Amoxicillin (beta-lactam)',
    payload: {
      drug_name: 'Amoxicillin',
      dosage: '500 mg',
      frequency: 'three times daily',
      prescriber_name: 'Dr. Kiran Shetty',
      prescriber_id: 'MCI-KA-77410',
      notes: 'Suspected bacterial sinusitis.',
      quantity: 21,
      supply_days: 7,
    },
  },
  {
    label: 'Tramadol (controlled)',
    payload: {
      drug_name: 'Tramadol',
      dosage: '50 mg',
      frequency: 'as needed for pain',
      prescriber_name: 'Dr. Vivek Menon',
      prescriber_id: 'MCI-KL-20558',
      notes: 'Chronic pain, patient reports lost script.',
      quantity: 60,
      supply_days: 30,
    },
  },
]

const blank = {
  drug_name: '',
  dosage: '',
  frequency: '',
  prescriber_name: '',
  prescriber_id: '',
  notes: '',
  quantity: 30,
  supply_days: 30,
}

export default function AddPrescriptionModal({ patient, onClose, onAdded }) {
  const [form, setForm] = useState(blank)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  async function submit() {
    setBusy(true)
    setError('')
    try {
      const created = await api.addRecord(patient.id, {
        record_type: 'prescription',
        payload: {
          ...form,
          quantity: Number(form.quantity) || 0,
          supply_days: Number(form.supply_days) || 0,
          date: new Date().toISOString().slice(0, 10),
        },
      })
      setResult(created)
      onAdded?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const flagCount =
    (result?.safety_flags?.length || 0) + (result?.fraud_flags?.length || 0)

  return (
    <Modal
      title="New prescription arrives"
      sub={`Written into ${patient?.name}'s vault, then reviewed by both analysers`}
      onClose={onClose}
      footer={
        result ? (
          <button className="primary" onClick={onClose}>
            Done
          </button>
        ) : (
          <>
            <button className="ghost" onClick={onClose}>
              Cancel
            </button>
            <button className="primary" disabled={busy || !form.drug_name.trim()} onClick={submit}>
              {busy ? 'Analysing…' : 'Add & analyse'}
            </button>
          </>
        )
      }
    >
      {!result && (
        <>
          <div>
            <label>Start from a preset</label>
            <div className="chip-list">
              {PRESETS.map((p) => (
                <span
                  key={p.label}
                  className="chip selectable"
                  onClick={() => setForm({ ...blank, ...p.payload })}
                >
                  {p.label}
                </span>
              ))}
            </div>
          </div>

          <div className="grid-2" style={{ gap: 14 }}>
            <Field label="Drug name">
              <input value={form.drug_name} onChange={set('drug_name')} placeholder="e.g. Ibuprofen" />
            </Field>
            <Field label="Dosage">
              <input value={form.dosage} onChange={set('dosage')} placeholder="e.g. 400 mg" />
            </Field>
            <Field label="Frequency">
              <input value={form.frequency} onChange={set('frequency')} placeholder="e.g. twice daily" />
            </Field>
            <Field label="Prescriber">
              <input value={form.prescriber_name} onChange={set('prescriber_name')} />
            </Field>
            <Field label="Prescriber ID">
              <input value={form.prescriber_id} onChange={set('prescriber_id')} />
            </Field>
            <Field label="Quantity">
              <input type="number" value={form.quantity} onChange={set('quantity')} />
            </Field>
            <Field label="Supply (days)">
              <input type="number" value={form.supply_days} onChange={set('supply_days')} />
            </Field>
          </div>

          <Field label="Notes">
            <textarea value={form.notes} onChange={set('notes')} />
          </Field>
        </>
      )}

      {error && <Banner tone="error">{error}</Banner>}

      {result && (
        <>
          {flagCount === 0 ? (
            <Banner tone="ok">
              Both analysers ran and found nothing to flag. An empty result is a valid
              answer — the system does not invent concerns.
            </Banner>
          ) : (
            <Banner tone="error">
              {flagCount} alert{flagCount > 1 ? 's' : ''} raised on this prescription.
            </Banner>
          )}
          <div>
            <FlagList safety={result.safety_flags} fraud={result.fraud_flags} />
          </div>
          <p className="small faint">
            Safety analysis: {result.safety_meta?.source}
            {result.safety_meta?.note ? ` (${result.safety_meta.note})` : ''} · Fraud rules
            fired: {result.fraud_meta?.rules_fired ?? 0}
          </p>
        </>
      )}
    </Modal>
  )
}
