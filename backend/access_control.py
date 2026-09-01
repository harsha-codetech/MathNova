"""The consent engine.

Two rules, and everything else in this file exists to enforce them:

  1. An AccessGrant is only created after a *valid Ed25519 signature* over the
     canonical consent payload is verified against a stored public key. Not a
     session, not a role, not an admin flag -- a signature.
  2. Every read of patient data is checked against a live grant: status must be
     `active`, it must not have expired, and its scope must cover every field
     being read.
"""

from models import AccessGrant, Delegate, MedicalRecord, Patient, db

# The scope vocabulary. Requesters ask for these; grants are scoped to these;
# reads are filtered by these. Each maps onto a MedicalRecord.record_type.
FIELD_RECORD_TYPE = {
    "prescriptions": "prescription",
    "allergies": "allergy",
    "diagnostics": "diagnostic",
    "reports": "report",
}
ACCESS_FIELDS = tuple(FIELD_RECORD_TYPE.keys())


class ConsentError(Exception):
    """Raised when a consent rule is violated. `status` is the HTTP code."""

    def __init__(self, message, status=403):
        super().__init__(message)
        self.message = message
        self.status = status


# --------------------------------------------------------------------------
# Signer resolution
# --------------------------------------------------------------------------
def resolve_signer(patient_id, signer):
    """Turn a signer spec from the request body into the key we verify against.

    `signer` is either "patient" or {"type": "delegate", "id": N} / "delegate:N".
    Returns (public_key_hex, granted_by, actor_label, audit_action).

    A delegate whose status is `revoked` is rejected here -- revocation has to
    bite at verification time, not merely hide a button in the UI.
    """
    patient = db.session.get(Patient, patient_id)
    if patient is None:
        raise ConsentError("patient not found", 404)

    kind, delegate_id = _parse_signer(signer)

    if kind == "patient":
        return patient.public_key, "patient", patient.name, "approved_by_patient"

    delegate = db.session.get(Delegate, delegate_id)
    if delegate is None or delegate.patient_id != patient_id:
        raise ConsentError("delegate not found for this patient", 404)
    if delegate.status != "active":
        raise ConsentError(
            f"delegate '{delegate.delegate_name}' has been revoked and can no longer sign"
        )

    return (
        delegate.delegate_public_key,
        f"delegate:{delegate.id}",
        f"{delegate.delegate_name} ({delegate.relationship}, delegate)",
        "approved_by_delegate",
    )


def _parse_signer(signer):
    """Accepts "patient", "delegate:3", {"type": "delegate", "id": 3} or
    {"type": "patient"}."""
    if signer in (None, "", "patient"):
        return "patient", None

    if isinstance(signer, str):
        if signer.startswith("delegate:"):
            try:
                return "delegate", int(signer.split(":", 1)[1])
            except ValueError:
                raise ConsentError("malformed delegate signer", 400)
        raise ConsentError(f"unknown signer '{signer}'", 400)

    if isinstance(signer, dict):
        kind = signer.get("type", "patient")
        if kind == "patient":
            return "patient", None
        if kind == "delegate":
            delegate_id = signer.get("id")
            if delegate_id is None:
                raise ConsentError("delegate signer requires an id", 400)
            return "delegate", int(delegate_id)

    raise ConsentError("malformed signer", 400)


def signer_key_for_authority(patient_id, signer):
    """Same as resolve_signer but for revocation, where the audit action differs."""
    public_key, granted_by, actor, _action = resolve_signer(patient_id, signer)
    return public_key, granted_by, actor


# --------------------------------------------------------------------------
# Field / scope helpers
# --------------------------------------------------------------------------
def normalise_fields(fields):
    if not isinstance(fields, (list, tuple)):
        raise ConsentError("fields must be a list", 400)
    cleaned = []
    for field in fields:
        if field not in FIELD_RECORD_TYPE:
            raise ConsentError(
                f"unknown field '{field}'. Valid fields: {', '.join(ACCESS_FIELDS)}", 400
            )
        if field not in cleaned:
            cleaned.append(field)
    if not cleaned:
        raise ConsentError("at least one field is required", 400)
    return sorted(cleaned)


def require_valid_grant(grant_id, patient_id, fields):
    """Rule 2. Returns the grant, or raises ConsentError with a message the UI
    can show verbatim."""
    grant = db.session.get(AccessGrant, grant_id)
    if grant is None:
        raise ConsentError("access grant not found", 404)
    if grant.patient_id != int(patient_id):
        raise ConsentError("this grant does not belong to that patient")

    status = grant.effective_status()
    if status == "revoked":
        raise ConsentError(
            "access grant has been REVOKED by the patient. Historical consent does not "
            "survive revocation."
        )
    if status == "expired":
        raise ConsentError("access grant has expired")

    scope = set(grant.scope or [])
    missing = [f for f in fields if f not in scope]
    if missing:
        raise ConsentError(
            "grant does not cover requested field(s): " + ", ".join(missing)
        )

    return grant


def records_in_scope(patient_id, fields):
    """Only the record types the grant actually covers -- nothing else leaves
    the vault."""
    record_types = [FIELD_RECORD_TYPE[f] for f in fields]
    records = (
        MedicalRecord.query.filter(
            MedicalRecord.patient_id == patient_id,
            MedicalRecord.record_type.in_(record_types),
        )
        .order_by(MedicalRecord.id)
        .all()
    )
    return [r.to_dict() for r in records]
