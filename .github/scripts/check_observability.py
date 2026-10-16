"""Check that both Lambdas have explicit CloudWatch log retention."""

from pathlib import Path

terraform = (Path("observability.tf")).read_text(encoding="utf-8")
for name in ("lambda-token", "lambda-email"):
    assert f"/aws/lambda/{name}" in terraform, f"Log group ausente: {name}"
assert terraform.count("retention_in_days") == 2
print("CloudWatch log groups e retenção configurados para as duas Lambdas")
