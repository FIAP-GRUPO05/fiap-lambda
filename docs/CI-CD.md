# CI/CD e operacao na AWS TWM

Cada repositorio usa um unico `.github/workflows/pipeline.yml`, com jobs dentro
da mesma execucao. Push e atualizacao de PR sao eventos diferentes: o push valida
a branch e o PR valida o resultado proposto para a branch de destino. Nao ha
workflow adicional disparado pelo fechamento do PR; o push do merge faz o deploy
e abre o PR da proxima etapa somente depois do sucesso.

| Evento | Validacao e resultado |
| --- | --- |
| Push `feature/<descricao>` | Build, testes e Terraform; abre PR para develop |
| PR `feature/*` para develop | Build, testes, cobertura >=90% no codigo, seguranca e observabilidade |
| Merge em develop | Repete os gates, implanta codigo no ambiente develop e abre PR para uma nova release |
| PR develop para `release/vX.Y.Z` | Gates anteriores e conexoes reais AWS, API Gateway, JWT, banco e New Relic do ambiente de origem |
| Merge na release | Implanta em homol; a aplicacao executa a regressao HTTPS antes de abrir PR para prod |
| PR release para prod | Gates anteriores, conectividade de homol e regressao; exige revisao humana |
| Merge em prod | Aplica Terraform compartilhado, implanta codigo em prod e verifica o resultado antes de abrir PR para main |
| PR prod para main | Somente Route e merge manual; sem build, testes ou deploy |
| Push `rollback/*` ou `rolback/*` | Abre PR direto para a release ativa enquanto prod estiver a frente de main |

Rotas invalidas falham em Route com as instrucoes corretas. Branches com outros
nomes nao iniciam CI no push. Rulesets remotos ativos exigem PR e os checks
Route/Verify nas branches de ambiente. Prod e main exigem uma aprovacao e nao
permitem bypass. O GitHub App abre os PRs e permite que seus eventos iniciem CI.
O merge de cada etapa continua sendo uma decisao humana.

## Versionamento

A maior release existente define a base do proximo SemVer. `feat:` ou
`feat(escopo):`, assim como a label `semver:minor`, incrementam minor;
`BREAKING CHANGE`, `tipo!:` ou a label `breaking` incrementam major.
Os demais casos incrementam patch. Releases seguem `release/vX.Y.Z`.

## Deploys e recursos compartilhados

A conta e `456687462806`, regiao `sa-east-1`. GitHub Actions usa OIDC e credenciais
temporarias. Integrantes contribuem pelo GitHub sem configurar chaves AWS locais.
Os papeis de PR podem consultar somente a identidade e o probe agregado de
telemetria; nao recebem acesso aos segredos nem permissoes de deploy.

EKS, rede, RDS e API Gateways sao compartilhados para reduzir custo. Os namespaces,
bancos, usuarios, chaves RSA e funcoes separam develop, homol e prod. As alteracoes
estruturais de `infra/platform` (K8s) e `infra/managed` (banco/Lambda) recebem
`terraform plan` e `apply` automaticamente apenas depois do merge na branch prod
do respectivo repositorio. Suas funcoes OIDC aceitam exclusivamente essa branch.
Um merge em develop ou release publica codigo/configuracao do seu ambiente e nao
aplica alteracoes na infraestrutura compartilhada que tambem atende producao.
O bootstrap de IAM/OIDC permanece uma operacao administrativa separada.

O registro ECR da aplicacao e atualizado por Terraform no job de publicacao.
Dashboards e alertas New Relic sao atualizados pelo workflow K8s. Estados no S3
usam criptografia, versionamento e bloqueio `.tflock`. Planos, estados locais e
credenciais nao devem ser adicionados ao Git.

O EKS possui API privada. CodeBuild dentro da VPC instala agentes e faz o deploy;
o workflow aguarda seu resultado e falha se o rollout, banco ou telemetria falhar.
A imagem e imutavel e passa por Trivy antes de ser enviada ao ECR.
A Lambda publica uma versao, faz smoke test e promove o alias live; a falha da
verificacao HTTP final restaura o alias anterior.

No primeiro provisionamento, a ordem e plataforma K8s, banco, Lambda e aplicacao.
O ALB e as chaves JWT exigem o bootstrap descrito nos READMEs. Depois das primeiras
migracoes Flyway, execute novamente o bootstrap de banco para criar o administrador.
As alteracoes futuras seguem os PRs e os jobs descritos acima.

## Validacao real e limites

Foram executadas 72 requisicoes HTTPS por ambiente, com sucesso nas 53 operacoes
publicadas no OpenAPI em develop, homol e prod. A regressao cobre cadastro,
autenticacao CPF, autorizacao, catalogo, estoque, orcamento, recusa, execucao e
entrega da ordem. Ela tambem confirma eventos de negocio e logs correlacionados
no New Relic. Isso cobre as operacoes publicadas; nao representa todos os valores
de entrada ou todos os cenarios de falha possiveis.

Os planos do ECR, RDS, EKS e Lambda foram executados com as funcoes reais do CI e
nao apresentaram diferencas em relacao a AWS. As politicas de Terraform foram
validadas no Access Analyzer. A promocao completa entre branches ainda depende
dos merges humanos dos PRs; os deploys iniciais foram feitos por CLI.

New Relic recebe APM Java, metricas Kubernetes, logs e eventos. Dashboards e
alertas estao provisionados; disponibilidade usa prontidao dos pods. Um monitor
externo de jornada HTTPS e notificacoes reais de alerta ainda sao pontos separados.
E-mail permanece `MAIL_TIPE=NONE`; os testes nao enviam mensagens reais.
Registros sinteticos de ordens de servico usados na regressao ficam identificados
pelo UUID da execucao e preservam o historico, inclusive em prod.

Os dois testes HTTP adicionais da Lambda exigem `API_GATEWAY_URL`,
`E2E_CUSTOMER_CPF` e `E2E_INACTIVE_CUSTOMER_CPF`; sem essas variaveis ficam skipped.
Os CPFs sinteticos fixos existem somente em develop/homol. O regressivo completo
da aplicacao cria seus proprios dados e valida o CPF em todos os ambientes.

Execute `python -m unittest discover -s .github/scripts -p 'test_*.py' -v` para
testar rotas/SemVer localmente. `simulate_flow.py` permanece uma simulacao local;
os gates de promocao usam `verify_external.py` com os servicos reais.
