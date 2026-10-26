"""Publish notification code and move live only after a verified-SES health check."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def deploy(environment, package, run=subprocess.run):
    if environment not in {"develop", "homol", "prod"}:
        raise ValueError("Invalid environment")
    function = f"fiap-email-{environment}"

    def aws(*args):
        result = run(["aws", *args, "--output", "json"], capture_output=True, text=True, check=True)
        return json.loads(result.stdout) if result.stdout.strip() else {}

    previous = aws("lambda", "get-alias", "--function-name", function, "--name", "live")["FunctionVersion"]
    version = aws("lambda", "update-function-code", "--function-name", function,
                  "--zip-file", "fileb://" + package, "--publish")["Version"]
    aws("lambda", "wait", "function-updated-v2", "--function-name", function)
    with tempfile.TemporaryDirectory() as directory:
        request, response = Path(directory) / "request.json", Path(directory) / "response.json"
        request.write_text(json.dumps({"operation": "health"}), encoding="utf-8")
        result = aws("lambda", "invoke", "--function-name", function, "--qualifier", version,
                     "--cli-binary-format", "raw-in-base64-out", "--payload", "file://" + str(request), str(response))
        health = json.loads(response.read_text(encoding="utf-8"))
        if result.get("FunctionError") or not health.get("ready") or health.get("provider") != "SES":
            raise RuntimeError("Notification health failed; previous live alias preserved; verify SES identity")
    aws("lambda", "update-alias", "--function-name", function, "--name", "live", "--function-version", version)
    print(f"Notifications deployed: {environment}; version {version}; previous {previous}; SES verified")


if __name__ == "__main__":
    deploy(*sys.argv[1:])
