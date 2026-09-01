"""Hash-chained, tamper-evident audit log -- one chain per patient.

    entry_hash = SHA-256( canonical_json({
        patient_id, actor, action, details, timestamp, prev_entry_hash
    }) )

Because `prev_entry_hash` is folded into every digest, editing any historical
row invalidates that row's hash *and* every hash after it. That is the whole
value a blockchain would have provided here, without consensus, mining or a
distributed ledger -- which is exactly the simplification the brief calls for.

The chain is per-patient so each data owner has an independently verifiable
history of who touched their record.
"""

from models import AuditLogEntry, db, iso, utcnow

GENESIS_HASH = "0" * 64


def compute_entry_hash(patient_id, actor, action, details, timestamp, prev_entry_hash):
    from crypto_utils import canonical_json, sha256_hex

    body = {
        "patient_id": int(patient_id),
        "actor": actor,
        "action": action,
        "details": details or {},
        "timestamp": iso(timestamp),
        "prev_entry_hash": prev_entry_hash,
    }
    return sha256_hex(canonical_json(body))


def head_hash(patient_id):
    """Hash of the most recent entry in this patient's chain (genesis if empty)."""
    last = (
        AuditLogEntry.query.filter_by(patient_id=patient_id)
        .order_by(AuditLogEntry.id.desc())
        .first()
    )
    return last.entry_hash if last else GENESIS_HASH


def log(patient_id, actor, action, details=None, timestamp=None):
    """Append one entry to the patient's chain.

    Caller is responsible for committing -- callers usually want the audit entry
    and the state change it describes to land in the same transaction.
    """
    ts = timestamp or utcnow()
    prev = head_hash(patient_id)
    entry_hash = compute_entry_hash(patient_id, actor, action, details, ts, prev)

    entry = AuditLogEntry(
        patient_id=patient_id,
        actor=actor,
        action=action,
        details=details or {},
        timestamp=ts,
        entry_hash=entry_hash,
        prev_entry_hash=prev,
    )
    db.session.add(entry)
    db.session.flush()
    return entry


def verify_chain(patient_id):
    """Recompute the whole chain and report the first break, if any.

    This is what makes the log *tamper-evident* rather than merely append-only:
    the frontend calls it and shows a green "chain intact" pill, so a judge can
    watch it fail live if a row is edited in SQLite.
    """
    entries = (
        AuditLogEntry.query.filter_by(patient_id=patient_id)
        .order_by(AuditLogEntry.id)
        .all()
    )

    prev = GENESIS_HASH
    for index, entry in enumerate(entries):
        if entry.prev_entry_hash != prev:
            return {
                "valid": False,
                "length": len(entries),
                "broken_at": entry.id,
                "position": index,
                "reason": "prev_entry_hash does not match the previous entry's hash",
            }

        recomputed = compute_entry_hash(
            entry.patient_id,
            entry.actor,
            entry.action,
            entry.details,
            entry.timestamp,
            entry.prev_entry_hash,
        )
        if recomputed != entry.entry_hash:
            return {
                "valid": False,
                "length": len(entries),
                "broken_at": entry.id,
                "position": index,
                "reason": "entry contents do not hash to the stored entry_hash",
                "recomputed": recomputed,
            }
        prev = entry.entry_hash

    return {"valid": True, "length": len(entries), "head": prev}
