"""Ed25519 key handling and canonical payload construction.

PyNaCl only -- no RSA anywhere in this project.

A signature is only meaningful if signer and verifier agree byte-for-byte on
what was signed, so every signable message goes through `canonical_json()`:
sorted keys, no insignificant whitespace, UTF-8. The frontend displays exactly
this string during the approval flow, which is what makes the crypto steps
legible to a judge watching the demo.
"""

import json

from nacl.encoding import HexEncoder
from nacl.signing import SigningKey


def generate_keypair():
    """Return (private_key_hex, public_key_hex) for a fresh Ed25519 identity.

    The "private key" we persist is the 32-byte Ed25519 seed, hex encoded --
    that is all PyNaCl needs to reconstruct the SigningKey.
    """
    signing_key = SigningKey.generate()
    private_hex = signing_key.encode(encoder=HexEncoder).decode("ascii")
    public_hex = signing_key.verify_key.encode(encoder=HexEncoder).decode("ascii")
    return private_hex, public_hex


def canonical_json(payload: dict) -> str:
    """Deterministic JSON serialisation used as the signable message."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
