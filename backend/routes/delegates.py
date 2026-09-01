"""Delegated proxy consent.

A delegate is someone the patient has cryptographically authorised to approve
access on their behalf -- a spouse, an adult child, a caregiver for a patient
who is unconscious, elderly or a minor. This is the case that breaks every
"just log in as the patient" design: the delegate must be able to consent
*without* impersonating the patient, and the audit trail has to say which of
them actually signed.

So delegates get their own Ed25519 keypair. An approval signed by Kavita
Deshmukh verifies against Kavita's public key and logs as
`approved_by_delegate` -- it is never mistakable for Rohit's own signature.
"""

from flask import Blueprint, jsonify, request

import audit
from access_control import ConsentError
from crypto_utils import (
    add_delegate_payload,
    canonical_json,
    generate_keypair,
    revoke_delegate_payload,
    sha256_hex,
    verify_signature,
)
from models import Delegate, Patient, db

bp = Blueprint("delegates", __name__, url_prefix="/api")


@bp.get("/patients/<int:patient_id>/delegates")
def list_delegates(patient_id):
    if db.session.get(Patient, patient_id) is None:
        return jsonify({"error": "patient not found"}), 404
    delegates = (
        Delegate.query.filter_by(patient_id=patient_id).order_by(Delegate.id).all()
    )
    return jsonify([d.to_dict() for d in delegates])


@bp.post("/patients/<int:patient_id>/delegates")
def add_delegate(patient_id):
    """The patient signs the authorisation; only then is a delegate keypair minted.

    Body: {delegate_name, relationship, signature}
    """
    patient = db.session.get(Patient, patient_id)
    if patient is None:
        return jsonify({"error": "patient not found"}), 404

    body = request.get_json(silent=True) or {}
    delegate_name = (body.get("delegate_name") or "").strip()
    relationship = (body.get("relationship") or "").strip()
    signature = body.get("signature")

    if not delegate_name or not relationship:
        return jsonify({"error": "delegate_name and relationship are required"}), 400
    if not signature:
        return jsonify({"error": "signature is required -- only the patient can appoint a delegate"}), 400

    message = canonical_json(add_delegate_payload(patient_id, delegate_name, relationship))
    if not verify_signature(patient.public_key, message, signature):
        return jsonify(
            {
                "error": "signature verification failed -- delegate not created",
                "verified": False,
                "canonical_message": message,
            }
        ), 400

    private_key, public_key = generate_keypair()
    delegate = Delegate(
        patient_id=patient_id,
        delegate_name=delegate_name,
        relationship=relationship,
        delegate_public_key=public_key,
        delegate_private_key=private_key,
        status="active",
    )
    db.session.add(delegate)
    db.session.flush()

    audit.log(
        patient_id=patient_id,
        actor=patient.name,
        action="delegate_added",
        details={
            "delegate_id": delegate.id,
            "delegate_name": delegate_name,
            "relationship": relationship,
            "delegate_public_key": public_key,
            "signature": signature,
            "signed_message": message,
            "message_sha256": sha256_hex(message),
        },
    )
    db.session.commit()

    return jsonify(
        {
            "delegate": delegate.to_dict(),
            "verification": {
                "canonical_message": message,
                "message_sha256": sha256_hex(message),
                "public_key": patient.public_key,
                "signature": signature,
                "verified": True,
                "signed_by": patient.name,
            },
        }
    ), 201


@bp.post("/delegates/<int:delegate_id>/revoke")
def revoke_delegate(delegate_id):
    """Body: {signature, signer}. Authority: the patient, or the delegate
    revoking themselves. One delegate may not revoke another -- that authority
    belongs to the data owner alone.
    """
    delegate = db.session.get(Delegate, delegate_id)
    if delegate is None:
        return jsonify({"error": "delegate not found"}), 404
    if delegate.status != "active":
        return jsonify({"error": "delegate is already revoked"}), 409

    patient = db.session.get(Patient, delegate.patient_id)
    body = request.get_json(silent=True) or {}
    signature = body.get("signature")
    signer = body.get("signer", "patient")

    if not signature:
        return jsonify({"error": "signature is required"}), 400

    try:
        public_key, actor = _revocation_authority(patient, delegate, signer)
    except ConsentError as err:
        return jsonify({"error": err.message}), err.status

    message = canonical_json(revoke_delegate_payload(delegate_id))
    if not verify_signature(public_key, message, signature):
        return jsonify(
            {
                "error": "signature verification failed -- delegate NOT revoked",
                "verified": False,
                "canonical_message": message,
            }
        ), 400

    delegate.status = "revoked"
    audit.log(
        patient_id=patient.id,
        actor=actor,
        action="delegate_revoked",
        details={
            "delegate_id": delegate.id,
            "delegate_name": delegate.delegate_name,
            "relationship": delegate.relationship,
            "signature": signature,
            "signed_message": message,
            "message_sha256": sha256_hex(message),
            "verified_against_public_key": public_key,
        },
    )
    db.session.commit()

    return jsonify(
        {
            "delegate": delegate.to_dict(),
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


def _revocation_authority(patient, delegate, signer):
    """Who may sign a delegate revocation, and with which key."""
    if signer in (None, "", "patient") or (
        isinstance(signer, dict) and signer.get("type") == "patient"
    ):
        return patient.public_key, patient.name

    signer_id = None
    if isinstance(signer, str) and signer.startswith("delegate:"):
        signer_id = int(signer.split(":", 1)[1])
    elif isinstance(signer, dict) and signer.get("type") == "delegate":
        signer_id = int(signer.get("id"))

    if signer_id == delegate.id:
        return delegate.delegate_public_key, f"{delegate.delegate_name} (self-revocation)"

    raise ConsentError("only the patient may revoke another person's delegate authority")
