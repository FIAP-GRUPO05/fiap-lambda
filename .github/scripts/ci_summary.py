"""Summarize executed code checks without claiming deployment validation."""
import json
import os
from pathlib import Path


def render(state, status, steps):
    icons = {"success": "✅", "failure": "❌", "cancelled": "⚠️", "skipped": "⏸️"}
    lines = ["## Validação da esteira", "", f"Estado da infraestrutura: `{state}`.",
             f"Resultado das verificações: `{status}`.", "",
             "| Verificação | Resultado |", "|---|---|"]
    for step in steps:
        name = str(step["name"]).replace("|", "\\|").replace("\n", " ")
        result = step.get("outcome") or "não executada"
        lines.append(f"| {name} | {icons.get(result, '⚠️')} {result} |")
    if state != "active":
        lines += ["", "### Validações externas pendentes", "",
                  "- ⏸️ Identidade e conectividade AWS dos ambientes.",
                  "- ⏸️ Telemetria real de New Relic e saúde do banco/API.",
                  "- ⏸️ Regressão HTTP dos endpoints implantados e rollout.",
                  "", "As verificações acima não foram executadas nem aprovadas por esta execução.",
                  "Deploys e alterações de infraestrutura permanecem bloqueados."]
        if state == "maintenance":
            lines += ["A abertura do próximo PR depende do sucesso das verificações de código; o merge é manual."]
        else:
            lines += ["As promoções entre ambientes permanecem bloqueadas durante/após a desmontagem."]
    else:
        lines += ["", "Este resumo cobre os passos listados. O resultado do deploy e rollout pertence aos respectivos jobs."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    summary = render(os.environ["FIAP_INFRA_STATE"], os.environ["CI_JOB_STATUS"],
                     json.loads(os.environ["CI_VALIDATION_STEPS"]))
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
        output.write(summary)
