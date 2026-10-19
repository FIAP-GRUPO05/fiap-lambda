"""Read-only checks against the deployed source environment before promotion."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request

source = os.environ.get("SOURCE_BRANCH", "develop")
environment = "homol" if source.startswith("release/") else "develop"
base = json.loads(os.environ["FIAP_RUNTIME_CONFIG"])[environment]["api_url"]
for path in ("/actuator/health", "/.well-known/openid-configuration", "/.well-known/jwks.json"):
    with urllib.request.urlopen(base + path, timeout=30) as response:
        result = json.load(response)
    if path.endswith("health") and result.get("status") != "UP":
        raise RuntimeError("Application/database health is not UP")
    if path.endswith("openid-configuration") and result.get("issuer") != base:
        raise RuntimeError("Unexpected JWT issuer")
    if path.endswith("jwks.json") and (not result.get("keys") or any("d" in key for key in result["keys"])):
        raise RuntimeError("Invalid public JWKS")
with tempfile.TemporaryDirectory() as directory:
    request, response = Path(directory) / "request.json", Path(directory) / "response.json"
    request.write_text(json.dumps({"environment": environment, "require_apm": True}))
    metadata = json.loads(subprocess.run(["aws", "lambda", "invoke", "--function-name", "fiap-observability-probe",
        "--cli-binary-format", "raw-in-base64-out", "--payload", f"file://{request}", str(response), "--output", "json"],
        capture_output=True, text=True, check=True).stdout)
    result = json.loads(response.read_text())
    if metadata.get("FunctionError") or not result.get("healthy"):
        raise RuntimeError("Real New Relic cluster/APM telemetry check failed")
print(f"AWS, HTTPS Gateway, JWT discovery, database health and real New Relic telemetry verified: {environment}")
