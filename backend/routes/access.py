"""Access requests, signature-verified grants, and grant-checked reads."""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

import audit
from ai.pipeline import analyse_access_request
from access_control import (
    ACCESS_FIELDS,
    ConsentError,
    normalise_fields,
    records_in_scope,
    require_valid_grant,
    resolve_signer,
    signer_key_for_authority,
)
from crypto_utils import (
    canonical_json,
    grant_payload,
    revoke_grant_payload,
    sha256_hex,
    verify_signature,
)
from models import AccessGrant, AccessRequest, Patient, db, iso, utcnow

bp = Blueprint("access", __name__, url_prefix="/api")


def _parse_iso(value):
    """Parse an ISO-8601 timestamp, tolerating a trailing 'Z'."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@bp.errorhandler(ConsentError)
def _consent_error(err):
    return jsonify({"error": err.message}), err.status


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------
@bp.get("/access-fields")
def access_fields():
    """The scope vocabulary, so the requester form never invents a field name."""
    return jsonify({"fields": list(ACCESS_FIELDS)})


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------
@bp.post("/access-requests")
def create_access_request():
    body = request.get_json(silent=True) or {}

    requester_name = (body.get("requester_name") or "").strip()
    requester_type = body.get("requester_type")
    patient_id = body.get("patient_id")
    purpose = (body.get("purpose") or "").strip()

    if not requester_name:
        return jsonify({"error": "requester_name is required"}), 400
    if requester_type not in ("hospital", "pharmacy", "lab", "insurer"):
        return jsonify({"error": "requester_type must be hospital|pharmacy|lab|insurer"}), 400
    if not purpose:
        return jsonify({"error": "purpose is required -- consent without a stated purpose is not consent"}), 400
    if db.session.get(Patient, patient_id) is None:
        return jsonify({"error": "patient not found"}), 404

    try:
        fields = normalise_fields(body.get("requested_fields") or [])
    except ConsentError as err:
        return jsonify({"error": err.message}), err.status

    access_request = AccessRequest(
        requester_name=requester_name,
        requester_type=requester_type,
        patient_id=patient_id,
        requested_fields=fields,
        purpose=purpose,
    )
    db.session.add(access_request)
    db.session.flush()

    audit.log(
        patient_id=patient_id,
        actor=f"{requester_name} ({requester_type})",
        action="request_created",
        details={
            "access_request_id": access_request.id,
            "requested_fields": fields,
            "purpose": purpose,
        },
    )

    # Fraud heuristics run on the consent side too, not just on prescriptions.
    analysis = analyse_access_request(access_request)
    db.session.commit()

    return jsonify({"access_request": access_request.to_dict(), **analysis}), 201


@bp.get("/access-requests")
def list_access_requests():
    query = AccessRequest.query
    patient_id = request.args.get("patient_id", type=int)
    requester_name = request.args.get("requester_name")
    status = request.args.get("status")

    if patient_id is not None:
        query = query.filter_by(patient_id=patient_id)
    if requester_name:
        query = query.filter_by(requester_name=requester_name)
    if status:
        query = query.filter_by(status=status)

    requests = query.order_by(AccessRequest.id.desc()).all()

    # Grants are attached inline so the patient dashboard and the requester
    # portal can both render from a single call.
    out = []
    for access_request in requests:
        item = access_request.to_dict()
        item["grants"] = [g.to_dict() for g in access_request.grants]
        out.append(item)
    return jsonify(out)


# --------------------------------------------------------------------------
# Approve  --  the cryptographic heart of the system
# --------------------------------------------------------------------------
@bp.post("/access-requests/<int:request_id>/approve")
def approve_access_request(request_id):
    """Approve by presenting a signature. No signature, no grant.

    Body: {
      signature:       hex Ed25519 detached signature,
      signer:          "patient" | {"type": "delegate", "id": N},
      granted_fields:  subset of the requested fields (the patient may narrow),
      expires_at:      ISO-8601 -- must be exactly what was signed
    }
    """
    access_request = db.session.get(AccessRequest, request_id)
    if access_request is None:
        return jsonify({"error": "access request not found"}), 404
    if access_request.status != "pending":
        return jsonify({"error": f"request is already {access_request.status}"}), 409

    body = request.get_json(silent=True) or {}
    signature = body.get("signature")
    if not signature:
        return jsonify({"error": "signature is required -- approval without a signature is not consent"}), 400

    try:
        granted_fields = normalise_fields(
            body.get("granted_fields") or access_request.requested_fields
        )
    except ConsentError as err:
        return jsonify({"error": err.message}), err.status

    # A patient may narrow the scope but never widen it beyond what was asked.
    requested = set(access_request.requested_fields or [])
    extra = [f for f in granted_fields if f not in requested]
    if extra:
        return jsonify({"error": "granted fields exceed the request: " + ", ".join(extra)}), 400

    expires_at_iso = body.get("expires_at")
    expires_at = _parse_iso(expires_at_iso)
    if expires_at is None:
        return jsonify({"error": "expires_at must be an ISO-8601 timestamp"}), 400
    if expires_at <= utcnow():
        return jsonify({"error": "expires_at is in the past"}), 400

    try:
        public_key, granted_by, actor, action = resolve_signer(
            access_request.patient_id, body.get("signer", "patient")
        )
    except ConsentError as err:
        return jsonify({"error": err.message}), err.status

    # Rebuild the canonical message server-side from data we trust, then verify.
    # We never trust a client-supplied "message" -- that would let a caller sign
    # one thing and have us record another.
    payload = grant_payload(access_request.id, granted_fields, expires_at_iso)
    message = canonical_json(payload)

    if not verify_signature(public_key, message, signature):
        audit.log(
            patient_id=access_request.patient_id,
            actor=actor,
            action="denied",
            details={
                "access_request_id": access_request.id,
                "reason": "signature verification FAILED",
                "public_key": public_key,
            },
        )
        db.session.commit()
        return jsonify(
            {
                "error": "signature verification failed -- no grant created",
                "verified": False,
                "canonical_message": message,
                "message_sha256": sha256_hex(message),
                "public_key": public_key,
            }
        ), 400

    grant = AccessGrant(
        access_request_id=access_request.id,
        patient_id=access_request.patient_id,
        granted_by=granted_by,
        signature=signature,
        scope=granted_fields,
        expires_at=expires_at,
        status="active",
    )
    access_request.status = "approved"
    db.session.add(grant)
    db.session.flush()

    audit.log(
        patient_id=access_request.patient_id,
        actor=actor,
        action=action,  # approved_by_patient | approved_by_delegate
        details={
            "access_request_id": access_request.id,
            "access_grant_id": grant.id,
            "granted_fields": granted_fields,
            "expires_at": expires_at_iso,
            "signature": signature,
            "signed_message": message,
            "message_sha256": sha256_hex(message),
            "verified_against_public_key": public_key,
        },
    )
    db.session.commit()

    return jsonify(
        {
            "access_request": access_request.to_dict(),
            "access_grant": grant.to_dict(),
            # Echoed back so the UI can render the crypto steps it just performed.
            "verification": {
                "canonical_message": message,
                "message_sha256": sha256_hex(message),
                "public_key": public_key,
                "signature": signature,
                "verified": True,
                "signed_by": actor,
            },
        }
    ), 201


@bp.post("/access-requests/<int:request_id>/deny")
def deny_access_request(request_id):
    """Denial needs no signature: refusing to hand over your own data is the
    default state, and a signature would only prove someone chose *not* to
    grant. The signer field is still recorded for attribution."""
    access_request = db.session.get(AccessRequest, request_id)
    if access_request is None:
        return jsonify({"error": "access request not found"}), 404
    if access_request.status != "pending":
        return jsonify({"error": f"request is already {access_request.status}"}), 409

    body = request.get_json(silent=True) or {}
    try:
        _key, _granted_by, actor, _action = resolve_signer(
            access_request.patient_id, body.get("signer", "patient")
        )
    except ConsentError as err:
        return jsonify({"error": err.message}), err.status

    access_request.status = "denied"
    audit.log(
        patient_id=access_request.patient_id,
        actor=actor,
        action="denied",
        details={
            "access_request_id": access_request.id,
            "reason": body.get("reason") or "denied by data owner",
            "requested_fields": access_request.requested_fields,
        },
    )
    db.session.commit()

    return jsonify({"access_request": access_request.to_dict()})


# --------------------------------------------------------------------------
# Grants
# --------------------------------------------------------------------------
@bp.get("/access-grants")
def list_access_grants():
    patient_id = request.args.get("patient_id", type=int)
    query = AccessGrant.query
    if patient_id is not None:
        query = query.filter_by(patient_id=patient_id)

    out = []
    for grant in query.order_by(AccessGrant.id.desc()).all():
        item = grant.to_dict()
        source = db.session.get(AccessRequest, grant.access_request_id)
        item["requester_name"] = source.requester_name if source else None
        item["requester_type"] = source.requester_type if source else None
        item["purpose"] = source.purpose if source else None
        out.append(item)
    return jsonify(out)


# --------------------------------------------------------------------------
# The grant-checked read path
# --------------------------------------------------------------------------
@bp.get("/records")
def fetch_records():
    """The only way a third party ever sees patient data.

    Query: patient_id, access_grant_id, optional fields=a,b (defaults to the
    grant's full scope). Rejected with a plain-language error if the grant is
    missing, revoked, expired or too narrow.
    """
    patient_id = request.args.get("patient_id", type=int)
    grant_id = request.args.get("access_grant_id", type=int)

    if patient_id is None or grant_id is None:
        return jsonify({"error": "patient_id and access_grant_id are both required"}), 400

    grant = db.session.get(AccessGrant, grant_id)
    if grant is None:
        return jsonify({"error": "access grant not found"}), 404

    raw_fields = request.args.get("fields")
    try:
        fields = (
            normalise_fields([f.strip() for f in raw_fields.split(",") if f.strip()])
            if raw_fields
            else list(grant.scope or [])
        )
        grant = require_valid_grant(grant_id, patient_id, fields)
    except ConsentError as err:
        source = db.session.get(AccessRequest, grant.access_request_id) if grant else None
        audit.log(
            patient_id=patient_id,
            actor=(source.requester_name if source else "unknown requester"),
            action="data_accessed",
            details={
                "access_grant_id": grant_id,
                "outcome": "DENIED",
                "reason": err.message,
                "attempted_fields": raw_fields or (grant.scope if grant else []),
            },
        )
        db.session.commit()
        return jsonify({"error": err.message, "outcome": "denied"}), err.status

    source = db.session.get(AccessRequest, grant.access_request_id)
    records = records_in_scope(patient_id, fields)

    audit.log(
        patient_id=patient_id,
        actor=f"{source.requester_name} ({source.requester_type})" if source else "unknown requester",
        action="data_accessed",
        details={
            "access_grant_id": grant.id,
            "access_request_id": grant.access_request_id,
            "outcome": "ALLOWED",
            "fields": fields,
            "record_count": len(records),
            "purpose": source.purpose if source else None,
        },
    )
    db.session.commit()

    return jsonify(
        {
            "outcome": "allowed",
            "patient_id": patient_id,
            "access_grant_id": grant.id,
            "fields": fields,
            "expires_at": iso(grant.expires_at),
            "records": records,
        }
    )


# --------------------------------------------------------------------------
# Mid-grant revocation
# --------------------------------------------------------------------------
@bp.post("/access-grants/<int:grant_id>/revoke")
def revoke_grant(grant_id):
    """Withdraw consent that was already given, before it expires.

    Body: {signature, signer}. The signature is over {grant_id, action:"revoke"}.
    Authority: the patient who owns the data, or any *currently active* delegate
    of theirs. A revoked delegate cannot revoke anything.

    Once this lands, `status` is authoritative -- every later read is refused by
    require_valid_grant() even though the grant has not expired.
    """
    grant = db.session.get(AccessGrant, grant_id)
    if grant is None:
        return jsonify({"error": "access grant not found"}), 404
    if grant.status == "revoked":
        return jsonify({"error": "grant is already revoked"}), 409

    body = request.get_json(silent=True) or {}
    signature = body.get("signature")
    if not signature:
        return jsonify({"error": "signature is required -- revocation is a signed act"}), 400

    try:
        public_key, _granted_by, actor = signer_key_for_authority(
            grant.patient_id, body.get("signer", "patient")
        )
    except ConsentError as err:
        return jsonify({"error": err.message}), err.status

    message = canonical_json(revoke_grant_payload(grant.id))
    if not verify_signature(public_key, message, signature):
        return jsonify(
            {
                "error": "signature verification failed -- grant NOT revoked",
                "verified": False,
                "canonical_message": message,
                "message_sha256": sha256_hex(message),
            }
        ), 400

    grant.status = "revoked"
    source = db.session.get(AccessRequest, grant.access_request_id)

    audit.log(
        patient_id=grant.patient_id,
        actor=actor,
        action="grant_revoked",
        details={
            "access_grant_id": grant.id,
            "access_request_id": grant.access_request_id,
            "requester_name": source.requester_name if source else None,
            "revoked_scope": grant.scope,
            "signature": signature,
            "signed_message": message,
            "message_sha256": sha256_hex(message),
            "verified_against_public_key": public_key,
        },
    )
    db.session.commit()

    return jsonify(
        {
            "access_grant": grant.to_dict(),
            "verification": {
                "canonical_message": message,
                "message_sha256": sha256_hex(message),
                "public_key": public_key,
                "signature": signature,
                "verified": True,
                "signed_by": actor,
            },
        }
    )
