"""Publish a Lambda version, smoke test it, then promote its live alias."""
import json
import subprocess
import sys
import tempfile
import urllib.request

environment, package = sys.argv[1:]
if environment not in {"develop", "homol", "prod"}:
    raise ValueError("Invalid environment")
function = f"fiap-auth-{environment}"


def aws(*arguments):
    result = subprocess.run(["aws", *arguments, "--output", "json"], capture_output=True, text=True, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


previous = aws("lambda", "get-alias", "--function-name", function, "--name", "live")["FunctionVersion"]
version = aws("lambda", "update-function-code", "--function-name", function,
              "--zip-file", f"fileb://{package}", "--publish")["Version"]
subprocess.run(["aws", "lambda", "wait", "function-updated-v2", "--function-name", function], check=True)
configuration = aws("lambda", "get-function-configuration", "--function-name", function)
issuer = configuration["Environment"]["Variables"]["JWT_ISSUER"]

with tempfile.TemporaryDirectory() as directory:
    from pathlib import Path
    request_path, response_path = Path(directory) / "request.json", Path(directory) / "response.json"
    for route, body, expected in [
        ("GET /.well-known/jwks.json", None, {200}),
        ("POST /auth/customer", {"cpf": "invalid"}, {400}),
        ("POST /auth/customer", {"cpf": "52998224725"}, {200, 401, 403}),
    ]:
        request_path.write_text(json.dumps({"routeKey": route, "body": json.dumps(body) if body else ""}))
        result = aws("lambda", "invoke", "--function-name", function, "--qualifier", version,
            "--cli-binary-format", "raw-in-base64-out", "--payload", f"file://{request_path}", str(response_path))
        response = json.loads(response_path.read_text())
        if result.get("FunctionError") or response.get("statusCode") not in expected:
            raise RuntimeError(f"Lambda smoke test failed: {route}; inspect CloudWatch without logging credentials")
        if route.startswith("GET"):
            key = json.loads(response["body"])["keys"][0]
            if "d" in key or key.get("alg") != "RS256":
                raise RuntimeError("Invalid public JWKS document")

aws("lambda", "update-alias", "--function-name", function, "--name", "live", "--function-version", version)
try:
    with urllib.request.urlopen(issuer + "/.well-known/jwks.json", timeout=30) as response:
        if response.status != 200 or not json.load(response).get("keys"):
            raise RuntimeError("API Gateway JWKS check failed")
except Exception:
    aws("lambda", "update-alias", "--function-name", function, "--name", "live", "--function-version", previous)
    raise
print(f"Lambda deployed and verified: {environment}, version {version}, previous {previous}")
