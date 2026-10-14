import base64
import json
import pathlib
import subprocess
import sys

KID = sys.argv[1] if len(sys.argv) > 1 else "fiap-key-1"
KEYS_DIR = pathlib.Path(__file__).parent
PRIVATE_KEY = KEYS_DIR / "private.pem"


def b64url(number):
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


subprocess.run(["openssl", "genrsa", "-out", str(PRIVATE_KEY), "2048"], check=True)
PRIVATE_KEY.chmod(0o600)

modulus_hex = subprocess.run(
    ["openssl", "rsa", "-in", str(PRIVATE_KEY), "-noout", "-modulus"],
    check=True, capture_output=True, text=True,
).stdout.strip().split("=", 1)[1]

jwks = {
    "keys": [{
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": KID,
        "n": b64url(int(modulus_hex, 16)),
        "e": b64url(65537),  # expoente padrão do openssl genrsa
    }]
}
(KEYS_DIR / "jwks.json").write_text(json.dumps(jwks, indent=2) + "\n")
print(f"Gerados {PRIVATE_KEY} e {KEYS_DIR / 'jwks.json'} (kid={KID})")
