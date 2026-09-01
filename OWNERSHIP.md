# Cipher — Person 1

**Area of ownership: cryptography, consent engine, tamper-evident audit trail.**

This branch carries the full working system; the files below are the ones this
contributor owns and is the point of contact for.

## Owned

| File | What it does |
| --- | --- |
| `backend/crypto_utils.py` | Ed25519 keygen (PyNaCl), canonical JSON, every signable payload builder, sign, verify |
| `backend/access_control.py` | The consent engine — signer resolution, scope normalisation, the live grant check |
| `backend/audit.py` | Per-patient SHA-256 hash chain: append, recompute, report the first break |
| `backend/models.py` | All tables, including grant status semantics (`active` / `revoked` / computed `expired`) |
| `backend/routes/access.py` | Access requests, signature-verified approval, denial, mid-grant revocation, the grant-checked read path |
| `backend/routes/delegates.py` | Delegated proxy consent — patient-signed appointment, signed revocation |
| `backend/routes/wallet.py` | The demo wallet, kept as a separate step so the approve endpoint provably holds no private key |
| `backend/routes/audit_routes.py` | Audit log endpoint with live chain verification |

## The two invariants this contributor defends

1. **No signature, no grant.** An `AccessGrant` row only ever comes into existence after a
   valid Ed25519 signature over the canonical consent payload has been verified against a
   stored public key. The approve endpoint has no access to any private key, and it rebuilds
   the signed message from its own rows rather than trusting anything the client sends.
2. **Every read is checked against live consent.** `status == "active"`, not expired, and
   the scope must cover every field requested. Revocation bites at verification time — a
   revoked delegate's key is refused, not merely hidden from the UI.

## Design decisions worth defending in a review

- **Ed25519, never RSA.** Small keys, small signatures, no padding-mode footguns.
- **Canonical JSON in exactly one place.** Signer and verifier must agree byte-for-byte, so
  every signable message is built by a function in `crypto_utils.py` and nowhere else.
- **The hash chain replaces a blockchain.** `entry_hash` folds in `prev_entry_hash`, so
  editing any historical row invalidates every hash after it. That is the property a ledger
  would have bought, without consensus or a distributed network.
- **`status` is authoritative, not expiry.** A grant that was revoked early must fail the
  check even though its `expires_at` is still in the future.
