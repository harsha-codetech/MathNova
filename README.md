# MathNova

**Patient-Sovereign, Signature-Verified Prescription Intelligence Network**

A patient-centric health-record platform where the patient is the sole owner of their
medical data. Every access by a hospital, pharmacy, lab or insurer must be backed by a
cryptographic signature the patient (or an authorised delegate) explicitly created — not a
login, not an admin override, not a role.

On top of that consent layer, an AI layer reviews every new prescription for drug
interactions, allergy conflicts and unsafe dosing, and flags patterns that look like
prescription fraud.

---

## What makes this different from "a health app with permissions"

| Ordinary access control | MathNova |
| --- | --- |
| A session or role decides who reads data | A **verified Ed25519 signature** decides. No signature, no grant. |
| The server can grant itself access | The server holds **no private key** — it can only accept or reject a signature it is handed. |
| Audit logs are rows an admin can edit | Audit entries are **hash-chained per patient**; editing any row breaks every hash after it. |
| Consent is a checkbox, forever | Consent is **scoped, time-boxed and revocable mid-grant**, and revocation is itself a signed act. |
| "Log in as the patient" for a caregiver | **Delegates hold their own keypair.** Their approvals verify against *their* key and log as `approved_by_delegate`. |

### This is a decentralisation-of-*trust* problem, not of *storage*

There is deliberately **no blockchain** here. Data lives in ordinary SQLite. What is
decentralised is *authority*: the power to release a record belongs to the key holder, not
to whoever controls the database. Tamper-evidence comes from a per-patient SHA-256 hash
chain, which is the property a ledger would have provided — without consensus, mining or a
distributed network. Decoupling storage from access control this way is what current
academic systems in this space actually do; it is the correct architecture, not a shortcut.

---

## Setup

Requirements: **Python 3.10+** and **Node 18+**.

### 1. Backend (Flask, port 5000)

```bash
cd backend
python -m venv .venv
```

Activate the virtualenv:

```bash
source .venv/Scripts/activate
```

(macOS/Linux: `source .venv/bin/activate`. Windows PowerShell: `.\.venv\Scripts\Activate.ps1`.)

Then install, seed and run:

```bash
pip install -r requirements.txt
```

```bash
python seed.py
```

```bash
python app.py
```

`seed.py` drops and rebuilds the demo database. Re-run it any time to get back to a clean
demo state. The API is then on `http://127.0.0.1:5000`.

### 2. Frontend (React + Vite, port 5173)

In a second terminal:

```bash
cd frontend
```

```bash
npm install
```

```bash
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to Flask, so there is nothing else to
configure.

### 3. Anthropic API key (for the AI layer)

The safety and fraud analysers call Claude (`claude-sonnet-5`). Set the key **before**
starting the backend:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

PowerShell:

```bash
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

Windows `cmd`:

```bash
set ANTHROPIC_API_KEY=sk-ant-...
```

**Without a key the app still runs end to end.** The analysers fall back to a small set of
offline heuristics, flags are stored with `source: "fallback"`, and both the topbar chip
and every flag card say `offline analyser` instead of `Claude`. That fallback exists purely
so a demo cannot die on a missing key mid-presentation — it is not the intended path, and
the UI never claims Claude wrote something it did not.

Check which mode you are in:

```bash
curl -s http://127.0.0.1:5000/api/health
```

---

## Demo script (about 4 minutes)

1. **Patient view — Ananya Iyer.** Her vault, her pending requests, her active grants, her
   delegates. Note the alerts panel and the disclosure link.
2. **Approve with the crypto steps visible.** Open the pending *MaxLife Insurance*
   request → narrow the scope if you like → *Sign & approve*. The modal shows the six real
   steps: canonical payload → SHA-256 → Ed25519 signature → server rebuilds the message
   independently → signature verified against the stored public key → grant issued and
   appended to the hash chain. Every value shown is the actual byte string used.
3. **Switch to Requester → MaxLife Insurance → Fetch data.** Only the granted fields come
   back. Nothing else leaves the vault.
4. **Switch back to Patient → Revoke that grant.** Revocation is signed too. Then go back
   to the requester and press *Fetch data* again: it is refused with a plain-language
   reason, and the refusal is logged.
5. **Delegated consent — Rohit Deshmukh.** His spouse Kavita is an active delegate. Open a
   pending request, pick *Kavita Deshmukh (Spouse)* as the signer, approve. The audit entry
   reads `approved_by_delegate` and names her — it is not indistinguishable from Rohit's own
   signature. Revoke her delegate authority and try again: the backend refuses the key.
6. **Safety flag — Rohit again.** He is on warfarin, and a *Naproxen* script is already in
   his vault flagged **high · drug interaction**. To fire one live: *+ New prescription* →
   preset *Diclofenac (NSAID)* on **Meera Krishnan**, who has a documented NSAID allergy →
   *Add & analyse*. Two flags appear: an allergy conflict and an SSRI/NSAID interaction.
