# Autenticacao serverless - Tech Challenge Fase 3

A Lambda autentica clientes pelo CPF e usuarios internos por e-mail/senha.
Os tres ambientes usam funcoes, chaves RSA e credenciais de banco separadas na
conta AWS TWM `456687462806`, regiao `sa-east-1`.

A raiz Terraform ativa e `infra/managed`. As definicoes anteriores com `LabRole`
foram substituidas. O estado remoto e `fiap/lambda-shared.tfstate`.

## Como funciona

- `POST /auth/customer`: valida e normaliza o CPF, consulta um cliente ACTIVE
  no RDS privado e emite JWT RS256 com `roles=[CUSTOMER]` e `customerId`.
  O CPF nao e incluido no token.
- `POST /auth/login`: confere e-mail e senha bcrypt e emite JWT RS256.
- `GET /.well-known/openid-configuration` e `GET /.well-known/jwks.json`:
  publicam metadados e somente a chave publica para validacao dos tokens.
- O API Gateway valida emissor, audiencia e assinatura nas rotas protegidas
  antes de encaminhar ao backend pelo VPC Link e pelo ALB interno compartilhado.
- A API Java aplica a autorizacao de negocio, incluindo isolamento das ordens
  de servico de cada cliente.

Cada Lambda le apenas o segredo de banco e a chave de assinatura de seu ambiente.
As senhas e chaves privadas ficam no Secrets Manager. A conexao PostgreSQL usa TLS.
CloudWatch tem retencao de 14 dias para funcoes e API Gateways.

`codeemail` preserva o adaptador SMTP e seus testes. O deploy atual usa
`MAIL_TIPE=NONE` na API enquanto as notificacoes reais estiverem em validacao.
Nenhum teste desta configuracao envia e-mails reais.

## Contribuir e testar

```powershell
python -m pip install -r requirements.txt coverage
python -m unittest discover -s tests -v
python -m coverage run --source=codetoken,codeemail -m unittest discover -s tests
python -m coverage report --fail-under=90
python -m unittest discover -s .github/scripts -p 'test_*.py' -v
```

Use Python 3.12. Os testes HTTP adicionais usam `API_GATEWAY_URL`,
`E2E_CUSTOMER_CPF` e `E2E_INACTIVE_CUSTOMER_CPF` quando houver dados de teste
controlados no ambiente; sem eles, esses dois testes ficam explicitamente skipped.

## Provisionar por CLI (administracao)

O EKS/RDS precisam estar provisionados pelos repositorios `fiap-k8s` e
`fiap-database`. Gere as dependencias Linux com a imagem oficial da Lambda:

```powershell
docker run --rm --entrypoint /bin/sh --mount "type=bind,source=$((Get-Location).Path),target=/work" public.ecr.aws/lambda/python:3.12 -c 'python -m pip install --no-cache-dir --no-compile --target /work/build/token-package -r /work/requirements.txt && cp /work/codetoken/main.py /work/build/token-package/main.py'
$env:AWS_PROFILE = '<perfil-administrador>'
terraform -chdir=infra/managed init -backend-config=backend.hcl
terraform -chdir=infra/managed plan
terraform -chdir=infra/managed apply
terraform -chdir=infra/managed output -json runtime_config
```

No primeiro bootstrap, antes de existir o ALB, aplique com
`-var=enable_backend_proxy=false`. Inicialize as chaves pelo workflow manual em
uma branch autorizada e depois aplique novamente com o valor padrao `true`.
O resultado `runtime_config` tambem configura a variavel de repositorio
`FIAP_RUNTIME_CONFIG` da aplicacao, sem conter credenciais.

## CI/CD e chaves

O fluxo e `feature/* -> develop -> release/vX.Y.Z -> prod -> main`. O mesmo
workflow valida build, testes, cobertura, seguranca e Terraform. Os merges dos
ambientes disparam o deploy por OIDC e a promocao seguinte depende de seu sucesso.
`prod -> main` segue como merge simples.

O job manual `Bootstrap signing keys` importa a chave de producao do secret
`JWT_PRIVATE_KEY` ja configurado no GitHub e cria chaves independentes para
desenvolvimento e homologacao. Uma chave desses ambientes ja inicializada e
preservada em novas execucoes. Valores privados nao sao impressos nem incluidos
no Git ou no estado Terraform.

No deploy normal, o papel OIDC e limitado a funcao do ambiente da branch.
A esteira publica uma versao Lambda, testa JWKS, validacao de CPF e acesso ao
banco, e promove o alias `live`. Se a verificacao HTTP final falhar, restaura o
alias anterior. Terraform gerencia a infraestrutura; a esteira gerencia codigo
e versao do alias. Integrantes nao precisam de chaves AWS locais para contribuir.
