# Nova — Person 3

**Area of ownership: the frontend, the demo experience, and the seeded demo world.**

This branch carries the full working system; the files below are the ones this
contributor owns and is the point of contact for.

## Owned

| File | What it does |
| --- | --- |
| `frontend/src/App.jsx` | Role switcher, tabs, all data loading and cross-role refresh |
| `frontend/src/api.js` | Fetch wrapper, proxied to Flask by Vite |
| `frontend/src/styles.css` | The whole design system — one file, no component library |
| `frontend/src/components/CryptoSteps.jsx` | **The judging feature**: the six real crypto steps, shown happening |
| `frontend/src/components/ApprovalModal.jsx` | Scope narrowing, expiry, signer choice, the stepped sign-and-verify flow |
| `frontend/src/components/PatientDashboard.jsx` | Vault, approval queue, grants, delegates, alerts |
| `frontend/src/components/RevokeGrantModal.jsx`, `DelegatePanel.jsx` | Signed revocation and delegate management |
| `frontend/src/components/RequesterPortal.jsx` | The other side of the table: request, then read only what was granted |
| `frontend/src/components/DisclosureDashboard.jsx` | Who saw what, when, why |
| `frontend/src/components/AuditLogPanel.jsx` | The chain, with a live `chain intact` pill |
| `frontend/src/components/Flags.jsx` | Safety and fraud badges with full explanation text |
| `backend/seed.py` | The demo world: patients, delegates, consent history, clinical scenarios |

## Design decisions worth defending in a review

- **The cryptography is shown, not hidden.** `CryptoSteps` walks the six real stages —
  canonical payload → SHA-256 → Ed25519 signature → server rebuilds the message
  independently → verified against the stored public key → grant issued and chained — and
  prints the actual byte string produced at each one. The ~420ms pacing exists so a room can
  follow it; the work itself is real, and a failure marks the exact step that failed rather
  than collapsing into a generic error toast.
- **Flags are loud, coloured cards with the full explanation**, never a bare icon. Severity
  drives the left border and the badge. In the roll-up panel identical warnings collapse to
  one card with a count, so a projector view stays readable; per record, each prescription
  still shows its own.
- **Both sides of the table in one app.** The role switcher lets a presenter act as the
  patient and then as the hospital without logging in or out, and every action on one side
  refreshes the other — the moment where a revoked grant turns into a refused read is the
  whole pitch, and it has to be one click away.
- **Laptop-first, deliberately.** No breakpoints, no mobile layout: high contrast and
  generous type so the back row can read the audit hashes.
- **Seeded history is real, not fixtures.** Every seeded grant is produced by genuinely
  signing and verifying the canonical payload, and the clinical scenarios run through the
  live analyser pipeline. If the crypto or the analysers were broken, `seed.py` would fail
  rather than quietly writing plausible-looking rows. Each patient's chain is backdated so
  it reads chronologically as well as being hash-ordered.

## The three seeded stories

- **Ananya Iyer** — a completed *request → grant → read → revoke* cycle, an active grant, a
  pending request, and a revoked delegate. The disclosure dashboard has content on first load.
- **Rohit Deshmukh** — the delegated-consent story (his spouse signed while he was sedated)
  and the seeded safety flag (an NSAID on top of warfarin).
- **Meera Krishnan** — the fraud story (Tramadol from three prescribers in 30 days) and the
  live allergy-conflict demo (add the Diclofenac preset and watch it fire).