7. **Fraud flags — Meera Krishnan.** Three different prescribers wrote Tramadol for her
   inside 30 days, each refill early, the last for double the usual quantity:
   `prescriber_shopping` (high), `early_refill` ×2, `high_quantity`. The rules fired in
   plain Python; Claude only wrote the explanation.
8. **Disclosure Dashboard tab.** Who touched this vault, what they saw, when, and why —
   reconstructed entirely from the hash chain.
9. **Audit Log tab.** `chain intact · N entries`. Optional party trick: edit any row
   directly in SQLite and reload — the pill turns red and names the broken entry.

### Tamper demo (optional, very effective)

With the backend running:

```bash
python -c "import sqlite3;c=sqlite3.connect('backend/mathnova.db');c.execute(\"UPDATE audit_log_entries SET actor='Totally Legit Hospital' WHERE id=2\");c.commit()"
```

Reload the Audit Log tab: the chain badge goes red and points at the exact entry.
Re-run `python seed.py` to restore.

---

## Architecture

```
frontend/                     React + Vite, plain CSS, no component library
  src/App.jsx                 role switcher, tabs, all data loading
  src/api.js                  fetch wrapper (proxied to Flask)
  src/components/
    PatientDashboard.jsx      vault, requests, grants, delegates, alerts
    ApprovalModal.jsx         the signed-approval flow
    CryptoSteps.jsx           the step-by-step crypto visualisation
    RevokeGrantModal.jsx      signed mid-grant revocation
    DelegatePanel.jsx         add / revoke delegates (patient-signed)
    RequesterPortal.jsx       submit requests, fetch granted data
    DisclosureDashboard.jsx   who saw what, when, why
    AuditLogPanel.jsx         hash chain with live integrity check
    Flags.jsx                 safety / fraud badges + explanations

backend/
  app.py                      Flask factory, create_all() on startup
  models.py                   every table
  crypto_utils.py             Ed25519 keygen, canonical JSON, sign, verify
  access_control.py           the consent engine (the two rules)
  audit.py                    hash chain: append + verify
  seed.py                     the whole demo world
  routes/
    patients.py               vault, records, flags, health
    access.py                 requests, approve, deny, revoke, grant-checked reads
    delegates.py              delegated proxy consent
    audit_routes.py           audit log + disclosure dashboard
    wallet.py                 the demo "wallet" that performs signing
  ai/
    claude_client.py          one Claude call, strict-JSON parsing, never raises
    safety.py                 prescription safety review  (Claude call #1)
    fraud.py                  rule heuristics + Claude explanation (Claude call #2)
    pipeline.py               runs both, writes findings into the audit chain
```

### The cryptographic flow

1. Every patient and delegate gets an Ed25519 keypair (PyNaCl `SigningKey`). **No RSA
   anywhere.**
2. To approve request `N`, the approver signs the canonical JSON of
   `{request_id, granted_fields, expires_at}` — sorted keys, no whitespace, UTF-8.
3. The backend **rebuilds that message from its own rows** (never from anything the client
   sends) and verifies the signature against the stored public key: the patient's if the
   patient approved, the delegate's if a delegate did *and their status is `active`*.
   Verification fails ⇒ no grant, and the failure is logged.
4. Every read checks a live grant: `status == "active"`, not expired, and scope covers
   every field requested. Otherwise the read is refused with a message the UI shows
   verbatim, and the refusal is written to the chain.
5. Revocation is a signed message too — `{grant_id, action: "revoke"}` or
   `{delegate_id, action: "revoke"}` — verified against someone with authority over that
   object. Access checks test `status == "active"`, never expiry alone.
6. **Every one of these actions appends a hash-chained audit entry.**

```
entry_hash = SHA-256( canonical_json({
    patient_id, actor, action, details, timestamp, prev_entry_hash
}) )
```

One chain per patient, genesis `prev_entry_hash` = 64 zeros. `GET /api/patients/:id/audit-log`
recomputes the whole chain on every read and reports the first break.

#### Why is there a `/api/wallet/sign` endpoint?

In production the private key lives in the browser or a hardware wallet and only the
signature crosses the wire. This build stores keys server-side for demo simplicity, so
signing is exposed as an explicit, *separate* step rather than folded silently into the
approve endpoint:

```
POST /api/wallet/sign                    -> "the key signs this exact message"
POST /api/access-requests/:id/approve    -> "the server verifies it"
```

The approve endpoint has no access to any private key. It can only accept or reject the
signature it is handed — exactly the property a real system has, and exactly what the
crypto-steps panel visualises.

### The AI layer

Two separate, single-purpose Claude calls (`claude-sonnet-5`, `max_tokens=1000`), never
combined into one prompt. Both use a system prompt that states the role and the exact JSON
schema, demand strict JSON with no markdown, and are parsed defensively (code fences
stripped, then a fallback to the outermost `{...}` span).

**Safety check** — on every new prescription. Claude receives the new prescription, the
patient's current medications and their documented allergies, and returns interactions,
allergy conflicts and dosage concerns with a plain-language explanation and a severity.
There is no drug-interaction database and no external API: reasoning over the patient's own
vault is the mechanism.

