#!/usr/bin/env python3
"""
Convert RSA public key PEM to JWK format for Epic FHIR JWKS endpoint
"""

import json
import base64
import hashlib
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

def convert_pem_to_jwk(pem_file_path: str) -> dict:
    """Convert PEM public key to JWK format"""

    # Read PEM file
    with open(pem_file_path, 'rb') as f:
        pem_data = f.read()

    # Load public key
    public_key = serialization.load_pem_public_key(
        pem_data,
        backend=default_backend()
    )

    # Get public numbers (modulus and exponent)
    public_numbers = public_key.public_numbers()

    # Convert to base64url format (without padding)
    def int_to_base64url(value):
        # Convert int to bytes
        value_bytes = value.to_bytes((value.bit_length() + 7) // 8, byteorder='big')
        # Base64url encode (no padding)
        return base64.urlsafe_b64encode(value_bytes).rstrip(b'=').decode('utf-8')

    # Generate key ID from public key fingerprint
    pem_str = pem_data.decode('utf-8')
    kid = hashlib.sha256(pem_data).hexdigest()[:16]

    # Create JWK
    jwk = {
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "kid": kid,
        "n": int_to_base64url(public_numbers.n),
        "e": int_to_base64url(public_numbers.e)
    }

    return jwk

def create_jwks(jwk: dict) -> dict:
    """Wrap JWK in JWKS (JSON Web Key Set) format"""
    return {
        "keys": [jwk]
    }

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python convert_pem_to_jwk.py <pem_file_path>")
        sys.exit(1)

    pem_file = sys.argv[1]

    # Convert to JWK
    jwk = convert_pem_to_jwk(pem_file)

    # Create JWKS
    jwks = create_jwks(jwk)

    # Print formatted JSON
    print(json.dumps(jwks, indent=2))

    # Also save to file
    output_file = "jwks.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(jwks, f, indent=2)

    print(f"\n✅ JWKS saved to {output_file}", file=sys.stderr)
    print(f"✅ Key ID (kid): {jwk['kid']}", file=sys.stderr)
