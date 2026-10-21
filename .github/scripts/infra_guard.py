"""Live S3 maintenance gate before AWS writes. Missing backend fails closed."""
import json
import os
from pathlib import Path
import subprocess
import tempfile


def check():
    if os.environ.get("FIAP_INFRA_STATE", "active") != "active":
        raise SystemExit("Infraestrutura em manutenção/desmontada; publicação bloqueada.")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        process = subprocess.run(["aws", "s3api", "get-object", "--bucket", "fiap-tfstate-456687462806",
            "--key", "fiap/operations/state.json", "--region", "sa-east-1", str(path), "--output", "json", "--no-cli-pager"],
            capture_output=True, text=True)
        if process.returncode:
            raise SystemExit("Não foi possível confirmar estado active no controle AWS; publicação bloqueada.")
        if json.loads(path.read_text())["state"] != "active":
            raise SystemExit("Controle central bloqueia publicação da infraestrutura.")
    print("Controle central ativo; publicação permitida.")


if __name__ == "__main__":
    check()
