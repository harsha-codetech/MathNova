import { useCallback, useState } from 'react'
import { Badge } from './ui.jsx'

// The judging feature: the cryptography is shown happening, step by step, with
// the real bytes at each stage -- never hidden behind an unlabelled spinner.
//
// Steps are deliberately paced (~420ms apart) so a room can follow them. The
// work itself is real: the delay only sits between the two network calls the
// flow already makes.

export function CryptoSteps({ steps }) {
  return (
    <div className="crypto-steps">
      {steps.map((step, index) => (
        <div key={step.key} className={`cstep ${step.state}`}>
          <div className="rail">
            <div className="dot">
              {step.state === 'done' ? '✓' : step.state === 'failed' ? '✕' : index + 1}
            </div>
            {index < steps.length - 1 && <div className="line" />}
          </div>
          <div className="body">
            <div className="title">{step.title}</div>
            {step.state !== 'pending' && step.detail && (
              <div className="detail">{step.detail}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

export function useCryptoSteps(definition) {
  const [steps, setSteps] = useState(() =>
    definition.map((s) => ({ ...s, state: 'pending', detail: null })),
  )

  const reset = useCallback(
    () => setSteps(definition.map((s) => ({ ...s, state: 'pending', detail: null }))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  const patch = useCallback((key, changes) => {
    setSteps((current) => current.map((s) => (s.key === key ? { ...s, ...changes } : s)))
  }, [])

  const start = useCallback((key) => patch(key, { state: 'running' }), [patch])

  const complete = useCallback(
    async (key, detail, pause = 420) => {
      patch(key, { state: 'done', detail })
      await sleep(pause)
    },
    [patch],
  )

  const fail = useCallback((key, detail) => patch(key, { state: 'failed', detail }), [patch])

  return { steps, reset, start, complete, fail }
}

// Small helpers for step bodies.
export const Code = ({ children, accent = false }) => (
  <div className={accent ? 'codebox accent' : 'codebox'}>{children}</div>
)

export const Verified = ({ children }) => (
  <div className="row" style={{ marginTop: 6 }}>
    <Badge tone="ok">verified</Badge>
    <span className="small dim">{children}</span>
  </div>
)
