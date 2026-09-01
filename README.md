# MathNova

**Patient-Sovereign, Signature-Verified Prescription Intelligence Network**

A patient-centric health-record platform where the patient is the sole owner of their
medical data. Every access by a hospital, pharmacy, lab or insurer must be backed by a
cryptographic signature the patient (or an authorised delegate) explicitly created — not a
login, not an admin override.

> Full setup, architecture notes and demo script land in phase 6. This is the phase 1
> scaffold: data model, seed data, health check and the React shell.

## Quick start

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe seed.py
.venv/Scripts/python.exe app.py
```

```bash
cd frontend
npm install
npm run dev
```

Backend on `http://127.0.0.1:5000`, frontend on `http://localhost:5173`
(the Vite dev server proxies `/api` to Flask).
