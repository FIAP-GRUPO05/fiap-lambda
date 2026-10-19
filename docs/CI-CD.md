# Fluxo de CI/CD da Fase 3

Cada repositório contém apenas `.github/workflows/pipeline.yml`. Cada evento abre uma execução da Action, com jobs e etapas dentro dela.

| Evento | Gate | Resultado |
| --- | --- | --- |
| Push `feature/<descricao>` | Build, testes e `terraform validate` onde houver Terraform | PR automático para `develop` |
| PR `feature/*` → `develop` | Build, testes, cobertura mínima de 90% nos repositórios com código, Trivy e observabilidade | Merge manual após checks; o merge abre PR para `release/vX.Y.Z` |
| PR `develop` → `release/vX.Y.Z` | Os gates anteriores e contratos AWS/New Relic simulados localmente | Merge manual; o merge abre PR para `prod` |
| PR `release/vX.Y.Z` → `prod` | Gates anteriores e regressão disponível | Merge manual; o merge abre PR para `main` |
| PR `prod` → `main` | Só validação de rota, sem build, testes ou deploy | Merge manual |
| Push `rollback/<descricao>` (também aceita `rolback/<descricao>`) | Sem esteira de build | PR direto para a release ativa enquanto `prod` estiver à frente de `main` |

PRs de rota inválida falham no job `Route` com mensagem de correção. Branches fora de `feature/*`, `rollback/*` e `rolback/*` não disparam o CI em push. As regras versionadas em `.github/rulesets/` precisam ser instaladas nas configurações de cada repositório GitHub para impedir o merge antes dos checks. Os arquivos JSON sozinhos não aplicam proteção remota.

## Versionamento

O nome da release segue SemVer. O próximo número é calculado a partir da maior branch `release/vX.Y.Z`. O PR integrado em `develop` usa a label `semver:minor` ou título `feat:` para subir o minor; `breaking` ou título com `!:` / `BREAKING CHANGE` sobe o major. Os demais casos sobem o patch. Exemplos: `v0.1.2` → `v0.1.3` para correção e `v0.1.2` → `v0.2.0` para funcionalidade.

`prod` deve ser criado a partir de `main` uma vez, no início. Os PRs sempre são criados automaticamente, mas o merge é manual. A automação não executa `terraform apply`, publica imagem nem implanta na AWS nesta fase de simulação.

## Limites da validação atual

- O teste de conectividade usa um servidor HTTP local que representa AWS e New Relic. Ele valida o contrato de requisição/resposta, não uma conta real.
- A regressão Java atual percorre os mappings registrados e verifica que cada rota responde ao método HTTP. Ela ainda não prova o comportamento de negócio de 100% dos endpoints. Os testes de integração existentes cobrem fluxos funcionais específicos.
- A Lambda tem dois testes E2E que exigem um API Gateway implantado; ficam ignorados na simulação. Há testes unitários de autenticação e e-mail.
- Regras de proteção, a opção do GitHub Actions para criar PRs, permissões `contents:write`/`pull-requests:write` e uma identidade de automação própria precisam ser configuradas no GitHub. PRs criados com o `GITHUB_TOKEN` podem exigir aprovação antes da execução do evento seguinte.
- O primeiro merge desta mudança em `develop` é uma implantação inicial da nova política. O workflow de PR usa a versão presente na branch de destino; valide esse merge inicial com a proteção atual e instale as novas regras em seguida.

## Verificação local

Execute `python .github/scripts/simulate_flow.py` em qualquer repositório para simular as promoções, o rollback, o SemVer e rotas inválidas sem acessar serviços externos. Execute os testes de cada projeto para medir os gates reais.
