"""Ed25519 key handling, canonical payloads, signing and verification.

PyNaCl only -- no RSA anywhere in this project.

A signature is only meaningful if signer and verifier agree byte-for-byte on
what was signed, so every signable message goes through `canonical_json()`:
sorted keys, no insignificant whitespace, UTF-8. The frontend displays exactly
this string during the approval flow, which is what makes the crypto steps
legible to a judge watching the demo.
"""

import hashlib
import json

from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------
def generate_keypair():
    """Return (private_key_hex, public_key_hex) for a fresh Ed25519 identity.

    The "private key" we persist is the 32-byte Ed25519 seed, hex encoded --
    that is all PyNaCl needs to reconstruct the SigningKey.
    """
    signing_key = SigningKey.generate()
    private_hex = signing_key.encode(encoder=HexEncoder).decode("ascii")
    public_hex = signing_key.verify_key.encode(encoder=HexEncoder).decode("ascii")
    return private_hex, public_hex


# --------------------------------------------------------------------------
# Canonicalisation
# --------------------------------------------------------------------------
def canonical_json(payload: dict) -> str:
    """Deterministic JSON serialisation used as the signable message."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Signable payload builders
#
# These live in one place on purpose: signer and verifier MUST construct the
# message identically or verification fails for the wrong reason. Anything that
# needs a signature builds its message here and nowhere else.
# --------------------------------------------------------------------------
def grant_payload(request_id: int, granted_fields, expires_at_iso: str) -> dict:
    """What an approver signs to authorise an access request.

    Exactly the shape from the brief: {request_id, granted_fields, expires_at}.
    granted_fields is sorted so the same consent produces the same bytes
    regardless of the order the UI happened to collect the checkboxes in.
    """
    return {
        "request_id": int(request_id),
        "granted_fields": sorted(granted_fields),
        "expires_at": expires_at_iso,
    }


def revoke_grant_payload(grant_id: int) -> dict:
    return {"grant_id": int(grant_id), "action": "revoke"}


def revoke_delegate_payload(delegate_id: int) -> dict:
    return {"delegate_id": int(delegate_id), "action": "revoke"}


def add_delegate_payload(patient_id: int, delegate_name: str, relationship: str) -> dict:
    """What a patient signs to authorise a new delegate.

    ASSUMPTION (noted rather than asked): the delegate's keypair does not exist
    until the server mints it, so the patient signs the *identity* of the person
    being authorised (name + relationship) rather than a public key they cannot
    yet know. In a production wallet-based flow the delegate would generate
    their own keypair first and the patient would sign that public key.
    """
    return {
        "action": "add_delegate",
        "patient_id": int(patient_id),
        "delegate_name": delegate_name,
        "relationship": relationship,
    }


# --------------------------------------------------------------------------
# Sign / verify
# --------------------------------------------------------------------------
def sign_message(private_key_hex: str, message: str) -> str:
    """Detached Ed25519 signature over the UTF-8 bytes of `message`, hex encoded."""
    signing_key = SigningKey(private_key_hex.encode("ascii"), encoder=HexEncoder)
    signed = signing_key.sign(message.encode("utf-8"))
    return signed.signature.hex()


def verify_signature(public_key_hex: str, message: str, signature_hex: str) -> bool:
    """True iff `signature_hex` is a valid Ed25519 signature over `message` by
    the holder of `public_key_hex`. Never raises -- a malformed signature is
    just an invalid one."""
    try:
        verify_key = VerifyKey(public_key_hex.encode("ascii"), encoder=HexEncoder)
        verify_key.verify(message.encode("utf-8"), bytes.fromhex(signature_hex))
        return True
    except (BadSignatureError, ValueError, TypeError):
        return False


def sign_payload(private_key_hex: str, payload: dict) -> dict:
    """Convenience wrapper returning everything the demo UI wants to show:
    the canonical string, its SHA-256 digest and the signature."""
    message = canonical_json(payload)
    return {
        "canonical_message": message,
        "message_sha256": sha256_hex(message),
        "signature": sign_message(private_key_hex, message),
    }