**Fraud check** — on every new prescription and every access request. Cheap deterministic
rules run first, in plain Python, with no AI call:

| Rule | Fires when |
| --- | --- |
| `early_refill` | a refill arrives less than 80% through the previous supply |
| `high_quantity` | quantity exceeds the usual maximum for that drug |
| `prescriber_shopping` | 3+ distinct prescribers wrote the same drug within 30 days |
| `request_velocity` | 3+ requests from one requester against one patient within 7 days |
| `over_collection` | the entire vault requested behind a very short purpose statement |

Only if a rule trips is Claude asked to explain, in plain language, why the pattern looks
suspicious — and it is instructed to acknowledge innocent explanations rather than accuse
anyone. Results are stored as `FraudFlag` rows, surfaced as coloured badges with the full
explanation in the UI, and appended to the audit chain. Never logged silently.

The last two rules are an extension: the brief's three rules are prescription-shaped, so
these are the equivalent heuristics for the consent side.

---

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | liveness + AI mode |
| `GET` | `/api/patients` | role-switcher list |
| `GET` | `/api/patients/:id/vault` | the patient's own view (no grant needed — they own it) |
| `POST` | `/api/patients/:id/records` | add a record; prescriptions run both analysers |
| `GET` | `/api/patients/:id/flags` | all safety + fraud flags |
| `GET` | `/api/access-fields` | the scope vocabulary |
| `POST` | `/api/access-requests` | requester asks for access |
| `GET` | `/api/access-requests?patient_id=` | approval queue (also `?requester_name=`) |
| `POST` | `/api/access-requests/:id/approve` | **signature verified here**, then grant |
| `POST` | `/api/access-requests/:id/deny` | refuse |
| `GET` | `/api/access-grants?patient_id=` | grants with requester context |
| `POST` | `/api/access-grants/:id/revoke` | signed mid-grant revocation |
| `GET` | `/api/records?patient_id=&access_grant_id=` | the only third-party read path, grant-checked |
| `GET` | `/api/patients/:id/delegates` | list delegates |
| `POST` | `/api/patients/:id/delegates` | patient signs a delegate authorisation |
| `POST` | `/api/delegates/:id/revoke` | signed delegate revocation |
| `GET` | `/api/patients/:id/audit-log` | hash chain + live integrity check |
| `GET` | `/api/patients/:id/disclosure-dashboard` | who accessed what, when, why |
| `POST` | `/api/wallet/sign` | demo wallet (see above) |

Scope vocabulary: `prescriptions`, `allergies`, `diagnostics`, `reports`.

---

## Seed data

Three patients, each with a documented allergy and a real medication list:

- **Ananya Iyer** — penicillin anaphylaxis; metformin, amlodipine, atorvastatin. One
  delegate (Sunita Iyer, mother) and one **revoked** delegate (Vikram Iyer, brother). A
  completed *request → grant → read → revoke* cycle with HealthFirst Clinic, plus an
  active Apollo Pharmacy grant and a pending MaxLife Insurance request.
- **Rohit Deshmukh** — sulfa allergy; warfarin, levothyroxine, losartan. Delegate Kavita
  Deshmukh (spouse) who **signed a grant on his behalf** while he was sedated. Carries the
  seeded **safety flag**: a Naproxen script on top of warfarin.
- **Meera Krishnan** — NSAID allergy; salbutamol, sertraline. Carries the seeded **fraud
  scenario**: Tramadol from three prescribers in 30 days, each early, the last at double
  quantity.

Every seeded grant is produced by genuinely signing and verifying the canonical payload,
and every step appends a real chain entry — if the crypto were broken, seeding would fail.
Each patient's chain is both hash-ordered and chronological.

---

## Deliberate non-goals

No blockchain or consensus. No authentication or authorisation system — the role switcher
*is* the identity model. No real drug-interaction database or external clinical API. No
production key management, HSMs or secure enclaves. No responsive or mobile layout — this
is built for a laptop screen on a projector.

## Demo simplifications, stated plainly

- **Private keys are stored server-side.** A real system keeps the patient's private key
  client-side — browser keystore, mobile secure element, or a hardware wallet — and the
  server only ever holds the public key. Everything else about the flow (canonical
  payloads, detached Ed25519 signatures, server-side verification against a stored public
  key) is what a production system does.
- **A patient signs a delegate's *name and relationship*,** not their public key, because
  the delegate's keypair does not exist until the server mints it. In a wallet-based flow
  the delegate would generate their own keypair first and the patient would sign that key.
- **The offline analyser fallback** is a small hard-coded heuristic table, not a drug
  database. It exists only so the demo survives a missing API key, and anything it produces
  is labelled `offline analyser` in the UI.

## Repository layout

Branches mirror the six build phases:

- `p1` … `p6` — the individual work unit for each phase
- `phase-1` … `phase-6` — cumulative state at the end of that phase
- `Cipher`, `Nexus`, `Nova` — the three contributors' areas of ownership
- `final` — the complete system
