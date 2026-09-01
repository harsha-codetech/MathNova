"""The demo "wallet".

In a real deployment this endpoint would not exist: the patient's private key
would live in their browser/phone and the signing would happen there, with only
the signature crossing the wire. Because this build stores keys server-side for
demo simplicity, we expose signing as an explicit, separate step instead of
folding it silently into the approve endpoint.

That separation is deliberate and worth keeping even in the demo:

    POST /api/wallet/sign      -> "the patient's key signs this exact message"
    POST /api/access-requests/:id/approve  -> "the server verifies it"

The approve endpoint has no access to any private key. It can only accept or
reject the signature it is handed, which is exactly the property a real system
has -- and it is what the crypto-steps panel in the UI visualises.
"""

from flask import Blueprint, jsonify, request

from access_control import ConsentError, normalise_fields
from crypto_utils import canonical_json, grant_payload, sha256_hex, sign_message
from models import Delegate, Patient, db

bp = Blueprint("wallet", __name__, url_prefix="/api/wallet")


def _signing_identity(patient_id, signer):
    """Return (private_key_hex, public_key_hex, label) for the chosen signer."""
    patient = db.session.get(Patient, patient_id)
    if patient is None:
        raise ConsentError("patient not found", 404)

    if signer in (None, "", "patient") or (isinstance(signer, dict) and signer.get("type") == "patient"):
        return patient.private_key, patient.public_key, patient.name

    delegate_id = None
    if isinstance(signer, str) and signer.startswith("delegate:"):
        delegate_id = int(signer.split(":", 1)[1])
    elif isinstance(signer, dict) and signer.get("type") == "delegate":
        delegate_id = signer.get("id")

    if delegate_id is None:
        raise ConsentError("malformed signer", 400)

    delegate = db.session.get(Delegate, int(delegate_id))
    if delegate is None or delegate.patient_id != patient_id:
        raise ConsentError("delegate not found for this patient", 404)
    if delegate.status != "active":
        raise ConsentError(f"delegate '{delegate.delegate_name}' has been revoked")

    return (
        delegate.delegate_private_key,
        delegate.delegate_public_key,
        f"{delegate.delegate_name} ({delegate.relationship}, delegate)",
    )


def _build_payload(intent, params):
    """Every signable message in the system is built here or in crypto_utils --
    never ad hoc at a call site."""
    if intent == "approve_request":
        return grant_payload(
            params["request_id"],
            normalise_fields(params.get("granted_fields") or []),
            params["expires_at"],
        )
    raise ConsentError(f"unknown signing intent '{intent}'", 400)


@bp.post("/sign")
def sign():
    """Body: {patient_id, signer, intent, params}."""
    body = request.get_json(silent=True) or {}
    patient_id = body.get("patient_id")
    intent = body.get("intent")
    params = body.get("params") or {}

    try:
        private_key, public_key, label = _signing_identity(patient_id, body.get("signer", "patient"))
        payload = _build_payload(intent, params)
    except ConsentError as err:
        return jsonify({"error": err.message}), err.status
    except (KeyError, TypeError) as err:
        return jsonify({"error": f"missing signing parameter: {err}"}), 400

    message = canonical_json(payload)
    return jsonify(
        {
            "signer_label": label,
            "public_key": public_key,
            "payload": payload,
            "canonical_message": message,
            "message_sha256": sha256_hex(message),
            "signature": sign_message(private_key, message),
        }
    )
