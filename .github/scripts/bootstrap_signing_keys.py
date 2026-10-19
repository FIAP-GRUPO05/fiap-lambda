"""Initialize isolated RSA keys without reading existing private keys back."""
import hashlib
import json
import os
import subprocess
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def aws(*arguments):
    response = subprocess.run(["aws", *arguments, "--output", "json"], capture_output=True, text=True, check=True)
    return json.loads(response.stdout)


for environment in ("develop", "homol", "prod"):
    name = f"fiap/{environment}/jwt-signing"
    metadata = aws("secretsmanager", "describe-secret", "--secret-id", name)
    if environment != "prod" and any("AWSCURRENT" in stages for stages in metadata.get("VersionIdsToStages", {}).values()):
        print(f"Signing key already initialized: {environment}")
        continue
    if environment == "prod":
        pem = os.environ["JWT_PRIVATE_KEY"].replace("\\n", "\n").strip().encode() + b"\n"
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise ValueError("JWT_PRIVATE_KEY must contain an RSA private key with at least 2048 bits")
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    version = hashlib.sha256(pem).hexdigest()
    with tempfile.NamedTemporaryFile(mode="wb") as private_file:
        private_file.write(pem)
        private_file.flush()
        aws("secretsmanager", "put-secret-value", "--secret-id", name,
            "--client-request-token", version, "--secret-string", f"file://{private_file.name}")
    print(f"Signing key initialized: {environment}")
