"""Check explicit CloudWatch log retention for authentication and its gateway."""

from pathlib import Path
import re

for file, group in (("authentication.tf", "/aws/lambda/fiap-auth-"), ("gateway.tf", "/aws/apigateway/fiap-"), ("notifications.tf", "/aws/lambda/fiap-email-")):
    terraform = (Path("infra/managed") / file).read_text(encoding="utf-8")
    assert group in terraform, f"Log group ausente em {file}"
    assert re.search(r"retention_in_days\s*=\s*14\b", terraform), f"Retencao ausente em {file}"
print("CloudWatch com retencao explicita para autenticacao e API Gateway nos tres ambientes")
